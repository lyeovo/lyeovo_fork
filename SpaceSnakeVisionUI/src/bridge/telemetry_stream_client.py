"""实时遥测 TCP 状态流（预留）——契约已冻结，接收端待实现。

线上帧格式（对齐控制端 tcpEncodeFrame.m / tcpStateStreamServer.m）::

    [4 字节大端无符号长度 N][N 字节 JSON 体]

JSON 体::

    {"v": 1, "type": "STATE", "seq": 123, "command_id": "", "data": {...}}

消息类型 (type): HELLO / HELLO_ACK / CMD / CMD_ACK / STATE / DONE / PING / PONG / ERROR

STATE.data 字段::

    t          float   时间戳（秒）
    joints     list[6] 关节绝对角（弧度 rad）
    gripper    int     0=HOLD, 1=OPEN, 2=CLOSE
    obj        [x, y]  目标平面坐标
    obj_frame  str     'base' | 'cam'
    obj_absent bool    目标是否丢失

现役遥测通道为文件桥 TaskStatus（见 docs/TASK_COMMAND_INTERFACE.md 第三节）；
本模块的 socket 传输层尚未接线到主窗口，仅解帧逻辑可用且已被单测覆盖。
"""

from __future__ import annotations

import json
import struct
from typing import Any, Callable, Dict, List, Optional, Tuple

HEADER_LEN = 4
_HEADER_FMT = ">I"  # 4 字节大端无符号
MAX_FRAME_BYTES = 1 << 20  # 1 MiB 单帧上限，防御损坏的长度前缀

MSG_HELLO = "HELLO"
MSG_HELLO_ACK = "HELLO_ACK"
MSG_CMD = "CMD"
MSG_CMD_ACK = "CMD_ACK"
MSG_STATE = "STATE"
MSG_DONE = "DONE"
MSG_PING = "PING"
MSG_PONG = "PONG"
MSG_ERROR = "ERROR"


def encode_frame(payload: Dict[str, Any]) -> bytes:
    """将消息体编码为线上帧（长度前缀 + UTF-8 JSON）。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return struct.pack(_HEADER_FMT, len(body)) + body


def decode_state_frame(buf: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
    """从字节缓冲区解出一帧。

    返回 ``(frame, remaining)``：
      - 半包（字节不足）时返回 ``(None, buf)``，调用方应缓存 buf 等待更多字节；
      - 成功时返回解析出的消息体 dict 与去掉该帧后的剩余字节（支持粘包）。

    长度前缀损坏（超过 ``MAX_FRAME_BYTES``）或 JSON 非法时抛 ``ValueError``，
    调用方据此重置缓冲/断开重连。
    """
    if len(buf) < HEADER_LEN:
        return None, buf

    (body_len,) = struct.unpack(_HEADER_FMT, buf[:HEADER_LEN])
    if body_len > MAX_FRAME_BYTES:
        raise ValueError(f"frame body length {body_len} exceeds cap {MAX_FRAME_BYTES}")

    end = HEADER_LEN + body_len
    if len(buf) < end:
        return None, buf  # 半包：等待更多字节

    body = buf[HEADER_LEN:end]
    remaining = buf[end:]
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid frame body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("frame body must be a JSON object")
    return parsed, remaining


class TelemetryStreamClient:
    """TCP STATE 流接收端骨架。

    ``feed`` 内的解帧与分发逻辑是完整且可单测的；``start`` 的 socket
    连接与接收循环尚未实现（契约已冻结，待接线）。
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5005,
        on_state: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self._on_state = on_state
        self._running = False
        self._buf = b""

    def start(self) -> None:
        raise NotImplementedError(
            "TCP STATE 流接收端待实现（契约已冻结，见 docs/TASK_COMMAND_INTERFACE.md 第四节）"
        )

    def stop(self) -> None:
        self._running = False
        self._buf = b""

    def feed(self, chunk: bytes) -> List[Dict[str, Any]]:
        """喂入收到的字节，返回本次解出的完整帧列表。

        每解出一个 STATE 帧即通过 ``on_state`` 回调派发其 ``data``。
        未来的 socket 接收循环只需把 recv 到的字节交给本方法。
        """
        self._buf += chunk
        frames: List[Dict[str, Any]] = []
        while True:
            frame, self._buf = decode_state_frame(self._buf)
            if frame is None:
                break
            frames.append(frame)
            if frame.get("type") == MSG_STATE:
                self.on_state(frame.get("data") or {})
        return frames

    def on_state(self, data: Dict[str, Any]) -> None:
        if self._on_state is not None:
            self._on_state(data)
