from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..camera.base_camera import CameraFrame
from ..models import DetectedObject
from .depth_pose import pose_from_depth
from .detector_base import DetectorBase


class YoloDetector(DetectorBase):
    def __init__(self, model_path: str = "yolo11n.pt", confidence_threshold: float = 0.35) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.names = {}
        self.error_message: Optional[str] = None
        self._load_model()

    @property
    def available(self) -> bool:
        return self.model is not None

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO

            path = Path(self.model_path)
            model_ref = str(path) if path.exists() else self.model_path
            self.model = YOLO(model_ref)
            self.names = getattr(self.model, "names", {}) or {}
        except Exception as exc:
            self.error_message = f"YOLO unavailable: {exc}"
            self.model = None

    def detect(self, frame: CameraFrame) -> list[DetectedObject]:
        if self.model is None:
            return []
        try:
            results = self.model.predict(frame.color_image, conf=self.confidence_threshold, verbose=False)
        except Exception as exc:
            self.error_message = f"YOLO inference failed: {exc}"
            return []
        detections: list[DetectedObject] = []
        if not results:
            return detections
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return detections
        for idx, box in enumerate(boxes):
            xyxy = box.xyxy[0].detach().cpu().numpy().astype(int).tolist()
            cls_id = int(box.cls[0].detach().cpu().item()) if box.cls is not None else -1
            conf = float(box.conf[0].detach().cpu().item()) if box.conf is not None else 0.0
            class_name = str(self.names.get(cls_id, f"class_{cls_id}"))
            x1, y1, x2, y2 = xyxy
            center = [int((x1 + x2) / 2), int((y1 + y2) / 2)]
            pose, depth, status = pose_from_depth(frame.depth_image, tuple(center), frame.intrinsics)
            detections.append(
                DetectedObject(
                    target_id=f"YOLO-{idx + 1:03d}",
                    timestamp=frame.timestamp,
                    class_name=class_name,
                    display_name=class_name,
                    detection_mode="yolo_depth",
                    marker_id=None,
                    confidence=conf,
                    stability_score=0.85 if status == "AVAILABLE" else 0.50,
                    bbox_xyxy=[int(x1), int(y1), int(x2), int(y2)],
                    center_pixel=center,
                    depth_m=depth,
                    pose_camera=pose,
                    status=status,
                )
            )
        return detections
