# D405 编码圆点靶标双目视觉项目开发说明

> 用途：把本文件交给 Codex / AI 编程助手，让其按模块生成完整 Python 项目代码。  
> 项目背景：面向“超冗余自由度蛇形机器人在轨组装”场景，Windows 上位机负责 D405 相机图像采集、编码圆点靶标识别、目标三维坐标/位姿估计、UI 显示与命令发布接口预留。  
> 当前重点：先实现 **D405 双目图像采集 → 双目标定参数读取/保存 → 左右图圆点检测 → 左右圆点匹配 → 三角化恢复 3D 点 → 靶标中心与姿态估计 → 输出 JSON**。

---

## 0. 给 Codex 的总体要求

请你基于本说明生成一个可运行的 Python 项目，项目名称建议为：

```text
snake_vision_d405_target
```

项目运行环境：

- 操作系统：Windows 10 / Windows 11
- Python：3.10 或 3.11
- 相机：Intel RealSense D405
- 主要依赖：`pyrealsense2`, `opencv-python`, `opencv-contrib-python`, `numpy`, `scipy`, `pyyaml`, `matplotlib`, `scikit-learn`
- 前期不强制使用 ROS2；需要保留未来接入 ROS2 / 控制模块的接口
- 所有空间坐标单位统一使用 **米 m**
- 所有角度内部计算使用 **弧度 rad**
- 所有输出结果必须包含时间戳、坐标系名称、置信度/质量指标

请按照“模块化、可调试、可测试”的原则写代码，不要把所有逻辑堆在一个脚本里。每个模块都要能单独运行测试。

---

## 1. 项目目标

### 1.1 当前阶段目标

当前阶段不要求直接识别复杂编码 ID，也不要求一开始就完成机器人闭环控制。当前阶段目标是：

1. 从 D405 读取左右红外图像；
2. 读取 D405 出厂内参、畸变参数和左右相机外参；
3. 对左右图像进行去畸变和极线校正；
4. 在左右图像中检测编码圆点靶标上的圆点中心；
5. 匹配左右图中属于同一个物理圆点的像素点；
6. 根据双目几何进行三角化，恢复圆点在左相机坐标系下的 3D 坐标；
7. 将同一靶标上的 9 个圆点聚合，估计靶标中心位置；
8. 通过平面拟合估计靶标平面法向和粗略姿态；
9. 实时显示检测结果，并将目标位姿输出为 JSON；
10. 为 UI 选择目标和后续命令发布预留接口。

### 1.2 后续扩展目标

后续扩展包括：

1. 多靶标识别；
2. 根据 9 点相对布局识别 target_id；
3. 建立靶标局部坐标系，输出完整 6DoF 位姿；
4. 坐标从相机系转换到机器人基座系；
5. UI 中选择目标并生成移动/抓取/停止命令；
6. 接入 ROS2 或串口/Socket/HTTP 接口发送控制命令。

---

## 2. 核心技术路线

本项目前期采用 **双目三角化路线**，而不是一开始使用 PnP。

原因：

- PnP 需要提前知道靶标上每个点在靶标坐标系下的真实 3D 坐标；
- 当前老师建议先把编码靶标当作“零散圆点阵列”，通过双目相机从图像中恢复每个圆点的三维坐标；
- 等能稳定恢复 3D 点后，再根据 9 个圆点之间的相对位置关系做 target_id 识别和整体位姿估计。

总体流程：

```text
D405 左右红外图像
        ↓
读取/保存双目标定参数
        ↓
左右图像去畸变 + 极线校正
        ↓
检测左图圆点中心、右图圆点中心
        ↓
基于极线约束进行左右点匹配
        ↓
双目三角化得到圆点 3D 坐标
        ↓
9 点聚合为一个靶标
        ↓
估计靶标中心、平面法向、姿态
        ↓
输出 JSON + 可视化 + UI/控制接口
```

---

## 3. 坐标系定义

### 3.1 图像坐标系

OpenCV 图像坐标：

```text
u 轴：图像向右为正
v 轴：图像向下为正
原点：图像左上角
单位：像素 px
```

圆心像素坐标记为：

```python
point_2d = [u, v]
```

### 3.2 左相机坐标系

本项目默认以 D405 左红外相机为视觉主坐标系：

```text
frame_id = "camera_left"
X 轴：向右
Y 轴：向下
Z 轴：向前，即相机看出去的方向
单位：米 m
```

三维点记为：

```python
point_3d_camera = [X, Y, Z]
```

### 3.3 靶标局部坐标系

当 9 个圆点被聚合成一个靶标后，建立局部坐标系：

```text
target frame:
origin：9 个圆点三维坐标均值，作为靶标中心
z_axis：靶标平面法向量
x_axis：靶标点云在平面内的第一主方向
y_axis：z_axis × x_axis 或通过 SVD 得到第二主方向
```

