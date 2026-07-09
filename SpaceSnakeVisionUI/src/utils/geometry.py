import math
from typing import Tuple

import cv2
import numpy as np


def rvec_to_euler(rvec: np.ndarray) -> Tuple[float, float, float]:
    rotation, _ = cv2.Rodrigues(rvec)
    sy = math.sqrt(rotation[0, 0] ** 2 + rotation[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        roll = math.atan2(rotation[2, 1], rotation[2, 2])
        pitch = math.atan2(-rotation[2, 0], sy)
        yaw = math.atan2(rotation[1, 0], rotation[0, 0])
    else:
        roll = math.atan2(-rotation[1, 2], rotation[1, 1])
        pitch = math.atan2(-rotation[2, 0], sy)
        yaw = 0.0
    return roll, pitch, yaw


def deproject_pixel(pixel: Tuple[int, int], depth_m: float, fx: float, fy: float, cx: float, cy: float) -> Tuple[float, float, float]:
    u, v = pixel
    x = (u - cx) * depth_m / fx
    y = (v - cy) * depth_m / fy
    return float(x), float(y), float(depth_m)
