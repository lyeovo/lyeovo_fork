import struct

import pytest

from src.bridge.telemetry_stream_client import (
    HEADER_LEN,
    MAX_FRAME_BYTES,
    TelemetryStreamClient,
    decode_state_frame,
    encode_frame,
)


def _state_frame(seq=1, joints=None):
    return {
        "v": 1,
        "type": "STATE",
        "seq": seq,
        "command_id": "",
        "data": {
            "t": 0.1 * seq,
            "joints": joints if joints is not None else [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "gripper": 1,
            "obj": [0.35, -0.12],
            "obj_frame": "base",
            "obj_absent": False,
        },
    }


def test_encode_decode_single_frame():
    payload = _state_frame()
    buf = encode_frame(payload)
    (n,) = struct.unpack(">I", buf[:HEADER_LEN])
    assert n == len(buf) - HEADER_LEN
    frame, remaining = decode_state_frame(buf)
    assert frame == payload
    assert remaining == b""


def test_decode_half_packet_waits():
    buf = encode_frame(_state_frame())
    # 不足 4 字节长度前缀
    frame, rem = decode_state_frame(buf[:3])
    assert frame is None
    assert rem == buf[:3]
    # 前缀够但体不全
    frame, rem = decode_state_frame(buf[: HEADER_LEN + 2])
    assert frame is None
    assert rem == buf[: HEADER_LEN + 2]


def test_decode_sticky_packets():
    f1 = encode_frame(_state_frame(seq=1))
    f2 = encode_frame({"v": 1, "type": "DONE", "seq": 2, "command_id": "X", "data": {}})
    buf = f1 + f2

    frame1, buf = decode_state_frame(buf)
    assert frame1["type"] == "STATE"
    assert frame1["seq"] == 1

    frame2, buf = decode_state_frame(buf)
    assert frame2["type"] == "DONE"

    frame3, buf = decode_state_frame(buf)
    assert frame3 is None
    assert buf == b""


def test_client_feed_dispatches_state_and_handles_partial():
    got = []
    client = TelemetryStreamClient(on_state=lambda d: got.append(d))
    full = encode_frame(_state_frame(seq=7))

    # 分两次喂入（模拟半包）：第一次不足以解出任何帧
    assert client.feed(full[:5]) == []
    assert got == []

    frames = client.feed(full[5:])
    assert len(frames) == 1
    assert frames[0]["seq"] == 7
    assert len(got) == 1
    assert got[0]["gripper"] == 1

    # 非 STATE 帧不触发 on_state 回调
    done = encode_frame({"v": 1, "type": "DONE", "seq": 8, "command_id": "", "data": {}})
    frames = client.feed(done)
    assert len(frames) == 1
    assert frames[0]["type"] == "DONE"
    assert len(got) == 1


def test_decode_rejects_oversized_length():
    bad = struct.pack(">I", MAX_FRAME_BYTES + 1) + b"{}"
    with pytest.raises(ValueError):
        decode_state_frame(bad)


def test_decode_rejects_invalid_json_body():
    body = b"{not json"
    bad = struct.pack(">I", len(body)) + body
    with pytest.raises(ValueError):
        decode_state_frame(bad)