最终位姿输出：

```python
position = [x, y, z]
orientation_quat = [qx, qy, qz, qw]
```

### 3.4 机器人基座坐标系预留

后续控制模块通常需要目标在机器人基座坐标系下的位置：

```text
frame_id = "robot_base"
```

当前机械结构尚未完全确定，因此先提供占位函数：

```python
def camera_to_base(p_camera: np.ndarray) -> np.ndarray:
    R_base_camera = np.eye(3)
    t_base_camera = np.zeros(3)
    return R_base_camera @ p_camera + t_base_camera
```

后续只需替换 `R_base_camera` 和 `t_base_camera`。

---

## 4. 项目目录结构

请生成如下项目结构：

```text
snake_vision_d405_target/
│
├── README.md
├── requirements.txt
├── main.py
│
├── config/
│   ├── stereo_params.yaml
│   ├── target_config.yaml
│   └── runtime_config.yaml
│
├── data/
│   ├── calib/
│   │   ├── left/
│   │   └── right/
│   ├── test_images/
│   │   ├── left/
│   │   └── right/
│   └── output/
│       ├── json/
│       ├── images/
│       └── logs/
│
├── src/
│   ├── __init__.py
│   │
│   ├── camera/
│   │   ├── __init__.py
│   │   ├── d405_capture.py
│   │   ├── d405_intrinsics.py
│   │   └── image_pair_loader.py
│   │
│   ├── calibration/
│   │   ├── __init__.py
│   │   ├── stereo_params.py
│   │   ├── stereo_rectifier.py
│   │   └── chessboard_calibration.py
│   │
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── circle_detector.py
│   │   └── visualization_2d.py
│   │
│   ├── stereo/
│   │   ├── __init__.py
│   │   ├── stereo_matcher.py
│   │   └── triangulator.py
│   │
│   ├── target/
│   │   ├── __init__.py
│   │   ├── target_cluster.py
│   │   ├── pose_estimator.py
│   │   └── target_identifier.py
│   │
│   ├── interface/
│   │   ├── __init__.py
│   │   ├── result_schema.py
│   │   ├── json_publisher.py
│   │   ├── command_schema.py
│   │   └── dummy_control_client.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config_io.py
│   │   ├── geometry.py
│   │   ├── logger.py
│   │   └── time_utils.py
│   │
│   └── ui/
│       ├── __init__.py
│       └── simple_viewer.py
│
├── scripts/
│   ├── 01_show_d405_stereo.py
│   ├── 02_save_d405_intrinsics.py
│   ├── 03_capture_calib_images.py
│   ├── 04_test_rectification.py
│   ├── 05_test_circle_detection.py
│   ├── 06_test_stereo_matching.py
│   ├── 07_test_triangulation.py
│   ├── 08_run_realtime_pipeline.py
│   └── 09_run_offline_pair.py
│
└── tests/
    ├── test_geometry.py
    ├── test_circle_detector.py
    ├── test_stereo_matcher.py
    └── test_pose_estimator.py
```

---

## 5. requirements.txt

请生成以下依赖：

```text
numpy
opencv-python
opencv-contrib-python
pyyaml
scipy
matplotlib
scikit-learn
pyrealsense2
```

注意：

- 如果 `pyrealsense2` 在某些环境安装失败，需要在 README 中说明可以先用离线图像调试。
- 所有模块应该支持离线图像输入，避免没有相机时无法开发。

---

## 6. 配置文件设计

### 6.1 config/runtime_config.yaml

```yaml
camera:
  width: 848
  height: 480
  fps: 30
  use_realsense: true
  infrared_left_index: 1
  infrared_right_index: 2

paths:
  stereo_params: "config/stereo_params.yaml"
  target_config: "config/target_config.yaml"
  output_json_dir: "data/output/json"
  output_image_dir: "data/output/images"
  log_dir: "data/output/logs"

rectification:
  alpha: 0
  draw_epipolar_lines: true
  epipolar_line_gap: 40

circle_detection:
  threshold_mode: "otsu"
  binary_inverse: true
  gaussian_kernel: 5
  min_area: 20
  max_area: 5000
  min_circularity: 0.60
  debug_show_binary: false

stereo_matching:
  y_threshold_px: 2.5
  min_disparity_px: 1.0
  max_disparity_px: 250.0
  uniqueness_check: true

target:
  expected_points_per_target: 9
  min_points_for_pose: 6
  cluster_eps_m: 0.08
  cluster_min_samples: 4
  max_plane_rmse_m: 0.005

output:
  save_json: true
  print_json: true
  smooth_result: true
  smoothing_alpha: 0.2
```

### 6.2 config/stereo_params.yaml

该文件由脚本 `02_save_d405_intrinsics.py` 自动生成。示例格式：

