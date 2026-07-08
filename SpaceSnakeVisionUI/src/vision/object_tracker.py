class ObjectTracker:
    def __init__(self, max_missing_frames: int = 12, iou_threshold: float = 0.25) -> None:
        self.max_missing_frames = max_missing_frames
        self.iou_threshold = iou_threshold
        self._tracks = {}
        self._next_id = 1

    def update(self, detections):
        for track in self._tracks.values():
            track["missing"] += 1

        for obj in detections:
            if obj.target_id.startswith("ARUCO-") or obj.detection_mode in ("marker", "yolo_marker"):
                continue
            match_id = self._best_match(obj)
            if match_id is None:
                match_id = f"TGT-{self._next_id:03d}"
                self._next_id += 1
            obj.target_id = match_id
            self._tracks[match_id] = {"bbox": obj.bbox_xyxy, "class_name": obj.class_name, "missing": 0}

        self._tracks = {tid: data for tid, data in self._tracks.items() if data["missing"] <= self.max_missing_frames}
        return detections

    def _best_match(self, obj):
        best_id = None
        best_iou = 0.0
        for track_id, data in self._tracks.items():
            if data["class_name"] != obj.class_name:
                continue
            score = _iou(obj.bbox_xyxy, data["bbox"])
            if score > best_iou:
                best_id = track_id
                best_iou = score
        return best_id if best_iou >= self.iou_threshold else None


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0
