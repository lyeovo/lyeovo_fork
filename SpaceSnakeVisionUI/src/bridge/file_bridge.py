from pathlib import Path
import hashlib
import os

from ..models import TaskCommand, TaskStatus
from .bridge_base import BridgeBase


class FileBridge(BridgeBase):
    def __init__(self, outbox_dir: Path, inbox_dir: Path, ignore_existing_statuses: bool = True) -> None:
        self.outbox_dir = Path(outbox_dir)
        self.inbox_dir = Path(inbox_dir)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        # 控制端以固定文件名 {command_id}_status.json 原地覆盖回写，
        # 故按“内容哈希”指纹去重：只要内容变化即重新解析。
        # （相比 (mtime_ns, size)，内容哈希对“同长度 + 同一时间刻度”的
        #  快速连续覆盖同样可靠——Windows 文件时间有 ~15ms 缓存粒度。）
        self._seen_status: dict[Path, str] = {}
        if ignore_existing_statuses:
            for path in self.inbox_dir.glob("*_status.json"):
                fp = self._fingerprint(path)
                if fp is not None:
                    self._seen_status[path] = fp

    @staticmethod
    def _fingerprint(path: Path):
        """读取文件内容并返回其 sha1 指纹；读取失败返回 None。"""
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return hashlib.sha1(data).hexdigest()

    def publish_command(self, command: TaskCommand) -> Path:
        path = self.outbox_dir / f"{command.command_id}.json"
        tmp_path = self.outbox_dir / f".{command.command_id}.json.tmp"
        tmp_path.write_text(command.to_json(), encoding="utf-8")
        os.replace(tmp_path, path)
        return path

    def poll_status(self) -> list[TaskStatus]:
        statuses = []
        for path in sorted(self.inbox_dir.glob("*_status.json")):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            fp = hashlib.sha1(data).hexdigest()
            if self._seen_status.get(path) == fp:
                continue
            # 内容变化：先记录指纹（避免对同一份无效内容每轮重复报错），再尝试解析
            self._seen_status[path] = fp
            try:
                statuses.append(TaskStatus.from_json(data.decode("utf-8")))
            except Exception as exc:
                print(f"FileBridge ignored invalid status file {path}: {exc}")
        return statuses
