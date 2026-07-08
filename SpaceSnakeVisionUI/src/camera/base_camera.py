from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class CameraIntrinsics:
    width: int = 640
    height: int = 480
    fx: float = 600.0
    fy: float = 600.0
    cx: float = 320.0
    cy: float = 240.0
    coeffs: tuple = (0.0, 0.0, 0.0, 0.0, 0.0)

    def camera_matrix(self) -> np.ndarray:
        return np.array([[self.fx, 0, self.cx], [0, self.fy, self.cy], [0, 0, 1]], dtype=np.float32)

    def dist_coeffs(self) -> np.ndarray:
        return np.array(self.coeffs, dtype=np.float32)


@dataclass
class CameraFrame:
    color_image: np.ndarray
    depth_image: Optional[np.ndarray]
    depth_colormap: Optional[np.ndarray]
    intrinsics: CameraIntrinsics
    timestamp: float
    infrared_image: Optional[np.ndarray] = None


class BaseCamera:
    name = "BaseCamera"

    def start(self) -> None:
        raise NotImplementedError

    def read(self) -> CameraFrame:
        raise NotImplementedError

    def stop(self) -> None:
        pass


def now_frame(color: np.ndarray, depth: Optional[np.ndarray], intrinsics: CameraIntrinsics) -> CameraFrame:
    return CameraFrame(color, depth, None, intrinsics, time.time())
