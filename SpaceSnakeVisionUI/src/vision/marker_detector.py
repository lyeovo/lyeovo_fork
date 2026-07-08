from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import yaml
from scipy.spatial.distance import cdist
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation

from ..camera.base_camera import CameraFrame
from ..models import DetectedObject, Euler, Pose3D, Quaternion, Vector3
from .detector_base import DetectorBase


class MarkerTemplateDetector(DetectorBase):
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.marker_root = self.project_root.parent / "snake_vision_d405_target"
        self.runtime_config = _load_yaml(self.marker_root / "config" / "runtime_config.yaml")
        self.database = _load_yaml(self.marker_root / "config" / "target_database.yaml")
        self.circle_cfg = dict(self.runtime_config.get("circle_detection", {}))
        marker_cfg = self.runtime_config.get("marker_detection", {})
        self.circle_cfg["use_roi"] = bool(marker_cfg.get("use_roi", False))
        self.max_candidates = int(marker_cfg.get("max_candidates", 240))
        self.min_dots = int(self.runtime_config.get("target_learning", {}).get("min_dots", 6))
        self.max_dots = int(self.runtime_config.get("target_learning", {}).get("max_dots", 12))
        self.cluster_radius_px = float(marker_cfg.get("cluster_radius_px", 90.0))
        self.min_cluster_span_px = float(marker_cfg.get("min_cluster_span_px", 12.0))
        self.max_cluster_span_px = float(marker_cfg.get("max_cluster_span_px", 240.0))
        self.max_clusters = int(marker_cfg.get("max_clusters", 8))
        self.max_match_error_m = float(self.runtime_config.get("target_matching", {}).get("max_match_error_m", 0.015))
        self.unknown_if_error_larger = bool(self.runtime_config.get("target_matching", {}).get("unknown_if_error_larger", True))
        self.allow_rotation = bool(self.runtime_config.get("target_matching", {}).get("allow_rotation", True))
        self._last_quat_by_target: dict[str, np.ndarray] = {}
        self._last_bearing_object: DetectedObject | None = None
        self._missed_frames = 0
        self.lost_after_frames = int(marker_cfg.get("lost_after_frames", 5))
        self.last_message = f"Marker detector loaded {len(self.database.get('targets', {}))} templates"

    def detect(self, frame: CameraFrame) -> list[DetectedObject]:
        gray = cv2.cvtColor(frame.color_image, cv2.COLOR_BGR2GRAY) if frame.color_image.ndim == 3 else frame.color_image
        dots = _detect_circles(gray, self.circle_cfg, self.max_candidates)
        clusters = _cluster_dots(
            dots,
            self.cluster_radius_px,
            2,
            self.max_dots,
            self.min_cluster_span_px,
            self.max_cluster_span_px,
            self.max_clusters,
        )
        if not clusters and len(dots) >= 2:
            clusters = [_nearest_dot_group(dots, self.max_dots)]
        detections = []
        for idx, cluster in enumerate(clusters):
            points_3d, valid_dots = _points_from_depth(cluster, frame.depth_image, frame.intrinsics)
            bearing = _bearing_from_dots(cluster, frame.intrinsics)
            bbox = _bbox_from_dots(cluster, gray.shape[1], gray.shape[0])
            center = [int(round(bearing["pixel_center"][0])), int(round(bearing["pixel_center"][1]))]
            stable_id = f"bearing_marker_{idx + 1}"
            pose = Pose3D(frame_id="camera_left", position=Vector3(), orientation_quat=Quaternion())
            depth_m = None
            match_error = None
            plane_rmse = None
            pose_rmse = None
            pose_method = None
            confidence = _bearing_confidence(len(cluster), len(valid_dots))
            status = "PARTIAL_DEPTH" if 0 < len(points_3d) < self.min_dots else "BEARING_ONLY"

            if len(points_3d) < self.min_dots:
                obj = self._make_detection(
                    stable_id,
                    "encoded_marker_bearing",
                    "encoded marker bearing",
                    frame.timestamp,
                    confidence,
                    bbox,
                    center,
                    depth_m,
                    pose,
                    status,
                    len(cluster),
                    len(valid_dots),
                    bearing,
                    match_error,
                    plane_rmse,
                    pose_rmse,
                    pose_method,
                )
                detections.append(obj)
                continue
            try:
                target_id, match_error, matched_template, matched_measured, plane_rmse = _match_template(
                    points_3d,
                    self.database.get("targets", {}),
                    self.max_match_error_m,
                    self.allow_rotation,
                    self.unknown_if_error_larger,
                )
                position, quat, pose_rmse, pose_method = _estimate_pose(matched_template, matched_measured, points_3d)
                stable_id = target_id if target_id != "unknown" else f"unknown_marker_{idx + 1}"
                quat = self._stabilize_quaternion(stable_id, quat)
            except Exception as exc:
                self.last_message = f"Marker detection skipped unstable cluster: {exc}"
                continue
            confidence = _confidence(len(valid_dots), len(cluster), match_error, plane_rmse, pose_rmse)
            status = "POSE_6DOF" if target_id != "unknown" and confidence >= 0.6 else "PARTIAL_DEPTH"
            euler = Rotation.from_quat(quat).as_euler("xyz", degrees=False)
            pose = Pose3D(
                frame_id="camera_left",
                position=Vector3(float(position[0]), float(position[1]), float(position[2])),
                orientation_euler=Euler(float(euler[0]), float(euler[1]), float(euler[2])),
                orientation_quat=Quaternion(float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])),
            )
            detections.append(
                self._make_detection(
                    stable_id,
                    "encoded_marker",
                    target_id if target_id != "unknown" else "unknown encoded marker",
                    frame.timestamp,
                    confidence,
                    bbox,
                    center,
                    float(position[2]),
                    pose,
                    status,
                    len(cluster),
                    len(valid_dots),
                    bearing,
                    match_error,
                    plane_rmse,
                    pose_rmse,
                    pose_method,
                )
            )
        if detections:
            self._missed_frames = 0
            self._last_bearing_object = detections[0]
            ids = ", ".join(obj.target_id for obj in detections)
            states = ", ".join(obj.status for obj in detections)
            self.last_message = f"Marker full-FOV capture: {len(detections)} target(s): {ids} [{states}]"
            return detections
        self._missed_frames += 1
        if self._last_bearing_object is not None and self._missed_frames <= self.lost_after_frames:
            lost = self._clone_lost(frame.timestamp)
            self.last_message = f"Marker target LOST, holding last bearing for {self._missed_frames}/{self.lost_after_frames}"
            return [lost]
        if self._last_bearing_object is None:
            self.last_message = f"Marker SEARCH: no target, dots={len(dots)}, clusters={len(clusters)}"
        else:
            self.last_message = f"Marker SEARCH: target absent, dots={len(dots)}, clusters={len(clusters)}"
        return []

    def _make_detection(
        self,
        target_id,
        class_name,
        display_name,
        timestamp,
        confidence,
        bbox,
        center,
        depth_m,
        pose,
        status,
        num_dots,
        valid_depth_points,
        bearing,
        match_error,
        plane_rmse,
        pose_rmse,
        pose_method,
    ):
        obj = DetectedObject(
            target_id=target_id,
            timestamp=timestamp,
            class_name=class_name,
            display_name=display_name,
            detection_mode="marker",
            marker_id=None,
            confidence=confidence,
            stability_score=confidence,
            bbox_xyxy=bbox,
            center_pixel=center,
            depth_m=depth_m,
            pose_camera=pose,
            status=status,
        )
        obj.bearing = bearing
        obj.quality = {
            "num_dots": num_dots,
            "valid_depth_points": valid_depth_points,
            "confidence": confidence,
            "bearing": bearing,
            "pose_available": status == "POSE_6DOF",
            "match_error_m": match_error,
            "plane_rmse_m": plane_rmse,
            "pose_rmse_m": pose_rmse,
            "pose_method": pose_method,
            "json_status": status,
            "pose": None if status != "POSE_6DOF" else {
                "position": {"x": pose.position.x, "y": pose.position.y, "z": pose.position.z},
                "orientation": {
                    "qx": pose.orientation_quat.x,
                    "qy": pose.orientation_quat.y,
                    "qz": pose.orientation_quat.z,
                    "qw": pose.orientation_quat.w,
                },
            },
        }
        return obj

    def _clone_lost(self, timestamp):
        last = self._last_bearing_object
        obj = self._make_detection(
            last.target_id,
            last.class_name,
            last.display_name,
            timestamp,
            max(0.2, last.confidence * 0.5),
            last.bbox_xyxy,
            last.center_pixel,
            None,
            Pose3D(frame_id="camera_left", position=Vector3(), orientation_quat=Quaternion()),
            "LOST",
            last.quality.get("num_dots", 0),
            last.quality.get("valid_depth_points", 0),
            last.quality.get("bearing"),
            None,
            None,
            None,
            None,
        )
        obj.quality["last_seen_bearing"] = last.quality.get("bearing")
        return obj

    def _stabilize_quaternion(self, target_id: str, quat) -> np.ndarray:
        quat = np.asarray(quat, dtype=float)
        last = self._last_quat_by_target.get(target_id)
        if last is not None and np.dot(last, quat) < 0:
            quat = -quat
        self._last_quat_by_target[target_id] = quat
        return quat


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _detect_circles(gray, cfg, max_candidates=240):
    work = gray
    x0 = y0 = 0
    if cfg.get("use_roi") and cfg.get("left_roi"):
        x0, y0, w, h = [int(v) for v in cfg["left_roi"]]
        work = gray[y0 : y0 + h, x0 : x0 + w]
    kernel_size = int(cfg.get("gaussian_kernel", 3))
    kernel_size = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
    blur = cv2.GaussianBlur(work, (kernel_size, kernel_size), 0)
    mode = cv2.THRESH_BINARY_INV if cfg.get("binary_inverse", False) else cv2.THRESH_BINARY
    if cfg.get("threshold_mode") == "manual":
        _, binary = cv2.threshold(blur, float(cfg.get("threshold_value", 35)), 255, mode)
    else:
        _, binary = cv2.threshold(blur, 0, 255, mode + cv2.THRESH_OTSU)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    dots = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < float(cfg.get("min_area", 30)) or area > float(cfg.get("max_area", 300)):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / float(h) if h else 0.0
        if aspect < float(cfg.get("min_aspect", 0.6)) or aspect > float(cfg.get("max_aspect", 1.4)):
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 1e-6:
            continue
        circularity = 4.0 * np.pi * area / (perimeter * perimeter)
        if circularity < float(cfg.get("min_circularity", 0.75)):
            continue
        moments = cv2.moments(contour)
        if abs(moments["m00"]) < 1e-6:
            continue
        dots.append(
            {
                "center": (float(moments["m10"] / moments["m00"] + x0), float(moments["m01"] / moments["m00"] + y0)),
                "area": float(area),
                "circularity": float(circularity),
            }
        )
    dots = sorted(dots, key=lambda item: (-item["circularity"], abs(item["area"] - 155.0)))
    return [item["center"] for item in dots[:max_candidates]]


