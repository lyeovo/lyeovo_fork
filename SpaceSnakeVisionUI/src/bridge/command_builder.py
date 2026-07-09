import time
from typing import Any, Dict, Optional

from ..models import Pose3D, TaskCommand, new_command_id


ZONE_POSES = {
    "Assembly_Port_A": Pose3D(frame_id="robot_base"),
    "Assembly_Port_B": Pose3D(frame_id="robot_base"),
    "Holding_Zone": Pose3D(frame_id="robot_base"),
    "Safe_Zone": Pose3D(frame_id="robot_base"),
}
ZONE_POSES["Assembly_Port_A"].position.x = 0.35
ZONE_POSES["Assembly_Port_A"].position.y = 0.10
ZONE_POSES["Assembly_Port_A"].position.z = 0.20
ZONE_POSES["Assembly_Port_B"].position.x = 0.35
ZONE_POSES["Assembly_Port_B"].position.y = -0.10
ZONE_POSES["Assembly_Port_B"].position.z = 0.20
ZONE_POSES["Holding_Zone"].position.x = 0.20
ZONE_POSES["Holding_Zone"].position.z = 0.15
ZONE_POSES["Safe_Zone"].position.x = 0.10
ZONE_POSES["Safe_Zone"].position.z = 0.30


def build_task_command(
    command_type: str,
    selected_target,
    destination_name: Optional[str],
    approach_distance_m: float,
    speed_mode: str,
    gripper_mode: str,
    estop_active: bool = False,
    *,
    robot_busy: bool = False,
    validation_report: Optional[Dict[str, Any]] = None,
    locked_at: Optional[float] = None,
    execution_mode: str = "simulation_only",
) -> TaskCommand:
    destination: Optional[Dict[str, Any]] = None
    if destination_name and destination_name in ZONE_POSES:
        destination = {"name": destination_name, "pose_base": ZONE_POSES[destination_name].to_dict()}
    return TaskCommand(
        schema_version="1.1",
        command_id=new_command_id(),
        timestamp=time.time(),
        source="SpaceSnakeVisionUI",
        command_type=command_type,
        selected_target=_target_summary(selected_target, locked_at) if selected_target else None,
        destination=destination,
        motion_params={
            "approach_distance_m": approach_distance_m,
            "speed_mode": speed_mode,
            "gripper_mode": gripper_mode,
            "stop_if_target_lost": True,
        },
        safety=_safety_summary(estop_active, robot_busy, validation_report, execution_mode),
    )


def build_estop_command() -> TaskCommand:
    return TaskCommand(
        "1.1",
        new_command_id("CMD-ESTOP"),
        time.time(),
        "SpaceSnakeVisionUI",
        "emergency_stop",
        safety={
            "require_user_confirm": False,
            "allow_execute": True,
            "allow_real_execute": True,
            "execution_mode": "real_robot",
            "validation_passed": True,
            "validation_message": "E-STOP bypass",
            "estop_active": True,
            "checks": {},
        },
        reason="User pressed E-STOP in UI",
    )


def _target_summary(obj, locked_at: Optional[float] = None) -> Dict[str, Any]:
    now = time.time()
    quality = getattr(obj, "quality", {}) or {}
    pose_available = bool(quality.get("pose_available", obj.status == "POSE_6DOF"))
    return {
        "target_id": obj.target_id,
        "class_name": obj.class_name,
        "display_name": obj.display_name,
        "detection_mode": obj.detection_mode,
        "marker_id": obj.marker_id,
        "confidence": obj.confidence,
        "stability_score": obj.stability_score,
        "timestamp": obj.timestamp,
        "locked_at": locked_at,
        "snapshot_age_s": max(0.0, now - locked_at) if locked_at else None,
        "bbox_xyxy": obj.bbox_xyxy,
        "center_pixel": obj.center_pixel,
        "depth_m": obj.depth_m,
        "status": obj.status,
        "frame_id": obj.pose_camera.frame_id,
        "bearing": getattr(obj, "bearing", None) or quality.get("bearing") or quality.get("last_seen_bearing"),
        "quality": {
            "num_dots": quality.get("num_dots"),
            "valid_depth_points": quality.get("valid_depth_points"),
            "confidence": quality.get("confidence", obj.confidence),
            "match_error_m": quality.get("match_error_m"),
            "plane_rmse_m": quality.get("plane_rmse_m"),
            "pose_rmse_m": quality.get("pose_rmse_m"),
        },
        "pose_camera": obj.pose_camera.to_dict() if pose_available else None,
        "pose_base": obj.pose_base.to_dict() if obj.pose_base else None,
    }


def _safety_summary(
    estop_active: bool,
    robot_busy: bool,
    validation_report: Optional[Dict[str, Any]],
    execution_mode: str,
) -> Dict[str, Any]:
    report = validation_report or {}
    validation_passed = bool(report.get("validation_passed", not estop_active))
    return {
        "require_user_confirm": True,
        "allow_execute": validation_passed and not estop_active,
        "allow_real_execute": bool(report.get("allow_real_execute", False)),
        "execution_mode": report.get("execution_mode", execution_mode),
        "validation_passed": validation_passed,
        "validation_message": report.get("validation_message", "validation not provided"),
        "checks": report.get("checks", {}),
        "estop_active": estop_active,
        "robot_busy": robot_busy,
    }
