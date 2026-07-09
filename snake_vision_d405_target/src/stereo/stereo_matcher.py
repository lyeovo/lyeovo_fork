from dataclasses import dataclass

@dataclass
class StereoMatch:
    left_index: int
    right_index: int
    u_left: float
    v_left: float
    u_right: float
    v_right: float
    disparity: float
    score: float

class StereoPointMatcher:
    def __init__(self, y_threshold_px=2.5, min_disparity_px=1.0, max_disparity_px=250.0, uniqueness_check=True):
        self.y_threshold_px = y_threshold_px
        self.min_disparity_px = min_disparity_px
        self.max_disparity_px = max_disparity_px
        self.uniqueness_check = uniqueness_check

    def match(self, left_circles, right_circles):
        candidates = []
        for li, l in enumerate(left_circles):
            for ri, r in enumerate(right_circles):
                dy = abs(l.v - r.v)
                disparity = l.u - r.u
                if dy <= self.y_threshold_px and self.min_disparity_px <= disparity <= self.max_disparity_px:
                    candidates.append((dy + 0.05 * abs(l.radius_est - r.radius_est), li, ri, disparity))
        candidates.sort()
        used_l, used_r, out = set(), set(), []
        for score, li, ri, disparity in candidates:
            if self.uniqueness_check and (li in used_l or ri in used_r):
                continue
            l, r = left_circles[li], right_circles[ri]
            out.append(StereoMatch(li, ri, l.u, l.v, r.u, r.v, float(disparity), float(score)))
            used_l.add(li)
            used_r.add(ri)
        return sorted(out, key=lambda m: m.left_index)
