import cv2
import numpy as np
from src.detection.circle_detector import CircleDetector
def test_detect_synthetic_dark_circle():
    img = np.full((120, 120), 255, dtype=np.uint8)
    cv2.circle(img, (60, 60), 12, 0, -1)
    circles = CircleDetector(min_area=50, max_area=1000, binary_inverse=True).detect(img)
    assert len(circles) == 1
    assert abs(circles[0].u - 60) < 1
    assert abs(circles[0].v - 60) < 1


def test_detect_bright_circles_inside_roi():
    img = np.zeros((160, 220), dtype=np.uint8)
    centers = [(80, 70), (120, 70), (80, 110), (120, 110)]
    for center in centers:
        cv2.circle(img, center, 6, 120, -1)

    detector = CircleDetector(
        min_area=30,
        max_area=300,
        min_circularity=0.75,
        gaussian_kernel=3,
        binary_inverse=False,
        threshold_mode="manual",
        threshold_value=35,
        use_roi=True,
        left_roi=[55, 45, 95, 95],
    )

    circles = detector.detect(img, side="left")

    assert len(circles) == 4
    assert [(round(c.u), round(c.v)) for c in circles] == centers
    assert detector.last_binary is not None
    assert detector.last_roi_image.shape == (95, 95)
