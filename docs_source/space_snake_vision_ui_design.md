# 面向航天器在轨组装的蛇形机器人交互式视觉作业系统设计说明

> 文件用途：本说明用于交给 Codex 生成项目代码。目标是实现一个 **太空任务风格 UI + Intel RealSense D405 相机视觉感知 + 任务指令发布接口** 的工程原型，并为后续与机械控制/运动规划同学联调预留稳定接口。

---

## 0. 项目名称

建议项目名：`SpaceSnakeVisionUI`

中文名：**蛇形机器人交互式视觉作业系统**

英文界面标题建议：

```text
ORBITAL SNAKE ROBOT MISSION CONTROL
```

---

## 1. 项目背景与系统定位

本项目背景是 **面向航天器在轨组装应用的超冗余自由度蛇形机器人**。任务设想为：服务星搭载长距离超冗余蛇形机械臂，末端安装相机和抓持工具；相机识别环境中的载荷模块、对接口或待操作物体；系统根据目标位姿规划蛇形臂动作，实现靠近、抓取、移动、对接等任务。

本 UI 子系统不直接完成机械控制，而是作为 **视觉感知、人机确认、任务发布、状态监控** 的中间层。它的核心定位是：

```text
D405 相机感知环境中的多个候选目标
        ↓
UI 以太空任务控制台风格显示目标、坐标、置信度和状态
        ↓
用户人工选择目标并指定任务类型，例如抓取、移动、对接
        ↓
系统封装为标准任务命令 TaskCommand
        ↓
通过 JSON / Socket / ROS2 接口发送给机械控制与运动规划模块
        ↓
控制模块返回任务状态，UI 实时显示执行进度
```

本阶段的目标不是完全自主作业，而是实现 **人机交互式视觉引导作业**：机器人自动“看见”目标，人负责“选择任务目标与作业意图”，控制模块负责“规划与执行”。

---

## 2. 总体设计目标

### 2.1 必须实现的功能

1. 使用 Intel RealSense D405 获取实时 RGB 图像和深度图。
2. 在 UI 中显示实时相机画面。
3. 识别环境中多个目标，并显示目标框、编号、类别、坐标、置信度。
4. 支持用户在相机画面或目标列表中选择目标。
5. 支持用户选择任务类型：
   - 移动到目标附近；
   - 抓取目标；
   - 抓取并移动到指定位置；
   - 对接到指定接口；
   - 回零；
   - 取消/暂停/急停。
6. 支持指定目标放置位置或对接口位置。
7. 将用户选择封装成统一的任务命令 `TaskCommand`。
8. 将任务命令保存为 JSON，并提供后续给控制同学接入的接口。
9. 支持模拟控制模块，方便在机械系统未完成前演示完整闭环。
10. UI 风格必须符合“太空环境、服务星、载荷星、在轨组装、任务控制台”的背景。

### 2.2 暂时不要求实现的功能

1. 不要求直接控制真实机械臂。
2. 不要求完成完整逆运动学求解。
3. 不要求完成高精度手眼标定。
4. 不要求一次性实现 ROS2 自定义消息，可以先用 JSON 字符串接口。
5. 不要求 YOLO 训练模型完整接入，可以先用 ArUco / AprilTag / 颜色块 / 模拟目标作为检测入口。

---

## 3. 推荐技术栈

### 3.1 主体技术路线

优先推荐：

```text
Python + PySide6 + OpenCV + pyrealsense2 + JSON/Socket Bridge
```

原因：

1. 当前视觉部分大概率已经基于 Python/OpenCV 实现，迁移成本低。
2. PySide6 可以做出比较正式的桌面 UI，适合最终演示。
3. pyrealsense2 可以直接读取 D405 的 RGB 和深度信息。
4. JSON/Socket 接口便于后续与机械控制同学联调。
5. ROS2 可作为后续扩展，不强依赖第一版开发环境。

### 3.2 主要依赖

建议 `requirements.txt`：

```txt
numpy
opencv-contrib-python
PySide6
pyrealsense2
pydantic
pyyaml
scipy
websockets
loguru
pytest
```

说明：

- `opencv-contrib-python`：用于 ArUco / AprilTag 相关功能。
- `pyrealsense2`：用于 Intel RealSense D405。
- `PySide6`：用于桌面 UI。
- `pydantic`：用于统一数据模型和 JSON 校验。
- `websockets`：可选，用于与控制模块通信。
- `loguru`：用于日志。

---

## 4. 系统架构

### 4.1 总体模块图

