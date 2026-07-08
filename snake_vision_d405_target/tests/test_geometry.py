import numpy as np
from src.utils.geometry import normalize, is_rotation_matrix, point_plane_distances

def test_normalize():
    assert np.allclose(normalize([3, 0, 0]), [1, 0, 0])

def test_rotation_matrix():
    assert is_rotation_matrix(np.eye(3))

def test_point_plane_distances():
    assert np.allclose(point_plane_distances([[0,0,1],[0,0,2]], [0,0,0], [0,0,1]), [1,2])
