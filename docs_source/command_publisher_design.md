# SpaceSnakeVisionUI 命令发布模块详细设计文档

版本：v1.0  
适用项目：面向航天器在轨组装应用的超冗余自由度蛇形机器人视觉 + UI 系统  
目标读者：后续负责编码的 Codex / 项目开发者 / 与规划控制模块联调的同学

---

## 0. 文档目的

当前项目已经完成了基础的视觉识别与 UI 交互雏形，目录中已经存在 `src/ui/command_panel.py`、`src/bridge/command_builder.py`、`src/bridge/file_bridge.py`、`src/bridge/mock_control_server.py`、`docs/interface_spec.md` 等文件。下一步要补充的是“命令发布功能”：

> 用户在 UI 中选择视觉识别到的目标后，系统将用户意图转换为标准化任务级指令 `TaskCommand`，经过安全校验后发布给规划/控制模块，并接收控制模块返回的 `TaskStatus`，在 UI 中显示任务状态和执行结果。

该模块不直接控制电机、不直接计算 IK、不直接发布底层关节角，而是承担“人机交互层 → 任务指令层 → 规划控制层”的桥接作用。

---

## 1. 业务定位

### 1.1 项目任务链路

项目演示中的完整链路应为：

```text
D405/Mock Camera
    ↓
视觉识别：YOLO / ArUco / Mock Detector
    ↓
目标列表与画面框选
    ↓
用户选择目标
    ↓
命令发布模块：生成、校验、发布 TaskCommand
    ↓
规划/控制模块：IK / 轨迹规划 / 抓手控制 / RViz 或真机执行
    ↓
状态反馈：TaskStatus
    ↓
UI 显示执行进度、失败原因和下一步操作
```

### 1.2 命令发布模块职责

命令发布模块负责：

1. 保存用户选中的目标快照，避免视觉流持续刷新导致目标丢失或 ID 变化。
2. 根据用户选择的任务类型、目标、放置区、速度模式、抓取模式生成任务级指令。
3. 在发布前进行安全校验，包括急停状态、目标有效性、置信度、稳定度、深度、目标时效、机器人忙闲状态等。
4. 支持文件桥接 `FileBridge`，第一阶段通过 `data/outbox/*.json` 与控制模块或 Mock 控制服务联调。
5. 预留 ROS2 桥接 `ROS2BridgeOptional`，后续可将同样的 JSON 字符串发布到 ROS2 topic。
6. 接收控制模块返回的 `TaskStatus`，维护机器人状态机，在 UI 中实时显示执行状态。
7. 支持 `emergency_stop`、`cancel_task`、`home` 等非目标类指令。

### 1.3 不属于本模块的职责

本模块不负责：

1. 视觉模型训练。
2. 相机标定和手眼标定的底层计算。
3. IK 求解、路径规划和关节角发布。
4. 底层电机控制。
5. 抓手闭环力控。

这些由视觉、规划、控制同学分别负责。本模块只把目标和任务参数用统一格式传出去。

---

## 2. 当前代码基础分析

当前项目中已有以下文件，可直接作为命令发布模块的基础：

```text
src/ui/command_panel.py
    UI 任务面板：任务类型、放置位置、接近距离、速度模式、抓取模式、生成任务、发布命令、取消任务、急停。

src/ui/main_window.py
    主窗口：接收视觉帧、目标选择、生成命令、发布命令、急停、轮询状态。

src/bridge/command_builder.py
    将 UI 参数和选中目标封装为 TaskCommand。

src/bridge/file_bridge.py
    将 TaskCommand 写到 data/outbox/*.json；从 data/inbox/*_status.json 读取 TaskStatus。

src/bridge/mock_control_server.py
    模拟控制模块：监听 outbox，依次写回 RECEIVED、ACCEPTED、PLANNING、EXECUTING、COMPLETED 状态。

src/bridge/ros2_bridge_optional.py
    ROS2 桥接占位文件，目前未真正实现。

src/models.py
    已定义 Vector3、Euler、Quaternion、Pose3D、DetectedObject、RobotState、TaskCommand、TaskStatus。

configs/bridge.yaml
    已预留 file、websocket、ros2 三种桥接方式。

configs/task_zones.yaml
    已定义 Assembly_Port_A、Assembly_Port_B、Holding_Zone、Safe_Zone。

README.md
    已写明第一阶段通过 data/outbox/*.json 与控制模块联调。
```

当前代码已经实现了最基础的流程：

```text
选择目标 → 生成任务 → 发布命令 → outbox 生成 JSON → mock server 写回 status → UI 打印日志
```

但还缺少工程化业务逻辑：

1. 缺少目标快照锁定。
2. 缺少完整发布前安全校验。
3. 缺少机器人忙闲状态管理。
4. 缺少发布后防重复发布机制。
5. 缺少状态反馈驱动 UI 状态变化。
6. 缺少 ROS2 发布实现。
7. 缺少系统化测试用例。

本设计文档主要围绕这些缺口展开。

---

## 3. 总体架构设计

### 3.1 逻辑架构

建议将命令发布功能拆成 5 个逻辑层：

```text
┌──────────────────────────────────────────┐
│                UI 交互层                  │
│  TargetTable / CameraView / CommandPanel │
└──────────────────────┬───────────────────┘
                       ↓
┌──────────────────────────────────────────┐
│             目标锁定与任务状态层           │
│  selected_target_snapshot / robot_busy   │
│  active_command_id / estop_active        │
└──────────────────────┬───────────────────┘
                       ↓
┌──────────────────────────────────────────┐
│              指令生成与安全校验层          │
│  validate_command / build_task_command   │
└──────────────────────┬───────────────────┘
                       ↓
┌──────────────────────────────────────────┐
│                桥接发布层                 │
│  FileBridge / ROS2BridgeOptional         │
└──────────────────────┬───────────────────┘
                       ↓
┌──────────────────────────────────────────┐
│              控制反馈与状态显示层          │
│  poll_status / update_robot_state / log  │
└──────────────────────────────────────────┘
```

### 3.2 文件级架构

建议保持现有目录结构，在现有文件上增量修改：

```text
src/
  models.py
  ui/
    main_window.py             # 主改：目标快照、安全校验、状态机、发布逻辑
    command_panel.py           # 小改：按钮状态、可选新增“解除急停/清空命令”
    status_bar.py              # 小改：状态显示更细
  bridge/
    bridge_base.py             # 保持抽象接口
    command_builder.py         # 主改：丰富 TaskCommand 字段，读取 zone 配置
    file_bridge.py             # 小改：原子写文件、防重复读取、错误日志
    mock_control_server.py     # 小改：模拟失败/拒绝/急停逻辑
    ros2_bridge_optional.py    # 主改：实现 std_msgs/String 发布与订阅
  utils/
    config.py                  # 可扩展读取 safety.yaml
configs/
  bridge.yaml
  task_zones.yaml
  safety.yaml                  # 新增：安全阈值配置
  command.yaml                 # 可选：命令类型与约束配置
```

---

## 4. 核心业务流程设计

### 4.1 正常任务流程：选择目标并发布任务