def _cluster_dots(dots, radius_px, min_dots, max_dots, min_span_px=12.0, max_span_px=240.0, max_clusters=8):
    if not dots:
        return []
    pts = np.asarray(dots, dtype=float)
    dist = cdist(pts, pts)
    seen = set()
    clusters = []
    for start in range(len(pts)):
        if start in seen:
            continue
        stack = [start]
        group = []
        seen.add(start)
        while stack:
            i = stack.pop()
            group.append(i)
            for j in np.where(dist[i] <= radius_px)[0]:
                if int(j) not in seen:
                    seen.add(int(j))
                    stack.append(int(j))
        if min_dots <= len(group) <= max_dots:
            cluster = [tuple(pts[i]) for i in group]
            span_x = max(p[0] for p in cluster) - min(p[0] for p in cluster)
            span_y = max(p[1] for p in cluster) - min(p[1] for p in cluster)
            span = max(span_x, span_y)
            if min_span_px <= span <= max_span_px:
                clusters.append(cluster)
    clusters = sorted(clusters, key=lambda cluster: abs(len(cluster) - 8))
    return clusters[:max_clusters]


def _nearest_dot_group(dots, max_dots):
    pts = np.asarray(dots, dtype=float)
    center = np.mean(pts, axis=0)
    order = np.argsort(np.linalg.norm(pts - center, axis=1))
    return [tuple(pts[i]) for i in order[:max(2, min(max_dots, len(order)))]]


