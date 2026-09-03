# SpaceSnakeVisionUI · 空间蛇形机器人任务总控台 (Mission Control HMI)

SpaceSnakeVisionUI 现已全面升级为**航天任务控制中心风格的机器人任务总控平台**。本系统通过 PySide6 构建了唯一的人机交互与任务决策前端，将 Intel RealSense D405 编码靶标视觉流、任务调度状态机、俯视地图作业操纵、机械臂关节动力学监视及控制算法（`ArmSimApp`）闭环整合在一起。

---

## 一、核心功能亮点

1. **唯一总控人机交互 (Single-Source HMI)**：
   - 彻底摆脱“视觉工具”单一属性，成为控制端与感知端的任务统揽中枢；
   - 支持全屏幕/大窗口多页面切换，信息高度集成而不拥挤。

2. **程序化动态流程图组件 (`WorkflowWidget`)**：
   - 严格映射 [`机械臂抓取操作系统流程图.svg`](file:///f:/Grade3/study/D405+UI/%E6%9C%BA%E6%A2%B0%E8%87%82%E6%8A%93%E5%8F%96%E6%93%8D%E4%BD%9C%E7%B3%BB%E7%BB%9F%E6%B5%81%E7%A8%8B%E5%9B%BE.svg) 的全部 16 个节点与条件分支；
   - 当前执行节点具备 **电光青蓝 (`#00E5FF`) 辉光边框与缓动呼吸动效**（~30 FPS）；
   - 已完成节点标记为 **深翡翠绿 (`#2EEA8A`) 与对勾图标**；
   - 支持鼠标悬停与点击交互穿透。

3. **航天级 5 大功能分页**：
   - **`MISSION` (首屏任务总览)**：动态工作流 + 实时相机画面 + 目标/机械臂遥测卡片 + 底部单步推进与分支选择操作条；
   - **`VISION` (视觉感知专页)**：大视野相机流 + 目标列表表单 + 目标 6DoF 详细位姿矩阵与红外圆点质量指标；
   - **`TASK` (任务作业专页)**：俯视工作空间地图（点击拾取坐标） + 10 类任务指令表单 + 可折叠历史任务抽屉；
   - **`CONTROL` (运动控制专页)**：吸收 `ArmSimApp.m` 精髓，自绘蛇形臂 2D 骨骼拓扑、6 关节角度遥测条、规划器指标；
   - **`SYSTEM` (系统监控专页)**：全系统 9 大子模块在线健康状态、网络往返延时 (RTT)、FPS 监视与全局时间戳审计日志。

4. **10 类标准化任务指令体系**：
   - `move_to (x, y)`：平移末端至物理坐标（**支持在 Mission Map 俯视地图点击直接拾取**）
   - `move_along (θ, d)`：沿水平方位角推进 $d$ 米
   - `move_for_pick`：视觉伺服闭环靠近目标物体
   - `move_for_place`：装配工位寻位
   - `rotate (α)`：末端自转 $\alpha$ 角度
   - `rotate_arm (α, n)`：第 $n$ 关节增量转角
   - `facing_arm (θ, n)`：第 $n$ 关节绝对朝向角
   - `pick`：夹爪力控抓取动作链
   - `place`：夹爪脱钩释放动作链
   - `withdraw`：轨迹原路回退
   - `reset`：回归零位与系统复位
   - `emergency_stop`：最高优先级急停

---

## 二、代码工程目录结构

```text
SpaceSnakeVisionUI/
├── configs/                  # 运行时配置（相机、任务工位等）
├── data/                     # 运行时通信交换目录（自动忽略临时测试数据）
│   ├── outbox/               # 发出的任务命令 JSON (CMD-*.json)
│   ├── inbox/                # 控制端回写的状态反馈 JSON (*_status.json)
│   └── vision/               # 导出的实时视觉流 JSON (latest_targets.json)
├── datasets/                 # 靶标训练数据集（201 / 222 / 207）
├── docs/
│   └── TASK_COMMAND_INTERFACE.md # 全任务控制接口技术规范
├── models/
│   └── marker_targets_best.pt# 训练达标的 YOLOv11 靶标模型 (mAP50=97.5%)
├── scripts/                  # 辅助采集与离线评估脚本
├── src/
│   ├── bridge/               # 文件通信桥、命令生成器与安全校验器
│   ├── camera/               # RealSense D405 与 Mock 相机驱动
│   ├── mission/              # 任务流程状态机 (MissionStateMachine) 与流程节点定义
│   ├── state/                # 集中式响应状态中心 (SystemStateStore)
│   ├── ui/
│   │   ├── main_window.py    # 总控主窗口容器 (Header + Navigation + Pages)
│   │   ├── navigation.py     # 左侧窄式航天导航栏
│   │   ├── status_bar.py     # 顶部常驻任务指示 Header
│   │   ├── theme.qss         # 航天深色高对比度 QSS 主题
│   │   ├── pages/            # 5 大功能专页
│   │   └── widgets/          # 自绘工作流组件 (WorkflowWidget) 等
│   └── vision/               # 两级视觉检测流水线 (YOLO + 模板精定位)
└── tests/                    # 单元与集成测试套件 (21项全部通过)
```

---

## 三、快速上手与启动命令

### 1. 安装环境依赖

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动总控交互界面

```powershell
# 演示模式 (Mock 相机 + Mock 识别 + 文件桥接)
.\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock

# 实机模式 (连接 RealSense D405 相机)
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file
```

### 3. 运行自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ --basetemp=./data/test_tmp
```
