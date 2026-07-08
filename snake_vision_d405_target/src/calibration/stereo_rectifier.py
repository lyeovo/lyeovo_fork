import cv2
import numpy as np

class StereoRectifier:
    def __init__(self, stereo_params, alpha=0.0):
        size = (stereo_params.image_width, stereo_params.image_height)
        self.R1, self.R2, self._P1, self._P2, self._Q, _, _ = cv2.stereoRectify(
            stereo_params.K_left, stereo_params.D_left, stereo_params.K_right, stereo_params.D_right,
            size, stereo_params.R, stereo_params.T, alpha=alpha)
        self.map1_l, self.map2_l = cv2.initUndistortRectifyMap(stereo_params.K_left, stereo_params.D_left, self.R1, self._P1, size, cv2.CV_16SC2)
        self.map1_r, self.map2_r = cv2.initUndistortRectifyMap(stereo_params.K_right, stereo_params.D_right, self.R2, self._P2, size, cv2.CV_16SC2)

    def rectify(self, left_img, right_img):
        return cv2.remap(left_img, self.map1_l, self.map2_l, cv2.INTER_LINEAR), cv2.remap(right_img, self.map1_r, self.map2_r, cv2.INTER_LINEAR)

    @property
    def P1(self): return self._P1
    @property
    def P2(self): return self._P2
    @property
    def Q(self): return self._Q

def draw_epipolar_lines(left_img, right_img, gap=40):
    left_bgr = cv2.cvtColor(left_img, cv2.COLOR_GRAY2BGR) if left_img.ndim == 2 else left_img.copy()
    right_bgr = cv2.cvtColor(right_img, cv2.COLOR_GRAY2BGR) if right_img.ndim == 2 else right_img.copy()
    pair = np.hstack([left_bgr, right_bgr])
    for y in range(0, pair.shape[0], int(gap)):
        cv2.line(pair, (0, y), (pair.shape[1] - 1, y), (0, 255, 0), 1)
    return pair