def _bearing_from_dots(dots, intr):
    pts = np.asarray(dots, dtype=float)
    center = np.mean(pts, axis=0)
    du = float(center[0] - intr.cx)
    dv = float(center[1] - intr.cy)
    x_norm = du / float(intr.fx)
    y_norm = dv / float(intr.fy)
    ray = np.array([x_norm, y_norm, 1.0], dtype=float)
    ray = ray / np.linalg.norm(ray)
    return {
        "pixel_center": [float(center[0]), float(center[1])],
        "pixel_error": [du, dv],
        "ray_camera": [float(ray[0]), float(ray[1]), float(ray[2])],
    }


def _median_depth(depth_image, u, v, radius=2):
    if depth_image is None:
        return None
    h, w = depth_image.shape[:2]
    x0, x1 = max(0, int(round(u)) - radius), min(w, int(round(u)) + radius + 1)
    y0, y1 = max(0, int(round(v)) - radius), min(h, int(round(v)) + radius + 1)
    patch = depth_image[y0:y1, x0:x1].reshape(-1)
    valid = patch[np.isfinite(patch) & (patch > 0.001)]
    return float(np.median(valid)) if valid.size >= 3 else None


def _points_from_depth(dots, depth_image, intr):
    points = []
    valid = []
    for u, v in dots:
        z = _median_depth(depth_image, u, v)
        if z is None:
            continue
        x = (u - intr.cx) * z / intr.fx
        y = (v - intr.cy) * z / intr.fy
        points.append([x, y, z])
        valid.append((u, v))
    return np.asarray(points, dtype=float), valid


