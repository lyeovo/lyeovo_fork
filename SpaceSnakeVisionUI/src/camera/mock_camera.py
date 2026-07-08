import math
import time

import cv2
import numpy as np

from .base_camera import BaseCamera, CameraFrame, CameraIntrinsics


class MockCamera(BaseCamera):
    name = "MockCamera"

    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.intrinsics = CameraIntrinsics(width=width, height=height, fx=610.0, fy=610.0, cx=width / 2, cy=height / 2)
        self.frame_idx = 0
        self.running = False

    def start(self) -> None:
        self.running = True

    def read(self) -> CameraFrame:
        self.frame_idx += 1
        h, w = self.intrinsics.height, self.intrinsics.width
        image = np.zeros((h, w, 3), dtype=np.uint8)
        image[:] = (16, 10, 5)
        for x in range(0, w, 40):
            cv2.line(image, (x, 0), (x, h), (48, 36, 18), 1)
        for y in range(0, h, 40):
            cv2.line(image, (0, y), (w, y), (48, 36, 18), 1)
        cv2.putText(image, "MOCK ORBITAL VISION FEED", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 229, 0), 2)

        centers = [(155, 145), (335, 225), (500, 320)]
        labels = ["PAYLOAD MODULE", "DOCKING PORT", "TOOL NODE"]
        marker_ids = [12, 23, 31]
        for i, (cx, cy) in enumerate(centers):
            drift = int(8 * math.sin(self.frame_idx * 0.06 + i))
            x, y = cx + drift, cy
            size = 58
            cv2.rectangle(image, (x - size, y - size), (x + size, y + size), (255, 229, 0), 2)
            cv2.line(image, (x - 12, y), (x + 12, y), (138, 234, 46), 1)
            cv2.line(image, (x, y - 12), (x, y + 12), (138, 234, 46), 1)
            cv2.putText(image, f"ID {marker_ids[i]} {labels[i]}", (x - size, y - size - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 246, 234), 1)
            cv2.circle(image, (x, y), 4, (90, 77, 255), -1)

        depth = np.full((h, w), 0.65, dtype=np.float32)
        depth += np.linspace(0.0, 0.12, w, dtype=np.float32)[None, :]
        return CameraFrame(image, depth, None, self.intrinsics, time.time())

    def stop(self) -> None:
        self.running = False
