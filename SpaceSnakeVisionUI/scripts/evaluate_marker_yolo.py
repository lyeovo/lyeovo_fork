from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate marker-target YOLO model against local YOLO labels.")
    parser.add_argument("--model", required=True, help="Path to trained YOLO .pt model, e.g. models/marker_targets_best.pt")
    parser.add_argument("--data", default="datasets/marker_targets/marker_targets.yaml", help="YOLO data yaml.")
    parser.add_argument("--split", choices=["train", "val"], default="val")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--iou", type=float, default=0.50, help="IoU threshold for TP matching.")
    parser.add_argument("--min-precision", type=float, default=0.90)
    parser.add_argument("--min-recall", type=float, default=0.90)
    parser.add_argument("--min-mean-iou", type=float, default=0.75)
    parser.add_argument("--save-vis", action="store_true", help="Save prediction visualizations.")
    parser.add_argument("--out-dir", default="runs/marker_eval", help="Evaluation output directory.")
    return parser.parse_args()


def load_dataset(data_yaml: Path, split: str):
    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    dataset_root = Path(data.get("path", data_yaml.parent))
    if not dataset_root.is_absolute():
        dataset_root = (data_yaml.parent / dataset_root).resolve() if not (ROOT / dataset_root).exists() else (ROOT / dataset_root).resolve()
    image_rel = data.get(split, f"images/{split}")
    image_dir = (dataset_root / image_rel).resolve()
    label_dir = (dataset_root / "labels" / split).resolve()
    names = data.get("names", {})
    names = {int(k): str(v) for k, v in names.items()} if isinstance(names, dict) else {i: str(v) for i, v in enumerate(names)}
    return image_dir, label_dir, names


def read_yolo_labels(label_path: Path, image_shape):
    height, width = image_shape[:2]
    boxes = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        cls, cx, cy, bw, bh = parts
        cls = int(float(cls))
        cx, cy, bw, bh = map(float, (cx, cy, bw, bh))
        x1 = (cx - bw / 2.0) * width
        y1 = (cy - bh / 2.0) * height
        x2 = (cx + bw / 2.0) * width
        y2 = (cy + bh / 2.0) * height
        boxes.append({"class_id": cls, "bbox": [x1, y1, x2, y2]})
    return boxes


def iou_xyxy(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def predict(model, image, conf):
    result = model.predict(image, conf=conf, verbose=False)[0]
    boxes = getattr(result, "boxes", None)
    preds = []
    if boxes is None:
        return preds
    for box in boxes:
        preds.append(
            {
                "class_id": int(box.cls[0].detach().cpu().item()) if box.cls is not None else -1,
                "conf": float(box.conf[0].detach().cpu().item()) if box.conf is not None else 0.0,
                "bbox": box.xyxy[0].detach().cpu().numpy().astype(float).tolist(),
            }
        )
    preds.sort(key=lambda item: item["conf"], reverse=True)
    return preds


def match_predictions(labels, preds, iou_threshold):
    used_labels = set()
    matches = []
    false_pos = []
    for pred in preds:
        best_idx = None
        best_iou = 0.0
        for idx, label in enumerate(labels):
            if idx in used_labels or pred["class_id"] != label["class_id"]:
                continue
            score = iou_xyxy(pred["bbox"], label["bbox"])
            if score > best_iou:
                best_idx = idx
                best_iou = score
        if best_idx is not None and best_iou >= iou_threshold:
            used_labels.add(best_idx)
            matches.append((pred, labels[best_idx], best_iou))
        else:
            false_pos.append(pred)
    false_neg = [label for idx, label in enumerate(labels) if idx not in used_labels]
    return matches, false_pos, false_neg


def draw_vis(image, labels, preds, matches, false_pos, false_neg, out_path):
    vis = image.copy()
    for label in labels:
        x1, y1, x2, y2 = [int(round(v)) for v in label["bbox"]]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 180, 0), 2)
    for pred in false_pos:
        x1, y1, x2, y2 = [int(round(v)) for v in pred["bbox"]]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
    for label in false_neg:
        x1, y1, x2, y2 = [int(round(v)) for v in label["bbox"]]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 0, 0), 2)
    for pred, _, score in matches:
        x1, y1, x2, y2 = [int(round(v)) for v in pred["bbox"]]
        cv2.putText(vis, f"TP {score:.2f}", (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 0), 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), vis)


def main():
    args = parse_args()
    data_yaml = (ROOT / args.data).resolve()
    model_path = (ROOT / args.model).resolve()
    image_dir, label_dir, names = load_dataset(data_yaml, args.split)
    images = sorted([p for p in image_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS])
    if not images:
        raise SystemExit(f"No images found in {image_dir}")
    if not model_path.exists():
        raise SystemExit(f"Model file not found: {model_path}")

    from ultralytics import YOLO

    model = YOLO(str(model_path))
    out_dir = (ROOT / args.out_dir).resolve()
    total_labels = total_preds = true_pos = false_pos_count = false_neg_count = 0
    ious = []
    per_image = []
    per_class = {class_id: {"tp": 0, "fp": 0, "fn": 0} for class_id in names}

    for image_path in images:
        image = cv2.imread(str(image_path))
        if image is None:
            continue
        labels = read_yolo_labels(label_dir / f"{image_path.stem}.txt", image.shape)
        preds = predict(model, image, args.conf)
        matches, fps, fns = match_predictions(labels, preds, args.iou)
        total_labels += len(labels)
        total_preds += len(preds)
        true_pos += len(matches)
        false_pos_count += len(fps)
        false_neg_count += len(fns)
        ious.extend(score for _, _, score in matches)
        for pred, _, _ in matches:
            per_class.setdefault(pred["class_id"], {"tp": 0, "fp": 0, "fn": 0})["tp"] += 1
        for pred in fps:
            per_class.setdefault(pred["class_id"], {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1
        for label in fns:
            per_class.setdefault(label["class_id"], {"tp": 0, "fp": 0, "fn": 0})["fn"] += 1
        per_image.append(
            {
                "image": str(image_path.relative_to(ROOT)),
                "labels": len(labels),
                "predictions": len(preds),
                "tp": len(matches),
                "fp": len(fps),
                "fn": len(fns),
                "mean_iou": float(np.mean([score for _, _, score in matches])) if matches else 0.0,
            }
        )
        if args.save_vis:
            draw_vis(image, labels, preds, matches, fps, fns, out_dir / "vis" / image_path.name)

    precision = true_pos / (true_pos + false_pos_count) if true_pos + false_pos_count else 0.0
    recall = true_pos / (true_pos + false_neg_count) if true_pos + false_neg_count else 0.0
    mean_iou = float(np.mean(ious)) if ious else 0.0
    passed = precision >= args.min_precision and recall >= args.min_recall and mean_iou >= args.min_mean_iou
    summary = {
        "passed": passed,
        "split": args.split,
        "model": str(model_path),
        "images": len(images),
        "labels": total_labels,
        "predictions": total_preds,
        "tp": true_pos,
        "fp": false_pos_count,
        "fn": false_neg_count,
        "precision": precision,
        "recall": recall,
        "mean_iou": mean_iou,
        "thresholds": {
            "conf": args.conf,
            "iou": args.iou,
            "min_precision": args.min_precision,
            "min_recall": args.min_recall,
            "min_mean_iou": args.min_mean_iou,
        },
        "per_class": per_class,
        "per_image": per_image,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_image"}, ensure_ascii=False, indent=2))
    print(f"[INFO] Full report: {out_dir / 'summary.json'}")
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
