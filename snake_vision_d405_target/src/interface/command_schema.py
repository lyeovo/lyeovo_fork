from dataclasses import asdict, dataclass, field
from typing import Dict
import json

@dataclass
class RobotCommand:
    timestamp: float
    command_type: str
    target_id: str
    target_pose: dict
    frame_id: str = "camera_left"
    extra: Dict = field(default_factory=dict)

def command_to_json(command, indent=2):
    return json.dumps(asdict(command), ensure_ascii=False, indent=indent)
