import time

import cv2
import numpy as np

from .base_camera import BaseCamera, CameraFrame, CameraIntrinsics
from .mock_camera import MockCamera


class RealSenseD405Camera(BaseCamera):
    name = "RealSenseD405Camera"

    def __init__(self, width: int = 848, height: int = 480, fps: int = 30, stream_mode: str = "color", infrared_index: int = 1) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.stream_mode = stream_mode
        self.infrared_index = infrared_index
        self.pipeline = None
        self.align = None
        self.intrinsics = CameraIntrinsics(width=width, height=height)
        self.fallback = MockCamera(width, height)
        self.using_mock = False

    def start(self) -> None:
        try:
            import pyrealsense2 as rs

            self.rs = rs
            self.pipeline = rs.pipeline()
            config = rs.config()
            if self.stream_mode == "infrared":
                config.enable_stream(rs.stream.infrared, self.infrared_index, self.width, self.height, rs.format.y8, self.fps)
            elif self.stream_mode == "hybrid":
                config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
                config.enable_stream(rs.stream.infrared, self.infrared_index, self.width, self.height, rs.format.y8, self.fps)
            else:
                config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
            config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)
            profile = self.pipeline.start(config)
            align_stream = rs.stream.infrared if self.stream_mode == "infrared" else rs.stream.color
            self.align = rs.align(align_stream)
            video_profile = profile.get_stream(rs.stream.infrared, self.infrared_index).as_video_stream_profile() if self.stream_mode == "infrared" else profile.get_stream(rs.stream.color).as_video_stream_profile()
            intr = video_profile.get_intrinsics()
            self.intrinsics = CameraIntrinsics(intr.width, intr.height, intr.fx, intr.fy, intr.ppx, intr.ppy, tuple(intr.coeffs))
        except Exception:
            self.using_mock = True
            self.fallback.start()

    def read(self) -> CameraFrame:
        if self.using_mock or self.pipeline is None:
            return self.fallback.read()
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=1000)
            aligned = self.align.process(frames) if self.align else frames
            color_frame = aligned.get_infrared_frame(self.infrared_index) if self.stream_mode == "infrared" else aligned.get_color_frame()
            infrared_frame = aligned.get_infrared_frame(self.infrared_index) if self.stream_mode in ("infrared", "hybrid") else None
            depth_frame = aligned.get_depth_frame()
            if not color_frame or not depth_frame:
                raise RuntimeError("RealSense frame unavailable")
            image = np.asanyarray(color_frame.get_data())
            color = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image
            infrared = np.asanyarray(infrared_frame.get_data()) if infrared_frame else None
            depth_raw = np.asanyarray(depth_frame.get_data()).astype(np.float32)
            depth = depth_raw * depth_frame.get_units()
            depth_vis = cv2.applyColorMap(cv2.convertScaleAbs(depth_raw, alpha=0.03), cv2.COLORMAP_JET)
            return CameraFrame(color, depth, depth_vis, self.intrinsics, time.time(), infrared)
        except Exception:
            self.using_mock = True
            self.fallback.start()
            return self.fallback.read()

    def stop(self) -> None:
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                pass
        self.fallback.stop()
