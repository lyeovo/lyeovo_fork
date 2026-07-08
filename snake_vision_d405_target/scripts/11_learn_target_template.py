import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.detection.circle_detector import CircleDetector
from src.target.template_database import TargetTemplateDatabase
from src.target.template_learner import (
    LearnedFrame,
    fuse_frames,
    learn_frame,
    points_3d_from_dots,
    save_learning_debug,
)
from src.utils.config_io import load_yaml


def parse_args():
    parser = argparse.ArgumentParser(description="Learn one encoded dot target template from D405 depth.")
    parser.add_argument("--target-id", required=True, help="Target id, for example target_1.")
    parser.add_argument("--num-frames", type=int, default=30, help="Number of valid frames to collect.")
    parser.add_argument("--min-dots", type=int, default=6, help="Minimum valid 3D dots per frame.")
    parser.add_argument("--save-debug", action="store_true", help="Save debug images and learning_summary.json.")
    parser.add_argument("--config", default="config/runtime_config.yaml", help="Runtime config path.")
    parser.add_argument("--database", default="config/target_database.yaml", help="Target database path.")
    return parser.parse_args()


def start_d405_depth_camera(camera_cfg):
    try:
        import pyrealsense2 as rs
    except ImportError as exc:
        raise RuntimeError("pyrealsense2 is not installed. Please install it before learning from D405 depth.") from exc
    pipeline = rs.pipeline()
    config = rs.config()
    width = int(camera_cfg.get("width", 848))
    height = int(camera_cfg.get("height", 480))
    fps = int(camera_cfg.get("fps", 30))
    left_index = int(camera_cfg.get("infrared_left_index", 1))
    config.enable_stream(rs.stream.infrared, left_index, width, height, rs.format.y8, fps)
    config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
    profile = pipeline.start(config)
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = float(depth_sensor.get_depth_scale())
    ir_profile = profile.get_stream(rs.stream.infrared, left_index).as_video_stream_profile()
    intrinsics = ir_profile.get_intrinsics()
    align = rs.align(rs.stream.infrared)
    return pipeline, align, intrinsics, depth_scale


def main():
    args = parse_args()
    cfg = load_yaml(args.config)
    learning_cfg = cfg.get("target_learning", {})
    depth_cfg = cfg.get("depth", {})
    detector = CircleDetector.from_config(cfg)
    debug_dir = Path("data/output/template_learning") / args.target_id
    frames = []
    requested_frames = int(args.num_frames or learning_cfg.get("num_frames", 30))
    min_dots = int(args.min_dots or learning_cfg.get("min_dots", 6))
    rejected_frames = 0
    pipeline, align, intrinsics, depth_scale = start_d405_depth_camera(cfg.get("camera", {}))
    print(f"[INFO] Learning {args.target_id}: collect {requested_frames} valid frames, min_dots={min_dots}")
    try:
        while len(frames) < requested_frames:
            frameset = align.process(pipeline.wait_for_frames())
            ir_frame = frameset.get_infrared_frame(int(cfg["camera"].get("infrared_left_index", 1)))
            depth_frame = frameset.get_depth_frame()
            if not ir_frame or not depth_frame:
                rejected_frames += 1
                continue
            ir_image = np.asanyarray(ir_frame.get_data())
            depth_image = np.asanyarray(depth_frame.get_data())
            dots = detector.detect(ir_image, side="left")
            if len(dots) < min_dots:
                rejected_frames += 1
                continue
            points_3d, valid_dots = points_3d_from_dots(
                dots,
                depth_image,
                intrinsics,
                window_size=int(learning_cfg.get("depth_window_size", 5)),
                depth_scale=depth_scale,
                min_depth_m=float(depth_cfg.get("min_depth_m", 0.10)),
                max_depth_m=float(depth_cfg.get("max_depth_m", 1.50)),
            )
            if len(points_3d) < min_dots:
                rejected_frames += 1
                continue
            local_2d, ordered_3d, plane_rmse = learn_frame(points_3d)
            if plane_rmse > float(learning_cfg.get("max_plane_rmse_m", 0.01)):
                rejected_frames += 1
                continue
            depth_ratio = len(points_3d) / float(max(len(dots), 1))
            frames.append(LearnedFrame(local_2d, ordered_3d, plane_rmse, depth_ratio))
            print(f"[INFO] accepted {len(frames)}/{requested_frames}: dots={len(dots)} valid_depth={len(points_3d)} plane_rmse={plane_rmse:.4f}m")
            if args.save_debug:
                save_learning_debug(debug_dir, len(frames), ir_image, dots, valid_dots, local_2d)
            time.sleep(0.02)
    finally:
        pipeline.stop()
    final_points, used_frames, fuse_rejected = fuse_frames(
        frames,
        max_frame_match_error_m=float(learning_cfg.get("max_frame_match_error_m", 0.02)),
    )
    rejected_frames += fuse_rejected
    db = TargetTemplateDatabase(args.database)
    entry = db.upsert_target(
        args.target_id,
        final_points,
        learned_frames=requested_frames,
        used_frames=len(used_frames),
        average_plane_rmse_m=float(np.mean([f.plane_rmse_m for f in used_frames])),
        average_depth_valid_ratio=float(np.mean([f.depth_valid_ratio for f in used_frames])),
    )
    summary = {
        "target_id": args.target_id,
        "requested_frames": requested_frames,
        "used_frames": len(used_frames),
        "rejected_frames": rejected_frames,
        "num_points": int(len(final_points)),
        "average_plane_rmse_m": entry["average_plane_rmse_m"],
        "average_depth_valid_ratio": entry["average_depth_valid_ratio"],
        "final_template_points": entry["template_points"],
        "created_at": entry["created_at"],
    }
    if args.save_debug:
        debug_dir.mkdir(parents=True, exist_ok=True)
        with (debug_dir / "learning_summary.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[INFO] Updated database: {Path(args.database)}")


if __name__ == "__main__":
    main()
