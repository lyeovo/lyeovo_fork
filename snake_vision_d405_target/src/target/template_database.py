from __future__ import annotations

from datetime import datetime
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.utils.config_io import load_yaml, save_yaml


DEFAULT_DATABASE = {
    "unit": "meter",
    "version": 1,
    "targets": {},
}


class TargetTemplateDatabase:
    def __init__(self, path: str | Path = "config/target_database.yaml"):
        self.path = Path(path)
        self.data = self.load()

    def load(self) -> dict[str, Any]:
        data = load_yaml(self.path, default=deepcopy(DEFAULT_DATABASE))
        data.setdefault("unit", "meter")
        data.setdefault("version", 1)
        data.setdefault("targets", {})
        return data

    def save(self) -> None:
        save_yaml(self.data, self.path)

    def targets(self) -> dict[str, Any]:
        return self.data.get("targets", {})

    def upsert_target(
        self,
        target_id: str,
        template_points,
        learned_frames: int,
        used_frames: int,
        average_plane_rmse_m: float,
        average_depth_valid_ratio: float,
        notes: str = "auto learned from D405 depth",
    ) -> dict[str, Any]:
        entry = {
            "target_id": target_id,
            "num_points": int(len(template_points)),
            "template_points": [[float(x), float(y), float(z)] for x, y, z in template_points],
            "learned_frames": int(learned_frames),
            "used_frames": int(used_frames),
            "average_plane_rmse_m": float(average_plane_rmse_m),
            "average_depth_valid_ratio": float(average_depth_valid_ratio),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "notes": notes,
        }
        self.data.setdefault("targets", {})[target_id] = entry
        self.save()
        return entry
