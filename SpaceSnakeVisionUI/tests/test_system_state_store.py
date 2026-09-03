from __future__ import annotations

import pytest
from src.state.system_state import SystemStateStore


def test_system_state_store_updates():
    store = SystemStateStore()
    received_states = []

    def on_state(s):
        received_states.append(s)

    store.stateChanged.connect(on_state)

    store.update_mission("ROBOT_START", 2, "启动中")
    assert store.state.mission.state == "ROBOT_START"
    assert store.state.mission.step_index == 2
    assert len(received_states) == 1

    store.update_command("CMD-001", "move_to", "EXECUTING", 0.5, "移动中")
    assert store.state.command.command_id == "CMD-001"
    assert store.state.command.progress == 0.5
    assert len(received_states) == 2

    store.update_vision(selected_target_id="target_1", confidence=0.98, depth_m=0.35)
    assert store.state.vision.selected_target_id == "target_1"
    assert store.state.vision.confidence == 0.98
    assert store.state.vision.depth_m == 0.35
    assert len(received_states) == 3
