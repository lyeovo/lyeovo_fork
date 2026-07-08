import cv2
import numpy as np

def draw_circles(gray_or_bgr, circles, color=(0, 255, 0)):
    img = cv2.cvtColor(gray_or_bgr, cv2.COLOR_GRAY2BGR) if gray_or_bgr.ndim == 2 else gray_or_bgr.copy()
    for i, c in enumerate(circles):
        center = (int(round(c.u)), int(round(c.v)))
        cv2.circle(img, center, max(2, int(round(c.radius_est))), color, 1)
        cv2.circle(img, center, 2, (0, 0, 255), -1)
        cv2.putText(img, str(i), (center[0] + 4, center[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return img

def draw_matches(left_img, right_img, left_circles, right_circles, matches):
    left = draw_circles(left_img, left_circles)
    right = draw_circles(right_img, right_circles)
    pair = np.hstack([left, right])
    offset = left.shape[1]
    for m in matches:
        cv2.line(pair, (int(m.u_left), int(m.v_left)), (int(m.u_right) + offset, int(m.v_right)), (255, 0, 0), 1)
    return pair
