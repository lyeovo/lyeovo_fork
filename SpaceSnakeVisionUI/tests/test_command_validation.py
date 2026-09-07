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
    result = validate_command("move_to", {"x": 0.3, "y": 0.2}, estop_active=True)
    assert not result.ok
    assert "E-STOP" in result.reason


def test_move_to_validation():
    # 有效坐标
    res1 = validate_command("move_to", {"x": 0.35, "y": -0.10})
    assert res1.ok

    # 边界内（±6m 全伸展可达）
    res_edge = validate_command("move_to", {"x": 6.0, "y": 0.0})
    assert res_edge.ok

    # 越界坐标（超出 ±6m）
    res2 = validate_command("move_to", {"x": 6.5, "y": 0.0})
    assert not res2.ok
    assert "exceeds" in res2.reason

    # 缺少参数
    res3 = validate_command("move_to", {})
    assert not res3.ok


def test_move_along_validation():
    # 正常
    res1 = validate_command("move_along", {"theta_deg": 30.0, "distance_m": 0.15})
    assert res1.ok

    # 距离非法
    res2 = validate_command("move_along", {"theta_deg": 30.0, "distance_m": -0.1})
    assert not res2.ok


def test_rotate_arm_validation():
    # 正常
    res1 = validate_command("rotate_arm", {"joint_index": 2, "alpha_deg": 45.0})
    assert res1.ok

    # 末关节（第 6 关节）合法
    res_edge = validate_command("rotate_arm", {"joint_index": 6, "alpha_deg": 45.0})
    assert res_edge.ok

    # 超出 6 关节（越界）
    res_over = validate_command("rotate_arm", {"joint_index": 7, "alpha_deg": 45.0})
    assert not res_over.ok

    # 关节编号越界
    res2 = validate_command("rotate_arm", {"joint_index": 99, "alpha_deg": 45.0})
    assert not res2.ok


def test_move_for_pick_requires_target():
    # 无 target 拒绝
    res1 = validate_command("move_for_pick", {})
    assert not res1.ok
    assert "target" in res1.reason

    # 有 target 通过
    res2 = validate_command("move_for_pick", {}, target=make_target())
    assert res2.ok


def test_robot_busy_blocks_regular_but_allows_cancel():
    blocked = validate_command("move_to", {"x": 0.1, "y": 0.1}, robot_busy=True)
    cancel = validate_command("cancel_task", {}, robot_busy=True)
    assert not blocked.ok
    assert cancel.ok
