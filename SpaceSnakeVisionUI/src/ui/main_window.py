import copy
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QGroupBox, QLabel, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget

from ..bridge.command_builder import build_estop_command, build_task_command
from ..bridge.command_validator import validate_command
from ..models import TaskCommand
from ..utils.image_utils import cv_bgr_to_qpixmap
from ..vision.pipeline import VisionPipeline
from .camera_view import CameraViewWidget
from .command_panel import TaskCommandPanel
from .log_console import LogConsole
from .mission_map import MissionMapWidget
from .status_bar import MissionStatusBar
from .task_list import TaskListWidget


class VisionWorker(QThread):
    frameReady = Signal(object, object)
    error = Signal(str)
    info = Signal(str)

    def __init__(self, camera, detector_mode: str, yolo_model: str, yolo_conf: float, project_root: Path) -> None:
        super().__init__()
        self.camera = camera
        self.pipeline = VisionPipeline(
            prefer_mock=camera.__class__.__name__ == "MockCamera",
            detector_mode=detector_mode,
            yolo_model=yolo_model,
            yolo_conf=yolo_conf,
            project_root=project_root,
        )
        if self.pipeline.last_message:
            self.info.emit(self.pipeline.last_message)
        self.running = True
        self._last_pipeline_message = None

    def run(self) -> None:
        try:
            self.camera.start()
        except Exception as exc:
            self.error.emit(f"Camera start failed: {exc}")
        while self.running:
            try:
                frame = self.camera.read()
                overlay, objects = self.pipeline.process(frame)
                if self.pipeline.last_message and self.pipeline.last_message != self._last_pipeline_message:
                    self._last_pipeline_message = self.pipeline.last_message
                    self.info.emit(self.pipeline.last_message)
                self.frameReady.emit(overlay, objects)
                self.msleep(33)
            except Exception as exc:
                self.error.emit(f"Vision loop error: {exc}")
                self.msleep(500)
        self.camera.stop()

    def stop(self) -> None:
        self.running = False


