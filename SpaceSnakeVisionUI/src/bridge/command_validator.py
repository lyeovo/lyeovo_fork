from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


TARGET_COMMANDS = {"move_near_target", "pick_target", "pick_and_place", "dock_to_interface"}
BYPASS_BUSY_COMMANDS = {"emergency_stop", "cancel_task"}


@dataclass
class ValidationConfig:
    target_max_age_s: float = 2.0
    min_confidence: float = 0.5
    min_stability: float = 0.3
    require_depth_for_motion: bool = True
    allow_simulation_without_pose_base: bool = True
    require_pose_base_for_real_robot: bool = True
    block_when_robot_busy: bool = True
    min_approach_distance_m: float = 0.01
    max_approach_distance_m: float = 0.5
    max_reach_m: float = 0.8


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
    target,
    destination_name: str | None,
    approach_distance_m: float,
    *,
    estop_active: bool = False,
    robot_busy: bool = False,
    locked_at: float | None = None,
    now: float | None = None,
    config: ValidationConfig | None = None,
) -> ValidationResult:
    cfg = config or ValidationConfig()
    now = time.time() if now is None else now
    checks: dict[str, Any] = {
        "command_type": command_type,
        "estop_active": estop_active,
        "robot_busy": robot_busy,
        "destination": destination_name,
        "approach_distance_m": approach_distance_m,
    }

    if estop_active and command_type != "emergency_stop":
        return ValidationResult(False, "E-STOP is active", checks)
    if cfg.block_when_robot_busy and robot_busy and command_type not in BYPASS_BUSY_COMMANDS:
        return ValidationResult(False, "robot is busy", checks)
    if not (cfg.min_approach_distance_m <= approach_distance_m <= cfg.max_approach_distance_m):
        return ValidationResult(False, "approach distance out of range", checks)

    if command_type not in TARGET_COMMANDS:
        return ValidationResult(True, "command does not require target", checks, "simulation_only", False)

    if target is None:
        return ValidationResult(False, "no target selected", checks)

    target_age_s = max(0.0, now - float(locked_at if locked_at is not None else getattr(target, "timestamp", now)))
    checks.update(
        {
            "target_id": getattr(target, "target_id", None),
            "target_age_s": target_age_s,
            "confidence": getattr(target, "confidence", None),
            "stability_score": getattr(target, "stability_score", None),
            "depth_m": getattr(target, "depth_m", None),
            "pose_base_available": getattr(target, "pose_base", None) is not None,
            "status": getattr(target, "status", None),
            "bearing_available": bool(getattr(target, "bearing", None) or getattr(target, "quality", {}).get("bearing")),
        }
    )
    if target_age_s > cfg.target_max_age_s:
        return ValidationResult(False, "target snapshot is stale", checks)
    if (
        command_type == "move_near_target"
        and checks["bearing_available"]
        and getattr(target, "status", None) in {"BEARING_ONLY", "APPROACH", "PARTIAL_DEPTH", "POSE_6DOF"}
    ):
        return ValidationResult(True, "bearing target accepted for approach; simulation only", checks, "simulation_only", False)
    if float(getattr(target, "confidence", 0.0) or 0.0) < cfg.min_confidence:
        return ValidationResult(False, "target confidence is too low", checks)
    if float(getattr(target, "stability_score", 0.0) or 0.0) < cfg.min_stability:
        return ValidationResult(False, "target stability is too low", checks)
    if cfg.require_depth_for_motion and getattr(target, "depth_m", None) is None:
        return ValidationResult(False, "target depth is missing", checks)

    pose_base = getattr(target, "pose_base", None)
    if pose_base is None:
        if cfg.allow_simulation_without_pose_base:
            return ValidationResult(True, "pose_base missing; simulation only", checks, "simulation_only", False)
        return ValidationResult(False, "pose_base missing", checks)

    return ValidationResult(True, "validation passed", checks, "real_robot", True)