```text
1. 视觉线程持续输出 objects。
2. UI 更新相机画面、目标表、mission map。
3. 用户从目标表或画面中点击目标。
4. 系统执行 select_target(target_id)。
5. 系统从当前 objects 中找到该目标。
6. 系统保存 selected_target_snapshot。
7. UI 显示“目标已锁定”。
8. 用户选择任务类型，例如 pick_and_place。
9. 用户选择放置位置，例如 Assembly_Port_A。
10. 用户点击“生成任务”。
11. 系统执行 _validate_command()。
12. 校验通过后执行 build_task_command()。
13. 系统生成 pending_command。
14. UI 显示命令预览，并允许“发布命令”。
15. 用户点击“发布命令”。
16. 系统通过 bridge.publish_command() 发布。
17. 系统记录 active_command_id，robot_busy=True，清空 pending_command。
18. 控制模块返回 TaskStatus。
19. UI 轮询 status，显示 RECEIVED / ACCEPTED / PLANNING / EXECUTING / COMPLETED。
20. 若到达终态，robot_busy=False。
```

### 4.2 急停流程

急停不需要目标、不需要机器人空闲、不需要命令预生成。任何状态下都允许急停。

```text
用户点击“急停”
    ↓
estop_active = True
    ↓
立即生成 emergency_stop TaskCommand
    ↓
通过 bridge 发布
    ↓
UI 状态栏变红：E-STOP: TRIGGERED
    ↓
非 emergency_stop / cancel_task 类指令全部禁止发布
    ↓
等待人工解除或重新启动程序
```

第一版可以不做“解除急停”，更安全。如果要做演示，可增加 `reset_estop` 按钮，但必须要求二次确认，并且只恢复 UI 侧标志，不代表真实硬件急停已解除。

### 4.3 取消任务流程

取消任务不依赖目标，但最好依赖当前是否有任务正在执行：

```text
用户点击“取消任务”
    ↓
如果 active_command_id 存在或 robot_busy=True
    ↓
生成 cancel_task 命令
    ↓
发布给控制模块
    ↓
UI 等待 CANCELED / FAILED / ESTOP_TRIGGERED
```

如果没有任务正在执行，可以允许发布取消命令，但 UI 应提示：

```text
No active task. Cancel command is published for synchronization only.
```

### 4.4 Home 回零流程

`home` 不需要目标，但需要满足：

1. 急停未触发。
2. 机器人不忙，或控制模块允许打断当前任务回零。
3. 用户二次确认。

第一版建议：机器人 busy 时不允许 `home`，只能先 `cancel_task` 或 `emergency_stop`。

---

## 5. 状态机设计

### 5.1 UI 侧任务状态机

建议在 `MainWindow` 中维护以下状态变量：

```python
self.selected_id: str | None
self.selected_target_snapshot: DetectedObject | None
self.pending_command: TaskCommand | None
self.active_command_id: str | None
self.robot_busy: bool
self.estop_active: bool
self.last_robot_status: str
self.last_status_message: str
```

UI 侧状态可抽象为：

```text
NO_TARGET
    ↓ 选择目标
TARGET_LOCKED
    ↓ 生成命令
COMMAND_READY
    ↓ 发布命令
COMMAND_SENT
    ↓ 收到 ACCEPTED / PLANNING / EXECUTING
EXECUTING
    ↓ 收到 COMPLETED
COMPLETED

任意状态 --急停--> ESTOP
任意执行状态 --取消--> CANCELING → CANCELED
任意执行状态 --失败--> FAILED
```

### 5.2 控制反馈状态枚举

沿用 `docs/interface_spec.md` 中定义的状态，并建议解释如下：

| 状态 | 含义 | UI 行为 |
|---|---|---|
| RECEIVED | 控制端收到命令 | 显示“命令已接收” |
| ACCEPTED | 控制端通过安全检查 | robot_busy=True |
| REJECTED | 控制端拒绝命令 | robot_busy=False，显示原因 |
| PLANNING | 正在规划轨迹 | 禁止普通任务按钮 |
| EXECUTING | 正在执行 | 显示进度 |
| PAUSED | 暂停 | 允许 resume/cancel/estop |
| COMPLETED | 完成 | robot_busy=False |
| FAILED | 失败 | robot_busy=False，显示失败原因 |
| CANCELED | 已取消 | robot_busy=False |
| ESTOP_TRIGGERED | 急停触发 | estop_active=True，界面红色警告 |

### 5.3 状态转移规则

```text
COMMAND_SENT + RECEIVED     → robot_busy=True
RECEIVED + ACCEPTED         → robot_busy=True
ACCEPTED + PLANNING         → robot_busy=True
PLANNING + EXECUTING        → robot_busy=True
EXECUTING + COMPLETED       → robot_busy=False, active_command_id=None
EXECUTING + FAILED          → robot_busy=False, active_command_id=None
任意状态 + REJECTED         → robot_busy=False, active_command_id=None
任意状态 + CANCELED         → robot_busy=False, active_command_id=None
任意状态 + ESTOP_TRIGGERED  → estop_active=True, robot_busy=False 或保持未知
```

如果收到的 `status.command_id` 与 `active_command_id` 不一致：

1. 若是旧任务状态，记录日志但不改变当前任务状态。
2. 若当前没有 active command，则可以显示为历史状态。
3. 不要让旧状态把新任务的 busy 状态清掉。

---

## 6. 目标锁定设计

### 6.1 为什么要锁定目标快照

当前视觉线程每帧会更新 `self.objects`。如果用户选中目标后，该目标短暂被遮挡、检测 ID 变化或 YOLO 置信度波动，发布任务时可能出现：

```text
用户明明选了目标，但 generate_command 时 _selected_obj() 返回 None。
```

因此，用户点击目标时必须保存一份“目标快照”。

### 6.2 目标快照字段

快照直接使用 `DetectedObject` 即可，至少包含：

```text
target_id
class_name
display_name
detection_mode
marker_id
confidence
stability_score
bbox_xyxy
center_pixel
depth_m
pose_camera
pose_base
status
timestamp
locked_at
last_seen_at
```

现有 `DetectedObject` 没有 `locked_at` 和 `last_seen_at` 字段，可以不改 dataclass，而在 `MainWindow` 中额外维护：

```python
self.selected_target_snapshot = obj
self.selected_target_locked_at = time.time()
self.selected_target_last_seen_at = obj.timestamp
```

也可以新增一个 dataclass：

```python
@dataclass
class TargetSelection:
    target: DetectedObject
    locked_at: float
    last_seen_at: float
    lock_source: str  # table / camera_view
```

第一版建议不新增 dataclass，减少改动。

### 6.3 目标锁定逻辑

`select_target(target_id)` 中执行：

```python
self.selected_id = target_id
obj = self._selected_obj()
if obj:
    self.selected_target_snapshot = copy.deepcopy(obj)
    self.selected_target_locked_at = time.time()
    self.selected_target_last_seen_at = obj.timestamp
    self.log.log(f"Target locked: {obj.target_id}")
else:
    self.log.log(f"Target selected but not found in current frame: {target_id}")
```

必须用 `copy.deepcopy(obj)`，避免后续 objects 刷新时引用被间接改变。

### 6.4 目标刷新逻辑

在 `on_frame()` 中：

1. 正常更新 `self.objects`。
2. 如果当前 selected_id 仍出现在当前帧中，则更新 `selected_target_last_seen_at`。
3. 是否自动更新 snapshot 要谨慎。

建议策略：

