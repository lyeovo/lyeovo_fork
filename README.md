# 空间蛇形机械臂任务总控台 (Mission Control HMI) 与 D405 靶标视觉系统

本仓库面向在轨空间装配与超冗余蛇形机械臂作业场景，打造了一套**航天任务控制中心风格（Mission Control Style）的机器人任务总控人机交互系统（HMI）**，深度融合 Intel RealSense D405 编码靶标视觉测量流水线，形成“**感知—决策—规划—执行—反馈**”全链路闭环控制平台。

---

## 📑 快速导航：您应该看哪个文档？

为了避免文档混乱，整个仓库已将所有陈旧/冗余草稿彻底清理，规范整理为以下 **3 份核心权威文档**，请根据您的角色对号入座：

| 您的角色 / 当前任务 | 对应必看文档 | 文档路径 | 核心解决的问题 |
| :--- | :--- | :--- | :--- |
| 🧑‍💻 **项目主开发者 / 汇报演示人员** | **项目总控台使用与架构总览** | 📌 [README.md](./README.md)（即本文件） | 系统全景、5 大分页功能、SVG 流程图状态机、两级视觉原理、环境运行命令 |
| 🤖 **运动控制端 / MATLAB 联调同学** | **全任务控制接口技术规范 (v2.0)** | 📘 [TASK_COMMAND_INTERFACE.md](./SpaceSnakeVisionUI/docs/TASK_COMMAND_INTERFACE.md) | 10 类指令 JSON 格式、控制端状态回传格式、SHA1去重覆盖机制、TCP 实时流预留 |
| 🤝 **跨团队交接人员 / 外部运行测试** | **独立交付版本开箱指南** | 📦 [D405_MarkerVision/README.md](./D405_MarkerVision/README.md) | 独立交接包目录结构、开箱启动命令、3类靶标最新权重与离线算法说明 |

> 💡 **补充参考**：底层算法库详情见 [`snake_vision_d405_target/README.md`](./snake_vision_d405_target/README.md)；UI 模块代码结构见 [`SpaceSnakeVisionUI/README.md`](./SpaceSnakeVisionUI/README.md)。

---

## 一、系统架构与设计理念

```text
                      ┌──────────────────────────────────────────────┐
                      │     ORBITAL SNAKE ROBOT MISSION CONTROL      │
                      │             (PySide6 总控 HMI)               │
                      └──────────────────────┬───────────────────────┘
                                             │
                                     SystemStateStore
                                             │
              ┌──────────────────────────────┼──────────────────────────────┐
              ▼                              ▼                              ▼
   ┌─────────────────────┐        ┌─────────────────────┐        ┌─────────────────────┐
   │    VisionManager    │        │   MissionManager    │        │   ControlManager    │
   │                     │        │                     │        │                     │
   │ • D405 双目/深度采集 │        │ • 流程图状态机调度   │        │ • Outbox 命令发布   │
   │ • YOLO 靶标粗识别   │        │ • 步骤决策与分支仲裁 │        │ • Inbox 状态轮询    │
   │ • 白点 6DoF 模板匹配│        │ • 任务安全边界自检   │        │ • MATLAB/dSPACE 桥接│
   └──────────┬──────────┘        └──────────┬──────────┘        └──────────┬──────────┘
              │                              │                              │
              ▼                              ▼                              ▼
     latest_targets.json              TaskCommand JSON               TaskStatus JSON
     (data/vision/)                   (data/outbox/)                 (data/inbox/)
              │                              │                              │
              └──────────────────────────────┼──────────────────────────────┘
                                             ▼
                                 ┌───────────────────────┐
                                 │ MATLAB / dSPACE 运动端 │
                                 │ (ArmSimApp / Planner) │
                                 └───────────────────────┘
```

### 1. 唯一交互总控台 (Single Source of HMI)
- **前端 (PySide6)**：作为唯一的人机交互与任务控制入口，统领视觉感知、工作流调度、俯视地图操纵、关节遥测与系统监控。
- **后台 (MATLAB / ArmSimApp)**：作为后端的运动学逆解求解器、动力学规划器与底层驱动引擎，通过标准 JSON 协议与总控通信，无需并列双开操作界面。

### 2. 航天总控 5 大功能分页
为解决电脑屏幕有限但信息高度集成的矛盾，采用“**顶部常驻状态 Header + 左侧紧凑导航栏 + 5 大独立功能页面**”：
- **① 🚀 MISSION (任务总览 - 核心首屏)**：
  - 基于《机械臂抓取操作系统流程图》的自绘程序化动态流程图（`WorkflowWidget`），当前执行节点具有电光青蓝发光边框与缓动呼吸动效；
  - 实时相机导引画面与目标准星；
  - 目标 6DoF 遥测卡片与机械臂末端状态卡片；
  - 底部阶段操作条，提供“执行推进下一步”与分支条件（“是/否”）快速仲裁。
