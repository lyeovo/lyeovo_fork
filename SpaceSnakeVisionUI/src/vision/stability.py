class StabilityChecker:
    def apply(self, detections):
        for obj in detections:
            if obj.detection_mode in ("marker", "yolo_marker") and obj.status in {"SEARCH", "BEARING_ONLY", "APPROACH", "PARTIAL_DEPTH", "POSE_6DOF", "LOST"}:
                continue
            if obj.depth_m is None:
                obj.status = "DEPTH_INVALID"
            elif obj.stability_score < 0.70:
                obj.status = "UNSTABLE"
        return detections
