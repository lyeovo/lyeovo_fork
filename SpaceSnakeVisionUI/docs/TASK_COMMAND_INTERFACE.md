# 空间蛇形机械臂任务指令控制接口规范 (Task Command Interface Specification)

> **版本**：v2.0  
> **适用模块**：UI 任务调度端 (`SpaceSnakeVisionUI`) $\longleftrightarrow$ 机械臂运动控制端 (`Motion Control / MockControlServer`)  
> **文件通信协议**：  
> - **命令下发路径**：`data/outbox/CMD-YYYYMMDD-NNNNN.json`  
> - **状态反馈路径**：`data/inbox/{command_id}_status.json`  
> - **实时视觉流路径**：`data/vision/latest_targets.json`

---

## 一、通用协议与外层数据结构

每次操作员在 UI 点击“生成任务”并“发布命令”后，UI 会在 `data/outbox/` 生成一个统一的 JSON 任务文件。其顶层公共字段结构如下：

```json
{
  "schema_version": "2.0",
  "command_id": "CMD-20260903-00001",
  "timestamp": 1788410000.123,
  "source": "SpaceSnakeVisionUI",
  "command_type": "<指令类型字符串>",
  "params": {
    /* 针对该指令的具体控制参数字典 */
  },
  "selected_target": {
    /* 当前锁定的视觉目标快照，若无则为 null */
  },
  "destination": {
    /* 目标工位信息，若无则为 null */
  },
  "motion_params": {
    /* 向后兼容字典，内容与 params 相同 */
  },
  "safety": {
    "require_user_confirm": true,
    "allow_execute": true,
    "allow_real_execute": true,
    "execution_mode": "real_robot",
    "validation_passed": true,
    "validation_message": "validation passed",
    "checks": {},
    "estop_active": false,
    "robot_busy": false
  }
}
```

### 公共字段说明：
1. **`schema_version`** (`string`)：固定为 `"2.0"`。
2. **`command_id`** (`string`)：唯一任务编号，如 `"CMD-20260903-00001"`。控制模块反馈执行状态时，**必须以该 ID 命名状态文件**（`data/inbox/{command_id}_status.json`）。
3. **`timestamp`** (`float`)：命令生成的时间戳（Unix 时间戳，单位：秒）。
4. **`source`** (`string`)：发布源，固定为 `"SpaceSnakeVisionUI"`。
5. **`command_type`** (`string`)：任务类型名称（详见下文 12 种指令）。
6. **`params`** (`object`)：核心参数字典，存放该指令的具体数值。
7. **`safety`** (`object`)：安全校验结论：
   - `allow_execute` (`bool`): 是否允许控制端执行。
   - `allow_real_execute` (`bool`): 是否允许真实物理机执行（若未标定或缺乏 6DoF，通常为 `false`）。
   - `execution_mode` (`string`): `"real_robot"`（真机）或 `"simulation_only"`（仅仿真/空跑）。
   - `estop_active` (`bool`): 当前 UI 是否处于急停锁定态。

---

## 二、每种任务指令具体信息与参数规范

### 1. `move_to`：末端移动到指定坐标 (x, y)

- **指令功能**：驱动机械臂末端执行器平移移动到基座坐标系或俯视工作平面的目标坐标 $(x, y)$。
- **输入交互**：可在 UI 界面微调框输入，或**在下方 MISSION MAP 俯视地图上单击任意位置快速拾取坐标**。
- **`params` 结构**：
  ```json
  "params": {
    "x": 0.350,
    "y": -0.120
  }
  ```
- **字段规范与物理量**：
  - `x` (`float`)：目标横向位置，单位：**米 (m)**，范围 $[-6, +6]$。基座坐标系中指向机器人右侧为正。
  - `y` (`float`)：目标纵向（前进）位置，单位：**米 (m)**，范围 $[-6, +6]$。基座坐标系中向前为正。
- **`selected_target`**：通常为 `null`（若当前界面锁定了目标，会同时附带该目标快照作为参考）。
- **`destination`**：`null`。

---

### 2. `move_along`：末端向 $\theta$ 方向移动 $d$ 米

