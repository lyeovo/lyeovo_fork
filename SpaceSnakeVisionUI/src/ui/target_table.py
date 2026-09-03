from __future__ import annotations

from typing import List, Optional
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem


class TargetTableWidget(QTableWidget):
    targetSelected = Signal(str)

    def __init__(self) -> None:
        super().__init__(0, 7)
        self.setHorizontalHeaderLabels(["ID", "类别", "x (m)", "y (m)", "z (m)", "稳定度", "状态"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.itemSelectionChanged.connect(self._emit_selection)
        self._objects: List[Any] = []
        self._updating = False

    def update_targets(self, objects, selected_id: Optional[str] = None) -> None:
        self._updating = True
        try:
            self._objects = list(objects)
            self.setRowCount(len(objects))
            selected_row = -1

            for row, obj in enumerate(objects):
                pose = getattr(obj, "pose_camera", None)
                pos = getattr(pose, "position", None) if pose else None

                x_str = f"{pos.x:+.3f}" if pos else "--"
                y_str = f"{pos.y:+.3f}" if pos else "--"
                z_str = f"{pos.z:+.3f}" if pos else (f"{obj.depth_m:.3f}" if getattr(obj, "depth_m", None) else "--")

                vals = [
                    str(getattr(obj, "target_id", "--")),
                    str(getattr(obj, "class_name", "--")),
                    x_str,
                    y_str,
                    z_str,
                    f"{getattr(obj, 'stability_score', 0.0):.2f}",
                    str(getattr(obj, "status", "UNKNOWN")),
                ]
                for col, val in enumerate(vals):
                    self.setItem(row, col, QTableWidgetItem(val))

                if selected_id and getattr(obj, "target_id", None) == selected_id:
                    selected_row = row

            if selected_row >= 0:
                self.selectRow(selected_row)
        finally:
            self._updating = False

    def _emit_selection(self) -> None:
        if self._updating:
            return
        row = self.currentRow()
        if 0 <= row < len(self._objects):
            target_id = getattr(self._objects[row], "target_id", None)
            if target_id:
                self.targetSelected.emit(target_id)
