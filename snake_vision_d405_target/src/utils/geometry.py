import numpy as np

def normalize(v, eps=1e-12):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n < eps:
        raise ValueError("Cannot normalize near-zero vector")
    return v / n

def is_rotation_matrix(R, atol=1e-6):
    R = np.asarray(R, dtype=float)
    return R.shape == (3, 3) and np.allclose(R.T @ R, np.eye(3), atol=atol) and np.isclose(np.linalg.det(R), 1.0, atol=atol)

def point_plane_distances(points, center, normal):
    return (np.asarray(points, dtype=float) - np.asarray(center, dtype=float)) @ normalize(normal)

def camera_to_base(p_camera):
    return np.eye(3) @ np.asarray(p_camera, dtype=float) + np.zeros(3)
