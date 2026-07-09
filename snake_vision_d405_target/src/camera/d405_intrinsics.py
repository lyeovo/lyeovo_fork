import numpy as np
from src.calibration.stereo_params import StereoParams

def _K(intr):
    return np.array([[intr.fx, 0.0, intr.ppx], [0.0, intr.fy, intr.ppy], [0.0, 0.0, 1.0]], dtype=float)

def read_d405_stereo_params(width=848, height=480, fps=30) -> StereoParams:
    try:
        import pyrealsense2 as rs
    except ImportError as e:
        raise RuntimeError("pyrealsense2 is not installed. Cannot read D405 intrinsics.") from e
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.infrared, 1, width, height, rs.format.y8, fps)
    config.enable_stream(rs.stream.infrared, 2, width, height, rs.format.y8, fps)
    try:
        profile = pipeline.start(config)
        left_profile = profile.get_stream(rs.stream.infrared, 1).as_video_stream_profile()
        right_profile = profile.get_stream(rs.stream.infrared, 2).as_video_stream_profile()
        left_intr = left_profile.get_intrinsics()
        right_intr = right_profile.get_intrinsics()
        extr = left_profile.get_extrinsics_to(right_profile)
        return StereoParams(width, height, _K(left_intr), np.array(left_intr.coeffs, dtype=float), _K(right_intr), np.array(right_intr.coeffs, dtype=float), np.array(extr.rotation, dtype=float).reshape(3, 3), np.array(extr.translation, dtype=float).reshape(3, 1))
    finally:
        pipeline.stop()
