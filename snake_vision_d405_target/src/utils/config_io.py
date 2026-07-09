from pathlib import Path
import yaml

def load_yaml(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"Config file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_yaml(data, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
