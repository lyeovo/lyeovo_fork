from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args():
    parser = argparse.ArgumentParser(description="Train marker-target YOLO model.")
    parser.add_argument("--model", default="yolo11n.pt", help="Base YOLO model, e.g. yolo11n.pt")
    parser.add_argument("--data", default="datasets/marker_targets/marker_targets.yaml")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--project", default="runs")
    parser.add_argument("--name", default="marker_targets")
    parser.add_argument("--device", default=None, help="Optional device, e.g. 0 or cpu.")
    return parser.parse_args()


def main():
    args = parse_args()
    data_path = ROOT / args.data
    if not data_path.exists():
        raise SystemExit(f"Data yaml not found: {data_path}")
    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise SystemExit(f"Cannot import ultralytics. Please install requirements first. Detail: {exc}") from exc
    print(
        "[INFO] Training:",
        f"model={args.model}",
        f"data={args.data}",
        f"epochs={args.epochs}",
        f"imgsz={args.imgsz}",
        f"batch={args.batch}",
        f"project={args.project}",
        f"name={args.name}",
    )
    model = YOLO(args.model)
    train_kwargs = {
        "data": args.data,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "project": args.project,
        "name": args.name,
    }
    if args.device:
        train_kwargs["device"] = args.device
    model.train(**train_kwargs)
    best = ROOT / args.project / "detect" / args.name / "weights" / "best.pt"
    print(f"[INFO] Training finished. Best model should be here: {best}")
    print("[INFO] Evaluate with:")
    print(f"  {sys.executable} scripts/evaluate_marker_yolo.py --model {best.relative_to(ROOT)} --save-vis")


if __name__ == "__main__":
    main()
