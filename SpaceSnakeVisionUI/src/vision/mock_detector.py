from ..camera.base_camera import CameraFrame
from ..models import DetectedObject
from .depth_pose import pose_from_depth
from .detector_base import DetectorBase


class MockDetector(DetectorBase):
    def detect(self, frame: CameraFrame) -> list[DetectedObject]:
        specs = [
            ("TGT-001", "payload_module", "载荷模块 1", 12, [97, 87, 213, 203], [155, 145]),
            ("TGT-002", "dock_port", "对接接口 2", 23, [277, 167, 393, 283], [335, 225]),
            ("TGT-003", "tool_node", "工具节点 3", 31, [442, 262, 558, 378], [500, 320]),
        ]
        result = []
        for target_id, cls, name, marker_id, bbox, center in specs:
            pose, depth, status = pose_from_depth(frame.depth_image, tuple(center), frame.intrinsics)
            result.append(
                DetectedObject(
                    target_id=target_id,
                    timestamp=frame.timestamp,
                    class_name=cls,
                    display_name=name,
                    detection_mode="mock_depth",
                    marker_id=marker_id,
                    confidence=0.92,
                    stability_score=0.88,
                    bbox_xyxy=bbox,
                    center_pixel=center,
                    depth_m=depth,
                    pose_camera=pose,
                    status=status,
                )
            )
        return result
