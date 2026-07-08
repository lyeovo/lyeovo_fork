from pathlib import Path
import os

from ..models import TaskCommand, TaskStatus
from .bridge_base import BridgeBase


class FileBridge(BridgeBase):
    def __init__(self, outbox_dir: Path, inbox_dir: Path, ignore_existing_statuses: bool = True) -> None:
        self.outbox_dir = Path(outbox_dir)
        self.inbox_dir = Path(inbox_dir)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self._seen_status_files: set[Path] = set(self.inbox_dir.glob("*_status.json")) if ignore_existing_statuses else set()

    def publish_command(self, command: TaskCommand) -> Path:
        path = self.outbox_dir / f"{command.command_id}.json"
        tmp_path = self.outbox_dir / f".{command.command_id}.json.tmp"
        tmp_path.write_text(command.to_json(), encoding="utf-8")
        os.replace(tmp_path, path)
        return path

    def poll_status(self) -> list[TaskStatus]:
        statuses = []
        for path in sorted(self.inbox_dir.glob("*_status.json")):
            if path in self._seen_status_files:
                continue
            try:
                statuses.append(TaskStatus.from_json(path.read_text(encoding="utf-8")))
                self._seen_status_files.add(path)
            except Exception as exc:
                print(f"FileBridge ignored invalid status file {path}: {exc}")
                continue
        return statuses
