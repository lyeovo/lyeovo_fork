from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class MissionMapWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.objects = []
        self.selected_id = None
        self.setMinimumHeight(190)

    def update_map(self, objects, selected_id) -> None:
        self.objects = list(objects)
        self.selected_id = selected_id
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#050814"))
        pen = QPen(QColor("#1B2A4A"))
        painter.setPen(pen)
        for x in range(0, self.width(), 32):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 32):
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(QPen(QColor("#00E5FF"), 2))
        origin = QPointF(self.width() * 0.18, self.height() * 0.72)
        painter.drawEllipse(origin, 8, 8)
        painter.drawText(origin.x() + 12, origin.y(), "ROBOT BASE")
        painter.setPen(QPen(QColor("#FFC857"), 2))
        painter.drawRect(self.width() - 88, 28, 62, 42)
        painter.drawText(self.width() - 118, 22, "PORT A")
        for obj in self.objects:
            px = origin.x() + obj.pose_camera.position.x * 450
            py = origin.y() - obj.pose_camera.position.z * 170
            color = QColor("#2EEA8A") if obj.target_id == self.selected_id else QColor("#00E5FF")
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(QPointF(px, py), 5, 5)
            painter.drawText(px + 8, py - 4, obj.target_id)
        painter.end()