class MainWindow(QMainWindow):
    def __init__(
        self,
        camera,
        bridge,
        bridge_status: str,
        project_root: Path,
        detector_mode: str = "yolo",
        yolo_model: str = "yolo11n.pt",
        yolo_conf: float = 0.35,
    ) -> None:
        super().__init__()
        self.camera = camera
        self.bridge = bridge
        self.bridge_status = bridge_status
        self.project_root = project_root
        self.objects = []
        self.selected_id = None
        self.selected_target_snapshot = None
        self.selected_target_locked_at: float | None = None
        self.selected_target_last_seen_at: float | None = None
        self.pending_command: TaskCommand | None = None
        self.pending_target_pixmap = None
        self.current_frame = None
        self.task_list_visible = False
        self.active_command_id: str | None = None
        self.robot_busy = False
        self.estop_active = False
        self.last_robot_status = "IDLE"
        self.last_status_message = ""
        self.setWindowTitle("ORBITAL SNAKE ROBOT MISSION CONTROL")
        self.resize(1280, 800)
        qss = (project_root / "src" / "ui" / "theme.qss").read_text(encoding="utf-8")
        self.setStyleSheet(qss)
        self._build_ui()
        self.worker = VisionWorker(camera, detector_mode, yolo_model, yolo_conf, project_root)
        self.worker.frameReady.connect(self.on_frame)
        self.worker.error.connect(self.log.log)
        self.worker.info.connect(self.log.log)
        self.worker.start()
        self.status.set_state(f"Camera: ONLINE | Vision: RUNNING | Bridge: {bridge_status} | Robot: IDLE | E-STOP: SAFE")
        self.log.log("Vision pipeline started")
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_status)
        self.poll_timer.start(600)

    def _build_ui(self) -> None:
        root = QWidget()
        main = QVBoxLayout(root)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        self.status = MissionStatusBar()
        main.addWidget(self.status)

        main_splitter = QSplitter(Qt.Vertical)
        content_splitter = QSplitter(Qt.Horizontal)

        self.task_sidebar = QWidget()
        task_sidebar_layout = QVBoxLayout(self.task_sidebar)
        task_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        task_sidebar_layout.setSpacing(6)
        self.task_sidebar_btn = QPushButton(">")
        self.task_sidebar_btn.setObjectName("sidebarToggleButton")
        self.task_sidebar_btn.setToolTip("展开任务列表")
        self.task_sidebar_btn.setMinimumWidth(30)
        self.task_sidebar_btn.setMaximumWidth(34)
        self.task_list = TaskListWidget()
        self.task_list.clear()
        self.task_list_group = wrap_group("TASK LIST", self.task_list)
        self.task_list_group.setVisible(False)
        task_sidebar_layout.addWidget(self.task_sidebar_btn, 0, Qt.AlignTop)
        task_sidebar_layout.addWidget(self.task_list_group, 1)
        self.task_sidebar.setMinimumWidth(34)
        self.task_sidebar.setMaximumWidth(34)

        left_splitter = QSplitter(Qt.Vertical)
        self.camera_view = CameraViewWidget()
        self.map = MissionMapWidget()
        camera_group = wrap_group("CAMERA VIEW", self.camera_view)
        map_group = wrap_group("MISSION MAP", self.map)
        camera_group.setMinimumHeight(280)
        map_group.setMinimumHeight(140)
        left_splitter.addWidget(camera_group)
        left_splitter.addWidget(map_group)
        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 1)
        left_splitter.setChildrenCollapsible(False)

        right_splitter = QSplitter(Qt.Vertical)
        self.selected_target_details = QPlainTextEdit()
        self.selected_target_details.setReadOnly(True)
        self.selected_target_details.setPlaceholderText("请选择一个目标")
        self.selected_target_details.setPlainText("请选择一个目标")
        self.command_panel = TaskCommandPanel()
        selected_group = wrap_group("SELECTED TARGET 6DoF", self.selected_target_details)
        command_group = wrap_group("COMMAND PANEL", self.command_panel)
        selected_group.setMinimumHeight(300)
        command_group.setMinimumHeight(230)
        right_splitter.addWidget(selected_group)
        right_splitter.addWidget(command_group)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        right_splitter.setChildrenCollapsible(False)
        right_splitter.setMinimumHeight(560)

        right_scroll = QScrollArea()
        right_scroll.setObjectName("rightPanelScroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setWidget(right_splitter)

        content_splitter.addWidget(self.task_sidebar)
        content_splitter.addWidget(left_splitter)
        content_splitter.addWidget(right_scroll)
        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 3)
        content_splitter.setStretchFactor(2, 2)
        content_splitter.setChildrenCollapsible(False)
        self.content_splitter = content_splitter

        self.log = LogConsole()
        log_group = wrap_group("MISSION LOG", self.log)
        log_group.setMinimumHeight(120)
        main_splitter.addWidget(content_splitter)
        main_splitter.addWidget(log_group)
        main_splitter.setStretchFactor(0, 5)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setChildrenCollapsible(False)
        main.addWidget(main_splitter, 1)

        self.setCentralWidget(root)
        self.camera_view.targetClicked.connect(self.select_by_pixel)
        self.command_panel.generateRequested.connect(self.generate_command)
        self.command_panel.publishRequested.connect(self.publish_command)
        self.command_panel.estopRequested.connect(self.emergency_stop)
        self.command_panel.cancelRequested.connect(self.cancel_task)
        self.task_sidebar_btn.clicked.connect(self.toggle_task_list)

    def on_frame(self, image, objects) -> None:
        self.objects = list(objects)
        self.current_frame = image.copy()
        VisionPipeline.redraw_selection(image, self.objects, self.selected_id)
        self.camera_view.set_frame_size(image.shape[1], image.shape[0])
        self.camera_view.setPixmap(cv_bgr_to_qpixmap(image))
        self.map.update_map(self.objects, self.selected_id)
        current = self._selected_obj()
        if self.selected_id and current:
            self.selected_target_last_seen_at = current.timestamp
            self._refresh_selected_target_details(current, realtime=True)
        elif self.selected_id:
            self.log.log(f"Target lost: {self.selected_id}")
        elif not self.objects:
            self.selected_target_details.setPlainText("SEARCH\n目标丢失，正在搜索")

    def select_target(self, target_id: str) -> None:
        self.selected_id = target_id
        obj = self._selected_obj()
        if obj:
            self.selected_target_snapshot = copy.deepcopy(obj)
            self.selected_target_locked_at = time.time()
            self.selected_target_last_seen_at = obj.timestamp
            self._refresh_selected_target_details(obj, realtime=True)
            self.log.log(f"Target locked: {obj.target_id}")
        self.map.update_map(self.objects, self.selected_id)

    def select_by_pixel(self, x: int, y: int) -> None:
        for obj in self.objects:
            x1, y1, x2, y2 = obj.bbox_xyxy
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.select_target(obj.target_id)
                break

    def generate_command(self, command_type, destination, approach, speed, gripper) -> None:
        obj = self._get_command_target()
        result = validate_command(
            command_type,
            obj,
            destination,
            approach,
            estop_active=self.estop_active,
            robot_busy=self.robot_busy,
            locked_at=self.selected_target_last_seen_at,
        )
        if not result.ok:
            self.log.log(f"Pre-check failed: {result.reason}")
            self.pending_command = None
            self._refresh_status_bar()
            return
        if obj and obj.status not in ("AVAILABLE", "LOCKED", "BEARING_ONLY", "PARTIAL_DEPTH", "POSE_6DOF"):
            self.log.log(f"Pre-check warning: target status is {obj.status}; command saved for test only")
        self.pending_command = build_task_command(
            command_type,
            obj,
            destination,
            approach,
            speed,
            gripper,
            self.estop_active,
            robot_busy=self.robot_busy,
            validation_report=result.to_report(),
            locked_at=self.selected_target_locked_at,
            execution_mode=result.execution_mode,
        )
        self.pending_target_pixmap = self._capture_target_pixmap(obj)
        self.task_list.add_command(
            self.pending_command,
            target_snapshot=self.pending_target_pixmap,
            initial_status="GENERATED",
        )
        self.log.log(
            f"Command generated: {self.pending_command.command_id} {command_type} "
            f"mode={result.execution_mode}"
        )
        self._refresh_status_bar()

    def publish_command(self) -> None:
        if self.pending_command is None:
            self.log.log("No pending command. Generate a task first.")
            return
        path = self.bridge.publish_command(self.pending_command)
        published_command = self.pending_command
        self.active_command_id = self.pending_command.command_id
        self.robot_busy = self.pending_command.command_type not in ("emergency_stop",)
        self.last_robot_status = "COMMAND_SENT"
        if published_command.command_id not in self.task_list.records:
            self.task_list.add_command(published_command, str(path), self.pending_target_pixmap, "PUBLISHED")
        else:
            self.task_list.mark_published(published_command.command_id, str(path))
        self.pending_command = None
        self.pending_target_pixmap = None
        self._refresh_status_bar()
        self.log.log(f"Command published to {path}")

    def emergency_stop(self) -> None:
        self.estop_active = True
        cmd = build_estop_command()
        path = self.bridge.publish_command(cmd)
        self.active_command_id = cmd.command_id
        self.robot_busy = False
        self.last_robot_status = "ESTOP"
        self.task_list.add_command(cmd, str(path), initial_status="PUBLISHED")
        self._refresh_status_bar()
        self.log.log(f"E-STOP command published to {path}")

    def cancel_task(self) -> None:
        result = validate_command(
            "cancel_task",
            None,
            None,
            0.05,
            estop_active=False,
            robot_busy=self.robot_busy,
        )
        cmd = build_task_command(
            "cancel_task",
            None,
            None,
            0.05,
            "demo_safe",
            "demo_grip",
            False,
            robot_busy=self.robot_busy,
            validation_report=result.to_report(),
        )
        path = self.bridge.publish_command(cmd)
        self.active_command_id = cmd.command_id
        self.robot_busy = True
        self.last_robot_status = "CANCELING"
        self.task_list.add_command(cmd, str(path), initial_status="PUBLISHED")
        self._refresh_status_bar()
        self.log.log(f"Cancel command published to {path}")

    def poll_status(self) -> None:
        for status in self.bridge.poll_status():
            self.log.log(f"Task {status.command_id}: {status.status} {status.progress:.0%} - {status.message}")
            self.task_list.add_status(status)
            self._apply_task_status(status)

    def _selected_obj(self):
        for obj in self.objects:
            if obj.target_id == self.selected_id:
                return obj
        return None

    def _get_command_target(self):
        return self._selected_obj() or self.selected_target_snapshot

    def _refresh_selected_target_details(self, obj, realtime: bool = False) -> None:
        pose = obj.pose_camera
        base = obj.pose_base
        camera_orientation_available = self._orientation_available(obj, pose)
        base_orientation_available = base is not None and self._orientation_available(obj, base)
        source_text = "current frame / realtime" if realtime else "locked snapshot"
        quality = getattr(obj, "quality", None) or {}
        bearing = getattr(obj, "bearing", None) or quality.get("bearing") or quality.get("last_seen_bearing")
        pose_available = bool(quality.get("pose_available", obj.status == "POSE_6DOF"))
        lines = [
            "Selected Target",
            f"ID: {obj.target_id}",
            f"Class: {obj.class_name}",
            f"Display Name: {obj.display_name}",
            f"Detection Mode: {obj.detection_mode}",
            f"Pose Source: {source_text}",
            f"Marker ID: {obj.marker_id if obj.marker_id is not None else '--'}",
            f"Status: {obj.status}",
            f"State Hint: {self._marker_state_text(obj.status)}",
            f"Timestamp: {obj.timestamp:.3f}",
            "",
            "Detection Quality",
            f"Confidence: {obj.confidence:.3f}",
            f"Stability Score: {obj.stability_score:.3f}",
            f"Depth: {obj.depth_m:.3f} m" if obj.depth_m is not None else "Depth: N/A",
            f"BBox xyxy: {obj.bbox_xyxy}",
            f"Center Pixel: {obj.center_pixel}",
            "",
            "Camera Frame 6DoF",
            f"Frame: {pose.frame_id}",
            f"x: {pose.position.x:.4f} m" if pose_available else "x: N/A",
            f"y: {pose.position.y:.4f} m" if pose_available else "y: N/A",
            f"z: {pose.position.z:.4f} m" if pose_available else "z: N/A",
            f"roll: {pose.orientation_euler.roll:.4f} rad" if camera_orientation_available else "roll: N/A",
            f"pitch: {pose.orientation_euler.pitch:.4f} rad" if camera_orientation_available else "pitch: N/A",
            f"yaw: {pose.orientation_euler.yaw:.4f} rad" if camera_orientation_available else "yaw: N/A",
            (
                "Orientation Source: solved from marker template pose"
                if camera_orientation_available
                else "Orientation Source: unavailable for depth-only / YOLO bbox detection"
            ),
            "",
            "Base Frame 6DoF",
        ]
        if quality:
            insert_at = lines.index("Camera Frame 6DoF") - 1
            quality_lines = [
                f"Marker Dots: {quality.get('valid_depth_points', '--')}/{quality.get('num_dots', '--')}",
                f"Match Error: {quality.get('match_error_m', 0.0):.4f} m" if quality.get("match_error_m") is not None else "Match Error: N/A",
                f"Plane RMSE: {quality.get('plane_rmse_m', 0.0):.4f} m" if quality.get("plane_rmse_m") is not None else "Plane RMSE: N/A",
                f"Pose RMSE: {quality.get('pose_rmse_m', 0.0):.4f} m" if quality.get("pose_rmse_m") is not None else "Pose RMSE: N/A",
                f"Pose Method: {quality.get('pose_method', '--')}",
            ]
            lines[insert_at:insert_at] = quality_lines
        if bearing:
            insert_at = lines.index("Camera Frame 6DoF") - 1
            lines[insert_at:insert_at] = [
                "",
                "Bearing",
                f"Pixel Center: {[round(v, 2) for v in bearing.get('pixel_center', [])]}",
                f"Pixel Error: {[round(v, 2) for v in bearing.get('pixel_error', [])]}",
                f"Ray Camera: {[round(v, 4) for v in bearing.get('ray_camera', [])]}",
            ]
        if base:
            lines.extend(
                [
                    f"Frame: {base.frame_id}",
                    f"x: {base.position.x:.4f} m",
                    f"y: {base.position.y:.4f} m",
                    f"z: {base.position.z:.4f} m",
                    f"roll: {base.orientation_euler.roll:.4f} rad" if base_orientation_available else "roll: N/A",
                    f"pitch: {base.orientation_euler.pitch:.4f} rad" if base_orientation_available else "pitch: N/A",
                    f"yaw: {base.orientation_euler.yaw:.4f} rad" if base_orientation_available else "yaw: N/A",
                ]
            )
        else:
            lines.append("Not available / waiting for calibration")
        if self.selected_target_locked_at:
            lines.extend(["", f"Locked At: {self.selected_target_locked_at:.3f}"])
        if self.selected_target_last_seen_at:
            lines.append(f"Last Seen At: {self.selected_target_last_seen_at:.3f}")
        self.selected_target_details.setPlainText("\n".join(lines))

    def _orientation_available(self, obj, pose) -> bool:
        if obj.detection_mode in ("marker", "yolo_marker"):
            return obj.status == "POSE_6DOF"
        if obj.detection_mode in ("aruco", "aruco_solvepnp"):
            return True
        euler = pose.orientation_euler
        return any(abs(value) > 1e-6 for value in (euler.roll, euler.pitch, euler.yaw))

    def _marker_state_text(self, status: str) -> str:
        return {
            "SEARCH": "目标丢失，正在搜索",
            "BEARING_ONLY": "方位锁定，正在靠近",
            "APPROACH": "方位锁定，正在靠近",
            "PARTIAL_DEPTH": "部分深度有效",
            "POSE_6DOF": "6DoF 已锁定，可执行",
            "LOST": "目标丢失，正在搜索",
        }.get(status, status)

    def _capture_target_pixmap(self, obj):
        if obj is None or self.current_frame is None:
            return None
        x1, y1, x2, y2 = obj.bbox_xyxy
        height, width = self.current_frame.shape[:2]
        pad = 12
        x1 = max(0, int(x1) - pad)
        y1 = max(0, int(y1) - pad)
        x2 = min(width, int(x2) + pad)
        y2 = min(height, int(y2) + pad)
        if x2 <= x1 or y2 <= y1:
            return None
        crop = self.current_frame[y1:y2, x1:x2].copy()
        return cv_bgr_to_qpixmap(crop)

    def _apply_task_status(self, status) -> None:
        terminal = {"COMPLETED", "FAILED", "CANCELED", "REJECTED"}
        if status.status == "ESTOP_TRIGGERED":
            self.estop_active = True
            self.robot_busy = False
            self.active_command_id = status.command_id
            self.last_robot_status = "ESTOP"
        elif self.active_command_id and status.command_id != self.active_command_id:
            self.last_status_message = f"Historical status: {status.status}"
            return
        elif status.status in terminal:
            self.robot_busy = False
            self.active_command_id = None
            self.last_robot_status = status.status
        else:
            self.robot_busy = True
            self.active_command_id = status.command_id
            self.last_robot_status = status.status
        self.last_status_message = status.message
        self._refresh_status_bar(status)

    def _refresh_status_bar(self, status=None) -> None:
        progress_part = f" {status.progress:.0%}" if status else ""
        task_part = f"Task: {self.active_command_id}" if self.active_command_id else "Task: --"
        self.status.set_state(
            f"Camera: ONLINE | Vision: RUNNING | Bridge: {self.bridge_status} | "
            f"Robot: {self.last_robot_status}{progress_part} | {task_part} | "
            f"E-STOP: {'TRIGGERED' if self.estop_active else 'SAFE'}",
            self.estop_active,
        )

    def toggle_task_list(self) -> None:
        self._show_task_list(not self.task_list_visible)

    def _show_task_list(self, visible: bool) -> None:
        self.task_list_visible = visible
        self.task_list_group.setVisible(visible)
        self.task_sidebar_btn.setText("<" if visible else ">")
        self.task_sidebar_btn.setToolTip("收起任务列表" if visible else "展开任务列表")
        if visible:
            self.task_sidebar.setMinimumWidth(500)
            self.task_sidebar.setMaximumWidth(16777215)
            self.content_splitter.setSizes([560, 500, 420])
        else:
            self.task_sidebar.setMinimumWidth(34)
            self.task_sidebar.setMaximumWidth(34)
            self.content_splitter.setSizes([34, 740, 500])

    def closeEvent(self, event) -> None:
        self.worker.stop()
        self.worker.wait(1500)
        super().closeEvent(event)


def wrap_group(title: str, widget: QWidget) -> QGroupBox:
    group = QGroupBox(title)
    layout = QVBoxLayout(group)
    layout.addWidget(widget)
    return group
