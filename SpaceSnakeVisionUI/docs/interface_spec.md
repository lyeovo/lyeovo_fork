# SpaceSnakeVisionUI Interface Spec

## Frames and Units

```yaml
frames:
  camera_frame: "camera_color_optical_frame"
  robot_base_frame: "robot_base"
  end_effector_frame: "end_effector"
  world_frame: "world"
units:
  position: "meter"
  angle: "radian"
  time: "unix timestamp seconds"
```

第一版必须提供 `pose_camera`。在手眼标定完成前，`pose_base` 可以为 `null`，控制模块应拒绝真实执行或只进入仿真。

## TaskCommand

UI 发布文件：

```text
data/outbox/CMD-YYYYMMDD-NNNNN.json
```

示例：

```json
{
  "schema_version": "1.0",
  "command_id": "CMD-20260702-00007",
  "timestamp": 1780000001.456,
  "source": "SpaceSnakeVisionUI",
  "command_type": "pick_and_place",
  "selected_target": {
    "target_id": "TGT-001",
    "class_name": "payload_module",
    "confidence": 0.92,
    "pose_camera": {
      "frame_id": "camera_color_optical_frame",
      "position": {"x": 0.182, "y": -0.041, "z": 0.526},
      "orientation_euler": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
      "orientation_quat": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    },
    "pose_base": null
  },
  "destination": {
    "name": "Assembly_Port_A",
    "pose_base": {
      "frame_id": "robot_base",
      "position": {"x": 0.35, "y": 0.1, "z": 0.2},
      "orientation_euler": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
      "orientation_quat": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    }
  },
  "motion_params": {
    "approach_distance_m": 0.05,
    "speed_mode": "demo_safe",
    "gripper_mode": "demo_grip",
    "stop_if_target_lost": true
  },
  "safety": {
    "require_user_confirm": true,
    "allow_execute": true,
    "estop_active": false
  }
}
```

支持的 `command_type`：

- `move_near_target`
- `pick_target`
- `pick_and_place`
- `dock_to_interface`
- `home`
- `cancel_task`
- `emergency_stop`

## TaskStatus

控制模块返回文件：

```text
data/inbox/CMD-YYYYMMDD-NNNNN_status.json
```

示例：

```json
{
  "schema_version": "1.0",
  "command_id": "CMD-20260702-00007",
  "timestamp": 1780000003.0,
  "status": "EXECUTING",
  "current_step": "MOVING_TO_PREGRASP",
  "progress": 0.42,
  "message": "Moving to pre-grasp pose",
  "robot_state": {
    "state": "EXECUTING",
    "end_effector_pose_base": null,
    "joint_positions": [],
    "message": ""
  }
}
```

状态枚举：

```text
RECEIVED
ACCEPTED
REJECTED
PLANNING
EXECUTING
PAUSED
COMPLETED
FAILED
CANCELED
ESTOP_TRIGGERED
```
