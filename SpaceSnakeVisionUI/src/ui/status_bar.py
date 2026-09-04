from __future__ import annotations

import time
from typing import Optional
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..state.system_state import SystemState, SystemStateStore


class MissionStatusBar(QWidget):
    """航天级任务总控常驻 Header"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = SystemStateStore.instance()
        self._build_ui()
        self.store.stateChanged.connect(self.on_state_updated)

        # 实时时间定时器
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self._update_clock()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 4, 8, 4)
        main_layout.setSpacing(4)

        # 顶行：主标题 + 子系统状态指示灯 + 时间戳
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.title = QLabel("ORBITAL SNAKE ROBOT MISSION CONTROL")
        self.title.setObjectName("HeaderTitle")
        top_row.addWidget(self.title)

        top_row.addStretch()

        self.subsystems_lbl = QLabel("INITIALIZING SUBSYSTEMS…")
        self.subsystems_lbl.setObjectName("SubsystemsStatus")
        top_row.addWidget(self.subsystems_lbl)

        self.clock_lbl = QLabel("00:00:00 UTC")
        self.clock_lbl.setObjectName("ClockLabel")
        top_row.addWidget(self.clock_lbl)

        main_layout.addLayout(top_row)

        # 底行：活跃任务名称 + 当前阶段 + 任务总进度条
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.mission_lbl = QLabel("ACTIVE MISSION: [M-01] 目标工件抓取装配任务")
        self.mission_lbl.setObjectName("MissionTitleLabel")
        bot_row.addWidget(self.mission_lbl)

        self.phase_lbl = QLabel("PHASE: 01 / 16 [流程开始]")
        self.phase_lbl.setObjectName("PhaseLabel")
        bot_row.addWidget(self.phase_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(6)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setTextVisible(True)
        bot_row.addWidget(self.progress_bar)

        bot_row.addStretch()

        self.state = QLabel("Bridge: FILE MODE | Robot: IDLE")
        self.state.setObjectName("StateSummaryLabel")
        bot_row.addWidget(self.state)

        main_layout.addLayout(bot_row)

        # 变更追踪，避免每次 stateChanged 都重复 setStyleSheet
        self._last_state_text: Optional[str] = None
        self._last_state_danger: Optional[bool] = None

        # 用当前状态初始化 header，避免首帧显示占位/假数据
        self.on_state_updated(self.store.state)

    def _update_clock(self) -> None:
        utc_str = time.strftime("%H:%M:%S UTC", time.gmtime())
        self.clock_lbl.setText(utc_str)

    def on_state_updated(self, state: SystemState) -> None:
        m = state.mission
        self.mission_lbl.setText(f"ACTIVE MISSION: [{m.mission_id}] {m.name}")
        self.phase_lbl.setText(f"PHASE: {m.step_index:02d} / {m.total_steps:02d} [{m.status_text}]")

        pct = int((m.step_index / max(1, m.total_steps)) * 100)
        self.progress_bar.setValue(pct)

        h = state.health
        r = state.robot
        estop_str = "[ ESTOP! ]" if h.estop_active else "[ SAFE ]"
        cam_str = "● ONLINE" if h.camera_online else "○ OFFLINE"
        vis_str = f"● {state.vision.detector_status}"

        if h.estop_active:
            ctl_str = "● ESTOP"
        elif not h.control_online:
            ctl_str = "○ OFFLINE"
        elif state.command.control_status in ("ACCEPTED", "PLANNING", "EXECUTING"):
            ctl_str = f"● {state.command.control_status}"
        else:
            ctl_str = "● READY"

        ds_str = "● ONLINE" if h.dspace_connected else "◐ STANDBY"
        rtt_str = f"{h.bridge_rtt_ms:.0f} ms" if h.bridge_rtt_ms is not None else "—"

        self.subsystems_lbl.setText(
            f"CAMERA: {cam_str}  |  VISION: {vis_str}  |  CONTROL: {ctl_str}  |  "
            f"dSPACE: {ds_str}  |  RTT: {rtt_str}  |  E-STOP: {estop_str}"
        )

        danger = bool(h.estop_active or r.state in ("ESTOP", "ESTOP_TRIGGERED"))
        state_text = f"Bridge: {h.bridge_mode} MODE | Robot: {r.state}"
        if state_text != self._last_state_text or danger != self._last_state_danger:
            self.set_state(state_text, danger)
            self._last_state_text = state_text
            self._last_state_danger = danger

    def set_state(self, text: str, danger: bool = False) -> None:
        self.state.setText(text)
        color = "#FF4D5A" if danger else "#2EEA8A"
        self.state.setStyleSheet(f"color: {color}; font-family: Consolas;")