```text
锁定后默认不自动替换 snapshot；
但如果当前帧检测到同 ID 目标，并且置信度更高、pose 更稳定，可以更新 last_seen_at；
真实执行仍以用户锁定时的 snapshot 为准，避免目标跳变。
```

后续可以支持两种模式：

| 模式 | 含义 |
|---|---|
| snapshot_mode | 任务使用点击瞬间的目标快照，适合静态目标抓取 |
| tracking_mode | 任务使用持续更新的目标位姿，适合目标跟踪 |

第一版使用 `snapshot_mode`。

---

## 7. 发布前安全校验设计

### 7.1 校验入口

在 `MainWindow` 中新增：

```python
def _validate_command(self, command_type: str, obj) -> tuple[bool, str, dict]:
    ...
```

返回：

```text
ok: 是否通过
reason: 失败或警告原因
check_report: 每条校验结果，用于写入 TaskCommand.safety
```

第一版也可以只返回 `(bool, str)`，但建议预留 `check_report`，方便后续写入 JSON。

### 7.2 安全校验规则总表

| 校验项 | 适用命令 | 规则 | 失败提示 |
|---|---|---|---|
| 急停状态 | 除 emergency_stop 外所有命令 | estop_active 必须为 False | E-STOP is active |
| 机器人忙闲 | 普通任务、home | robot_busy 必须为 False | robot is busy |
| 目标存在 | 需要目标的命令 | obj 不为 None | no target selected |
| 目标时效 | 需要目标的命令 | now - obj.timestamp <= 2.0s | target pose is stale |
| 目标置信度 | 需要目标的命令 | confidence >= 0.5 | target confidence too low |
| 目标稳定度 | 需要目标的命令 | stability_score >= 0.3 | target is unstable |
| 深度可用 | 真实空间运动 | depth_m 不为 None | target depth unavailable |
| pose_base 可用 | 真实机械臂执行 | pose_base 不为 None | target base pose unavailable |
| 工作空间 | pose_base 可用时 | 距基座距离不超过最大可达半径 | target unreachable |
| 目的地 | pick_and_place/dock | destination 不为空且在配置中 | invalid destination |
| 接近距离 | 运动命令 | 0.01 <= approach <= 0.5 | invalid approach distance |
| 任务类型 | 所有 | 在支持列表中 | unsupported command type |

### 7.3 命令类型分类

```python
TARGET_REQUIRED_COMMANDS = {
    "move_near_target",
    "pick_target",
    "pick_and_place",
    "dock_to_interface",
}

DESTINATION_REQUIRED_COMMANDS = {
    "pick_and_place",
    "dock_to_interface",
}

NO_TARGET_COMMANDS = {
    "home",
    "cancel_task",
    "emergency_stop",
}

ALWAYS_ALLOWED_COMMANDS = {
    "emergency_stop",
}
```

### 7.4 pose_base 的特殊处理

当前项目 README 中已经说明：`pose_base` 第一版可以为 `null`，等待手眼标定和机械结构确定。因此校验逻辑应该区分“演示/仿真”和“真实执行”：

```text
如果 execution_mode = simulation_only：
    pose_base 可以为 null，命令允许发布，但 safety.allow_real_execute=False。

如果 execution_mode = real_robot：
    pose_base 必须存在，否则拒绝发布。
```

第一版建议默认：

```python
execution_mode = "simulation_only" if obj.pose_base is None else "real_candidate"
```

写入命令：

```json
"safety": {
  "allow_execute": true,
  "allow_real_execute": false,
  "execution_mode": "simulation_only",
  "reason": "pose_base is null; command is for simulation/mock control only"
}
```

这样不会阻塞 UI 演示，同时也不会误导控制同学直接真机执行。

### 7.5 建议新增 safety 配置

新增 `configs/safety.yaml`：

```yaml
safety:
  target_max_age_s: 2.0
  min_confidence: 0.5
  min_stability: 0.3
  require_depth_for_motion: true
  require_pose_base_for_real_robot: true
  max_reach_m: 0.8
  min_approach_distance_m: 0.01
  max_approach_distance_m: 0.5
  block_when_robot_busy: true
  allow_simulation_without_pose_base: true
```

如果项目暂时不想新增配置文件，也可以先在 `main_window.py` 中写常量，后续再迁移。

---

## 8. TaskCommand 数据结构设计

### 8.1 当前结构

当前 `TaskCommand` 已有字段：

```python
schema_version
command_id
timestamp
source
command_type
selected_target
destination
motion_params
safety
reason
```

建议保持该 dataclass，不做破坏式修改，只在字典字段中增加内容。

### 8.2 建议使用 schema_version = 1.1

第一阶段可以仍然写 `1.0`，但建议升级为 `1.1`，因为要加入目标快照、安全校验报告、执行模式等字段。

### 8.3 TaskCommand v1.1 完整示例

```json
{
  "schema_version": "1.1",
  "command_id": "CMD-20260706-12345",
  "timestamp": 1783312800.123,
  "source": "SpaceSnakeVisionUI",
  "command_type": "pick_and_place",
  "execution_mode": "simulation_only",
  "selected_target": {
    "target_id": "TGT-001",
    "class_name": "payload_module",
    "display_name": "目标模块 1",
    "detection_mode": "yolo",
    "marker_id": null,
    "confidence": 0.91,
    "stability_score": 0.84,
    "timestamp": 1783312799.800,
    "locked_at": 1783312800.000,
    "snapshot_age_s": 0.323,
    "bbox_xyxy": [120, 80, 260, 220],
    "center_pixel": [190, 150],
    "depth_m": 0.526,
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
    "display_name": "装配接口 A",
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
    "stop_if_target_lost": true,
    "pregrasp_policy": "offset_along_camera_z",
    "tolerance_m": 0.01
  },
  "safety": {
    "require_user_confirm": true,
    "allow_execute": true,
    "allow_real_execute": false,
    "estop_active": false,
    "robot_busy": false,
    "validation_passed": true,
    "validation_message": "ok",
    "checks": [
      {"name": "estop", "passed": true, "message": "E-STOP safe"},
      {"name": "target_exists", "passed": true, "message": "target snapshot available"},
      {"name": "target_freshness", "passed": true, "message": "target age 0.32s"},
      {"name": "pose_base", "passed": false, "severity": "warning", "message": "pose_base is null; simulation only"}
    ]
  }
}
```

### 8.4 selected_target 字段说明

| 字段 | 含义 |
|---|---|
| target_id | 视觉模块分配的目标 ID |
| class_name | YOLO/ArUco/Mock 输出类别 |
| display_name | UI 显示名称 |
| detection_mode | yolo / aruco / mock |
| marker_id | ArUco ID，无则为 null |
| confidence | 检测置信度 |
| stability_score | 目标稳定度 |
| timestamp | 视觉检测时间 |
| locked_at | 用户锁定时间 |
| snapshot_age_s | 生成命令时快照年龄 |
| bbox_xyxy | 图像框 |
| center_pixel | 图像中心点 |
| depth_m | 深度 |
| pose_camera | 相机坐标系位姿 |
| pose_base | 基座坐标系位姿；未标定时为 null |

### 8.5 command_type 语义

