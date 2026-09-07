from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from ..camera.base_camera import CameraFrame
from ..models import DetectedObject, Euler, Pose3D, Quaternion, Vector3
from .detector_base import DetectorBase
from .marker_detector import (
    _bbox_from_dots,
    _bearing_from_dots,
    _confidence,
    _detect_circles,
    _estimate_pose,
    _load_yaml,
    _match_template,
    _points_from_depth,
)


class YoloMarkerDetector(DetectorBase):
    def __init__(self, project_root: Path, model_path: str, confidence_threshold: float = 0.35) -> None:
        self.project_root = Path(project_root)
        self.marker_root = self.project_root.parent / "snake_vision_d405_target"
        self.runtime_config = _load_yaml(self.marker_root / "config" / "runtime_config.yaml")
        self.database = _load_yaml(self.marker_root / "config" / "target_database.yaml")
        self.circle_cfg = dict(self.runtime_config.get("circle_detection", {}))
        self.circle_cfg["use_roi"] = False
        self.yolo_cfg = self.runtime_config.get("marker_yolo", {})
        self.model_path = str(model_path)
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.names = {}
        self.error_message: Optional[str] = None
        self.class_to_target_id = _default_class_mapping(self.yolo_cfg.get("class_to_target_id", {}))
        self.min_dots_for_bearing = int(self.yolo_cfg.get("min_dots_for_bearing", 2))
        self.min_dots_for_pose = int(self.yolo_cfg.get("min_dots_for_pose", 6))
        self.roi_pad_px = int(self.yolo_cfg.get("roi_pad_px", 30))
        self.use_board_mask = bool(self.yolo_cfg.get("use_board_mask", True))
        self.board_mask_pad_px = int(self.yolo_cfg.get("board_mask_pad_px", 10))
        self.adaptive_dot_threshold = bool(self.yolo_cfg.get("adaptive_dot_threshold", True))
        self.max_match_error_m = float(self.runtime_config.get("target_matching", {}).get("max_match_error_m", 0.015))
        self.allow_rotation = bool(self.runtime_config.get("target_matching", {}).get("allow_rotation", True))
        self.unknown_if_error_larger = bool(self.runtime_config.get("target_matching", {}).get("unknown_if_error_larger", True))
        self._last_quat_by_target: dict[str, np.ndarray] = {}
        self._last_pose_by_target: dict[str, tuple[Pose3D, float, float]] = {}
        self.pose_hold_seconds = float(self.yolo_cfg.get("pose_hold_seconds", 0.35))
        self._load_model()
        if self.available:
            self.last_message = f"YOLO-marker detector loaded: {self.model_path}"
        else:
            self.last_message = self.error_message or "YOLO-marker detector unavailable"

    @property
    def available(self) -> bool:
        return self.model is not None

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO

            path = Path(self.model_path)
            if not path.is_absolute():
                path = self.project_root / path
            model_ref = str(path) if path.exists() else self.model_path
            self.model = YOLO(model_ref)
            self.names = getattr(self.model, "names", {}) or {}
        except Exception as exc:
            self.error_message = f"YOLO-marker unavailable: {exc}"
            self.model = None

    def detect(self, frame: CameraFrame) -> list[DetectedObject]:
        if self.model is None:
            return []
        try:
            results = self.model.predict(frame.color_image, conf=self.confidence_threshold, verbose=False)
        except Exception as exc:
            self.error_message = f"YOLO-marker inference failed: {exc}"
            self.last_message = self.error_message
            return []
        detections = []
        boxes = getattr(results[0], "boxes", None) if results else None
        if boxes is None:
            self.last_message = "YOLO-marker SEARCH: no bbox"
            return []
        for idx, box in enumerate(boxes):
            xyxy = box.xyxy[0].detach().cpu().numpy().astype(int).tolist()
            cls_id = int(box.cls[0].detach().cpu().item()) if box.cls is not None else -1
            yolo_conf = float(box.conf[0].detach().cpu().item()) if box.conf is not None else 0.0
            class_name = str(self.names.get(cls_id, f"class_{cls_id}"))
            target_hint = self._target_id_from_class(class_name, cls_id, idx)
            detections.append(self._detect_one(frame, xyxy, class_name, target_hint, yolo_conf, idx))
        states = ", ".join(f"{obj.target_id}:{obj.status}" for obj in detections)
        self.last_message = f"YOLO-marker capture: {states}" if detections else "YOLO-marker SEARCH: no target"
        return detections

    def _detect_one(self, frame: CameraFrame, xyxy, class_name, target_hint, yolo_conf, idx):
        h, w = frame.color_image.shape[:2]
        x1, y1, x2, y2 = _clip_bbox(xyxy, w, h, self.roi_pad_px)
        board_quad = _detect_board_quad(frame.color_image, [x1, y1, x2, y2]) if self.use_board_mask else _bbox_quad([x1, y1, x2, y2])
        board_mask = _mask_from_quad((h, w), board_quad, self.board_mask_pad_px) if self.use_board_mask else None
        center = [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
        bbox_bearing = _bearing_from_dots([center], frame.intrinsics)
        rough_depth = _median_depth_in_mask(frame.depth_image, board_mask, [x1, y1, x2, y2])

        stable_id = target_hint
        confidence = float(np.clip(yolo_conf, 0.0, 1.0))

        if rough_depth is not None and rough_depth > 0.02 and np.isfinite(rough_depth):
            u_c, v_c = float(center[0]), float(center[1])
            fx, fy = float(frame.intrinsics.fx), float(frame.intrinsics.fy)
            cx, cy = float(frame.intrinsics.cx), float(frame.intrinsics.cy)
            cam_x = float((u_c - cx) * float(rough_depth) / fx)
            cam_y = float((v_c - cy) * float(rough_depth) / fy)
            cam_z = float(rough_depth)
            pos_3d = Vector3(cam_x, cam_y, cam_z)
            status = "AVAILABLE"
            depth_m = float(rough_depth)
            pose_method = "yolo_depth_deprojection"
        else:
            pos_3d = Vector3()
            status = "BEARING_ONLY"
            depth_m = None
            pose_method = "yolo_bbox_bearing"

        pose = Pose3D(
            frame_id="camera_left",
            position=pos_3d,
            orientation_quat=Quaternion(0.0, 0.0, 0.0, 1.0),
            orientation_euler=Euler(0.0, 0.0, 0.0),
        )

        bbox = _bbox_from_quad(board_quad, w, h) if board_quad else [x1, y1, x2, y2]
        obj = DetectedObject(
            target_id=stable_id,
            timestamp=frame.timestamp,
            class_name=class_name,
            display_name=stable_id,
            detection_mode="yolo_marker",
            marker_id=None,
            confidence=confidence,
            stability_score=confidence,
            bbox_xyxy=bbox,
            center_pixel=[int(round(center[0])), int(round(center[1]))],
            depth_m=depth_m,
            pose_camera=pose,
            status=status,
        )
        obj.bearing = bbox_bearing
        obj.quality = {
            "confidence": confidence,
            "yolo_confidence": yolo_conf,
            "yolo_class_name": class_name,
            "board_quad": board_quad,
            "rough_distance_m": rough_depth,
            "bearing": bbox_bearing,
            "pose_available": status == "AVAILABLE",
            "pose_method": pose_method,
            "json_status": status,
            "pose": None if status != "AVAILABLE" else {
                "position": {"x": pose.position.x, "y": pose.position.y, "z": pose.position.z},
                "orientation": {"qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
            },
        }
        return obj

    def _target_id_from_class(self, class_name: str, cls_id: int, idx: int) -> str:
        keys = [class_name, class_name.lower(), str(cls_id)]
        for key in keys:
            if key in self.class_to_target_id:
                return self.class_to_target_id[key]
        return class_name if class_name and not class_name.startswith("class_") else f"yolo_marker_{idx + 1}"

    def _target_subset(self, target_id: str):
        targets = self.database.get("targets", {})
        if target_id in targets:
            return {target_id: targets[target_id]}
        return targets

    def _stabilize_quaternion(self, target_id: str, quat) -> np.ndarray:
        quat = np.asarray(quat, dtype=float)
        last = self._last_quat_by_target.get(target_id)
        if last is not None and np.dot(last, quat) < 0:
            quat = -quat
        self._last_quat_by_target[target_id] = quat
        return quat


def _default_class_mapping(config_mapping):
    mapping = {
        "201": "target_1",
        "target_201": "target_1",
        "marker_201": "target_1",
        "222": "target_2",
        "target_222": "target_2",
        "marker_222": "target_2",
        "207": "target_3",
        "target_207": "target_3",
        "marker_207": "target_3",
        "target_1": "target_1",
        "target_2": "target_2",
        "target_3": "target_3",
        "0": "target_1",
        "1": "target_2",
        "2": "target_3",
    }
    mapping.update({str(k): str(v) for k, v in (config_mapping or {}).items()})
    return mapping


def _clip_bbox(xyxy, width, height, pad):
    x1, y1, x2, y2 = [int(v) for v in xyxy]
    return [
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(width - 1, x2 + pad),
        min(height - 1, y2 + pad),
    ]


def _bbox_quad(bbox):
    x1, y1, x2, y2 = [int(v) for v in bbox]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _bbox_from_quad(quad, width, height, pad=4):
    pts = np.asarray(quad, dtype=float)
    return [
        max(0, int(np.min(pts[:, 0]) - pad)),
        max(0, int(np.min(pts[:, 1]) - pad)),
        min(width - 1, int(np.max(pts[:, 0]) + pad)),
        min(height - 1, int(np.max(pts[:, 1]) + pad)),
    ]


def _detect_board_quad(color_image, bbox):
    h, w = color_image.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w - 1, x2), min(h - 1, y2)
    roi = color_image[y1:y2, x1:x2]
    if roi.size == 0:
        return _bbox_quad([x1, y1, x2, y2])

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((5, 5), np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel, iterations=2)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _bbox_quad([x1, y1, x2, y2])

    min_area = max(80.0, 0.08 * float((x2 - x1) * (y2 - y1)))
    contours = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not contours:
        return _bbox_quad([x1, y1, x2, y2])
    contour = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.03 * peri, True)
    if len(approx) == 4:
        pts = approx.reshape(4, 2).astype(float)
    else:
        pts = cv2.boxPoints(cv2.minAreaRect(contour)).astype(float)
    pts[:, 0] += x1
    pts[:, 1] += y1
    pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
    return _order_quad_points(pts).round().astype(int).tolist()


