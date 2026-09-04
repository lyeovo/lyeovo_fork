from src.bridge.file_bridge import FileBridge
from src.models import RobotState, TaskCommand, TaskStatus


def make_command():
    return TaskCommand("1.1", "CMD-TEST-00001", 1.0, "test", "home")


def test_publish_command_writes_json(tmp_path):
    bridge = FileBridge(tmp_path / "outbox", tmp_path / "inbox")
    path = bridge.publish_command(make_command())
    assert path.exists()
    assert not (tmp_path / "outbox" / ".CMD-TEST-00001.json.tmp").exists()
    assert "CMD-TEST-00001" in path.read_text(encoding="utf-8")


def test_poll_status_reads_once(tmp_path):
    bridge = FileBridge(tmp_path / "outbox", tmp_path / "inbox")
    status = TaskStatus("1.0", "CMD-TEST-00001", 1.0, "COMPLETED", "DONE", 1.0, "ok", RobotState())
    (tmp_path / "inbox" / "CMD-TEST-00001_1_COMPLETED_status.json").write_text(status.to_json(), encoding="utf-8")
    first = bridge.poll_status()
    second = bridge.poll_status()
    assert len(first) == 1
    assert first[0].status == "COMPLETED"
    assert second == []


def test_poll_status_ignores_invalid_json(tmp_path):
    bridge = FileBridge(tmp_path / "outbox", tmp_path / "inbox")
    (tmp_path / "inbox" / "bad_status.json").write_text("{not json", encoding="utf-8")
    assert bridge.poll_status() == []


def test_poll_status_rereads_in_place_overwrite(tmp_path):
    """控制端固定文件名原地覆盖时，内容变化即应被重新读取（指纹去重）。"""
    bridge = FileBridge(tmp_path / "outbox", tmp_path / "inbox")
    fn = tmp_path / "inbox" / "CMD-TEST-00001_status.json"

    s1 = TaskStatus("1.0", "CMD-TEST-00001", 1.0, "ACCEPTED", "SAFETY_ACCEPTED", 0.2, "accepted", RobotState(state="ACCEPTED"))
    fn.write_text(s1.to_json(), encoding="utf-8")
    first = bridge.poll_status()
    assert len(first) == 1
    assert first[0].status == "ACCEPTED"

    # 同内容再轮询：指纹未变，不重复投递
    assert bridge.poll_status() == []

    # 原地覆盖为不同状态（内容/大小变化）：应再次读到新状态
    s2 = TaskStatus("1.0", "CMD-TEST-00001", 2.0, "COMPLETED", "MOVE_TO_COMPLETED", 1.0, "done", RobotState(state="COMPLETED"))
    fn.write_text(s2.to_json(), encoding="utf-8")
    second = bridge.poll_status()
    assert len(second) == 1
    assert second[0].status == "COMPLETED"

    # 覆盖后内容稳定：不再重复投递
    assert bridge.poll_status() == []


def test_matlab_radians_and_joint_padding():
    """验证从 MATLAB 回传的 TaskStatus JSON（未声明单位、4 个弧度关节角）能够被正确解析"""
    import json
    import math

    matlab_status_dict = {
        "schema_version": "1.0",
        "command_id": "CMD-MATLAB-001",
        "timestamp": 123456.78,
        "status": "COMPLETED",
        "current_step": "move_to",
        "progress": 1.0,
        "message": "任务完成",
        "robot_state": {
            "state": "IDLE",
            "end_effector_pose_base": [],
            "joint_positions": [0.5, -0.8, 1.2, -0.3],  # MATLAB 4 个弧度角
            "message": "normal"
        }
    }
    ts = TaskStatus.from_dict(matlab_status_dict)
    rob = ts.robot_state
    assert rob._unit_specified is False
    assert len(rob.joint_positions) == 4

    # 模拟 MainWindow._apply_robot_state 解析逻辑
    vals = [float(v) for v in rob.joint_positions]
    unit = str(getattr(rob, "joint_positions_unit", "deg")).strip().lower()
    unit_specified = getattr(rob, "_unit_specified", True)
    is_rad = (unit == "rad") or (not unit_specified and any(abs(v) > 1e-4 for v in vals) and all(abs(v) <= 3.2 for v in vals))
    assert is_rad is True

    deg_vals = [math.degrees(v) for v in vals]
    if len(deg_vals) < 6:
        deg_vals = deg_vals + [0.0] * (6 - len(deg_vals))
    assert len(deg_vals) == 6
    assert abs(deg_vals[0] - math.degrees(0.5)) < 1e-3
    assert abs(deg_vals[1] - math.degrees(-0.8)) < 1e-3
    assert abs(deg_vals[4] - 0.0) < 1e-3
