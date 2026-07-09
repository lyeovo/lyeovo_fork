import numpy as np

class D405StereoCamera:
    def __init__(self, width=848, height=480, fps=30, left_index=1, right_index=2):
        self.width, self.height, self.fps = width, height, fps
        self.left_index, self.right_index = left_index, right_index
        self.pipeline = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()

    def start(self):
        try:
            import pyrealsense2 as rs
        except ImportError as e:
            raise RuntimeError("pyrealsense2 is not installed. Install it or use offline mode.") from e
        self.rs = rs
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.infrared, self.left_index, self.width, self.height, rs.format.y8, self.fps)
        config.enable_stream(rs.stream.infrared, self.right_index, self.width, self.height, rs.format.y8, self.fps)
        try:
            self.pipeline.start(config)
        except Exception as e:
            raise RuntimeError("Cannot open D405 camera. Please check USB connection and RealSense driver.") from e

    def get_frames(self):
        if self.pipeline is None:
            raise RuntimeError("D405 camera is not started")
        frames = self.pipeline.wait_for_frames()
        left = frames.get_infrared_frame(self.left_index)
        right = frames.get_infrared_frame(self.right_index)
        if not left or not right:
            raise RuntimeError("Failed to read left/right infrared frames from D405")
        return np.asanyarray(left.get_data()), np.asanyarray(right.get_data())

    def stop(self):
        if self.pipeline is not None:
            self.pipeline.stop()
            self.pipeline = None
