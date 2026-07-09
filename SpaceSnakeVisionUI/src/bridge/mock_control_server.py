import argparse
import time
from pathlib import Path

from ..models import RobotState, TaskCommand, TaskStatus


def run_file_mode(root: Path) -> None:
    outbox = root / "data" / "outbox"
    inbox = root / "data" / "inbox"
    outbox.mkdir(parents=True, exist_ok=True)
    inbox.mkdir(parents=True, exist_ok=True)
    seen = set()
    print(f"MockControlServer watching {outbox}")
    while True:
        for path in sorted(outbox.glob("CMD-*.json")):
            if path in seen:
                continue
            seen.add(path)
            command = TaskCommand.from_json(path.read_text(encoding="utf-8"))
            for status, step, progress in _steps_for(command):
                msg = TaskStatus("1.0", command.command_id, time.time(), status, step, progress, f"Mock control: {step}", RobotState(state=status))
                timestamp_ms = int(time.time() * 1000)
                (inbox / f"{command.command_id}_{timestamp_ms}_{status}_status.json").write_text(msg.to_json(), encoding="utf-8")
                print(f"{command.command_id}: {status}")
                time.sleep(0.8)
        time.sleep(0.5)


def _steps_for(command: TaskCommand) -> list[tuple[str, str, float]]:
    if command.command_type == "emergency_stop":
        return [("ESTOP_TRIGGERED", "ESTOP_TRIGGERED", 1.0)]
    if command.command_type == "cancel_task":
        return [("RECEIVED", "COMMAND_RECEIVED", 0.05), ("CANCELED", "TASK_CANCELED", 1.0)]
    if not command.safety.get("allow_execute", False):
        return [("RECEIVED", "COMMAND_RECEIVED", 0.05), ("REJECTED", "SAFETY_REJECTED", 0.0)]
    return [
        ("RECEIVED", "COMMAND_RECEIVED", 0.05),
        ("ACCEPTED", "SAFETY_ACCEPTED", 0.20),
        ("PLANNING", "PLANNING_TRAJECTORY", 0.45),
        ("EXECUTING", "EXECUTING_TASK", 0.75),
        ("COMPLETED", "TASK_COMPLETED", 1.0),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["file"], default="file")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    run_file_mode(Path(args.root))


if __name__ == "__main__":
    main()
