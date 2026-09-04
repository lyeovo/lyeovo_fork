from __future__ import annotations

import os
import pytest
from PySide6.QtWidgets import QApplication

from src.models import Pose3D, RobotState, Vector3, Euler
from src.state.system_state import SystemStateStore
from src.ui.pages.components_page import ActuatorCardWidget, ComponentsPage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_actuator_card_widget(qapp):
    card = ActuatorCardWidget(
        channel_id=1,
        name="Joint 1",
        cn_name="基座回转关节",
        motor_type="joint",
        min_val=-180.0,
        max_val=180.0,
    )
    assert card.channel_id == 1
    assert "Joint 1" in card.motor_name

    # 更新角度 45.0 度
    card.update_value(45.0, vel=10.0)
    assert "+45.0°" in card.main_val_lbl.text()
    assert "rad" in card.sub_val_lbl.text()
    assert card.status_lbl.text() == "NORMAL"

    # 极限角度测试 175.0 度 (触发 LIMIT 警告)
    card.update_value(175.0)
    assert card.status_lbl.text() == "LIMIT"


def test_gripper_gap_card_widget(qapp):
    card = ActuatorCardWidget(
        channel_id=8,
        name="GripperGap",
        cn_name="末端夹爪开合电机",
        motor_type="gripper_gap",
        min_val=0.0,
        max_val=1.0,
        unit="ratio",
    )
    # 模拟全开 1.0
    card.update_value(1.0, extra_str="OPEN (全开就绪)")
    assert "100.0%" in card.main_val_lbl.text()
    assert "OPEN" in card.sub_val_lbl.text()


def test_components_page_state_update(qapp):
    store = SystemStateStore.instance()
    page = ComponentsPage()

    # 验证 8 个电机卡片全部生成
    assert len(page.motor_cards) == 8

    # 模拟推送 Robot 遥测状态 (包含 6 个关节角度 + 1个 GripperOri 与夹爪状态 CLOSED)
    store.update_robot(
        state="EXECUTING",
        joint_angles_deg=[10.0, -20.0, 30.0, -40.0, 50.0, -60.0, 15.0],
        gripper_state="CLOSED",
        ee_x=1.234,
        ee_y=0.567,
        ee_z=0.100,
        ee_yaw=45.0,
    )

    # 检查界面响应
    assert "+10.0°" in page.motor_cards[0].main_val_lbl.text()
    assert "-60.0°" in page.motor_cards[5].main_val_lbl.text()
    assert "+15.0°" in page.motor_cards[6].main_val_lbl.text()  # GripperOri
    assert "CLOSED" in page.gripper_status_lbl.text()
    assert "1.234" in page.ee_pose_lbl.text()
