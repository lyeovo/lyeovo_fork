from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch latest_targets.json for motion-control integration tests.")
    parser.add_argument("--path", default="data/vision/latest_targets.json", help="Path to latest vision-state JSON.")
    parser.add_argument("--interval", type=float, default=0.2, help="Polling interval in seconds.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    last_timestamp = None
    print(f"[INFO] Watching {path.resolve()}")
    while True:
        if not path.exists():
            print("[WAIT] vision state file not found")
            time.sleep(args.interval)
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] read failed: {exc}")
            time.sleep(args.interval)
            continue
        timestamp = data.get("timestamp")
        if timestamp != last_timestamp:
            last_timestamp = timestamp
            targets = data.get("targets", [])
            best = data.get("selected_target") or (targets[0] if targets else None)
            if best is None:
                print(f"[{timestamp:.3f}] SEARCH no target")
            else:
                bearing = best.get("bearing") or {}
                quality = best.get("quality") or {}
                pose = best.get("pose_camera")
                center = bearing.get("pixel_center")
                ray = bearing.get("ray_camera")
                print(
                    f"[{timestamp:.3f}] {best.get('target_id')} {best.get('status')} "
                    f"center={center} ray={ray} rough_z={quality.get('rough_distance_m')} "
                    f"dots={quality.get('valid_depth_points')}/{quality.get('num_dots')} "
                    f"pose={'yes' if pose else 'no'}"
                )
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
