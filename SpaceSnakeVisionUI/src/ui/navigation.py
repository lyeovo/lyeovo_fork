from __future__ import annotations

from typing import List, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class NavigationWidget(QWidget):
    pageChanged = Signal(int)
    estopTriggered = Signal()

    PAGES: List[Tuple[str, str, str]] = [
        ("MISSION", "🚀\nMISSION", "任务总览与流程监控"),
        ("VISION", "👁\nVISION", "视觉感知与6DoF精密测量"),
        ("TASK", "🎯\nTASK", "任务发布与地图选点操纵"),
        ("CONTROL", "🦾\nCONTROL", "机械臂位姿拓扑与关节状态"),
        ("COMPONENTS", "🧩\nCOMPS", "机构几何与舵机详细参数"),
        ("SYSTEM", "🖥\nSYSTEM", "系统诊断与健康状态监控"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(80)
        self.setObjectName("NavigationWidget")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(12)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for idx, (code, label, tooltip) in enumerate(self.PAGES):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.setObjectName(f"NavBtn_{code}")
            btn.setMinimumHeight(64)
            btn.setCursor(Qt.PointingHandCursor)
            self.btn_group.addButton(btn, idx)
            layout.addWidget(btn)

            if idx == 0:
                btn.setChecked(True)

        self.btn_group.idClicked.connect(self.pageChanged.emit)

        layout.addStretch()

        # 底端常驻 E-STOP 红色急停大按钮
        self.estop_btn = QPushButton("🛑\nE-STOP")
        self.estop_btn.setObjectName("NavEstopBtn")
        self.estop_btn.setMinimumHeight(64)
        self.estop_btn.setCursor(Qt.PointingHandCursor)
        self.estop_btn.clicked.connect(self.estopTriggered.emit)
        layout.addWidget(self.estop_btn)

    def set_current_page(self, index: int) -> None:
        btn = self.btn_group.button(index)
        if btn:
            btn.setChecked(True)