- **② 👁 VISION (视觉感知专页)**：
  - 大视野高帧率 D405 相机流；
  - 视野多目标选择表格与状态机阶段指示；
  - 目标 6DoF 详细位姿矩阵（X, Y, Z, R, P, Y）、红外白点质量指标（有效点数、重投影误差）。
- **③ 🎯 TASK (任务作业专页)**：
  - 俯视地图（`MissionMapWidget`）：支持直接在地图上单击任意位置快速拾取物理坐标，并高亮航点；
  - 10 类任务指令表单（`move_to`, `move_along`, `move_for_pick`, `move_for_place`, `rotate`, `rotate_arm`, `facing_arm`, `pick`, `place`, `withdraw`, `reset`）；
  - 可折叠历史任务清单抽屉。
- **④ 🦾 CONTROL (运动控制专页)**：
  - 吸收 `ArmSimApp.m` 精髓，自绘蛇形机械臂 2D 骨骼拓扑姿态；
  - 6 关节角度实时监测矩阵与角位移柱状条；
  - 规划器运行指标（求解耗时、末端跟踪误差、dSPACE 链路频率）。
- **⑤ 🖥 SYSTEM (系统诊断专页)**：
  - 全系统 9 大子模块（相机、YOLO、白点匹配、状态机、命令桥、规划器、dSPACE、关节执行器、夹爪）在线健康状态指示灯；
  - 视觉帧率 (FPS) 与命令通信往返延时 (RTT)；
  - 全流程统一时间戳审计控制台日志。

---

## 二、流程图状态机驱动 (MissionStateMachine)

系统核心由任务级状态机驱动，严格对照 [`机械臂抓取操作系统流程图.svg`](file:///f:/Grade3/study/D405+UI/%E6%9C%BA%E6%A2%B0%E8%87%82%E6%8A%93%E5%8F%96%E6%93%8D%E4%BD%9C%E7%B3%BB%E7%BB%9F%E6%B5%81%E7%A8%8B%E5%9B%BE.svg) 的完整业务闭环：

```text
流程开始
   ↓
启动机械臂 (发布 reset)
   ↓
相机视野中是否有目标物体？ (判断分支 1)
   ├─ [否] → 俯视 Map 点选大致位置 → 发布 move_to (x, y) → 机械臂移到大致位置 → 二次检测视野
   └─ [是]
      ↓
相机画面中点选目标物体 → 发布 move_for_pick (视觉伺服靠近)
      ↓
到达目标位置 (6DoF 对齐预备姿态)
      ↓
下达抓取命令 (发布 pick 动作链)
      ↓
机械臂抓取物体
      ↓
是否抓取成功？ (力控与接触传感器判断分支 2)
   ├─ [否] → 返回重新下达抓取 (重试)
   └─ [是]
      ↓
发布放置到终点任务命令 → 发布 move_for_place (装配工位寻位)
      ↓
机械臂携物体到达终点工位
      ↓
下达放置命令 (发布 place 释放脱钩)
      ↓
机械臂放置物体
      ↓
任务完成，进入下一个工件循环 (循环复位)
```

---

## 三、视觉靶标检测与两级识别

针对空间对接靶标，系统支持 `201`、`222`、`207` 三类编码靶标（YOLOv11 模型已完成全类别训练，mAP50 达到 97.5%）：

```text
SEARCH        : 视野内未检测到目标靶标
BEARING_ONLY  : 远距离，YOLO 检测到靶标外形，输出方位射线 (bearing ray)
PARTIAL_DEPTH : 中近距离，检测到部分红外圆点，深度逐步恢复
POSE_6DOF     : 近距离，有效白点 >= 6，结合模板匹配算法输出稳定 6 自由度位姿
LOST          : 瞬时遮挡或视野丢失，保留短时记忆
```

---

## 四、接口规范与数据通信协议

UI 与控制端（MATLAB/dSPACE）采用标准分层文件桥通信：

- **任务指令下发**：`data/outbox/CMD-YYYYMMDD-NNNNN.json`
- **控制状态反馈**：`data/inbox/{command_id}_status.json`
- **实时视觉闭环流**：`data/vision/latest_targets.json`

> 详细字段定义、物理单位与参数范围请查阅：  
> 📄 [TASK_COMMAND_INTERFACE.md](file:///f:/Grade3/study/D405+UI/SpaceSnakeVisionUI/docs/TASK_COMMAND_INTERFACE.md)

---

## 五、快速启动与操作指南

推荐在 Windows PowerShell 中运行：

```powershell
cd SpaceSnakeVisionUI

# 1. 使用 Mock 模拟环境启动总控（无需连接相机硬件，便于演示测试）
.\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock

# 2. 连接 RealSense D405 相机真机启动
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file

# 3. 运行 Mock 控制模块（模拟控制端接收命令与汇报状态）
.\.venv\Scripts\python.exe -m src.bridge.mock_control_server --mode file

# 4. 执行全套自动化单元与集成测试（21 项全通过）
.\.venv\Scripts\python.exe -m pytest tests/ --basetemp=./data/test_tmp
```
