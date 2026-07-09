from src.bridge.command_builder import build_task_command


def test_home_command_can_build_without_target():
    cmd = build_task_command("home", None, "Safe_Zone", 0.05, "demo_safe", "demo_grip")
    assert cmd.command_type == "home"
    assert cmd.destination["name"] == "Safe_Zone"
