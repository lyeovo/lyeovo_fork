from src.utils.geometry import deproject_pixel


def test_deproject_center_pixel():
    assert deproject_pixel((320, 240), 0.5, 600, 600, 320, 240) == (0.0, 0.0, 0.5)
