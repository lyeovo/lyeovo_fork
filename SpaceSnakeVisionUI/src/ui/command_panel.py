from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


TASK_TYPES = [
    ("move_to", "move_to (x, y) - 移动到指定坐标"),
    ("move_along", "move_along (θ, d) - 沿方向移动"),
    ("move_for_pick", "move_for_pick - 靠近抓取目标"),
    ("move_for_place", "move_for_place - 移动至放置位置"),
    ("rotate", "rotate (α) - 末端旋转"),
    ("rotate_arm", "rotate_arm (α, n) - 关节旋转"),
    ("facing_arm", "facing_arm (θ, n) - 关节点向"),
    ("pick", "pick - 夹爪抓取动作"),
    ("place", "place - 夹爪释放动作"),
    ("withdraw", "withdraw - 退回上一状态"),
    ("reset", "reset - 恢复初始位置"),
]


class TaskCommandPanel(QWidget):
    generateRequested = Signal(str, dict)  # command_type, params
    publishRequested = Signal()
    estopRequested = Signal()
    cancelRequested = Signal()
    commandTypeChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # 任务类型选择器
        self.task_type_combo = QComboBox()
        for cmd_type, display_text in TASK_TYPES:
            self.task_type_combo.addItem(display_text, userData=cmd_type)
        self.task_type_combo.setMinimumHeight(30)
        self.task_type_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        type_row = QHBoxLayout()
        type_label = QLabel("任务类型")
        type_label.setMinimumWidth(80)
        type_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        type_row.addWidget(type_label)
        type_row.addWidget(self.task_type_combo, 1)
        layout.addLayout(type_row)

        # 动态参数栈式表单容器
        self.param_stack = QStackedWidget()
        self._build_param_forms()
        layout.addWidget(self.param_stack)

        self.task_type_combo.currentIndexChanged.connect(self._on_type_changed)

        # 底部动作按钮组
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

        # 指令生成结果预览与安全校验标签
        self.validation_label = QLabel("安全状态: 就绪待生成")
        self.validation_label.setStyleSheet("color: #00E5FF; font-size: 11px;")
        layout.addWidget(self.validation_label)

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(100)
        self.preview_edit.setPlaceholderText("生成的指令 JSON 报文将在此预览...")
        self.preview_edit.setObjectName("LogConsole")
        layout.addWidget(self.preview_edit)

        layout.addStretch(1)

        self.generate_btn.clicked.connect(self._generate)
        self.publish_btn.clicked.connect(self.publishRequested.emit)
        self.cancel_btn.clicked.connect(self.cancelRequested.emit)
        self.estop_btn.clicked.connect(self.estopRequested.emit)

    def set_preview(self, json_str: str, report: Optional[dict] = None) -> None:
        self.preview_edit.setPlainText(json_str)
        if report:
            ok = bool(report.get("validation_passed", False))
            msg = str(report.get("validation_message", "未知校验"))
            color = "#2EEA8A" if ok else "#FF4D5A"
            self.validation_label.setText(f"安全状态: {msg}")
            self.validation_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")

    def _build_param_forms(self) -> None:
        # Form 0: move_to (x, y)
        w_move_to = QWidget()
        f0 = QGridLayout(w_move_to)
        f0.setContentsMargins(0, 0, 0, 0)
        self.move_to_x = self._double_spin(-6.0, 6.0, 0.35, step=0.01, decimals=3, suffix=" m")
        self.move_to_y = self._double_spin(0.0, 6.0, 0.20, step=0.01, decimals=3, suffix=" m")
        self._add_field(f0, 0, "目标 X", self.move_to_x)
        self._add_field(f0, 1, "目标 Y", self.move_to_y)
        hint0 = QLabel("💡 提示：可在下方地图中点击快速选点（仅限前方 Y≥0，后方为墙体）")
        hint0.setStyleSheet("color: #00E5FF; font-size: 11px;")
        f0.addWidget(hint0, 2, 0, 1, 2, Qt.AlignCenter)
        self.param_stack.addWidget(w_move_to)

        # Form 1: move_along (theta, d)
        w_move_along = QWidget()
        f1 = QGridLayout(w_move_along)
        f1.setContentsMargins(0, 0, 0, 0)
        self.move_along_theta = self._double_spin(-180.0, 180.0, 0.0, step=1.0, decimals=1, suffix=" °")
        self.move_along_d = self._double_spin(0.01, 6.0, 0.10, step=0.01, decimals=3, suffix=" m")
        self._add_field(f1, 0, "方向角 θ", self.move_along_theta)
        self._add_field(f1, 1, "移动距离 d", self.move_along_d)
        self.param_stack.addWidget(w_move_along)

        # Form 2: move_for_pick
        w_pick_move = QWidget()
        f2 = QVBoxLayout(w_pick_move)
        f2.setContentsMargins(0, 4, 0, 4)
        hint2 = QLabel("🎯 实时视觉引导：根据当前锁定的目标相对位姿自动生成靠近动作")
        hint2.setWordWrap(True)
        hint2.setStyleSheet("color: #2EEA8A; font-size: 12px;")
        f2.addWidget(hint2)
        self.param_stack.addWidget(w_pick_move)

        # Form 3: move_for_place
        w_place_move = QWidget()
        f3 = QGridLayout(w_place_move)
        f3.setContentsMargins(0, 0, 0, 0)
        self.place_dest_combo = QComboBox()
        self.place_dest_combo.addItems(["Goal_Zone"])
        self.place_dest_combo.setMinimumHeight(30)
        self._add_field(f3, 0, "放置工位", self.place_dest_combo)
        hint3 = QLabel("📦 硬编码轨迹：向预设放置区移动")
        hint3.setStyleSheet("color: #FFC857; font-size: 11px;")
        f3.addWidget(hint3, 1, 0, 1, 2, Qt.AlignCenter)
        self.param_stack.addWidget(w_place_move)

        # Form 4: rotate (alpha)
        w_rot = QWidget()
        f4 = QGridLayout(w_rot)
        f4.setContentsMargins(0, 0, 0, 0)
        self.rotate_alpha = self._double_spin(-180.0, 180.0, 30.0, step=1.0, decimals=1, suffix=" °")
        self._add_field(f4, 0, "旋转角 α", self.rotate_alpha)
        self.param_stack.addWidget(w_rot)

        # Form 5: rotate_arm (alpha, n)
        w_rot_arm = QWidget()
        f5 = QGridLayout(w_rot_arm)
        f5.setContentsMargins(0, 0, 0, 0)
        self.rot_arm_n = self._spin(1, 6, 1)
        self.rot_arm_alpha = self._double_spin(-180.0, 180.0, 15.0, step=1.0, decimals=1, suffix=" °")
        self._add_field(f5, 0, "关节编号 n", self.rot_arm_n)
        self._add_field(f5, 1, "旋转角 α", self.rot_arm_alpha)
        self.param_stack.addWidget(w_rot_arm)

        # Form 6: facing_arm (theta, n)
        w_facing_arm = QWidget()
        f6 = QGridLayout(w_facing_arm)
        f6.setContentsMargins(0, 0, 0, 0)
        self.facing_arm_n = self._spin(1, 6, 1)
        self.facing_arm_theta = self._double_spin(-180.0, 180.0, 0.0, step=1.0, decimals=1, suffix=" °")
        self._add_field(f6, 0, "关节编号 n", self.facing_arm_n)
        self._add_field(f6, 1, "面向方位 θ", self.facing_arm_theta)
        self.param_stack.addWidget(w_facing_arm)

        # Form 7: pick
        w_act_pick = QWidget()
        f7 = QVBoxLayout(w_act_pick)
        hint7 = QLabel("🦾 执行抓取：触发末端夹爪抓取动作链")
        hint7.setStyleSheet("color: #00E5FF; font-size: 12px;")
        f7.addWidget(hint7)
        self.param_stack.addWidget(w_act_pick)

        # Form 8: place
        w_act_place = QWidget()
        f8 = QVBoxLayout(w_act_place)
        hint8 = QLabel("🤲 执行放置：触发末端夹爪释放/放置动作链")
        hint8.setStyleSheet("color: #00E5FF; font-size: 12px;")
        f8.addWidget(hint8)
        self.param_stack.addWidget(w_act_place)

        # Form 9: withdraw
        w_withdraw = QWidget()
        f9 = QVBoxLayout(w_withdraw)
        hint9 = QLabel("⏪ 状态退回：机械臂退回上一动作前状态")
        hint9.setStyleSheet("color: #FFC857; font-size: 12px;")
        f9.addWidget(hint9)
        self.param_stack.addWidget(w_withdraw)

        # Form 10: reset
        w_reset = QWidget()
        f10 = QVBoxLayout(w_reset)
        hint10 = QLabel("🔄 初始复位：机械臂恢复至安全零位")
        hint10.setStyleSheet("color: #FFC857; font-size: 12px;")
        f10.addWidget(hint10)
        self.param_stack.addWidget(w_reset)

    def _on_type_changed(self, index: int) -> None:
        self.param_stack.setCurrentIndex(index)
        cmd_type = self.current_command_type()
        self.commandTypeChanged.emit(cmd_type)

    def current_command_type(self) -> str:
        return self.task_type_combo.currentData()

    def set_target_coordinate(self, x: float, y: float) -> None:
        """从外部（如地图点击）快速填入坐标（后方墙体防护，Y >= 0）"""
        idx = self.task_type_combo.findData("move_to")
        if idx >= 0 and self.task_type_combo.currentIndex() != idx:
            self.task_type_combo.setCurrentIndex(idx)
        self.move_to_x.setValue(x)
        self.move_to_y.setValue(max(0.0, y))

    def _double_spin(self, min_val: float, max_val: float, val: float, step: float = 0.01, decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setValue(val)
        if suffix:
            spin.setSuffix(suffix)
        spin.setMinimumHeight(30)
        spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return spin

    def _spin(self, min_val: int, max_val: int, val: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(val)
        spin.setMinimumHeight(30)
        spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return spin

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(34)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def _add_field(self, layout: QGridLayout, row: int, text: str, widget: QWidget) -> None:
        label = QLabel(text)
        label.setMinimumWidth(80)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(label, row, 0)
        layout.addWidget(widget, row, 1)

    def _generate(self) -> None:
        cmd_type = self.current_command_type()
        params = {}
        if cmd_type == "move_to":
            params = {
                "x": round(float(self.move_to_x.value()), 4),
                "y": round(float(self.move_to_y.value()), 4),
            }
        elif cmd_type == "move_along":
            params = {
                "theta_deg": round(float(self.move_along_theta.value()), 2),
                "distance_m": round(float(self.move_along_d.value()), 4),
            }
        elif cmd_type == "move_for_pick":
            params = {}
        elif cmd_type == "move_for_place":
            params = {
                "destination": self.place_dest_combo.currentText(),
            }
        elif cmd_type == "rotate":
            params = {
                "alpha_deg": round(float(self.rotate_alpha.value()), 2),
            }
        elif cmd_type == "rotate_arm":
            params = {
                "joint_index": int(self.rot_arm_n.value()),
                "alpha_deg": round(float(self.rot_arm_alpha.value()), 2),
            }
        elif cmd_type == "facing_arm":
            params = {
                "joint_index": int(self.facing_arm_n.value()),
                "theta_deg": round(float(self.facing_arm_theta.value()), 2),
            }
        elif cmd_type in ("pick", "place", "withdraw", "reset"):
            params = {}

        self.generateRequested.emit(cmd_type, params)