def _local_2d(points_3d):
    points = np.asarray(points_3d, dtype=float)
    center = np.mean(points, axis=0)
    centered = points - center
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    x_axis = vt[0] / np.linalg.norm(vt[0])
    y_axis = vt[1] / np.linalg.norm(vt[1])
    if x_axis[0] < 0:
        x_axis *= -1.0
    if y_axis[1] < 0:
        y_axis *= -1.0
    normal = np.cross(x_axis, y_axis)
    normal = normal / np.linalg.norm(normal)
    if normal[2] > 0:
        normal *= -1.0
        y_axis *= -1.0
    y_axis = np.cross(normal, x_axis)
    rotation = np.column_stack([x_axis, y_axis, normal])
    local = (rotation.T @ centered.T).T
    rmse = float(np.sqrt(np.mean((centered @ normal) ** 2)))
    points_2d = local[:, :2]
    points_2d -= np.mean(points_2d, axis=0)
    return points_2d, rmse


def _best_chamfer(observed_2d, template_2d, allow_rotation):
    angles = np.linspace(0, 2 * np.pi, 72, endpoint=False) if allow_rotation else [0.0]
    best = (float("inf"), None)
    mirrors = [np.array([1.0, 1.0]), np.array([-1.0, 1.0]), np.array([1.0, -1.0]), np.array([-1.0, -1.0])]
    for angle in angles:
        c, s = np.cos(angle), np.sin(angle)
        rot = np.array([[c, -s], [s, c]], dtype=float)
        for mirror in mirrors:
            obs = (observed_2d * mirror) @ rot.T
            dist = cdist(obs, template_2d)
            if len(obs) <= len(template_2d):
                obs_idx, template_idx = linear_sum_assignment(dist)
                one_to_one = np.full(len(obs), -1, dtype=int)
                one_to_one[obs_idx] = template_idx
                assigned_error = float(np.mean(dist[obs_idx, template_idx]))
            else:
                template_idx, obs_idx = linear_sum_assignment(dist.T)
                one_to_one = np.full(len(obs), -1, dtype=int)
                one_to_one[obs_idx] = template_idx
                assigned_error = float(np.mean(dist[obs_idx, template_idx]))
            chamfer_error = float((np.mean(np.min(dist, axis=1)) + np.mean(np.min(dist, axis=0))) / 2.0)
            error = 0.5 * chamfer_error + 0.5 * assigned_error
            if error < best[0]:
                best = (error, one_to_one)
    return best


