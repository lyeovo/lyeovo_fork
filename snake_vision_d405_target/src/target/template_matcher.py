from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial.distance import cdist

from src.target.pose_estimator import project_points_to_local_2d


@dataclass
class TemplateMatchResult:
    target_id: str
    match_error_m: float | None
    confidence: float
    matched_template_points: list[list[float]]
    matched_measured_points: list[list[float]]
    plane_rmse_m: float | None
    status: str


def _rotate_2d(points, angle):
    c = np.cos(angle)
    s = np.sin(angle)
    r = np.array([[c, -s], [s, c]], dtype=float)
    return points @ r.T


def _best_chamfer(observed_2d, template_2d, allow_rotation=True):
    observed = np.asarray(observed_2d, dtype=float)
    template = np.asarray(template_2d, dtype=float)
    if len(observed) == 0 or len(template) == 0:
        return float("inf"), np.empty((0,), dtype=int), observed
    angles = np.linspace(0.0, 2.0 * np.pi, 72, endpoint=False) if allow_rotation else [0.0]
    best = (float("inf"), None, observed)
    for angle in angles:
        rotated = _rotate_2d(observed, angle)
        dist = cdist(rotated, template)
        error = float((np.mean(np.min(dist, axis=1)) + np.mean(np.min(dist, axis=0))) / 2.0)
        if error < best[0]:
            best = (error, np.argmin(dist, axis=1), rotated)
    return best


def match_current_points(points_3d_camera, database_targets, config=None):
    cfg = config or {}
    max_error = float(cfg.get("max_match_error_m", 0.015))
    allow_rotation = bool(cfg.get("allow_rotation", True))
    observed_2d, _, _, _, plane_rmse = project_points_to_local_2d(points_3d_camera)
    best = None
    for target_id, target in (database_targets or {}).items():
        template = np.asarray(target.get("template_points", []), dtype=float)
        if len(template) < 3:
            continue
        error, nearest_template_idx, rotated_observed = _best_chamfer(observed_2d, template[:, :2], allow_rotation)
        if best is None or error < best[0]:
            best = (error, target_id, target, nearest_template_idx, rotated_observed)
    if best is None:
        return TemplateMatchResult("unknown", None, 0.0, [], [], float(plane_rmse), "unknown")
    error, target_id, target, nearest_template_idx, _ = best
    known = error <= max_error or not cfg.get("unknown_if_error_larger", True)
    confidence = float(np.clip(np.exp(-error / max(max_error, 1e-9)), 0.0, 1.0))
    if not known:
        target_id = "unknown"
        confidence = min(confidence, 0.5)
    template_points = np.asarray(target.get("template_points", []), dtype=float)
    matched_template = template_points[nearest_template_idx].tolist() if nearest_template_idx is not None else []
    return TemplateMatchResult(
        target_id=target_id,
        match_error_m=float(error),
        confidence=confidence,
        matched_template_points=matched_template,
        matched_measured_points=np.asarray(points_3d_camera, dtype=float).tolist(),
        plane_rmse_m=float(plane_rmse),
        status="valid" if known else "unknown",
    )


def compute_confidence(valid_depth_points, num_dots, match_error_m=None, plane_rmse_m=None, pose_rmse_m=None):
    score = 1.0
    if num_dots:
        score *= max(0.0, min(1.0, valid_depth_points / float(num_dots)))
    if match_error_m is not None:
        score *= float(np.exp(-float(match_error_m) / 0.015))
    if plane_rmse_m is not None:
        score *= float(np.exp(-float(plane_rmse_m) / 0.01))
    if pose_rmse_m is not None:
        score *= float(np.exp(-float(pose_rmse_m) / 0.01))
    return float(np.clip(score, 0.0, 1.0))


def confidence_status(confidence):
    if confidence >= 0.75:
        return "valid"
    if confidence >= 0.6:
        return "unstable"
    return "invalid"

