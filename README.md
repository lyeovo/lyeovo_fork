# D405 编码靶标视觉与蛇形机器人任务总控台 (交接交付版)

本项目是专门针对“**D405 编码靶标视觉测量流水线**”与“**蛇形机械臂任务总控台 (Mission Control HMI)**”联调与交付的独立集成工程。它将最新的感知算法、训练权重、任务状态机以及航天级任务总控界面整合在一起，供视觉团队与运动控制团队快速开箱运行与工程对接。

---

## 一、系统核心亮点与交付成果

1. **航天风格任务总控台 (Mission Control HMI)**：
   - Python/PySide6 作为唯一任务决策前端；
   - 顶部常驻状态 Header + 左侧紧凑导航栏 + 5 大功能分页（`MISSION` 总览、`VISION` 视觉、`TASK` 任务、`CONTROL` 运动、`SYSTEM` 监控）。

2. **流程图驱动的动态工作流 (`WorkflowWidget`)**：
   - 严格对应 [`机械臂抓取操作系统流程图.svg`](file:///f:/Grade3/study/D405+UI/%E6%9C%BA%E6%A2%B0%E8%87%82%E6%8A%93%E5%8F%96%E6%93%8D%E4%BD%9C%E7%B3%BB%E7%BB%9F%E6%B5%81%E7%A8%8B%E5%9B%BE.svg) 业务逻辑；
   - 具有呼吸发光效果、完成状态标记、分支自动条件判定与单步执行推进。

3. **两级视觉识别与已达标的 YOLO 权重**：
   - 模型文件：`SpaceSnakeVisionUI/models/marker_targets_best.pt`；
   - 支持 `201`、`222`、`207` 三类靶标全识别，训练评估 Precision=0.963, Recall=0.972, mAP50=97.5%；
   - 远距离输出方位角 `bearing`，近距离在白点深度有效时输出稳定 6 自由度位姿。

4. **10 类标准化任务指令与俯视地图操纵**：
   - 在 `TASK` 页或 `MISSION` 页支持直接在俯视地图点击拾取目标坐标，自动回填 `move_to` 指令；
   - 完整接口文档见：`docs/TASK_COMMAND_INTERFACE.md`。

---

## 二、交付目录结构

```text
D405_MarkerVision/
├── README.md                         # 本交付全景说明与快速开箱
├── docs/
│   └── TASK_COMMAND_INTERFACE.md     # 全任务控制指令接口技术规范 (v2.0 权威标准)
├── snake_vision_d405_target/         # D405 红外白点检测与模板学习库
│   ├── config/
│   │   ├── runtime_config.yaml       # 靶标参数与两级状态机配置
│   │   └── target_database.yaml      # 201/222/207 已学习的白点几何模板
│   └── src/                          # 视觉核心算法库
└── SpaceSnakeVisionUI/               # 任务总控台主程序
    ├── run_ui.py                     # 启动入口
    ├── models/
    │   └── marker_targets_best.pt    # 3类靶标最新 YOLO 权重
    ├── src/
    │   ├── mission/                  # 流程图状态机
    │   ├── state/                    # 集中式状态存储
    │   ├── ui/                       # 5大分页、自绘流程图与主题
    │   └── bridge/                   # 文件桥接与指令校验
    └── tests/                        # 单元与集成测试套件 (36项全通过)
```

---

## 三、快速启动

推荐在 Windows PowerShell 下运行：

```powershell
cd SpaceSnakeVisionUI

# 1. 启动模拟总控演示
.\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock

# 2. 启动 D405 实机总控
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file

# 3. 运行自动化测试验证
.\.venv\Scripts\python.exe -m pytest tests/ --basetemp=./data/test_tmp
```
