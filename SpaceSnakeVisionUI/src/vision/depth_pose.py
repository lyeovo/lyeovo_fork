from typing import Optional, Tuple

import numpy as np

from ..camera.base_camera import CameraIntrinsics
from ..models import Euler, Pose3D, Vector3
from ..utils.geometry import deproject_pixel


def median_depth(depth_image: np.ndarray | None, center: Tuple[int, int], radius: int = 4) -> Optional[float]:
    if depth_image is None:
        return None
    u, v = center
    h, w = depth_image.shape[:2]
    patch = depth_image[max(0, v - radius) : min(h, v + radius + 1), max(0, u - radius) : min(w, u + radius + 1)]
    valid = patch[np.isfinite(patch) & (patch > 0.001)]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def pose_from_depth(depth_image: np.ndarray | None, center: Tuple[int, int], intr: CameraIntrinsics) -> tuple[Pose3D, Optional[float], str]:
    depth = median_depth(depth_image, center)
    if depth is None:
        return Pose3D(position=Vector3()), None, "DEPTH_INVALID"
    x, y, z = deproject_pixel(center, depth, intr.fx, intr.fy, intr.cx, intr.cy)
    return Pose3D(position=Vector3(x, y, z), orientation_euler=Euler()), depth, "AVAILABLE"
