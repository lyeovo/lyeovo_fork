from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import TaskCommand, TaskStatus


ROW_HEIGHT = 78
THUMB_SIZE = 64


class TaskListWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.records: dict[str, dict] = {}
        self.order: list[str] = []
        self._thumb_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Shot", "Command ID", "Type", "Target", "Destination", "Status", "Progress"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setIconSize(self.table.sizeHint())
        self.table.setAlternatingRowColors(False)
        self.table.itemSelectionChanged.connect(self._show_selected_details)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 82)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)

        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(180)
        self.summary.setPlaceholderText("Select a task to view details.")
        self.summary.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.summary.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.status_history = QPlainTextEdit()
        self.status_history.setReadOnly(True)
        self.status_history.setMinimumHeight(120)
        self.status_history.setPlaceholderText("Status updates will appear here.")
        self.status_history.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.status_history.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        detail_splitter = QSplitter(Qt.Vertical)
        detail_splitter.addWidget(self.summary)
        detail_splitter.addWidget(self.status_history)
        detail_splitter.setStretchFactor(0, 2)
        detail_splitter.setStretchFactor(1, 1)
        detail_splitter.setChildrenCollapsible(False)
        detail_layout.addWidget(detail_splitter)

        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(self.table)
        main_splitter.addWidget(detail_panel)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setChildrenCollapsible(False)
        layout.addWidget(main_splitter)

    def clear(self) -> None:
        self.records.clear()
        self.order.clear()
        self._thumb_labels.clear()
        self.table.setRowCount(0)
        self.summary.clear()
        self.status_history.clear()

    def add_command(
        self,
        command: TaskCommand,
        publish_ref: str | None = None,
        target_snapshot: QPixmap | None = None,
        initial_status: str = "PENDING",
    ) -> None:
        command_id = command.command_id
        if command_id not in self.records:
            self.order.insert(0, command_id)
            self.records[command_id] = {
                "command": command,
                "publish_ref": publish_ref,
                "statuses": [],
                "snapshot": target_snapshot,
                "latest_status": initial_status,
                "latest_progress": 0.0,
            }
            self.table.insertRow(0)
            self.table.setRowHeight(0, ROW_HEIGHT)
            self._install_thumbnail_cell(command_id)
        else:
            record = self.records[command_id]
            record["command"] = command
            record["publish_ref"] = publish_ref or record.get("publish_ref")
            record["snapshot"] = target_snapshot or record.get("snapshot")
            record["latest_status"] = initial_status
        self._refresh_row(command_id)
        self.table.selectRow(self._row_for(command_id))
        self._show_selected_details()

    def mark_published(self, command_id: str, publish_ref: str | None = None) -> None:
        if command_id not in self.records:
            return
        record = self.records[command_id]
        record["publish_ref"] = publish_ref or record.get("publish_ref")
        record["latest_status"] = "PUBLISHED"
        record["latest_progress"] = 0.0
        self._refresh_row(command_id)
        if self._selected_command_id() == command_id:
            self._show_selected_details()

    def add_status(self, status: TaskStatus) -> None:
        command_id = status.command_id
        if command_id not in self.records:
            self.order.insert(0, command_id)
            self.records[command_id] = {
                "command": None,
                "publish_ref": None,
                "statuses": [],
                "snapshot": None,
                "latest_status": status.status,
                "latest_progress": status.progress,
            }
            self.table.insertRow(0)
            self.table.setRowHeight(0, ROW_HEIGHT)
            self._install_thumbnail_cell(command_id)
        record = self.records[command_id]
        record["statuses"].append(status)
        record["latest_status"] = status.status
        record["latest_progress"] = status.progress
        self._refresh_row(command_id)
        if self._selected_command_id() == command_id:
            self._show_selected_details()

    def _install_thumbnail_cell(self, command_id: str) -> None:
        row = self._row_for(command_id)
        label = QLabel("No\nImage")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(THUMB_SIZE, THUMB_SIZE)
        label.setStyleSheet("background: #02040D; border: 1px solid #1B2A4A; color: #8FA6C8;")
        self._thumb_labels[command_id] = label
        self.table.setCellWidget(row, 0, label)

    def _refresh_row(self, command_id: str) -> None:
        row = self._row_for(command_id)
        self.table.setRowHeight(row, ROW_HEIGHT)
        record = self.records[command_id]
        command = record.get("command")
        target = command.selected_target if command else None
        destination = command.destination if command else None
        values = [
            command_id,
            command.command_type if command else "--",
            target.get("target_id", "--") if target else "--",
            destination.get("name", "--") if destination else "--",
            record.get("latest_status", "--"),
            f"{float(record.get('latest_progress', 0.0)):.0%}",
        ]
        for offset, value in enumerate(values, start=1):
            item = self.table.item(row, offset)
            if item is None:
                item = QTableWidgetItem()
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, offset, item)
            item.setText(str(value))
        self._refresh_thumbnail(command_id)

    def _refresh_thumbnail(self, command_id: str) -> None:
        label = self._thumb_labels.get(command_id)
        if label is None:
            return
        snapshot = self.records[command_id].get("snapshot")
        if snapshot and not snapshot.isNull():
            label.setText("")
            label.setPixmap(snapshot.scaled(THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            label.setPixmap(QPixmap())
            label.setText("No\nImage")

    def _show_selected_details(self) -> None:
        command_id = self._selected_command_id()
        if not command_id:
            return
        record = self.records[command_id]
        command = record.get("command")
        if not command:
            self.summary.setPlainText(f"Command ID: {command_id}\nStatus: {record.get('latest_status', '--')}")
        else:
            self.summary.setPlainText(self._command_summary(command, record))
        self.status_history.setPlainText(self._status_summary(record))

    def _command_summary(self, command: TaskCommand, record: dict) -> str:
        target = command.selected_target or {}
        destination = command.destination or {}
        params = command.params or command.motion_params or {}
        safety = command.safety or {}
        param_lines = [f"  {k}: {v}" for k, v in params.items()] if params else ["  (None)"]
        lines = [
            f"Command ID: {command.command_id}",
            f"Task Type: {command.command_type}",
            f"Status: {record.get('latest_status', '--')}",
            f"Published To: {record.get('publish_ref') or '--'}",
            "",
            "Parameters:",
            *param_lines,
            "",
            f"Target ID: {target.get('target_id', '--')}",
            f"Target Class: {target.get('class_name', '--')}",
            f"Confidence: {target.get('confidence', '--')}",
            f"Stability: {target.get('stability_score', '--')}",
            f"Depth: {target.get('depth_m', '--')} m" if target.get('depth_m') is not None else "Depth: --",
            "",
            f"Destination: {destination.get('name', '--')}",
            "",
            f"Execution Mode: {safety.get('execution_mode', '--')}",
            f"Allow Execute: {safety.get('allow_execute', '--')}",
            f"Allow Real Execute: {safety.get('allow_real_execute', '--')}",
            f"Validation: {safety.get('validation_message', '--')}",
        ]
        return "\n".join(lines)

    def _status_summary(self, record: dict) -> str:
        statuses = record.get("statuses") or []
        if not statuses:
            return "No status received yet. Start mock_control_server or connect the control module."
        return "\n".join(f"{item.status:>16}  {item.progress:.0%}  {item.message}" for item in statuses)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for command_id in self.order:
            self._refresh_thumbnail(command_id)

    def _selected_command_id(self) -> str | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        if row < 0 or row >= len(self.order):
            return None
        return self.order[row]

    def _row_for(self, command_id: str) -> int:
        return self.order.index(command_id)
