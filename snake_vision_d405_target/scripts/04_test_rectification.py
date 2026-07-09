import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse, cv2
from src.camera.image_pair_loader import load_gray_pair
from src.calibration.stereo_params import load_stereo_params
from src.calibration.stereo_rectifier import StereoRectifier, draw_epipolar_lines
ap=argparse.ArgumentParser(); ap.add_argument("--left", required=True); ap.add_argument("--right", required=True); a=ap.parse_args()
left,right=load_gray_pair(a.left,a.right); rect=StereoRectifier(load_stereo_params("config/stereo_params.yaml"))
lr,rr=rect.rectify(left,right); cv2.imshow("rectified epipolar check", draw_epipolar_lines(lr,rr)); cv2.waitKey(0); cv2.destroyAllWindows()
