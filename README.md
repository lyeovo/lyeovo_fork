# D405 编码靶标视觉与 SpaceSnake UI

本仓库用于 Intel RealSense D405 编码圆点靶标识别和机械臂视觉 UI 集成。当前系统把贴在目标物体上的编码靶标作为目标本体：远距离先用 YOLO 找到靶标大致方位，近距离再识别靶标上的白色圆点并输出 6DoF 位姿。

项目包含两个主要模块：

```text
D405+UI/
  SpaceSnakeVisionUI/          # PySide6 UI、YOLO 靶标检测、任务发布接口
  snake_vision_d405_target/    # D405 红外圆点检测、模板学习、靶标位姿估计
```

## 当前能力

- 使用 D405 彩色图通过 YOLO 识别编码靶标整体区域。
- 使用 D405 红外图在 YOLO 靶标区域内识别白色圆点。
- 支持 `201`、`222`、`207` 三类编码靶标的模板映射。
- 远距离不强制输出 6DoF，只输出目标方位 `bearing`。
- 近距离在有效深度圆点数量足够时输出完整 6DoF。
- UI 中显示靶标状态、目标框、板面四边形、方位和位姿。
- 通过 file bridge 输出任务 JSON，便于后续接机械臂控制模块。

## 两级识别逻辑

系统不是一看到靶标就强行输出 6DoF，而是按状态机工作：

```text
SEARCH
  没看到靶标

BEARING_ONLY
  YOLO 已看到靶标，但白点或深度不足，只输出方位

PARTIAL_DEPTH
  有部分白点深度有效，但不足以稳定估计 6DoF

POSE_6DOF
  至少 6 个白点深度有效，并且模板匹配稳定

LOST
  短时间丢失目标，保留 last_seen_bearing
```

UI 对应显示：

```text
BEARING_ONLY  -> 方位锁定，正在靠近
PARTIAL_DEPTH -> 部分深度有效
POSE_6DOF     -> 6DoF 已锁定，可执行
LOST          -> 目标丢失，正在搜索
```

## 运行环境

推荐在 Windows PowerShell 中运行。当前项目使用本地虚拟环境：

```powershell
cd F:\Grade3\study\D405+UI\SpaceSnakeVisionUI

.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file
```

如果需要重新创建环境：

```powershell
cd F:\Grade3\study\D405+UI\SpaceSnakeVisionUI

python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

`snake_vision_d405_target` 也有自己的 `requirements.txt`，用于单独调试 D405 双目、圆点检测和模板学习。

## 启动 UI

D405 实机 + 靶标 YOLO + 文件桥接：

```powershell
cd F:\Grade3\study\D405+UI\SpaceSnakeVisionUI

.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file
```

等价的显式写法：

```powershell
.\.venv\Scripts\python.exe run_ui.py `
  --camera d405 `
  --bridge file `
  --detector yolo_marker `
  --yolo-model models\marker_targets_best.pt `
  --yolo-conf 0.35
```

Mock 模式：

```powershell
.\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock
```

## YOLO 靶标模型

当前 UI 默认使用：

```text
SpaceSnakeVisionUI/models/marker_targets_best.pt
```

这个模型会识别编码靶标整体区域。远距离阶段使用 YOLO 框计算 bearing，近距离阶段在 YOLO 区域内继续做白点检测和 6DoF。

### 采集 YOLO 数据

以采集 `201` 靶标为例：

```powershell
cd F:\Grade3\study\D405+UI\SpaceSnakeVisionUI

.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 201
```

操作方式：

```text
摄像头对准靶标
看到红框正确框住靶标后按 s 保存
按 q 或 ESC 退出
```

程序会自动保存图片和 YOLO 标注到：

```text
datasets/marker_targets/images/
datasets/marker_targets/labels/
```

### 训练 YOLO

```powershell
.\.venv\Scripts\python.exe scripts\train_marker_yolo.py --epochs 80 --batch 8 --name marker_targets_v1
```

训练完成后模型通常在：

```text
runs/detect/marker_targets_v1/weights/best.pt
```

### 评估 YOLO

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_marker_yolo.py `
  --model runs\detect\marker_targets_v1\weights\best.pt `
  --save-vis
```

主要看：

```text
precision >= 0.90
recall    >= 0.90
mean_iou  >= 0.75
```

评估通过后可复制为 UI 默认模型：

```powershell
copy runs\detect\marker_targets_v1\weights\best.pt models\marker_targets_best.pt
```

## 靶标模板学习

如果新增编码靶标，需要先在 `snake_vision_d405_target` 中学习白点模板。学习时画面里尽量只放一个靶标，并保证 8 个白点清晰无遮挡。

示例：

```powershell
cd F:\Grade3\study\D405+UI\snake_vision_d405_target

.\.venv\Scripts\python.exe scripts\11_learn_target_template.py --target-id target_1
```

模板会写入：

```text
snake_vision_d405_target/config/target_database.yaml
```

UI 侧类别映射配置在：

```text
snake_vision_d405_target/config/runtime_config.yaml
```

关键配置：

```yaml
marker_yolo:
  class_to_target_id:
    "201": "target_1"
    "222": "target_2"
    "207": "target_3"
```

## 抗环境干扰设计

为了避免周围环境影响 6DoF，当前 `yolo_marker` 检测器采用：

```text
YOLO 框
  -> 黑色靶标板面四边形
  -> 板面 mask
  -> mask 内白点检测
  -> 自适应阈值
  -> 深度反投影
  -> 模板匹配 / Kabsch 位姿估计