```yaml
image_width: 848
image_height: 480

K_left:
  - [389.20166016, 0.0, 315.42495728]
  - [0.0, 388.65734863, 237.17500305]
  - [0.0, 0.0, 1.0]

D_left: [-0.05406127, 0.05562355, 0.00020929, 0.00054739, -0.01739847]

K_right:
  - [389.0, 0.0, 315.0]
  - [0.0, 389.0, 237.0]
  - [0.0, 0.0, 1.0]

D_right: [0.0, 0.0, 0.0, 0.0, 0.0]

R:
  - [1.0, 0.0, 0.0]
  - [0.0, 1.0, 0.0]
  - [0.0, 0.0, 1.0]

T:
  - [-0.055]
  - [0.0]
  - [0.0]
```

注意：

- 上面的数值只是格式示例，代码运行时必须读取真实 D405 参数；
- `T` 单位必须确认是米；
- 如果从 RealSense SDK 读取，保存时也统一成米。

### 6.3 config/target_config.yaml

前期可以不依赖真实靶标数据库，但要预留文件：

```yaml
targets:
  default_9dot:
    description: "默认 9 圆点靶标，前期仅用于显示，不强制用于 PnP"
    expected_points: 9
    unit: "m"
    use_for_identification: false

identification:
  enabled: false
  method: "relative_layout"
```

后续如果需要识别不同靶标 ID，可以扩展：

```yaml
targets:
  target_201:
    expected_points: 9
    pattern_2d_normalized:
      - [-1,  1]
      - [ 0,  1]
      - [ 1,  1]
      - [-1,  0]
      - [ 0,  0]
      - [ 1,  0]
      - [-1, -1]
      - [ 0, -1]
      - [ 1, -1]
```

---

## 7. 数据结构设计

### 7.1 StereoParams

文件：`src/calibration/stereo_params.py`

请定义数据类：

```python
from dataclasses import dataclass
import numpy as np

@dataclass
class StereoParams:
    image_width: int
    image_height: int
    K_left: np.ndarray
    D_left: np.ndarray
    K_right: np.ndarray
    D_right: np.ndarray
    R: np.ndarray
    T: np.ndarray
```

要求提供：

```python
load_stereo_params(path: str) -> StereoParams
save_stereo_params(params: StereoParams, path: str) -> None
```

---

### 7.2 Circle2D

文件：`src/detection/circle_detector.py`

```python
from dataclasses import dataclass

@dataclass
class Circle2D:
    u: float
    v: float
    area: float
    circularity: float
    radius_est: float
```

---

### 7.3 StereoMatch

文件：`src/stereo/stereo_matcher.py`

```python
from dataclasses import dataclass

@dataclass
class StereoMatch:
    left_index: int
    right_index: int
    u_left: float
    v_left: float
    u_right: float
    v_right: float
    disparity: float
    score: float
```

---

### 7.4 TargetPoseResult

文件：`src/interface/result_schema.py`

```python
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

@dataclass
class TargetPoseResult:
    timestamp: float
    target_id: str
    frame_id: str
    position: List[float]
    orientation: Optional[List[float]]
    points_3d: List[List[float]]
    quality: Dict[str, Any]
```

要求提供函数：

```python
def result_to_dict(result: TargetPoseResult) -> dict:
    ...

def result_to_json(result: TargetPoseResult, indent: int = 2) -> str:
    ...
```

输出 JSON 格式如下：

```json
{
  "timestamp": 1720000000.123,
  "target_id": "unknown",
  "frame_id": "camera_left",
  "position": {
    "x": 0.035,
    "y": -0.012,
    "z": 0.420
  },
  "orientation": {
    "qx": 0.01,
    "qy": 0.02,
    "qz": 0.03,
    "qw": 0.99
  },
  "points_3d": [
    [0.01, -0.02, 0.42],
    [0.02, -0.02, 0.42]
  ],
  "quality": {
    "num_points": 9,
    "num_matches": 9,
    "plane_rmse_m": 0.002,
    "confidence": 0.91
  }
}
```

---

## 8. 模块详细实现要求

## 8.1 D405 左右图像采集模块

文件：`src/camera/d405_capture.py`

请实现类：

```python
class D405StereoCamera:
    def __init__(self, width=848, height=480, fps=30):
        ...

    def start(self) -> None:
        ...

    def get_frames(self) -> tuple[np.ndarray, np.ndarray]:
        """返回 left_img, right_img，均为 uint8 灰度图。"""
        ...

    def stop(self) -> None:
        ...
```

要求：

1. 使用 `pyrealsense2`；
2. 开启左红外和右红外：

```python
config.enable_stream(rs.stream.infrared, 1, width, height, rs.format.y8, fps)
config.enable_stream(rs.stream.infrared, 2, width, height, rs.format.y8, fps)
```

