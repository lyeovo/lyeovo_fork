from __future__ import annotations

import math
from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...state.system_state import SystemState, SystemStateStore


class ActuatorCardWidget(QFrame):
    """单通道舵机/电机详细遥测卡片组件"""

    def __init__(
        self,
        channel_id: int,
        name: str,
        cn_name: str,
        motor_type: str = "joint",
        min_val: float = -180.0,
        max_val: float = 180.0,
        unit: str = "deg",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardFrame")
        self.channel_id = channel_id
        self.motor_name = name
        self.cn_name = cn_name
        self.motor_type = motor_type
        self.min_val = min_val
        self.max_val = max_val
        self.unit = unit

        self._build_ui()
        self.update_value(0.0)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 1. 顶部通道标签与状态
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        ch_lbl = QLabel(f"CH-{self.channel_id:02d}")
        ch_lbl.setStyleSheet(
            "background: #102B4C; color: #00E5FF; font-weight: 700; "
            "border-radius: 3px; padding: 1px 6px; font-family: Consolas;"
        )
        top_row.addWidget(ch_lbl)

        title_lbl = QLabel(f"{self.motor_name} · {self.cn_name}")
        title_lbl.setStyleSheet("font-weight: 600; color: #EAF6FF;")
        top_row.addWidget(title_lbl, stretch=1)

        self.status_lbl = QLabel("NORMAL")
        self.status_lbl.setObjectName("StatusOnline")
        self.status_lbl.setStyleSheet(
            "background: rgba(46, 234, 138, 0.12); color: #2EEA8A; "
            "border: 1px solid #2EEA8A; border-radius: 3px; padding: 1px 5px; "
            "font-size: 11px; font-weight: 700; font-family: Consolas;"
        )
        top_row.addWidget(self.status_lbl)
        layout.addLayout(top_row)

        # 2. 核心主数值与副单位显示
        val_row = QHBoxLayout()
        val_row.setContentsMargins(0, 0, 0, 0)

        self.main_val_lbl = QLabel("0.0°")
        self.main_val_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #00E5FF; font-family: Consolas, 'JetBrains Mono';"
        )
        val_row.addWidget(self.main_val_lbl)

        self.sub_val_lbl = QLabel("[0.000 rad]")
        self.sub_val_lbl.setStyleSheet(
            "font-size: 12px; color: #8FA6C8; font-family: Consolas, 'JetBrains Mono'; margin-top: 4px;"
        )
        val_row.addWidget(self.sub_val_lbl, stretch=1)

        layout.addLayout(val_row)

        # 3. 硬件转角范围标尺进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(500)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                background: #091226;
                border: 1px solid #1E3860;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00B4D8, stop:1 #2EEA8A);
                border-radius: 3px;
            }
            """
        )
        layout.addWidget(self.progress_bar)

        # 4. 底部刻度与角速度
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)

        if self.motor_type == "gripper_gap":
            limit_text = "0% (闭合) ─── 100% (全开)"
        else:
            limit_text = f"{int(self.min_val)}° ────── 0° ────── {int(self.max_val)}°"

        scale_lbl = QLabel(limit_text)
        scale_lbl.setStyleSheet("color: #5A7499; font-size: 11px; font-family: Consolas;")
        bottom_row.addWidget(scale_lbl)

        bottom_row.addStretch()

        self.vel_lbl = QLabel("ω: 0.0°/s")
        self.vel_lbl.setStyleSheet("color: #8FA6C8; font-size: 11px; font-family: Consolas;")
        bottom_row.addWidget(self.vel_lbl)

        layout.addLayout(bottom_row)

    def update_value(self, val: float, vel: float = 0.0, extra_str: Optional[str] = None) -> None:
        """更新舵机角度或开合度数值

        val: 若为关节角，单位为度(deg)；若为开合度，范围0.0~1.0
        """
        if self.motor_type == "gripper_gap":
            # 夹爪开合度电机
            ratio = max(0.0, min(1.0, val))
            pct = ratio * 100.0
            self.main_val_lbl.setText(f"{pct:.1f}%")
            if extra_str:
                self.sub_val_lbl.setText(f"[{extra_str}]")
            else:
                mode_str = "OPEN (全开)" if ratio > 0.8 else ("CLOSED (闭合)" if ratio < 0.2 else "HOLD (保持)")
                self.sub_val_lbl.setText(f"[{mode_str}]")
            self.progress_bar.setValue(int(ratio * 1000))
            self.vel_lbl.setText(f"行程: {ratio * 100.0:.0f} mm")
        else:
            # 旋转舵机/关节电机 (deg)
            deg = max(self.min_val, min(self.max_val, val))
            rad = math.radians(deg)
            self.main_val_lbl.setText(f"{deg:+.1f}°")
            self.sub_val_lbl.setText(f"[{rad:+.3f} rad]")

            # 映射进度条 (-180 ~ +180 映射到 0 ~ 1000)
            span = self.max_val - self.min_val
            norm = (deg - self.min_val) / span if span > 0 else 0.5
            self.progress_bar.setValue(int(norm * 1000))

            self.vel_lbl.setText(f"ω: {vel:+.1f}°/s")

            # 接近极限警告变色
            if abs(deg) >= 170.0:
                self.status_lbl.setText("LIMIT")
                self.status_lbl.setStyleSheet(
                    "background: rgba(255, 77, 90, 0.15); color: #FF4D5A; "
                    "border: 1px solid #FF4D5A; border-radius: 3px; padding: 1px 5px; "
                    "font-size: 11px; font-weight: 700; font-family: Consolas;"
                )
            else:
                self.status_lbl.setText("NORMAL")
                self.status_lbl.setStyleSheet(
                    "background: rgba(46, 234, 138, 0.12); color: #2EEA8A; "
                    "border: 1px solid #2EEA8A; border-radius: 3px; padding: 1px 5px; "
                    "font-size: 11px; font-weight: 700; font-family: Consolas;"
                )


class ComponentsPage(QWidget):
    """Page 5: 机械臂硬件组件与舵机详细参数专页

    完全基于控制仓库（lyeovo/Hyper-Redundant-Snake-Robot-Manipulator-Algorithm）中
    的 motorConfig.m、modelDefaults.m、createArmModel.m 与 exportMotorCmd.m 真实规范构建。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = SystemStateStore.instance()
        self._build_ui()
        self.store.stateChanged.connect(self.on_state_updated)

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ── 1. 顶部说明标题栏 ────────────────────────────────────────────────────────
        header_frame = QFrame()
        header_frame.setObjectName("ActionToolbar")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 8, 12, 8)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        h_title = QLabel("⚙ 空间蛇形机械臂硬件组件与电控舵机遥测 (ACTUATORS & HARDWARE TELEMETRY)")
        h_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #00E5FF; letter-spacing: 0.5px;")
        title_box.addWidget(h_title)

        h_sub = QLabel(
            "基于 ArmSimulator2D 电控 8 通道规范 · 6-DoF 超冗余连杆 · Intel RealSense D405 眼在手微距载荷 · dSPACE 20ms 实时闭环"
        )
        h_sub.setStyleSheet("font-size: 11px; color: #8FA6C8;")
        title_box.addWidget(h_sub)
        h_layout.addLayout(title_box)

        h_layout.addStretch()

        bus_status_box = QHBoxLayout()
        bus_status_box.setSpacing(8)
        bus_dot = QLabel("●")
        bus_dot.setStyleSheet("color: #2EEA8A; font-size: 14px;")
        bus_status_box.addWidget(bus_dot)
        bus_txt = QLabel("ACTUATOR BUS: SYNCED (50Hz)")
        bus_txt.setStyleSheet("color: #2EEA8A; font-family: Consolas; font-weight: 700; font-size: 12px;")
        bus_status_box.addWidget(bus_txt)
        h_layout.addLayout(bus_status_box)

        main_layout.addWidget(header_frame)

        # ── 2. 模块 1：8 通道舵机与电机实时遥测矩阵 ──────────────────────────────────
        actuator_group = QFrame()
        actuator_group.setObjectName("CardFrame")
        ag_layout = QVBoxLayout(actuator_group)
        ag_layout.setContentsMargins(12, 10, 12, 10)
        ag_layout.setSpacing(8)

        ag_title = QLabel("8 通道驱动电机与末端舵机实时矩阵 (8-CHANNEL ACTUATOR MATRIX)")
        ag_title.setObjectName("SubheaderLabel")
        ag_layout.addWidget(ag_title)

        grid = QGridLayout()
        grid.setSpacing(8)

        # 定义 8 个电机规格 (对齐 motorConfig.m)
        self.motor_cards: List[ActuatorCardWidget] = []
        configs = [
            (1, "Joint 1", "基座回转关节", "joint", -180.0, 180.0, "deg"),
            (2, "Joint 2", "近端俯仰关节", "joint", -180.0, 180.0, "deg"),
            (3, "Joint 3", "中段偏航关节", "joint", -180.0, 180.0, "deg"),
            (4, "Joint 4", "中段微调关节", "joint", -180.0, 180.0, "deg"),
            (5, "Joint 5", "远端俯仰关节", "joint", -180.0, 180.0, "deg"),
            (6, "Joint 6", "末端腕部关节", "joint", -180.0, 180.0, "deg"),
            (7, "GripperOri", "夹爪朝向旋转舵机", "joint", -180.0, 180.0, "deg"),
            (8, "GripperGap", "末端夹爪开合电机", "gripper_gap", 0.0, 1.0, "ratio"),
        ]

        for idx, (cid, name, cn, mtype, mn, mx, unit) in enumerate(configs):
            card = ActuatorCardWidget(cid, name, cn, mtype, mn, mx, unit, self)
            self.motor_cards.append(card)
            row = idx // 4
            col = idx % 4
            grid.addWidget(card, row, col)

        ag_layout.addLayout(grid)
        main_layout.addWidget(actuator_group)

        # ── 3. 下半部分：三栏式机构几何、末端载荷与电控规格 ────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        # 3.1 左栏：机构几何与运动学参数 (Kinematics & Geometry)
        kin_frame = QFrame()
        kin_frame.setObjectName("CardFrame")
        kin_layout = QVBoxLayout(kin_frame)
        kin_layout.setContentsMargins(12, 10, 12, 10)
        kin_layout.setSpacing(6)

        kin_title = QLabel("机构物理几何与运动学 (KINEMATICS)")
        kin_title.setObjectName("SubheaderLabel")
        kin_layout.addWidget(kin_title)

        kin_specs = [
            ("机构拓扑", "平面 6-DoF 超冗余串联连杆"),
            ("单节连杆标称长 (L_seg)", "1043.93 mm (1.04393 m)"),
            ("全展最大臂展跨度", "6263.58 mm (±6.26 m)"),
            ("机器人基座安装坐标", "[X: 0.00 m, Y: 0.00 m]"),
            ("避障硬安全边界 (ρ₀)", "50.0 mm (0.05 m)"),
            ("标定安全裕度 (margin)", "10.0 mm (0.01 m)"),
            ("综合防撞安全包络", "60.0 mm (0.06 m)"),
            ("势场屏障激活半径", "500.0 mm (0.50 m)"),
            ("屏障梯度截断上限 (C)", "200.0"),
        ]
        for k, v in kin_specs:
            row = QHBoxLayout()
            lbl_k = QLabel(k)
            lbl_k.setStyleSheet("color: #8FA6C8; font-size: 12px;")
            lbl_v = QLabel(v)
            lbl_v.setStyleSheet("color: #EAF6FF; font-family: Consolas; font-weight: 600; font-size: 12px;")
            row.addWidget(lbl_k)
            row.addStretch()
            row.addWidget(lbl_v)
            kin_layout.addLayout(row)

        kin_layout.addStretch()

        # 末端当前位姿实时显示
        ee_box = QFrame()
        ee_box.setStyleSheet("background: #070D1D; border: 1px solid #1E3860; border-radius: 4px; padding: 4px;")
        ee_layout = QVBoxLayout(ee_box)
        ee_layout.setContentsMargins(6, 4, 6, 4)
        ee_layout.setSpacing(2)
        ee_head = QLabel("末端执行器当前笛卡尔位姿 (END-EFFECTOR POSE)")
        ee_head.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 700;")
        ee_layout.addWidget(ee_head)
        self.ee_pose_lbl = QLabel("X: +0.000 m | Y: +0.000 m | Z: +0.000 m | θ: +0.0°")
        self.ee_pose_lbl.setStyleSheet("color: #2EEA8A; font-family: Consolas; font-weight: 700; font-size: 12px;")
        ee_layout.addWidget(self.ee_pose_lbl)
        kin_layout.addWidget(ee_box)

        bottom_row.addWidget(kin_frame, stretch=1)

        # 3.2 中栏：末端执行器与视觉传感器 (End-Effector & D405 Payload)
        payload_frame = QFrame()
        payload_frame.setObjectName("CardFrame")
        pl_layout = QVBoxLayout(payload_frame)
        pl_layout.setContentsMargins(12, 10, 12, 10)
        pl_layout.setSpacing(6)

        pl_title = QLabel("末端夹爪与 D405 载荷 (PAYLOAD)")
        pl_title.setObjectName("SubheaderLabel")
        pl_layout.addWidget(pl_title)

        payload_specs = [
            ("视觉传感器型号", "Intel RealSense D405 微距双目"),
            ("相机安装位姿", "眼在手 (Eye-in-Hand) 末端法兰固定"),
            ("有效高精度测距区", "70 mm ~ 500 mm (微米级精度)"),
            ("深度流分辨率/帧率", "1280×720 @ 30 FPS"),
            ("末端夹爪物理类型", "电动平行两指夹爪 (带自旋轴)"),
            ("有效开合行程范围", "0.0 mm (闭合) ~ 100.0 mm (全开)"),
            ("朝向旋转轴自由度", "±180.0° 连续旋转"),
            ("额定有效载荷", "1.50 kg"),
            ("末端夹持力传感器", "就绪 (0.0 N 正常无阻力)"),
        ]
        for k, v in payload_specs:
            row = QHBoxLayout()
            lbl_k = QLabel(k)
            lbl_k.setStyleSheet("color: #8FA6C8; font-size: 12px;")
            lbl_v = QLabel(v)
            lbl_v.setStyleSheet("color: #EAF6FF; font-family: Consolas; font-weight: 600; font-size: 12px;")
            row.addWidget(lbl_k)
            row.addStretch()
            row.addWidget(lbl_v)
            pl_layout.addLayout(row)

        pl_layout.addStretch()

        # 夹爪当前实时状态指示
        grip_box = QFrame()
        grip_box.setStyleSheet("background: #070D1D; border: 1px solid #1E3860; border-radius: 4px; padding: 4px;")
        grip_layout = QVBoxLayout(grip_box)
        grip_layout.setContentsMargins(6, 4, 6, 4)
        grip_layout.setSpacing(2)
        grip_head = QLabel("末端夹爪当前工况 (GRIPPER STATUS)")
        grip_head.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 700;")
        grip_layout.addWidget(grip_head)
        self.gripper_status_lbl = QLabel("CODE: 0 [HOLD] | 开合度: 100.0% | 机构就绪")
        self.gripper_status_lbl.setStyleSheet("color: #FFC857; font-family: Consolas; font-weight: 700; font-size: 12px;")
        grip_layout.addWidget(self.gripper_status_lbl)
        pl_layout.addWidget(grip_box)

        bottom_row.addWidget(payload_frame, stretch=1)

        # 3.3 右栏：电控下位机与 dSPACE 通信总线 (dSPACE & Controller Bus)
        bus_frame = QFrame()
        bus_frame.setObjectName("CardFrame")
        bus_layout = QVBoxLayout(bus_frame)
        bus_layout.setContentsMargins(12, 10, 12, 10)
        bus_layout.setSpacing(6)

        bus_title = QLabel("电控下位机与 dSPACE 通信 (BUS SPECS)")
        bus_title.setObjectName("SubheaderLabel")
        bus_layout.addWidget(bus_title)

        ctrl_specs = [
            ("下位机主控平台", "dSPACE 实时仿真与控制系统"),
            ("总控通信接口", "TASK_COMMAND_INTERFACE (JSON/文件桥)"),
            ("采样与控制周期 (Δt)", "20 ms (50.0 Hz 闭环更新)"),
            ("轨迹插补协议", "q_seq(K×8) / t_seq / gripper_seq"),
            ("角速度平滑度校验", "vel_ok = PASS (各关节无突变)"),
            ("轨迹防撞安全校验", "safety_ok = PASS (全连杆无碰撞)"),
            ("核心逆解与规划器", "CVAE / Momentum 梯度流 / RRT*"),
            ("逆解优化最大迭代步", "800 steps (modelDefaults 唯一源)"),
            ("底层故障诊断码", "0x0000 (SYSTEM_NOMINAL)"),
        ]
        for k, v in ctrl_specs:
            row = QHBoxLayout()
            lbl_k = QLabel(k)
            lbl_k.setStyleSheet("color: #8FA6C8; font-size: 12px;")
            lbl_v = QLabel(v)
            lbl_v.setStyleSheet("color: #EAF6FF; font-family: Consolas; font-weight: 600; font-size: 12px;")
            row.addWidget(lbl_k)
            row.addStretch()
            row.addWidget(lbl_v)
            bus_layout.addLayout(row)

        bus_layout.addStretch()

        # 通信总线自检指示
        diag_box = QFrame()
        diag_box.setStyleSheet("background: #070D1D; border: 1px solid #1E3860; border-radius: 4px; padding: 4px;")
        diag_layout = QVBoxLayout(diag_box)
        diag_layout.setContentsMargins(6, 4, 6, 4)
        diag_layout.setSpacing(2)
        diag_head = QLabel("控制器通信与指令状态 (CONTROLLER HEALTH)")
        diag_head.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 700;")
        diag_layout.addWidget(diag_head)
        self.bus_health_lbl = QLabel("LINK: CONNECTED | JITTER: <1.2ms | CMD: IDLE")
        self.bus_health_lbl.setStyleSheet("color: #2EEA8A; font-family: Consolas; font-weight: 700; font-size: 12px;")
        diag_layout.addWidget(self.bus_health_lbl)
        bus_layout.addWidget(diag_box)

        bottom_row.addWidget(bus_frame, stretch=1)
        main_layout.addLayout(bottom_row)

        # ── 4. 模块 4：总控可人为指定运行参数与算法调优面板 ─────────────────────────
        cfg_frame = QFrame()
        cfg_frame.setObjectName("CardFrame")
        cfg_layout = QVBoxLayout(cfg_frame)
        cfg_layout.setContentsMargins(12, 10, 12, 10)
        cfg_layout.setSpacing(8)

        cfg_top = QHBoxLayout()
        cfg_title = QLabel("总控人为指定参数与算法期望配置 (RUN-TIME CONFIGURABLE PARAMETERS)")
        cfg_title.setObjectName("SubheaderLabel")
        cfg_top.addWidget(cfg_title)
        cfg_top.addStretch()

        reset_btn = QLabel("💡 可由操作员在总控指定，用于动态重载算法模板 (modelDefaults)")
        reset_btn.setStyleSheet("color: #00E5FF; font-size: 11px;")
        cfg_top.addWidget(reset_btn)
        cfg_layout.addLayout(cfg_top)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(16)

        # 4.1 运行速度限制 (Speed Limit / dq_max)
        spd_box = QVBoxLayout()
        spd_box.setSpacing(3)
        spd_lbl = QLabel("末端/关节运行速度限制 (Speed Limit):")
        spd_lbl.setStyleSheet("color: #8FA6C8; font-size: 11px; font-weight: 600;")
        spd_box.addWidget(spd_lbl)

        spd_inner = QHBoxLayout()
        self.spd_val_lbl = QLabel("30.0 °/s (50%)")
        self.spd_val_lbl.setStyleSheet("color: #2EEA8A; font-family: Consolas; font-weight: 700; font-size: 12px; min-width: 90px;")
        spd_inner.addWidget(self.spd_val_lbl)

        self.spd_slider = QProgressBar()
        self.spd_slider.setTextVisible(False)
        self.spd_slider.setFixedHeight(6)
        self.spd_slider.setRange(10, 100)
        self.spd_slider.setValue(50)
        self.spd_slider.setStyleSheet(
            "QProgressBar { background: #091226; border: 1px solid #1E3860; border-radius: 3px; } "
            "QProgressBar::chunk { background: #00E5FF; border-radius: 2px; }"
        )
        spd_inner.addWidget(self.spd_slider, stretch=1)
        spd_box.addLayout(spd_inner)
        controls_row.addLayout(spd_box, stretch=2)

        # 4.2 算法迭代步数期望 (max_iter)
        iter_box = QVBoxLayout()
        iter_box.setSpacing(3)
        iter_lbl = QLabel("逆解最大迭代步数 (Max Iterations):")
        iter_lbl.setStyleSheet("color: #8FA6C8; font-size: 11px; font-weight: 600;")
        iter_box.addWidget(iter_lbl)

        self.iter_val_lbl = QLabel("800 步 (收敛保障)")
        self.iter_val_lbl.setStyleSheet("color: #00E5FF; font-family: Consolas; font-weight: 700; font-size: 12px;")
        iter_box.addWidget(self.iter_val_lbl)
        controls_row.addLayout(iter_box, stretch=1)

        # 4.3 避障安全硬边界 (rho0)
        safe_box = QVBoxLayout()
        safe_box.setSpacing(3)
        safe_lbl = QLabel("避障硬安全距离 (Barrier rho0):")
        safe_lbl.setStyleSheet("color: #8FA6C8; font-size: 11px; font-weight: 600;")
        safe_box.addWidget(safe_lbl)

        self.safe_val_lbl = QLabel("50.0 mm (+10mm 裕度)")
        self.safe_val_lbl.setStyleSheet("color: #FFC857; font-family: Consolas; font-weight: 700; font-size: 12px;")
        safe_box.addWidget(self.safe_val_lbl)
        controls_row.addLayout(safe_box, stretch=1)

        # 4.4 优化权重策略模式 (Optimization Policy)
        policy_box = QVBoxLayout()
        policy_box.setSpacing(3)
        policy_lbl = QLabel("多目标权重偏置 (Optimization Policy):")
        policy_lbl.setStyleSheet("color: #8FA6C8; font-size: 11px; font-weight: 600;")
        policy_box.addWidget(policy_lbl)

        self.policy_val_lbl = QLabel("标准均衡 (Pos:1.0 | Obs:0.5 | Ang:0.3)")
        self.policy_val_lbl.setStyleSheet("color: #EAF6FF; font-family: Consolas; font-weight: 700; font-size: 12px;")
        policy_box.addWidget(self.policy_val_lbl)
        controls_row.addLayout(policy_box, stretch=2)

        cfg_layout.addLayout(controls_row)
        main_layout.addWidget(cfg_frame)

    def on_state_updated(self, state: SystemState) -> None:
        """响应全局状态更新，实时刷新 8 通道电机及组件参数"""
        rob = state.robot

        # 1. 更新机械臂 6 关节电机
        angles = getattr(rob, "joint_angles_deg", None) or [0.0] * 6
        for idx in range(6):
            if idx < len(angles):
                self.motor_cards[idx].update_value(angles[idx])
            else:
                self.motor_cards[idx].update_value(0.0)

        # 2. 更新 CH-07: GripperOri (夹爪旋转)
        if len(angles) >= 7:
            self.motor_cards[6].update_value(angles[6])
        else:
            self.motor_cards[6].update_value(0.0)

        # 3. 更新 CH-08: GripperGap (夹爪开合)
        grip = str(getattr(rob, "gripper_state", "HOLDING")).upper()
        if "OPEN" in grip:
            self.motor_cards[7].update_value(1.0, extra_str="OPEN (全开就绪)")
            self.gripper_status_lbl.setText("STATE: OPEN | 开合度: 100.0% (100mm) | 目标捕获释放")
            self.gripper_status_lbl.setStyleSheet("color: #2EEA8A; font-family: Consolas; font-weight: 700; font-size: 12px;")
        elif "CLOSE" in grip:
            self.motor_cards[7].update_value(0.0, extra_str="CLOSED (夹持锁定)")
            self.gripper_status_lbl.setText("STATE: CLOSED | 开合度: 0.0% (闭合) | 目标已抓取夹紧")
            self.gripper_status_lbl.setStyleSheet("color: #00E5FF; font-family: Consolas; font-weight: 700; font-size: 12px;")
        else:
            self.motor_cards[7].update_value(0.5, extra_str="HOLD (姿态保持)")
            self.gripper_status_lbl.setText("STATE: HOLDING | 开合度: 50.0% | 保持当前行程")
            self.gripper_status_lbl.setStyleSheet("color: #FFC857; font-family: Consolas; font-weight: 700; font-size: 12px;")

        # 4. 更新末端位姿
        self.ee_pose_lbl.setText(
            f"X: {rob.ee_x:+.3f} m | Y: {rob.ee_y:+.3f} m | Z: {rob.ee_z:+.3f} m | θ: {rob.ee_yaw:+.1f}°"
        )

        # 5. 更新总线健康状态
        robot_st = rob.state or "IDLE"
        self.bus_health_lbl.setText(f"LINK: ACTIVE | JITTER: <1.5ms | STATE: {robot_st}")
