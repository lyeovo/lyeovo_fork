# 空间蛇形机械臂任务总控台 (Mission Control HMI) 与 D405 靶标视觉系统

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![PySide6 / Qt6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-green.svg)](https://doc.qt.io/qtforpython/)
[![RealSense D405](https://img.shields.io/badge/Camera-Intel%20RealSense%20D405-orange.svg)](https://www.intelrealsense.com/depth-camera-d405/)
[![YOLOv11](https://img.shields.io/badge/AI-YOLOv11%20mAP50%2097.5%25-brightgreen.svg)](https://github.com/ultralytics/ultralytics)
[![MATLAB Control](https://img.shields.io/badge/Backend-MATLAB%20%2F%20dSPACE-red.svg)](https://www.mathworks.com/)
[![Tests Passing](https://img.shields.io/badge/tests-44%20passed-success.svg)](./SpaceSnakeVisionUI/tests/)

面向在轨空间装配与超冗余蛇形机械臂作业场景，本系统打造了一套**航天任务控制中心风格（Mission Control Style）的机器人人机交互总控系统（HMI）**，深度融合 **Intel RealSense D405 毫米级高精度立体视觉测量**，打通“**高精度感知 $\to$ 工作流状态机决策 $\to$ 任务指令总线 $\to$ 逆解规划与动力学执行 $\to$ 30FPS 逐帧慢放与遥测闭环**”的全链路控制平台。

---

## 📑 核心文档导航

| 角色 / 场景 | 推荐文档 | 路径 | 主要内容 |
| :--- | :--- | :--- | :--- |
| 🧑‍🚀 **总控操作 / 汇报演示** | **系统综合技术手册 (本文件)** | 📌 [README.md](./README.md) | 系统架构、5大分页、坐标系规范、逐帧慢放、开箱运行指南 |
| 🤖 **算法联调 / MATLAB 同学** | **任务指令接口技术规范 (v2.0)** | 📘 [TASK_COMMAND_INTERFACE.md](./SpaceSnakeVisionUI/docs/TASK_COMMAND_INTERFACE.md) | 10类指令 JSON 协议、状态回传机制、SHA1去重、慢放参数 |
| 📦 **视觉交接 / 独立测试** | **视觉算法与独立包指南** | 📦 [D405_MarkerVision/README.md](./D405_MarkerVision/README.md) | 靶标检测权重、离线测试工具、白点 6DoF 位姿解算流水线 |

---

## 一、系统全景架构与数据拓扑

系统采用**唯一交互总控台（Single Source of HMI）**设计理念：由 Python 客户端统一负责视觉引导、任务规划、俯视雷达操控与状态审计；MATLAB/dSPACE 算法端作为无头算力后台，专注逆运动学求解与动力学执行，双方通过标准文件桥/网络桥解耦互通。

```text
                      ┌─────────────────────────────────────────────────────────────┐
                      │             ORBITAL SNAKE ROBOT MISSION CONTROL             │
                      │                    (PySide6 总控 HMI)                       │
                      └──────────────────────────────┬──────────────────────────────┘
                                                     │
                                             SystemStateStore
                                                     │
                     ┌───────────────────────────────┼───────────────────────────────┐
                     ▼                               ▼                               ▼
          ┌─────────────────────┐         ┌─────────────────────┐         ┌─────────────────────┐
          │    VisionManager    │         │   MissionManager    │         │   ControlManager    │
          │                     │         │                     │         │                     │
          │ • D405 双目/深度流   │         │ • 流程图状态机调度   │         │ • 10类指令打包下发  │
          │ • YOLOv11 靶标识别  │         │ • 自动推进与分支仲裁 │         │ • 启动自动清理垃圾  │
          │ • 白点 6DoF 位姿解算 │         │ • 任务安全边界自检   │         │ • 状态与遥测轮询监听│
          └──────────┬──────────┘         └──────────┬──────────┘         └──────────┬──────────┘
                     │                               │                               │
                     ▼                               ▼                               ▼
            latest_targets.json               TaskCommand JSON                TaskStatus JSON
             (data/vision/)                    (data/outbox/)                  (data/inbox/)
                     │                               │                               │
                     └───────────────────────────────┼───────────────────────────────┘
                                                     ▼
                                        ┌─────────────────────────┐
                                        │  MATLAB / dSPACE 运动端  │
                                        │   (runTaskLoop.m / IK)  │
                                        └─────────────────────────┘
```

### 三大通信通道
1. **任务下发队列 (`data/outbox/CMD-YYYYMMDD-NNNNN.json`)**：UI 向控制端发布的结构化作业指令；
2. **状态与遥测回传 (`data/inbox/{command_id}_status.json`)**：控制端向 UI 汇报执行状态（`RUNNING`、`COMPLETED` 等）及 6 关节实时角度；
3. **视觉闭环感知流 (`data/vision/latest_targets.json`)**：视觉模块以 30FPS 实时广播的靶标三维位姿与置信度。

---

## 二、航天总控五大功能分页

UI 采用深空控制台配色体系（太空深蓝 `#050814`、电光青蓝 `#00E5FF`、琥珀金 `#FFC857`、警示品红 `#FF0055`），提供 60FPS 极佳流畅体验：

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [● OPERATIONAL] ORBITAL SNAKE ROBOT MISSION CONTROL HMI                2026-09-04 16:00:00 UTC   │
├──────────┬───────────────────────────────────────────────────────────────────────────────────────┤
│ 🚀 MISSION│ • 核心首屏：自绘《机械臂抓取操作系统流程图》动态状态机（呼吸动效指示当前阶段）       │
│          │ • 相机视觉引导十字线准星、靶标 6DoF 姿态卡片、夹爪开合状态指示                        │
│          │ • 底部快速操作条：单步推进、分支仲裁（“是/否”）、紧急中止                             │
├──────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ 👁 VISION │ • D405 实时高分辨率彩色/深度视频流展示                                                │
│          │ • 靶标实时识别矩阵（201, 222, 207 靶标），6DoF 位姿 (X, Y, Z, R, P, Y) 实时显示       │
│          │ • 两级识别质量指示：有效白点数量、重投影误差、跟踪置信度状态机                        │
├──────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ 🎯 TASK   │ • 俯视雷达作业地图（MissionMapWidget）：支持直接点击任意物理坐标生成航点 (Waypoint)  │
│          │ • 坐标系雷达方位角系统：0° 正前、±30°、±45°、±60°、±90° 辐射射线与外环度数刻度盘     │
│          │ • 机械臂 6 节连杆骨骼与 J1-J5 关节实时显示、末端执行器夹爪动效                        │
│          │ • 目标点击自动触发末端手眼变换（FK + Extrinsics），物理位置不缩在原点                 │
│          │ • 光标悬停物理遥测（X, Y, 方位角 AZ, 极距 R）                                         │
│          │ • 10 类标准指令参数配置面板与折叠式任务历史抽屉                                       │
├──────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ 🦾 CONTROL│ • 蛇形机械臂 2D 骨骼拓扑结构全览                                                     │
│          │ • 6 关节角位移实时指示柱与动态数据卡片                                                │
│          │ • 逆运动学求解耗时、末端跟踪误差、dSPACE 总线通信质量监控                             │
├──────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ 🖥 SYSTEM │ • 9 大子模块（相机、YOLO、白点、状态机、命令桥、规划器、dSPACE、关节、夹爪）健康矩阵  │
│          │ • 系统级性能监控：视觉帧率 (FPS)、通信往返时延 (RTT)                                  │
│          │ • 统一纳秒级时间戳审计控制台日志                                                      │
└──────────┴───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、三维空间与平面坐标系统一规范（核心）

为了保证地面站操作员、D405 光学镜头与 MATLAB 机械臂逆解算法之间的空间语义完全一致，系统建立了严格的坐标系映射矩阵：

```text
     【地面站 UI 俯视雷达坐标系】                     【MATLAB 机械臂平面坐标系】
                +Y (FWD, 0°)                                +Y_matlab (LEFT)
                     ▲                                             ▲
                     │                                             │
      -X (LEFT) ─────┼─────► +X (RIGHT)                            │
        (-90°)       │         (+90°)                              │
                  Base(0,0)                        -X_matlab ──────┼──────► +X_matlab (FWD)
                                                                   │           (初始伸展方向)
                                                                Base(0,0)
```

### 1. 坐标轴定义
| 坐标系 | 原点 | 主轴 / 正方向定义 | 方位角 (Azimuth) 定义 |
| :--- | :--- | :--- | :--- |
| **UI 俯视雷达系** | 机械臂底座 $(0,0)$ | $+Y$：正前方 (0°)<br>$+X$：正右方 (+90°)<br>$-X$：正左方 (-90°) | 相对正前方的顺时针夹角：<br>$\text{AZ} = \operatorname{atan2}(X, Y)$，极距 $R=\sqrt{X^2+Y^2}$ |
| **MATLAB 机械臂系** | 机械臂底座 $(0,0)$ | $+X_{\text{matlab}}$：机械臂前向基准伸展线<br>$+Y_{\text{matlab}}$：机械臂向左侧弯曲方向 | 极角 $\theta = \operatorname{atan2}(Y, X)$（0° 为沿 $+X_{\text{matlab}}$） |
| **D405 相机光学系** | 相机左红外传感器 | $+Z_{\text{cam}}$：光轴前向（深度）<br>$+X_{\text{cam}}$：水平向右<br>$+Y_{\text{cam}}$：垂直向下 | $X_{\text{ui}} = X_{\text{cam}}$， $Y_{\text{ui}} = Z_{\text{cam}}$ |

### 2. 坐标转换映射关系
从 UI 地面站拾取坐标 $(x_{\text{ui}}, y_{\text{ui}})$ 转换为 MATLAB 机械臂规划坐标 $(x_{\text{m}}, y_{\text{m}})$：
$$\begin{cases} x_{\text{matlab}} = y_{\text{ui}} \\ y_{\text{matlab}} = -x_{\text{ui}} \end{cases} \iff \begin{cases} x_{\text{ui}} = -y_{\text{matlab}} \\ y_{\text{ui}} = x_{\text{matlab}} \end{cases}$$

> 💡 **彻底解决 90° 旋转偏差**：算法库中的 `taskToSegments.m` 与 `projectTo2D.m` 已全量集成该标准变换，操作员在 UI 地图上点选任意坐标，机械臂都会分毫不差地准确移动至该物理点！

---

## 四、逐帧慢放与平滑轨迹回放（Slow Motion）

为真实反映空间超冗余机械臂连贯柔顺的游动过程，避免机械臂瞬间闪现跳变，系统采用**双端轨迹平滑慢放体系**：

```text
[MATLAB 运动规划端]                                   [Python UI 俯视雷达端]
q_traj (30 帧离散平滑轨迹)                           Smoothstep 缓动插值定时器 (33ms 步长)
       │                                                      │
       ▼                                                      ▼
opts.playback_delay = 0.04 (40ms 逐帧写入 inbox)      关节角度以 30 FPS 丝滑游动过渡
```

### 1. 初始伸展状态（Straight-Out Init）
- 修复了旧版直接向 $(0,0)$ 弯折蜷缩的 Bug；
- 执行 `reset` 指令时，机械臂各关节归零，直立伸展于正前方向（$+Y$ 轴方向），准备作业。

### 2. 慢放帧率调节
在 MATLAB 启动配置中指定 `opts.playback_delay`：
- `opts.playback_delay = 0.04`：40ms 刷新一帧（约 25 FPS，标准航天慢放模式）；
- `opts.playback_delay = 0.02`：快速推演模式（50 FPS）；
- `opts.playback_delay = 0.00`：即时完成模式（纯离线仿真）。

---

## 五、10 类标准任务指令集 (Task Commands)

系统支持 10 类标准化空间作业指令，完全覆盖自主抓取、避障游动与工位装配：

| 指令类型 (type) | 说明 | 关键参数 | 典型应用场景 |
| :--- | :--- | :--- | :--- |
| `reset` | 初始复位 | - | 各关节归零，沿正前方伸展 |
| `move_to` | 平面到达指定点 | `x`, `y` (米) | 俯视雷达地图点选粗定位 |
| `move_along` | 沿指定航向直线推进 | `theta_deg` (度), `distance_m` (米) | 定向接近、微距进给 |
| `move_for_pick` | 抓取前置伺服靠近 | `target_id` / `x, y, z` | 对准空间工件准备就位 |
| `move_for_place` | 放置前置工位寻位 | `target_id` / `x, y, z` | 移动至目标放置区域 |
| `rotate` | 末端朝向旋转 | `theta_deg` (度) | 调整末端夹爪对准角度 |
| `rotate_arm` | 指定单关节旋转 | `joint_index` (1~6), `alpha_deg` (度) | 手工微调或解奇异姿态 |
| `facing_arm` | 全臂面向对准 | `phi_deg` (度) | 机械臂整体航向扇区切换 |
| `pick` | 执行抓取动作链 | `target_id` (可选) | 闭合夹爪并确认锁定 |
| `place` | 执行释放动作链 | `target_id` (可选) | 张开夹爪脱钩工件 |
| `withdraw` | 安全撤回 | `distance_m` (米) | 完成作业后沿原路径脱离 |

---

## 六、快速启动与操作指南

### 1. 环境准备
推荐使用 64 位 Windows 10/11，进入项目目录：
```powershell
cd F:\Grade3\study\D405+UI\SpaceSnakeVisionUI
```

激活已配置完整的虚拟环境：
```powershell
.\.venv\Scripts\Activate.ps1
```

---

### 2. 运行模式 A：全链路 Mock 闭环演示（无需外接硬件）
适合开箱体验、界面交互汇报与脱机演示：

**终端 1（启动 UI 总控台）**：
```powershell
.\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock
```

**终端 2（启动 Mock 控制服务端）**：
```powershell
.\.venv\Scripts\python.exe -m src.bridge.mock_control_server --mode file
```

> 🎯 **操作演示**：
> 1. 打开 UI 的 **MISSION** 页面，点击底部 **“推进下一步”**，流程图依次高亮推进；
> 2. 切换到 **TASK** 页面，在俯视图中任意点击一个位置（如 `X=1.5, Y=3.0`），点击 **“发布任务指令”**；
> 3. 观察俯视雷达中的机械臂以 30 FPS 丝滑游动过去，夹爪随之到达目标点！

---

### 3. 运行模式 B：RealSense D405 相机真机 + MATLAB 运动算法联调

#### 步骤 1：连接 D405 相机并启动 UI
```powershell
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file
```
- UI 启动时会**自动清空历史垃圾指令文件**，杜绝历史缓存误触发。
- 进入 **VISION** 页面即可看到实时的 D405 高清视频流与靶标检测框。

#### 步骤 2：启动 MATLAB 算法监听循环
打开 MATLAB，在命令行窗口输入以下标准脚本：
```matlab
% 1. 进入机械臂运动规划算法仓库
cd('F:\Grade3\study\Hyper-Redundant-Snake-Robot-Manipulator-Algorithm-main');
addpath(fullfile(pwd, 'ArmSimulator2D'));

% 2. 创建 6 自由度蛇形臂几何动力学模型
model = createArmModel();

% 3. 配置与 UI 的通信信箱及慢放回放参数
opts = struct();
opts.outbox = 'F:/Grade3/study/D405+UI/SpaceSnakeVisionUI/data/outbox';
opts.inbox  = 'F:/Grade3/study/D405+UI/SpaceSnakeVisionUI/data/inbox';
opts.poll_interval  = 0.2;   % 轮询间隔(秒)
opts.playback_delay = 0.04;  % 轨迹慢放回放延时(秒)，25 FPS 丝滑展现
opts.verbose        = true;

% 4. 启动任务监听与执行循环
runTaskLoop(model, opts);
```

#### 步骤 3：下达任务与全自动闭环
1. 在 UI **MISSION** 页面点击“启动机械臂”，MATLAB 自动执行 `reset`，机械臂平滑展开；
2. 相机识别到工件（如靶标 201）后，点击“移动到目标物体”，MATLAB 计算逆解，机械臂精准逼近靶标；
3. 点击“抓取”，夹爪闭合；随后下达“放置”，机械臂运送至右侧终点区域并脱钩！

---

### 4. 自动化测试套件
项目配备覆盖核心几何、状态机、协议解析与 UI 绘制的测试套件，可随时执行验证：
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ --basetemp=./data/test_tmp
```
输出结果示例：
```text
============================= 44 passed in 0.66s ==============================
```

---

## 七、常见问题与排错指南 (FAQ)

### Q1: 为什么重新启动 UI 或 MATLAB 时，会自动把历史旧任务瞬间执行一遍？
- **原因**：历史运行在 `data/outbox/` 和 `data/inbox/` 遗留了未被归档的 `.json` 或 `.done` 文件。
- **解决方案**：系统在 `src/main.py` 启动入口中内置了清理钩子，每次打开 UI 会自动将两目录下的残留命令安全清除，确保每一次运行都是干净的初始状态。

### Q2: 为什么执行 `reset` 指令时机械臂会缩成一团或者反向弯折？
- **原因**：旧版逆解中将 `reset` 终点设置为坐标 `(0, 0)`，迫使末端贴向基座造成过度蜷缩。
- **解决方案**：已升级为 `execResetSeg`，直接将 6 个关节角度归零并平滑插值，机械臂自然优雅地笔直伸展朝向正前方。

### Q3: 为什么在俯视图中点击坐标后，机械臂运动方向好像旋转了 90 度？
- **原因**：地面站雷达坐标系以正前方为 $+Y$ 轴，而平面机械臂算法初始基准为 $+X$ 轴。
- **解决方案**：系统在 `taskToSegments.m`、`mock_control_server.py` 与 `mission_map.py` 中全量统一了转换矩阵 $X_{\text{matlab}} = Y_{\text{ui}}, Y_{\text{matlab}} = -X_{\text{ui}}$，坐标方向已完全一致。

### Q4: MATLAB 中执行完任务瞬间结束，无法看清中间动作过程？
- **原因**：未设置离散轨迹播放延时。
- **解决方案**：在 MATLAB 的 `opts` 中设置 `opts.playback_delay = 0.04;`（每帧 40 毫秒），`taskExecute.m` 会自动按 30 帧序列平滑回放并同步推送至 UI 俯视图。

---

## 八、技术支持与开发规范

- **开发语言**：Python 3.10+ / MATLAB R2022b+
- **GUI 框架**：PySide6 (Qt for Python 6.6+)
- **代码注释规范**：全项目遵循统一的简体中文（Simplified Chinese）注释与文档规范。
- **开源许可证**：内部科研与项目演示用途专用，保留所有权利。
