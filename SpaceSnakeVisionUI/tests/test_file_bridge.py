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
