from __future__ import annotations

import pytest

from src.mission.state_machine import MissionState, MissionStateMachine, ROBOT_WAIT_NODES
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

    sm.advance()  # SYS_START -> completed
    sm.advance()  # ROBOT_START -> completed
    assert sm.is_completed("SYS_START")

    sm.jump_to("TARGET_REACHED")
    assert sm.current_node_id == "TARGET_REACHED"

    sm.reset()
    assert sm.current_node_id == "SYS_START"
    assert len(sm.completed_nodes) == 0


def test_mission_new_cycle_clears_completed_highlights():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    # 跳转到末尾节点 MISSION_COMPLETE
    sm.jump_to("MISSION_COMPLETE")
    sm.completed_nodes.add("ROBOT_PLACING")
    assert len(sm.completed_nodes) > 0

    # 从 MISSION_COMPLETE 推进进入新循环 -> 回到检测目标位置 VISION_CHECK_1，高亮应全部清空且无需重置机械臂
    next_node = sm.advance()
    assert next_node.node_id == "VISION_CHECK_1"
    assert len(sm.completed_nodes) == 0
    assert not sm.is_completed("MISSION_COMPLETE")
    assert not sm.is_completed("ROBOT_PLACING")


def test_mission_jump_backward_clears_subsequent_highlights():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    sm.jump_to("OPERATOR_PLACE_TASK")
    sm.completed_nodes.update(["SYS_START", "ROBOT_START", "TARGET_SELECT_PICK", "OPERATOR_PICK_CMD"])
    
    # 模拟跳回到前面的 TARGET_SELECT_PICK，其后续节点的完成高亮应当被清除
    sm.jump_to("TARGET_SELECT_PICK")
    assert sm.current_node_id == "TARGET_SELECT_PICK"
    assert not sm.is_completed("TARGET_SELECT_PICK")
    assert not sm.is_completed("OPERATOR_PICK_CMD")
    assert sm.is_completed("SYS_START")
    assert sm.is_completed("ROBOT_START")


def test_advance_if_hint_matches_and_advances():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    # ROBOT_START 的 command_hint 是 reset
    sm.jump_to("ROBOT_START")
    assert sm.advance_if_hint("reset") is True
    assert sm.current_node_id == "VISION_CHECK_1"


def test_advance_if_hint_no_match_keeps_node():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    sm.jump_to("COARSE_MAP_SELECT")  # hint = move_to
    # 不匹配的指令不推进
    assert sm.advance_if_hint("pick") is False
    assert sm.current_node_id == "COARSE_MAP_SELECT"
    # emergency_stop / cancel_task 无对应 hint，自然跳过
    assert sm.advance_if_hint("emergency_stop") is False
    assert sm.advance_if_hint("cancel_task") is False
    assert sm.current_node_id == "COARSE_MAP_SELECT"
    # 匹配则推进到 COARSE_MOVING
    assert sm.advance_if_hint("move_to") is True
    assert sm.current_node_id == "COARSE_MOVING"


def test_advance_if_hint_on_node_without_hint():
    store = SystemStateStore()
    sm = MissionStateMachine(store)

    # ROBOT 等待节点无 command_hint，发布即推进不应命中
    sm.jump_to("COARSE_MOVING")
    assert sm.advance_if_hint("move_to") is False
    assert sm.current_node_id == "COARSE_MOVING"


def test_robot_wait_nodes_membership():
    # 完成即推进集合应恰好是 5 个 ROBOT 等待节点
    assert ROBOT_WAIT_NODES == {
        "COARSE_MOVING",
        "TARGET_REACHED",
        "ROBOT_PICKING",
        "REACH_DESTINATION",
        "ROBOT_PLACING",
    }
    # OPERATOR 命令节点不在其中（它们靠“发布即推进”）
    assert "ROBOT_START" not in ROBOT_WAIT_NODES
    assert "COARSE_MAP_SELECT" not in ROBOT_WAIT_NODES
    assert "OPERATOR_PICK_CMD" not in ROBOT_WAIT_NODES
