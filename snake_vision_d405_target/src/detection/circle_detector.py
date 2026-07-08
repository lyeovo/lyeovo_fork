from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np

@dataclass
class Circle2D:
    u: float
    v: float
    area: float
    circularity: float
    radius_est: float
    bbox: tuple[float, float, float, float] | None = None

class CircleDetector:
    def __init__(
        self,
        min_area=20,
        max_area=5000,
        min_circularity=0.60,
        gaussian_kernel=5,
        binary_inverse=True,
        threshold_mode="otsu",
        threshold_value=35,
        use_roi=False,
        left_roi=None,
        right_roi=None,
        min_aspect=0.6,
        max_aspect=1.4,
        debug_dir=None,
        debug_print=False,
    ):
        self.min_area = min_area
        self.max_area = max_area
        self.min_circularity = min_circularity
        self.gaussian_kernel = gaussian_kernel if gaussian_kernel % 2 == 1 else gaussian_kernel + 1
        self.binary_inverse = binary_inverse
        self.threshold_mode = threshold_mode
        self.threshold_value = threshold_value
        self.use_roi = use_roi
        self.left_roi = left_roi
        self.right_roi = right_roi
        self.min_aspect = min_aspect
        self.max_aspect = max_aspect
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.debug_print = debug_print
        self.last_binary = None
        self.last_roi_image = None
        self.last_debug_infos = []
        self.last_candidate_infos = []

    @classmethod
    def from_config(cls, config):
        c = config.get("circle_detection", config)
        paths = config.get("paths", {})
        debug_dir = c.get("debug_dir") or paths.get("debug_dir")
        return cls(
            min_area=c.get("min_area", 20),
            max_area=c.get("max_area", 5000),
            min_circularity=c.get("min_circularity", 0.60),
            gaussian_kernel=c.get("gaussian_kernel", 5),
            binary_inverse=c.get("binary_inverse", True),
            threshold_mode=c.get("threshold_mode", "otsu"),
            threshold_value=c.get("threshold_value", 35),
            use_roi=c.get("use_roi", False),
            left_roi=c.get("left_roi"),
            right_roi=c.get("right_roi"),
            min_aspect=c.get("min_aspect", 0.6),
            max_aspect=c.get("max_aspect", 1.4),
            debug_dir=debug_dir,
            debug_print=c.get("debug_print", False),
        )

    def roi_for_side(self, side):
        if not self.use_roi:
            return None
        if side == "left":
            return self.left_roi
        if side == "right":
            return self.right_roi
        return None

    def detect(self, gray_img, roi=None, side=None, debug_name=None):
        if gray_img.ndim != 2:
            gray_img = cv2.cvtColor(gray_img, cv2.COLOR_BGR2GRAY)
        roi = roi if roi is not None else self.roi_for_side(side)
        x0, y0 = 0, 0
        if roi is not None:
            x0, y0, w, h = [int(v) for v in roi]
            gray_work = gray_img[y0:y0 + h, x0:x0 + w].copy()
        else:
            gray_work = gray_img.copy()
        self.last_roi_image = gray_work
        blur = cv2.GaussianBlur(gray_work, (self.gaussian_kernel, self.gaussian_kernel), 0)
        mode = cv2.THRESH_BINARY_INV if self.binary_inverse else cv2.THRESH_BINARY
        if self.threshold_mode == "manual":
            _, binary = cv2.threshold(blur, float(self.threshold_value), 255, mode)
        else:
            _, binary = cv2.threshold(blur, 0, 255, mode + cv2.THRESH_OTSU)
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        self.last_binary = binary
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        circles = []
        debug_infos = []
        candidate_infos = []
        for c in contours:
            area = cv2.contourArea(c)
            x, y, bw, bh = cv2.boundingRect(c)
            bbox = (float(x + x0), float(y + y0), float(bw), float(bh))
            aspect = bw / float(bh) if bh else 0.0
            perimeter = cv2.arcLength(c, True)
            circularity = 0.0
            accepted = True
            reject_reason = ""
            if area < self.min_area or area > self.max_area:
                accepted = False
                reject_reason = "area"
            if perimeter <= 1e-6:
                accepted = False
                reject_reason = "perimeter"
            else:
                circularity = 4.0 * np.pi * area / (perimeter * perimeter)
            if accepted and circularity < self.min_circularity:
                accepted = False
                reject_reason = "circularity"
            if accepted and (aspect < self.min_aspect or aspect > self.max_aspect):
                accepted = False
                reject_reason = "aspect"
            candidate_info = {
                "area": float(area),
                "circularity": float(circularity),
                "bbox": bbox,
                "aspect": float(aspect),
                "accepted": accepted,
                "reject_reason": reject_reason,
            }
            candidate_infos.append(candidate_info)
            if not accepted:
                continue
            M = cv2.moments(c)
            if abs(M["m00"]) < 1e-6:
                candidate_info["accepted"] = False
                candidate_info["reject_reason"] = "moments"
                continue
            u = M["m10"] / M["m00"] + x0
            v = M["m01"] / M["m00"] + y0
            circles.append(Circle2D(float(u), float(v), float(area), float(circularity), float((area / np.pi) ** 0.5), bbox))
            debug_infos.append({"area": float(area), "circularity": float(circularity), "bbox": bbox})
        circles = sorted(circles, key=lambda p: (p.v, p.u))
        self.last_debug_infos = debug_infos
        self.last_candidate_infos = candidate_infos
        if self.debug_print:
            name = debug_name or side or "image"
            for info in candidate_infos:
                status = "accepted" if info["accepted"] else f"rejected:{info['reject_reason']}"
                print(
                    f"[DEBUG] {name} contour {status} "
                    f"area={info['area']:.1f} circularity={info['circularity']:.3f} "
                    f"aspect={info['aspect']:.2f} bbox={info['bbox']}"
                )
        if self.debug_dir and debug_name:
            self.save_debug_images(gray_img, circles, debug_name)
        return circles

    def save_debug_images(self, gray_img, circles, name):
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(self.debug_dir / f"{name}_roi.png"), self.last_roi_image)
        cv2.imwrite(str(self.debug_dir / f"{name}_binary.png"), self.last_binary)
        vis = cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR) if gray_img.ndim == 2 else gray_img.copy()
        for c in circles:
            center = (int(round(c.u)), int(round(c.v)))
            cv2.circle(vis, center, max(2, int(round(c.radius_est))), (0, 255, 0), 1)
            cv2.circle(vis, center, 2, (0, 0, 255), -1)
            if c.bbox is not None:
                x, y, w, h = [int(round(v)) for v in c.bbox]
                cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 0, 0), 1)
        cv2.imwrite(str(self.debug_dir / f"{name}_detected.png"), vis)
