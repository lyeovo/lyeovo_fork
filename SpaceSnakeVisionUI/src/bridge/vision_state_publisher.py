from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class VisionStatePublisher:
    """Write the latest vision state for the motion-control side to poll."""

    def __init__(self, output_dir: Path, frame_id: str = "camera_left") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.output_dir / "latest_targets.json"
        self.frame_id = frame_id

    def publish(self, detections, selected_id: str | None = None) -> Path:
        now = time.time()
        targets = [_target_to_dict(obj, now) for obj in detections]
        selected = next((target for target in targets if target["target_id"] == selected_id), None)
        payload = {
            "schema_version": "vision_state.v1",
            "timestamp": now,
            "frame_id": self.frame_id,
            "camera_pose_base": None,
            "camera_pose_note": "camera_pose_base is null until hand-eye calibration is provided",
            "selected_target_id": selected_id,
            "selected_target": selected,
            "targets": targets,
        }
        tmp_path = self.latest_path.with_suffix(f".tmp_{os.getpid()}")
        try:
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
            os.replace(tmp_path, self.latest_path)
        except (PermissionError, OSError):
            # 兼容 Windows 下多进程/多线程瞬时文件读写锁冲突，避免 UI 异常崩溃
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
        return self.latest_path


def _target_to_dict(obj, now: float) -> dict[str, Any]:
    quality = dict(getattr(obj, "quality", {}) or {})
    pose_available = bool(quality.get("pose_available", getattr(obj, "status", None) == "POSE_6DOF"))
    pose_camera = getattr(obj, "pose_camera", None)
    bearing = getattr(obj, "bearing", None) or quality.get("bearing") or quality.get("last_seen_bearing")
    return {
        "target_id": obj.target_id,
        "class_name": obj.class_name,
        "display_name": obj.display_name,
        "status": obj.status,
        "detection_mode": obj.detection_mode,
        "timestamp": obj.timestamp,
        "age_s": max(0.0, now - obj.timestamp),
        "frame_id": pose_camera.frame_id if pose_camera else "camera_left",
        "bbox_xyxy": obj.bbox_xyxy,
        "center_pixel": obj.center_pixel,
        "depth_m": obj.depth_m,
        "bearing": bearing,
        "pose_camera": pose_camera.to_dict() if pose_available and pose_camera else None,
        "pose_base": obj.pose_base.to_dict() if getattr(obj, "pose_base", None) else None,
        "quality": {
            "num_dots": quality.get("num_dots"),
            "valid_depth_points": quality.get("valid_depth_points"),
            "confidence": quality.get("confidence", obj.confidence),
            "yolo_confidence": quality.get("yolo_confidence"),
            "rough_distance_m": quality.get("rough_distance_m"),
            "match_error_m": quality.get("match_error_m"),
            "plane_rmse_m": quality.get("plane_rmse_m"),
            "pose_rmse_m": quality.get("pose_rmse_m"),
            "pose_method": quality.get("pose_method"),
            "dot_source": quality.get("dot_source"),
            "board_quad": quality.get("board_quad"),
            "adaptive_threshold": quality.get("adaptive_threshold"),
            "pose_available": pose_available,
        },
    }


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