3. 若无法连接相机，要抛出清晰错误信息；
4. 支持 `with` 语法更好，但不是强制；
5. `get_frames()` 返回两个 `np.ndarray`。

脚本：`scripts/01_show_d405_stereo.py`

功能：

- 打开 D405；
- 实时显示左右红外图；
- 按 `s` 保存当前帧到 `data/test_images/left` 和 `data/test_images/right`；
- 按 `ESC` 退出。

---

## 8.2 读取 D405 内外参模块

文件：`src/camera/d405_intrinsics.py`

请实现：

```python
def read_d405_stereo_params(width=848, height=480, fps=30) -> StereoParams:
    ...
```

逻辑：

1. 启动 D405 左右红外流；
2. 获取左右相机 intrinsics：

```python
left_profile = profile.get_stream(rs.stream.infrared, 1).as_video_stream_profile()
right_profile = profile.get_stream(rs.stream.infrared, 2).as_video_stream_profile()
left_intr = left_profile.get_intrinsics()
right_intr = right_profile.get_intrinsics()
```

3. 转换成内参矩阵：

```python
K = [[fx, 0, ppx],
     [0, fy, ppy],
     [0, 0, 1]]
```

4. 获取左右相机外参：

```python
extr = left_profile.get_extrinsics_to(right_profile)
R = np.array(extr.rotation).reshape(3, 3)
T = np.array(extr.translation).reshape(3, 1)
```

5. 返回 `StereoParams`。

脚本：`scripts/02_save_d405_intrinsics.py`

功能：

- 读取 D405 参数；
- 打印 K、D、R、T；
- 保存到 `config/stereo_params.yaml`。

---

## 8.3 双目校正模块

文件：`src/calibration/stereo_rectifier.py`

请实现类：

```python
class StereoRectifier:
    def __init__(self, stereo_params: StereoParams, alpha: float = 0.0):
        ...

    def rectify(self, left_img: np.ndarray, right_img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ...

    @property
    def P1(self) -> np.ndarray:
        ...

    @property
    def P2(self) -> np.ndarray:
        ...

    @property
    def Q(self) -> np.ndarray:
        ...
```

内部需要调用：

```python
cv2.stereoRectify()
cv2.initUndistortRectifyMap()
cv2.remap()
```

要求：

- 初始化时计算 `R1, R2, P1, P2, Q` 和 remap 映射表；
- `rectify()` 输入原始左右图，输出校正后的左右图；
- 提供 `draw_epipolar_lines(image_pair)` 工具函数，用于横向拼接左右图并画水平线。

脚本：`scripts/04_test_rectification.py`

功能：

- 读取相机实时图或离线图；
- 进行双目校正；
- 拼接左右图；
- 画水平线；
- 人工检查同一个圆点是否在同一水平线上。

验收标准：

```text
同一个物理圆点在左右校正图中的 v 坐标差应尽量小，最好 < 1~2 px。
```

---

## 8.4 圆点检测模块

文件：`src/detection/circle_detector.py`

请实现类：

```python
class CircleDetector:
    def __init__(
        self,
        min_area: float = 20,
        max_area: float = 5000,
        min_circularity: float = 0.60,
        gaussian_kernel: int = 5,
        binary_inverse: bool = True,
    ):
        ...

    def detect(self, gray_img: np.ndarray) -> list[Circle2D]:
        ...
```

圆点检测流程：

1. 输入灰度图；
2. 高斯滤波：

```python
blur = cv2.GaussianBlur(gray_img, (k, k), 0)
```

3. Otsu 二值化：

```python
_, binary = cv2.threshold(
    blur, 0, 255,
    cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
)
```

4. 找轮廓：

```python
contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
```

5. 用面积筛选；
6. 用圆度筛选：

```python
circularity = 4 * np.pi * area / (perimeter * perimeter)
```

7. 用图像矩计算中心：

```python
cx = M["m10"] / M["m00"]
cy = M["m01"] / M["m00"]
```

8. 返回 `Circle2D` 列表，按 `v` 再按 `u` 排序。

还要提供：

```python
def draw_circles(img: np.ndarray, circles: list[Circle2D], color=(0,255,0)) -> np.ndarray:
    ...
```

脚本：`scripts/05_test_circle_detection.py`

功能：

- 对实时图或离线图检测圆点；
- 在图像上画圆心和序号；
- 打印检测到的圆点数、面积、圆度；
- 支持调参。

验收标准：

```text
画面中只有一个 9 点靶标时，应稳定检测出 9 个圆点。
```

---

## 8.5 左右圆点匹配模块

文件：`src/stereo/stereo_matcher.py`

请实现类：

```python
class StereoPointMatcher:
    def __init__(
        self,
        y_threshold_px: float = 2.5,
        min_disparity_px: float = 1.0,
        max_disparity_px: float = 250.0,
        uniqueness_check: bool = True,
    ):
        ...

    def match(self, left_circles: list[Circle2D], right_circles: list[Circle2D]) -> list[StereoMatch]:
        ...
```

