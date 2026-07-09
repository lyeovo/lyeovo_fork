from pathlib import Path

from .bridge.file_bridge import FileBridge
from .bridge.ros2_bridge_optional import ROS2BridgeOptional
from .camera.mock_camera import MockCamera
from .camera.realsense_d405 import RealSenseD405Camera
from .ui.main_window import MainWindow


def create_main_window(
    project_root: Path,
    camera_mode: str,
    bridge_mode: str,
    detector_mode: str = "yolo",
    yolo_model: str = "yolo11n.pt",
    yolo_conf: float = 0.35,
) -> MainWindow:
    if camera_mode == "d405":
        stream_mode = "infrared" if detector_mode == "marker" else "hybrid" if detector_mode == "yolo_marker" else "color"
        camera = RealSenseD405Camera(stream_mode=stream_mode)
    else:
        camera = MockCamera()

    if bridge_mode == "ros2":
        try:
            bridge = ROS2BridgeOptional()
            bridge_status = "ROS2 MODE"
        except Exception as exc:
            bridge = FileBridge(project_root / "data" / "outbox", project_root / "data" / "inbox")
            bridge_status = f"ROS2 UNAVAILABLE -> FILE MODE ({exc})"
    elif bridge_mode != "file":
        bridge = FileBridge(project_root / "data" / "outbox", project_root / "data" / "inbox")
        bridge_status = f"{bridge_mode.upper()} PLACEHOLDER -> FILE MODE"
    else:
        bridge = FileBridge(project_root / "data" / "outbox", project_root / "data" / "inbox")
        bridge_status = "FILE MODE"

    return MainWindow(
        camera=camera,
        bridge=bridge,
        bridge_status=bridge_status,
        project_root=project_root,
        detector_mode=detector_mode,
        yolo_model=yolo_model,
        yolo_conf=yolo_conf,
    )
