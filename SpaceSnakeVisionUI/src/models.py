from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Euler:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


@dataclass
class Quaternion:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0


@dataclass
class Pose3D:
    frame_id: str = "camera_color_optical_frame"
    position: Vector3 = field(default_factory=Vector3)
    orientation_euler: Euler = field(default_factory=Euler)
    orientation_quat: Quaternion = field(default_factory=Quaternion)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pose3D":
        return cls(
            frame_id=data.get("frame_id", "camera_color_optical_frame"),
            position=Vector3(**data.get("position", {})),
            orientation_euler=Euler(**data.get("orientation_euler", {})),
            orientation_quat=Quaternion(**data.get("orientation_quat", {})),
        )

    @classmethod
    def from_json(cls, raw: str) -> "Pose3D":
        return cls.from_dict(json.loads(raw))


@dataclass
class DetectedObject:
    target_id: str
    timestamp: float
    class_name: str
    display_name: str
    detection_mode: str
    marker_id: Optional[int]
    confidence: float
    stability_score: float
    bbox_xyxy: List[int]
    center_pixel: List[int]
    depth_m: Optional[float]
    pose_camera: Pose3D
    pose_base: Optional[Pose3D] = None
    status: str = "AVAILABLE"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DetectedObject":
        data = dict(data)
        data["pose_camera"] = Pose3D.from_dict(data["pose_camera"])
        data["pose_base"] = Pose3D.from_dict(data["pose_base"]) if data.get("pose_base") else None
        return cls(**data)

    @classmethod
    def from_json(cls, raw: str) -> "DetectedObject":
        return cls.from_dict(json.loads(raw))


@dataclass
class RobotState:
    state: str = "IDLE"
    end_effector_pose_base: Optional[Pose3D] = None
    joint_positions: List[float] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RobotState":
        data = dict(data)
        if data.get("end_effector_pose_base"):
            data["end_effector_pose_base"] = Pose3D.from_dict(data["end_effector_pose_base"])
        return cls(**data)


@dataclass
class TaskCommand:
    schema_version: str
    command_id: str
    timestamp: float
    source: str
    command_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    selected_target: Optional[Dict[str, Any]] = None
    destination: Optional[Dict[str, Any]] = None
    motion_params: Dict[str, Any] = field(default_factory=dict)
    safety: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "TaskCommand":
        data = json.loads(raw)
        return cls(**data)


@dataclass
class TaskStatus:
    schema_version: str
    command_id: str
    timestamp: float
    status: str
    current_step: str
    progress: float
    message: str
    robot_state: RobotState = field(default_factory=RobotState)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "TaskStatus":
        data = json.loads(raw)
        data["robot_state"] = RobotState.from_dict(data.get("robot_state", {}))
        return cls(**data)


def new_command_id(prefix: str = "CMD") -> str:
    return f"{prefix}-{time.strftime('%Y%m%d')}-{int(time.time() * 1000) % 100000:05d}"
