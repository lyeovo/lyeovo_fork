import argparse
import math
import os
import time
from pathlib import Path

from ..models import (
    Euler,
    Pose3D,
    Quaternion,
    RobotState,
    TaskCommand,
    TaskStatus,
    Vector3,
)

# 与控制页默认骨骼姿态一致，作为遥测插值起点
HOME_JOINTS = [0.0, 15.0, -20.0, 30.0, -10.0, 5.0]
HOME_EE = (0.30, 0.05)

# 终止类状态：不做运动插值，仅回显静止遥测
_TERMINAL = ("ESTOP_TRIGGERED", "CANCELED", "REJECTED")


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
                msg = TaskStatus(
                    schema_version="1.0",
                    command_id=command.command_id,
                    timestamp=time.time(),
                    status=status,
                    current_step=step,
                    progress=progress,
                    message=f"Mock control: {step}",
                    robot_state=_robot_state(command, status, progress),
                    planner=_planner(command, status, progress),
                )
                _write_status(inbox, msg)
                rob = msg.robot_state
                print(
                    f"{command.command_id}: {status} ({progress:.0%}) "
                    f"joints={rob.joint_positions} gripper={rob.gripper}"
                )
                time.sleep(0.8)
        time.sleep(0.5)


def _write_status(inbox: Path, status_obj: TaskStatus) -> None:
    """固定文件名原地覆盖，对齐控制端 taskWriteStatus.m（tmp + 原子替换）。

    UI 侧 FileBridge 以 (mtime_ns, size) 指纹去重，内容变化即重新解析。
    """
    fn = inbox / f"{status_obj.command_id}_status.json"
    tmp = fn.with_name(fn.name + ".tmp")
    tmp.write_text(status_obj.to_json(), encoding="utf-8")
    os.replace(tmp, fn)


def _steps_for(command: TaskCommand) -> list[tuple[str, str, float]]:
    c_type = command.command_type
    if c_type == "emergency_stop":
        return [("ESTOP_TRIGGERED", "ESTOP_TRIGGERED", 1.0)]
    if c_type == "cancel_task":
        return [("RECEIVED", "COMMAND_RECEIVED", 0.05), ("CANCELED", "TASK_CANCELED", 1.0)]
    if not command.safety.get("allow_execute", False):
        return [("RECEIVED", "COMMAND_RECEIVED", 0.05), ("REJECTED", "SAFETY_REJECTED", 0.0)]

    step_name = f"EXECUTING_{c_type.upper()}"
    return [
        ("RECEIVED", "COMMAND_RECEIVED", 0.05),
        ("ACCEPTED", "SAFETY_ACCEPTED", 0.20),
        ("PLANNING", f"PLANNING_{c_type.upper()}", 0.45),
        ("EXECUTING", step_name, 0.75),
        ("COMPLETED", f"{c_type.upper()}_COMPLETED", 1.0),
    ]


def _target_joints(c_type: str) -> list[float]:
    if c_type == "reset":
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    if c_type in ("pick", "place"):
        return [8.0, -18.0, 26.0, -22.0, 14.0, -6.0]
    if c_type in ("rotate", "rotate_arm", "facing_arm"):
        return [0.0, 15.0, -20.0, 30.0, -10.0, 45.0]
    # move_to / move_along / move_for_pick / move_for_place / withdraw
    return [12.0, -24.0, 34.0, -16.0, 22.0, -10.0]


def _ee_goal(command: TaskCommand) -> tuple[float, float]:
    c_type = command.command_type
    params = command.params or {}
    if c_type == "move_to":
        return float(params.get("x", 0.35)), float(params.get("y", 0.10))
    if c_type == "move_for_place":
        dest = command.destination or {}
        pos = (dest.get("pose_base") or {}).get("position") or {}
        return float(pos.get("x", 0.35)), float(pos.get("y", 0.10))
    return 0.40, 0.15


def _ee_pose(command: TaskCommand, progress: float) -> Pose3D:
    gx, gy = _ee_goal(command)
    x = HOME_EE[0] + (gx - HOME_EE[0]) * progress
    y = HOME_EE[1] + (gy - HOME_EE[1]) * progress
    params = command.params or {}
    yaw = float(params.get("alpha_deg", params.get("theta_deg", 0.0))) * progress
    half = math.radians(yaw) / 2.0
    return Pose3D(
        frame_id="robot_base",
        position=Vector3(x=round(x, 4), y=round(y, 4), z=0.0),
        orientation_euler=Euler(roll=0.0, pitch=0.0, yaw=round(yaw, 3)),
        orientation_quat=Quaternion(x=0.0, y=0.0, z=round(math.sin(half), 5), w=round(math.cos(half), 5)),
    )


def _gripper(c_type: str, status: str) -> int:
    # 0=HOLD, 1=OPEN, 2=CLOSE（对齐控制端 gripper_seq）
    if c_type == "pick":
        if status == "COMPLETED":
            return 2
        if status == "EXECUTING":
            return 1
        return 0
    if c_type == "place":
        if status == "COMPLETED":
            return 1
        if status in ("PLANNING", "EXECUTING"):
            return 2
        return 0
    return 0


def _robot_state(command: TaskCommand, status: str, progress: float) -> RobotState:
    c_type = command.command_type
    if status in _TERMINAL:
        # 急停/取消/拒绝：保持静止遥测，不做运动插值
        return RobotState(
            state=status,
            end_effector_pose_base=_ee_pose(command, 0.0),
            joint_positions=list(HOME_JOINTS),
            joint_positions_unit="deg",
            gripper=0,
            message=f"halted: {status}",
        )
    target = _target_joints(c_type)
    joints = [round(h + (t - h) * progress, 2) for h, t in zip(HOME_JOINTS, target)]
    return RobotState(
        state=status,
        end_effector_pose_base=_ee_pose(command, progress),
        joint_positions=joints,
        joint_positions_unit="deg",
        gripper=_gripper(c_type, status),
        message="normal",
    )


def _planner(command: TaskCommand, status: str, progress: float) -> dict:
    if status in ("RECEIVED",) or status in _TERMINAL:
        return {}
    c_type = command.command_type
    if c_type == "move_for_pick":
        method = "cvae"
    elif c_type in ("move_to", "move_along", "move_for_place"):
        method = "rrtstar"
    else:
        method = "auto"
    # 求解耗时随进度略降；跟踪/角度误差随进度收敛
    solve_time_ms = round(18.0 + 12.0 * (1.0 - progress), 1)
    tracking_error_mm = round(14.0 * (1.0 - progress) + 0.6, 2)
    angle_error_deg = round(6.0 * (1.0 - progress) + 0.2, 2)
    return {
        "method_used": method,
        "solve_time_ms": solve_time_ms,
        "tracking_error_mm": tracking_error_mm,
        "angle_error_deg": angle_error_deg,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["file"], default="file")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    run_file_mode(Path(args.root))


if __name__ == "__main__":
    main()