| command_type | 含义 | 是否需要目标 | 是否需要目的地 | 控制侧建议动作 |
|---|---|---|---|---|
| move_near_target | 移动到目标附近预抓取点 | 是 | 否 | 规划到 pregrasp pose |
| pick_target | 抓取目标 | 是 | 否 | 靠近 + 夹取 |
| pick_and_place | 抓取并放置 | 是 | 是 | 抓取目标后移动到 destination |
| dock_to_interface | 对接口对接 | 是 | 是/可选 | 对齐目标接口并执行对接 |
| home | 回零/安全姿态 | 否 | 否 | 回到初始姿态 |
| cancel_task | 取消当前任务 | 否 | 否 | 停止当前任务，进入安全状态 |
| emergency_stop | 急停 | 否 | 否 | 立即停止 |

---

## 9. TaskStatus 数据结构设计

### 9.1 当前结构

当前 `TaskStatus` 已有字段：

```python
schema_version
command_id
timestamp
status
current_step
progress
message
robot_state
```

建议保持不变。

### 9.2 TaskStatus 示例

```json
{
  "schema_version": "1.1",
  "command_id": "CMD-20260706-12345",
  "timestamp": 1783312802.300,
  "status": "EXECUTING",
  "current_step": "MOVING_TO_PREGRASP",
  "progress": 0.42,
  "message": "Moving to pre-grasp pose",
  "robot_state": {
    "state": "EXECUTING",
    "end_effector_pose_base": null,
    "joint_positions": [0.1, -0.2, 0.05, 0.0, 0.0, 0.0],
    "message": "IK converged; trajectory executing"
  }
}
```

### 9.3 current_step 建议枚举

```text
COMMAND_RECEIVED
SAFETY_CHECKING
SAFETY_ACCEPTED
SAFETY_REJECTED
PLANNING_TRAJECTORY
IK_SOLVING
MOVING_TO_PREGRASP
APPROACHING_TARGET
GRIPPER_CLOSING
MOVING_TO_DESTINATION
RELEASING_TARGET
RETURNING_HOME
TASK_COMPLETED
TASK_FAILED
TASK_CANCELED
ESTOP_TRIGGERED
```

UI 不需要理解全部细节，只需原样显示。

---

## 10. UI 设计修改

### 10.1 目标选择区

当前右侧 `SELECTED TARGET` 区域已经显示目标 ID、类别、置信度、稳定度、相机系位姿。建议增加：

```text
Lock Status: LOCKED / LOST / STALE / LIVE
Snapshot Age: 0.8 s
Depth: 0.526 m / N/A
Base Pose: Available / Not Available
Execution Mode: Simulation Only / Real Candidate
```

目标锁定后显示：

```text
Selected Target
ID: TGT-001
Class: bottle
Mode: yolo
Confidence: 0.91
Stability: 0.84
Depth: 0.526 m
Lock Status: LOCKED
Snapshot Age: 0.3 s
Base Pose: Not Available / Simulation Only
```

### 10.2 命令面板

当前按钮：

```text
生成任务
发布命令
取消任务
急停
```

建议按钮状态规则：

| 状态 | 生成任务 | 发布命令 | 取消任务 | 急停 |
|---|---|---|---|---|
| 无目标且任务需要目标 | 禁用或点击后提示 | 禁用 | 可用 | 可用 |
| 目标已锁定 | 可用 | 生成后可用 | 可用 | 可用 |
| pending_command 存在 | 可用 | 可用 | 可用 | 可用 |
| robot_busy=True | 禁用普通生成 | 禁用普通发布 | 可用 | 可用 |
| estop_active=True | 禁用普通生成 | 禁用普通发布 | 可用 | 可用 |

第一版可以不做动态禁用，只要点击后给出日志提示即可。但更推荐动态更新按钮，视觉上更清楚。

### 10.3 命令预览区

建议在 `COMMAND PANEL` 下方增加一个小型只读文本框：

```text
Pending Command
ID: CMD-20260706-12345
Type: pick_and_place
Target: TGT-001 / bottle
Destination: Assembly_Port_A
Execution: simulation_only
Safety: PASSED with warning: pose_base is null
```

如果不想新建 widget，可以先写到 `MISSION LOG`。

### 10.4 状态栏

当前状态栏格式：

```text
Camera: ONLINE | Vision: RUNNING | Bridge: FILE MODE | Robot: IDLE | E-STOP: SAFE
```

建议扩展：

```text
Camera: ONLINE | Vision: RUNNING | Bridge: FILE MODE | Robot: EXECUTING | Task: CMD-xxxxx 42% | E-STOP: SAFE
```

急停时：

```text
Camera: ONLINE | Vision: RUNNING | Bridge: FILE MODE | Robot: ESTOP | Task: -- | E-STOP: TRIGGERED
```

---

## 11. 桥接层设计

### 11.1 BridgeBase 抽象接口

保持现有接口：

```python
class BridgeBase:
    def publish_command(self, command: TaskCommand):
        raise NotImplementedError

    def poll_status(self) -> list[TaskStatus]:
        raise NotImplementedError
```

所有 bridge 都必须实现这两个方法。

### 11.2 FileBridge 设计

FileBridge 是第一阶段主方案。

#### 发布规则

```text
data/outbox/{command_id}.json
```

建议改为原子写：

```python
path_tmp = outbox / f"{command.command_id}.json.tmp"
path_final = outbox / f"{command.command_id}.json"
path_tmp.write_text(command.to_json(), encoding="utf-8")
path_tmp.replace(path_final)
```

避免控制端读到半写入文件。

#### 状态读取规则

```text
data/inbox/{command_id}_status.json
```

当前实现每个命令只有一个 status 文件，会被后写状态覆盖。如果 Mock 控制服务快速写多个状态，UI 可能只读到最后一个状态。

更好的做法是每个状态一个文件：

```text
data/inbox/{command_id}_{timestamp_ms}_{status}.json
```

例如：

```text
CMD-20260706-12345_1783312800100_RECEIVED_status.json
CMD-20260706-12345_1783312800900_ACCEPTED_status.json
CMD-20260706-12345_1783312801700_EXECUTING_status.json
CMD-20260706-12345_1783312802500_COMPLETED_status.json
```

这样 UI 能看到完整状态序列。

如果不想改太多，也可以保留原文件名，但 Mock Server 每次写完后 sleep 长一点，UI 轮询间隔小一点。不过更推荐多文件状态。

### 11.3 MockControlServer 设计

Mock Server 应模拟以下逻辑：

1. 如果 `command_type == emergency_stop`：立即返回 `ESTOP_TRIGGERED`。
2. 如果 `safety.allow_execute == false`：返回 `REJECTED`。
3. 如果 `command_type` 是普通任务：返回完整序列。
4. 如果 `command_type == cancel_task`：返回 `RECEIVED → CANCELED`。
5. 如果 `command_type == home`：返回 `RECEIVED → PLANNING → EXECUTING → COMPLETED`。

建议状态序列：

```python
NORMAL_SEQUENCE = [
    ("RECEIVED", "COMMAND_RECEIVED", 0.05),
    ("ACCEPTED", "SAFETY_ACCEPTED", 0.20),
    ("PLANNING", "PLANNING_TRAJECTORY", 0.45),
    ("EXECUTING", "EXECUTING_TASK", 0.75),
    ("COMPLETED", "TASK_COMPLETED", 1.00),
]
```

### 11.4 ROS2BridgeOptional 设计

后续 ROS2 联调时，不建议一开始就写自定义 msg。第一版直接使用 `std_msgs/String` 传 JSON：

