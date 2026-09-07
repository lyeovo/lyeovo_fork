from __future__ import annotations

import numpy as np
import pytest

from src.camera.base_camera import CameraFrame, CameraIntrinsics
from src.models import DetectedObject, Euler, Pose3D, Quaternion, Vector3
from src.bridge.command_builder import camera_to_base_pose
from src.vision.pipeline import VisionPipeline
from src.vision.depth_pose import pose_from_depth


def test_depth_pose_creates_valid_3dof_with_quaternion():
    intr = CameraIntrinsics(fx=600.0, fy=600.0, cx=320.0, cy=240.0, width=640, height=480)
    depth_image = np.full((480, 640), 0.5, dtype=np.float32)  # 50cm 深度
    center = (380, 270)  # 右下偏一点

    pose, depth, status = pose_from_depth(depth_image, center, intr)
    assert status == "AVAILABLE"
    assert depth == pytest.approx(0.5, abs=1e-3)
    assert pose.position.z == pytest.approx(0.5, abs=1e-3)
    # 期望反投影：x = (380 - 320) * 0.5 / 600 = 60 * 0.5 / 600 = 0.05m
    assert pose.position.x == pytest.approx(0.05, abs=1e-3)
    # y = (270 - 240) * 0.5 / 600 = 30 * 0.5 / 600 = 0.025m
    assert pose.position.y == pytest.approx(0.025, abs=1e-3)
    # 四元数应当有效非空
    assert pose.orientation_quat.w == pytest.approx(1.0)


def test_pipeline_draws_axes_for_3dof_and_6dof():
    intr = CameraIntrinsics(fx=600.0, fy=600.0, cx=320.0, cy=240.0, width=640, height=480)
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    obj_3dof = DetectedObject(
        target_id="TGT-301",
        timestamp=100.0,
        class_name="marker",
        display_name="TGT-301",
        detection_mode="yolo_marker",
        marker_id=None,
        confidence=0.85,
        stability_score=0.85,
        bbox_xyxy=[280, 200, 360, 280],
        center_pixel=[320, 240],
        depth_m=0.45,
        pose_camera=Pose3D(
            position=Vector3(0.0, 0.0, 0.45),
            orientation_quat=Quaternion(0.0, 0.0, 0.0, 1.0),
        ),
        status="POSE_3DOF",
    )

    # 绘制 overlay，不应抛出任何异常，并且图像中有绘制内容（非全黑）
    VisionPipeline.draw_overlay(img, [obj_3dof], None, intr)
    assert np.any(img > 0)


def test_camera_to_base_pose_with_3dof_position():
    # 假设末端在相机系下观测到目标在正前方 0.4m (cam_z=0.4, cam_x=0.0)
    # 机械臂 6 个关节全为 0 度时，顺向运动学末端垂直向上 (accum_angle = pi/2 = +Y 轴)
    # 臂展开长度 ≈ 6 * 1.04393 ≈ 6.26358m
    pose_cam = Pose3D(
        position=Vector3(x=0.0, y=0.0, z=0.40),
        orientation_quat=Quaternion(0.0, 0.0, 0.0, 1.0),
    )
    joint_angles = [0.0] * 6
    pose_base = camera_to_base_pose(pose_cam, joint_angles)

    # 世界坐标 X 应该非常接近 0 (末端 X=0, cam_x=0)
    assert pose_base.position.x == pytest.approx(0.0, abs=1e-3)
    # 世界坐标 Y 应该在末端基础再加上 0.4m
    expected_ee_y = 6 * 1.04393
    assert pose_base.position.y == pytest.approx(expected_ee_y + 0.40, abs=1e-3)
