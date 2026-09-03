from __future__ import annotations

import math
from typing import Dict, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...mission.state_machine import MissionStateMachine
from ...mission.workflow_definition import NODE_MAP, WORKFLOW_NODES, WorkflowNode


class WorkflowWidget(QWidget):
    """基于流程图 SVG 拓扑的程序化动态流程图组件"""

    nodeClicked = Signal(str)  # 点击节点发射 node_id

    def __init__(self, state_machine: Optional[MissionStateMachine] = None) -> None:
        super().__init__()
        self.sm = state_machine or MissionStateMachine()
        self.sm.nodeChanged.connect(self._on_node_changed)

        self.setMinimumSize(420, 520)
        self.setMouseTracking(True)

        # 呼吸发光动画参数
        self._glow_phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_glow)
        self._timer.start(33)  # ~30 FPS

        self._hovered_node_id: Optional[str] = None

    def _update_glow(self) -> None:
        self._glow_phase = (self._glow_phase + 0.08) % (math.pi * 2)
        self.update()

    def _on_node_changed(self, node_id: str) -> None:
        self.update()

    def set_state_machine(self, sm: MissionStateMachine) -> None:
        self.sm = sm
        self.sm.nodeChanged.connect(self._on_node_changed)
        self.update()

    def _get_node_rects(self) -> Dict[str, QRectF]:
        """按原 SVG 的三列拓扑排列节点位置"""
        w = max(400, self.width())
        h = max(500, self.height())

        col_w = (w - 40) / 3.0
        c1_x = 20
        c2_x = 20 + col_w + 10
        c3_x = 20 + (col_w + 10) * 2

        node_h = 36
        gap_y = 12

        rects: Dict[str, QRectF] = {}

        # Column 1: 粗定位分支 (X: c1_x)
        y = 20
        rects["SYS_START"] = QRectF(c1_x, y, col_w, node_h); y += node_h + gap_y
        rects["ROBOT_START"] = QRectF(c1_x, y, col_w, node_h); y += node_h + gap_y
        rects["VISION_CHECK_1"] = QRectF(c1_x, y, col_w, node_h); y += node_h + gap_y
        rects["COARSE_MAP_SELECT"] = QRectF(c1_x, y, col_w, node_h); y += node_h + gap_y
        rects["COARSE_MOVING"] = QRectF(c1_x, y, col_w, node_h); y += node_h + gap_y
        rects["VISION_CHECK_2"] = QRectF(c1_x, y, col_w, node_h)

        # Column 2: 目标伺服与抓取分支 (X: c2_x)
        y = 20 + (node_h + gap_y) * 2  # 从第 3 行对齐
        rects["TARGET_SELECT_PICK"] = QRectF(c2_x, y, col_w, node_h); y += node_h + gap_y
        rects["TARGET_REACHED"] = QRectF(c2_x, y, col_w, node_h); y += node_h + gap_y
        rects["OPERATOR_PICK_CMD"] = QRectF(c2_x, y, col_w, node_h); y += node_h + gap_y
        rects["ROBOT_PICKING"] = QRectF(c2_x, y, col_w, node_h); y += node_h + gap_y
        rects["PICK_CHECK"] = QRectF(c2_x, y, col_w, node_h)

        # Column 3: 终点放置分支 (X: c3_x)
        y = 20 + (node_h + gap_y) * 2  # 从第 3 行对齐
        rects["OPERATOR_PLACE_TASK"] = QRectF(c3_x, y, col_w, node_h); y += node_h + gap_y
        rects["REACH_DESTINATION"] = QRectF(c3_x, y, col_w, node_h); y += node_h + gap_y
        rects["OPERATOR_PLACE_CMD"] = QRectF(c3_x, y, col_w, node_h); y += node_h + gap_y
        rects["ROBOT_PLACING"] = QRectF(c3_x, y, col_w, node_h); y += node_h + gap_y
        rects["MISSION_COMPLETE"] = QRectF(c3_x, y, col_w, node_h)

        return rects

    def mouseMoveEvent(self, event) -> None:
        pos = event.position() if hasattr(event, "position") else event.pos()
        rects = self._get_node_rects()
        new_hover = None
        for nid, r in rects.items():
            if r.contains(pos):
                new_hover = nid
                break
        if new_hover != self._hovered_node_id:
            self._hovered_node_id = new_hover
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            pos = event.position() if hasattr(event, "position") else event.pos()
            rects = self._get_node_rects()
            for nid, r in rects.items():
                if r.contains(pos):
                    self.nodeClicked.emit(nid)
                    break

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#050814"))

        rects = self._get_node_rects()

        # 1. 绘制连线与分支箭头
        self._draw_connections(painter, rects)

        # 2. 绘制节点卡片
        glow_alpha = int(120 + 80 * math.sin(self._glow_phase))
        active_id = self.sm.current_node_id

        for node in WORKFLOW_NODES:
            nid = node.node_id
            if nid not in rects:
                continue
            r = rects[nid]
            is_active = (nid == active_id)
            is_done = self.sm.is_completed(nid)
            is_hover = (nid == self._hovered_node_id)

            # 决定样式背景与边框
            if is_active:
                # 呼吸发光边框
                glow_color = QColor(0, 229, 255, glow_alpha)
                painter.setPen(QPen(glow_color, 4))
                painter.setBrush(QColor("#0F223D"))
                painter.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 6, 6)

                pen = QPen(QColor("#00E5FF"), 2)
                bg = QColor("#0A2A4A")
            elif is_done:
                pen = QPen(QColor("#2EEA8A"), 1)
                bg = QColor("#0D261A")
            elif is_hover:
                pen = QPen(QColor("#4070A0"), 1)
                bg = QColor("#121A30")
            else:
                pen = QPen(QColor("#1A2B4C"), 1)
                bg = QColor("#0A1020")

            painter.setPen(pen)
            painter.setBrush(bg)
            painter.drawRoundedRect(r, 5, 5)

            # 绘制节点标题与状态标记
            title_color = QColor("#00E5FF") if is_active else (QColor("#2EEA8A") if is_done else QColor("#D0DDF0"))
            painter.setPen(title_color)

            font = QFont("Microsoft YaHei", 9)
            font.setBold(is_active)
            painter.setFont(font)

            # 节点前置角标
            if is_active:
                tag = "▶ "
            elif is_done:
                tag = "✓ "
            else:
                tag = f"{node.index:02d} "

            text = f"{tag}{node.title}"
            painter.drawText(r.adjusted(8, 2, -8, -2), Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.end()

    def _draw_connections(self, painter: QPainter, rects: Dict[str, QRectF]) -> None:
        """绘制节点间的流动线"""
        line_pen = QPen(QColor("#1B335A"), 1, Qt.DashLine)
        active_pen = QPen(QColor("#00E5FF"), 1)

        # 遍历节点流向
        for node in WORKFLOW_NODES:
            r1 = rects.get(node.node_id)
            if not r1:
                continue

            # 主分支
            if node.next_node_id and node.next_node_id in rects:
                r2 = rects[node.next_node_id]
                painter.setPen(active_pen if (node.node_id == self.sm.current_node_id) else line_pen)
                # 简单连接中心
                p1 = QPointF(r1.center().x(), r1.bottom())
                p2 = QPointF(r2.center().x(), r2.top())
                painter.drawLine(p1, p2)

            # 备选分支（若有）
            if node.alt_node_id and node.alt_node_id in rects:
                r_alt = rects[node.alt_node_id]
                painter.setPen(line_pen)
                p1 = QPointF(r1.right(), r1.center().y())
                p2 = QPointF(r_alt.left(), r_alt.center().y())
                painter.drawLine(p1, p2)
