import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse, numpy as np
from src.camera.image_pair_loader import load_gray_pair
from src.pipeline import load_runtime_config, process_pair
from src.target.pose_estimator import fit_plane_svd
ap=argparse.ArgumentParser(); ap.add_argument("--left", required=True); ap.add_argument("--right", required=True); a=ap.parse_args()
left,right=load_gray_pair(a.left,a.right); cfg=load_runtime_config(); _,_,points=process_pair(left,right,cfg); print("[INFO] 3D points:"); print(points)
if len(points)>1:
    d=[np.linalg.norm(points[i]-points[j]) for i in range(len(points)) for j in range(i+1,len(points))]; print(f"pair distance min/mean/max = {min(d):.6f}/{np.mean(d):.6f}/{max(d):.6f} m")
if len(points)>=3:
    _,_,rmse=fit_plane_svd(points); print(f"plane_rmse_m = {rmse:.6f}")
    if rmse > cfg["target"]["max_plane_rmse_m"]: print("[WARN] plane RMSE is larger than configured threshold")
