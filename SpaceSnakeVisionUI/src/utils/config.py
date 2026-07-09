from pathlib import Path
from typing import Any, Dict

import yaml


def load_yaml(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return default or {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
