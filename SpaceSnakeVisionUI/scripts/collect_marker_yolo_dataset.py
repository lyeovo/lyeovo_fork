from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.camera.realsense_d405 import RealSenseD405Camera


CLASS_TO_ID = {"201": 0, "222": 1, "207": 2, "target_1": 0, "target_2": 1, "target_3": 2}


def parse_args():
    parser = argparse.ArgumentParser(description="Collect YOLO marker-target images with automatic bbox labels.")
    parser.add_argument("--class-id", required=True, choices=sorted(CLASS_TO_ID.keys()), help="Marker class to save, e.g. 201, 222, 207.")
    parser.add_argument("--split", choices=["train", "val", "auto"], default="auto", help="Dataset split. auto sends every Nth sample to val.")
    parser.add_argument("--val-every", type=int, default=5, help="When --split auto, every Nth saved image goes to val.")
    parser.add_argument("--dataset-dir", default="datasets/marker_targets", help="YOLO dataset root.")
    parser.add_argument("--width", type=int, default=848)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--dark-threshold", type=int, default=85, help="V-channel threshold for black marker board.")
    parser.add_argument("--min-area-frac", type=float, default=0.002, help="Minimum bbox area as image-area fraction.")
    parser.add_argument("--max-area-frac", type=float, default=0.60, help="Maximum bbox area as image-area fraction.")
    parser.add_argument("--save-all", action="store_true", help="Save all detected marker boxes with the same class label.")
    return parser.parse_args()


def ensure_dirs(dataset_dir: Path):
    for split in ("train", "val"):
        (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)


def detect_black_marker_boxes(image, dark_threshold=85, min_area_frac=0.002, max_area_frac=0.60):
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    saturation = hsv[:, :, 1]
    dark_mask = (value < int(dark_threshold)).astype(np.uint8) * 255
    # Suppress very low-saturation background shadows less aggressively than the dark plate.
    dark_mask[(value > int(dark_threshold * 0.8)) & (saturation < 35)] = 0
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    image_area = float(width * height)
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        bbox_area = float(w * h)
        if bbox_area < min_area_frac * image_area or bbox_area > max_area_frac * image_area:
            continue
        aspect = w / float(h) if h else 0.0
        if aspect < 0.55 or aspect > 2.2:
            continue
        extent = area / bbox_area if bbox_area else 0.0
        if extent < 0.35:
            continue
        pad = max(4, int(0.03 * max(w, h)))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(width - 1, x + w + pad)
        y2 = min(height - 1, y + h + pad)
        boxes.append((x1, y1, x2, y2, bbox_area, extent))
    boxes.sort(key=lambda box: box[4], reverse=True)
    return boxes, mask


def yolo_line(class_index, bbox, image_shape):
    height, width = image_shape[:2]
    x1, y1, x2, y2 = bbox[:4]
    cx = ((x1 + x2) / 2.0) / width
    cy = ((y1 + y2) / 2.0) / height
    bw = (x2 - x1) / width
    bh = (y2 - y1) / height
    return f"{class_index} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def choose_split(split, saved_count, val_every):
    if split != "auto":
        return split
    return "val" if val_every > 0 and (saved_count + 1) % val_every == 0 else "train"


def draw_overlay(image, boxes, selected_index, class_name, saved_count):
    vis = image.copy()
    for idx, box in enumerate(boxes):
        x1, y1, x2, y2 = box[:4]
        color = (0, 0, 255) if idx == selected_index else (0, 180, 255)
        thickness = 3 if idx == selected_index else 2
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(vis, f"{idx + 1}:{class_name}", (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    info = "s: save  n/p: switch box  m: mask  q/ESC: quit"
    cv2.putText(vis, info, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    cv2.putText(vis, f"class={class_name} saved={saved_count}", (12, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    if not boxes:
        cv2.putText(vis, "No red bbox: adjust camera/light or dark-threshold", (12, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    return vis


def save_sample(frame_image, boxes, selected_index, args, saved_count):
    split = choose_split(args.split, saved_count, args.val_every)
    dataset_dir = ROOT / args.dataset_dir
    class_index = CLASS_TO_ID[args.class_id]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stem = f"marker_{args.class_id}_{split}_{stamp}_{saved_count + 1:04d}"
    image_path = dataset_dir / "images" / split / f"{stem}.jpg"
    label_path = dataset_dir / "labels" / split / f"{stem}.txt"
    if args.save_all:
        chosen = boxes
    else:
        chosen = [boxes[selected_index]]
    label_lines = [yolo_line(class_index, box, frame_image.shape) for box in chosen]
    cv2.imwrite(str(image_path), frame_image)
    label_path.write_text("\n".join(label_lines) + "\n", encoding="utf-8")
    return image_path, label_path, split, len(chosen)


def main():
    args = parse_args()
    dataset_dir = ROOT / args.dataset_dir
    ensure_dirs(dataset_dir)
    camera = RealSenseD405Camera(args.width, args.height, args.fps, stream_mode="color")
    camera.start()
    if getattr(camera, "using_mock", False):
        print("[WARN] D405 is unavailable; camera fell back to mock. Dataset images will not be useful.")
    print("[INFO] Point D405 at marker class", args.class_id)
    print("[INFO] Wait for a red bbox, press s to save image+YOLO label. Press q or ESC to quit.")
    saved_count = 0
    selected_index = 0
    show_mask = False
    try:
        while True:
            frame = camera.read()
            image = frame.color_image
            boxes, mask = detect_black_marker_boxes(
                image,
                args.dark_threshold,
                args.min_area_frac,
                args.max_area_frac,
            )
            if boxes:
                selected_index = max(0, min(selected_index, len(boxes) - 1))
            else:
                selected_index = 0
            vis = draw_overlay(image, boxes, selected_index, args.class_id, saved_count)
            cv2.imshow("collect marker YOLO dataset", mask if show_mask else vis)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("m"):
                show_mask = not show_mask
            elif key == ord("n") and boxes:
                selected_index = (selected_index + 1) % len(boxes)
            elif key == ord("p") and boxes:
                selected_index = (selected_index - 1) % len(boxes)
            elif key == ord("s"):
                if not boxes:
                    print("[WARN] No bbox detected; not saved.")
                    continue
                image_path, label_path, split, box_count = save_sample(image, boxes, selected_index, args, saved_count)
                saved_count += 1
                print(f"[SAVE] {split} boxes={box_count} image={image_path} label={label_path}")
    finally:
        camera.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
