from __future__ import annotations

import pytest

from src.mission.state_machine import MissionState, MissionStateMachine
from src.mission.workflow_definition import WORKFLOW_NODES
from src.state.system_state import SystemStateStore


def test_mission_state_machine_initialization():
    store = SystemStateStore()
    sm = MissionStateMachine(store)
    assert sm.current_node_id == "SYS_START"
    assert sm.current_node.index == 1
    assert store.state.mission.state == "SYS_START"


def test_mission_state_machine_advance_linear():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    # 1 -> 2
    n2 = sm.advance()
    assert n2.node_id == "ROBOT_START"
    assert sm.is_completed("SYS_START")

    # 2 -> 3 (VISION_CHECK_1, 决策节点)
    n3 = sm.advance()
    assert n3.node_id == "VISION_CHECK_1"
    assert n3.category == "DECISION"


def test_mission_state_machine_decision_branches():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    sm.jump_to("VISION_CHECK_1")

    # 测试分支 【否】 -> COARSE_MAP_SELECT
    branch_no = sm.advance(decision_choice=False)
    assert branch_no.node_id == "COARSE_MAP_SELECT"

    # 重置回到 VISION_CHECK_1
    sm.jump_to("VISION_CHECK_1")
    # 测试分支 【是】 -> TARGET_SELECT_PICK
    branch_yes = sm.advance(decision_choice=True)
    assert branch_yes.node_id == "TARGET_SELECT_PICK"


def test_mission_state_machine_pick_branch():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    sm.jump_to("PICK_CHECK")
    # 抓取失败 -> 返回 OPERATOR_PICK_CMD 重试
    fail_node = sm.advance(decision_choice=False)
    assert fail_node.node_id == "OPERATOR_PICK_CMD"

    sm.jump_to("PICK_CHECK")
    # 抓取成功 -> 进入 OPERATOR_PLACE_TASK
    succ_node = sm.advance(decision_choice=True)
    assert succ_node.node_id == "OPERATOR_PLACE_TASK"


def test_mission_state_machine_reset_and_jump():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    sm.jump_to("TARGET_REACHED")
    assert sm.current_node_id == "TARGET_REACHED"

    sm.reset()
    assert sm.current_node_id == "SYS_START"
    assert len(sm.completed_nodes) == 0
