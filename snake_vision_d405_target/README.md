# D405 编码圆点靶标双目视觉项目

本项目用于 Intel RealSense D405 的左右红外图像处理：从图像中检测编码圆点靶标，匹配左右圆点，三角化恢复 3D 点，并输出靶标中心、粗略姿态和 JSON 结果。

当前阶段的目标很明确：先把“圆点检测 -> 左右匹配 -> 三角化 -> JSON 输出”跑稳定。不要一上来接机器人真实控制，也不要一开始纠结高精度姿态；先确认左右图里的圆点能稳定被检测出来。

## 1. 当前靶标和检测逻辑

当前配置针对的是 D405 红外图中常见的：

```text
亮灰色圆点 + 黑色底板
```

因此默认检测逻辑不是“黑点白底”，而是：

- 在 ROI 区域内检测，不默认全图搜索；
- 使用手动阈值 `threshold_value: 35`；
- 使用普通二值化 `binary_inverse: false`，即检测亮点；
- 允许当前靶标只检测到 7 到 8 个点；
- 只要左右图各不少于 `min_points: 6`，就可以继续做匹配和三角化调试。

默认配置在 [config/runtime_config.yaml](F:/Grade3/study/D405+UI/snake_vision_d405_target/config/runtime_config.yaml)：

```yaml
circle_detection:
  use_roi: true
  left_roi: [345, 170, 160, 115]
  right_roi: [360, 170, 130, 110]
  threshold_mode: "manual"
  threshold_value: 35
  binary_inverse: false
  gaussian_kernel: 3
  min_area: 30
  max_area: 300
  min_circularity: 0.75
  min_aspect: 0.6
  max_aspect: 1.4
  expected_points: 8
  min_points: 6
  debug_print: true
```

## 2. 目录结构

```text
snake_vision_d405_target/
  config/
    runtime_config.yaml       # 主运行配置
    stereo_params.yaml        # D405 双目标定参数
    target_config.yaml        # 靶标配置预留
  data/
    test_images/              # 采集到的左右测试图
    output/
      debug/                  # 圆点检测调试图
      images/                 # 匹配可视化图
      json/                   # 3D 结果 JSON
  scripts/
    01_show_d405_stereo.py
    02_save_d405_intrinsics.py
    04_test_rectification.py
    05_test_circle_detection.py
    06_test_stereo_matching.py
    07_test_triangulation.py
    08_run_realtime_pipeline.py
    09_run_offline_pair.py
    11_learn_target_template.py
  src/
    detection/circle_detector.py
    stereo/
    target/
    pipeline.py
  main.py
```

## 3.1 靶标学习 / 自动建库

如果你不知道每个编码靶标上白色圆点的真实物理坐标，可以先让程序用 D405 深度自动学习模板。学习阶段画面里只放一个靶标，尽量让圆点清晰、无遮挡、距离在 `0.10 m` 到 `1.50 m` 之间。

学习 `target_1`：

```powershell
python scripts/11_learn_target_template.py --target-id target_1 --num-frames 30 --save-debug
```

继续学习其他靶标：

```powershell
python scripts/11_learn_target_template.py --target-id target_2 --num-frames 30 --save-debug
python scripts/11_learn_target_template.py --target-id target_3 --num-frames 30 --save-debug
```

脚本会打开 D405 左红外图和深度图，复用现有圆点检测模块，读取每个圆点中心附近 `5 x 5` 窗口的深度中值，再反投影成 camera_left 坐标系下的 3D 点。每帧会拟合靶标平面并投影到局部二维坐标系，多帧对齐融合后写入：

```text
config/target_database.yaml
```

如果同一个 `target_id` 已经存在，会覆盖该靶标模板，但保留数据库里的其他靶标。数据库里的 `template_points` 单位是米，格式为局部靶标坐标系下的 `[x, y, 0.0]`，不是归一化坐标。

查看数据库：