```text
┌─────────────────────────────────────────────────────────────────┐
│                      SpaceSnakeVisionUI                         │
├─────────────────────────────────────────────────────────────────┤
│  Camera Layer                                                    │
│  ├── RealSenseD405Camera                                         │
│  └── MockCamera                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Vision Layer                                                    │
│  ├── ArucoDetector / AprilTagDetector                            │
│  ├── DepthPoseEstimator                                          │
│  ├── ObjectTracker                                               │
│  └── TargetStabilityChecker                                      │
├─────────────────────────────────────────────────────────────────┤
│  UI Layer                                                        │
│  ├── MainWindow                                                  │
│  ├── CameraViewWidget                                            │
│  ├── TargetTableWidget                                           │
│  ├── TaskCommandPanel                                            │
│  ├── MissionMapWidget                                            │
│  ├── RobotStatusPanel                                            │
│  └── LogConsole                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Command & Bridge Layer                                          │
│  ├── TaskCommandBuilder                                          │
│  ├── FileBridge                                                  │
│  ├── SocketBridge                                                │
│  ├── MockControlServer                                           │
│  └── ROS2Bridge Optional                                         │
├─────────────────────────────────────────────────────────────────┤
│  Data Models                                                     │
│  ├── DetectedObject                                              │
│  ├── TargetPose                                                  │
│  ├── TaskCommand                                                 │
│  ├── TaskStatus                                                  │
│  └── RobotState                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 数据流

```text
D405 RGB + Depth
        ↓
CameraManager 获取帧
        ↓
VisionPipeline 检测目标并估计坐标/位姿
        ↓
ObjectTracker 分配 target_id 并稳定跟踪
        ↓
UI 显示目标框、坐标、置信度、状态
        ↓
用户选择目标 + 选择任务 + 设置目标位置
        ↓
TaskCommandBuilder 生成标准命令
        ↓
FileBridge / SocketBridge / ROS2Bridge 发布命令
        ↓
控制模块返回 TaskStatus / RobotState
        ↓
