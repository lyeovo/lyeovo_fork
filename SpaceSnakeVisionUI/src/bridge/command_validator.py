from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


ALL_COMMAND_TYPES = {
    "move_to",
    "move_along",
    "move_for_pick",
    "move_for_place",
    "rotate",
    "rotate_arm",
    "facing_arm",
    "pick",
    "place",
    "withdraw",
    "reset",
    "emergency_stop",
    "cancel_task",
}
TARGET_REQUIRED_COMMANDS = {"move_for_pick"}
BYPASS_BUSY_COMMANDS = {"emergency_stop", "cancel_task"}


@dataclass
class ValidationConfig:
    target_max_age_s: float = 3.0
    min_confidence: float = 0.4
    min_stability: float = 0.2
    max_xy_range_m: float = 6.0        # 6 节 × 1m 平面臂全伸展半径
    max_move_distance_m: float = 6.0   # 单次移动距离上限 = 最大可达半径
    min_joint_index: int = 1
    max_joint_index: int = 6           # 机械臂共 6 个关节
    block_when_robot_busy: bool = True


@dataclass
class ValidationResult:
    ok: bool
    reason: str
    checks: dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "simulation_only"
    allow_real_execute: bool = False

    def to_report(self) -> dict[str, Any]:
        return {
            "validation_passed": self.ok,
            "validation_message": self.reason,
            "checks": self.checks,
            "execution_mode": self.execution_mode,
            "allow_real_execute": self.allow_real_execute,
        }


def validate_command(
    command_type: str,
    params: dict[str, Any] | None = None,
    target = None,
    destination_name: str | None = None,
    *,
    estop_active: bool = False,
    robot_busy: bool = False,
    locked_at: float | None = None,
    now: float | None = None,
    config: ValidationConfig | None = None,
) -> ValidationResult:
    cfg = config or ValidationConfig()
    now = time.time() if now is None else now
    p = dict(params or {})
    checks: dict[str, Any] = {
        "command_type": command_type,
        "params": p,
        "estop_active": estop_active,
        "robot_busy": robot_busy,
        "destination": destination_name,
    }

    if estop_active and command_type != "emergency_stop":
        return ValidationResult(False, "E-STOP is active", checks)
    if cfg.block_when_robot_busy and robot_busy and command_type not in BYPASS_BUSY_COMMANDS:
        return ValidationResult(False, "robot is busy", checks)

    if command_type == "emergency_stop":
        return ValidationResult(True, "E-STOP triggered", checks, "real_robot", True)

    if command_type == "move_to":
        if "x" not in p or "y" not in p:
            return ValidationResult(False, "move_to requires 'x' and 'y' coordinates", checks)
        try:
            x, y = float(p["x"]), float(p["y"])
            if abs(x) > cfg.max_xy_range_m or abs(y) > cfg.max_xy_range_m:
                return ValidationResult(False, f"Target coordinate ({x:.2f}, {y:.2f}) exceeds work range ±{cfg.max_xy_range_m}m", checks)
        except (ValueError, TypeError):
            return ValidationResult(False, "Invalid numeric format for x or y", checks)

    elif command_type == "move_along":
        if "theta_deg" not in p or "distance_m" not in p:
            return ValidationResult(False, "move_along requires 'theta_deg' and 'distance_m'", checks)
        try:
            d = float(p["distance_m"])
            if d <= 0 or d > cfg.max_move_distance_m:
                return ValidationResult(False, f"Distance {d:.2f}m must be in (0, {cfg.max_move_distance_m}]m", checks)
        except (ValueError, TypeError):
            return ValidationResult(False, "Invalid numeric format for theta or distance", checks)

    elif command_type in ("rotate_arm", "facing_arm"):
        if "joint_index" not in p:
            return ValidationResult(False, f"{command_type} requires 'joint_index'", checks)
        try:
            joint_idx = int(p["joint_index"])
            if joint_idx < cfg.min_joint_index or joint_idx > cfg.max_joint_index:
                return ValidationResult(False, f"Joint index {joint_idx} out of range [{cfg.min_joint_index}, {cfg.max_joint_index}]", checks)
        except (ValueError, TypeError):
            return ValidationResult(False, "Invalid joint index", checks)

    if command_type in TARGET_REQUIRED_COMMANDS:
        if target is None:
            return ValidationResult(False, "no target selected for target-based motion", checks)
        target_age_s = max(0.0, now - float(locked_at if locked_at is not None else getattr(target, "timestamp", now)))
        checks.update(
            {
                "target_id": getattr(target, "target_id", None),
                "target_age_s": target_age_s,
                "confidence": getattr(target, "confidence", None),
                "stability_score": getattr(target, "stability_score", None),
                "status": getattr(target, "status", None),
            }
        )
        if target_age_s > cfg.target_max_age_s:
            return ValidationResult(False, "target snapshot is stale", checks)
        if float(getattr(target, "confidence", 0.0) or 0.0) < cfg.min_confidence:
            return ValidationResult(False, "target confidence is too low", checks)

    return ValidationResult(True, "validation passed", checks, "real_robot", True)