```powershell
Get-Content config/target_database.yaml
```

开启 `--save-debug` 后，调试结果会保存到：

```text
data/output/template_learning/<target_id>/
```

重点看这些文件：

- `learning_summary.json`：学习帧数、使用帧数、剔除帧数、平面拟合误差和最终模板点；
- `frame_xxxx_dots.png`：圆点检测是否稳定；
- `frame_xxxx_depth_valid.png`：哪些圆点拿到了有效深度；
- `frame_xxxx_local2d.png`：单帧局部点阵是否形状稳定。

判断学习结果是否可靠，优先看：

- `used_frames` 接近 `requested_frames`，说明大多数帧可用；
- `average_depth_valid_ratio` 建议大于 `0.8`；
- `average_plane_rmse_m` 建议小于 `0.01`；
- `num_points` 应符合实际靶标点数，当前流程允许 6 到 12 个点；
- 多个靶标的点阵不能太相似，否则实时匹配的 `match_error_m` 会接近，程序可能输出 `unknown` 或低置信度。

相关配置在 [config/runtime_config.yaml](F:/Grade3/study/D405+UI/snake_vision_d405_target/config/runtime_config.yaml)：

```yaml
target_learning:
  num_frames: 30
  min_dots: 6
  max_dots: 12
  depth_window_size: 5
  max_plane_rmse_m: 0.01
  max_frame_match_error_m: 0.02

target_matching:
  max_match_error_m: 0.015
  unknown_if_error_larger: true
  allow_rotation: true
```

## 3.2 使用模板数据库实时识别和 6DoF 输出

学习完模板后，实时脚本仍然按原来的方式运行：

```powershell
python scripts/08_run_realtime_pipeline.py
```

实时阶段会先检测左右红外圆点并三角化出 3D 点，然后和 `config/target_database.yaml` 中的每个模板做 Chamfer 点集匹配。误差最小且小于 `target_matching.max_match_error_m` 的模板会作为当前 `target_id`；误差过大时输出 `unknown`，避免乱认。

姿态估计优先使用模板点和实测点的 Kabsch 刚体配准，无法建立可靠对应关系时自动退回 PCA 平面拟合。输出坐标默认在 `camera_left` 坐标系下，位置单位为米，姿态为四元数 `[qx, qy, qz, qw]`。质量字段里会包含：

- `match_error_m`：模板匹配误差，越小越好；
- `plane_rmse_m`：平面拟合误差；
- `pose_rmse_m`：Kabsch 配准误差，PCA 回退时为 `None`；
- `confidence`：综合置信度，范围 `[0, 1]`；
- `status`：`valid`、`unstable`、`invalid` 或 `unknown`。

建议控制侧只接受 `status: valid` 且 `confidence >= 0.75` 的结果；`confidence < 0.6` 时不要发布控制命令。

## 3. 环境安装

进入项目目录：

```powershell
cd F:\Grade3\study\D405+UI\snake_vision_d405_target
```

创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

如果只是用已有左右图片做离线调试，`pyrealsense2` 暂时装不上也可以先跳过相机采集部分。

## 4. 推荐运行顺序

第一次调试按这个顺序来，不要跳步：

1. 打开 D405，看左右红外图是否正常；
2. 保存当前 D405 的双目标定参数；
3. 采集一组正对靶标的左右红外图；
4. 检查双目校正；
5. 检查圆点检测；
6. 检查左右圆点匹配；
7. 三角化输出 3D 点；
8. 再拍近距离、远距离、倾斜图验证稳定性。

## 5. 打开相机并采集图片

检查左右红外窗口：

```powershell
python main.py --mode show_camera
```

窗口打开后：

- 按 `s` 保存一对左右图片；
- 按 `ESC` 退出。

图片会保存到：

```text
data/test_images/left/
data/test_images/right/
```

保存 D405 双目标定参数：

```powershell
python main.py --mode save_intrinsics
```

成功后会写入：

