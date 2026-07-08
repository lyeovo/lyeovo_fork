import math

import numpy as np
from scipy.spatial.transform import Rotation


class PoseSmoother:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.position = None
        self.quaternion = None

    def update(self, position, quaternion):
        position = np.asarray(position, dtype=float)
        self.position = position if self.position is None else (1 - self.alpha) * self.position + self.alpha * position
        self.quaternion = quaternion
        return self.position, quaternion


def fit_plane_svd(points_3d):
    points = np.asarray(points_3d, dtype=float)
    if len(points) < 3:
        raise ValueError("At least 3 points are required to fit a plane")
    center = np.mean(points, axis=0)
    centered = points - center
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    normal = vt[-1] / np.linalg.norm(vt[-1])
    rmse = float(np.sqrt(np.mean((centered @ normal) ** 2)))
    return center, normal, rmse


def local_frame_from_points(points_3d):
    points = np.asarray(points_3d, dtype=float)
    center = np.mean(points, axis=0)
    centered = points - center
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    x_axis = vt[0] / np.linalg.norm(vt[0])
    y_axis = vt[1] / np.linalg.norm(vt[1])
    z_axis = np.cross(x_axis, y_axis)
    z_axis = z_axis / np.linalg.norm(z_axis)
    # Make the normal face roughly toward the camera for stable signs.
    if np.dot(z_axis, center) > 0:
        z_axis *= -1.0
        y_axis *= -1.0
    y_axis = np.cross(z_axis, x_axis)
    y_axis = y_axis / np.linalg.norm(y_axis)
    rotation = np.column_stack([x_axis, y_axis, z_axis])
    if np.linalg.det(rotation) < 0:
        z_axis *= -1.0
        rotation = np.column_stack([x_axis, y_axis, z_axis])
    _, normal, rmse = fit_plane_svd(points)
    return center, rotation, normal, rmse


def project_points_to_local_2d(points_3d):
    points = np.asarray(points_3d, dtype=float)
    center, rotation, normal, rmse = local_frame_from_points(points)
    local = (rotation.T @ (points - center).T).T
    local_2d = local[:, :2]
    local_2d -= np.mean(local_2d, axis=0)
    return local_2d, center, rotation, normal, rmse


def estimate_target_pose(points_3d, max_plane_rmse_m=0.005):
    points = np.asarray(points_3d, dtype=float)
    if len(points) < 3:
        raise ValueError("At least 3 points are required for pose estimation")
    center, rotation, normal, rmse = local_frame_from_points(points)
    quat = Rotation.from_matrix(rotation).as_quat()
    confidence = max(0.0, min(1.0, 1.0 - rmse / max_plane_rmse_m)) if max_plane_rmse_m > 0 else 0.0
    return center, quat, {"num_points": int(len(points)), "plane_rmse_m": float(rmse), "confidence": float(confidence), "normal": normal.tolist()}


def estimate_pose_kabsch(template_points_target, measured_points_camera):
    template = np.asarray(template_points_target, dtype=float)
    measured = np.asarray(measured_points_camera, dtype=float)
    if len(template) != len(measured) or len(template) < 3:
        raise ValueError("Kabsch pose estimation requires at least 3 paired points")
    template_center = np.mean(template, axis=0)
    measured_center = np.mean(measured, axis=0)
    template_c = template - template_center
    measured_c = measured - measured_center
    h = template_c.T @ measured_c
    u, _, vt = np.linalg.svd(h)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    translation = measured_center - rotation @ template_center
    transformed = (rotation @ template.T).T + translation
    rmse = float(math.sqrt(np.mean(np.sum((transformed - measured) ** 2, axis=1))))
    quat = Rotation.from_matrix(rotation).as_quat()
    return translation, quat, rmse


def estimate_pose_with_fallback(template_points_target, measured_points_camera, max_plane_rmse_m=0.005):
    try:
        position, quat, pose_rmse = estimate_pose_kabsch(template_points_target, measured_points_camera)
        _, _, plane_quality = estimate_target_pose(measured_points_camera, max_plane_rmse_m)
        plane_quality["pose_rmse_m"] = float(pose_rmse)
        plane_quality["pose_method"] = "template_kabsch"
        return position, quat, plane_quality
    except Exception:
        position, quat, quality = estimate_target_pose(measured_points_camera, max_plane_rmse_m)
        quality["pose_rmse_m"] = None
        quality["pose_method"] = "pca_fallback"
        return position, quat, quality

