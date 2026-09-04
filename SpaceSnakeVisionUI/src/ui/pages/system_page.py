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
            status_lbl = QLabel("○ IDLE")
            status_lbl.setObjectName("StatusIdle")
            grid.addWidget(name_lbl, row, col)
            grid.addWidget(status_lbl, row, col + 1)
            self.modules.append((name, status_lbl))

        top_layout.addLayout(grid)

        # 性能指标
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(16)
        self.fps_lbl = QLabel("Vision Pipeline: 0.0 FPS")
        self.rtt_lbl = QLabel("Bridge RTT: —")
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

        # 用当前状态初始化健康灯与指标，避免首帧显示假数据
        self.on_state_updated(self.store.state)

    def _set_light(self, lbl: QLabel, level: str, text: Optional[str] = None) -> None:
        obj_map = {
            "online": "StatusOnline",
            "warn": "StatusWarn",
            "offline": "StatusOffline",
            "idle": "StatusIdle",
        }
        default_text = {
            "online": "● ONLINE",
            "warn": "◐ WARN",
            "offline": "○ OFFLINE",
            "idle": "○ IDLE",
        }
        obj = obj_map.get(level, "StatusIdle")
        if lbl.objectName() != obj:
            lbl.setObjectName(obj)
            # objectName 变更后需重新 polish，QSS 颜色才会生效
            style = lbl.style()
            style.unpolish(lbl)
            style.polish(lbl)
        lbl.setText(text if text is not None else default_text.get(level, "○ IDLE"))

    def on_state_updated(self, state: SystemState) -> None:
        h = state.health
        v = state.vision
        r = state.robot
        lights = [lbl for _, lbl in self.modules]

        # 1. Intel D405 相机
        self._set_light(lights[0], "online" if h.camera_online else "offline")

        # 2. YOLO 目标检测器
        if not h.vision_running or v.detector_status in ("ERROR", "FAULT", "OFFLINE"):
            self._set_light(lights[1], "offline")
        else:
            self._set_light(lights[1], "online", text=f"● {v.detector_status}")

        # 3. 白点 6DoF 位姿估计器
        if v.pose_available:
            self._set_light(lights[2], "online", text="● 6DoF LOCK")
        elif v.valid_dots > 0:
            self._set_light(lights[2], "warn", text=f"◐ {v.valid_dots}/{v.total_dots} DOT")
        else:
            self._set_light(lights[2], "idle", text="○ NO FIX")

        # 4. 任务状态机（进程内，恒在线）
        self._set_light(lights[3], "online", text=f"● S{state.mission.step_index}")

        # 5. Outbox/Inbox 文件桥（以状态回传新鲜度为准）
        if h.control_online:
            self._set_light(lights[4], "online", text=f"● {h.bridge_mode}")
        else:
            self._set_light(lights[4], "offline", text="○ NO PEER")

        # 6. MATLAB 运动规划器（控制端存活）
        self._set_light(lights[5], "online" if h.control_online else "offline")

        # 7. dSPACE 控制器链路（文件桥模式下为预留 STANDBY）
        if h.dspace_connected:
            self._set_light(lights[6], "online")
        else:
            self._set_light(lights[6], "idle", text="◐ STANDBY·TCP")

        # 8. 蛇形臂关节执行器（随控制遥测新鲜度）
        self._set_light(lights[7], "online" if h.control_online else "offline")

        # 9. 夹爪微控制器
        if h.control_online:
            self._set_light(lights[8], "online", text=f"● {r.gripper_state}")
        else:
            self._set_light(lights[8], "offline")

        # 性能指标
        self.fps_lbl.setText(f"Vision Pipeline: {v.fps:.1f} FPS")
        if h.bridge_rtt_ms is not None:
            self.rtt_lbl.setText(f"Bridge RTT: {h.bridge_rtt_ms:.1f} ms")
        else:
            self.rtt_lbl.setText("Bridge RTT: —")
        self.cmd_lbl.setText(
            f"Active Command: {state.command.command_id or 'NONE'} [{state.command.control_status}]"
        )
