from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json

@dataclass
class TargetPoseResult:
    timestamp: float
    target_id: str
    frame_id: str
    position: List[float]
    orientation: Optional[List[float]]
    points_3d: List[List[float]]
    quality: Dict[str, Any]

def result_to_dict(result):
    pos = result.position or [None, None, None]
    ori = result.orientation
    return {
        "timestamp": result.timestamp,
        "target_id": result.target_id,
        "frame_id": result.frame_id,
        "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
        "orientation": None if ori is None else {"qx": ori[0], "qy": ori[1], "qz": ori[2], "qw": ori[3]},
        "points_3d": result.points_3d,
        "quality": result.quality,
    }

def result_to_json(result, indent=2):
    return json.dumps(result_to_dict(result), ensure_ascii=False, indent=indent)
