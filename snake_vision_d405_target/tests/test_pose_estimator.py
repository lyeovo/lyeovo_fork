import numpy as np
from src.target.pose_estimator import estimate_target_pose, fit_plane_svd
def test_pose_estimator_plane():
    points = np.array([[x, y, 0.5] for x in [-0.04,0,0.04] for y in [-0.04,0,0.04]], dtype=float)
    center, normal, rmse = fit_plane_svd(points)
    pos, quat, quality = estimate_target_pose(points)
    assert np.allclose(center, [0,0,0.5])
    assert np.allclose(pos, [0,0,0.5])
    assert rmse < 1e-9
    assert len(quat) == 4
