import cv2
import numpy as np

from ..camera.base_camera import CameraFrame
from ..models import DetectedObject, Euler, Pose3D, Vector3
from ..utils.geometry import rvec_to_euler
from .depth_pose import pose_from_depth
from .detector_base import DetectorBase


class ArucoDetector(DetectorBase):
    def __init__(self, marker_size_m: float = 0.04) -> None:
        self.marker_size_m = marker_size_m
        self.available = hasattr(cv2, "aruco")
        if self.available:
            self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            self.parameters = cv2.aruco.DetectorParameters()

    def detect(self, frame: CameraFrame) -> list[DetectedObject]:
        if not self.available:
            return []
        gray = cv2.cvtColor(frame.color_image, cv2.COLOR_BGR2GRAY)
        if hasattr(cv2.aruco, "ArucoDetector"):
            detector = cv2.aruco.ArucoDetector(self.dictionary, self.parameters)
            corners, ids, _ = detector.detectMarkers(gray)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(gray, self.dictionary, parameters=self.parameters)
        if ids is None:
            return []
        detections = []
        for corner, marker_id in zip(corners, ids.flatten()):
            pts = corner.reshape(4, 2).astype(np.float32)
            x1, y1 = pts.min(axis=0).astype(int)
            x2, y2 = pts.max(axis=0).astype(int)
            center = [int((x1 + x2) / 2), int((y1 + y2) / 2)]
            pose, depth, status = pose_from_depth(frame.depth_image, tuple(center), frame.intrinsics)
            pnp_pose = self._estimate_pose_solvepnp(pts, frame)
            if pnp_pose is not None:
                pose = pnp_pose
                if depth is not None:
                    pose.position.z = depth
            detections.append(
                DetectedObject(
                    target_id=f"ARUCO-{int(marker_id):03d}",
                    timestamp=frame.timestamp,
                    class_name="aruco_marker",
                    display_name=f"ArUco Marker {int(marker_id)}",
                    detection_mode="aruco_depth_solvepnp",
                    marker_id=int(marker_id),
                    confidence=0.95,
                    stability_score=0.80,
                    bbox_xyxy=[int(x1), int(y1), int(x2), int(y2)],
                    center_pixel=center,
                    depth_m=depth,
                    pose_camera=pose,
                    status=status,
                )
            )
        return detections

    def _estimate_pose_solvepnp(self, image_points: np.ndarray, frame: CameraFrame) -> Pose3D | None:
        s = self.marker_size_m
        object_points = np.array([[-s / 2, s / 2, 0], [s / 2, s / 2, 0], [s / 2, -s / 2, 0], [-s / 2, -s / 2, 0]], dtype=np.float32)
        flags = cv2.SOLVEPNP_IPPE_SQUARE if hasattr(cv2, "SOLVEPNP_IPPE_SQUARE") else cv2.SOLVEPNP_ITERATIVE
        ok, rvec, tvec = cv2.solvePnP(object_points, image_points, frame.intrinsics.camera_matrix(), frame.intrinsics.dist_coeffs(), flags=flags)
        if not ok:
            return None
        roll, pitch, yaw = rvec_to_euler(rvec)
        tx, ty, tz = tvec.reshape(3).tolist()
        return Pose3D(position=Vector3(float(tx), float(ty), float(tz)), orientation_euler=Euler(roll, pitch, yaw))