匹配逻辑：

1. 对每个左图点 `(uL, vL)`，遍历所有右图点 `(uR, vR)`；
2. 计算：

```python
dy = abs(vL - vR)
disparity = uL - uR
```

3. 只保留满足：

```python
dy <= y_threshold_px
min_disparity_px <= disparity <= max_disparity_px
```

4. 匹配评分：

```python
score = dy + 0.01 * abs(disparity)
```

5. 选择 score 最小者；
6. 若 `uniqueness_check=True`，确保一个右图点最多只能被匹配一次；若冲突，保留 score 更小的匹配。

还要提供可视化：

```python
def draw_matches(left_img, right_img, left_circles, right_circles, matches) -> np.ndarray:
    """横向拼接左右图，并画匹配线。"""
```

脚本：`scripts/06_test_stereo_matching.py`

功能：

- 检测左右圆点；
- 执行匹配；
- 显示匹配线；
- 打印匹配数量和每对点的视差。

验收标准：

```text
单个 9 点靶标时，应匹配出 8~9 对点；匹配线应大致水平，不应明显交叉混乱。
```

---

## 8.6 三角化模块

文件：`src/stereo/triangulator.py`

请实现类：

```python
class StereoTriangulator:
    def __init__(self, P1: np.ndarray, P2: np.ndarray):
        ...

    def triangulate(self, matches: list[StereoMatch]) -> np.ndarray:
        """返回 shape = (N, 3) 的三维点，单位 m，坐标系为校正后的左相机坐标系。"""
        ...
```

使用 OpenCV：

```python
points_4d = cv2.triangulatePoints(P1, P2, pts_left.T, pts_right.T)
points_3d = (points_4d[:3] / points_4d[3]).T
```

要求：

- 对无效点进行过滤，例如 `Z <= 0` 的点丢弃；
- 可选过滤极端深度，例如 `Z > 5m` 可认为异常，参数可配置；
- 返回 `np.ndarray`。

另提供简单公式版本用于调试：

```python
def triangulate_by_disparity(matches, P1, P2) -> np.ndarray:
    ...
```

脚本：`scripts/07_test_triangulation.py`

功能：

- 完成从图像到 3D 点的完整流程；
- 打印每个 3D 点坐标；
- 计算 3D 点之间的距离；
- 显示 3D 散点图。

验收标准：

```text
靶标在相机前方时，所有点 Z 应为正；
靶标前后移动时，Z 应随距离变化；
同一靶标上点云应大致共面。
```

---

## 8.7 靶标聚类模块

文件：`src/target/target_cluster.py`

前期可以简化：如果点数不多，默认所有点属于同一个靶标。

请实现：

```python
def cluster_targets(points_3d: np.ndarray, eps_m: float = 0.08, min_samples: int = 4) -> list[np.ndarray]:
    ...
```

逻辑：

1. 如果点数小于等于 12，直接返回 `[points_3d]`；
2. 如果点数较多，使用 `sklearn.cluster.DBSCAN` 进行空间聚类；
3. 每个 cluster 返回一个 `np.ndarray`。

要求：

- 忽略 label = -1 的噪声点；
- 每个 cluster 至少有 `min_samples` 个点；
- 后续每个 cluster 交给位姿估计模块。

---

## 8.8 靶标中心和平面姿态估计模块

文件：`src/target/pose_estimator.py`

请实现：

```python
def fit_plane_svd(points_3d: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """
    返回 center, normal, rmse
    center: 点云中心
    normal: 平面法向量，单位向量
    rmse: 点到平面的均方根误差
    """
    ...
```

SVD 逻辑：

```python
center = np.mean(points_3d, axis=0)
centered = points_3d - center
U, S, Vt = np.linalg.svd(centered)
normal = Vt[-1]
normal = normal / np.linalg.norm(normal)
distances = centered @ normal
rmse = np.sqrt(np.mean(distances ** 2))
```

请实现完整姿态估计：

```python
def estimate_target_pose(points_3d: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    返回 position, quaternion, quality
    quaternion 顺序为 [qx, qy, qz, qw]
    """
    ...
```

姿态估计逻辑：

1. 用点云均值作为 position；
2. 用 SVD 得到平面内两个主方向和法向：

```python
x_axis = Vt[0]
y_axis = Vt[1]
z_axis = np.cross(x_axis, y_axis)
```

3. 保证轴归一化；
4. 组装旋转矩阵：

```python
R = np.column_stack([x_axis, y_axis, z_axis])
```

5. 如果 `det(R) < 0`，修正一个轴；
6. 使用 `scipy.spatial.transform.Rotation.from_matrix(R).as_quat()` 转成四元数；
7. 返回质量指标：

