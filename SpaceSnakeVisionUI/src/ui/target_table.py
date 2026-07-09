from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem


class TargetTableWidget(QTableWidget):
    targetSelected = Signal(str)

    def __init__(self) -> None:
        super().__init__(0, 7)
        self.setHorizontalHeaderLabels(["ID", "类别", "x", "y", "z", "稳定度", "状态"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.itemSelectionChanged.connect(self._emit_selection)
        self._objects = []

    def update_targets(self, objects) -> None:
        self._objects = list(objects)
        self.setRowCount(len(objects))
        for row, obj in enumerate(objects):
            vals = [
                obj.target_id,
                obj.class_name,
                f"{obj.pose_camera.position.x:.3f}",
                f"{obj.pose_camera.position.y:.3f}",
                f"{obj.pose_camera.position.z:.3f}",
                f"{obj.stability_score:.2f}",
                obj.status,
            ]
            for col, val in enumerate(vals):
                self.setItem(row, col, QTableWidgetItem(val))

    def _emit_selection(self) -> None:
        row = self.currentRow()
        if 0 <= row < len(self._objects):
            self.targetSelected.emit(self._objects[row].target_id)