- **指令功能**：从当前末端位置出发，在水平面内沿方位角 $\theta$ 方向直线延伸/位移 $d$ 米。
- **`params` 结构**：
  ```json
  "params": {
    "theta_deg": 45.0,
    "distance_m": 0.20
  }
  ```
- **字段规范与物理量**：
  - `theta_deg` (`float`)：移动方向方位角，单位：**度 (°)**，范围 $[-180.0, +180.0]$。$0^\circ$ 表示正前方，$+90^\circ$ 表示右侧，$-90^\circ$ 表示左侧。
  - `distance_m` (`float`)：单次位移距离，单位：**米 (m)**，范围 $(0, 6]$。
- **`selected_target`**：`null`。
- **`destination`**：`null`。

---

### 3. `move_for_pick`：根据实时相对位置向物体移动

- **指令功能**：视觉伺服（Visual Servoing）靠近动作。驱动末端从当前姿态向视觉锁定的靶标物体自主靠近，直至到达抓取预备姿态（Pre-grasp Pose）。
- **前置依赖**：必须在 UI 画面或目标列表中成功锁定一个目标（`selected_id` 不为空）。
- **`params` 结构**：
  ```json
  "params": {}
  ```
- **`selected_target`（携带目标完整位姿与质量快照）**：
  ```json
  "selected_target": {
    "target_id": "target_1",
    "class_name": "201",
    "display_name": "Marker 201",
    "detection_mode": "yolo_marker",
    "confidence": 0.95,
    "status": "POSE_6DOF",
    "depth_m": 0.285,
    "bbox_xyxy": [120, 80, 260, 220],
    "center_pixel": [190, 150],
    "bearing": {
      "pixel_center": [190, 150],
      "pixel_error": [20, -10],
      "ray_camera": [0.08, -0.04, 0.99]
    },
    "pose_camera": {
      "frame_id": "camera_left",
      "position": {"x": 0.025, "y": -0.012, "z": 0.285},
      "orientation": {"qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
      "orientation_euler": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
    },
    "pose_base": null,
    "quality": {
      "num_dots": 8,
      "valid_depth_points": 8,
      "match_error_m": 0.0012
    }
  }
  ```
- **控制端执行规范**：
  1. 读取本指令获取初始锁定目标 ID (`target_id`)；
  2. 在移动过程中，控制模块需持续以高频（如 30Hz）读取 `data/vision/latest_targets.json` 获得实时闭环位姿；
  3. 当 `status == "BEARING_ONLY"` 时沿视线向量 `bearing.ray_camera` 靠近；
  4. 当 `status == "POSE_6DOF"` 时，利用 6 自由度位姿精确调整末端法向对齐。

---

### 4. `move_for_place`：根据硬编码向放置位置移动

- **指令功能**：装配放置寻位。驱动机械臂从当前抓持状态移动到预设的硬编码终点放置区（`Goal_Zone`，位于基座右前方）。
- **`params` 结构**：
  ```json
  "params": {
    "destination": "Goal_Zone"
  }
  ```
- **`destination` 字段结构**：
  ```json
  "destination": {
    "name": "Goal_Zone",
    "pose_base": {
      "frame_id": "robot_base",
      "position": {"x": 4.0, "y": 0.10, "z": 2.0},
      "orientation": {"qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0}
    }
  }
  ```
- **字段规范与物理量**：
  - `destination.name` (`string`)：工位标识，当前仅 `"Goal_Zone"`（单一终点区域，位于基座右前方）。
  - `destination.pose_base` (`object`)：预置的基座坐标系空间位姿（米与四元数）。

---

### 5. `rotate`：末端固定位置旋转 $\alpha$ 角

- **指令功能**：末端执行器固定当前三维位置不动，仅绕工具末端中心轴（Tool Roll 轴）自转 $\alpha$ 角度。
- **`params` 结构**：
  ```json
  "params": {
    "alpha_deg": 90.0
  }
  ```
- **字段规范与物理量**：
  - `alpha_deg` (`float`)：相对旋转角度，单位：**度 (°)**，范围 $[-180.0, +180.0]$。正值为顺时针，负值为逆时针。

---

### 6. `rotate_arm`：第 $n$ 关节旋转 $\alpha$ 度

