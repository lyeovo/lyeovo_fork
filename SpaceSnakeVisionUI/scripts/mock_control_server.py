#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mock 控制端服务脚本 (模拟 MATLAB runTaskLoop.m 行为)
集成 2D 平面蛇形臂逆运动学 (IK) 求解器，支持根据 UI 下发的目标坐标实时解算各关节角度！

工作机制：
1. 监听 data/outbox/*.json 任务文件；
2. 依据指令类型与坐标参数 (x, y) 求解真实关节角；
3. 向 data/inbox/{command_id}_status.json 回写实时关节角与工况 (中间状态与完成状态平滑插值)；
4. 将处理完成的文件重命名为 .done，与 MATLAB runTaskLoop 保持完全一致。
"""

import json
import math
import time
from pathlib import Path


def solve_2d_ik(target_x: float, target_y: float, n_seg: int = 6, seg_len: float = 1.04393, max_iter: int = 60) -> list[float]:
    """2D 平面蛇形臂 CCD 逆运动学求解器
    基座在 (0, 0)，对齐 MATLAB planarFK_L 零位 (+X 轴延伸)
    返回 6 个关节的相对角度 (单位：度)
    """
    q = [0.0] * n_seg
    init_phi = math.atan2(target_y, target_x)
    q[0] = init_phi
    dist = math.hypot(target_x, target_y)
    max_reach = n_seg * seg_len * 0.98
    if dist > max_reach:
        target_x *= (max_reach / dist)
        target_y *= (max_reach / dist)

    for _ in range(max_iter):
        for i in reversed(range(n_seg)):
            cur_x, cur_y, accum = 0.0, 0.0, 0.0
            for j in range(i):
                accum += q[j]
                cur_x += seg_len * math.cos(accum)
                cur_y += seg_len * math.sin(accum)
            ee_x, ee_y, ee_accum = cur_x, cur_y, accum
            for j in range(i, n_seg):
                ee_accum += q[j]
                ee_x += seg_len * math.cos(ee_accum)
                ee_y += seg_len * math.sin(ee_accum)

            d_ee = math.atan2(ee_y - cur_y, ee_x - cur_x)
            d_tg = math.atan2(target_y - cur_y, target_x - cur_x)
            delta = (d_tg - d_ee + math.pi) % (2 * math.pi) - math.pi
            q[i] += max(-0.4, min(0.4, delta))
            q[i] = max(-math.radians(110), min(math.radians(110), q[i]))

    return [round(math.degrees(a), 2) for a in q]


def compute_ee_fk(angles_deg: list[float], seg_len: float = 1.04393) -> tuple[float, float, float]:
    """根据关节角计算末端 (x, y, yaw_deg)"""
    x, y, accum = 0.0, 0.0, 0.0
    for a in angles_deg:
        accum += math.radians(a)
        x += seg_len * math.cos(accum)
        y += seg_len * math.sin(accum)
    return round(x, 3), round(y, 3), round(math.degrees(accum), 1)


def main():
    project_root = Path(__file__).resolve().parents[1]
    outbox = project_root / "data" / "outbox"
    inbox = project_root / "data" / "inbox"
    outbox.mkdir(parents=True, exist_ok=True)
    inbox.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("🤖 空间蛇形臂模拟控制端 (Mock Control Server + 真实 2D IK) 已启动")
    print(f"📁 监听目录 (outbox): {outbox}")
    print(f"📁 回写目录 (inbox) : {inbox}")
    print("⏳ 等待 UI 端下发指令中... (按 Ctrl+C 退出)")
    print("=" * 65)

    current_angles = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    while True:
        cmd_files = sorted(outbox.glob("CMD-*.json"), key=lambda f: f.stat().st_mtime)
        for fn in cmd_files:
            try:
                raw = fn.read_text(encoding="utf-8")
                cmd = json.loads(raw)
            except Exception as e:
                print(f"[ERROR] 读取解析失败 {fn.name}: {e}")
                continue

            cid = cmd.get("command_id", "CMD-UNKNOWN")
            ctype = cmd.get("command_type", "unknown")
            params = cmd.get("params", {}) or {}
            print(f"\n[RECEIVED] 收到指令: {cid} | 类型: {ctype}")

            # 依据指令类型求解目标关节角
            if ctype == "move_to":
                tx = float(params.get("x", 1.5))
                ty = float(params.get("y", 2.5))
                target_angles = solve_2d_ik(tx, ty)
                print(f"  └─> [IK 计算] 目标 ({tx:.3f}, {ty:.3f}) => 关节角: {target_angles}")
            elif ctype == "move_for_pick":
                st = cmd.get("selected_target") or {}
                pos = (st.get("pose_camera") or {}).get("position") or {}
                tx = float(pos.get("x", 1.0))
                ty = float(pos.get("z", 2.8))  # 相机 Z 为深度纵向
                target_angles = solve_2d_ik(tx, ty)
                print(f"  └─> [IK 抓取] 目标 ({tx:.3f}, {ty:.3f}) => 关节角: {target_angles}")
            elif ctype == "move_for_place":
                # 放置区中心 (4.0, 2.0)
                target_angles = solve_2d_ik(4.0, 2.0)
                print(f"  └─> [IK 放置] 放置区 (4.0, 2.0) => 关节角: {target_angles}")
            elif ctype == "reset":
                target_angles = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                print(f"  └─> [RESET] 机械臂复位至初始构型")
            else:
                target_angles = list(current_angles)

            gripper_val = 2 if "pick" in ctype or "grasp" in ctype else (1 if "place" in ctype or "drop" in ctype else 0)

            status_file = inbox / f"{cid}_status.json"

            # 阶段 1: 正在执行 (EXECUTING，中间插值角度)
            mid_angles = [round((c + t) / 2.0, 2) for c, t in zip(current_angles, target_angles)]
            ee_x, ee_y, ee_yaw = compute_ee_fk(mid_angles)
            status_executing = {
                "schema_version": "2.0",
                "command_id": cid,
                "timestamp": time.time(),
                "status": "EXECUTING",
                "current_step": ctype,
                "progress": 0.50,
                "message": f"机械臂正在执行 {ctype} 轨迹规划与运动控制...",
                "robot_state": {
                    "state": "EXECUTING",
                    "joint_positions": mid_angles,
                    "joint_positions_unit": "deg",
                    "gripper": gripper_val,
                    "end_effector_pose_base": {
                        "position": {"x": ee_x, "y": ee_y, "z": 0.0},
                        "orientation_euler": {"roll": 0.0, "pitch": 0.0, "yaw": ee_yaw},
                    },
                },
                "planner": {
                    "method_used": "CCD_Inverse_Kinematics",
                    "solve_time_ms": 1.2,
                    "tracking_error_mm": 0.5,
                    "angle_error_deg": 0.05,
                },
            }
            status_file.write_text(json.dumps(status_executing, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  └─> [STATUS: EXECUTING] 已写回中间状态 (进度 50%)")
            time.sleep(1.0)

            # 阶段 2: 执行完成 (COMPLETED，到达目标角度)
            current_angles = list(target_angles)
            ee_x, ee_y, ee_yaw = compute_ee_fk(current_angles)
            status_completed = {
                "schema_version": "2.0",
                "command_id": cid,
                "timestamp": time.time(),
                "status": "COMPLETED",
                "current_step": ctype,
                "progress": 1.00,
                "message": f"指令 {ctype} 动作执行完成",
                "robot_state": {
                    "state": "IDLE",
                    "joint_positions": current_angles,
                    "joint_positions_unit": "deg",
                    "gripper": gripper_val,
                    "end_effector_pose_base": {
                        "position": {"x": ee_x, "y": ee_y, "z": 0.0},
                        "orientation_euler": {"roll": 0.0, "pitch": 0.0, "yaw": ee_yaw},
                    },
                },
                "planner": {
                    "method_used": "CCD_Inverse_Kinematics",
                    "solve_time_ms": 1.5,
                    "tracking_error_mm": 0.1,
                    "angle_error_deg": 0.01,
                },
            }
            status_file.write_text(json.dumps(status_completed, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  └─> [STATUS: COMPLETED] 末端已达 ({ee_x:.3f}, {ee_y:.3f})，执行完成！")

            # 将 outbox 文件更名为 .done
            done_fn = fn.with_suffix(".json.done")
            fn.rename(done_fn)

        time.sleep(0.2)


if __name__ == "__main__":
    main()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
