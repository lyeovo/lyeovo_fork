# D405 编码靶标视觉 UI 交接项目

这个项目是给视觉和运动控制联调用的交接版。它把当前最新版功能整理成一个独立文件夹，方便直接理解、运行和对接。

核心目标：

```text
远距离：
  YOLO 识别编码靶标整体区域，输出目标相对相机的大致方位和粗距离。

近距离：
  在 YOLO 靶标区域内进一步识别 8 个白色圆点，读取深度并输出目标 6DoF 位姿。

运动控制对接：
  实时读取目标相对相机的位置数据，根据状态决定“搜索、靠近、等待 6DoF、执行精动作”。
```

## 1. 项目结构

```text
D405_MarkerVision/
  README.md
  docs/
    CONTROL_INTERFACE.md              # 给运动控制同学看的接口说明
  SpaceSnakeVisionUI/
    run_ui.py                         # UI 启动入口
    requirements.txt
    models/
      marker_targets_best.pt          # 当前靶标 YOLO 模型
    scripts/
      collect_marker_yolo_dataset.py  # 半自动采集 YOLO 数据
      train_marker_yolo.py            # 训练 YOLO
      evaluate_marker_yolo.py         # 达标检测
      watch_latest_vision_state.py    # 模拟控制端读取实时视觉状态
    src/
      vision/yolo_marker_detector.py  # YOLO 粗识别 + 白点精定位
      bridge/vision_state_publisher.py# 实时视觉状态 JSON 导出
  snake_vision_d405_target/
    config/
      runtime_config.yaml             # 靶标识别和状态机参数
      target_database.yaml            # 已学习的靶标白点模板
    scripts/
      11_learn_target_template.py     # 靶标模板学习
    src/
      target/
      detection/
      stereo/
```

## 2. 当前识别模式

当前采用“两级识别”：

```text
YOLO 粗识别
  输入：D405 彩色图
  作用：识别整块编码靶标，得到 bbox、中心、粗距离、bearing ray

白点精定位
  输入：D405 红外图 + 深度图
  作用：在 YOLO 区域内识别白色圆点，读取深度，匹配模板，输出 6DoF
```

为了减少环境干扰，白点检测不是全图搜索，而是：

```text
YOLO bbox
  -> 提取黑色靶标板面的四边形
  -> 生成 board mask
  -> 只在 mask 内找白点
  -> 根据 mask 内亮度自动调阈值
  -> 做模板匹配和 6DoF
```

UI 中橙色四边形表示系统认为的靶标板面区域。它越贴合黑色板面，白点检测越稳定。

## 3. 状态机

视觉模块不会因为没有 6DoF 就直接判定目标丢失。输出状态如下：

```text
SEARCH
  完全没看到靶标。

BEARING_ONLY
  YOLO 已看到靶标，但白点/深度不足，只输出目标方位。

PARTIAL_DEPTH
  有部分白点深度有效，但不足以稳定估计 6DoF。

POSE_6DOF
  至少 6 个白点深度有效，并且模板匹配稳定，输出 position + quaternion。

LOST
  短时间丢失目标，保留上一次方位。
```

运动控制建议：

```text
SEARCH / LOST:
  停止前进或小范围搜索。

BEARING_ONLY:
  使用 bearing.ray_camera 闭环靠近目标。

PARTIAL_DEPTH:
  继续小步靠近或调整视角，等待更多有效深度点。

POSE_6DOF:
  可进入近距离精定位、对接、抓取等动作。
```

## 4. 安装环境

建议在 Windows PowerShell 运行。

```powershell
cd D405_MarkerVision\SpaceSnakeVisionUI

python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

如果本机已经有原项目 `.venv`，也可以继续使用已有环境。

## 5. 启动实时 UI

D405 实机模式：

```powershell
cd D405_MarkerVision\SpaceSnakeVisionUI

.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file
```

显式启动参数：

```powershell
.\.venv\Scripts\python.exe run_ui.py `
  --camera d405 `
  --bridge file `
  --detector yolo_marker `
  --yolo-model models\marker_targets_best.pt `
  --yolo-conf 0.35
```

无相机测试 UI：

```powershell
.\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock
```

## 6. 实时位置数据接口

UI 运行后，每帧会写出最新视觉状态：

```text
SpaceSnakeVisionUI/data/vision/latest_targets.json
```

运动控制同学可以直接轮询这个文件，里面包含：

```text
target_id
status
bearing.pixel_center
bearing.pixel_error
bearing.ray_camera
depth_m / rough_distance_m
pose_camera
quality
```

测试读取：

```powershell
cd D405_MarkerVision\SpaceSnakeVisionUI

.\.venv\Scripts\python.exe scripts\watch_latest_vision_state.py
```

核心判断：

```text
status == "BEARING_ONLY"
  使用 bearing.ray_camera 做远距离靠近。

status == "POSE_6DOF"
  使用 pose_camera 做近距离精定位。
```

更完整的接口说明见：

```text
docs/CONTROL_INTERFACE.md
```

注意：当前 `pose_camera` 是目标相对 `camera_left` 的位姿，不是机械臂基座坐标。要转成 `robot_base`，还需要手眼标定得到 `T_base_camera`。

## 7. 半自动采集 YOLO 数据

采集前建议：

- 每次只放一种靶标，例如先采 `201`。
- 改变距离、角度、光照、背景。
- 红框必须正确框住整块黑色靶标后再保存。

