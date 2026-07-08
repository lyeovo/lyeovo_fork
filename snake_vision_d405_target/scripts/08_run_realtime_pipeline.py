import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from src.camera.d405_capture import D405StereoCamera
from src.pipeline import load_runtime_config, process_pair
cfg=load_runtime_config(); c=cfg["camera"]
with D405StereoCamera(c["width"],c["height"],c["fps"],c["infrared_left_index"],c["infrared_right_index"]) as cam:
    print("[INFO] realtime pipeline started. Press ESC to exit.")
    while True:
        left,right=cam.get_frames(); _,vis,_=process_pair(left,right,cfg,save_visualization=False); cv2.imshow("D405 target pipeline",vis)
        if (cv2.waitKey(1)&0xFF)==27: break
cv2.destroyAllWindows()
