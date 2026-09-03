import pytest
from PySide6.QtWidgets import QApplication
from src.ui.command_panel import TaskCommandPanel
from src.ui.mission_map import MissionMapWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_mission_map_coordinate_roundtrip(qapp):
    widget = MissionMapWidget()
    widget.resize(600, 300)
    ox, oy, sx, sy = widget._get_origin_and_scale()

    test_coords = [(0.0, 0.0), (0.35, 0.20), (-0.40, 0.60), (0.123, 0.456)]
    for wx, wy in test_coords:
        pt = widget.world_to_pixel(wx, wy)
        rx, ry = widget.pixel_to_world(pt.x(), pt.y())
        assert abs(rx - wx) < 1e-4
        assert abs(ry - wy) < 1e-4


def test_command_panel_dynamic_params(qapp):
    panel = TaskCommandPanel()

    # 1. 测试 move_to 并设置地图坐标
    panel.set_target_coordinate(0.42, 0.18)
    assert panel.current_command_type() == "move_to"
    assert abs(panel.move_to_x.value() - 0.42) < 1e-3
    assert abs(panel.move_to_y.value() - 0.18) < 1e-3

    generated_events = []
    panel.generateRequested.connect(lambda cmd, params: generated_events.append((cmd, params)))

    panel._generate()
    assert len(generated_events) == 1
    assert generated_events[0][0] == "move_to"
    assert generated_events[0][1] == {"x": 0.42, "y": 0.18}

    # 2. 测试切换为 move_along
    idx_along = panel.task_type_combo.findData("move_along")
    panel.task_type_combo.setCurrentIndex(idx_along)
    panel.move_along_theta.setValue(45.0)
    panel.move_along_d.setValue(0.25)
    panel._generate()
    assert generated_events[-1][0] == "move_along"
    assert generated_events[-1][1] == {"theta_deg": 45.0, "distance_m": 0.25}

    # 3. 测试切换为 rotate_arm
    idx_rot_arm = panel.task_type_combo.findData("rotate_arm")
    panel.task_type_combo.setCurrentIndex(idx_rot_arm)
    panel.rot_arm_n.setValue(3)
    panel.rot_arm_alpha.setValue(-45.0)
    panel._generate()
    assert generated_events[-1][0] == "rotate_arm"
    assert generated_events[-1][1] == {"joint_index": 3, "alpha_deg": -45.0}