- **指令功能**：单关节独立控制。针对蛇形臂的第 $n$ 级旋转关节，使其在当前关节角基础上增量旋转 $\alpha$ 度。
- **`params` 结构**：
  ```json
  "params": {
    "joint_index": 3,
    "alpha_deg": -30.0
  }
  ```
- **字段规范与物理量**：
  - `joint_index` (`int`)：目标关节序号（1 索引），范围 $[1, 6]$。1 表示最靠近底座的第 1 关节。
  - `alpha_deg` (`float`)：增量旋转角度，单位：**度 (°)**，范围 $[-180.0, +180.0]$。

---

### 7. `facing_arm`：第 $n$ 关节面向 $\theta$ 方向

- **指令功能**：关节绝对朝向控制。调整从底座至第 $n$ 关节的子运动链，使第 $n$ 关节法线或弯曲平面直接指向物理空间的绝对方位角 $\theta$。
- **`params` 结构**：
  ```json
  "params": {
    "joint_index": 2,
    "theta_deg": 60.0
  }
  ```
- **字段规范与物理量**：
  - `joint_index` (`int`)：目标关节序号，范围 $[1, 6]$。
  - `theta_deg` (`float`)：绝对朝向角，单位：**度 (°)**，基座坐标系下范围 $[-180.0, +180.0]$。

---

### 8. `pick`：夹爪抓取动作链

- **指令功能**：触发末端夹爪的标准闭合抓取与装配卡扣锁紧流程（动作链包括：使能预紧力矩 $\to$ 夹爪闭合 $\to$ 接触传感器力控反馈确认 $\to$ 锁定确认）。
- **`params` 结构**：
  ```json
  "params": {}
  ```
- **字段规范**：无额外参数，控制端执行内置的标准化 Gripper Grasp 动作链。

---

### 9. `place`：夹爪放置动作链

- **指令功能**：触发末端夹爪的标准释放与装配到位脱钩流程（动作链包括：解锁卡扣 $\to$ 夹爪张开至全开位置 $\to$ 传感器确认脱离）。
- **`params` 结构**：
  ```json
  "params": {}
  ```
- **字段规范**：无额外参数，控制端执行内置的标准化 Gripper Release 动作链。

---

### 10. `withdraw`：退回上一状态

- **指令功能**：轨迹回退/回撤。沿着此前执行轨迹反向回退设定距离（如反向倒退 10cm）或恢复到上一个稳态断点，通常用于插入/对接失败后的安全退出。
- **`params` 结构**：
  ```json
  "params": {}
  ```

---

### 11. `reset`：恢复初始位置

- **指令功能**：系统零位复位。驱动蛇形臂所有关节（1~6 关节）依次回归机械零点（Home Position / 收拢姿态），夹爪复位，清除内部临时误差。
- **`params` 结构**：
  ```json
  "params": {}
  ```

---

### 12. `emergency_stop`：最高优先级急停

- **指令功能**：安全急停。立即切断伺服力矩或进入强力抱闸停机状态，中断所有正在执行的规划任务。
- **`params` 结构**：
  ```json
  "params": {}
  ```
- **`safety` 特殊标识**：
  ```json
  "safety": {
    "require_user_confirm": false,
    "allow_execute": true,
    "allow_real_execute": true,
    "execution_mode": "real_robot",
    "estop_active": true
  }
  ```

---

### 13. `cancel_task`：取消当前任务

- **指令功能**：非紧急性任务终止。机械臂以平滑减速度在当前轨迹上刹车停止，保持就地等待姿态，不清除关节使能。
- **`params` 结构**：
  ```json
  "params": {}
  ```

---

## 三、控制模块状态反馈规范 (TaskStatus)

当控制模块在 `data/outbox/` 读取到任一任务文件后，**必须在 `data/inbox/{command_id}_status.json` 中写回状态信息**，UI 界面将每 600ms 轮询一次并更新界面任务列表、监控页健康灯与状态机联动。

