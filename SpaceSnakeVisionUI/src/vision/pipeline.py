import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .aruco_detector import ArucoDetector
from .mock_detector import MockDetector
from .marker_detector import MarkerTemplateDetector
from .object_tracker import ObjectTracker
from .stability import StabilityChecker
from .yolo_marker_detector import YoloMarkerDetector
from .yolo_detector import YoloDetector


class VisionPipeline:
    def __init__(self, prefer_mock: bool = False, detector_mode: str = "yolo", yolo_model: str = "yolo11n.pt", yolo_conf: float = 0.35, project_root=None) -> None:
        self.aruco = ArucoDetector()
        self.yolo = YoloDetector(yolo_model, yolo_conf) if detector_mode in ("auto", "yolo") else None
        self.marker = MarkerTemplateDetector(project_root) if detector_mode == "marker" and project_root is not None else None
        self.yolo_marker = YoloMarkerDetector(project_root, yolo_model, yolo_conf) if detector_mode == "yolo_marker" and project_root is not None else None
        self.mock = MockDetector()
        self.tracker = ObjectTracker()
        self.stability = StabilityChecker()
        self.prefer_mock = prefer_mock
        self.detector_mode = detector_mode
        self.last_message = None
        if self.yolo is not None and not self.yolo.available:
            self.last_message = self.yolo.error_message
        if self.marker is not None:
            self.last_message = self.marker.last_message
        if self.yolo_marker is not None:
            self.last_message = self.yolo_marker.last_message

    def process(self, frame):
        detections = []
        if self.detector_mode == "yolo_marker" and self.yolo_marker is not None and self.yolo_marker.available:
            detections = self.yolo_marker.detect(frame)
            self.last_message = self.yolo_marker.last_message
        elif self.detector_mode == "marker" and self.marker is not None:
            detections = self.marker.detect(frame)
            self.last_message = self.marker.last_message
        if not detections and self.detector_mode in ("auto", "yolo") and self.yolo is not None and self.yolo.available:
            detections = self.yolo.detect(frame)
            if self.yolo.error_message:
                self.last_message = self.yolo.error_message
        if not detections and self.detector_mode in ("auto", "aruco") and not self.prefer_mock:
            detections = self.aruco.detect(frame)
        if not detections and self.detector_mode == "mock":
            detections = self.mock.detect(frame)
        elif not detections and self.detector_mode == "auto" and self.prefer_mock and (self.yolo is None or not self.yolo.available):
            detections = self.mock.detect(frame)
        detections = self.tracker.update(detections)
        detections = self.stability.apply(detections)
        overlay = frame.color_image.copy()
        self.draw_overlay(overlay, detections, None, frame.intrinsics)
        return overlay, detections

    @staticmethod
    def draw_overlay(image, detections, selected_id, intrinsics=None):
        for obj in detections:
            x1, y1, x2, y2 = obj.bbox_xyxy
            color = (255, 229, 0) if obj.target_id != selected_id else (138, 234, 46)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            quad = getattr(obj, "quality", {}).get("board_quad") if hasattr(obj, "quality") else None
            if quad:
                pts = np.asarray(quad, dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(image, [pts], True, (0, 180, 255), 2)
            cx, cy = obj.center_pixel
            cv2.drawMarker(image, (cx, cy), color, cv2.MARKER_CROSS, 24, 2)

            pose_cam = getattr(obj, "pose_camera", None)
            has_valid_pos = (
                pose_cam is not None
                and getattr(pose_cam, "position", None) is not None
                and getattr(pose_cam.position, "z", 0.0) is not None
                and pose_cam.position.z > 0.02
                and np.isfinite(pose_cam.position.z)
            )

            if has_valid_pos:
                px = pose_cam.position.x
                py = pose_cam.position.y
                pz = pose_cam.position.z
                label = f"{obj.target_id} X:{px:+.2f} Y:{py:+.2f} Z:{pz:.2f}m"
            else:
                label = f"{obj.target_id} {obj.class_name} z={obj.depth_m or 0:.3f}m"
            cv2.putText(image, label, (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

            # 只要具有有效 3D 相对位置，无论 6DoF 还是 3DoF，均绘制空间三维坐标系指示
            if has_valid_pos and intrinsics is not None:
                VisionPipeline.draw_pose_axes(image, obj, intrinsics)

    @staticmethod
    def redraw_selection(image, detections, selected_id):
        VisionPipeline.draw_overlay(image, detections, selected_id)
        if selected_id:
            cv2.putText(image, f"TARGET LOCKED: {selected_id}", (18, image.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (138, 234, 46), 2)

    @staticmethod
    def draw_pose_axes(image, obj, intrinsics, axis_length_m: float = 0.04):
        pose = obj.pose_camera
        origin = np.array([pose.position.x, pose.position.y, pose.position.z], dtype=float)
        if not np.all(np.isfinite(origin)) or origin[2] <= 0.01:
            return

        # 提取旋转姿态；若是 3-DoF 或无有效四元数，默认对齐相机基底
        quat = getattr(pose, "orientation_quat", None)
        rotation = np.eye(3)
        if quat is not None:
            q_arr = np.array([quat.x, quat.y, quat.z, quat.w], dtype=float)
            if np.all(np.isfinite(q_arr)) and np.linalg.norm(q_arr) > 1e-4:
                try:
                    rotation = Rotation.from_quat(q_arr).as_matrix()
                except Exception:
                    rotation = np.eye(3)

        axis_points = np.vstack(
            [
                origin,
                origin + rotation[:, 0] * axis_length_m,
                origin + rotation[:, 1] * axis_length_m,
                origin + rotation[:, 2] * axis_length_m,
            ]
        )
        pixels = []
        for point in axis_points:
            if point[2] <= 0.005:
                return
            u = int(round(intrinsics.fx * point[0] / point[2] + intrinsics.cx))
            v = int(round(intrinsics.fy * point[1] / point[2] + intrinsics.cy))
            pixels.append((u, v))
        h, w = image.shape[:2]
        if not (0 <= pixels[0][0] < w and 0 <= pixels[0][1] < h):
            return
        origin_px = pixels[0]
        for end_px, color, label in [
            (pixels[1], (0, 0, 255), "X"),
            (pixels[2], (0, 255, 0), "Y"),
            (pixels[3], (255, 0, 0), "Z"),
        ]:
            cv2.arrowedLine(image, origin_px, end_px, color, 3, tipLength=0.25)
            cv2.putText(image, label, end_px, cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
