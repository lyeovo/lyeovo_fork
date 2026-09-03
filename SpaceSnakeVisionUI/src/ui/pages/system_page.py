from __future__ import annotations

from typing import List, Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..log_console import LogConsoleWidget
from ...state.system_state import SystemState, SystemStateStore


class SystemPage(QWidget):
    """Page 5: 系统通信诊断与健康度监控专页"""

    def __init__(self, log_console: LogConsoleWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.log_console = log_console
        self.store = SystemStateStore.instance()
        self._build_ui()
        self.store.stateChanged.connect(self.on_state_updated)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Vertical)

        # 1. 顶部健康指标与模块状态
        top_box = QFrame()
        top_box.setObjectName("CardFrame")
        top_layout = QVBoxLayout(top_box)
        top_layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("SYSTEM SUBSYSTEMS HEALTH & TELEMETRY · 子系统在线状态与网络指标")
        title.setObjectName("SubheaderLabel")
        top_layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)

        self.modules: List[Tuple[str, QLabel]] = []
        mod_names = [
            "Intel D405 Stereo Camera",
            "YOLO Target Detector",
            "White Dot 6DoF Estimator",
            "Mission State Machine",
            "Outbox/Inbox File Bridge",
            "MATLAB Motion Planner",
            "dSPACE Controller Link",
            "Snake Arm Joint Actuators",
            "Gripper Microcontroller",
        ]

        for i, name in enumerate(mod_names):
            row = i // 3
            col = (i % 3) * 2
            name_lbl = QLabel(name)
            status_lbl = QLabel("● ONLINE")
            status_lbl.setObjectName("StatusOnline")
            grid.addWidget(name_lbl, row, col)
            grid.addWidget(status_lbl, row, col + 1)
            self.modules.append((name, status_lbl))

        top_layout.addLayout(grid)

        # 性能指标
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(16)
        self.fps_lbl = QLabel("Vision Pipeline: 30.0 FPS")
        self.rtt_lbl = QLabel("Bridge Latency: 4.2 ms")
        self.cmd_lbl = QLabel("Active Command: NONE")
        for lbl in (self.fps_lbl, self.rtt_lbl, self.cmd_lbl):
            lbl.setObjectName("TelemetryLabel")
            metrics_row.addWidget(lbl)
        metrics_row.addStretch()
        top_layout.addLayout(metrics_row)

        splitter.addWidget(top_box)

        # 2. 底部全局审计日志控制台
        log_box = QFrame()
        log_box.setObjectName("CardFrame")
        lb_layout = QVBoxLayout(log_box)
        lb_layout.setContentsMargins(6, 6, 6, 6)
        lb_title = QLabel("SYSTEM AUDIT & EVENT LOG · 统一时间戳任务事件日志")
        lb_title.setObjectName("SubheaderLabel")
        lb_layout.addWidget(lb_title)
        lb_layout.addWidget(self.log_console, stretch=1)
        splitter.addWidget(log_box)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    def on_state_updated(self, state: SystemState) -> None:
        self.fps_lbl.setText(f"Vision Pipeline: {state.vision.fps:.1f} FPS")
        self.cmd_lbl.setText(f"Active Command: {state.command.command_id or 'NONE'} [{state.command.control_status}]")
