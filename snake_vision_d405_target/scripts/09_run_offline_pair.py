import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse, cv2
from src.camera.image_pair_loader import load_gray_pair
from src.pipeline import load_runtime_config, process_pair
ap=argparse.ArgumentParser(); ap.add_argument("--left", required=True); ap.add_argument("--right", required=True); ap.add_argument("--show", action="store_true"); a=ap.parse_args()
left,right=load_gray_pair(a.left,a.right); results,vis,_=process_pair(left,right,load_runtime_config()); print(f"[INFO] results: {len(results)}")
if a.show:
    cv2.imshow("offline pair result",vis); cv2.waitKey(0); cv2.destroyAllWindows()
