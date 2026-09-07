import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


# 机械臂几何：6 节 × 1.04393m，平面全伸展最大作业半径 ≈6.26m
N_SEGMENTS = 6
SEG_LEN_M = 1.04393  # 真实连杆标称长度（对齐 modelDefaults.m）
MAX_REACH_M = 6.0  # 显示范围保持 ±6m
GRID_STEP_M = 1.0
RANGE_ARCS_M = (2.0, 4.0, 6.0)

# 终点区域：地图右侧的单一放置区（世界坐标矩形，单位 m）
GOAL_ZONE = {"x_min": 3.2, "x_max": 4.8, "y_min": 1.2, "y_max": 2.8}
GOAL_CENTER = (
    (GOAL_ZONE["x_min"] + GOAL_ZONE["x_max"]) / 2.0,
    (GOAL_ZONE["y_min"] + GOAL_ZONE["y_max"]) / 2.0,
)  # (4.0, 2.0)


class MissionMapWidget(QWidget):
    coordinateSelected = Signal(float, float)  # x (m), y (m)
    targetSelected = Signal(str)  # 选中目标的 target_id

    def __init__(self) -> None:
        super().__init__()
        self.objects = []
        self.selected_id: Optional[str] = None
        self.selected_waypoint: Optional[Tuple[float, float]] = None
        self.hover_coord: Optional[Tuple[float, float]] = None
        # 机械臂关节角度（度），用于在地图上绘制连杆姿态
        self.joint_angles_deg: List[float] = [0.0] * N_SEGMENTS
        # 夹爪状态：OPEN / CLOSED / HOLDING
        self.gripper_state: str = "OPEN"
        self.setMinimumHeight(200)
        self.setMouseTracking(True)

        # 逐帧平滑慢放过渡动画 (30 FPS, 每步 33ms)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._on_anim_step)
        self._anim_start_angles: List[float] = [0.0] * N_SEGMENTS
        self._anim_target_angles: List[float] = [0.0] * N_SEGMENTS
        self._anim_step: int = 0
        self._anim_total_steps: int = 24  # 24 帧慢放平滑过渡（约 0.8 秒丝滑游动）

    def set_joint_angles(self, angles: List[float], gripper_state: str = "OPEN") -> None:
        """更新机械臂关节角度与夹爪状态，启动逐帧平滑慢放动画"""
        raw = list(angles)
        target = list(raw[:N_SEGMENTS]) if len(raw) >= N_SEGMENTS else list(raw) + [0.0] * (N_SEGMENTS - len(raw))
        self.gripper_state = gripper_state

        # 若角度变化极小 (<0.1度)，直接同步无延迟
        if all(abs(c - t) < 0.1 for c, t in zip(self.joint_angles_deg, target)):
            self.joint_angles_deg = target
            self.update()
            return

        # 启动逐帧平滑插值动画
        self._anim_start_angles = list(self.joint_angles_deg)
        self._anim_target_angles = target
        self._anim_step = 0
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _on_anim_step(self) -> None:
        """逐帧更新机械臂关节角度（Smoothstep 缓动）"""
        self._anim_step += 1
        progress = min(1.0, self._anim_step / float(self._anim_total_steps))
        # 三次平滑曲线 (Smoothstep)
        ease = progress * progress * (3.0 - 2.0 * progress)
        self.joint_angles_deg = [
            round(s + (t - s) * ease, 2)
            for s, t in zip(self._anim_start_angles, self._anim_target_angles)
        ]
        self.update()
        if progress >= 1.0:
            self._anim_timer.stop()

    def update_map(self, objects, selected_id: Optional[str] = None) -> None:
        self.objects = list(objects)
        self.selected_id = selected_id
        self.update()

    def set_waypoint(self, x: float, y: float) -> None:
        self.selected_waypoint = (x, y)
        self.update()

    def clear_waypoint(self) -> None:
        self.selected_waypoint = None
        self.update()

    def _get_origin_and_scale(self) -> Tuple[float, float, float, float]:
        """返回 (origin_x, origin_y, scale_x, scale_y)

        等比缩放（scale_x == scale_y），完整显示机械臂 ±MAX_REACH_M 的可达区域，
        基座水平居中、靠近底部，保证测距圆弧为正圆、距离比例真实。
        """
        w = max(100, self.width())
        h = max(100, self.height())
        origin_x = w * 0.50
        origin_y = h * 0.82
        # 可达区域: X: [-6, +6] m (宽 12m), Y: [0, 6] m (长 6m，前方半圆)
        scale_from_width = (w * 0.90) / (2.0 * MAX_REACH_M)
        scale_from_height = (h * 0.78) / MAX_REACH_M
        scale = min(scale_from_width, scale_from_height)
        return origin_x, origin_y, scale, scale

    def world_to_pixel(self, x: float, y: float) -> QPointF:
        ox, oy, sx, sy = self._get_origin_and_scale()
        px = ox + x * sx
        py = oy - y * sy
        return QPointF(px, py)

    def pixel_to_world(self, px: float, py: float) -> Tuple[float, float]:
        ox, oy, sx, sy = self._get_origin_and_scale()
        x = (px - ox) / max(1e-6, sx)
        y = (oy - py) / max(1e-6, sy)
        return x, y

    def mouseMoveEvent(self, event) -> None:
        pos = event.position() if hasattr(event, "position") else event.pos()
        x, y = self.pixel_to_world(pos.x(), pos.y())
        self.hover_coord = (round(x, 3), round(y, 3))
        self.update()

    def leaveEvent(self, event) -> None:
        self.hover_coord = None
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            pos = event.position() if hasattr(event, "position") else event.pos()
            x, y = self.pixel_to_world(pos.x(), pos.y())
            # 限制在机械臂前方可达作业范围内 (X: ±MAX_REACH_M, Y: [0.0, MAX_REACH_M])
            # 物理防护墙体位于后方 (Y <= 0)，严禁越界进入墙体
            clamped_x = round(max(-MAX_REACH_M, min(MAX_REACH_M, x)), 3)
            clamped_y = round(max(0.0, min(MAX_REACH_M, y)), 3)

            # 优先检查是否点击了已有的目标靶标 (点击吸附与选择，容差半径 0.40m)
            clicked_obj_id = None
            for obj in self.objects:
                pos_x, pos_y = None, None
                if getattr(obj, "pose_base", None) is not None:
                    pb = obj.pose_base.position
                    pos_x, pos_y = pb.x, (pb.y if abs(pb.y) > 1e-4 else pb.z)
                elif getattr(obj, "pose_camera", None) is not None and obj.pose_camera.position.z > 0.02:
                    pos_x, pos_y = self.camera_to_world_coord(obj.pose_camera.position.x, obj.pose_camera.position.z)

                if pos_x is not None and pos_y is not None:
                    # 仅吸附位于前方 Y >= 0 的目标
                    if pos_y >= 0.0 and math.hypot(pos_x - clamped_x, pos_y - clamped_y) <= 0.40:
                        clicked_obj_id = obj.target_id
                        clamped_x, clamped_y = round(pos_x, 3), round(pos_y, 3)
                        break

            self.selected_waypoint = (clamped_x, clamped_y)
            if clicked_obj_id:
                self.selected_id = clicked_obj_id
                self.targetSelected.emit(clicked_obj_id)
            self.coordinateSelected.emit(clamped_x, clamped_y)
            self.update()

    def compute_forward_kinematics(self) -> Tuple[List[Tuple[float, float]], float]:
        """顺向运动学 (FK): 返回所有关节的世界坐标点列表及末端切向朝向角 accum_angle (弧度)"""
        cur_x, cur_y = 0.0, 0.0  # 基座世界坐标 (0, 0)
        accum_angle = math.pi / 2.0  # 初始朝向：垂直向上伸展（正前方 +Y 轴）
        joint_world_pts: List[Tuple[float, float]] = [(cur_x, cur_y)]
        n_draw = max(N_SEGMENTS, len(self.joint_angles_deg))
        for idx in range(n_draw):
            ang_deg = self.joint_angles_deg[idx] if idx < len(self.joint_angles_deg) else 0.0
            accum_angle += math.radians(ang_deg)
            next_x = cur_x + SEG_LEN_M * math.cos(accum_angle)
            next_y = cur_y + SEG_LEN_M * math.sin(accum_angle)
            joint_world_pts.append((next_x, next_y))
            cur_x, cur_y = next_x, next_y
        return joint_world_pts, accum_angle

    def camera_to_world_coord(self, cam_x: float, cam_z: float) -> Tuple[float, float]:
        """将末端相机坐标系下的相对位姿 (cam_x, cam_z) 转换到机械臂空间基座物理坐标系 (world_x, world_y)

        相机安装在机械臂末端 (Eye-in-Hand):
        - cam_z 为相机光轴前向深度，沿着末端当前伸展朝向 ee_angle
        - cam_x 为相机水平向右偏差，沿着末端右侧法向 (ee_angle - 90°)
        """
        joint_pts, ee_angle = self.compute_forward_kinematics()
        ee_x, ee_y = joint_pts[-1]
        # 前向单位向量: (cos(ee_angle), sin(ee_angle))
        # 右侧单位向量: (sin(ee_angle), -cos(ee_angle))
        world_x = ee_x + cam_z * math.cos(ee_angle) + cam_x * math.sin(ee_angle)
        world_y = ee_y + cam_z * math.sin(ee_angle) - cam_x * math.cos(ee_angle)
        return world_x, world_y

    def _draw_robot_arm(self, painter: QPainter) -> None:
        """在俯视地图上绘制机械臂 6 节连杆骨骼、关节与末端夹爪"""
        joint_world_pts, accum_angle = self.compute_forward_kinematics()

        # 将世界坐标转换为像素坐标
        joint_pixel_pts = [self.world_to_pixel(wx, wy) for wx, wy in joint_world_pts]

        # 绘制连杆（粗青蓝色线段）
        link_pen = QPen(QColor(0, 229, 255, 180), 3)
        painter.setPen(link_pen)
        for i in range(len(joint_pixel_pts) - 1):
            painter.drawLine(joint_pixel_pts[i], joint_pixel_pts[i + 1])

        # 绘制关节圆点（金黄色小圆，标注关节编号）
        joint_font = QFont("Consolas", 7)
        painter.setFont(joint_font)
        for i in range(1, len(joint_pixel_pts) - 1):  # 跳过基座和末端
            pt = joint_pixel_pts[i]
            painter.setPen(QPen(QColor("#FFC857"), 2))
            painter.setBrush(QColor("#FFC857"))
            painter.drawEllipse(pt, 4, 4)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor(255, 200, 87, 160))
            painter.drawText(pt.x() + 6, pt.y() - 3, f"J{i}")

        # 绘制末端执行器夹爪标记（品红色大圆 + 夹爪张合状态指示）
        ee_pt = joint_pixel_pts[-1]
        ee_wx, ee_wy = joint_world_pts[-1]

        # 夹爪颜色根据状态变化
        if "CLOSE" in self.gripper_state.upper():
            grip_color = QColor("#FF0055")
            grip_label = "CLOSED"
        elif "OPEN" in self.gripper_state.upper():
            grip_color = QColor("#2EEA8A")
            grip_label = "OPEN"
        else:
            grip_color = QColor("#FFC857")
            grip_label = "HOLD"

        # 外圈光晕
        painter.setPen(QPen(grip_color, 1))
        painter.setBrush(QColor(grip_color.red(), grip_color.green(), grip_color.blue(), 30))
        painter.drawEllipse(ee_pt, 12, 12)

        # 内圈实心
        painter.setPen(QPen(grip_color, 2))
        painter.setBrush(QColor(grip_color.red(), grip_color.green(), grip_color.blue(), 120))
        painter.drawEllipse(ee_pt, 6, 6)
        painter.setBrush(Qt.NoBrush)

        # 夹爪张合指示：两条短线模拟夹爪张开/闭合
        claw_spread = 7 if "OPEN" in self.gripper_state.upper() else 3
        painter.setPen(QPen(grip_color, 2))
        painter.drawLine(
            QPointF(ee_pt.x() - claw_spread, ee_pt.y() - 8),
            QPointF(ee_pt.x() - claw_spread, ee_pt.y() + 8),
        )
        painter.drawLine(
            QPointF(ee_pt.x() + claw_spread, ee_pt.y() - 8),
            QPointF(ee_pt.x() + claw_spread, ee_pt.y() + 8),
        )

        # 末端标注（包含坐标与方位角）
        ee_az = math.degrees(math.atan2(ee_wx, max(1e-6, ee_wy)))
        painter.setPen(grip_color)
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(
            ee_pt.x() + 14,
            ee_pt.y() + 4,
            f"EE ({ee_wx:+.2f}, {ee_wy:+.2f}) [AZ:{ee_az:+.1f}°] [{grip_label}]",
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        # 背景
        painter.fillRect(self.rect(), QColor("#050814"))

        ox, oy, sx, sy = self._get_origin_and_scale()
        base_pt = QPointF(ox, oy)

        # ----------------- 绘制后方物理防护墙体 (Y <= 0 禁行区) -----------------
        wall_top_y = oy
        wall_height = h - wall_top_y
        if wall_height > 0:
            wall_rect = QRectF(0, wall_top_y, w, wall_height)
            # 墙体基础填充（深灰红色工业防护警示底色）
            painter.fillRect(wall_rect, QColor("#120B10"))

            # 绘制斜向警告斑马条纹 (Hazard Stripes)
            stripe_pen = QPen(QColor(255, 0, 85, 32), 2)
            painter.setPen(stripe_pen)
            stripe_spacing = 28
            for sx_offset in range(-int(wall_height * 2), int(w) + int(wall_height), stripe_spacing):
                p1 = QPointF(sx_offset, wall_top_y)
                p2 = QPointF(sx_offset + wall_height, h)
                painter.drawLine(p1, p2)

            # 绘制坚固的物理墙体防护边界线 (Y = 0 实线 + 红色外发光)
            glow_pen = QPen(QColor(255, 0, 85, 70), 5)
            painter.setPen(glow_pen)
            painter.drawLine(QPointF(0, wall_top_y), QPointF(w, wall_top_y))

            wall_edge_pen = QPen(QColor("#FF0055"), 2)
            painter.setPen(wall_edge_pen)
            painter.drawLine(QPointF(0, wall_top_y), QPointF(w, wall_top_y))

            # 墙体警示标牌文字
            wall_font = QFont("Consolas", 8, QFont.Bold)
            painter.setFont(wall_font)
            painter.setPen(QColor(255, 60, 110, 220))
            wall_label = "🧱 物理防护墙体 / PHYSICAL RESTRICTED WALL (Y ≤ 0) · 严禁越界 · 机械臂仅在前方 [-90°, +90°] 作业"
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(wall_label)
            painter.drawText(int((w - tw) / 2), int(wall_top_y + min(22, wall_height * 0.55)), wall_label)

        # 绘制网格与刻度 (每 GRID_STEP_M 一条线)
        grid_pen = QPen(QColor("#0A192F"), 1, Qt.DotLine)
        painter.setPen(grid_pen)
        n_grid = int(round(MAX_REACH_M / GRID_STEP_M))
        for i in range(-n_grid, n_grid + 1):
            gx = i * GRID_STEP_M
            p_top = self.world_to_pixel(gx, MAX_REACH_M)
            p_bot = self.world_to_pixel(gx, 0.0)
            painter.drawLine(p_top, p_bot)

        for i in range(0, n_grid + 1):
            gy = i * GRID_STEP_M
            p_left = self.world_to_pixel(-MAX_REACH_M, gy)
            p_right = self.world_to_pixel(MAX_REACH_M, gy)
            painter.drawLine(p_left, p_right)

        # 测距同心圆弧 (RANGE_ARCS_M: 2m, 4m, 6m)
        range_pen = QPen(QColor("#16355C"), 1, Qt.DashLine)
        painter.setPen(range_pen)
        font = QFont("Consolas", 8)
        painter.setFont(font)
        for r_m in RANGE_ARCS_M:
            rx_px = r_m * sx
            ry_px = r_m * sy
            rect = QRectF(ox - rx_px, oy - ry_px, rx_px * 2, ry_px * 2)
            painter.drawArc(rect, 0 * 16, 180 * 16)
            painter.setPen(QColor("#1E5080"))
            painter.drawText(ox + rx_px + 4, oy - 2, f"{r_m:.1f}m")
            painter.setPen(range_pen)

        # ----------------- 坐标系方位角系统 (Azimuth & Bearing System) -----------------
        az_font = QFont("Consolas", 8)
        painter.setFont(az_font)

        # 1. 绘制外圈刻度线（每 5° 一个短刻度，每 15° 一个长刻度）
        r_outer = MAX_REACH_M
        for deg in range(-90, 91, 5):
            rad = math.radians(deg)
            sin_a = math.sin(rad)
            cos_a = math.cos(rad)
            p_arc = self.world_to_pixel(r_outer * sin_a, r_outer * cos_a)
            tick_len_px = 7 if (deg % 15 == 0) else 4
            tick_dx = (sin_a * sx / max(1e-6, sx)) * tick_len_px
            tick_dy = -(cos_a * sy / max(1e-6, sy)) * tick_len_px
            p_outer = QPointF(p_arc.x() + tick_dx, p_arc.y() + tick_dy)

            painter.setPen(QPen(QColor("#1E4E7A" if deg % 15 == 0 else "#102C48"), 1))
            painter.drawLine(p_arc, p_outer)

        # 2. 绘制主要方位角射线与角度标签
        major_azimuths = [
            (-90, "-90° (L)"),
            (-60, "-60°"),
            (-45, "-45°"),
            (-30, "-30°"),
            (0, "0° (FWD)"),
            (30, "+30°"),
            (45, "+45°"),
            (60, "+60°"),
            (90, "+90° (R)"),
        ]

        minor_azimuths = [-75, -15, 15, 75]
        painter.setPen(QPen(QColor(16, 44, 72, 140), 1, Qt.DotLine))
        for deg in minor_azimuths:
            rad = math.radians(deg)
            p_end = self.world_to_pixel(r_outer * math.sin(rad), r_outer * math.cos(rad))
            painter.drawLine(base_pt, p_end)

        for deg, label in major_azimuths:
            rad = math.radians(deg)
            sin_a = math.sin(rad)
            cos_a = math.cos(rad)
            p_end = self.world_to_pixel(r_outer * sin_a, r_outer * cos_a)

            if deg == 0:
                painter.setPen(QPen(QColor(0, 229, 255, 120), 1.5, Qt.DashLine))
            else:
                painter.setPen(QPen(QColor(30, 80, 128, 160), 1, Qt.DashLine))
            painter.drawLine(base_pt, p_end)

            label_dist_px = 18 if (deg in (0, -90, 90)) else 14
            label_x = p_end.x() + sin_a * label_dist_px
            label_y = p_end.y() - cos_a * label_dist_px

            painter.setPen(QColor("#00E5FF" if deg == 0 else "#4C95C5"))
            text_rect = QRectF(label_x - 35, label_y - 8, 70, 16)
            painter.drawText(text_rect, Qt.AlignCenter, label)

        # ----------------- 终点区域（GOAL ZONE） -----------------
        gz = GOAL_ZONE
        p_tl = self.world_to_pixel(gz["x_min"], gz["y_max"])
        p_br = self.world_to_pixel(gz["x_max"], gz["y_min"])
        goal_rect = QRectF(p_tl.x(), p_tl.y(), p_br.x() - p_tl.x(), p_br.y() - p_tl.y())
        painter.setPen(QPen(QColor("#FFC857"), 2, Qt.DashLine))
        painter.setBrush(QColor(255, 200, 87, 38))
        painter.drawRect(goal_rect)
        painter.setBrush(Qt.NoBrush)
        gcx, gcy = GOAL_CENTER
        c_pt = self.world_to_pixel(gcx, gcy)
        painter.setPen(QPen(QColor("#FFC857"), 1))
        painter.drawLine(QPointF(c_pt.x() - 9, c_pt.y()), QPointF(c_pt.x() + 9, c_pt.y()))
        painter.drawLine(QPointF(c_pt.x(), c_pt.y() - 9), QPointF(c_pt.x(), c_pt.y() + 9))
        painter.setPen(QColor("#FFC857"))
        painter.drawText(int(goal_rect.left()) + 4, int(goal_rect.top()) - 6, "终点区域 GOAL")

        # ----------------- 绘制机器人基座与坐标轴指示 -----------------
        painter.setPen(QPen(QColor("#00E5FF"), 2))
        painter.setBrush(QColor(0, 229, 255, 40))
        painter.drawEllipse(base_pt, 10, 10)
        painter.setBrush(Qt.NoBrush)
        painter.drawText(base_pt.x() + 14, base_pt.y() + 4, "ROBOT BASE (0, 0)")

        axis_len = 28.0
        p_y_axis = QPointF(base_pt.x(), base_pt.y() - axis_len)
        p_x_axis = QPointF(base_pt.x() + axis_len, base_pt.y())
        painter.setPen(QPen(QColor("#00E5FF"), 1.5))
        painter.drawLine(base_pt, p_y_axis)
        painter.drawLine(base_pt, p_x_axis)
        painter.setPen(QColor(0, 229, 255, 180))
        painter.setFont(QFont("Consolas", 7))
        painter.drawText(p_y_axis.x() - 14, p_y_axis.y() - 4, "+Y(FWD)")
        painter.drawText(p_x_axis.x() + 4, p_x_axis.y() + 3, "+X(R)")

        # ----------------- 绘制机械臂连杆骨骼、关节与夹爪 -----------------
        self._draw_robot_arm(painter)

        # ----------------- 绘制识别到的目标 -----------------
        joint_world_pts, ee_angle = self.compute_forward_kinematics()
        ee_x, ee_y = joint_world_pts[-1]
        ee_pt = self.world_to_pixel(ee_x, ee_y)

        for obj in self.objects:
            pos_x, pos_y = None, None
            has_depth = False

            # 1. 优先使用已完成手眼标定解算的基座系绝对位姿 pose_base
            if getattr(obj, "pose_base", None) is not None:
                pb = obj.pose_base.position
                if abs(pb.x) > 1e-4 or abs(pb.y) > 1e-4 or abs(pb.z) > 1e-4:
                    pos_x = pb.x
                    pos_y = pb.y if abs(pb.y) > 1e-4 else pb.z
                    has_depth = True

            # 2. 若无 pose_base，则使用末端相机位姿 (Eye-in-Hand) 进行手眼正向几何变换
            if pos_x is None and getattr(obj, "pose_camera", None) is not None:
                cam_x = obj.pose_camera.position.x
                cam_z = obj.pose_camera.position.z
                if cam_z > 0.02:
                    pos_x, pos_y = self.camera_to_world_coord(cam_x, cam_z)
                    has_depth = True

            # 3. 目标渲染
            if has_depth and pos_x is not None and pos_y is not None:
                pt = self.world_to_pixel(pos_x, pos_y)
                is_selected = (obj.target_id == self.selected_id)
                color = QColor("#2EEA8A") if is_selected else QColor("#00E5FF")

                # 绘制末端到目标的视觉导引视线 (Line of Sight)
                painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 100), 1, Qt.DashLine))
                painter.drawLine(ee_pt, pt)

                # 绘制目标靶标圈
                painter.setPen(QPen(color, 2))
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), 40))
                painter.drawEllipse(pt, 7, 7)
                if is_selected:
                    painter.drawEllipse(pt, 13, 13)
                painter.setBrush(Qt.NoBrush)

                # 目标在空间基座系中的物理位置与方位角
                obj_az = math.degrees(math.atan2(pos_x, max(1e-6, pos_y)))
                obj_r = math.hypot(pos_x, pos_y)
                painter.setPen(color)
                painter.setFont(QFont("Consolas", 8))
                painter.drawText(
                    pt.x() + 10,
                    pt.y() - 4,
                    f"{obj.target_id} ({pos_x:+.2f}, {pos_y:+.2f}) [AZ:{obj_az:+.1f}°, {obj_r:.2f}m]",
                )
            else:
                # 若尚未检测出深度 (BEARING ONLY)，从末端沿当前视向绘制虚线导引射线，绝不落在原点 (0,0)
                ray_len_m = 0.8
                ray_end_x = ee_x + ray_len_m * math.cos(ee_angle)
                ray_end_y = ee_y + ray_len_m * math.sin(ee_angle)
                p_end = self.world_to_pixel(ray_end_x, ray_end_y)
                painter.setPen(QPen(QColor(255, 200, 87, 140), 1, Qt.DashLine))
                painter.drawLine(ee_pt, p_end)
                painter.setPen(QColor("#FFC857"))
                painter.setFont(QFont("Consolas", 7))
                painter.drawText(p_end.x() + 6, p_end.y() + 3, f"{obj.target_id} [BEARING ONLY]")

        # ----------------- 绘制当前选定的路点 Waypoint -----------------
        if self.selected_waypoint is not None:
            wx, wy = self.selected_waypoint
            wpt = self.world_to_pixel(wx, wy)
            wp_az = math.degrees(math.atan2(wx, max(1e-6, wy)))
            wp_r = math.hypot(wx, wy)
            painter.setPen(QPen(QColor("#FF0055"), 2))
            painter.drawLine(QPointF(wpt.x() - 10, wpt.y()), QPointF(wpt.x() + 10, wpt.y()))
            painter.drawLine(QPointF(wpt.x(), wpt.y() - 10), QPointF(wpt.x(), wpt.y() + 10))
            painter.drawEllipse(wpt, 8, 8)
            painter.setPen(QColor("#FF0055"))
            painter.drawText(wpt.x() + 12, wpt.y() + 14, f"WP: ({wx:.2f}, {wy:.2f}) [AZ:{wp_az:+.1f}°, R:{wp_r:.2f}m]")

        # ----------------- 左上角图例与方位角定义 -----------------
        painter.setPen(QColor(0, 229, 255, 180))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(12, 20, "RADAR AZIMUTH: 0°=FWD(+Y) | +90°=RIGHT(+X) | -90°=LEFT(-X) | REAR: PHYSICAL WALL (Y≤0)")

        # ----------------- 绘制鼠标悬停坐标与方位角提示 -----------------
        if self.hover_coord is not None:
            hx, hy = self.hover_coord
            hpt = self.world_to_pixel(hx, hy)
            in_wall = (hy < 0.0)

            cross_color = QColor(255, 0, 85, 140) if in_wall else QColor(0, 229, 255, 90)
            painter.setPen(QPen(cross_color, 1, Qt.DashLine))
            painter.drawLine(QPointF(hpt.x(), 0), QPointF(hpt.x(), h))
            painter.drawLine(QPointF(0, hpt.y()), QPointF(w, hpt.y()))

            if in_wall:
                telemetry_str = f"CURSOR: X={hx:+.3f}m, Y={hy:+.3f}m | 🧱 墙体禁行区 (RESTRICTED WALL · Y<=0)"
                box_pen = QPen(QColor("#FF0055"), 1)
                box_brush = QColor(35, 10, 20, 230)
                text_color = QColor("#FF4D7D")
            else:
                az_deg = math.degrees(math.atan2(hx, max(1e-6, hy)))
                r_dist = math.hypot(hx, hy)
                telemetry_str = f"CURSOR: X={hx:+.3f}m, Y={hy:+.3f}m | AZ: {az_deg:+.1f}° | R: {r_dist:.2f}m"
                box_pen = QPen(QColor("#0E3B68"), 1)
                box_brush = QColor(5, 12, 28, 200)
                text_color = QColor("#00E5FF")

            fm = painter.fontMetrics()
            t_w = fm.horizontalAdvance(telemetry_str) + 16
            t_box = QRectF(w - t_w - 12, h - 26, t_w, 20)
            painter.setPen(box_pen)
            painter.setBrush(box_brush)
            painter.drawRoundedRect(t_box, 3, 3)
            painter.setBrush(Qt.NoBrush)

            painter.setPen(text_color)
            painter.drawText(t_box, Qt.AlignCenter, telemetry_str)

        painter.end()
