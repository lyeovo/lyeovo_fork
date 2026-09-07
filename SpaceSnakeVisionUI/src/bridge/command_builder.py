import time
from typing import Any, Dict, Optional

from ..models import Pose3D, TaskCommand, new_command_id


# 单一终点放置区（与 mission_map.GOAL_ZONE 对齐）：地图右侧，中心 map(x=4.0, y=2.0)
ZONE_POSES = {
    "Goal_Zone": Pose3D(frame_id="robot_base"),
}
ZONE_POSES["Goal_Zone"].position.x = 4.0
ZONE_POSES["Goal_Zone"].position.y = 2.0
ZONE_POSES["Goal_Zone"].position.z = 0.0


def build_task_command(
    command_type: str,
    params: Optional[Dict[str, Any]] = None,
    selected_target = None,
    destination_name: Optional[str] = None,
    estop_active: bool = False,
    *,
    robot_busy: bool = False,
    validation_report: Optional[Dict[str, Any]] = None,
    locked_at: Optional[float] = None,
    execution_mode: str = "simulation_only",
) -> TaskCommand:
    clean_params = dict(params or {})
    destination: Optional[Dict[str, Any]] = None
    if destination_name and destination_name in ZONE_POSES:
        destination = {"name": destination_name, "pose_base": ZONE_POSES[destination_name].to_dict()}
    elif command_type == "move_for_place" and "destination" in clean_params:
        destination = {"name": clean_params["destination"]}

    return TaskCommand(
        schema_version="2.0",
        command_id=new_command_id(),
        timestamp=time.time(),
        source="SpaceSnakeVisionUI",
        command_type=command_type,
        params=clean_params,
        selected_target=_target_summary(selected_target, locked_at) if selected_target else None,
        destination=destination,
        motion_params=clean_params,
        safety=_safety_summary(estop_active, robot_busy, validation_report, execution_mode),
    )


def build_estop_command() -> TaskCommand:
    return TaskCommand(
        schema_version="2.0",
        command_id=new_command_id("CMD-ESTOP"),
        timestamp=time.time(),
        source="SpaceSnakeVisionUI",
        command_type="emergency_stop",
        params={},
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


def camera_to_base_pose(
    pose_camera: Pose3D,
    joint_angles_deg: Optional[list] = None,
    seg_len_m: float = 1.04393,
    n_segments: int = 6,
) -> Pose3D:
    """根据机械臂顺向运动学 (FK) 将末端相机的局部相对位姿转换为空间基座绝对物理位姿"""
    import math
    from ..models import Euler, Vector3

    angles = joint_angles_deg or [0.0] * n_segments
    cur_x, cur_y = 0.0, 0.0
    accum_angle = math.pi / 2.0  # 初始垂直向上 (+Y 轴)
    for idx in range(n_segments):
        deg = angles[idx] if idx < len(angles) else 0.0
        accum_angle += math.radians(deg)
        cur_x += seg_len_m * math.cos(accum_angle)
        cur_y += seg_len_m * math.sin(accum_angle)

    cam_x = pose_camera.position.x
    cam_z = pose_camera.position.z
    # 前向深度沿 accum_angle，横偏沿右侧法向
    world_x = cur_x + cam_z * math.cos(accum_angle) + cam_x * math.sin(accum_angle)
    world_y = cur_y + cam_z * math.sin(accum_angle) - cam_x * math.cos(accum_angle)
    return Pose3D(
        frame_id="robot_base",
        position=Vector3(x=round(world_x, 4), y=round(world_y, 4), z=0.0),
        orientation_euler=Euler(roll=0.0, pitch=0.0, yaw=round(accum_angle, 4)),
    )


def _target_summary(obj, locked_at: Optional[float] = None) -> Dict[str, Any]:
    now = time.time()
    quality = getattr(obj, "quality", {}) or {}
    pose_available = getattr(obj, "pose_camera", None) is not None

    pose_base = obj.pose_base.to_dict() if getattr(obj, "pose_base", None) else None
    if pose_base is None and pose_available and obj.pose_camera.position.z > 0.02:
        pb_obj = camera_to_base_pose(obj.pose_camera)
        pose_base = pb_obj.to_dict()

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
        "frame_id": obj.pose_camera.frame_id if pose_available else "camera_left",
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
        "pose_base": pose_base,
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