> **写回约定（与控制端 `taskWriteStatus.m` 一致）**：状态文件采用**固定文件名 `{command_id}_status.json` 原地覆盖**（建议先写 `tmp` 再原子 `movefile/replace`），每次状态跃迁覆盖同一文件。UI 侧 `FileBridge` 以**内容哈希（sha1）指纹**去重——只要文件内容变化即重新解析，因此**同一命令的 RECEIVED→ACCEPTED→PLANNING→EXECUTING→COMPLETED 全过程都会被逐帧捕获**，无需为每个状态生成不同文件名。

### 反馈 JSON 格式（v1.0，含扩展遥测）：
```json
{
  "schema_version": "1.0",
  "command_id": "CMD-20260903-00001",
  "timestamp": 1788410002.500,
  "status": "EXECUTING",
  "current_step": "EXECUTING_MOVE_TO",
  "progress": 0.65,
  "message": "Moving end-effector to (0.35, -0.12)",
  "robot_state": {
    "state": "EXECUTING",
    "end_effector_pose_base": {
      "frame_id": "robot_base",
      "position": {"x": 0.3375, "y": -0.0775, "z": 0.0},
      "orientation_euler": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
      "orientation_quat": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    },
    "joint_positions": [9.0, -14.25, 20.5, -4.5, 14.0, -6.25],
    "joint_positions_unit": "deg",
    "gripper": 0,
    "message": "normal"
  },
  "planner": {
    "method_used": "rrtstar",
    "solve_time_ms": 21.0,
    "tracking_error_mm": 4.1,
    "angle_error_deg": 1.7
  }
}
```

### `robot_state` 字段规范（控制端按能力选填，UI 缺失即显示 “—”）：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `state` | `string` | 机器人状态串（可复用 `status`，如 `EXECUTING`/`COMPLETED`/`ESTOP_TRIGGERED`），UI Header 直接显示。 |
| `end_effector_pose_base` | `object` \| `[]` | 末端在**基座坐标系**的位姿，形状对齐 `models.Pose3D`。平面蛇形臂 `z=0`、`roll=pitch=0`、`yaw=θ`。**无数据时 MATLAB `jsonencode` 会写成 `[]`，UI 已容忍并归一化为空。** |
| `joint_positions` | `float[6]` | 6 关节角。 |
| `joint_positions_unit` | `string` | **新增**：`"deg"`（缺省）或 `"rad"`。标注 `"rad"` 时 UI 自动换算为度显示，消除单位歧义。 |
| `gripper` | `int` | **新增**：`0`=HOLD（保持）、`1`=OPEN（张开）、`2`=CLOSE（闭合），对齐控制端 `gripper_seq`。UI 映射为 HOLDING/OPEN/CLOSED。 |
| `message` | `string` | 附加信息。 |

### `planner` 字段规范（顶层可选块，控制端有则填）：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `method_used` | `string` | 实际规划/求解算法（如 `auto`/`rrtstar`/`cvae`/`momentum`）。 |
| `solve_time_ms` | `float` | IK/轨迹求解耗时（毫秒）。 |
| `tracking_error_mm` | `float` | 末端跟踪误差（对应控制端 `si.dist_end`，毫米）。 |
| `angle_error_deg` | `float` | 末端角度误差（对应 `si.err_ang`，度）。 |

> **向后兼容**：`robot_state` 与 `planner` 的所有扩展字段均为可选；控制端未提供时，UI 对应监控项显示占位符（“—” / “STANDBY”），不影响既有 `state`/`joint_positions`/`message` 最小回传。UI 解析器会**忽略未知键**，控制端可安全追加自定义字段。

### 状态枚举值（`status`）：
- **`RECEIVED`**：控制模块已成功读取文件。
- **`ACCEPTED`**：指令参数及碰撞自检通过，已加入执行队列。
- **`PLANNING`**：正在进行运动学逆解（IK）与避障轨迹规划。
- **`EXECUTING`**：控制器正在驱动关节电机运动，`progress` 字段需从 `0.0` 递增至 `1.0`。
- **`COMPLETED`**：任务圆满完成，末端到达预定容差范围内。
- **`REJECTED`**：安全校验未通过或逆解无解，任务拒绝。
- **`CANCELED`**：收到 `cancel_task` 后已平稳刹车停机。
- **`ESTOP_TRIGGERED`**：进入急停停机状态。
- **`FAILED`**：执行过程中遇到异常（如关节超温、力矩超限或视觉目标丢失超时）。