UI 更新任务进度与机器人状态
```

---

## 5. UI 风格设计

### 5.1 视觉风格关键词

UI 不能做成普通工业按钮界面，而要体现项目背景。整体风格建议：

```text
太空任务控制台
深空蓝黑背景
卫星轨道线
赛博蓝色边框
半透明信息面板
任务编号
坐标读数
状态灯
类似航天测控大厅的实时监控界面
```

建议英文元素：

```text
MISSION CONTROL
ORBITAL ASSEMBLY
SERVICE SATELLITE
PAYLOAD MODULE
TARGET LOCKED
DOCKING PORT
MANIPULATOR STATUS
VISION ONLINE
COMMAND ARMED
```

中文元素：

```text
在轨组装任务控制台
服务星视觉系统
载荷模块识别
目标锁定
对接接口
蛇形机械臂状态
任务指令发布
安全监控
```

### 5.2 配色规范

建议使用深色主题：

```yaml
background_main: "#050814"
background_panel: "#0B1026"
panel_border: "#1E88E5"
primary_cyan: "#00E5FF"
primary_blue: "#2F6BFF"
success_green: "#2EEA8A"
warning_amber: "#FFC857"
danger_red: "#FF4D5A"
text_primary: "#EAF6FF"
text_secondary: "#8FA6C8"
grid_line: "#1B2A4A"
selected_target: "#00E5FF"
locked_target: "#2EEA8A"
invalid_target: "#FF4D5A"
```

### 5.3 字体规范

- 中文界面字体：`Microsoft YaHei UI`。
- 数字/坐标/日志字体：`JetBrains Mono` 或 `Consolas`。
- 坐标、任务编号、时间戳使用等宽字体，增强仪表盘感。

### 5.4 主界面布局

推荐分辨率：`1280 × 800`，也要适配 `1920 × 1080`。

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 顶部状态栏：ORBITAL SNAKE ROBOT MISSION CONTROL                           │
│ Camera: ONLINE | Vision: RUNNING | Bridge: CONNECTED | Robot: IDLE | E-STOP │
├──────────────────────────────────────────────┬─────────────────────────────┤
│ 左侧主视觉区                                  │ 右侧目标与任务区             │
│ ┌──────────────────────────────────────────┐ │ ┌─────────────────────────┐ │
│ │ D405 实时画面                            │ │ │ 目标列表 TARGETS        │ │
│ │ 目标框、编号、坐标、锁定准星               │ │ │ Target 0 red_block ...   │ │
│ │                                          │ │ │ Target 1 dock_port ...   │ │
│ └──────────────────────────────────────────┘ │ └─────────────────────────┘ │
│ ┌──────────────────────────────────────────┐ │ ┌─────────────────────────┐ │
│ │ 任务地图 / 俯视坐标系                     │ │ │ 当前选中目标             │ │
│ │ 服务星、相机、目标点、放置区、对接口         │ │ │ 坐标、姿态、置信度       │ │
│ └──────────────────────────────────────────┘ │ └─────────────────────────┘ │
│                                                │ ┌─────────────────────────┐ │
│                                                │ │ 任务指令 COMMAND PANEL  │ │
│                                                │ │ 抓取/移动/对接/回零      │ │
│                                                │ │ 放置位置/接口选择        │ │
│                                                │ └─────────────────────────┘ │
├──────────────────────────────────────────────┴─────────────────────────────┤
│ 底部日志与安全控制：日志、任务进度、暂停、取消、急停                         │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. UI 功能详细设计

### 6.1 顶部状态栏

顶部状态栏显示全局系统状态：

| 字段 | 示例 | 含义 |
|---|---|---|
| Mission Time | `T+00:12:31` | 系统运行时间 |
| Camera | `ONLINE` / `OFFLINE` | D405 是否在线 |
| Vision | `RUNNING` / `PAUSED` | 视觉算法是否运行 |
| Bridge | `CONNECTED` / `FILE MODE` / `DISCONNECTED` | 与控制模块通信状态 |
| Robot | `IDLE` / `PLANNING` / `EXECUTING` / `ERROR` | 机器人状态 |
| E-STOP | `SAFE` / `TRIGGERED` | 急停状态 |

颜色规则：

```text
ONLINE / RUNNING / SAFE      绿色
FILE MODE / WARNING          黄色
OFFLINE / ERROR / TRIGGERED  红色
```

### 6.2 左侧实时视觉画面

功能：

1. 显示 D405 RGB 实时画面。
2. 叠加目标检测框。
3. 显示目标编号、类别、坐标、置信度。
4. 对选中目标显示十字准星和“TARGET LOCKED”。
5. 支持鼠标点击目标框进行选择。
6. 支持显示深度无效警告。
7. 支持显示目标丢失警告。

叠加文字示例：

```text
TGT-003  PAYLOAD_MODULE
x=0.182m y=-0.041m z=0.526m
conf=0.93  status=TRACKING
```

选中后显示：

```text
TARGET LOCKED: TGT-003
```

### 6.3 目标列表 Target Table

目标列表显示当前识别到的所有候选目标。

表格字段：

| 字段 | 说明 |
|---|---|
| ID | 目标编号，例如 `TGT-001` |
| 类别 | `payload_module` / `dock_port` / `lego_block` / `aruco_marker` |
| x | 相机系或基座系 x 坐标，单位 m |
| y | 相机系或基座系 y 坐标，单位 m |
| z | 深度，单位 m |
| 置信度 | 检测置信度 |
| 稳定度 | 目标连续帧稳定程度 |
| 状态 | 可执行/坐标不稳定/深度无效/已锁定/执行中 |

状态定义：

```text
AVAILABLE       可执行
LOCKED          已锁定
UNSTABLE        坐标不稳定
DEPTH_INVALID   深度无效
OUT_OF_RANGE    超出工作空间
LOST            目标丢失
EXECUTING       执行中
DONE            已完成
```

### 6.4 当前选中目标信息面板

用户选中目标后，右侧显示详细信息：

```text
Selected Target
ID: TGT-003
Class: payload_module
Detection Mode: ArUco + Depth
Marker ID: 12
Confidence: 0.93
Stability: 0.87

Camera Frame Pose:
x = 0.182 m
y = -0.041 m
z = 0.526 m
roll  = 0.00 rad
pitch = 0.02 rad
yaw   = -0.01 rad

