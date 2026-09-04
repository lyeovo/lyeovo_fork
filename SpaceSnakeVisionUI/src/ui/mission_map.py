import math
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


# 机械臂几何：6 节 × 1m，平面全伸展最大作业半径 6m
N_SEGMENTS = 6
SEG_LEN_M = 1.0
MAX_REACH_M = N_SEGMENTS * SEG_LEN_M  # 6.0 m
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

    def __init__(self) -> None:
        super().__init__()
        self.objects = []
        self.selected_id: Optional[str] = None
        self.selected_waypoint: Optional[Tuple[float, float]] = None
        self.hover_coord: Optional[Tuple[float, float]] = None
        self.setMinimumHeight(200)
        self.setMouseTracking(True)

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
            # 限制在机械臂可达作业范围内 (±MAX_REACH_M)
            clamped_x = round(max(-MAX_REACH_M, min(MAX_REACH_M, x)), 3)
            clamped_y = round(max(-MAX_REACH_M, min(MAX_REACH_M, y)), 3)
            self.selected_waypoint = (clamped_x, clamped_y)
            self.coordinateSelected.emit(clamped_x, clamped_y)
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        # 背景
        painter.fillRect(self.rect(), QColor("#050814"))

        ox, oy, sx, sy = self._get_origin_and_scale()
        base_pt = QPointF(ox, oy)

        # 绘制网格与刻度 (每 GRID_STEP_M 一条线)
        grid_pen = QPen(QColor("#0F223D"), 1, Qt.DotLine)
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

        # 绘制终点区域（右侧单一放置区，按世界坐标绘制，随地图缩放）
        gz = GOAL_ZONE
        p_tl = self.world_to_pixel(gz["x_min"], gz["y_max"])  # 左上
        p_br = self.world_to_pixel(gz["x_max"], gz["y_min"])  # 右下
        goal_rect = QRectF(p_tl.x(), p_tl.y(), p_br.x() - p_tl.x(), p_br.y() - p_tl.y())
        painter.setPen(QPen(QColor("#FFC857"), 2, Qt.DashLine))
        painter.setBrush(QColor(255, 200, 87, 38))
        painter.drawRect(goal_rect)
        painter.setBrush(Qt.NoBrush)
        # 中心十字
        gcx, gcy = GOAL_CENTER
        c_pt = self.world_to_pixel(gcx, gcy)
        painter.setPen(QPen(QColor("#FFC857"), 1))
        painter.drawLine(QPointF(c_pt.x() - 9, c_pt.y()), QPointF(c_pt.x() + 9, c_pt.y()))
        painter.drawLine(QPointF(c_pt.x(), c_pt.y() - 9), QPointF(c_pt.x(), c_pt.y() + 9))
        # 标签
        painter.setPen(QColor("#FFC857"))
        painter.drawText(int(goal_rect.left()) + 4, int(goal_rect.top()) - 6, "终点区域 GOAL")

        # 绘制机器人基座
        painter.setPen(QPen(QColor("#00E5FF"), 2))
        painter.setBrush(QColor(0, 229, 255, 40))
        painter.drawEllipse(base_pt, 10, 10)
        painter.setBrush(Qt.NoBrush)
        painter.drawText(base_pt.x() + 14, base_pt.y() + 4, "ROBOT BASE (0, 0)")

        # 绘制识别到的目标
        for obj in self.objects:
            pos_x = obj.pose_camera.position.x
            pos_y = obj.pose_camera.position.z  # 相机向前对应平面纵向
            pt = self.world_to_pixel(pos_x, pos_y)
            is_selected = (obj.target_id == self.selected_id)
            color = QColor("#2EEA8A") if is_selected else QColor("#00E5FF")
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(pt, 6, 6)
            if is_selected:
                painter.drawEllipse(pt, 12, 12)
            painter.drawText(pt.x() + 8, pt.y() - 4, f"{obj.target_id} ({pos_x:.2f}, {pos_y:.2f})")

        # 绘制当前选定的路点 Waypoint
        if self.selected_waypoint is not None:
            wx, wy = self.selected_waypoint
            wpt = self.world_to_pixel(wx, wy)
            painter.setPen(QPen(QColor("#FF0055"), 2))
            # 绘制十字与准星圆
            painter.drawLine(QPointF(wpt.x() - 10, wpt.y()), QPointF(wpt.x() + 10, wpt.y()))
            painter.drawLine(QPointF(wpt.x(), wpt.y() - 10), QPointF(wpt.x(), wpt.y() + 10))
            painter.drawEllipse(wpt, 8, 8)
            painter.setPen(QColor("#FF0055"))
            painter.drawText(wpt.x() + 12, wpt.y() + 14, f"WP: ({wx:.2f}, {wy:.2f})")

        # 绘制鼠标悬停坐标提示
        if self.hover_coord is not None:
            hx, hy = self.hover_coord
            hpt = self.world_to_pixel(hx, hy)
            painter.setPen(QPen(QColor(0, 229, 255, 120), 1, Qt.DashLine))
            painter.drawLine(QPointF(hpt.x(), 0), QPointF(hpt.x(), h))
            painter.drawLine(QPointF(0, hpt.y()), QPointF(w, hpt.y()))
            painter.setPen(QColor("#00E5FF"))
            painter.drawText(w - 180, h - 10, f"CURSOR: X={hx:+.3f}m, Y={hy:+.3f}m")

        painter.end()
