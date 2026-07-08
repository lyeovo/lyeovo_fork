from src.models import DetectedObject, Pose3D


def test_pose_json_round_trip():
    pose = Pose3D()
    restored = Pose3D.from_json(pose.to_json())
    assert restored.frame_id == "camera_color_optical_frame"


def test_detected_object_json_round_trip():
    obj = DetectedObject(
        target_id="TGT-001",
        timestamp=1.0,
        class_name="payload_module",
        display_name="载荷模块 1",
        detection_mode="mock_depth",
        marker_id=12,
        confidence=0.9,
        stability_score=0.8,
        bbox_xyxy=[1, 2, 3, 4],
        center_pixel=[2, 3],
        depth_m=0.5,
        pose_camera=Pose3D(),
    )
    restored = DetectedObject.from_json(obj.to_json())
    assert restored.target_id == "TGT-001"
    assert restored.pose_camera.position.z == 0.0
