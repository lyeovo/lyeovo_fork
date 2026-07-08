# SpaceSnakeVisionUI

SpaceSnakeVisionUI 是一个面向在轨装配场景的蛇形机器人视觉作业 UI 原型。它把相机画面、目标检测、人工选择、任务级命令发布和控制端状态反馈串成一条可演示链路。

当前版本的重点不是直接控制电机或求解 IK，而是完成这一层桥接：

```text
D405 / Mock Camera
  -> YOLO / Mock Detector
  -> 用户选择目标
  -> UI 生成 TaskCommand
  -> 发布到 data/outbox/*.json 或 ROS2 topic
  -> 控制端 / MockControlServer 返回 TaskStatus
  -> UI 状态栏、日志、任务列表同步更新
```

## 功能概览

- 支持 Mock 相机和 RealSense D405 相机入口。
- 支持 Mock 检测器和 YOLO 检测器，YOLO 默认使用 `yolo11n.pt`。
- 可以在目标表格或相机画面中点击检测框锁定目标。
- 锁定目标后保存目标快照，避免视觉流刷新导致目标 ID 或目标对象丢失。
- 生成任务前会做安全校验，包括急停状态、机器人忙闲状态、目标是否存在、目标置信度、稳定度、深度和快照时效。
- 发布命令后写入 `data/outbox/CMD-*.json`，供控制模块读取。
- 支持 `pick_and_place`、`move_near_target`、`pick_target`、`dock_to_interface`、`home`、`cancel_task`、`emergency_stop` 等任务级命令。
- 支持 MockControlServer 写回 `RECEIVED`、`ACCEPTED`、`PLANNING`、`EXECUTING`、`COMPLETED`、`REJECTED`、`CANCELED`、`ESTOP_TRIGGERED` 等状态。
- UI 左侧内置可展开/收起的任务列表侧边栏。生成任务后会立即出现任务记录，点击任务可以查看任务类型、目标截图、目标信息、目的地、安全校验和状态历史。
- 主界面右侧有竖向滚动条；目标表、目标详情、命令面板、相机画面、地图和日志之间都有可拖动分隔条，可以按演示需要调整区域大小。
- 预留 ROS2 JSON 桥接。没有安装 `rclpy` 时会自动回退到 file mode，不影响普通演示。

## 安装

