from pathlib import Path
from src.interface.result_schema import result_to_json
from src.utils.time_utils import filename_timestamp

class JsonResultPublisher:
    def __init__(self, output_dir, save_json=True, print_json=True):
        self.output_dir = Path(output_dir)
        self.save_json = save_json
        self.print_json = print_json
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, result):
        text = result_to_json(result)
        if self.print_json:
            print(text)
        if self.save_json:
            path = self.output_dir / f"target_pose_{filename_timestamp()}.json"
            path.write_text(text, encoding="utf-8")
            print(f"[INFO] JSON saved: {path}")