```text
config/stereo_params.yaml
```

真实实验前应使用自己的 D405 跑一次 `save_intrinsics`，不要长期依赖示例参数。

## 6. 检查双目校正

使用同一次保存的左右图片：

```powershell
python scripts/04_test_rectification.py --left data/test_images/left/你的左图.png --right data/test_images/right/你的右图.png
```

看窗口中的水平线。同一个物理圆点在左图和右图中应该基本落在同一条水平线上。如果明显上下错开，后面的匹配和三角化都会不稳定。

常见问题：

- 左右图不是同一次保存的；
- 左右路径写反；
- `config/stereo_params.yaml` 不是当前这台 D405 的参数；
- 相机内参保存失败或文件被旧参数覆盖。

## 7. 检查圆点检测

这是当前最关键的一步。

运行：

```powershell
python scripts/05_test_circle_detection.py --left data/test_images/left/left_20260707_163909_786.png --right data/test_images/right/right_20260707_163909_786.png
```

理想输出类似：

```text
left circles: 8
right circles: 8
```

或者：

```text
left circles: 7
right circles: 8
```

当前阶段这已经可以接受。不要要求必须正好 9 个点，因为当前编码靶标可能有缺点、暗点或遮挡。

程序会生成调试图：

```text
data/output/debug/left_roi.png
data/output/debug/right_roi.png
data/output/debug/left_binary.png
data/output/debug/right_binary.png
data/output/debug/left_detected.png
data/output/debug/right_detected.png
```

重点看 `left_binary.png` 和 `right_binary.png`：

- 正确情况：黑色背景，白色圆点，背景没有大面积变白；
- 阈值太低：背景或底板大片发白；
- 阈值太高：圆点断裂、变小甚至消失；
- ROI 不准：`left_roi.png` 或 `right_roi.png` 里没有完整靶标。

调参建议：

```yaml
# 背景发白，误检很多
threshold_value: 40
# 或
threshold_value: 45

# 圆点断裂或消失
threshold_value: 30
# 或
threshold_value: 25
```

如果靶标位置变了，优先改：

```yaml
left_roi: [x, y, width, height]
right_roi: [x, y, width, height]
```

不要一上来关掉 ROI 做全图检测。全图里背景、反光和其他亮点会明显增加误检。

## 8. Debug 打印怎么看

`debug_print: true` 时，圆点检测器会打印候选轮廓信息：

```text
[DEBUG] left contour accepted area=...
[DEBUG] left contour rejected:area area=...
[DEBUG] left contour rejected:circularity area=...
[DEBUG] left contour rejected:aspect area=...
```

含义：

- `accepted`：这个轮廓通过筛选，会被当成圆点；
- `rejected:area`：面积太小或太大；
- `rejected:circularity`：圆度不足，不像圆点；
- `rejected:aspect`：外接框宽高比不合适；
- `bbox`：候选轮廓在原图坐标系下的位置。

如果控制台全是 `rejected:area`，通常调 `min_area` 或 `max_area`。如果全是 `rejected:circularity`，可能是阈值让圆点破碎，先看 `binary.png`。

## 9. 检查左右匹配

圆点检测数量合理后，再跑匹配：

```powershell
python scripts/06_test_stereo_matching.py --left data/test_images/left/left_20260707_163909_786.png --right data/test_images/right/right_20260707_163909_786.png
```

看三件事：

- `matches` 数量是否接近检测到的圆点数；
- 匹配线是否基本水平；
- 匹配线是否明显交叉。

如果匹配线乱，先回到第 6 步检查校正，再回到第 7 步检查圆点检测，不要直接怀疑三角化。

可调参数：

```yaml
stereo_matching:
  y_threshold_px: 2.5
  min_disparity_px: 1.0
  max_disparity_px: 250.0
  uniqueness_check: true
```

## 10. 三角化和输出 JSON

检测和匹配稳定后，运行：