def _match_template(points_3d, targets, max_error, allow_rotation, unknown_if_error_larger):
    observed_2d, plane_rmse = _local_2d(points_3d)
    observed_signature = _distance_signature(observed_2d)
    best = None
    for target_id, target in targets.items():
        template = np.asarray(target.get("template_points", []), dtype=float)
        if len(template) < 3:
            continue
        chamfer_error, nearest = _best_chamfer(observed_2d, template[:, :2], allow_rotation)
        signature_error = _signature_error(observed_signature, _distance_signature(template[:, :2]))
        error = 0.6 * signature_error + 0.4 * chamfer_error
        if best is None or error < best[0]:
            best = (error, target_id, template, nearest)
    if best is None:
        raise ValueError("target database is empty")
    error, target_id, template, nearest = best
    if unknown_if_error_larger and error > max_error:
        target_id = "unknown"
    measured = np.asarray(points_3d, dtype=float)
    valid = np.asarray(nearest, dtype=int) >= 0
    return target_id, float(error), template[np.asarray(nearest)[valid]], measured[valid], float(plane_rmse)


def _distance_signature(points_2d):
    points = np.asarray(points_2d, dtype=float)
    if len(points) < 2:
        return np.empty((0,), dtype=float)
    upper = np.triu_indices(len(points), k=1)
    return np.sort(cdist(points, points)[upper])


def _signature_error(a, b):
    if len(a) == 0 or len(b) == 0:
        return float("inf")
    n = min(len(a), len(b))
    return float(np.mean(np.abs(a[:n] - b[:n])))


def _estimate_pose(template_points, measured_points, fallback_points):
    try:
        template = np.asarray(template_points, dtype=float)
        measured = np.asarray(measured_points, dtype=float)
        tc = np.mean(template, axis=0)
        mc = np.mean(measured, axis=0)
        h = (template - tc).T @ (measured - mc)
        u, _, vt = np.linalg.svd(h)
        rotation = vt.T @ u.T
        if np.linalg.det(rotation) < 0:
            vt[-1, :] *= -1.0
            rotation = vt.T @ u.T
        translation = mc - rotation @ tc
        transformed = (rotation @ template.T).T + translation
        rmse = float(math.sqrt(np.mean(np.sum((transformed - measured) ** 2, axis=1))))
        return translation, Rotation.from_matrix(rotation).as_quat(), rmse, "template_kabsch"
    except Exception:
        points = np.asarray(fallback_points, dtype=float)
        center = np.mean(points, axis=0)
        _, _, vt = np.linalg.svd(points - center, full_matrices=False)
        rotation = np.column_stack([vt[0], vt[1], np.cross(vt[0], vt[1])])
        return center, Rotation.from_matrix(rotation).as_quat(), None, "pca_fallback"


def _confidence(valid_depth_points, num_dots, match_error_m, plane_rmse_m, pose_rmse_m):
    score = valid_depth_points / float(max(num_dots, 1))
    score *= float(np.exp(-match_error_m / 0.015))
    score *= float(np.exp(-plane_rmse_m / 0.01))
    if pose_rmse_m is not None:
        score *= float(np.exp(-pose_rmse_m / 0.01))
    return float(np.clip(score, 0.0, 1.0))


def _bearing_confidence(num_dots, valid_depth_points):
    dot_score = min(1.0, num_dots / 8.0)
    depth_bonus = min(0.25, valid_depth_points / 8.0 * 0.25)
    return float(np.clip(0.35 + 0.4 * dot_score + depth_bonus, 0.0, 0.85))


def _bbox_from_dots(dots, width, height, pad=14):
    xs = [p[0] for p in dots]
    ys = [p[1] for p in dots]
    return [
        max(0, int(min(xs) - pad)),
        max(0, int(min(ys) - pad)),
        min(width - 1, int(max(xs) + pad)),
        min(height - 1, int(max(ys) + pad)),
    ]
