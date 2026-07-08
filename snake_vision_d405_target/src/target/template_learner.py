from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.distance import cdist

from src.target.pose_estimator import project_points_to_local_2d


@dataclass
class LearnedFrame:
    points_2d: np.ndarray
    points_3d_camera: np.ndarray
    plane_rmse_m: float
    depth_valid_ratio: float


def get_median_depth(depth_image, u, v, window_size=5, min_valid=3, depth_scale=1.0):
    h, w = depth_image.shape[:2]
    half = int(window_size) // 2
    x0 = max(0, int(round(u)) - half)
    x1 = min(w, int(round(u)) + half + 1)
    y0 = max(0, int(round(v)) - half)
    y1 = min(h, int(round(v)) + half + 1)
    values = np.asarray(depth_image[y0:y1, x0:x1], dtype=float).reshape(-1)
    values = values[values > 0]
    if len(values) < min_valid:
        return None
    return float(np.median(values) * depth_scale)


def deproject_pixel(u, v, depth_m, intrinsics):
    if isinstance(intrinsics, dict):
        fx = float(intrinsics["fx"])
        fy = float(intrinsics["fy"])
        cx = float(intrinsics.get("cx", intrinsics.get("ppx")))
        cy = float(intrinsics.get("cy", intrinsics.get("ppy")))
    else:
        fx = float(intrinsics.fx)
        fy = float(intrinsics.fy)
        cx = float(intrinsics.ppx)
        cy = float(intrinsics.ppy)
    return [(float(u) - cx) * depth_m / fx, (float(v) - cy) * depth_m / fy, depth_m]


def points_3d_from_dots(dots_2d, depth_image, intrinsics, window_size=5, depth_scale=1.0, min_depth_m=0.1, max_depth_m=1.5):
    points = []
    valid_dots = []
    for dot in dots_2d:
        if hasattr(dot, "u") and hasattr(dot, "v"):
            u = dot.u
            v = dot.v
        else:
            u = dot[0]
            v = dot[1]
        z = get_median_depth(depth_image, u, v, window_size=window_size, depth_scale=depth_scale)
        if z is None or z < min_depth_m or z > max_depth_m:
            continue
        points.append(deproject_pixel(u, v, z, intrinsics))
        valid_dots.append((float(u), float(v)))
    return np.asarray(points, dtype=float), valid_dots


def learn_frame(points_3d_camera):
    points = np.asarray(points_3d_camera, dtype=float)
    local_2d, _, _, _, plane_rmse = project_points_to_local_2d(points)
    order = np.lexsort((local_2d[:, 0], local_2d[:, 1]))
    return local_2d[order], points[order], float(plane_rmse)


def _procrustes_no_scale(source, target):
    source_c = source - np.mean(source, axis=0)
    target_c = target - np.mean(target, axis=0)
    u, _, vt = np.linalg.svd(source_c.T @ target_c)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1.0
        r = u @ vt
    return source_c @ r


def fuse_frames(frames, max_frame_match_error_m=0.02):
    if not frames:
        raise ValueError("No valid frames to fuse")
    reference = np.asarray(frames[0].points_2d, dtype=float)
    buckets = [[p] for p in reference]
    used = [frames[0]]
    rejected = 0
    for frame in frames[1:]:
        current = np.asarray(frame.points_2d, dtype=float)
        if abs(len(current) - len(reference)) > 2:
            rejected += 1
            continue
        aligned = _procrustes_no_scale(current, reference)
        dist = cdist(aligned, reference)
        nearest = np.argmin(dist, axis=1)
        error = float(np.mean(np.min(dist, axis=1)))
        if error > max_frame_match_error_m:
            rejected += 1
            continue
        for i, ref_idx in enumerate(nearest):
            buckets[int(ref_idx)].append(aligned[i])
        used.append(frame)
    final = np.asarray([np.mean(bucket, axis=0) for bucket in buckets], dtype=float)
    final -= np.mean(final, axis=0)
    final_3d = np.column_stack([final, np.zeros(len(final))])
    return final_3d, used, rejected


def save_learning_debug(debug_dir, frame_index, ir_image=None, dots=None, valid_dots=None, local_points_2d=None):
    debug_dir = Path(debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)
    if ir_image is not None:
        cv2.imwrite(str(debug_dir / f"frame_{frame_index:04d}_ir.png"), ir_image)
        vis = cv2.cvtColor(ir_image, cv2.COLOR_GRAY2BGR) if ir_image.ndim == 2 else ir_image.copy()
        for dot in dots or []:
            cv2.circle(vis, (int(round(dot.u)), int(round(dot.v))), 4, (0, 255, 0), 1)
        cv2.imwrite(str(debug_dir / f"frame_{frame_index:04d}_dots.png"), vis)
        depth_vis = cv2.cvtColor(ir_image, cv2.COLOR_GRAY2BGR) if ir_image.ndim == 2 else ir_image.copy()
        for u, v in valid_dots or []:
            cv2.circle(depth_vis, (int(round(u)), int(round(v))), 4, (0, 255, 255), -1)
        cv2.imwrite(str(debug_dir / f"frame_{frame_index:04d}_depth_valid.png"), depth_vis)
    if local_points_2d is not None and len(local_points_2d):
        canvas = np.full((400, 400, 3), 255, dtype=np.uint8)
        pts = np.asarray(local_points_2d, dtype=float)
        span = max(float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1])), 1e-6)
        pix = (pts / span * 280 + 200).astype(int)
        for x, y in pix:
            cv2.circle(canvas, (int(x), int(y)), 4, (0, 0, 255), -1)
        cv2.imwrite(str(debug_dir / f"frame_{frame_index:04d}_local2d.png"), canvas)
