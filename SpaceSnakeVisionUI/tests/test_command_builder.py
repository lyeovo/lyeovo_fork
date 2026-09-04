import json
from src.bridge.command_builder import build_estop_command, build_task_command
from src.models import TaskCommand


def test_build_all_ten_command_types():
    # 1. move_to
    cmd1 = build_task_command("move_to", {"x": 0.35, "y": -0.10})
    assert cmd1.command_type == "move_to"
    assert cmd1.params["x"] == 0.35
    assert cmd1.params["y"] == -0.10
    assert cmd1.schema_version == "2.0"

    # 2. move_along
    cmd2 = build_task_command("move_along", {"theta_deg": 45.0, "distance_m": 0.20})
    assert cmd2.command_type == "move_along"
    assert cmd2.params["theta_deg"] == 45.0

    # 3. move_for_pick
    cmd3 = build_task_command("move_for_pick", {})
    assert cmd3.command_type == "move_for_pick"

    # 4. move_for_place
    cmd4 = build_task_command("move_for_place", {"destination": "Goal_Zone"})
    assert cmd4.command_type == "move_for_place"
    assert cmd4.destination["name"] == "Goal_Zone"

    # 5. rotate
    cmd5 = build_task_command("rotate", {"alpha_deg": 90.0})
    assert cmd5.params["alpha_deg"] == 90.0

    # 6. rotate_arm
    cmd6 = build_task_command("rotate_arm", {"joint_index": 2, "alpha_deg": -30.0})
    assert cmd6.params["joint_index"] == 2
    assert cmd6.params["alpha_deg"] == -30.0

    # 7. facing_arm
    cmd7 = build_task_command("facing_arm", {"joint_index": 3, "theta_deg": 60.0})
    assert cmd7.params["joint_index"] == 3
    assert cmd7.params["theta_deg"] == 60.0

    # 8. pick
    cmd8 = build_task_command("pick", {})
    assert cmd8.command_type == "pick"

    # 9. place
    cmd9 = build_task_command("place", {})
    assert cmd9.command_type == "place"

    # 10. withdraw
    cmd10 = build_task_command("withdraw", {})
    assert cmd10.command_type == "withdraw"

    # 11. reset
    cmd11 = build_task_command("reset", {})
    assert cmd11.command_type == "reset"

    # 12. estop
    cmd_estop = build_estop_command()
    assert cmd_estop.command_type == "emergency_stop"
    assert cmd_estop.safety["estop_active"] is True

    # JSON round-trip test
    raw = cmd1.to_json()
    parsed = TaskCommand.from_json(raw)
    assert parsed.command_id == cmd1.command_id
    assert parsed.params == {"x": 0.35, "y": -0.10}