```python
quality = {
    "num_points": int(N),
    "plane_rmse_m": float(rmse),
    "confidence": float(confidence)
}
```

confidence 建议简单定义：

```python
confidence = max(0.0, min(1.0, 1.0 - rmse / max_plane_rmse_m))
```

注意：

- 前期姿态可能存在 180° 翻转问题，这是正常的；
- 对控制来说，前期可以优先使用 position；
- 姿态后续可结合靶标点的排序/编码进一步稳定。

---

## 8.9 靶标 ID 识别模块，后续可选

文件：`src/target/target_identifier.py`

前期实现占位即可：

```python
class TargetIdentifier:
    def __init__(self, config_path: str):
        ...

    def identify(self, points_3d: np.ndarray) -> tuple[str, float]:
        return "unknown", 0.0
```

后续扩展路线：

1. 用位姿估计得到靶标局部坐标系；
2. 将 3D 点投影到靶标平面；
3. 归一化 2D 点布局；
4. 与 `target_config.yaml` 中模板比较；
5. 返回误差最小的 target_id 和识别置信度。

---

## 8.10 JSON 输出模块

文件：`src/interface/json_publisher.py`

请实现：

```python
class JsonResultPublisher:
    def __init__(self, output_dir: str, save_json: bool = True, print_json: bool = True):
        ...

    def publish(self, result: TargetPoseResult) -> None:
        ...
```

功能：

- 将结果打印到控制台；
- 可选保存为文件：

```text
data/output/json/target_pose_YYYYMMDD_HHMMSS_mmm.json
```

---

## 8.11 命令接口预留模块

文件：`src/interface/command_schema.py`

请定义命令结构：

```python
@dataclass
class RobotCommand:
    timestamp: float
    command_type: str
    target_id: str
    target_pose: dict
    frame_id: str
    extra: dict
```

支持命令类型：

```text
move_to_target
approach_target
grasp_target
release_target
stop
```

输出 JSON 示例：

```json
{
  "timestamp": 1720000000.123,
  "command_type": "move_to_target",
  "target_id": "target_001",
  "frame_id": "camera_left",
  "target_pose": {
    "position": [0.035, -0.012, 0.420],
    "orientation": [0.01, 0.02, 0.03, 0.99]
  },
  "extra": {
    "speed_level": "slow",
    "safety_check": true
  }
}
```

文件：`src/interface/dummy_control_client.py`

先实现一个假控制接口：

```python
class DummyControlClient:
    def send_command(self, command: RobotCommand) -> None:
        print("[DUMMY CONTROL]", command)
```

后续可以替换成：

- Socket；
- HTTP；
- Serial；
- ROS2 topic；
- 直接调用控制同学提供的 Python API。

---

## 8.12 简单实时主流程

文件：`scripts/08_run_realtime_pipeline.py`

请实现完整实时流程：

```text
1. 读取 runtime_config.yaml
2. 读取 stereo_params.yaml
3. 初始化 D405StereoCamera
4. 初始化 StereoRectifier
5. 初始化 CircleDetector
6. 初始化 StereoPointMatcher
7. 初始化 StereoTriangulator
8. 初始化 TargetIdentifier 和 JsonResultPublisher
9. while True:
     读取左右图
     校正左右图
     检测圆点
     匹配左右点
     三角化得到 3D 点
     聚类为靶标
     对每个靶标估计 position + orientation
     输出 JSON
     显示图像和匹配结果
     按 ESC 退出
```

实时显示界面至少包括：

- 左校正图，画出圆点中心；
- 右校正图，画出圆点中心；
- 左右拼接图，画匹配线；
- 控制台打印靶标中心坐标和质量指标。

---

## 8.13 离线图像主流程

文件：`scripts/09_run_offline_pair.py`

支持命令行参数：

```bash
python scripts/09_run_offline_pair.py --left data/test_images/left/left_000.png --right data/test_images/right/right_000.png
```

功能：

- 对一对离线左右图运行完整流程；
- 保存检测可视化图片到 `data/output/images`；
- 保存 JSON 到 `data/output/json`；
- 打印结果。

---

## 9. main.py

项目根目录下 `main.py` 作为统一入口。

建议支持：

```bash
python main.py --mode realtime
python main.py --mode offline --left xxx.png --right yyy.png
python main.py --mode show_camera
python main.py --mode save_intrinsics
```

参数说明：

```text
--mode realtime         实时运行完整流程
--mode offline          对离线图片运行完整流程
--mode show_camera      只显示 D405 左右图
--mode save_intrinsics  读取并保存 D405 参数
```

---

## 10. README.md 内容要求

请生成 README，至少包含：

1. 项目简介；
2. 环境安装；
3. 目录结构；
4. D405 连接检查；
5. 保存 D405 标定参数；
6. 实时运行；
7. 离线图片运行；
8. 输出 JSON 字段说明；
9. 常见问题；
10. 后续如何接 UI 和机器人控制。

