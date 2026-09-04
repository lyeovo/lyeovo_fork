from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QObject, Signal


@dataclass
class MissionInfo:
    mission_id: str = "MISSION-01"
    name: str = "目标工件抓取装配任务"
    state: str = "SYSTEM_READY"
    step_index: int = 1
    total_steps: int = 13
    status_text: str = "系统就绪，等待启动"


@dataclass
class ActiveCommandInfo:
    command_id: Optional[str] = None
    command_type: str = "--"
    control_status: str = "IDLE"
    progress: float = 0.0
    message: str = "就绪"


@dataclass
class RobotTelemetry:
    state: str = "IDLE"  # IDLE, MOVING, GRASPING, HOLDING, ESTOP
    ee_x: float = 0.0
    ee_y: float = 0.0
    ee_z: float = 0.0
    ee_roll: float = 0.0
    ee_pitch: float = 0.0
    ee_yaw: float = 0.0
    joint_angles_deg: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    gripper_state: str = "OPEN"  # OPEN, CLOSING, CLOSED, HOLDING
    method_used: str = "--"  # 规划算法（auto/rrt/rrtstar/cvae/momentum...）
    solve_time_ms: Optional[float] = None  # IK/轨迹求解耗时
    tracking_error_mm: Optional[float] = None  # 末端跟踪误差 (dist_end)
    angle_error_deg: Optional[float] = None  # 末端角度误差 (err_ang)
    telemetry_source: str = "file"  # 遥测来源通道: file | tcp


@dataclass
class VisionTelemetry:
    camera_status: str = "ONLINE"
    detector_status: str = "SEARCH"
    selected_target_id: Optional[str] = None
    target_class: Optional[str] = None
    confidence: float = 0.0
    depth_m: Optional[float] = None
    pose_available: bool = False
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    valid_dots: int = 0
    total_dots: int = 8
    fps: float = 30.0


@dataclass
class SystemHealth:
    camera_online: bool = True
    vision_running: bool = True
    control_online: bool = False
    dspace_connected: bool = False
    bridge_mode: str = "FILE"
    estop_active: bool = False
    robot_busy: bool = False
    bridge_rtt_ms: Optional[float] = None  # publish→首个状态回传实测往返延时
    last_status_rx: Optional[float] = None  # 最近一次收到状态的时刻（新鲜度判定）


@dataclass
class SystemState:
    timestamp: float = field(default_factory=time.time)
    mission: MissionInfo = field(default_factory=MissionInfo)
    command: ActiveCommandInfo = field(default_factory=ActiveCommandInfo)
    robot: RobotTelemetry = field(default_factory=RobotTelemetry)
    vision: VisionTelemetry = field(default_factory=VisionTelemetry)
    health: SystemHealth = field(default_factory=SystemHealth)


class SystemStateStore(QObject):
    """单例全局状态存储与响应总线"""

    stateChanged = Signal(object)  # 广播 SystemState

    _instance: Optional[SystemStateStore] = None

    def __init__(self) -> None:
        super().__init__()
        self.state = SystemState()

    @classmethod
    def instance(cls) -> SystemStateStore:
        if cls._instance is None:
            cls._instance = SystemStateStore()
        return cls._instance

    def update_mission(self, state: str, step_index: int, status_text: str, mission_id: Optional[str] = None) -> None:
        self.state.timestamp = time.time()
        self.state.mission.state = state
        self.state.mission.step_index = step_index
        self.state.mission.status_text = status_text
        if mission_id:
            self.state.mission.mission_id = mission_id
        self.stateChanged.emit(self.state)

    def update_command(self, command_id: Optional[str], command_type: str, control_status: str, progress: float, message: str) -> None:
        self.state.timestamp = time.time()
        self.state.command.command_id = command_id
        self.state.command.command_type = command_type
        self.state.command.control_status = control_status
        self.state.command.progress = progress
        self.state.command.message = message
        self.stateChanged.emit(self.state)

    def update_vision(self, **kwargs: Any) -> None:
        self.state.timestamp = time.time()
        for k, v in kwargs.items():
            if hasattr(self.state.vision, k):
                setattr(self.state.vision, k, v)
        self.stateChanged.emit(self.state)

    def update_robot(self, **kwargs: Any) -> None:
        self.state.timestamp = time.time()
        for k, v in kwargs.items():
            if hasattr(self.state.robot, k):
                setattr(self.state.robot, k, v)
        self.stateChanged.emit(self.state)

    def update_health(self, **kwargs: Any) -> None:
        self.state.timestamp = time.time()
        for k, v in kwargs.items():
            if hasattr(self.state.health, k):
                setattr(self.state.health, k, v)
        self.stateChanged.emit(self.state)