Base Frame Pose:
Not Available / Waiting for calibration
```

说明：机械结构还没完全确定时，`Base Frame Pose` 可以显示 `Not Available`，但数据模型必须预留 `pose_base` 字段。

### 6.5 任务指令面板 Command Panel

任务类型按钮：

```text
[移动到目标附近]
[抓取目标]
[抓取并移动]
[对接到接口]
[回到初始位姿]
```

任务参数区：

1. 接近距离：默认 `0.05 m`。
2. 速度模式：`low` / `normal` / `demo_safe`。
3. 抓取模式：`soft_grip` / `firm_grip` / `demo_grip`。
4. 放置位置：
   - `Assembly Port A`
   - `Assembly Port B`
   - `Holding Zone`
   - `Safe Zone`
   - `Custom Pose`

自定义位置输入：

```text
x: ____ m
y: ____ m
z: ____ m
roll: ____ rad
pitch: ____ rad
yaw: ____ rad
```

确认按钮：

```text
[锁定目标]
[预检查]
[生成任务]
[发布命令]
```

安全按钮：

```text
[暂停]
[继续]
[取消任务]
[急停]
```

### 6.6 任务地图 Mission Map

可以先实现二维俯视图，不必一开始做完整三维。

显示内容：

1. 相机位置。
2. 机器人基座位置。
3. 当前识别目标点。
4. 选中目标点。
5. 放置区域。
6. 对接接口 A/B/C/D。
7. 任务路径示意线。

地图风格：深色网格 + 坐标轴 + 小卫星图标。

### 6.7 日志与任务进度

日志示例：

```text
[12:31:05] Camera online: Intel RealSense D405
[12:31:06] Vision pipeline started
[12:31:09] Detected 3 targets
[12:31:12] Target TGT-003 locked
[12:31:16] Command generated: pick_and_place
[12:31:17] Command published to outbox/task_0007.json
[12:31:18] Waiting for control module response
[12:31:22] Task accepted by mock control server
```

任务进度条：

```text
Step 1/5 Target Locked        DONE
Step 2/5 Pre-check            DONE
Step 3/5 Planning             RUNNING
Step 4/5 Executing            WAITING
Step 5/5 Completed            WAITING
```

---

## 7. D405 相机与视觉模块设计

### 7.1 D405 采集要求

默认参数：

```yaml
camera:
  type: "realsense_d405"
  color_width: 640
  color_height: 480
  depth_width: 640
  depth_height: 480
  fps: 30
  align_depth_to_color: true
  enable_depth: true
  enable_color: true
```

D405 模块必须提供：

```python
class CameraFrame:
    color_image: np.ndarray
    depth_image: np.ndarray
    depth_colormap: np.ndarray | None
    intrinsics: CameraIntrinsics
    timestamp: float
```

### 7.2 无相机模式

为了方便 Codex 和其他同学在没有 D405 的电脑上开发，必须提供 `MockCamera`。

`MockCamera` 功能：

1. 读取本地图片或视频。
2. 生成模拟深度。
3. 生成若干模拟目标。
4. 保证 UI 可以在无 D405 情况下启动。

启动参数：

```bash
python -m src.main --camera mock
python -m src.main --camera d405
```

### 7.3 目标检测方式

第一阶段优先实现 ArUco 检测：

```text
目标物体上贴 ArUco / AprilTag
相机识别 marker ID
利用角点 + 标记实际尺寸估计 6DoF 位姿
同时读取深度图校验距离
```

也要预留 YOLO 或颜色识别入口：

```text
DetectorBase
├── ArucoDetector
├── ColorBlockDetector
├── YoloDetector Placeholder
└── MockDetector
```

### 7.4 ArUco 位姿估计注意事项

OpenCV 版本可能存在 `cv2.aruco.estimatePoseSingleMarkers` 不可用的问题，因此代码不能只依赖这个函数。需要实现 `solvePnP` 备用方案。

备用方案逻辑：

```python
# 已知 marker_size，例如 0.04 m
object_points = np.array([
    [-s/2,  s/2, 0],
    [ s/2,  s/2, 0],
    [ s/2, -s/2, 0],
    [-s/2, -s/2, 0],
], dtype=np.float32)