README 中给出命令：

```bash
pip install -r requirements.txt
python main.py --mode show_camera
python main.py --mode save_intrinsics
python main.py --mode realtime
python main.py --mode offline --left data/test_images/left/left_000.png --right data/test_images/right/right_000.png
```

---

## 11. 精度验证功能

请在 `scripts/07_test_triangulation.py` 中增加一些验证输出：

### 11.1 点间距验证

如果有多个 3D 点，计算所有点对距离：

```python
for i in range(N):
    for j in range(i + 1, N):
        dist = np.linalg.norm(points_3d[i] - points_3d[j])
```

打印最小距离、最大距离、平均距离。

### 11.2 平面拟合验证

输出：

```text
plane_rmse_m = xxx
```

如果 `plane_rmse_m > max_plane_rmse_m`，给出 warning。

### 11.3 深度稳定性

实时运行时可对最近若干帧中心位置做滑动平均：

```python
center_smooth = (1 - alpha) * center_last + alpha * center_now
```

要求写一个简单类：

```python
class PoseSmoother:
    def __init__(self, alpha=0.2):
        ...

    def update(self, position, quaternion):
        ...
```

前期可以只平滑 position。

---

## 12. 错误处理要求

代码必须对以下情况进行处理：

1. 没有检测到圆点；
2. 左图检测到圆点，右图没检测到；
3. 匹配数量小于 3；
4. 三角化后没有有效 3D 点；
5. 点数不足以拟合平面；
6. D405 没连接；
7. `stereo_params.yaml` 不存在；
8. 配置文件字段缺失。

遇到错误时不要直接崩溃，应打印清晰提示。例如：

```text
[WARN] No circles detected in right image.
[WARN] Only 2 stereo matches found, skip triangulation.
[ERROR] Cannot open D405 camera. Please check USB connection.
```

---

## 13. 单元测试要求

请至少写以下测试：

### 13.1 test_geometry.py

测试：

- 向量归一化；
- 旋转矩阵是否合法；
- 点到平面距离计算。

### 13.2 test_stereo_matcher.py

构造简单左右点：

```python
left = [(100, 50), (200, 50), (300, 80)]
right = [(90, 50.5), (190, 50.2), (290, 80.1)]
```

应该匹配出 3 对。

### 13.3 test_pose_estimator.py

构造一个平面上的 9 个点：

```python
z = 0.5
points = [[x, y, z] for x in [-0.04, 0, 0.04] for y in [-0.04, 0, 0.04]]
```

要求：

- center 约等于 `[0, 0, 0.5]`；
- plane_rmse 接近 0；
- quaternion 非空。

---

## 14. 关键算法公式说明

### 14.1 双目视差深度公式

校正后的双目图像中，同一个点的视差为：

```text
d = u_left - u_right
```

深度：

```text
Z = f * B / d
```

其中：

```text
f: 焦距，单位 px
B: 左右相机基线，单位 m
d: 视差，单位 px
Z: 深度，单位 m
```

三维坐标：

```text
X = (u_left - cx) * Z / f
Y = (v_left - cy) * Z / f
Z = f * B / d
```

实际代码优先使用 `cv2.triangulatePoints(P1, P2, ...)`。

### 14.2 平面拟合

给定点云 `points_3d`，中心：

```python
center = np.mean(points_3d, axis=0)
```

去中心化：

```python
centered = points_3d - center
```

SVD：

```python
U, S, Vt = np.linalg.svd(centered)
```

法向量：

```python
normal = Vt[-1]
```

点到平面距离：

```python
distances = centered @ normal
rmse = np.sqrt(np.mean(distances ** 2))
```

---

## 15. UI 接入建议，后续扩展

前期可以先用 OpenCV 窗口显示。后续如果做 UI，建议使用 PyQt5 / PySide6。

UI 需要显示：

```text
左侧：实时相机图像
中间：检测圆点和匹配线
右侧：目标列表
下方：命令按钮
```

目标列表字段：

```text
target_id
x, y, z
距离
检测点数
置信度
状态：可选 / 不可靠 / 丢失
```

按钮：

```text
选择目标
移动到目标
靠近目标
抓取目标
释放目标
急停
```

UI 点击按钮后生成 `RobotCommand`，先发给 `DummyControlClient`，后续替换真实控制接口。

---

## 16. 未来 ROS2 接口预留

虽然 Windows 上位机前期不强制 ROS2，但请在设计上预留 ROS2 适配。

未来可发布话题：

```text
/target_pose          geometry_msgs/PoseStamped
/target_points        sensor_msgs/PointCloud2 或自定义消息
/robot_command        自定义命令消息或 std_msgs/String JSON
```

前期可以先用 JSON 字符串模拟：

