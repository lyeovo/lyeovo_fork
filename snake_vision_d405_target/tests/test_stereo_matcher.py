from src.detection.circle_detector import Circle2D
from src.stereo.stereo_matcher import StereoPointMatcher
def c(u, v): return Circle2D(u, v, 100, 1.0, 5)
def test_match_three_points():
    left = [c(100,50), c(200,50), c(300,80)]
    right = [c(90,50.5), c(190,50.2), c(290,80.1)]
    assert len(StereoPointMatcher().match(left, right)) == 3
