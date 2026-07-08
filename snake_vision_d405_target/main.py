import argparse
import runpy

def main():
    ap = argparse.ArgumentParser(description="D405 coded target stereo vision pipeline")
    ap.add_argument("--mode", choices=["realtime", "offline", "show_camera", "save_intrinsics"], required=True)
    ap.add_argument("--left")
    ap.add_argument("--right")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.mode == "show_camera":
        runpy.run_path("scripts/01_show_d405_stereo.py", run_name="__main__")
    elif args.mode == "save_intrinsics":
        runpy.run_path("scripts/02_save_d405_intrinsics.py", run_name="__main__")
    elif args.mode == "realtime":
        runpy.run_path("scripts/08_run_realtime_pipeline.py", run_name="__main__")
    elif args.mode == "offline":
        if not args.left or not args.right:
            raise SystemExit("--mode offline requires --left and --right")
        import sys
        sys.argv = ["09_run_offline_pair.py", "--left", args.left, "--right", args.right] + (["--show"] if args.show else [])
        runpy.run_path("scripts/09_run_offline_pair.py", run_name="__main__")

if __name__ == "__main__":
    main()
