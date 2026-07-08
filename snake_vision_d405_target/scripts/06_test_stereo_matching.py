import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse, cv2
from src.camera.image_pair_loader import load_gray_pair
from src.detection.circle_detector import CircleDetector
from src.detection.visualization_2d import draw_matches
from src.stereo.stereo_matcher import StereoPointMatcher
from src.utils.config_io import load_yaml
ap=argparse.ArgumentParser(); ap.add_argument("--left", required=True); ap.add_argument("--right", required=True); ap.add_argument("--config", default="config/runtime_config.yaml"); a=ap.parse_args()
cfg=load_yaml(a.config); left,right=load_gray_pair(a.left,a.right); det=CircleDetector.from_config(cfg); lc,rc=det.detect(left,side="left",debug_name="left"),det.detect(right,side="right",debug_name="right"); m=StereoPointMatcher(**cfg.get("stereo_matching",{})).match(lc,rc); print("left circles:",len(lc)); print("right circles:",len(rc)); print("matches:",len(m)); cv2.imshow("matches",draw_matches(left,right,lc,rc,m)); cv2.waitKey(0); cv2.destroyAllWindows()
