from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..command_panel import TaskCommandPanel
from ..mission_map import MissionMapWidget
from ..task_list import TaskListWidget
from ...state.system_state import SystemState, SystemStateStore


class TaskPage(QWidget):
    """Page 3: 任务发布与地图选点操纵专页"""

    generateRequested = Signal(str, dict)
    publishRequested = Signal()
    estopRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = SystemStateStore.instance()
        self._build_ui()
        # 订阅状态变更，将关节角度实时同步到俯视地图
        self.store.stateChanged.connect(self.on_state_updated)

    def on_state_updated(self, state: SystemState) -> None:
        """状态变更时更新俯视地图上的机械臂姿态"""
        rob = state.robot
        self.mission_map.set_joint_angles(rob.joint_angles_deg, rob.gripper_state)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)

        # 1. 俯视地图面板
        map_box = QFrame()
        map_box.setObjectName("CardFrame")
        m_layout = QVBoxLayout(map_box)
        m_layout.setContentsMargins(6, 6, 6, 6)

        map_header = QLabel("MISSION TOP-DOWN MAP · 俯视作业空间地图（点击快速拾取坐标）")
        map_header.setObjectName("SubheaderLabel")
        m_layout.addWidget(map_header)

        self.mission_map = MissionMapWidget()
        m_layout.addWidget(self.mission_map, stretch=1)
        splitter.addWidget(map_box)

        # 2. 任务命令控制面板
        cmd_box = QFrame()
        cmd_box.setObjectName("CardFrame")
        c_layout = QVBoxLayout(cmd_box)
        c_layout.setContentsMargins(6, 6, 6, 6)

        cmd_header = QLabel("TASK COMMAND BUILDER · 10类任务指令控制台")
        cmd_header.setObjectName("SubheaderLabel")
        c_layout.addWidget(cmd_header)

        self.command_panel = TaskCommandPanel()
        self.command_panel.generateRequested.connect(self.generateRequested.emit)
        self.command_panel.publishRequested.connect(self.publishRequested.emit)
        self.command_panel.estopRequested.connect(self.estopRequested.emit)
        self.command_panel.cancelRequested.connect(self.cancelRequested.emit)
        c_layout.addWidget(self.command_panel, stretch=1)

        # 历史任务清单展开/折叠按钮
        self.toggle_tasks_btn = QPushButton("📜 切换展开/收起历史任务清单")
        self.toggle_tasks_btn.clicked.connect(self._toggle_task_list)
        c_layout.addWidget(self.toggle_tasks_btn)

        splitter.addWidget(cmd_box)

        # 3. 历史任务清单
        self.task_list = TaskListWidget()
        self.task_list.setVisible(False)
        splitter.addWidget(self.task_list)

        # 地图选点联动回填至命令面板
        self.mission_map.coordinateSelected.connect(self.command_panel.set_target_coordinate)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)
        layout.addWidget(splitter)

    def _toggle_task_list(self) -> None:
        self.task_list.setVisible(not self.task_list.isVisible())
