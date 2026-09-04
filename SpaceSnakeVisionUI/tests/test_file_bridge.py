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