| 方向 | Topic | 消息类型 | 内容 |
|---|---|---|---|
| UI → 控制 | `/space_snake/task_command` | `std_msgs/String` | TaskCommand JSON |
| 控制 → UI | `/space_snake/task_status` | `std_msgs/String` | TaskStatus JSON |

实现逻辑：

```text
ROS2BridgeOptional 初始化 rclpy
    ↓
创建 node: space_snake_ui_bridge
    ↓
创建 publisher: /space_snake/task_command
    ↓
创建 subscriber: /space_snake/task_status
    ↓
后台线程 spin
    ↓
publish_command(command): 发布 command.to_json()
    ↓
poll_status(): 返回 subscriber 缓存的 TaskStatus 列表
```

注意：PySide6 UI 主线程不能被 ROS2 spin 阻塞，所以必须开后台线程。

---

## 12. command_builder.py 设计

### 12.1 当前问题

当前 `ZONE_POSES` 是写死在代码里的，虽然 `configs/task_zones.yaml` 已经存在。建议后续从配置读取，但第一版可以保留写死值。

当前 `_target_summary()` 字段太少，只保留：

```python
target_id
class_name
confidence
pose_camera
pose_base
```

建议扩展为完整目标快照。

### 12.2 build_task_command 建议签名

当前签名：

```python
def build_task_command(command_type, selected_target, destination_name, approach_distance_m, speed_mode, gripper_mode, estop_active=False)
```

建议扩展为：

```python
def build_task_command(
    command_type: str,
    selected_target,
    destination_name: Optional[str],
    approach_distance_m: float,
    speed_mode: str,
    gripper_mode: str,
    estop_active: bool = False,
    robot_busy: bool = False,
    validation_report: Optional[dict] = None,
    locked_at: Optional[float] = None,
    execution_mode: str = "simulation_only",
) -> TaskCommand:
```

如果想减少改动，也可以保持原签名，将新字段暂时不传。

### 12.3 _target_summary 建议内容

```python
def _target_summary(obj, locked_at=None) -> dict:
    now = time.time()
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
        "snapshot_age_s": now - obj.timestamp,
        "bbox_xyxy": obj.bbox_xyxy,
        "center_pixel": obj.center_pixel,
        "depth_m": obj.depth_m,
        "pose_camera": obj.pose_camera.to_dict(),
        "pose_base": obj.pose_base.to_dict() if obj.pose_base else None,
        "status": obj.status,
    }
```

### 12.4 safety 字段建议

```python
safety = {
    "require_user_confirm": True,
    "allow_execute": validation_report.get("allow_execute", not estop_active),
    "allow_real_execute": validation_report.get("allow_real_execute", False),
    "execution_mode": execution_mode,
    "estop_active": estop_active,
    "robot_busy": robot_busy,
    "validation_passed": validation_report.get("passed", True),
    "validation_message": validation_report.get("message", "ok"),
    "checks": validation_report.get("checks", []),
}
```

---

## 13. main_window.py 详细修改设计

### 13.1 新增成员变量

在 `__init__` 中新增：

```python
import time
import copy

self.selected_target_snapshot = None
self.selected_target_locked_at = None
self.selected_target_last_seen_at = None
self.active_command_id = None
self.robot_busy = False
self.last_robot_status = "IDLE"
self.last_status_message = ""
```

### 13.2 修改 select_target

```python
def select_target(self, target_id: str) -> None:
    self.selected_id = target_id
    obj = self._selected_obj()
    if obj:
        self.selected_target_snapshot = copy.deepcopy(obj)
        self.selected_target_locked_at = time.time()
        self.selected_target_last_seen_at = obj.timestamp
        self._update_selected_label(obj, lock_status="LOCKED")
        self.log.log(f"Target locked: {obj.target_id}")
    else:
        self.log.log(f"Target selected but not found in current frame: {target_id}")
    self.map.update_map(self.objects, self.selected_id)
```

可以把原来很长的 label 文本封装到 `_update_selected_label()`。

### 13.3 修改 on_frame

```python
def on_frame(self, image, objects) -> None:
    self.objects = list(objects)
    VisionPipeline.redraw_selection(image, self.objects, self.selected_id)
    self.camera_view.set_frame_size(image.shape[1], image.shape[0])
    self.camera_view.setPixmap(cv_bgr_to_qpixmap(image))
    self.table.update_targets(self.objects)
    self.map.update_map(self.objects, self.selected_id)

    obj = self._selected_obj()
    if self.selected_id:
        if obj:
            self.selected_target_last_seen_at = obj.timestamp
        else:
            self.log.log(f"Target lost: {self.selected_id}")
```

后续可以避免每帧重复打印 lost 日志，加入 `_target_lost_logged` 标志。

### 13.4 新增 _get_command_target

```python
def _get_command_target(self):
    return self._selected_obj() or self.selected_target_snapshot
```

说明：

1. 优先使用当前帧对象，保证数据新。
2. 如果当前帧丢失，则使用锁定快照，允许用户继续生成仿真命令。
3. 安全校验会根据 age 判断是否允许发布。

更保守的策略是只使用 snapshot，不使用当前帧。第一版建议优先当前对象。

### 13.5 新增 _validate_command

核心伪代码：

```python
def _validate_command(self, command_type: str, obj, destination=None, approach=0.05):
    checks = []

    def add(name, passed, message, severity="error"):
        checks.append({"name": name, "passed": passed, "message": message, "severity": severity})
        return passed

    if command_type != "emergency_stop" and self.estop_active:
        add("estop", False, "E-STOP is active")
        return False, "E-STOP is active", {"passed": False, "checks": checks}
    add("estop", True, "E-STOP safe")

    if self.robot_busy and command_type not in {"cancel_task", "emergency_stop"}:
        add("robot_busy", False, "robot is busy")
        return False, "robot is busy", {"passed": False, "checks": checks}
    add("robot_busy", True, "robot is idle or command can interrupt")

    target_required = command_type in {"move_near_target", "pick_target", "pick_and_place", "dock_to_interface"}
    if target_required and obj is None:
        add("target_exists", False, "no target selected")
        return False, "no target selected", {"passed": False, "checks": checks}

    if obj is not None:
        age = time.time() - obj.timestamp
        if age > 2.0:
            add("target_freshness", False, f"target pose is stale: {age:.2f}s old")
            return False, f"target pose is stale: {age:.2f}s old", {"passed": False, "checks": checks}
        add("target_freshness", True, f"target age {age:.2f}s")

        if obj.confidence < 0.5:
            add("target_confidence", False, f"target confidence too low: {obj.confidence:.2f}")
            return False, f"target confidence too low: {obj.confidence:.2f}", {"passed": False, "checks": checks}
        add("target_confidence", True, f"confidence {obj.confidence:.2f}")

        if obj.stability_score < 0.3:
            add("target_stability", False, f"target is unstable: {obj.stability_score:.2f}")
            return False, f"target is unstable: {obj.stability_score:.2f}", {"passed": False, "checks": checks}
        add("target_stability", True, f"stability {obj.stability_score:.2f}")

        if obj.depth_m is None and target_required:
            add("target_depth", False, "target depth is unavailable")
            return False, "target depth is unavailable", {"passed": False, "checks": checks}
        add("target_depth", True, "target depth available")

        if obj.pose_base is None:
            add("pose_base", False, "pose_base is null; command is simulation only", severity="warning")

    if command_type in {"pick_and_place", "dock_to_interface"} and not destination:
        add("destination", False, "destination is required")
        return False, "destination is required", {"passed": False, "checks": checks}
    add("destination", True, "destination ok")

    if approach < 0.01 or approach > 0.5:
        add("approach_distance", False, "invalid approach distance")
        return False, "invalid approach distance", {"passed": False, "checks": checks}
    add("approach_distance", True, f"approach {approach:.2f}m")

    allow_real_execute = bool(obj and obj.pose_base is not None)
    execution_mode = "real_candidate" if allow_real_execute else "simulation_only"

    return True, "ok", {
        "passed": True,
        "message": "ok",
        "allow_execute": True,
        "allow_real_execute": allow_real_execute,
        "execution_mode": execution_mode,
        "checks": checks,
    }
```

