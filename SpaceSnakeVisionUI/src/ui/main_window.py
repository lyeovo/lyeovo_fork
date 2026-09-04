from __future__ import annotations

import copy
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..bridge.command_builder import build_estop_command, build_task_command
from ..bridge.command_validator import validate_command
from ..bridge.vision_state_publisher import VisionStatePublisher
from ..mission.state_machine import MissionStateMachine, ROBOT_WAIT_NODES
from ..models import TaskCommand
from ..state.system_state import SystemStateStore
from ..utils.image_utils import cv_bgr_to_qpixmap
from ..vision.pipeline import VisionPipeline
from .log_console import LogConsoleWidget
from .navigation import NavigationWidget
from .pages.control_page import ControlPage
from .pages.mission_page import MissionPage
from .pages.system_page import SystemPage
from .pages.task_page import TaskPage
from .pages.vision_page import VisionPage
from .status_bar import MissionStatusBar


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
    """空间蛇形机械臂任务总控台 (Mission Control HMI) 主窗口"""

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
        self.project_root = Path(project_root)

        # 全局状态中心与状态机
        self.store = SystemStateStore.instance()
        self.state_machine = MissionStateMachine(self.store)

        # 视觉流发布器
        self.vision_state_publisher = VisionStatePublisher(self.project_root / "data" / "vision")

        # 运行时缓存
        self.objects: List[Any] = []
        self.selected_id: Optional[str] = None
        self.selected_target_snapshot = None
        self.selected_target_locked_at: Optional[float] = None
        self.selected_target_last_seen_at: Optional[float] = None
        self.pending_command: Optional[TaskCommand] = None
        self.current_frame = None

        self.active_command_id: Optional[str] = None
        self.robot_busy = False
        self.estop_active = False
        self.last_robot_status = "IDLE"
        self.last_status_message = ""

        # 反馈闭环度量：发布时刻（RTT）、FPS 滚动统计
        self._publish_ts: Dict[str, float] = {}
        self._rtt_done: set = set()
        self._fps_frames: int = 0
        self._fps_last: float = time.time()

        # 窗口基本属性
        self.setWindowTitle("ORBITAL SNAKE ROBOT MISSION CONTROL · 任务总控台")
        self.resize(1360, 840)

        # 载入主题
        qss_path = self.project_root / "src" / "ui" / "theme.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

        self._build_ui()

        # 启动视觉感知线程
        self.worker = VisionWorker(camera, detector_mode, yolo_model, yolo_conf, self.project_root)
        self.worker.frameReady.connect(self.on_frame)
        self.worker.error.connect(lambda msg: self.log.log(f"[ERROR] {msg}"))
        self.worker.info.connect(lambda msg: self.log.log(f"[INFO] {msg}"))
        self.worker.start()

        # 状态轮询定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_status)
        self.timer.start(600)

        self.log.log("Mission Control HMI initialized successfully.")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 1. 顶部航天总控 Header
        self.header = MissionStatusBar(self)
        main_layout.addWidget(self.header)

        # 2. 中间：左侧窄导航栏 + 中央多页面 StackedWidget
        center_row = QHBoxLayout()
        center_row.setContentsMargins(0, 0, 0, 0)
        center_row.setSpacing(4)

        self.navigation = NavigationWidget()
        center_row.addWidget(self.navigation)

        self.stack = QStackedWidget()

        # 共享日志组件
        self.log = LogConsoleWidget()

        # Page 0: 【MISSION】核心任务总览
        self.page_mission = MissionPage(self.state_machine, self)
        self.page_mission.stepTriggerRequested.connect(self.on_mission_step_trigger)
        self.page_mission.stepChoiceRequested.connect(self.on_mission_step_choice)
        self.page_mission.resetRequested.connect(self.on_mission_reset)
        self.page_mission.camera_view.targetClicked.connect(self.select_by_pixel)
        self.stack.addWidget(self.page_mission)

        # Page 1: 【VISION】视觉感知
        self.page_vision = VisionPage(self)
        self.page_vision.targetSelected.connect(self.select_target)
        self.page_vision.camera_view.targetClicked.connect(self.select_by_pixel)
        self.stack.addWidget(self.page_vision)

        # Page 2: 【TASK】任务作业
        self.page_task = TaskPage(self)
        self.page_task.generateRequested.connect(self.generate_command)
        self.page_task.publishRequested.connect(self.publish_command)
        self.page_task.estopRequested.connect(self.emergency_stop)
        self.page_task.cancelRequested.connect(self.cancel_task)
        self.page_task.mission_map.coordinateSelected.connect(self.on_map_coordinate_selected)
        self.stack.addWidget(self.page_task)

        # Page 3: 【CONTROL】运动控制
        self.page_control = ControlPage(self)
        self.stack.addWidget(self.page_control)

        # Page 4: 【SYSTEM】系统监控
        self.page_system = SystemPage(self.log, self)
        self.stack.addWidget(self.page_system)

        center_row.addWidget(self.stack, stretch=1)
        main_layout.addLayout(center_row, stretch=1)

        # 导航与急停信号绑定
        self.navigation.pageChanged.connect(self.stack.setCurrentIndex)
        self.navigation.estopTriggered.connect(self.emergency_stop)

    # ---------------- 视觉感知与目标选择 ----------------
    def on_frame(self, image, objects) -> None:
        self.objects = list(objects)
        self.current_frame = image.copy()

        # 实测视觉流水线 FPS（每秒刷新一次）
        self._fps_frames += 1
        now = time.time()
        elapsed = now - self._fps_last
        if elapsed >= 1.0:
            self.store.update_vision(fps=round(self._fps_frames / elapsed, 1))
            self._fps_frames = 0
            self._fps_last = now

        # 有帧到达即视为相机在线（仅在掉线后恢复时更新，避免逐帧广播）
        if not self.store.state.health.camera_online:
            self.store.update_health(camera_online=True)

        # 在画面上绘制选框与准星
        VisionPipeline.redraw_selection(image, self.objects, self.selected_id)
        pix = cv_bgr_to_qpixmap(image)

        # 同步刷新 MissionPage 与 VisionPage 相机
        self.page_mission.camera_view.set_frame_size(image.shape[1], image.shape[0])
        self.page_mission.camera_view.setPixmap(pix)

        self.page_vision.camera_view.set_frame_size(image.shape[1], image.shape[0])
        self.page_vision.camera_view.setPixmap(pix)
        self.page_vision.target_table.update_targets(self.objects, self.selected_id)

        # 同步刷新俯视地图
        self.page_task.mission_map.update_map(self.objects, self.selected_id)

        # 发布最新视觉数据供控制模块读取
        try:
            self.vision_state_publisher.publish(self.objects, self.selected_id)
        except Exception as exc:
            pass

        # 遥测数据同步至状态中心
        current = self._selected_obj()
        if self.selected_id and current:
            self.selected_target_last_seen_at = current.timestamp
            self._sync_vision_to_store(current)
        elif not self.objects:
            self.store.update_vision(
                detector_status="SEARCH",
                selected_target_id=None,
                target_class=None,
                depth_m=None,
                pose_available=False,
            )

    def _sync_vision_to_store(self, obj) -> None:
        pose = getattr(obj, "pose_camera", None)
        pos = getattr(pose, "position", None) if pose else None
        euler = getattr(pose, "orientation_euler", None) if pose else None
        quality = getattr(obj, "quality", {}) or {}

        self.store.update_vision(
            selected_target_id=obj.target_id,
            target_class=obj.class_name,
            detector_status=obj.status,
            confidence=obj.confidence,
            depth_m=obj.depth_m,
            pose_available=bool(obj.status == "POSE_6DOF"),
            pos_x=getattr(pos, "x", 0.0) if pos else 0.0,
            pos_y=getattr(pos, "y", 0.0) if pos else 0.0,
            pos_z=getattr(pos, "z", 0.0) if pos else 0.0,
            roll=getattr(euler, "roll", 0.0) if euler else 0.0,
            pitch=getattr(euler, "pitch", 0.0) if euler else 0.0,
            yaw=getattr(euler, "yaw", 0.0) if euler else 0.0,
            valid_dots=quality.get("num_dots", 0),
        )

    def select_target(self, target_id: str) -> None:
        self.selected_id = target_id
        obj = self._selected_obj()
        if obj:
            self.selected_target_snapshot = copy.deepcopy(obj)
            self.selected_target_locked_at = time.time()
            self.selected_target_last_seen_at = obj.timestamp
            self._sync_vision_to_store(obj)
            self.log.log(f"[VISION] Target locked: {obj.target_id} ({obj.class_name})")

        self.page_task.mission_map.update_map(self.objects, self.selected_id)

    def select_by_pixel(self, x: int, y: int) -> None:
        for obj in self.objects:
            x1, y1, x2, y2 = obj.bbox_xyxy
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.select_target(obj.target_id)
                # 联动状态机：若当前处于视野确认或点选目标阶段，自动生成并发布 move_for_pick
                if self.state_machine.current_node_id in ("VISION_CHECK_1", "VISION_CHECK_2", "TARGET_SELECT_PICK"):
                    self.state_machine.jump_to("TARGET_SELECT_PICK")
                    self.log.log(f"[MISSION] 相机画面点选锁定目标 {obj.target_id}，自动生成并发布靠近抓取指令 (move_for_pick)...")
                    self.generate_command("move_for_pick", {})
                    self.publish_command()
                break

    def on_map_coordinate_selected(self, x: float, y: float) -> None:
        self.page_task.command_panel.set_target_coordinate(x, y)
        self.log.log(f"[MAP] Target coordinate selected: X={x:+.3f}m, Y={y:+.3f}m")

    # ---------------- 任务流程状态机联动 ----------------
    def on_mission_step_trigger(self) -> None:
        cur_node = self.state_machine.current_node
        nid = cur_node.node_id

        if nid == "ROBOT_START":
            self.log.log("[MISSION] Operator starting robot (Homing/Reset)...")
            self.generate_command("reset", {})
            self.publish_command()

        elif nid == "COARSE_MAP_SELECT":
            # 切换到 TaskPage 让操作员在 Map 上点选，发布 move_to 后自动推进
            self.stack.setCurrentIndex(2)
            self.navigation.set_current_page(2)
            self.log.log("[MISSION] Please click waypoint on Map in TASK page, then generate & publish move_to.")

        elif nid == "TARGET_SELECT_PICK":
            if not self.selected_id:
                self.log.log("[MISSION] Warning: No target locked! Please select target on Camera image first.")
                return
            self.log.log(f"[MISSION] Publishing move_for_pick for target: {self.selected_id}")
            self.generate_command("move_for_pick", {})
            self.publish_command()

        elif nid == "OPERATOR_PICK_CMD":
            self.log.log("[MISSION] Operator triggering pick command...")
            self.generate_command("pick", {})
            self.publish_command()

        elif nid == "OPERATOR_PLACE_TASK":
            self.log.log("[MISSION] Publishing move_for_place...")
            self.generate_command("move_for_place", {"destination": "Goal_Zone"})
            self.publish_command()

        elif nid == "OPERATOR_PLACE_CMD":
            self.log.log("[MISSION] Operator triggering place command...")
            self.generate_command("place", {})
            self.publish_command()

        elif nid == "MISSION_COMPLETE":
            # 任务完成，点击进入新工件循环：清空上周期目标锁定与各步骤高亮，回到起点
            self.selected_id = None
            self.selected_target_snapshot = None
            self.store.update_vision(selected_target_id=None)
            next_node = self.state_machine.advance()
            self.log.log(f"[MISSION] 进入新工件循环，已清空上周期完成高亮与目标锁定，回到 [{next_node.index:02d}] {next_node.title}。")

        else:
            # 非命令节点（SYS_START / ROBOT 等待）：手动推进
            next_node = self.state_machine.advance()
            self.log.log(f"[MISSION] Advanced to stage: [{next_node.index:02d}] {next_node.title}")

    def on_mission_step_choice(self, choice: bool) -> None:
        next_node = self.state_machine.advance(decision_choice=choice)
        choice_text = "YES / 确认" if choice else "NO / 否"
        self.log.log(f"[MISSION] Branch chosen: {choice_text} -> [{next_node.index:02d}] {next_node.title}")

        if next_node.node_id == "COARSE_MAP_SELECT":
            # 引导跳转到 TASK 页面
            self.stack.setCurrentIndex(2)
            self.navigation.set_current_page(2)

    def on_mission_reset(self) -> None:
        self.state_machine.reset()
        self.selected_id = None
        self.selected_target_snapshot = None
        self.store.update_vision(selected_target_id=None)
        self.log.log("[MISSION] 流程已重置回初始状态，各步骤高亮与目标锁定已全部清空。")

    # ---------------- 命令生成与发布 ----------------
    def generate_command(self, command_type: str, params: dict) -> None:
        obj = self._get_command_target()
        destination = params.get("destination")
        result = validate_command(
            command_type,
            params=params,
            target=obj,
            destination_name=destination,
            estop_active=self.estop_active,
            robot_busy=self.robot_busy,
            locked_at=self.selected_target_locked_at,
        )
        report = result.to_report()

        cmd = build_task_command(
            command_type,
            params=params,
            selected_target=obj,
            destination_name=destination,
            estop_active=self.estop_active,
            robot_busy=self.robot_busy,
            validation_report=report,
            locked_at=self.selected_target_locked_at,
        )
        self.pending_command = cmd

        # 更新 TaskPage 预览
        self.page_task.command_panel.set_preview(cmd.to_json(), report)
        self.log.log(f"[COMMAND] Generated {command_type}: {report['validation_message']}")

    def publish_command(self) -> None:
        if not self.pending_command:
            self.log.log("[COMMAND] No pending command to publish.")
            return

        cmd = self.pending_command
        self.active_command_id = cmd.command_id
        self._publish_ts[cmd.command_id] = time.time()
        path = self.bridge.publish_command(cmd)

        self.store.update_command(
            command_id=cmd.command_id,
            command_type=cmd.command_type,
            control_status="DISPATCHED",
            progress=0.0,
            message="命令已发送至 outbox",
        )

        self.page_task.task_list.add_task(cmd, publish_ref=str(path.name))
        self.log.log(f"[COMMAND] Published {cmd.command_id} to {path.name}")

        # 发布即推进：命令命中当前节点 hint 且通过安全校验时推进流程
        if cmd.safety.get("allow_execute", False):
            if self.state_machine.advance_if_hint(cmd.command_type):
                self.log.log(f"[MISSION] Auto-advanced on publishing '{cmd.command_type}'.")
        else:
            self.log.log(f"[COMMAND] '{cmd.command_type}' 未通过安全校验，流程保持当前节点。")

    def emergency_stop(self) -> None:
        self.estop_active = True
        cmd = build_estop_command()
        self.bridge.publish_command(cmd)
        self.active_command_id = cmd.command_id

        self.store.update_health(estop_active=True)
        self.store.update_command(
            command_id=cmd.command_id,
            command_type="emergency_stop",
            control_status="ESTOP_TRIGGERED",
            progress=0.0,
            message="E-STOP 触发！",
        )
        self.log.log("[SAFETY] EMERGENCY STOP TRIGGERED!")

    def cancel_task(self) -> None:
        if self.active_command_id:
            cmd = build_task_command("cancel_task", {}, estop_active=self.estop_active)
            self.bridge.publish_command(cmd)
            self.log.log(f"[COMMAND] Sent cancel request for {self.active_command_id}")

    # ---------------- 状态轮询 ----------------
    def poll_status(self) -> None:
        statuses = self.bridge.poll_status()
        if not statuses:
            self._update_control_freshness()
            return
        for status in statuses:
            self._consume_status(status)

    def _consume_status(self, status) -> None:
        now = time.time()
        cid = status.command_id
        st = status.status

        # RTT：发布命令后收到该命令的首个状态回传时实测一次
        if cid in self._publish_ts and cid not in self._rtt_done:
            rtt = max(0.0, (now - self._publish_ts[cid]) * 1000.0)
            self.store.update_health(bridge_rtt_ms=rtt)
            self._rtt_done.add(cid)

        self.robot_busy = st in ("ACCEPTED", "PLANNING", "EXECUTING")
        self.last_robot_status = st

        self.store.update_command(
            command_id=cid,
            command_type=status.current_step or "--",
            control_status=st,
            progress=status.progress,
            message=status.message,
        )
        self.store.update_health(
            robot_busy=self.robot_busy,
            control_online=True,
            last_status_rx=now,
        )

        self._apply_robot_state(status.robot_state)
        self._apply_planner(status.planner)

        self.page_task.task_list.update_status(status)

        # 完成即推进：ROBOT 等待节点上，活跃命令 COMPLETED 时推进状态机
        if st == "COMPLETED" and cid == self.active_command_id:
            if self.state_machine.current_node_id in ROBOT_WAIT_NODES:
                self.state_machine.advance()

    def _apply_robot_state(self, rob) -> None:
        if rob is None:
            return
        kwargs: Dict[str, Any] = {}

        if getattr(rob, "state", None):
            kwargs["state"] = rob.state

        joints = getattr(rob, "joint_positions", None)
        if joints and isinstance(joints, list) and len(joints) >= 6:
            vals = list(joints[:6])
            if str(getattr(rob, "joint_positions_unit", "deg")).lower() == "rad":
                vals = [math.degrees(v) for v in vals]
            kwargs["joint_angles_deg"] = vals

        ee = getattr(rob, "end_effector_pose_base", None)
        if ee is not None:
            kwargs["ee_x"] = ee.position.x
            kwargs["ee_y"] = ee.position.y
            kwargs["ee_z"] = ee.position.z
            kwargs["ee_roll"] = ee.orientation_euler.roll
            kwargs["ee_pitch"] = ee.orientation_euler.pitch
            kwargs["ee_yaw"] = ee.orientation_euler.yaw

        gripper_map = {0: "HOLDING", 1: "OPEN", 2: "CLOSED"}
        g = getattr(rob, "gripper", None)
        if g in gripper_map:
            kwargs["gripper_state"] = gripper_map[g]

        if kwargs:
            self.store.update_robot(**kwargs)

    def _apply_planner(self, planner) -> None:
        if not planner:
            return
        kwargs: Dict[str, Any] = {}
        if planner.get("method_used"):
            kwargs["method_used"] = str(planner["method_used"])
        for key in ("solve_time_ms", "tracking_error_mm", "angle_error_deg"):
            val = planner.get(key)
            if val is not None:
                kwargs[key] = val
        if kwargs:
            self.store.update_robot(**kwargs)

    def _update_control_freshness(self) -> None:
        h = self.store.state.health
        if (
            h.control_online
            and h.last_status_rx is not None
            and (time.time() - h.last_status_rx) > 3.0
        ):
            self.robot_busy = False
            self.store.update_health(control_online=False, robot_busy=False)

    def _selected_obj(self):
        for obj in self.objects:
            if obj.target_id == self.selected_id:
                return obj
        return None

    def _get_command_target(self):
        obj = self._selected_obj()
        if obj:
            return obj
        if self.selected_target_snapshot and self.selected_id == self.selected_target_snapshot.target_id:
            return self.selected_target_snapshot
        return None

    def closeEvent(self, event) -> None:
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1000)
        event.accept()
