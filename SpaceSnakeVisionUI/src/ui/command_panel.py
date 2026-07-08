from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QGridLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


class TaskCommandPanel(QWidget):
    generateRequested = Signal(str, str, float, str, str)
    publishRequested = Signal()
    estopRequested = Signal()
    cancelRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        self.task_type = self._combo(["move_near_target", "pick_target", "pick_and_place", "dock_to_interface", "home"])
        self.destination = self._combo(["Assembly_Port_A", "Assembly_Port_B", "Holding_Zone", "Safe_Zone"])
        self.approach = QDoubleSpinBox()
        self.approach.setRange(0.01, 0.5)
        self.approach.setSingleStep(0.01)
        self.approach.setValue(0.05)
        self.approach.setMinimumHeight(30)
        self.approach.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.speed = self._combo(["demo_safe", "low", "normal"])
        self.gripper = self._combo(["demo_grip", "soft_grip", "firm_grip"])

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 1)
        self._add_row(form, 0, "任务类型", self.task_type)
        self._add_row(form, 1, "放置/接口", self.destination)
        self._add_row(form, 2, "接近距离 m", self.approach)
        self._add_row(form, 3, "速度模式", self.speed)
        self._add_row(form, 4, "抓取模式", self.gripper)
        layout.addLayout(form)

        button_grid = QGridLayout()
        button_grid.setHorizontalSpacing(8)
        button_grid.setVerticalSpacing(8)
        self.generate_btn = self._button("生成任务")
        self.publish_btn = self._button("发布命令")
        self.cancel_btn = self._button("取消任务")
        self.estop_btn = self._button("急停")
        self.estop_btn.setObjectName("dangerButton")
        button_grid.addWidget(self.generate_btn, 0, 0)
        button_grid.addWidget(self.publish_btn, 0, 1)
        button_grid.addWidget(self.cancel_btn, 1, 0)
        button_grid.addWidget(self.estop_btn, 1, 1)
        layout.addLayout(button_grid)
        layout.addStretch(1)

        self.generate_btn.clicked.connect(self._generate)
        self.publish_btn.clicked.connect(self.publishRequested.emit)
        self.cancel_btn.clicked.connect(self.cancelRequested.emit)
        self.estop_btn.clicked.connect(self.estopRequested.emit)

    def _combo(self, values: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        combo.setMinimumHeight(30)
        combo.setMinimumWidth(150)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return combo

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(34)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def _add_row(self, layout: QGridLayout, row: int, text: str, widget: QWidget) -> None:
        label = QLabel(text)
        label.setMinimumWidth(82)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(label, row, 0)
        layout.addWidget(widget, row, 1)

    def _generate(self) -> None:
        self.generateRequested.emit(
            self.task_type.currentText(),
            self.destination.currentText(),
            float(self.approach.value()),
            self.speed.currentText(),
            self.gripper.currentText(),
        )
