import cv2
import numpy as np

class StereoTriangulator:
    def __init__(self, P1, P2, min_z=0.0, max_z=5.0):
        self.P1 = np.asarray(P1, dtype=float)
        self.P2 = np.asarray(P2, dtype=float)
        self.min_z = min_z
        self.max_z = max_z

    def triangulate(self, matches):
        if not matches:
            return np.empty((0, 3), dtype=float)
        pts_l = np.array([[m.u_left, m.v_left] for m in matches], dtype=float)
        pts_r = np.array([[m.u_right, m.v_right] for m in matches], dtype=float)
        p4 = cv2.triangulatePoints(self.P1, self.P2, pts_l.T, pts_r.T)
        points = (p4[:3] / p4[3]).T
        mask = np.isfinite(points).all(axis=1) & (points[:, 2] > self.min_z) & (points[:, 2] < self.max_z)
        return points[mask]

def triangulate_by_disparity(matches, P1, P2):
    P1 = np.asarray(P1, dtype=float)
    P2 = np.asarray(P2, dtype=float)
    f, cx, cy = P1[0, 0], P1[0, 2], P1[1, 2]
    baseline = abs(P2[0, 3] / P2[0, 0])
    pts = []
    for m in matches:
        if m.disparity <= 0:
            continue
        z = f * baseline / m.disparity
        pts.append([(m.u_left - cx) * z / f, (m.v_left - cy) * z / f, z])
    return np.asarray(pts, dtype=float)
