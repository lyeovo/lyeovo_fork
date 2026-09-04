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

def test_mission_map_target_handeye_projection(qapp):
    """测试目标在末端手眼变换下的空间绝对物理位置映射"""
    from src.models import DetectedObject, Pose3D, Vector3

    widget = MissionMapWidget()
    # 全直立朝向 +Y 轴
    widget.joint_angles_deg = [0.0] * 6
    joint_pts, ee_angle = widget.compute_forward_kinematics()
    ee_x, ee_y = joint_pts[-1]
    assert abs(ee_x - 0.0) < 1e-3
    assert abs(ee_y - 6 * 1.04393) < 1e-3

    # 相机测得前方 0.3m, 右侧 0.05m
    wx, wy = widget.camera_to_world_coord(0.05, 0.30)
    assert abs(wx - 0.05) < 1e-3
    assert abs(wy - (ee_y + 0.30)) < 1e-3

    # 传入 target 对象并重绘
    obj = DetectedObject(
        target_id="TGT-201",
        timestamp=100.0,
        class_name="201",
        display_name="Target 201",
        detection_mode="yolo_marker",
        marker_id=201,
        confidence=0.9,
        stability_score=0.9,
        bbox_xyxy=[10, 10, 100, 100],
        center_pixel=[50, 50],
        depth_m=0.30,
        pose_camera=Pose3D(position=Vector3(0.05, 0.0, 0.30)),
    )
    widget.update_map([obj], selected_id="TGT-201")
    widget.repaint()


def test_target_click_coordinate_transformation(qapp):
    """测试点击选中目标时，能够将相机相对坐标准确转换为真实物理空间基座坐标"""
    from src.bridge.command_builder import camera_to_base_pose
    from src.models import Pose3D, Vector3

    # 相机测得：向右 0.08m，正前深度 0.35m
    pose_cam = Pose3D(frame_id="camera_left", position=Vector3(0.08, -0.02, 0.35))

    # 机械臂各关节处于初始全直立 (各关节均为 0°)
    pose_base = camera_to_base_pose(pose_cam, [0.0] * 6)
    assert pose_base.frame_id == "robot_base"

    ee_nominal_y = 6 * 1.04393  # 6.26358m
    # 物理空间 X 坐标为 +0.08m，Y 坐标为 末端 Y + 0.35m
    assert abs(pose_base.position.x - 0.08) < 1e-3
    assert abs(pose_base.position.y - (ee_nominal_y + 0.35)) < 1e-3



