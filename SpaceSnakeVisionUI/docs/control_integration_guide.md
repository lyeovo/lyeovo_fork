# Control Integration Guide

## File Bridge

1. 控制模块监听 `data/outbox/*.json`。
2. 解析 `TaskCommand.command_type`、`selected_target.pose_camera`、`selected_target.pose_base` 和 `destination.pose_base`。
3. 如果 `pose_base == null`，真实机械臂执行应拒绝或只进入仿真。
4. 控制模块写回 `data/inbox/{command_id}_status.json`。

## Mock Server

```bash
python -m src.bridge.mock_control_server --mode file
```

Mock 状态序列：

```text
RECEIVED -> ACCEPTED -> PLANNING -> EXECUTING -> COMPLETED
```
