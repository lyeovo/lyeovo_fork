import math
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


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
        """返回 (origin_x, origin_y, scale_x, scale_y)"""
        w = max(100, self.width())
        h = max(100, self.height())
        origin_x = w * 0.50
        origin_y = h * 0.82
        # 工作区范围: X: [-0.6, +0.6] m (宽 1.2m), Y: [0.0, 1.0] m (长 1.0m)
        scale_x = (w * 0.75) / 1.2
        scale_y = (h * 0.70) / 1.0
        return origin_x, origin_y, scale_x, scale_y

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
            # 限制在合理作业范围
            clamped_x = round(max(-1.5, min(1.5, x)), 3)
            clamped_y = round(max(-1.5, min(1.5, y)), 3)
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

        # 绘制网格与刻度 (每 0.2m 一条线)
        grid_pen = QPen(QColor("#0F223D"), 1, Qt.DotLine)
        painter.setPen(grid_pen)
        for gx in [i * 0.2 for i in range(-5, 6)]:
            p_top = self.world_to_pixel(gx, 1.2)
            p_bot = self.world_to_pixel(gx, -0.2)
            painter.drawLine(p_top, p_bot)

        for gy in [i * 0.2 for i in range(-1, 7)]:
            p_left = self.world_to_pixel(-0.8, gy)
            p_right = self.world_to_pixel(0.8, gy)
            painter.drawLine(p_left, p_right)

        # 测距同心圆弧 (0.2m, 0.4m, 0.6m, 0.8m)
        range_pen = QPen(QColor("#16355C"), 1, Qt.DashLine)
        painter.setPen(range_pen)
        font = QFont("Consolas", 8)
        painter.setFont(font)
        for r_m in (0.2, 0.4, 0.6, 0.8):
            rx_px = r_m * sx
            ry_px = r_m * sy
            rect = QRectF(ox - rx_px, oy - ry_px, rx_px * 2, ry_px * 2)
            painter.drawArc(rect, 0 * 16, 180 * 16)
            painter.setPen(QColor("#1E5080"))
            painter.drawText(ox + rx_px + 4, oy - 2, f"{r_m:.1f}m")
            painter.setPen(range_pen)

        # 绘制预设装配区工位
        painter.setPen(QPen(QColor("#FFC857"), 1, Qt.DashLine))
        port_a_pt = self.world_to_pixel(0.35, 0.20)
        painter.drawRect(QRectF(port_a_pt.x() - 20, port_a_pt.y() - 15, 40, 30))
        painter.drawText(port_a_pt.x() - 18, port_a_pt.y() - 18, "PORT A")

        port_b_pt = self.world_to_pixel(-0.35, 0.20)
        painter.drawRect(QRectF(port_b_pt.x() - 20, port_b_pt.y() - 15, 40, 30))
        painter.drawText(port_b_pt.x() - 18, port_b_pt.y() - 18, "PORT B")

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
