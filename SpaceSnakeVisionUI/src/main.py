import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .app import create_main_window


def ensure_data_dirs(root: Path) -> None:
    for rel in ("data/outbox", "data/inbox", "data/logs", "data/recordings", "data/samples"):
        (root / rel).mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SpaceSnakeVisionUI")
    parser.add_argument("--camera", choices=["mock", "d405"], default="mock")
    parser.add_argument("--bridge", choices=["file", "websocket", "ros2"], default="file")
    parser.add_argument("--detector", choices=["auto", "yolo", "aruco", "mock", "marker", "yolo_marker"], default="yolo_marker")
    parser.add_argument("--yolo-model", default="models/marker_targets_best.pt", help="YOLO model path or model name, for example models/marker_targets_best.pt")
    parser.add_argument("--yolo-conf", type=float, default=0.35, help="YOLO confidence threshold")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    ensure_data_dirs(project_root)
    app = QApplication(sys.argv)
    window = create_main_window(
        project_root=project_root,
        camera_mode=args.camera,
        bridge_mode=args.bridge,
        detector_mode=args.detector,
        yolo_model=args.yolo_model,
        yolo_conf=args.yolo_conf,
    )
    window.show()
    return app.exec()
