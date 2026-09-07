"""链路控制台页面：手动启动/停止整条真实链的各模块，带参数框与实时日志调试。

模块：
  ② 运动控制/算法 (MATLAB runTaskLoop)      —— QProcess 启动
  ③ 电控 mock (TCP 服务器, mock_elec_server.py) —— QProcess 启动（保留 TCP 服务器创建）
  ③′ 真机 dSPACE/Interpreter                —— 占位连接状态
  ① 视觉/任务调度 (GUI 本体)                  —— 只读显示

参数只保留"能拉起+接线+输出节奏"的关键项；算法微调留在 ArmSimApp 侧。
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from ...state.system_state import SystemStateStore


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


class ChainPage(QWidget):
    """Page 5: 链路控制台 —— 手动启动/调试整条链。"""

    ALGO = {"auto": "auto", "momentum": "momentum", "sa": "sa", "rrt": "rrt",
            "rrtstar": "rrtstar", "prm": "prm", "graph": "graph", "rl": "rl", "cvae": "cvae"}

    def __init__(self, log_console: QPlainTextEdit, project_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.log_console = log_console
        self.project_root = Path(project_root)
        self._store = SystemStateStore.instance()
        self._procs: Dict[str, QProcess] = {}
        self._status: Dict[str, QLabel] = {}
        self._manual_stop: set = set()   # 记录手动停止的模块，避免 finished 信号覆盖状态
        self._build_ui()
        self._fs_timer = QTimer(self)
        self._fs_timer.timeout.connect(self._refresh_files)
        self._fs_timer.start(1000)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        # 沿用主题：QLineEdit 深色、组标题青字，提升可读性
        self.setStyleSheet(
            "QLineEdit { background:#07122C; border:1px solid #1E88E5; color:#EAF6FF;"
            "  padding:3px; border-radius:3px; selection-background-color:#123D63; }"
            "QLineEdit:focus { border:1px solid #00E5FF; }"
            "QGroupBox { font-weight:600; }"
            "QGroupBox::title { color:#00E5FF; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        title = QLabel("链路控制台 · 手动启动 / 调试整条真实链")
        title.setObjectName("HeaderTitle")
        outer.addWidget(title)
        hint = QLabel("按模块改参数后点「启动」（subprocess 拉起）；「注入」写一条任务到 outbox；日志随各模块 stdout/stderr 实时刷新。")
        hint.setObjectName("ActionHintLabel")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # 共通
        common = QGroupBox("共通配置"); common.setObjectName("CardFrame")
        f = QFormLayout(common)
        self.ed_out = self._edit(f, "outbox 目录", str(self.project_root / "data" / "outbox"))
        self.ed_in = self._edit(f, "inbox 目录", str(self.project_root / "data" / "inbox"))
        self.ed_repo = self._edit(f, "MATLAB 仓库路径", "D:\\thuedu\\26夏")
        v.addWidget(common)

        # 模块② 算法
        algo = self._module_group("模块② 运动控制 / 算法（MATLAB runTaskLoop）")
        ag = QGridLayout(); ag.setHorizontalSpacing(10); ag.setVerticalSpacing(6)
        ag.addWidget(QLabel("求解算法"), 0, 0)
        self.cb_method = QComboBox(); self.cb_method.addItems(list(self.ALGO.values()))
        ag.addWidget(self.cb_method, 0, 1)
        self.ed_N = self._grid_field(ag, 0, 2, "关节数 N", "6")
        self.ed_L = self._grid_field(ag, 1, 0, "杆长 L (m)", "1.04393")
        self.ed_snap = self._grid_field(ag, 1, 2, "snapshot_m（每累积步数输出）", "10")
        self.ed_dec = self._grid_field(ag, 2, 0, "抽稀 n（每 n 步下发一组）", "2")
        self.ed_ad = self._grid_field(ag, 2, 2, "approach_dist (m)", "0.15")
        self.ed_tx = self._grid_field(ag, 3, 0, "测试目标 x", "1.2")
        self.ed_ty = self._grid_field(ag, 3, 2, "测试目标 y", "0.8")
        self.ed_tth = self._grid_field(ag, 4, 0, "测试目标 θ (rad)", "0")
        self._add_ctrl_row(algo, "algo", ag)
        v.addWidget(algo)

        # 模块③ 电控 mock（保留 TCP 服务器创建）
        elec = self._module_group("模块③ 电控 mock（TCP 服务器）· 保留服务器创建")
        eg = QGridLayout(); eg.setHorizontalSpacing(10); eg.setVerticalSpacing(6)
        self.ed_srv_port = self._grid_field(eg, 0, 0, "服务器端口", "9100")
        self.ed_srv_bind = self._grid_field(eg, 0, 2, "服务器绑定地址", "0.0.0.0")
        self.ed_srv_interval = self._grid_field(eg, 1, 0, "STATE 帧间隔 (s)", "0.05")
        self.ed_srv_script = self._grid_field(eg, 1, 2, "mock_elec_server.py", "D:\\thuedu\\26夏\\mock_elec_server.py")
        self.ed_cli_ip = self._grid_field(eg, 2, 0, "下发连接 IP(服务端实网IP)", "10.55.145.80")
        self.ed_cli_port = self._grid_field(eg, 2, 2, "下发端口", "9100")
        self.ed_step = self._grid_field(eg, 3, 0, "电机步进/圈", "40000")
        self.ed_servo_open = self._grid_field(eg, 3, 2, "舵机开角度 (度)", "90")
        self.ed_servo_close = self._grid_field(eg, 4, 0, "舵机关角度 (度)", "0")
        self.cb_fb = QCheckBox("实时反馈"); self.cb_fb.setChecked(True); eg.addWidget(self.cb_fb, 4, 2)
        self._add_ctrl_row(elec, "elec", eg)
        v.addWidget(elec)

        # 模块③′ 真机 dSPACE
        real = self._module_group("模块③′ 真机 dSPACE / ControlDesk Interpreter（连接占位）")
        rg = QGridLayout(); rg.setHorizontalSpacing(10); rg.setVerticalSpacing(6)
        self.ed_r_ip = self._grid_field(rg, 0, 0, "Interpreter 连接 IP", "192.168.1.20")
        self.ed_r_port = self._grid_field(rg, 0, 2, "Interpreter 端口", "9100")
        self.ed_varroot = self._grid_field(rg, 1, 0, "变量前缀 VAR_ROOT", "Application/SnakeArm_HIL")
        self.ed_proj = self._grid_field(rg, 1, 2, "ControlDesk 工程名", "Project_motiontest0829")
        v.addWidget(real)

        # 状态 / 一键 / 测试
        st = QGroupBox("模块状态 · 一键操作 · 测试"); st.setObjectName("CardFrame")
        stv = QGridLayout(st)
        self.st_algo = QLabel("○ 算法未启动"); self.st_algo.setObjectName("StatusIdle")
        self.st_elec = QLabel("○ 电控未启动"); self.st_elec.setObjectName("StatusIdle")
        self.st_real = QLabel("○ 真机未连接"); self.st_real.setObjectName("StatusIdle")
        for i, lbl in enumerate((self.st_algo, self.st_elec, self.st_real)):
            stv.addWidget(lbl, i, 0)
        b_all = QPushButton("▶ 一键启动整链（电控+算法）")
        b_stop = QPushButton("⏹ 一键停止全部")
        b_inj = QPushButton("▶ 注入测试 TaskCommand 到 outbox")
        b_all.clicked.connect(lambda: (self.start_module("elec"), self.start_module("algo")))
        b_stop.clicked.connect(lambda: (self.stop_module("elec"), self.stop_module("algo")))
        b_inj.clicked.connect(self.inject_command)
        for i, b in enumerate((b_all, b_stop, b_inj)):
            stv.addWidget(b, i, 1)
        v.addWidget(st)

        # 日志（放竖向 QSplitter，可拖拽调大小，不再限高 200）
        self.chain_log = QPlainTextEdit(); self.chain_log.setReadOnly(True)
        self.chain_log.setPlaceholderText("各模块 stdout/stderr 会在这里实时刷新…")
        self.chain_log.setMinimumHeight(180)

        scroll.setWidget(body)
        split = QSplitter(Qt.Vertical)
        split.addWidget(scroll)
        split.addWidget(self.chain_log)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, stretch=1)

    def _edit(self, form: QFormLayout, label: str, default: str) -> QLineEdit:
        e = QLineEdit(default)
        form.addRow(label, e)
        return e

    def _module_group(self, title: str) -> QGroupBox:
        g = QGroupBox(title); g.setObjectName("CardFrame")
        v = QVBoxLayout(g); v.setContentsMargins(8, 8, 8, 8); v.setSpacing(6)
        return g

    def _grid_field(self, grid: QGridLayout, row: int, col: int, label: str, default: str, placeholder: str = "") -> QLineEdit:
        lbl = QLabel(label); grid.addWidget(lbl, row, col)
        e = QLineEdit(default); e.setPlaceholderText(placeholder)
        grid.addWidget(e, row, col + 1)
        return e

    def _add_ctrl_row(self, group: QGroupBox, key: str, grid: QGridLayout) -> None:
        """把参数字段网格 + 启动/停止/状态行 加进模块组。"""
        lay = group.layout()   # QVBoxLayout
        lay.addLayout(grid)
        row = QHBoxLayout()
        btn_on = QPushButton("▶ 启动"); btn_on.setObjectName("BtnYes")
        btn_off = QPushButton("⏹ 停止"); btn_off.setObjectName("BtnNo")
        btn_on.clicked.connect(lambda: self.start_module(key))
        btn_off.clicked.connect(lambda: self.stop_module(key))
        st = QLabel("○ IDLE"); st.setObjectName("StatusIdle")
        self._status[key] = st
        row.addWidget(btn_on); row.addWidget(btn_off); row.addWidget(st, stretch=1)
        lay.addLayout(row)

    # ---------- 模块控制 ----------
    def start_module(self, key: str) -> None:
        if key == "elec":
            self._start_elec()
        elif key == "algo":
            self._start_algo()

    def stop_module(self, key: str) -> None:
        p = self._procs.pop(key, None)
        if p is not None and p.state() != QProcess.NotRunning:
            self._manual_stop.add(key)
            self._kill_proc(p)                  # 强杀进程树，避免子进程残留
            self._log(f"[{key}] 已停止")
            self._set_status(key, "○ STOPPED", "StatusIdle")
        self._sync_store(key, False)

    def _kill_proc(self, proc: QProcess) -> None:
        """强杀进程树（Windows taskkill /F /T），并等待回收。"""
        pid = proc.processId()
        if pid:
            try:
                os.system(f'taskkill /F /T /PID {int(pid)} >NUL 2>&1')   # 杀进程及其所有子进程
            except Exception:
                pass
        try:
            proc.kill()
            proc.waitForFinished(2000)
        except Exception:
            pass

    def _start_elec(self) -> None:
        script = self.ed_srv_script.text().strip()
        port = self.ed_srv_port.text().strip()
        bind = self.ed_srv_bind.text().strip() or '0.0.0.0'   # 0.0.0.0=监听所有网卡(局域网可达)
        # 用 GUI 自己的 python(sys.executable)，确保跑的是当前 mock_elec_server.py 且可靠
        self._start_qprocess("elec", sys.executable, [script, port, bind])
        self._log(f"[elec] 启动 TCP 服务器 {script} :{port} bind={bind}")

    def _start_algo(self) -> None:
        repo = self.ed_repo.text().strip()
        out = self.ed_out.text().strip(); inn = self.ed_in.text().strip()
        m = self.cb_method.currentText(); N = self.ed_N.text().strip(); L = self.ed_L.text().strip()
        snap = self.ed_snap.text().strip(); ad = self.ed_ad.text().strip()
        eip = self.ed_cli_ip.text().strip(); eport = self.ed_cli_port.text().strip()
        opts = (f"'outbox','{out}','inbox','{inn}','method','{m}',"
                f"'snapshot_m',{snap},'approach_dist',{ad},'verbose',true")
        # elec_host 非空=每任务后下发电控 20 参帧(需电控已启动，失败容忍)；空=纯仿真不连电控
        if eip:
            opts += f",'elec_host','{eip}','elec_port',{int(eport)}"
        run = (f"addpath('{repo}'); addpath(fullfile('{repo}','ArmSimulator2D'));"
               f"m=createArmModel(struct('N',{int(N)},'L_seg',{float(L)},"
               f"'obstacles',struct('rects',[],'circles',[])));"
               f"runTaskLoop(m, struct({opts}))")
        self._start_qprocess("algo", "matlab", ["-batch", run])
        self._log(f"[algo] 启动 MATLAB runTaskLoop (method={m}, N={N}, "
                  f"elec={ (f'{eip}:{eport}') if eip else 'off(仿真)' })")

    def _start_qprocess(self, key: str, program: str, args) -> None:
        p = self._procs.pop(key, None)
        if p is not None and p.state() != QProcess.NotRunning:
            p.kill()
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(list(args))
        proc.readyReadStandardOutput.connect(lambda: self._log(f"[{key}][out]\n{proc.readAllStandardOutput().data().decode('utf-8', 'replace')}"))
        proc.readyReadStandardError.connect(lambda: self._log(f"[{key}][err]\n{proc.readAllStandardError().data().decode('utf-8', 'replace')}"))
        proc.started.connect(lambda: self._on_started(key))
        proc.finished.connect(lambda code, st: self._on_finish(key, code, st))
        proc.errorOccurred.connect(lambda e: self._on_error(key, e))
        self._procs[key] = proc
        self._set_status(key, "◐ 启动中…", "StatusWarn")   # 放在 start 前，started(异步)会随后覆盖为运行中
        self._sync_store(key, True)   # 广播：算法/电控 启动 → control_online/dspace_connected
        proc.start()

    def _on_started(self, key: str) -> None:
        """QProcess 真正拉起后：由「启动中」切到「运行中」。"""
        self._set_status(key, "● 运行中", "StatusOnline")
        self._log(f"[{key}] 已启动")

    def _on_finish(self, key: str, code: int, st) -> None:
        if key in self._manual_stop:
            self._manual_stop.discard(key)      # 手动停止：保持「已停止」，不再覆盖
            self._procs.pop(key, None)
            return
        self._log(f"[{key}] 已退出 (code={code})")
        self._set_status(key, "○ STOPPED", "StatusIdle")
        self._procs.pop(key, None)
        self._sync_store(key, False)

    def _on_error(self, key: str, err) -> None:
        self._log(f"[{key}] 错误: {err}")
        self._set_status(key, "● ERROR", "StatusOffline")
        self._sync_store(key, False)

    def _set_status(self, key: str, text: str, obj: str) -> None:
        lbl = self._status.get(key)
        if lbl is None:
            return
        lbl.setText(text)
        lbl.setObjectName(obj)
        style = lbl.style(); style.unpolish(lbl); style.polish(lbl)

    def _sync_store(self, key: str, running: bool) -> None:
        """把链模块启停同步到 SystemStateStore，让顶条/SYSTEM 页联动（广播驱动）。"""
        h = {}
        if key == "algo":
            h["control_online"] = running
        elif key == "elec":
            h["dspace_connected"] = running
            h["bridge_mode"] = "CHAIN" if running else "FILE"
        if h:
            self._store.update_health(**h)

    # ---------- outbox/inbox 监视 + 注入 ----------
    def _refresh_files(self) -> None:
        out = self.ed_out.text().strip(); inn = self.ed_in.text().strip()
        try:
            do = sorted(p.name for p in Path(out).glob("*.json")) if Path(out).exists() else []
            di = sorted(p.name for p in Path(inn).glob("*_status.json")) if Path(inn).exists() else []
            self.st_real.setText(f"○ outbox({len(do)}): {', '.join(do[-3:])} | inbox({len(di)}): {', '.join(di[-3:])}")
        except Exception:
            pass
        # 算法进程兜底：进程确实 Running → 运行中（防止 started 信号未触发而一直「启动中」）
        if 'algo' in self._procs and self._procs['algo'].state() == QProcess.Running:
            self._set_status('algo', '● 运行中', 'StatusOnline')
        # 电控状态机细化：启动后 → 等待连接(READY,无客户端) / 已连接(CONN,有客户端)
        if 'elec' in self._procs:
            connf = os.path.join(tempfile.gettempdir(), 'elec_mock_conn.txt')
            readyf = os.path.join(tempfile.gettempdir(), 'elec_mock_ready.txt')
            if os.path.exists(connf):
                self._set_status('elec', '● 已连接', 'StatusOnline')
            elif os.path.exists(readyf):
                self._set_status('elec', '◐ 等待连接', 'StatusWarn')

    def inject_command(self) -> None:
        out = self.ed_out.text().strip()
        x = self.ed_tx.text().strip(); y = self.ed_ty.text().strip(); th = self.ed_tth.text().strip()
        cid = f"CMD-CONSOLE-{datetime.datetime.now().strftime('%H%M%S')}"
        cmd = {"schema_version": "2.0", "command_id": cid, "timestamp": datetime.datetime.now().timestamp(),
               "source": "SpaceSnakeVisionUI", "command_type": "move_to",
               "params": {"x": float(x), "y": float(y)}, "motion_params": {},
               "selected_target": None,
               "destination": {"name": "Goal_Zone", "pose_base": {"frame_id": "robot_base",
                                 "position": {"x": float(x), "y": float(y), "z": 0.0},
                                 "orientation_euler": {"roll": 0, "pitch": 0, "yaw": float(th)}}},
               "safety": {"allow_execute": True, "estop_active": False}}
        p = Path(out); p.mkdir(parents=True, exist_ok=True)
        (p / f"{cid}.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"[inject] {cid} → {out}")

    def _log(self, msg: str) -> None:
        self.chain_log.appendPlainText(f"[{_ts()}] {msg}")
        self.log_console.log(msg)
