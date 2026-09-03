from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..widgets.workflow_view import WorkflowWidget
from ..camera_view import CameraViewWidget
from ...mission.state_machine import MissionStateMachine
from ...state.system_state import SystemState, SystemStateStore


class MissionPage(QWidget):
    """Page 1: 核心任务总览页 (Mission Overview)"""

    stepTriggerRequested = Signal()
    stepChoiceRequested = Signal(bool)  # 分支选择（True: 是, False: 否）
    resetRequested = Signal()
    gotoPageRequested = Signal(int)     # 快速跳转到其他页面 (1: vision, 2: task, etc.)

    def __init__(self, state_machine: MissionStateMachine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.sm = state_machine
        self.store = SystemStateStore.instance()
        self._build_ui()
        self.store.stateChanged.connect(self.on_state_updated)

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)

        # 1. 左侧：程序化流程图组件
        workflow_box = QFrame()
        workflow_box.setObjectName("CardFrame")
        wf_layout = QVBoxLayout(workflow_box)
        wf_layout.setContentsMargins(6, 6, 6, 6)

        wf_title = QLabel("MISSION WORKFLOW · 抓取操作系统流程")
        wf_title.setObjectName("SubheaderLabel")
        wf_layout.addWidget(wf_title)

        self.workflow_view = WorkflowWidget(self.sm)
        self.workflow_view.nodeClicked.connect(self._on_workflow_node_clicked)
        wf_layout.addWidget(self.workflow_view, stretch=1)

        splitter.addWidget(workflow_box)

        # 2. 右侧：相机实时画面 + 目标位姿卡片 + 末端卡片
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 实时相机流
        cam_card = QFrame()
        cam_card.setObjectName("CardFrame")
        cam_card_layout = QVBoxLayout(cam_card)
        cam_card_layout.setContentsMargins(6, 6, 6, 6)
        cam_header = QLabel("OPTICAL GUIDANCE · 实时视觉导引")
        cam_header.setObjectName("SubheaderLabel")
        cam_card_layout.addWidget(cam_header)

        self.camera_view = CameraViewWidget()
        self.camera_view.setMinimumHeight(240)
        cam_card_layout.addWidget(self.camera_view, stretch=1)
        right_layout.addWidget(cam_card, stretch=2)

        # 遥测卡片水平分栏
        telemetry_row = QHBoxLayout()
        telemetry_row.setSpacing(8)

        # 目标位姿卡片
        self.target_card = QFrame()
        self.target_card.setObjectName("CardFrame")
        t_layout = QVBoxLayout(self.target_card)
        t_layout.setContentsMargins(8, 6, 8, 6)
        t_header = QLabel("TARGET 6DoF · 锁定目标")
        t_header.setObjectName("SubheaderLabel")
        t_layout.addWidget(t_header)

        self.target_text = QLabel("Target: --\nStatus: SEARCH\nPos: --\nEuler: --")
        self.target_text.setObjectName("TelemetryLabel")
        t_layout.addWidget(self.target_text)
        telemetry_row.addWidget(self.target_card)

        # 机械臂末端卡片
        self.robot_card = QFrame()
        self.robot_card.setObjectName("CardFrame")
        r_layout = QVBoxLayout(self.robot_card)
        r_layout.setContentsMargins(8, 6, 8, 6)
        r_header = QLabel("ROBOT EE · 机械臂末端")
        r_header.setObjectName("SubheaderLabel")
        r_layout.addWidget(r_header)

        self.robot_text = QLabel("State: IDLE\nEE: (0.00, 0.00, 0.00) m\nGripper: OPEN\nPlanner: READY")
        self.robot_text.setObjectName("TelemetryLabel")
        r_layout.addWidget(self.robot_text)
        telemetry_row.addWidget(self.robot_card)

        right_layout.addLayout(telemetry_row, stretch=1)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        main_layout.addWidget(splitter, stretch=1)

        # 3. 底部指令操作与进度引导条
        bottom_bar = QFrame()
        bottom_bar.setObjectName("ActionToolbar")
        b_layout = QHBoxLayout(bottom_bar)
        b_layout.setContentsMargins(12, 6, 12, 6)
        b_layout.setSpacing(12)

        self.action_hint = QLabel("当前阶段: 01 流程启动 | 等待操作")
        self.action_hint.setObjectName("ActionHintLabel")
        b_layout.addWidget(self.action_hint)

        b_layout.addStretch()

        # 分支选择按钮（在判断节点时高亮显示）
        self.btn_choice_yes = QPushButton("是 / 符合条件")
        self.btn_choice_yes.setObjectName("BtnYes")
        self.btn_choice_yes.clicked.connect(lambda: self.stepChoiceRequested.emit(True))
        b_layout.addWidget(self.btn_choice_yes)

        self.btn_choice_no = QPushButton("否 / 未检出")
        self.btn_choice_no.setObjectName("BtnNo")
        self.btn_choice_no.clicked.connect(lambda: self.stepChoiceRequested.emit(False))
        b_layout.addWidget(self.btn_choice_no)

        # 推进下一步按钮
        self.btn_step_next = QPushButton("▶ 执行推进下一步")
        self.btn_step_next.setObjectName("BtnPrimaryAction")
        self.btn_step_next.clicked.connect(self.stepTriggerRequested.emit)
        b_layout.addWidget(self.btn_step_next)

        # 重置流程按钮
        self.btn_reset = QPushButton("↺ 重置流程")
        self.btn_reset.clicked.connect(self.resetRequested.emit)
        b_layout.addWidget(self.btn_reset)

        main_layout.addWidget(bottom_bar)

    def on_state_updated(self, state: SystemState) -> None:
        # 更新目标卡片
        v = state.vision
        if v.selected_target_id:
            t_str = (
                f"ID: {v.selected_target_id} ({v.target_class or '--'})\n"
                f"Status: {v.detector_status} | Conf: {v.confidence:.2f}\n"
                f"Pos: X={v.pos_x:+.3f}, Y={v.pos_y:+.3f}, Z={v.pos_z:+.3f}m\n"
                f"Rot: R={v.roll:+.1f}°, P={v.pitch:+.1f}°, Y={v.yaw:+.1f}°"
            )
        else:
            t_str = f"Target: 未锁定\nStatus: {v.detector_status}\nDepth: {f'{v.depth_m:.3f}m' if v.depth_m else '--'}\nDots: {v.valid_dots}/{v.total_dots}"
        self.target_text.setText(t_str)

        # 更新机器人卡片
        rob = state.robot
        r_str = (
            f"State: {rob.state} | Gripper: {rob.gripper_state}\n"
            f"EE Pos: X={rob.ee_x:+.3f}, Y={rob.ee_y:+.3f}, Z={rob.ee_z:+.3f}m\n"
            f"Command: {state.command.command_type} [{state.command.control_status}]\n"
            f"Progress: {state.command.progress:.0%}"
        )
        self.robot_text.setText(r_str)

        # 更新底部提示与分支按钮可见性
        cur_node = self.sm.current_node
        self.action_hint.setText(f"当前阶段: [{cur_node.index:02d}] {cur_node.title} — {cur_node.description}")

        is_decision = (cur_node.category == "DECISION")
        self.btn_choice_yes.setVisible(is_decision)
        self.btn_choice_no.setVisible(is_decision)

    def _on_workflow_node_clicked(self, node_id: str) -> None:
        self.sm.jump_to(node_id)