采集 `201`：

```powershell
cd D405_MarkerVision\SpaceSnakeVisionUI

.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 201
```

采集 `222`：

```powershell
.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 222
```

采集 `207`：

```powershell
.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 207
```

操作键：

```text
s      保存当前图片和自动标注
n / p  切换候选框
m      显示/隐藏 mask
q/ESC  退出
```

保存位置：

```text
datasets/marker_targets/images/train
datasets/marker_targets/images/val
datasets/marker_targets/labels/train
datasets/marker_targets/labels/val
```

## 8. 训练 YOLO

```powershell
cd D405_MarkerVision\SpaceSnakeVisionUI

.\.venv\Scripts\python.exe scripts\train_marker_yolo.py --epochs 80 --batch 8 --name marker_targets_v1
```

训练结果：

```text
runs/detect/marker_targets_v1/weights/best.pt
```

训练通过后复制成 UI 默认模型：

```powershell
copy runs\detect\marker_targets_v1\weights\best.pt models\marker_targets_best.pt
```

## 9. 达标检测

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_marker_yolo.py `
  --model runs\detect\marker_targets_v1\weights\best.pt `
  --save-vis
```

建议达标线：

```text
precision >= 0.90
recall    >= 0.90
mean_iou  >= 0.75
```

可视化结果会保存到：

```text
runs/marker_eval/vis
```

## 10. 靶标白点模板学习

YOLO 负责识别整块靶标，6DoF 还需要白点模板。模板文件在：

```text
snake_vision_d405_target/config/target_database.yaml
```

如果新增靶标，进入靶标视觉模块学习：

```powershell
cd D405_MarkerVision\snake_vision_d405_target

.\.venv\Scripts\python.exe scripts\11_learn_target_template.py --target-id target_1
```

学习时画面里只放一个靶标，保证 8 个白点清晰无遮挡。

类别映射在：

```text
snake_vision_d405_target/config/runtime_config.yaml
```

```yaml
marker_yolo:
  class_to_target_id:
    "201": "target_1"
    "222": "target_2"
    "207": "target_3"
```

## 11. 任务命令发布与地图操纵

UI 支持通过命令面板与下方 **MISSION MAP** 俯视地图下发 10 类任务指令：

1. **`move_to (x, y)`**：末端移动到指定物理坐标。**直接在下方 MISSION MAP 地图上点击即可快速拾取物理坐标并回填到 X/Y 输入框，同时在地图上高亮标出 `WP: (x, y)`**。
2. **`move_along (θ, d)`**：末端向 $\theta$ 方向移动 $d$ 米。
3. **`move_for_pick`**：根据实时相对位置向锁定目标移动。
4. **`move_for_place`**：向预设工位（Port A / Port B 等）移动。
5. **`rotate (α)`**：末端固定位置旋转 $\alpha$ 角。
6. **`rotate_arm (α, n)`**：第 $n$ 关节旋转 $\alpha$ 度。
7. **`facing_arm (θ, n)`**：第 $n$ 关节面向 $\theta$ 方向。
8. **`pick`**：夹爪抓取动作链。
9. **`place`**：夹爪放置动作链。
10. **`withdraw`** / **`reset`**：退回上一状态 / 恢复初始安全姿态。
11. **`emergency_stop`**：独立最高优先级急停。

任务发布后将写入：

```text
SpaceSnakeVisionUI/data/outbox/CMD-*.json
```

控制端处理完后回写状态到：

```text
SpaceSnakeVisionUI/data/inbox/{command_id}_status.json
```

## 12. 运动控制对接最小流程

1. 视觉同学启动 UI：

   ```powershell
   cd D405_MarkerVision\SpaceSnakeVisionUI
   .\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file
   ```

2. 控制同学读取：

   ```text
   SpaceSnakeVisionUI/data/vision/latest_targets.json
   ```

3. 如果 `status == BEARING_ONLY`，按 `bearing.ray_camera` 控制相机/机械臂朝目标靠近。

4. 如果 `status == PARTIAL_DEPTH`，继续小步靠近并等待深度稳定。

5. 如果 `status == POSE_6DOF`，读取 `pose_camera.position` 和 `pose_camera.orientation_quat`。

6. 完成手眼标定后，将 `pose_camera` 转换为 `pose_base`，再执行真实机械臂精动作。

7. UI 发布任务时，控制端监听：

   ```text
   SpaceSnakeVisionUI/data/outbox/CMD-*.json
   ```

8. 控制端回写状态：

   ```text
   SpaceSnakeVisionUI/data/inbox/{command_id}_status.json
   ```

## 13. 常见问题

### YOLO 显示有目标，但没有 6DoF

说明只是识别到了整块靶标，白点深度还不够稳定。看：

```text
quality.num_dots
quality.valid_depth_points
quality.pose_method
quality.match_error_m
```

### 25 cm 左右仍然没有 6DoF

可能是白点反光导致深度空洞，或者板面四边形 mask 裁掉了部分白点。优先检查 UI 橙色四边形是否贴合靶标板面。

### 环境反光干扰白点

当前已经启用 board mask 和自适应阈值。如果仍有误检，可以调：

```yaml
marker_yolo:
  board_mask_pad_px: 10
  adaptive_dot_threshold: true
```

### 运动控制可以直接用 pose_camera 吗

只能用于相机坐标系下的相对运动或仿真。真实机械臂基座坐标需要手眼标定。
