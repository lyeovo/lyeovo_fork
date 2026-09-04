from __future__ import annotations

import math
from typing import List, Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...state.system_state import SystemState, SystemStateStore


class SnakeRobotViewWidget(QWidget):
    """蛇形机械臂骨骼姿态 2D 拓扑图"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self.joint_angles_deg: List[float] = [0.0, 15.0, -20.0, 30.0, -10.0, 5.0]

    def set_joint_angles(self, angles: List[float]) -> None:
        self.joint_angles_deg = list(angles)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#050814"))

        w, h = self.width(), self.height()
        origin = QPointF(w * 0.25, h * 0.75)

        # 绘制背景网格
        grid_pen = QPen(QColor("#0F223D"), 1, Qt.DotLine)
        painter.setPen(grid_pen)
        for x in range(0, w, 40):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 40):
            painter.drawLine(0, y, w, y)

        # 绘制机器人基座
        painter.setPen(QPen(QColor("#00E5FF"), 2))
        painter.setBrush(QColor(0, 229, 255, 40))
        painter.drawEllipse(origin, 10, 10)
        painter.drawText(origin.x() - 25, origin.y() + 24, "BASE (0,0)")

        # 顺向运动学连杆连线绘制 (简化 2D 骨骼，连杆长度 45px)
        seg_len = min(w, h) * 0.09
        cur_pt = origin
        accum_angle = 0.0

        painter.setPen(QPen(QColor("#2EEA8A"), 3))

        for idx, ang_deg in enumerate(self.joint_angles_deg):
            accum_angle += math.radians(ang_deg)
            # 基础延伸方向朝右上
            rad = -math.pi / 4 + accum_angle
            next_pt = QPointF(cur_pt.x() + seg_len * math.cos(rad), cur_pt.y() + seg_len * math.sin(rad))

            # 画杆
            painter.setPen(QPen(QColor("#00E5FF"), 3))
            painter.drawLine(cur_pt, next_pt)

            # 画关节圆点
            painter.setPen(QPen(QColor("#FFC857"), 2))
            painter.setBrush(QColor("#FFC857"))
            painter.drawEllipse(next_pt, 4, 4)

            cur_pt = next_pt

        # 绘制末端执行器夹爪标记
        painter.setPen(QPen(QColor("#FF0055"), 2))
        painter.setBrush(QColor(255, 0, 85, 80))
        painter.drawEllipse(cur_pt, 7, 7)
        painter.drawText(cur_pt.x() + 10, cur_pt.y() - 4, "EE (End-Effector)")

        painter.end()


class ControlPage(QWidget):
    """Page 4: 运动控制与关节动力学专页"""

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

        # 左侧：机械臂拓扑视图
        robot_box = QFrame()
        robot_box.setObjectName("CardFrame")
        rb_layout = QVBoxLayout(robot_box)
        rb_layout.setContentsMargins(6, 6, 6, 6)
        rb_title = QLabel("SNAKE KINEMATIC TOPOLOGY · 蛇形臂运动学拓扑与姿态")
        rb_title.setObjectName("SubheaderLabel")
        rb_layout.addWidget(rb_title)

        self.robot_view = SnakeRobotViewWidget()
        rb_layout.addWidget(self.robot_view, stretch=1)
        splitter.addWidget(robot_box)

        # 右侧：关节角矩阵与规划器指标
        right_panel = QWidget()
        rp_layout = QVBoxLayout(right_panel)
        rp_layout.setContentsMargins(0, 0, 0, 0)
        rp_layout.setSpacing(8)

        # 关节角度监视
        joint_box = QFrame()
        joint_box.setObjectName("CardFrame")
        jb_layout = QVBoxLayout(joint_box)
        jb_layout.setContentsMargins(8, 8, 8, 8)
        jb_title = QLabel("JOINT ANGLES TELEMETRY · 关节转角遥测矩阵")
        jb_title.setObjectName("SubheaderLabel")
        jb_layout.addWidget(jb_title)

        self.joint_bars: List[QProgressBar] = []
        self.joint_labels: List[QLabel] = []

        grid = QGridLayout()
        grid.setSpacing(8)
        for i in range(6):
            lbl = QLabel(f"Joint {i+1}: 0.0°")
            lbl.setObjectName("TelemetryLabel")
            bar = QProgressBar()
            bar.setRange(-180, 180)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(14)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(bar, i, 1)
            self.joint_labels.append(lbl)
            self.joint_bars.append(bar)

        jb_layout.addLayout(grid)
        rp_layout.addWidget(joint_box)

        # 规划器状态与参数
        planner_box = QFrame()
        planner_box.setObjectName("CardFrame")
        pb_layout = QVBoxLayout(planner_box)
        pb_layout.setContentsMargins(8, 8, 8, 8)
        pb_title = QLabel("PLANNER STATUS · 运动规划算法与驱动链路")
        pb_title.setObjectName("SubheaderLabel")
        pb_layout.addWidget(pb_title)

        self.planner_info = QLabel("Awaiting control telemetry…")
        self.planner_info.setObjectName("TelemetryLabel")
        pb_layout.addWidget(self.planner_info)
        rp_layout.addWidget(planner_box)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        # 用当前状态初始化关节条与规划器信息，避免首帧显示占位/假数据
        self.on_state_updated(self.store.state)

    def _build_planner_text(self, state: SystemState) -> str:
        c = state.command
        r = state.robot
        h = state.health

        prog = f"{(c.progress or 0.0) * 100.0:.0f}%"
        solve = f"{r.solve_time_ms:.1f} ms" if r.solve_time_ms is not None else "—"
        track = f"{r.tracking_error_mm:.2f} mm" if r.tracking_error_mm is not None else "—"
        angle = f"{r.angle_error_deg:.2f}°" if r.angle_error_deg is not None else "—"
        dspace = "CONNECTED (TCP)" if h.dspace_connected else "STANDBY (TCP reserved)"
        ee = f"x={r.ee_x:+.3f}  y={r.ee_y:+.3f}  θ={r.ee_yaw:+.1f}°"

        return (
            f"Execution State:    {c.control_status}\n"
            f"Active Command:     {c.command_type or '--'}\n"
            f"Progress:           {prog}\n"
            f"Planner Method:     {r.method_used}\n"
            f"IK Solve Time:      {solve}\n"
            f"Tracking Error:     {track}\n"
            f"Angle Error:        {angle}\n"
            f"EE Pose (base):     {ee}\n"
            f"dSPACE Controller:  {dspace}\n"
            f"Gripper:            {r.gripper_state}"
        )

    def on_state_updated(self, state: SystemState) -> None:
        angles = state.robot.joint_angles_deg or [0.0] * 6
        self.robot_view.set_joint_angles(angles)
        for i, val in enumerate(angles[:6]):
            if i < len(self.joint_labels):
                self.joint_labels[i].setText(f"Joint {i+1}: {val:+.1f}°")
                self.joint_bars[i].setValue(int(val))
        self.planner_info.setText(self._build_planner_text(state))