```bash
cd SpaceSnakeVisionUI
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

如果当前机器没有 D405 或 `pyrealsense2` 不可用，可以直接使用 Mock 模式完成 UI 和文件接口演示。

## 启动 UI

Mock 相机 + 文件桥接 + Mock 检测器：

```bash
.\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock
```

D405 + 文件桥接 + YOLO：

```bash
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file --detector yolo --yolo-model yolo11n.pt --yolo-conf 0.35
```

如果 D405 初始化失败，程序会回退到 MockCamera，UI 不会因为没有硬件直接崩溃。

## 启动 Mock 控制端

如果只启动 UI，点击“发布命令”后 UI 会显示任务已经发布，但不会自动出现 `RECEIVED -> COMPLETED` 这类控制端状态。要看到完整状态流，需要另开一个终端启动 MockControlServer：

```bash
cd SpaceSnakeVisionUI
.\.venv\Scripts\python.exe -m src.bridge.mock_control_server --mode file
```

MockControlServer 会监听：

```text
data/outbox/CMD-*.json
```

并写回：

```text
data/inbox/*_status.json
```

UI 每 600 ms 轮询一次 inbox。收到状态后，任务列表、任务日志和顶部状态栏都会更新。

## 推荐演示流程

1. 启动 UI：

   ```bash
   .\.venv\Scripts\python.exe run_ui.py --camera mock --bridge file --detector mock
   ```

2. 另开终端启动 MockControlServer：

   ```bash
   .\.venv\Scripts\python.exe -m src.bridge.mock_control_server --mode file
   ```

3. 在 UI 的目标表格或相机画面中选择一个目标，例如 `TGT-001`。
4. 在 Command Panel 中选择任务类型，例如 `pick_and_place`。
5. 选择放置区域，例如 `Assembly_Port_A`。
6. 点击“生成任务”。
7. 点击“发布命令”。
8. 点击界面最左侧的 `>` 展开任务列表侧边栏。
9. 在任务列表中点击对应任务，查看目标截图、任务摘要、发布路径和状态历史。

正常情况下，任务状态会依次变为：

```text
PUBLISHED
RECEIVED
ACCEPTED
PLANNING
EXECUTING
COMPLETED
```

## 任务列表说明

界面最左侧的 `>` 按钮用于展开任务列表侧边栏；展开后按钮会变成 `<`，再次点击即可收起。任务列表每次启动程序都会清空，旧状态文件不会自动灌入新列表。

- 左侧表格：显示 `Command ID`、任务类型、目标、目的地、最新状态和进度。
- 右侧详情：显示当前选中任务的目标截图、发布位置、任务参数、安全校验结果和状态历史。

任务发布后，列表会立刻新增一条 `PUBLISHED` 记录。这个状态表示 UI 已经把命令写入 outbox 或发布到桥接层。

如果任务长期停在 `PUBLISHED`，通常表示控制端还没有写回状态。请检查：

- MockControlServer 是否已经启动。
- `data/outbox/` 中是否有对应 `CMD-*.json`。
- `data/inbox/` 中是否生成了 `*_status.json`。
- 控制端是否拒绝了命令，例如 `safety.allow_execute=false`。

## 命令安全校验

普通目标任务发布前会检查：

- 是否处于 E-STOP 状态。
- 机器人是否正在执行其他任务。
- 是否已经选择目标。
- 目标快照是否过期。
- `confidence` 是否高于配置阈值。
- `stability_score` 是否高于配置阈值。
- `depth_m` 是否存在。
- `pose_base` 是否可用。

如果 `pose_base` 为空，UI 不会直接拒绝仿真任务，而是在 TaskCommand 的 `safety` 中写入：

```json
{
  "execution_mode": "simulation_only",
  "allow_real_execute": false
}
```

这表示控制端可以用于仿真或联调，但不应直接驱动真实机械臂执行。

安全阈值位于：

```text
configs/safety.yaml
```

## 文件接口约定

UI 发布命令：

```text
data/outbox/CMD-*.json
```

控制端写回状态：

```text
data/inbox/*_status.json
```

一个 TaskCommand JSON 中包含：

- `schema_version`
- `command_id`
- `timestamp`
- `command_type`
- `selected_target`
- `destination`
- `motion_params`
- `safety`

控制端只需要读取 `data/outbox/*.json`，按照 `command_type` 和 `safety` 决定是否执行，再持续写回 `TaskStatus` JSON。

## 常见问题

### 点击“发布命令”后看起来没反应

先点击最左侧 `>` 展开任务列表。如果能看到 `PUBLISHED`，说明 UI 已经成功发布命令。

如果没有后续状态，请启动 MockControlServer，或检查真实控制模块是否正在监听 `data/outbox` 并写回 `data/inbox`。

### 没选目标时不能生成 pick_and_place

这是预期行为。`pick_and_place`、`pick_target`、`move_near_target`、`dock_to_interface` 都需要目标。`home`、`cancel_task`、`emergency_stop` 不依赖目标。

### 急停后普通任务不能生成

这是预期行为。`emergency_stop` 触发后，普通任务会被阻止。第一版没有把“解除硬件急停”做成普通按钮，避免 UI 误导真实设备状态。

### YOLO 能识别但 pose_base 为空

这表示当前目标只有相机坐标系位姿，还没有完成手眼标定或基坐标转换。命令仍可用于仿真联调，但 JSON 中会标记 `allow_real_execute=false`。

## 目录说明

```text
src/ui/main_window.py              UI 主状态机、目标锁定、命令发布、状态刷新
src/ui/task_list.py                可显示/隐藏的任务列表和详情查看
src/bridge/command_builder.py      TaskCommand 构造
src/bridge/command_validator.py    发布前安全校验
src/bridge/file_bridge.py          outbox/inbox 文件桥接
src/bridge/mock_control_server.py  Mock 控制端
src/bridge/ros2_bridge_optional.py 可选 ROS2 JSON 桥接
src/models.py                      TaskCommand / TaskStatus / DetectedObject 等数据模型
configs/bridge.yaml                桥接配置
configs/safety.yaml                安全阈值配置
configs/task_zones.yaml            任务放置区域配置
```

## 验证命令

语法检查：

```bash
$env:PYTHONPYCACHEPREFIX="$env:TEMP\spacesnake_pycache"
.\.venv\Scripts\python.exe -m compileall src tests
```

单元测试：

```bash
$env:PYTHONPYCACHEPREFIX="$env:TEMP\spacesnake_pycache"
.\.venv\Scripts\python.exe -m pytest
```

如果 Windows 上已有 `__pycache__` 权限异常，可以保留上面的 `PYTHONPYCACHEPREFIX` 设置，把 pyc 临时文件写到系统临时目录。
## 编码靶标识别模式

当编码靶标已经在 `snake_vision_d405_target` 项目中学习完成后，可以把编码靶标贴在目标物体上，并让 UI 只识别这些靶标。启动方式：

```bash
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file --detector marker
```

`marker` 模式会读取：

```text
F:\Grade3\study\D405+UI\snake_vision_d405_target\config\target_database.yaml
```

UI 会使用 D405 左红外图作为主画面，并把深度图对齐到红外图。检测流程为：

```text
红外圆点检测 -> 圆点深度中值 -> 3D 反投影 -> 模板匹配 target_1/target_2/target_3 -> 6DoF 姿态估计
```

右侧 `SELECTED TARGET 6DoF` 面板会显示 `Match Error`、`Plane RMSE`、`Pose RMSE`、`Confidence`、位置、欧拉角和四元数。建议只在 `Status: AVAILABLE` 且 `Confidence >= 0.75` 时发布控制命令；如果显示 `unknown_marker_*`，说明模板匹配误差过大或多个靶标圆点被聚成了一个簇。

`marker` 模式默认是全视野自动捕获，不要求靶标放在画面中央。相关配置在相邻项目的 `config/runtime_config.yaml` 中：

```yaml
marker_detection:
  use_roi: false
  max_candidates: 240
  cluster_radius_px: 90.0
  min_cluster_span_px: 12.0
  max_cluster_span_px: 240.0
  max_clusters: 8
```

如果画面里有大量反光点导致误检，可以降低 `max_candidates` 或缩小 `max_cluster_span_px`；如果靶标距离很远、点阵在图像上变小，可以适当降低 `min_cluster_span_px` 和 `cluster_radius_px`。

远距离阶段不强制输出 6DoF。D405 距离较远时白点深度可能不稳定，`marker` 模式会先输出 bearing：

```text
SEARCH -> BEARING_ONLY / PARTIAL_DEPTH -> POSE_6DOF
```

状态含义：

- `SEARCH`：完全没看到靶标；
- `BEARING_ONLY`：看到 2 个以上白点或靶标区域，只输出 `pixel_center`、`pixel_error`、`ray_camera`；
- `PARTIAL_DEPTH`：部分白点深度有效，但不足 6 个，暂不输出 6DoF；
- `POSE_6DOF`：有效深度点不少于 6 个，输出完整 position + quaternion；
- `LOST`：短时间丢失目标，保留 `last_seen_bearing`，控制侧应暂停前进或做小范围搜索。

`move_near_target` 可以使用 `BEARING_ONLY` / `PARTIAL_DEPTH` 的 bearing 做小步靠近；抓取、对接等需要精确姿态的任务应等到 `POSE_6DOF` 后再执行。

## YOLO 粗识别 + 白点精定位模式

推荐最终流程使用 `yolo_marker`：

```text
远距离：YOLO 识别整块黑色编码靶标 -> 输出 target_id、bearing、粗距离
近距离：在 YOLO bbox 内检测 8 个白点 -> 深度反投影 -> 模板配准 -> 输出 6DoF
```

训练 YOLO 时把三类靶标按编号标注为：

```text
201
222
207
```

数据集配置已放在：

```text
datasets/marker_targets/marker_targets.yaml
```

目录结构按 YOLO 格式放置：

```text
datasets/marker_targets/
  images/train/
  images/val/
  labels/train/
  labels/val/
  marker_targets.yaml
```

训练示例：

```bash
yolo detect train model=yolo11n.pt data=datasets/marker_targets/marker_targets.yaml epochs=100 imgsz=640 batch=8
```

训练完成后，把 `best.pt` 放到例如：

```text
models/marker_targets_best.pt
```

启动 UI：

```bash
.\.venv\Scripts\python.exe run_ui.py --camera d405 --bridge file --detector yolo_marker --yolo-model models/marker_targets_best.pt --yolo-conf 0.35
```

默认类别映射位于相邻项目的 `config/runtime_config.yaml`：

```yaml
marker_yolo:
  class_to_target_id:
    "201": "target_1"
    "222": "target_2"
    "207": "target_3"
```

如果你训练时直接把类别命名成 `target_1/target_2/target_3`，也可以使用；如果编号和模板对应关系不同，修改上面的映射即可。

### 半自动采集 YOLO 数据

运行采集脚本，每次采一个类别。脚本会打开 D405 彩色画面，自动寻找黑色靶标板并画红框；红框准确时按 `s` 保存图片和 YOLO 标签。

采集 201：

```bash
.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 201
```

采集 222：

```bash
.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 222
```

采集 207：

```bash
.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 207
```

按键：

- `s`：保存当前图片和标签；
- `n` / `p`：如果画面里有多个红框，切换要保存的框；
- `m`：查看黑色区域分割 mask，用于判断阈值是否合适；
- `q` 或 `ESC`：退出。

默认保存到：

```text
datasets/marker_targets/images/train
datasets/marker_targets/images/val
datasets/marker_targets/labels/train
datasets/marker_targets/labels/val
```

脚本默认每保存 5 张就把 1 张放入 `val`。如果红框找不到或框不准，可以调整黑色阈值：

```bash
.\.venv\Scripts\python.exe scripts\collect_marker_yolo_dataset.py --class-id 201 --dark-threshold 100
```
## YOLO 训练和达标检测

当前如果只采了 `201`，可以先做 smoke training，确认训练链路没问题：

```bash
.\.venv\Scripts\python.exe scripts\train_marker_yolo.py --epochs 80 --batch 8 --name marker_201_smoke
```

训练完成后评估验证集：

```bash
.\.venv\Scripts\python.exe scripts\evaluate_marker_yolo.py --model runs/detect/marker_201_smoke/weights/best.pt --save-vis
```

评估脚本会计算：

- `precision`：检测出来的框有多少是真的；
- `recall`：标注框有多少被找回来；
- `mean_iou`：预测框和标注框平均重合程度；
- `tp/fp/fn`：正确、误检、漏检数量。

默认达标线：

```text
precision >= 0.90
recall >= 0.90
mean_iou >= 0.75
```

完整报告保存到：

```text
runs/marker_eval/summary.json
```

如果要先放宽一点做调试：

```bash
.\.venv\Scripts\python.exe scripts\evaluate_marker_yolo.py --model runs/detect/marker_201_smoke/weights/best.pt --min-precision 0.80 --min-recall 0.80 --min-mean-iou 0.65 --save-vis
```

等 `201/222/207` 三类都采够后，再统一训练：

```bash
.\.venv\Scripts\python.exe scripts\train_marker_yolo.py --epochs 120 --batch 8 --name marker_targets_3class
.\.venv\Scripts\python.exe scripts\evaluate_marker_yolo.py --model runs/detect/marker_targets_3class/weights/best.pt --save-vis
```
