# 视觉 UI 与运动控制数据接口

本文给运动控制同学使用，说明如何从视觉 UI 获得目标相对相机的位置，以及如何通过文件桥接接收任务命令、回写执行状态。

## 1. 坐标系约定

当前视觉模块稳定输出的是相机坐标系下的数据：

```text
frame_id = camera_left
X: 相机图像右方向
Y: 相机图像下方向
Z: 相机前方
单位: meter
```

远距离阶段只保证方位：

```text
target bearing = ray_camera
```

近距离阶段才输出完整位姿：

```text
target pose_camera = position + quaternion
```

注意：`camera_pose_base` 当前为 `null`，因为还没有手眼标定。运动控制如果要把 `camera_left` 下的目标位置变换到 `robot_base`，需要后续提供：

```text
T_base_camera
```

## 2. 实时视觉状态文件

UI 运行时每帧会写：

```text
SpaceSnakeVisionUI/data/vision/latest_targets.json
```

运动控制端可以轮询这个文件。写入是原子替换，读到半截 JSON 的概率很低；如果偶发解析失败，下一帧重读即可。

启动 UI：

```powershell
cd D405_MarkerVision\SpaceSnakeVisionUI
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file
```

另开一个终端模拟运动控制端读取：

```powershell
cd D405_MarkerVision\SpaceSnakeVisionUI
.\.venv\Scripts\python.exe scripts\watch_latest_vision_state.py
```

## 3. latest_targets.json 结构

示例：

```json
{
  "schema_version": "vision_state.v1",
  "timestamp": 1783520000.123,
  "frame_id": "camera_left",
  "camera_pose_base": null,
  "camera_pose_note": "camera_pose_base is null until hand-eye calibration is provided",
  "selected_target_id": "target_1",
  "selected_target": {
    "target_id": "target_1",
    "status": "POSE_6DOF",
    "frame_id": "camera_left",
    "depth_m": 0.25,
    "bearing": {
      "pixel_center": [424.0, 238.0],
      "pixel_error": [0.0, 0.0],
      "ray_camera": [0.01, -0.02, 0.9997]
    },
    "pose_camera": {
      "frame_id": "camera_left",
      "position": {"x": 0.01, "y": -0.02, "z": 0.25},
      "orientation_euler": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
      "orientation_quat": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    },
    "pose_base": null,
    "quality": {
      "num_dots": 8,
      "valid_depth_points": 8,
      "confidence": 0.92,
      "rough_distance_m": 0.25,
      "pose_available": true
    }
  },
  "targets": []
}
```

## 4. 控制策略建议

运动控制端不要只看 `depth_m`，应按 `status` 决策：

```text
SEARCH
  没有目标，停止前进或做小范围搜索。

BEARING_ONLY
  远距离 YOLO 已锁定目标。使用 bearing.ray_camera 做闭环靠近。
  此时 pose_camera = null，不要执行抓取/插接等精动作。

PARTIAL_DEPTH
  已有部分白点深度，但不足以稳定 6DoF。可以继续小步靠近或微调视角。

POSE_6DOF
  近距离白点深度足够，pose_camera 可用。可以进入精定位、对接或抓取流程。

LOST
  短时丢失目标。暂停前进，使用 last bearing 或小范围搜索。
```

远距离靠近可以使用：

```text
ray_camera = [rx, ry, rz]
横向误差 ~= rx / rz
纵向误差 ~= ry / rz
```

例如：

```text
rx > 0: 目标在相机右侧
rx < 0: 目标在相机左侧
ry > 0: 目标在图像下方
ry < 0: 目标在图像上方
```

## 5. 任务命令文件桥接

UI 点击“发布命令”后，会写：

```text
SpaceSnakeVisionUI/data/outbox/CMD-*.json
```

控制端处理完后回写：

```text
SpaceSnakeVisionUI/data/inbox/{command_id}_status.json
```

命令中的目标字段和实时状态文件一致，核心字段是：

```json
{
  "selected_target": {
    "target_id": "target_1",
    "status": "POSE_6DOF",
    "bearing": {},
    "pose_camera": {},
    "pose_base": null,
    "quality": {}
  }
}
```

当 `pose_base == null` 时，真实机械臂不能直接按基座坐标执行；应先做手眼标定，或者只使用 bearing 做靠近。

## 6. 推荐对接步骤

1. 先跑 UI，确认 `data/vision/latest_targets.json` 持续更新。
2. 控制端只读 `latest_targets.json`，实现远距离 `BEARING_ONLY` 闭环靠近。
3. 靠近到 D405 白点深度稳定后，等待 `POSE_6DOF`。
4. 做手眼标定，得到 `T_base_camera`。
5. 将 `pose_camera` 转成 `pose_base`，再允许真实精动作。
6. 最后接入 `data/outbox` / `data/inbox` 任务命令闭环。
