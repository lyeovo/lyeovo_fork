import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
from src.camera.d405_capture import D405StereoCamera
from src.utils.time_utils import filename_timestamp
out_l = Path("data/test_images/left"); out_r = Path("data/test_images/right")
out_l.mkdir(parents=True, exist_ok=True); out_r.mkdir(parents=True, exist_ok=True)
with D405StereoCamera() as cam:
    print("[INFO] D405 started. Press s to save, ESC to exit.")
    while True:
        left, right = cam.get_frames()
        cv2.imshow("D405 left infrared", left); cv2.imshow("D405 right infrared", right)
        key = cv2.waitKey(1) & 0xFF
        if key == 27: break
        if key == ord("s"):
            ts = filename_timestamp()
            cv2.imwrite(str(out_l / f"left_{ts}.png"), left)
            cv2.imwrite(str(out_r / f"right_{ts}.png"), right)
            print("[INFO] saved", ts)
cv2.destroyAllWindows()
