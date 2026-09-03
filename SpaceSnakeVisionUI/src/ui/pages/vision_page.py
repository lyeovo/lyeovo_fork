from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..camera_view import CameraViewWidget
from ..target_table import TargetTableWidget
from ...state.system_state import SystemState, SystemStateStore


class VisionPage(QWidget):
    """Page 2: 视觉感知与6DoF测量专页"""

    targetSelected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = SystemStateStore.instance()
        self._build_ui()
        self.store.stateChanged.connect(self.on_state_updated)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧：大尺寸相机画面
        left_box = QFrame()
        left_box.setObjectName("CardFrame")
        l_layout = QVBoxLayout(left_box)
        l_layout.setContentsMargins(6, 6, 6, 6)

        cam_header = QLabel("D405 REALTIME SENSOR FEED · 实时彩色与红外混合流")
        cam_header.setObjectName("SubheaderLabel")
        l_layout.addWidget(cam_header)

        self.camera_view = CameraViewWidget()
        l_layout.addWidget(self.camera_view, stretch=1)
        splitter.addWidget(left_box)

        # 右侧：目标列表与 6DoF 诊断参数
        right_panel = QWidget()
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(0, 0, 0, 0)
        r_layout.setSpacing(8)

        # 目标表格
        table_box = QFrame()
        table_box.setObjectName("CardFrame")
        tb_layout = QVBoxLayout(table_box)
        tb_layout.setContentsMargins(6, 6, 6, 6)
        tb_title = QLabel("DETECTED TARGETS · 视野检测目标列表")
        tb_title.setObjectName("SubheaderLabel")
        tb_layout.addWidget(tb_title)

        self.target_table = TargetTableWidget()
        self.target_table.targetSelected.connect(self.targetSelected.emit)
        tb_layout.addWidget(self.target_table)
        r_layout.addWidget(table_box, stretch=1)

        # 详细 6DoF 遥测参数文本框
        details_box = QFrame()
        details_box.setObjectName("CardFrame")
        dt_layout = QVBoxLayout(details_box)
        dt_layout.setContentsMargins(6, 6, 6, 6)
        dt_title = QLabel("6DoF POSE & QUALITY SPEC · 位姿与质量参数")
        dt_title.setObjectName("SubheaderLabel")
        dt_layout.addWidget(dt_title)

        self.details_edit = QPlainTextEdit()
        self.details_edit.setReadOnly(True)
        self.details_edit.setObjectName("LogConsole")
        dt_layout.addWidget(self.details_edit)
        r_layout.addWidget(details_box, stretch=2)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

    def on_state_updated(self, state: SystemState) -> None:
        v = state.vision
        lines = [
            "=== TARGET 6DoF SPECIFICATION ===",
            f"Target ID:          {v.selected_target_id or 'NONE'}",
            f"Class Name:         {v.target_class or '--'}",
            f"State Machine:      {v.detector_status}",
            f"Confidence:         {v.confidence:.2f}",
            f"Estimated Depth:    {f'{v.depth_m:.4f} m' if v.depth_m else '--'}",
            "",
            "=== CAMERA FRAME METRICS ===",
            f"Position X:         {v.pos_x:+.4f} m",
            f"Position Y:         {v.pos_y:+.4f} m",
            f"Position Z:         {v.pos_z:+.4f} m",
            f"Roll (X):           {v.roll:+.2f} °",
            f"Pitch (Y):          {v.pitch:+.2f} °",
            f"Yaw (Z):            {v.yaw:+.2f} °",
            "",
            "=== INFRARED DOT QUALITY ===",
            f"Valid Depth Dots:   {v.valid_dots} / {v.total_dots}",
            f"Pipeline FPS:       {v.fps:.1f} Hz",
        ]
        self.details_edit.setPlainText("\n".join(lines))
