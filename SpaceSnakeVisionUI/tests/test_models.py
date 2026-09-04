import json

from src.models import DetectedObject, Pose3D, RobotState, TaskStatus


def test_pose_json_round_trip():
    pose = Pose3D()
    restored = Pose3D.from_json(pose.to_json())
    assert restored.frame_id == "camera_color_optical_frame"


def test_detected_object_json_round_trip():
    obj = DetectedObject(
        target_id="TGT-001",
        timestamp=1.0,
        class_name="payload_module",
        display_name="载荷模块 1",
        detection_mode="mock_depth",
        marker_id=12,
        confidence=0.9,
        stability_score=0.8,
        bbox_xyxy=[1, 2, 3, 4],
        center_pixel=[2, 3],
        depth_m=0.5,
        pose_camera=Pose3D(),
    )
    restored = DetectedObject.from_json(obj.to_json())
    assert restored.target_id == "TGT-001"
    assert restored.pose_camera.position.z == 0.0


def test_robot_state_extended_round_trip():
    rs = RobotState(
        state="EXECUTING",
        end_effector_pose_base=Pose3D(frame_id="robot_base"),
        joint_positions=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        joint_positions_unit="rad",
        gripper=2,
        message="normal",
    )
    restored = RobotState.from_dict(json.loads(rs.to_json()))
    assert restored.joint_positions_unit == "rad"
    assert restored.gripper == 2
    assert restored.joint_positions == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert restored.end_effector_pose_base is not None
    assert restored.end_effector_pose_base.frame_id == "robot_base"


def test_robot_state_tolerates_empty_ee_and_unknown_keys():
    # MATLAB jsonencode 会把空位姿写成 []；并需容忍未知键
    data = {
        "state": "IDLE",
        "end_effector_pose_base": [],
        "joint_positions": [0, 0, 0, 0, 0, 0],
        "some_future_field": 123,
    }
    rs = RobotState.from_dict(data)
    assert rs.end_effector_pose_base is None
    assert rs.joint_positions_unit == "deg"  # 缺省按度
    assert rs.gripper == 0


def test_task_status_extended_round_trip():
    ts = TaskStatus(
        schema_version="1.0",
        command_id="CMD-1",
        timestamp=1.0,
        status="EXECUTING",
        current_step="EXECUTING_MOVE_TO",
        progress=0.5,
        message="moving",
        robot_state=RobotState(state="EXECUTING", gripper=1, joint_positions_unit="deg"),
        planner={
            "method_used": "rrtstar",
            "solve_time_ms": 21.0,
            "tracking_error_mm": 4.1,
            "angle_error_deg": 1.7,
        },
    )
    restored = TaskStatus.from_json(ts.to_json())
    assert restored.planner["method_used"] == "rrtstar"
    assert restored.planner["tracking_error_mm"] == 4.1
    assert restored.robot_state.gripper == 1
    assert restored.robot_state.end_effector_pose_base is None


def test_task_status_defaults_planner_and_tolerates_ee_list():
    raw = json.dumps(
        {
            "schema_version": "1.0",
            "command_id": "CMD-2",
            "timestamp": 2.0,
            "status": "COMPLETED",
            "current_step": "DONE",
            "progress": 1.0,
            "message": "ok",
            "robot_state": {
                "state": "COMPLETED",
                "end_effector_pose_base": [],
                "joint_positions": [0, 0, 0, 0, 0, 0],
            },
        }
    )
    ts = TaskStatus.from_json(raw)
    assert ts.planner == {}
    assert ts.robot_state.end_effector_pose_base is None
    assert ts.status == "COMPLETED"