```json
{
  "topic": "/target_pose",
  "msg_type": "PoseStamped",
  "data": {
    "frame_id": "camera_left",
    "position": [0.1, 0.0, 0.5],
    "orientation": [0, 0, 0, 1]
  }
}
```

---

## 17. 开发优先级

请严格按以下顺序开发，不要先写复杂 UI：

### 第一阶段：跑通相机和参数

1. `01_show_d405_stereo.py`
2. `02_save_d405_intrinsics.py`
3. `stereo_params.yaml`

验收：能看到左右图，能保存内参外参。

### 第二阶段：跑通离线图像算法

1. 保存一对左右图；
2. `04_test_rectification.py`
3. `05_test_circle_detection.py`
4. `06_test_stereo_matching.py`
5. `07_test_triangulation.py`

验收：能从一对图片输出 3D 点。

### 第三阶段：跑通实时 pipeline

1. `08_run_realtime_pipeline.py`
2. 实时输出靶标中心坐标；
3. 实时显示匹配线；
4. 保存 JSON。

验收：移动靶标时，输出坐标随之变化。

### 第四阶段：位姿估计和 UI/命令接口

1. 平面拟合；
2. 粗略姿态；
3. JSON 标准输出；
4. Dummy 命令发布。

验收：可以选定一个目标并生成 `move_to_target` 命令。

---

## 18. 需要特别注意的问题

### 18.1 PnP 和双目三角化不要混淆

前期流程是：

```text
左右图像 2D 点 + 双目标定参数 → 三角化 → 3D 点
```

不是：

```text
已知靶标 3D 模板点 + 单目图像 2D 点 → PnP → 位姿
```

PnP 可以作为后续增强，但不是当前第一步。

### 18.2 左右匹配是关键

如果左右点匹配错，3D 点会严重错误。必须画匹配线人工检查。

### 18.3 单位统一

全部使用米 m，不要混用 mm。

### 18.4 姿态前期可能不稳定

只靠无序 9 点做 SVD 姿态，可能存在方向翻转。前期控制优先用 position，姿态后续结合点排序/编码模板稳定。

### 18.5 D405 深度图可作为辅助验证

虽然本项目正式路线是左右图三角化，但 D405 自带深度图可以用于对比验证。后续可以加一个辅助模块，比较：

```text
双目三角化 Z
D405 depth Z
尺子测量真实 Z
```

---

## 19. 预期终端输出示例

实时运行时，控制台输出类似：

```text
[INFO] D405 started: 848x480@30
[INFO] Stereo params loaded from config/stereo_params.yaml
[INFO] Rectifier initialized.
[FRAME 1024]
  left circles: 9
  right circles: 9
  stereo matches: 9
  valid 3d points: 9
  target center camera_left: x=0.034 m, y=-0.011 m, z=0.421 m
  plane_rmse: 0.0018 m
  confidence: 0.91
```

如果失败：

```text
[WARN] left circles: 9, right circles: 3
[WARN] only 2 stereo matches found, skip pose estimation.
```

---

## 20. 最终交付物

请生成完整项目，至少包括：

1. 可运行代码；
2. `requirements.txt`；
3. `README.md`；
4. 配置文件模板；
5. 实时运行脚本；
6. 离线调试脚本；
7. JSON 输出示例；
8. 基础单元测试。

最终我希望可以执行：

```bash
pip install -r requirements.txt
python main.py --mode show_camera
python main.py --mode save_intrinsics
python main.py --mode realtime
```

在没有相机时，也能执行：

```bash
python main.py --mode offline --left data/test_images/left/left_000.png --right data/test_images/right/right_000.png
```

并得到：

```text
检测可视化图片
匹配线图片
3D 点输出
靶标中心坐标
JSON 文件
```

---

## 21. 给 Codex 的实现方式建议

请你先生成项目框架和核心模块，不要一次性写出难以调试的大段代码。建议分批完成：

1. 先创建目录、配置文件、README、requirements；
2. 实现 D405 取图和内参读取；
3. 实现配置读写和 StereoParams；
4. 实现双目校正；
5. 实现圆点检测；
6. 实现左右匹配；
7. 实现三角化；
8. 实现位姿估计；
9. 实现实时主流程；
10. 实现离线主流程和测试。

每一步都要保证可以单独运行。不要等所有代码写完才测试。

---

## 22. 本项目当前最小可行版本定义

如果时间紧，最小可行版本只需要完成：

```text
1. D405 左右红外图实时显示
2. D405 内参外参读取并保存 YAML
3. 左右图圆点检测
4. 左右点匹配
5. 三角化输出 3D 点
6. 输出靶标中心坐标
7. OpenCV 窗口显示检测结果
```

不用一开始完成：

```text
1. 复杂 UI
2. ROS2
3. 多靶标 ID 识别
4. 真实机器人控制
5. 高精度姿态控制
```

这些都作为后续扩展。

