from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class WorkflowNode:
    node_id: str
    index: int
    title: str
    category: str  # "START", "ACTION", "DECISION", "ROBOT", "OPERATOR", "COMPLETE"
    description: str
    command_hint: Optional[str] = None  # 对应的底层指令名，如 "move_to", "pick" 等
    next_node_id: Optional[str] = None
    alt_node_id: Optional[str] = None  # 分支时备选节点（如“否”）


WORKFLOW_NODES: List[WorkflowNode] = [
    WorkflowNode(
        node_id="SYS_START",
        index=1,
        title="流程开始",
        category="START",
        description="任务初始化与系统自检",
        next_node_id="ROBOT_START",
    ),
    WorkflowNode(
        node_id="ROBOT_START",
        index=2,
        title="启动机械臂",
        category="OPERATOR",
        description="操作员在 UI 上点击启动机械臂（复位至工作零点）",
        command_hint="reset",
        next_node_id="VISION_CHECK_1",
    ),
    WorkflowNode(
        node_id="VISION_CHECK_1",
        index=3,
        title="检测视野目标",
        category="DECISION",
        description="相机视野中是否有目标物体？是则直接点选，否则通过地图粗定位",
        next_node_id="TARGET_SELECT_PICK",  # 是
        alt_node_id="COARSE_MAP_SELECT",   # 否
    ),
    WorkflowNode(
        node_id="COARSE_MAP_SELECT",
        index=4,
        title="地图点选粗定位",
        category="OPERATOR",
        description="操作员在 UI 界面的俯视 map 中点选大致位置，并发布任务命令",
        command_hint="move_to",
        next_node_id="COARSE_MOVING",
    ),
    WorkflowNode(
        node_id="COARSE_MOVING",
        index=5,
        title="移动到大致位置",
        category="ROBOT",
        description="机械臂移动到大致位置",
        next_node_id="VISION_CHECK_2",
    ),
    WorkflowNode(
        node_id="VISION_CHECK_2",
        index=6,
        title="二次检测视野目标",
        category="DECISION",
        description="到达大致位置后，相机视野中是否有目标物体？",
        next_node_id="TARGET_SELECT_PICK",  # 是
        alt_node_id="ROBOT_START",          # 否，重新回到初始状态搜索
    ),
    WorkflowNode(
        node_id="TARGET_SELECT_PICK",
        index=7,
        title="相机点选接近目标",
        category="OPERATOR",
        description="操作员在 UI 相机画面中点选目标物体，并发布视觉伺服接近任务命令",
        command_hint="move_for_pick",
        next_node_id="TARGET_REACHED",
    ),
    WorkflowNode(
        node_id="TARGET_REACHED",
        index=8,
        title="到达目标位置",
        category="ROBOT",
        description="机械臂完成视觉伺服对齐，到达目标抓取预备点",
        next_node_id="OPERATOR_PICK_CMD",
    ),
    WorkflowNode(
        node_id="OPERATOR_PICK_CMD",
        index=9,
        title="下达抓取命令",
        category="OPERATOR",
        description="操作员在 UI 界面下达抓取命令",
        command_hint="pick",
        next_node_id="ROBOT_PICKING",
    ),
    WorkflowNode(
        node_id="ROBOT_PICKING",
        index=10,
        title="机械臂抓取物体",
        category="ROBOT",
        description="机械臂执行夹爪闭合与力控卡扣锁紧动作链",
        next_node_id="PICK_CHECK",
    ),
    WorkflowNode(
        node_id="PICK_CHECK",
        index=11,
        title="判断抓取成功",
        category="DECISION",
        description="根据接触传感与力矩反馈判断是否抓取成功？",
        next_node_id="OPERATOR_PLACE_TASK",  # 是
        alt_node_id="OPERATOR_PICK_CMD",     # 否，返回重新抓取
    ),
    WorkflowNode(
        node_id="OPERATOR_PLACE_TASK",
        index=12,
        title="发布终点任务命令",
        category="OPERATOR",
        description="操作员在 UI 界面发布放置到终点任务命令",
        command_hint="move_for_place",
        next_node_id="REACH_DESTINATION",
    ),
    WorkflowNode(
        node_id="REACH_DESTINATION",
        index=13,
        title="携物到达终点",
        category="ROBOT",
        description="机械臂抓取着物体到达终点工位",
        next_node_id="OPERATOR_PLACE_CMD",
    ),
    WorkflowNode(
        node_id="OPERATOR_PLACE_CMD",
        index=14,
        title="下达放置命令",
        category="OPERATOR",
        description="操作员在 UI 界面下达放置命令",
        command_hint="place",
        next_node_id="ROBOT_PLACING",
    ),
    WorkflowNode(
        node_id="ROBOT_PLACING",
        index=15,
        title="机械臂放置物体",
        category="ROBOT",
        description="机械臂解锁夹爪并释放物体脱钩",
        next_node_id="MISSION_COMPLETE",
    ),
    WorkflowNode(
        node_id="MISSION_COMPLETE",
        index=16,
        title="任务完成进入新循环",
        category="COMPLETE",
        description="任务完成，记录归档并进入下一个物体循环",
        next_node_id="SYS_START",
    ),
]

NODE_MAP = {node.node_id: node for node in WORKFLOW_NODES}