---

## 四、实时遥测 TCP 状态流（预留 · 契约已冻结）

> **状态**：契约已冻结，**UI 侧接收端待实现**。现役遥测通道为第三节文件桥 TaskStatus（事件级低频）；TCP 流面向未来 20–50Hz 高频实时遥测（关节/夹爪/目标），对齐控制端 `tcpStateStreamServer.m` + `tcpEncodeFrame.m`。UI 已在 `src/bridge/telemetry_stream_client.py` 提供**解帧纯函数与接收端骨架**：`decode_state_frame` / `encode_frame` / `TelemetryStreamClient.feed` 已实现并被单测覆盖，`start()` 的 socket 连接与接收循环待接线（当前抛 `NotImplementedError`，未连入主窗口）。

### 4.1 帧格式（Framing）
每帧 = **4 字节大端无符号长度前缀 `N`** + **`N` 字节 UTF-8 JSON 体**：

```
[ 00 00 00 N ][ {JSON body ...} ]
```

- 长度前缀 `N` 仅计 JSON 体字节数，不含前缀自身。
- 接收方按前缀切分，天然支持**粘包/半包**：字节不足则缓存等待，一次可读多帧。
- UI 侧单帧上限 `MAX_FRAME_BYTES = 1 MiB`；超限视为链路损坏，应重置缓冲并重连。

### 4.2 消息体通用结构
```json
{
  "v": 1,
  "type": "STATE",
  "seq": 12345,
  "command_id": "CMD-20260903-00001",
  "data": { }
}
```
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `v` | `int` | 协议版本，固定 `1`。 |
| `type` | `string` | 消息类型（见 4.3）。 |
| `seq` | `int` | 单调递增序号，用于丢帧检测。 |
| `command_id` | `string` | 关联命令 ID；无关联时为空串 `""`。 |
| `data` | `object` | 类型相关负载。 |

### 4.3 消息类型（`type`）
| type | 方向 | 说明 |
| --- | --- | --- |
| `HELLO` | 控制端 → UI | 连接握手，携带能力/版本信息。 |
| `HELLO_ACK` | UI → 控制端 | 握手确认。 |
| `CMD` | UI → 控制端 | 下发任务指令（等价文件桥 outbox 命令）。 |
| `CMD_ACK` | 控制端 → UI | 指令接收确认。 |
| `STATE` | 控制端 → UI | **高频实时遥测**（见 4.4）。 |
| `DONE` | 控制端 → UI | 当前命令执行结束。 |
| `PING` / `PONG` | 双向 | 心跳保活。 |
| `ERROR` | 双向 | 错误上报。 |

### 4.4 `STATE.data` 字段表
```json
{
  "t": 1788410002.500,
  "joints": [0.0, 0.218, -0.091, 0.524, -0.175, 0.087],
  "gripper": 1,
  "obj": [0.35, -0.12],
  "obj_frame": "base",
  "obj_absent": false
}
```
| 字段 | 类型 | 单位/取值 | 说明 |
| --- | --- | --- | --- |
| `t` | `float` | 秒 | 采样时间戳。 |
| `joints` | `float[6]` | **弧度 rad（绝对角）** | 6 关节绝对角。⚠️ 与文件桥 `joint_positions` 缺省的**度**不同，TCP 流固定为 **rad**，UI 接收端需换算为度。 |
| `gripper` | `int` | `0`/`1`/`2` | 0=HOLD、1=OPEN、2=CLOSE（同文件桥约定）。 |
| `obj` | `[x, y]` | 米 m | 目标平面坐标。 |
| `obj_frame` | `string` | `'base'` \| `'cam'` | `obj` 所在坐标系。 |
| `obj_absent` | `bool` | — | 目标是否丢失。 |

> **接线约定（待实现）**：UI 接收端解出 `STATE` 帧后，应把 `joints`（rad→deg）写入 `SystemStateStore.update_robot(joint_angles_deg=..., telemetry_source="tcp")`，`gripper`→`gripper_state`，`obj`/`obj_absent`→视觉目标叠加。`telemetry_source` 字段用于在监控页标注当前遥测来自 `file` 还是 `tcp`。
