import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.camera.d405_intrinsics import read_d405_stereo_params
from src.calibration.stereo_params import save_stereo_params
p = read_d405_stereo_params()
print("K_left=\n", p.K_left); print("D_left=", p.D_left.ravel())
print("K_right=\n", p.K_right); print("D_right=", p.D_right.ravel())
print("R=\n", p.R); print("T=\n", p.T)
save_stereo_params(p, "config/stereo_params.yaml")
print("[INFO] saved config/stereo_params.yaml")