def _order_quad_points(points):
    pts = np.asarray(points, dtype=float)
    center = np.mean(pts, axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    ordered = pts[np.argsort(angles)]
    start = int(np.argmin(np.sum(ordered, axis=1)))
    return np.roll(ordered, -start, axis=0)


def _mask_from_quad(shape_hw, quad, pad_px):
    mask = np.zeros(shape_hw, dtype=np.uint8)
    pts = np.asarray(quad, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [pts], 255)
    if pad_px > 0:
        k = max(1, int(pad_px) * 2 + 1)
        mask = cv2.dilate(mask, np.ones((k, k), np.uint8), iterations=1)
    return mask


def _auto_circle_cfg(gray_roi, mask_roi, base_cfg, enabled):
    cfg = dict(base_cfg)
    if not enabled:
        return cfg, float(cfg.get("threshold_value", 35))
    values = gray_roi[mask_roi > 0] if mask_roi is not None and np.any(mask_roi > 0) else gray_roi.reshape(-1)
    values = values[np.isfinite(values)]
    if values.size < 20:
        return cfg, float(cfg.get("threshold_value", 35))
    bg = float(np.percentile(values, 55))
    fg = float(np.percentile(values, 98))
    threshold = bg + 0.42 * max(0.0, fg - bg)
    threshold = float(np.clip(threshold, 28.0, 210.0))
    cfg["threshold_mode"] = "manual"
    cfg["threshold_value"] = threshold
    cfg["binary_inverse"] = False
    return cfg, threshold


def _filter_dots_by_mask(dots_roi, mask_roi):
    if mask_roi is None:
        return dots_roi
    h, w = mask_roi.shape[:2]
    filtered = []
    for u, v in dots_roi:
        x = int(round(u))
        y = int(round(v))
        if 0 <= x < w and 0 <= y < h and mask_roi[y, x] > 0:
            filtered.append((u, v))
    return filtered


def _median_depth_in_mask(depth_image, mask, bbox):
    if depth_image is None:
        return None
    x1, y1, x2, y2 = bbox
    patch = depth_image[y1:y2, x1:x2]
    if mask is not None:
        mask_patch = mask[y1:y2, x1:x2] > 0
        patch = patch[mask_patch]
    else:
        patch = patch.reshape(-1)
    valid = patch[np.isfinite(patch) & (patch > 0.001)]
    return float(np.median(valid)) if valid.size >= 12 else None
