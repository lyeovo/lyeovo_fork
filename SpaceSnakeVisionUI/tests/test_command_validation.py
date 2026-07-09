import time

from src.bridge.command_validator import validate_command
from src.models import DetectedObject, Pose3D


def make_target(**overrides):
    data = {
        "target_id": "TGT-001",
        "timestamp": time.time(),
        "class_name": "payload",
        "display_name": "Payload",
        "detection_mode": "mock",
        "marker_id": None,
        "confidence": 0.9,
        "stability_score": 0.8,
        "bbox_xyxy": [10, 10, 80, 80],
        "center_pixel": [45, 45],
        "depth_m": 0.35,
        "pose_camera": Pose3D(),
        "pose_base": None,
        "status": "AVAILABLE",
    }
    data.update(overrides)
    return DetectedObject(**data)


def test_estop_blocks_regular_command():
    result = validate_command("pick_and_place", make_target(), "Assembly_Port_A", 0.05, estop_active=True)
    assert not result.ok
    assert "E-STOP" in result.reason


def test_home_without_target_passes():
    result = validate_command("home", None, "Safe_Zone", 0.05)
    assert result.ok


def test_target_command_requires_target():
    result = validate_command("pick_and_place", None, "Assembly_Port_A", 0.05)
    assert not result.ok
    assert result.reason == "no target selected"


def test_low_confidence_rejected():
    result = validate_command("pick_target", make_target(confidence=0.2), "Assembly_Port_A", 0.05)
    assert not result.ok
    assert "confidence" in result.reason


def test_pose_base_missing_allows_simulation_only():
    result = validate_command("pick_target", make_target(pose_base=None), "Assembly_Port_A", 0.05)
    assert result.ok
    assert result.execution_mode == "simulation_only"
    assert not result.allow_real_execute


def test_robot_busy_blocks_regular_but_allows_cancel():
    blocked = validate_command("pick_target", make_target(), "Assembly_Port_A", 0.05, robot_busy=True)
    cancel = validate_command("cancel_task", None, None, 0.05, robot_busy=True)
    assert not blocked.ok
    assert cancel.ok
