from __future__ import annotations

from typing import List, Optional, Set
from PySide6.QtCore import QObject, Signal

from .workflow_definition import NODE_MAP, WORKFLOW_NODES, WorkflowNode
from ..state.system_state import SystemStateStore


# 等待物理完成的 ROBOT 节点：活跃命令回 COMPLETED 时应自动推进（完成即推进）
ROBOT_WAIT_NODES = {node.node_id for node in WORKFLOW_NODES if node.category == "ROBOT"}


class MissionState:
    SYS_START = "SYS_START"
    ROBOT_START = "ROBOT_START"
    VISION_CHECK_1 = "VISION_CHECK_1"
    COARSE_MAP_SELECT = "COARSE_MAP_SELECT"
    COARSE_MOVING = "COARSE_MOVING"
    VISION_CHECK_2 = "VISION_CHECK_2"
    TARGET_SELECT_PICK = "TARGET_SELECT_PICK"
    TARGET_REACHED = "TARGET_REACHED"
    OPERATOR_PICK_CMD = "OPERATOR_PICK_CMD"
    ROBOT_PICKING = "ROBOT_PICKING"
    PICK_CHECK = "PICK_CHECK"
    OPERATOR_PLACE_TASK = "OPERATOR_PLACE_TASK"
    REACH_DESTINATION = "REACH_DESTINATION"
    OPERATOR_PLACE_CMD = "OPERATOR_PLACE_CMD"
    ROBOT_PLACING = "ROBOT_PLACING"
    MISSION_COMPLETE = "MISSION_COMPLETE"


class MissionStateMachine(QObject):
    """基于流程图拓扑的任务级状态机"""

    nodeChanged = Signal(str)  # 发射当前 node_id

    def __init__(self, store: Optional[SystemStateStore] = None) -> None:
        super().__init__()
        self.store = store or SystemStateStore.instance()
        self.current_node_id: str = "SYS_START"
        self.completed_nodes: Set[str] = set()
        self._sync_to_store()

    @property
    def current_node(self) -> WorkflowNode:
        return NODE_MAP.get(self.current_node_id, WORKFLOW_NODES[0])

    def advance(self, decision_choice: bool = True) -> WorkflowNode:
        """向下一个节点推进"""
        cur = self.current_node
        self.completed_nodes.add(cur.node_id)

        target_id: Optional[str] = None
        if cur.category == "DECISION":
            target_id = cur.next_node_id if decision_choice else cur.alt_node_id
        else:
            target_id = cur.next_node_id

        if not target_id:
            target_id = "SYS_START"

        self.current_node_id = target_id
        self._sync_to_store()
        self.nodeChanged.emit(self.current_node_id)
        return self.current_node

    def advance_if_hint(self, command_type: str) -> bool:
        """发布即推进：发布的命令与当前节点的 command_hint 匹配时推进。

        覆盖 reset/move_to/move_for_pick/pick/move_for_place/place；
        emergency_stop/cancel_task 无对应 hint，自然跳过。
        """
        cur = self.current_node
        if cur.command_hint and cur.command_hint == command_type:
            self.advance()
            return True
        return False

    def jump_to(self, node_id: str) -> bool:
        """跳转到特定节点"""
        if node_id not in NODE_MAP:
            return False
        self.current_node_id = node_id
        self._sync_to_store()
        self.nodeChanged.emit(self.current_node_id)
        return True

    def reset(self) -> None:
        """重置任务流程"""
        self.completed_nodes.clear()
        self.current_node_id = "SYS_START"
        self._sync_to_store()
        self.nodeChanged.emit(self.current_node_id)

    def is_completed(self, node_id: str) -> bool:
        return node_id in self.completed_nodes

    def _sync_to_store(self) -> None:
        cur = self.current_node
        self.store.update_mission(
            state=cur.node_id,
            step_index=cur.index,
            status_text=cur.description,
        )