### 13.6 修改 generate_command

```python
def generate_command(self, command_type, destination, approach, speed, gripper) -> None:
    obj = self._get_command_target()

    ok, reason, report = self._validate_command(command_type, obj, destination, approach)
    if not ok:
        self.log.log(f"Pre-check failed: {reason}")
        return

    self.pending_command = build_task_command(
        command_type,
        obj,
        destination,
        approach,
        speed,
        gripper,
        self.estop_active,
        robot_busy=self.robot_busy,
        validation_report=report,
        locked_at=self.selected_target_locked_at,
        execution_mode=report.get("execution_mode", "simulation_only"),
    )
    self.log.log(f"Command generated: {self.pending_command.command_id} {command_type}")
    self.log.log(f"Execution mode: {report.get('execution_mode')}; real execute: {report.get('allow_real_execute')}")
```

如果暂时不改 `build_task_command` 签名，则先少传参数。

### 13.7 修改 publish_command

```python
def publish_command(self) -> None:
    if self.pending_command is None:
        self.log.log("No pending command. Generate a task first.")
        return

    path = self.bridge.publish_command(self.pending_command)
    self.active_command_id = self.pending_command.command_id
    self.robot_busy = True
    self.last_robot_status = "COMMAND_SENT"
    self.log.log(f"Command published to {path}")

    self.pending_command = None
    self._refresh_status_bar()
```

如果发布的是 `emergency_stop`，由 `emergency_stop()` 单独处理。

### 13.8 修改 emergency_stop

```python
def emergency_stop(self) -> None:
    self.estop_active = True
    cmd = build_estop_command()
    path = self.bridge.publish_command(cmd)
    self.active_command_id = cmd.command_id
    self.robot_busy = False
    self.last_robot_status = "ESTOP"
    self.status.set_state(
        f"Camera: ONLINE | Vision: RUNNING | Bridge: {self.bridge_status} | Robot: ESTOP | E-STOP: TRIGGERED",
        True,
    )
    self.log.log(f"E-STOP command published to {path}")
```

### 13.9 修改 cancel_task

```python
def cancel_task(self) -> None:
    cmd = build_task_command(
        "cancel_task",
        None,
        None,
        0.05,
        "demo_safe",
        "demo_grip",
        self.estop_active,
    )
    path = self.bridge.publish_command(cmd)
    self.active_command_id = cmd.command_id
    self.log.log(f"Cancel command published to {path}")
```

不建议通过 `self.pending_command = ...; self.publish_command()`，因为 `publish_command()` 会把 `robot_busy=True`，而 cancel 本身应该是打断命令。

### 13.10 修改 poll_status

```python
def poll_status(self) -> None:
    for status in self.bridge.poll_status():
        self.log.log(
            f"Task {status.command_id}: {status.status} "
            f"{status.progress:.0%} - {status.message}"
        )
        self._apply_task_status(status)
```

新增：

```python
def _apply_task_status(self, status):
    if status.status in {"RECEIVED", "ACCEPTED", "PLANNING", "EXECUTING", "PAUSED"}:
        self.robot_busy = True
        self.last_robot_status = status.status
    elif status.status in {"COMPLETED", "FAILED", "CANCELED", "REJECTED"}:
        if status.command_id == self.active_command_id:
            self.robot_busy = False
            self.active_command_id = None
        self.last_robot_status = status.status
    elif status.status == "ESTOP_TRIGGERED":
        self.estop_active = True
        self.robot_busy = False
        self.last_robot_status = "ESTOP"

    self.last_status_message = status.message
    self._refresh_status_bar(status)
```

新增：

```python
def _refresh_status_bar(self, status=None):
    task_part = f"Task: {self.active_command_id}" if self.active_command_id else "Task: --"
    progress_part = f" {status.progress:.0%}" if status else ""
    self.status.set_state(
        f"Camera: ONLINE | Vision: RUNNING | Bridge: {self.bridge_status} | "
        f"Robot: {self.last_robot_status}{progress_part} | {task_part} | "
        f"E-STOP: {'TRIGGERED' if self.estop_active else 'SAFE'}",
        self.estop_active,
    )
```

---

## 14. 配置文件设计

### 14.1 configs/bridge.yaml

保留现有内容，建议增加：

```yaml
bridge:
  mode: "file"
  file:
    outbox_dir: "data/outbox"
    inbox_dir: "data/inbox"
    atomic_write: true
    status_file_mode: "multi_file"
  ros2:
    enabled: false
    task_command_topic: "/space_snake/task_command"
    task_status_topic: "/space_snake/task_status"
    message_type: "std_msgs/String"
```

### 14.2 configs/safety.yaml

新增：

```yaml
safety:
  target_max_age_s: 2.0
  min_confidence: 0.5
  min_stability: 0.3
  require_depth_for_motion: true
  allow_simulation_without_pose_base: true
  require_pose_base_for_real_robot: true
  block_when_robot_busy: true
  min_approach_distance_m: 0.01
  max_approach_distance_m: 0.5
  max_reach_m: 0.8
```

### 14.3 configs/task_zones.yaml

现有内容可继续使用。建议 `command_builder.py` 从该配置读取目的地，而不是硬编码 `ZONE_POSES`。

---

## 15. 与控制/规划同学的接口约定

### 15.1 第一阶段：文件接口

UI 写：

```text
data/outbox/CMD-*.json
```

控制读：

```text
data/outbox/CMD-*.json
```

控制写：

```text
data/inbox/*_status.json
```

UI 读：

```text
data/inbox/*_status.json
```

### 15.2 控制侧处理规则

控制模块收到 `TaskCommand` 后应做：

```text
1. 解析 command_type。
2. 检查 safety.allow_execute。
3. 如果是真实机械臂执行，必须检查 selected_target.pose_base 是否存在。
4. 如果 pose_base 为 null，只允许仿真或拒绝真实执行。
5. 根据 command_type 调用不同规划/控制逻辑。
6. 过程状态持续写回 TaskStatus。
7. 失败时在 message 中写清楚原因，例如 IK failed / target unreachable / pose_base missing。
```

### 15.3 控制侧伪代码