```powershell
python scripts/07_test_triangulation.py --left data/test_images/left/你的左图.png --right data/test_images/right/你的右图.png
```

或运行完整离线流程：

```powershell
python main.py --mode offline --left data/test_images/left/你的左图.png --right data/test_images/right/你的右图.png --show
```

输出文件：

```text
data/output/images/matches_时间.png
data/output/json/target_pose_时间.json
```

JSON 里的核心字段：

```json
{
  "target_id": "unknown",
  "frame_id": "camera_left",
  "position": {"x": 0.035, "y": -0.012, "z": 0.420},
  "orientation": {"qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
  "points_3d": [],
  "quality": {
    "num_points": 8,
    "num_matches": 8,
    "plane_rmse_m": 0.002
  }
}
```

当前阶段优先看：

- `position.z` 是否为正；
- 靶标靠近时 `z` 是否变小；
- 靶标远离时 `z` 是否变大；
- `num_matches` 是否稳定；
- `plane_rmse_m` 是否没有突然变大。

## 11. 实时流程

离线图片稳定后，再跑实时流程：

```powershell
python main.py --mode realtime
```

观察：

- 圆点框是否稳定；
- 匹配线是否稳定；
- 控制台 JSON 中的 `position.z` 是否随远近变化；
- `num_matches` 是否大部分时间不少于 6。

按 `ESC` 退出。

## 12. 靶标制作建议

为了让 D405 红外图更稳定，推荐：

- 黑色硬纸板或哑光底板；
- 白色或浅灰色哑光圆点；
- 不要使用强反光材料；
- 圆点在图像中最好有 15 到 25 像素宽；
- 靶标尽量平整，不要弯曲；
- 左右图里圆点都要完整可见。

如果圆点只有十来个像素，检测仍然可以做，但会更依赖阈值和 ROI。

## 13. 常见问题

### 13.1 图里看得到靶标，但检测不到圆点

按这个顺序排查：

1. 看 `left_roi.png` 和 `right_roi.png`，确认 ROI 框住了靶标；
2. 看 `left_binary.png` 和 `right_binary.png`，确认是黑底白点；
3. 亮点黑底时保持 `binary_inverse: false`；
4. 从 `threshold_value: 35` 开始，在 25 到 45 之间试；
5. 圆点太小就降低 `min_area`；
6. 噪声太多就提高 `min_area` 或 `min_circularity`。

### 13.2 检测数量总是少于 6

优先处理图像条件：

- 靶标靠近一点，让圆点变大；
- 调整角度，避免红外反光；
- 重新设置 ROI；
- 降低 `threshold_value`；
- 降低 `min_area`。

### 13.3 左右都能检测，但匹配错乱

优先检查：

- 左右图是否来自同一次采集；
- 双目校正是否正常；
- 同一个物理圆点是否大致在同一水平线；
- `y_threshold_px` 是否过大或过小。

### 13.4 3D 距离不对

优先检查：

- `stereo_params.yaml` 是否来自当前 D405；
- 左右图片是否写反；
- 匹配线是否连错；
- 近距离和远距离图的 `z` 变化方向是否正确。

## 14. 验证命令

语法检查：

```powershell
.\.venv\Scripts\python.exe -m compileall src scripts
```

如果安装了 `pytest`：

```powershell
pip install pytest
.\.venv\Scripts\python.exe -m pytest tests
```

当前 `requirements.txt` 只包含运行依赖，`pytest` 是可选测试依赖。

## 15. 当前阶段的判断标准

先不要急着做机器人控制或高精度姿态。当前合格标准是：

```text
左图检测到 7 到 8 个点
右图检测到 7 到 8 个点
检测框基本画在圆点上
binary 图没有大量背景误检
匹配线基本水平且不明显交叉
三角化得到的 z 为正
靶标靠近时 z 变小，远离时 z 变大
```

达到这些之后，再继续做编码识别、稳定姿态估计、UI 接入和机器人控制接口。
