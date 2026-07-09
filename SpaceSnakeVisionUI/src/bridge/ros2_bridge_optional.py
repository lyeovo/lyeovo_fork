from __future__ import annotations

import threading
from collections import deque

from ..models import TaskCommand, TaskStatus


class ROS2BridgeOptional:
    """Optional ROS2 JSON bridge using std_msgs/String."""

    def __init__(
        self,
        task_command_topic: str = "/space_snake/task_command",
        task_status_topic: str = "/space_snake/task_status",
    ) -> None:
        try:
            import rclpy
            from rclpy.node import Node
            from std_msgs.msg import String
        except Exception as exc:
            raise RuntimeError(f"ROS2/rclpy is not available: {exc}") from exc

        self.rclpy = rclpy
        self.String = String
        self.task_command_topic = task_command_topic
        self.task_status_topic = task_status_topic
        self._statuses: deque[TaskStatus] = deque()

        if not rclpy.ok():
            rclpy.init(args=None)

        class _BridgeNode(Node):
            pass

        self.node = _BridgeNode("space_snake_vision_ui_bridge")
        self.publisher = self.node.create_publisher(String, task_command_topic, 10)
        self.node.create_subscription(String, task_status_topic, self._on_status_message, 10)
        self._spin_thread = threading.Thread(target=rclpy.spin, args=(self.node,), daemon=True)
        self._spin_thread.start()

    def publish_command(self, command: TaskCommand) -> str:
        msg = self.String()
        msg.data = command.to_json()
        self.publisher.publish(msg)
        return f"ros2:{self.task_command_topic}"

    def poll_status(self) -> list[TaskStatus]:
        statuses = list(self._statuses)
        self._statuses.clear()
        return statuses

    def _on_status_message(self, msg) -> None:
        try:
            self._statuses.append(TaskStatus.from_json(msg.data))
        except Exception as exc:
            self.node.get_logger().warning(f"Invalid TaskStatus JSON: {exc}")

    def close(self) -> None:
        try:
            self.node.destroy_node()
        finally:
            if self.rclpy.ok():
                self.rclpy.shutdown()