```python
for command_file in outbox:
    cmd = TaskCommand.from_json(command_file.read_text())

    write_status(cmd.command_id, "RECEIVED", "COMMAND_RECEIVED", 0.05)

    if not cmd.safety.get("allow_execute", False):
        write_status(cmd.command_id, "REJECTED", "SAFETY_REJECTED", 0.0, "UI safety check failed")
        continue

    if cmd.command_type == "emergency_stop":
        stop_all_motion()
        write_status(cmd.command_id, "ESTOP_TRIGGERED", "ESTOP_TRIGGERED", 1.0)
        continue

    if real_robot_mode and cmd.selected_target and cmd.selected_target.get("pose_base") is None:
        write_status(cmd.command_id, "REJECTED", "SAFETY_REJECTED", 0.0, "pose_base missing")
        continue

    write_status(cmd.command_id, "ACCEPTED", "SAFETY_ACCEPTED", 0.2)
    write_status(cmd.command_id, "PLANNING", "PLANNING_TRAJECTORY", 0.4)
    plan = planner.plan(cmd)
    if not plan.ok:
        write_status(cmd.command_id, "FAILED", "TASK_FAILED", 0.4, plan.reason)
        continue

    write_status(cmd.command_id, "EXECUTING", "EXECUTING_TASK", 0.7)
    result = controller.execute(plan)
    if result.ok:
        write_status(cmd.command_id, "COMPLETED", "TASK_COMPLETED", 1.0)
    else:
        write_status(cmd.command_id, "FAILED", "TASK_FAILED", result.progress, result.reason)
```

---

## 16. 测试设计

### 16.1 单元测试

新增或扩展：

```text
tests/test_command_builder.py
tests/test_file_bridge.py
tests/test_command_validation.py
tests/test_task_status_flow.py
```

#### test_command_builder.py

测试：

1. `build_task_command("home", None, ...)` 可以生成无目标命令。
2. `build_task_command("pick_and_place", obj, "Assembly_Port_A", ...)` 包含目标和目的地。
3. `selected_target` 包含 confidence、stability_score、depth_m、pose_camera、pose_base。
4. `safety.execution_mode` 正确写入。

#### test_command_validation.py

测试：

1. 急停状态下普通命令被拒绝。
2. 无目标时 `pick_and_place` 被拒绝。
3. 无目标时 `home` 通过。
4. 置信度低被拒绝。
5. 稳定度低被拒绝。
6. 目标过期被拒绝。
7. pose_base 为 null 时仿真命令允许，但 `allow_real_execute=False`。
8. robot_busy 时普通任务被拒绝，cancel/estop 允许。

#### test_file_bridge.py

测试：

1. publish_command 后 outbox 中存在 JSON。
2. poll_status 可以读到 inbox 中状态。
3. 已读状态不会重复返回。
4. 损坏 JSON 不导致程序崩溃。

### 16.2 手工测试流程

#### 流程 A：Mock 相机 + FileBridge + MockControlServer

终端 1：

```bash
python run_ui.py --camera mock --bridge file --detector mock
```

终端 2：

```bash
python -m src.bridge.mock_control_server --mode file
```

操作：

```text
1. 选择 TGT-001。
2. 任务类型选 pick_and_place。
3. 目的地选 Assembly_Port_A。
4. 点击生成任务。
5. 检查日志：Command generated。
6. 点击发布命令。
7. 检查 data/outbox 出现 CMD-*.json。
8. 检查 UI 日志出现 RECEIVED、ACCEPTED、PLANNING、EXECUTING、COMPLETED。
9. 检查状态栏从 Robot: IDLE → EXECUTING → COMPLETED。
```

#### 流程 B：未选择目标直接生成任务

```text
1. 不选目标。
2. 任务类型选 pick_and_place。
3. 点击生成任务。
4. 期望日志：Pre-check failed: no target selected。
5. 不生成 pending_command。
```

#### 流程 C：急停

```text
1. 点击急停。
2. 期望 outbox 出现 CMD-ESTOP-*.json。
3. 状态栏变为 E-STOP: TRIGGERED。
4. 再尝试生成普通任务，期望失败：E-STOP is active。
```

#### 流程 D：机器人忙时重复发布

```text
1. 发布一个 pick_and_place。
2. 在 EXECUTING 状态时再尝试生成普通任务。
3. 期望失败：robot is busy。
4. 点击取消任务，允许发布 cancel_task。
```

#### 流程 E：D405 + YOLO

```bash
python run_ui.py --camera d405 --bridge file --detector yolo --yolo-model yolo11n.pt --yolo-conf 0.35
```

验证：

```text
1. 画面中出现识别框。
2. 点击目标框锁定目标。
3. 若 depth_m 有值，允许生成 move_near_target。
4. 若 pose_base 为 null，命令 execution_mode 为 simulation_only。
```

---

## 17. Codex 开发任务书

下面这部分可以直接作为给 Codex 的开发提示。

### 17.1 总任务

请在现有 `SpaceSnakeVisionUI` 项目中完善“命令发布功能”。当前项目已有 PySide6 UI、视觉目标检测、`TaskCommand`/`TaskStatus` 数据模型、`FileBridge`、`MockControlServer`。请在不破坏现有运行方式的前提下，增加目标快照锁定、发布前安全校验、机器人忙闲状态管理、发布后防重复发布、状态反馈驱动 UI 更新，并实现可选 ROS2 JSON 字符串桥接。

### 17.2 必须保持兼容的运行命令

```bash
python run_ui.py --camera mock --bridge file --detector mock
python run_ui.py --camera d405 --bridge file --detector yolo --yolo-model yolo11n.pt --yolo-conf 0.35
python -m src.bridge.mock_control_server --mode file
```

这些命令必须继续可运行。

### 17.3 具体修改任务

#### 任务 1：修改 `src/ui/main_window.py`

新增成员变量：

```python
self.selected_target_snapshot
self.selected_target_locked_at
self.selected_target_last_seen_at
self.active_command_id
self.robot_busy
self.last_robot_status
self.last_status_message
```

修改 `select_target()`：

1. 用户选择目标时保存 `copy.deepcopy(obj)` 到 `selected_target_snapshot`。
2. 记录 `selected_target_locked_at = time.time()`。
3. 更新 selected label，显示 locked 状态、snapshot age、depth、pose_base 是否可用。

新增 `_get_command_target()`：

```python
return self._selected_obj() or self.selected_target_snapshot
```

新增 `_validate_command(command_type, obj, destination, approach)`：

1. 急停状态下阻止非 emergency_stop 命令。
2. robot_busy 时阻止普通任务。
3. 需要目标的命令必须有目标。
4. 检查目标 age、confidence、stability_score、depth_m。
5. pose_base 为 null 时不拒绝仿真命令，但写 warning，`allow_real_execute=False`。
6. 检查 destination 和 approach distance。
7. 返回 `(ok, reason, report)`。

修改 `generate_command()`：

1. 使用 `_get_command_target()` 获取目标。
2. 调用 `_validate_command()`。
3. 校验失败只写 log，不生成 pending_command。
4. 校验成功后调用 `build_task_command()`。
5. 日志显示 command_id、command_type、execution_mode。

修改 `publish_command()`：

1. 如果没有 pending command，提示。
2. 发布后设置 `active_command_id`。
3. 发布后设置 `robot_busy=True`。
4. 发布后清空 `pending_command`，避免重复发布。
5. 刷新状态栏。

修改 `emergency_stop()`：

1. 任何时候都能发布。
2. 设置 `estop_active=True`。
3. 发布 `build_estop_command()`。
4. 状态栏变红。

修改 `cancel_task()`：

1. 直接生成并发布 cancel_task。
2. 不依赖 selected target。
3. 不通过普通 `pending_command` 流程。

修改 `poll_status()`：