success, rvec, tvec = cv2.solvePnP(
    object_points,
    image_points,
    camera_matrix,
    dist_coeffs,
    flags=cv2.SOLVEPNP_IPPE_SQUARE
)
```

### 7.5 深度坐标估计

对于没有姿态的普通目标，可以用检测框中心点和深度估计三维坐标：

```python
center_u = int((x1 + x2) / 2)
center_v = int((y1 + y2) / 2)
depth_m = depth_frame.get_distance(center_u, center_v)
point_xyz = rs.rs2_deproject_pixel_to_point(intrinsics, [center_u, center_v], depth_m)
```

注意事项：

1. 深度为 0 时无效。
2. 应在目标框附近取小窗口中位数深度，避免单点噪声。
3. 坐标单位统一为米。
4. 坐标系需要明确是 `camera_color_optical_frame`。

---

## 8. 数据模型设计

推荐使用 Pydantic 或 dataclass。所有跨模块数据都必须能序列化为 JSON。

### 8.1 Pose3D

```json
{
  "frame_id": "camera_color_optical_frame",
  "position": {
    "x": 0.182,
    "y": -0.041,
    "z": 0.526
  },
  "orientation_euler": {
    "roll": 0.0,
    "pitch": 0.02,
    "yaw": -0.01
  },
  "orientation_quat": {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "w": 1.0
  }
}
```

### 8.2 DetectedObject

```json
{
  "target_id": "TGT-003",
  "timestamp": 1780000000.123,
  "class_name": "payload_module",
  "display_name": "载荷模块 3",
  "detection_mode": "aruco_depth",
  "marker_id": 12,
  "confidence": 0.93,
  "stability_score": 0.87,
  "bbox_xyxy": [120, 80, 220, 190],
  "center_pixel": [170, 135],
  "depth_m": 0.526,
  "pose_camera": {
    "frame_id": "camera_color_optical_frame",
    "position": {"x": 0.182, "y": -0.041, "z": 0.526},
    "orientation_euler": {"roll": 0.0, "pitch": 0.02, "yaw": -0.01},
    "orientation_quat": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
  },
  "pose_base": null,
  "status": "AVAILABLE"
}
```

### 8.3 TaskCommand

```json
{
  "schema_version": "1.0",
  "command_id": "CMD-20260702-0007",
  "timestamp": 1780000001.456,
  "source": "SpaceSnakeVisionUI",
  "command_type": "pick_and_place",
  "selected_target": {
    "target_id": "TGT-003",
    "class_name": "payload_module",
    "confidence": 0.93,
    "pose_camera": {
      "frame_id": "camera_color_optical_frame",
      "position": {"x": 0.182, "y": -0.041, "z": 0.526},
      "orientation_euler": {"roll": 0.0, "pitch": 0.02, "yaw": -0.01},
      "orientation_quat": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    },
    "pose_base": null
  },
  "destination": {
    "name": "Assembly_Port_A",
    "pose_base": {
      "frame_id": "robot_base",
      "position": {"x": 0.35, "y": 0.10, "z": 0.20},
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

### 8.4 TaskStatus

控制模块返回给 UI 的任务状态：

```json
{
  "schema_version": "1.0",
  "command_id": "CMD-20260702-0007",
  "timestamp": 1780000003.000,
  "status": "EXECUTING",
  "current_step": "MOVING_TO_PREGRASP",
  "progress": 0.42,
  "message": "Moving to pre-grasp pose",
  "robot_state": {
    "state": "EXECUTING",
    "end_effector_pose_base": null,
    "joint_positions": []
  }
}
```

`status` 枚举：

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

---

## 9. 与机械控制同学的接口设计

### 9.1 第一阶段：文件接口

用于最快联调。

目录：

```text
data/outbox/     UI 输出任务命令
data/inbox/      控制模块返回任务状态
data/logs/       系统日志
data/recordings/ 录制数据
```

UI 发布命令时生成：

```text
data/outbox/CMD-20260702-0007.json
```

控制模块读取该文件，处理后写入：

```text
data/inbox/CMD-20260702-0007_status.json
```

优点：最简单，适合机械系统未完成时先约定格式。

### 9.2 第二阶段：Socket / WebSocket 接口

建议监听地址：

```yaml
bridge:
  mode: "websocket"
  host: "127.0.0.1"
  port: 8765
```

消息方向：

```text
UI → Control: TaskCommand
Control → UI: TaskStatus, RobotState
```

建议实现一个 `MockControlServer`，收到命令后按时间返回状态：

```text
RECEIVED → ACCEPTED → PLANNING → EXECUTING → COMPLETED
```

这样即使没有真实机械臂，也能演示完整系统闭环。

### 9.3 第三阶段：ROS2 接口预留

如果后续接 ROS2，可以先用 `std_msgs/String` 发布 JSON，避免一开始写自定义 msg。

建议话题：

| Topic | 方向 | 消息类型 | 内容 |
|---|---|---|---|
| `/space_snake/detected_objects` | Vision → UI/Control | `std_msgs/String` | 当前检测目标列表 JSON |
| `/space_snake/selected_target` | UI → Control | `std_msgs/String` | 当前锁定目标 JSON |
| `/space_snake/task_command` | UI → Control | `std_msgs/String` | 任务命令 JSON |
| `/space_snake/task_status` | Control → UI | `std_msgs/String` | 任务状态 JSON |
| `/space_snake/robot_state` | Control → UI | `std_msgs/String` | 机器人状态 JSON |
| `/joint_states` | Control → RViz | `sensor_msgs/JointState` | 关节角 |

后续再升级为自定义消息：

```text
space_snake_msgs/DetectedObjectArray
space_snake_msgs/TaskCommand
space_snake_msgs/TaskStatus
space_snake_msgs/RobotState
```

### 9.4 坐标系约定

必须写入接口文档：

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

在机械结构未完成前：

```text
pose_camera 必须提供
pose_base 可以为 null
```

机械结构完成后：

```text
pose_camera 通过 T_base_camera 转换为 pose_base
控制模块优先使用 pose_base
如果 pose_base 为 null，控制模块需要拒绝真实执行，只允许仿真或等待标定
```

---

## 10. 安全逻辑

### 10.1 发布命令前检查

点击“发布命令”前必须检查：

```text
1. 是否已选择目标？
2. 目标是否仍在最近 N 帧中出现？
3. 目标深度是否有效？
4. 目标稳定度是否大于阈值，例如 0.70？
5. 控制接口是否在线，或者是否处于文件模式？
6. 是否已选择任务类型？
7. 如果任务需要放置位置，是否已选择 destination？
8. 急停是否未触发？
9. 用户是否完成二次确认？
```

只有全部通过，`发布命令` 按钮才允许点击。

### 10.2 急停逻辑

急停按钮必须始终可见。

点击急停后：

```text
1. UI 状态变为 ESTOP_TRIGGERED。
2. 立即发送 command_type = emergency_stop。
3. 禁止发布新的抓取/移动任务。
4. 允许用户点击 Reset E-STOP，但需要二次确认。
```

急停命令示例：

```json
{
  "schema_version": "1.0",
  "command_id": "CMD-ESTOP-0001",
  "timestamp": 1780000005.0,
  "source": "SpaceSnakeVisionUI",
  "command_type": "emergency_stop",
  "reason": "User pressed E-STOP in UI"
}
```

---

## 11. 推荐项目目录结构

```text
SpaceSnakeVisionUI/
├── README.md
├── requirements.txt
├── run_ui.py
├── configs/
│   ├── camera.yaml
│   ├── ui_theme.yaml
│   ├── task_zones.yaml
│   ├── transform.yaml
│   └── bridge.yaml
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── app.py
│   ├── models.py
│   ├── camera/
│   │   ├── __init__.py
│   │   ├── base_camera.py
│   │   ├── realsense_d405.py
│   │   └── mock_camera.py
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   ├── detector_base.py
│   │   ├── aruco_detector.py
│   │   ├── color_block_detector.py
│   │   ├── mock_detector.py
│   │   ├── depth_pose.py
│   │   ├── object_tracker.py
│   │   └── stability.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py
│   │   ├── camera_view.py
│   │   ├── target_table.py
│   │   ├── command_panel.py
│   │   ├── mission_map.py
│   │   ├── status_bar.py
│   │   ├── log_console.py
│   │   └── theme.qss
│   ├── bridge/
│   │   ├── __init__.py
│   │   ├── bridge_base.py
│   │   ├── file_bridge.py
│   │   ├── socket_bridge.py
│   │   ├── mock_control_server.py
│   │   └── ros2_bridge_optional.py
│   └── utils/
│       ├── __init__.py
│       ├── geometry.py
│       ├── image_utils.py
│       ├── config.py
│       └── logging_utils.py
├── data/
│   ├── inbox/
│   ├── outbox/
│   ├── logs/
│   ├── recordings/
│   └── samples/
├── docs/
│   ├── interface_spec.md
│   ├── ui_design.md
│   └── control_integration_guide.md
└── tests/
    ├── test_models.py
    ├── test_command_builder.py
    └── test_geometry.py
```

---

## 12. 配置文件示例

### 12.1 `configs/task_zones.yaml`

```yaml
zones:
  Assembly_Port_A:
    display_name: "装配接口 A"
    frame_id: "robot_base"
    position: {x: 0.35, y: 0.10, z: 0.20}
    orientation_euler: {roll: 0.0, pitch: 0.0, yaw: 0.0}
  Assembly_Port_B:
    display_name: "装配接口 B"
    frame_id: "robot_base"
    position: {x: 0.35, y: -0.10, z: 0.20}
    orientation_euler: {roll: 0.0, pitch: 0.0, yaw: 0.0}
  Holding_Zone:
    display_name: "临时停放区"
    frame_id: "robot_base"
    position: {x: 0.20, y: 0.00, z: 0.15}
    orientation_euler: {roll: 0.0, pitch: 0.0, yaw: 0.0}
  Safe_Zone:
    display_name: "安全等待区"
    frame_id: "robot_base"
    position: {x: 0.10, y: 0.00, z: 0.30}
    orientation_euler: {roll: 0.0, pitch: 0.0, yaw: 0.0}
```

### 12.2 `configs/transform.yaml`

```yaml
# 机械结构未确定时，先不启用真实坐标转换。
transform:
  enable_camera_to_base: false
  camera_frame: "camera_color_optical_frame"
  robot_base_frame: "robot_base"
  T_base_camera:
    translation: {x: 0.0, y: 0.0, z: 0.0}
    rotation_euler: {roll: 0.0, pitch: 0.0, yaw: 0.0}
```

### 12.3 `configs/bridge.yaml`

```yaml
bridge:
  mode: "file"  # file | websocket | ros2
  file:
    outbox_dir: "data/outbox"
    inbox_dir: "data/inbox"
  websocket:
    host: "127.0.0.1"
    port: 8765
  ros2:
    enabled: false
    task_command_topic: "/space_snake/task_command"
    task_status_topic: "/space_snake/task_status"
```

---

## 13. Codex 开发任务拆解

### Task 1：建立项目骨架

要求：

1. 按第 11 节目录结构创建项目。
2. 编写 `README.md`，包含安装、运行、无相机模式、D405 模式。
3. 编写 `requirements.txt`。
4. 实现 `run_ui.py`，支持：

```bash
python run_ui.py --camera mock --bridge file
python run_ui.py --camera d405 --bridge file
python run_ui.py --camera mock --bridge websocket
```

### Task 2：实现数据模型

实现：

```text
Pose3D
DetectedObject
TaskCommand
TaskStatus
RobotState
```

要求：

1. 使用 Pydantic 或 dataclass。
2. 所有模型支持 `to_json()` 和 `from_json()`。
3. 写测试 `tests/test_models.py`。

### Task 3：实现 D405 相机模块

实现：

```text
BaseCamera
RealSenseD405Camera
MockCamera
```

要求：

1. D405 不存在时不能导致 UI 崩溃。
2. 如果 D405 打不开，自动提示并切换到 Mock 模式或退出时给出明确错误。
3. 支持 RGB 与深度对齐。
4. 提供相机内参。

### Task 4：实现视觉检测管线

实现：

```text
VisionPipeline
ArucoDetector
DepthPoseEstimator
ObjectTracker
StabilityChecker
```

要求：

1. 支持 ArUco 检测。
2. 支持 `solvePnP` 备用位姿估计。
3. 支持深度中心点估计。
4. 对每个目标生成 `DetectedObject`。
5. 对连续目标分配稳定 `target_id`。

### Task 5：实现 UI 主界面

实现 PySide6 主界面：

```text
MainWindow
CameraViewWidget
TargetTableWidget
SelectedTargetPanel
TaskCommandPanel
MissionMapWidget
RobotStatusPanel
LogConsole
```

要求：

1. 深色太空风格。
2. 左侧显示实时图像和目标叠加。
3. 右侧显示目标列表和任务按钮。
4. 目标可以通过点击画面或点击表格选中。
5. 选中目标高亮。
6. 无相机模式下也能显示模拟目标。

### Task 6：实现任务命令生成与发布

实现：

```text
TaskCommandBuilder
FileBridge
SocketBridge
MockControlServer
```

要求：

1. 用户选择目标和任务后生成 `TaskCommand`。
2. 文件模式下写入 `data/outbox/*.json`。
3. 提供模拟控制服务器，返回任务状态。
4. UI 能显示任务状态变化。

### Task 7：实现安全逻辑

要求：

1. 未选择目标时，禁止发布抓取/移动任务。
2. 目标不稳定时，禁止发布真实执行命令，但允许保存为测试命令。
3. 急停按钮始终可用。
4. 急停后禁止发布新任务。
5. 取消任务需要发送 `cancel_task`。

### Task 8：完善文档

生成：

```text
docs/interface_spec.md
docs/ui_design.md
docs/control_integration_guide.md
```

其中 `interface_spec.md` 必须包含 JSON schema 示例，方便机械控制同学直接使用。

---

## 14. 验收标准

### 14.1 无相机模式验收

运行：

```bash
python run_ui.py --camera mock --bridge file
```

应实现：

1. UI 正常打开。
2. 显示模拟相机画面。
3. 显示至少 3 个模拟目标。
4. 用户可以点击目标。
5. 用户可以选择“抓取并移动”。
6. 用户可以选择放置位置 `Assembly_Port_A`。
7. 点击“发布命令”后，`data/outbox/` 中生成 JSON 文件。
8. 日志显示命令已发布。

### 14.2 D405 模式验收

运行：

```bash
python run_ui.py --camera d405 --bridge file
```

应实现：

1. UI 正常显示 D405 实时画面。
2. 如果画面中有 ArUco 标记，能够识别并显示目标框。
3. 能显示目标三维坐标。
4. 能选中目标并发布命令。
5. D405 断开时 UI 不崩溃，显示相机离线。

### 14.3 与控制模块联调验收

运行模拟控制：

```bash
python -m src.bridge.mock_control_server --mode file
```

应实现：

1. UI 发布命令。
2. MockControlServer 接收到命令。
3. MockControlServer 写入任务状态。
4. UI 显示状态从 `RECEIVED` 到 `COMPLETED`。

---

## 15. 后续与机械控制同学对接说明

机械控制同学只需要先完成以下最低接口：

1. 读取或订阅 `TaskCommand`。
2. 解析：
   - `command_type`
   - `selected_target.pose_camera`
   - `selected_target.pose_base`
   - `destination.pose_base`
3. 如果 `pose_base == null`，可以先只做仿真或拒绝真实执行。
4. 返回 `TaskStatus`。
5. 真实控制接入后，控制模块负责：
   - 坐标系转换；
   - 逆运动学；
   - 轨迹规划；
   - 夹爪控制；
   - 安全停止。

视觉 UI 侧承诺：

1. 坐标单位统一为米。
2. 角度单位统一为弧度。
3. 所有命令都有唯一 `command_id`。
4. 所有命令都带 `timestamp`。
5. 所有命令都明确 `frame_id`。
6. 不直接发送裸坐标，而是发送完整任务包。

---

## 16. 给 Codex 的直接开发提示词

可以把下面这段直接发给 Codex：

```text
请根据当前仓库中的设计说明，生成一个 Python 项目 SpaceSnakeVisionUI。

项目目标：实现面向航天器在轨组装背景的蛇形机器人交互式视觉作业 UI。系统使用 PySide6 做深色太空任务控制台风格界面，使用 OpenCV 和 pyrealsense2 接入 Intel RealSense D405，识别 ArUco 目标并估计目标坐标/位姿。UI 中显示实时相机画面、目标框、目标列表、选中目标信息、任务指令面板、任务地图、机器人状态和日志。用户可以选择目标，选择任务类型，例如移动到目标附近、抓取目标、抓取并移动到指定位置、对接接口，然后生成标准 TaskCommand JSON。第一阶段通过文件接口 data/outbox/*.json 与控制模块联调，同时提供 MockControlServer 模拟控制状态返回。

请严格按照以下要求：
1. 使用 Python + PySide6 + OpenCV + pyrealsense2。
2. 没有 D405 时必须能用 --camera mock 启动。
3. UI 不能阻塞，摄像头采集和视觉处理放到 QThread 或后台线程。
4. 使用 Pydantic 或 dataclass 定义 Pose3D、DetectedObject、TaskCommand、TaskStatus、RobotState。
5. ArUco 位姿估计不要只依赖 estimatePoseSingleMarkers，要提供 solvePnP 备用方案。
6. 所有跨模块接口都使用 JSON 可序列化结构。
7. 输出目录包括 data/outbox、data/inbox、data/logs。
8. 提供 README.md、requirements.txt 和 docs/interface_spec.md。
9. 提供 run_ui.py，支持：
   python run_ui.py --camera mock --bridge file
   python run_ui.py --camera d405 --bridge file
10. UI 风格为太空任务控制台：深蓝黑背景、青蓝色边框、状态灯、目标锁定准星、任务日志。
11. 保留后续 ROS2 接口文件 ros2_bridge_optional.py，但第一版可以不真正依赖 ROS2。
12. 代码要模块化、可运行、带基本异常处理，D405 不存在时不要崩溃。
```

---

## 17. 最终展示建议

最终演示可以按照以下流程：

```text
1. 打开 ORBITAL SNAKE ROBOT MISSION CONTROL。
2. D405 相机识别桌面上的多个模拟载荷模块。
3. UI 自动标出 Target 0、Target 1、Target 2。
4. 用户选择 Target 1。
5. UI 显示 TARGET LOCKED。
6. 用户选择任务：抓取并移动到 Assembly Port A。
7. 点击预检查，通过后点击发布命令。
8. 系统生成 CMD-xxxx.json。
9. MockControlServer 返回 ACCEPTED、PLANNING、EXECUTING、COMPLETED。
10. UI 日志和任务进度条同步更新。
11. 后续接真实机械控制时，只需要替换 MockControlServer 为真实控制节点。
```

这个演示能体现完整链路：

```text
视觉感知 → 人机交互 → 任务封装 → 控制接口 → 状态反馈
```

也能体现项目背景：

```text
服务星视觉系统识别载荷模块，由人确认后发布在轨组装任务，蛇形机械臂执行抓取、移动和对接。
```