```

UI 中会显示橙色四边形，表示系统认为的靶标板面区域。这个四边形应尽量贴合黑色靶标板面。

相关配置：

```yaml
marker_yolo:
  roi_pad_px: 30
  use_board_mask: true
  board_mask_pad_px: 10
  adaptive_dot_threshold: true
  pose_hold_seconds: 0.35
```

调参建议：

- 橙色四边形偏小：增大 `board_mask_pad_px`。
- 白点数量忽多忽少：检查 `adaptive_dot_threshold` 和红外曝光。
- `num_dots >= 6` 但 `valid_depth_points < 6`：说明白点看到了，但深度不稳定。
- `valid_depth_points >= 6` 仍不是 `POSE_6DOF`：检查模板匹配误差和误检点。

## 输出 JSON 与任务命令发布

### 1. 实时视觉状态输出 (`latest_targets.json`)

视觉模块输出结构核心字段如下：

```json
{
  "target_id": "target_1",
  "status": "BEARING_ONLY | PARTIAL_DEPTH | POSE_6DOF | LOST | SEARCH",
  "frame_id": "camera_left",
  "bearing": {
    "pixel_center": [0, 0],
    "pixel_error": [0, 0],
    "ray_camera": [0, 0, 1]
  },
  "pose": {
    "position": {"x": 0, "y": 0, "z": 0},
    "orientation": {"qx": 0, "qy": 0, "qz": 0, "qw": 1}
  },
  "quality": {
    "num_dots": 8,
    "valid_depth_points": 8,
    "confidence": 0.95
  }
}
```

当 `status != POSE_6DOF` 时，`pose` 允许为空，控制模块应使用 `bearing` 做靠近或搜索。

### 2. 任务命令发布契约 (`CMD-*.json`)

UI 支持生成并发布 10 种标准化任务指令至 `data/outbox/`：

| 任务类型 | 描述 | 核心参数 `params` |
| :--- | :--- | :--- |
| `move_to` | 末端移动到指定物理坐标 (x, y) | `{"x": float, "y": float}`（**支持在下方 Mission Map 地图上点击快速取点**） |
| `move_along` | 末端向 $\theta$ 方向移动 $d$ 米 | `{"theta_deg": float, "distance_m": float}` |
| `move_for_pick` | 根据实时相对位置向物体移动 | 自动关联锁定目标位姿 |
| `move_for_place` | 根据硬编码向放置位置移动 | `{"destination": "Assembly_Port_A"}` |
| `rotate` | 末端固定位置旋转 $\alpha$ 角 | `{"alpha_deg": float}` |
| `rotate_arm` | 第 $n$ 关节旋转 $\alpha$ 度 | `{"joint_index": int, "alpha_deg": float}` |
| `facing_arm` | 第 $n$ 关节面向 $\theta$ 方向 | `{"joint_index": int, "theta_deg": float}` |
| `pick` | 夹爪抓取动作链 | `{}` |
| `place` | 夹爪放置动作链 | `{}` |
| `withdraw` | 退回上一状态 | `{}` |
| `reset` | 恢复初始位置 | `{}` |
| `emergency_stop` | 最高优先级急停 | `{}` |

任务发布 JSON 示例（Schema v2.0）：

```json
{
  "schema_version": "2.0",
  "command_id": "CMD-20260902-00001",
  "timestamp": 1788320000.123,
  "source": "SpaceSnakeVisionUI",
  "command_type": "move_to",
  "params": {
    "x": 0.350,
    "y": 0.200
  },
  "selected_target": null,
  "safety": {
    "validation_passed": true,
    "validation_message": "validation passed",
    "estop_active": false,
    "execution_mode": "real_robot"
  }
}
```

## 目录说明

```text
SpaceSnakeVisionUI/
  run_ui.py                         # UI 启动入口
  src/camera/realsense_d405.py      # D405 color/IR/depth 采集
  src/vision/yolo_marker_detector.py# YOLO + 板面 mask + 白点 6DoF
  src/vision/pipeline.py            # 视觉流水线和画面叠加
  scripts/collect_marker_yolo_dataset.py
  scripts/train_marker_yolo.py
  scripts/evaluate_marker_yolo.py
  models/marker_targets_best.pt

snake_vision_d405_target/
  config/runtime_config.yaml
  config/target_database.yaml
  scripts/11_learn_target_template.py
  src/target/
  src/detection/
  src/stereo/
```

## Git 忽略规则

仓库不会提交以下内容：

```text
.venv/
runs/
采集图片和 YOLO 标签
data/outbox、data/inbox、data/logs
大型 zip 文件
yolo11n.pt 基础权重
```

仓库保留 `models/marker_targets_best.pt`，这样克隆后 UI 可以直接加载当前靶标模型。

## 常用命令

```powershell
# 启动 UI
cd F:\Grade3\study\D405+UI\SpaceSnakeVisionUI
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file

# 采集 201 数据
.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 201

# 训练 YOLO
.\.venv\Scripts\python.exe scripts\train_marker_yolo.py --epochs 80 --batch 8 --name marker_targets_v1

# 评估 YOLO
.\.venv\Scripts\python.exe scripts\evaluate_marker_yolo.py --model runs\detect\marker_targets_v1\weights\best.pt --save-vis

# 学习靶标模板
cd F:\Grade3\study\D405+UI\snake_vision_d405_target
.\.venv\Scripts\python.exe scripts\11_learn_target_template.py --target-id target_1
```