1. 读取 status 后调用 `_apply_task_status(status)`。
2. 根据 status 更新 robot_busy、active_command_id、last_robot_status、estop_active。
3. 刷新状态栏。

#### 任务 2：修改 `src/bridge/command_builder.py`

1. 将 schema_version 升级到 `1.1`，或保持 `1.0` 但增加字段。
2. 扩展 `_target_summary()`，加入：
   - display_name
   - detection_mode
   - marker_id
   - stability_score
   - timestamp
   - locked_at
   - snapshot_age_s
   - bbox_xyxy
   - center_pixel
   - depth_m
   - status
3. 扩展 `build_task_command()` 参数，支持：
   - robot_busy
   - validation_report
   - locked_at
   - execution_mode
4. 在 `safety` 中写入：
   - allow_execute
   - allow_real_execute
   - execution_mode
   - validation_passed
   - validation_message
   - checks
5. 保持原有 tests 尽量不失效；必要时同步更新 tests。

#### 任务 3：修改 `src/bridge/file_bridge.py`

1. 发布命令时采用临时文件 + rename 的原子写入。
2. `poll_status()` 忽略损坏 JSON，但不要静默吞掉，建议返回前至少 print 或可选记录。
3. 支持多状态文件名，如果 Mock Server 改成多文件 status，确保能读取。

#### 任务 4：修改 `src/bridge/mock_control_server.py`

1. 如果收到 `emergency_stop`，返回 `ESTOP_TRIGGERED`。
2. 如果 `safety.allow_execute` 为 false，返回 `REJECTED`。
3. 如果收到 `cancel_task`，返回 `RECEIVED → CANCELED`。
4. 普通命令返回 `RECEIVED → ACCEPTED → PLANNING → EXECUTING → COMPLETED`。
5. 每个状态写成独立文件，避免覆盖：

```text
data/inbox/{command_id}_{timestamp_ms}_{status}_status.json
```

#### 任务 5：实现 `src/bridge/ros2_bridge_optional.py`

1. 使用 `std_msgs.msg.String` 发布 JSON。
2. 发布 topic 默认 `/space_snake/task_command`。
3. 订阅 topic 默认 `/space_snake/task_status`。
4. 后台线程 spin，不阻塞 PySide6 主线程。
5. `publish_command(command)` 返回类似 `ros2:/space_snake/task_command`。
6. `poll_status()` 返回缓存的 `TaskStatus` 列表，并清空缓存。
7. 如果未安装 ROS2/rclpy，不影响 file mode。

#### 任务 6：修改 `src/app.py`

1. 当 `bridge_mode == "ros2"` 时尝试加载 `ROS2BridgeOptional`。
2. 如果加载失败，回退到 `FileBridge`，并在 bridge_status 中写明失败原因。
3. `file` 模式必须保持不变。

#### 任务 7：新增或更新 tests

至少增加以下测试：

```text
tests/test_command_validation.py
tests/test_file_bridge.py
```

如果 `_validate_command` 在 `MainWindow` 中不方便单测，可以把校验逻辑拆到 `src/bridge/command_validator.py` 或 `src/utils/command_validation.py` 中，方便无 UI 测试。

---

## 18. 推荐实现顺序

建议 Codex 按以下顺序实现，避免一次性改太多导致项目跑不起来：

```text
Step 1：先改 main_window.py，加入 selected_target_snapshot、robot_busy、active_command_id。
Step 2：加入 _validate_command，只做日志提示，不改 command_builder。
Step 3：修改 publish_command，发布后清空 pending_command，并根据 status 更新 robot_busy。
Step 4：扩展 command_builder 的 JSON 字段。
Step 5：改 mock_control_server，让状态反馈更完整。
Step 6：改 file_bridge 原子写文件。
Step 7：加 tests。
Step 8：实现 ROS2BridgeOptional。
Step 9：更新 docs/interface_spec.md 和 README.md。
```

每一步完成后都运行：

```bash
python run_ui.py --camera mock --bridge file --detector mock
python -m src.bridge.mock_control_server --mode file
pytest
```

---

## 19. 验收标准

### 19.1 基础验收

1. 程序能正常启动。
2. Mock 模式下能显示目标。
3. 点击目标后 selected target 区域显示目标信息。
4. 点击生成任务后能生成 pending command。
5. 点击发布命令后 outbox 出现 JSON。
6. Mock server 能读取命令并写回状态。
7. UI 能显示状态序列。
8. 发布后不能重复发布同一个 pending command。

### 19.2 安全验收

1. 未选择目标时，`pick_and_place` 不能生成。
2. `home` 可以无目标生成。
3. 急停后普通任务不能生成。
4. 机器人 busy 时普通任务不能生成。
5. `cancel_task` 和 `emergency_stop` 在 busy 时仍可发布。
6. 目标置信度过低、稳定度过低、深度缺失、目标过期时能提示明确原因。
7. pose_base 为 null 时允许仿真命令，但 JSON 中 `allow_real_execute=false`。

### 19.3 联调验收

1. 控制同学可以只读取 `data/outbox/*.json` 就知道任务类型、目标位姿、目的地和安全状态。
2. 控制同学只要写回 `TaskStatus` JSON，UI 就能显示进度。
3. 同一套 `TaskCommand` JSON 后续可以无缝转到 ROS2 topic 发布。

---

## 20. 汇报表达建议

你在汇报中可以这样描述：

> 在现有视觉识别和 UI 目标选择的基础上，我增加了任务级命令发布模块。该模块将用户选中的目标保存为目标快照，结合任务类型、目的地、接近距离、速度模式和抓取模式生成标准化 TaskCommand。在发布前，系统会检查急停状态、机器人忙闲状态、目标置信度、稳定性、深度有效性和目标位姿时效；通过后再通过文件桥接或 ROS2 桥接发布给规划控制模块。控制模块返回 TaskStatus 后，UI 实时更新任务进度和执行结果，从而形成“视觉感知—人机选择—任务发布—控制反馈”的闭环。

---

## 21. 最小可交付版本 MVP

如果时间很紧，只需要实现以下 6 点：

1. `selected_target_snapshot`：选中目标后锁定快照。
2. `_validate_command()`：校验急停、目标存在、目标新鲜度、confidence、stability、depth、robot_busy。
3. `publish_command()`：发布后清空 pending command，设置 robot_busy。
4. `poll_status()`：根据 TaskStatus 更新 robot_busy 和状态栏。
5. `mock_control_server.py`：支持多状态反馈。
6. `docs/interface_spec.md`：更新 TaskCommand 示例。

这 6 点完成后，你的“命令发布功能”就可以作为一个完整模块展示。

---

## 22. 未来扩展方向

后续可以继续扩展：

1. `reset_estop`：增加解除 UI 急停按钮，但必须二次确认。
2. `pause_task` / `resume_task`：暂停与继续。
3. `tracking_mode`：目标移动时持续更新位姿。
4. `task_queue`：多目标任务队列，模拟 4 个载荷星逐一对接。
5. `custom ROS2 msg`：将 JSON 字符串升级为自定义 ROS2 消息。
6. `control acknowledgement timeout`：命令发布后 N 秒未收到 RECEIVED，提示控制端无响应。
7. `record/replay`：记录每次命令和状态，便于报告和答辩展示。
8. `workspace visualization`：在 UI 中显示目标是否超出可达区域。

