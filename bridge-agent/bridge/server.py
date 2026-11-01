#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bridge/server.py — 浏览器桥接服务（P0，Python 标准库，零第三方依赖）

职责：接收 Agent / 真人 的浏览器操作任务，交给 Chrome 扩展执行，回报结果。
- 任务队列：pending → executing → done / failed
- 扩展通过 /api/task/poll 轮询取任务，/api/task/result 回报
- 所有任务与结果追加写入 logs/tasks.jsonl（验证后台）
- 监听 127.0.0.1:8080

用法：
    python bridge/server.py [--port 8080] [--host 127.0.0.1]
"""
import argparse
import base64
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG_DIR = os.path.join(ROOT, "logs")
TASKS_LOG = os.path.join(LOG_DIR, "tasks.jsonl")
AGENT_RUNS_DIR = os.path.join(LOG_DIR, "agent_runs")
SCREENSHOTS_DIR = os.path.join(LOG_DIR, "screenshots")   # P4-V-T1：截图落盘目录
CONSOLE_HTML = os.path.join(ROOT, "web", "console.html")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(AGENT_RUNS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# 让 bridge 进程能 import agent/core.py（命名空间包）
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
try:
    from agent.core import run_loop as agent_run_loop
    from agent.core import load_api_key as agent_load_api_key
    from agent.core import SKILLS as AGENT_SKILLS
    AGENT_AVAILABLE = True
except Exception as e:  # pragma: no cover
    AGENT_AVAILABLE = False
    AGENT_IMPORT_ERROR = str(e)

# P2-5：多 Agent 数据库桥存储层（SQLite：tasks 表写穿 + candidates 表入库/查表）
try:
    from agent.db import (init_db as db_init, upsert_task as db_upsert_task,
                          insert_candidates as db_insert_candidates,
                          query_candidates as db_query_candidates,
                          stats as db_stats, site_for_url as db_site_for_url)
    DB_AVAILABLE = True
except Exception as e:  # pragma: no cover
    DB_AVAILABLE = False
    DB_IMPORT_ERROR = str(e)

TASK_TTL_SECONDS = 300  # 任务超过 5 分钟未认领视为超时


class TaskStore:
    """线程安全的任务表 + JSONL 持久化 + SQLite tasks 表写穿（P2-5）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks = {}  # task_id -> dict
        self._order = []  # 保持创建顺序

    def _sync_db(self, task):
        """P2-5：tasks 表写穿（SQLite 不可用时静默降级，不影响内存任务链）。"""
        if DB_AVAILABLE:
            db_upsert_task(task)

    def create(self, action, params=None, source="api"):
        with self._lock:
            task_id = uuid.uuid4().hex[:12]
            task = {
                "id": task_id,
                "action": action,
                "params": params or {},
                "source": source,
                "status": "pending",      # pending/executing/done/failed/timeout
                "created_at": time.time(),
                "picked_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
            }
            self._tasks[task_id] = task
            self._order.append(task_id)
            self._append_log(task)
            self._sync_db(task)
            return task

    def pick_pending(self):
        """扩展轮询：取最早的 pending 任务并标记 executing。"""
        with self._lock:
            now = time.time()
            for tid in self._order:
                t = self._tasks.get(tid)
                if t is None:
                    continue
                if t["status"] == "pending" and (now - t["created_at"]) > TASK_TTL_SECONDS:
                    t["status"] = "timeout"
                    t["finished_at"] = now
                    t["error"] = "任务超时未被认领"
                    self._append_log(t)
                    self._sync_db(t)
                    continue
                if t["status"] == "pending":
                    t["status"] = "executing"
                    t["picked_at"] = now
                    self._append_log(t)
                    self._sync_db(t)
                    return t
            return None

    def finish(self, task_id, ok, result=None, error=None):
        with self._lock:
            t = self._tasks.get(task_id)
            if t is None:
                return False
            if t["status"] in ("done", "failed"):
                return False
            t["status"] = "done" if ok else "failed"
            t["finished_at"] = time.time()
            t["result"] = result
            t["error"] = error
            # P4-V-T1/P4-SOM：screenshot / som_shot 任务 → data_url 落盘 logs/screenshots/，
            # 结果换成文件路径（JSONL/DB 只记路径，不记几 MB 的 base64；som_shot 保留 elements 映射）
            if ok and t["action"] in ("screenshot", "som_shot") and isinstance(result, dict) and result.get("data_url"):
                t["result"] = self._save_screenshot(t["id"], result)
            self._append_log(t)
            self._sync_db(t)
            return True

    def _save_screenshot(self, task_id, result):
        """把扩展返回的 PNG data_url 写盘，返回 {ok, file, path, bytes, ...}（去掉 data_url）。"""
        data_url = result.get("data_url") or ""
        out = {k: v for k, v in result.items() if k != "data_url"}
        try:
            b64 = data_url.split(",", 1)[1] if data_url.startswith("data:image/") else data_url
            raw = base64.b64decode(b64)
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"{ts}_{task_id}.png"
            fpath = os.path.join(SCREENSHOTS_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(raw)
            out["ok"] = True
            out["file"] = fname
            out["path"] = fpath.replace("\\", "/")       # 绝对路径（agent/视觉模块可直接读）
            out["path_rel"] = f"logs/screenshots/{fname}"  # 相对 ROOT，展示用
            out["bytes"] = len(raw)
            out["saved_at"] = time.time()
            return out
        except Exception as e:
            out["ok"] = False
            out["error"] = f"截图落盘失败: {e}"
            return out

    def get(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            return json.loads(json.dumps(t)) if t else None

    def list_recent(self, limit=50):
        with self._lock:
            ids = self._order[-limit:]
            return [json.loads(json.dumps(self._tasks[i])) for i in ids if i in self._tasks]

    def pending_count(self):
        """还没被扩展认领的任务数（popup 显示 + 能不能停判断）。"""
        with self._lock:
            return sum(1 for t in self._tasks.values() if t["status"] == "pending")

    def inflight(self):
        """当前正被扩展执行的任务（executing）—— popup 状态行 + "现在有活可停"判断。"""
        with self._lock:
            for tid in reversed(self._order):
                t = self._tasks.get(tid)
                if t is not None and t["status"] == "executing":
                    picked = t["picked_at"] or time.time()
                    return {"id": t["id"], "action": t["action"], "source": t["source"],
                            "picked_at": picked, "age_s": round(time.time() - picked, 1)}
            return None

    def clear_pending(self):
        """人工停止：把尚未被认领的 pending 任务全部作废（正在 executing 的那个由脚本自查收尾）。"""
        with self._lock:
            now = time.time()
            n = 0
            for tid in self._order:
                t = self._tasks.get(tid)
                if t is not None and t["status"] == "pending":
                    t["status"] = "failed"
                    t["finished_at"] = now
                    t["error"] = "人工停止（清空待执行队列）"
                    self._append_log(t)
                    self._sync_db(t)
                    n += 1
            return n

    def _append_log(self, task):
        """JSONL 持久化（验证后台）。"""
        try:
            with open(TASKS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(task, ensure_ascii=False) + "\n")
        except Exception:
            pass


STORE = TaskStore()


class ControlGate:
    """人工总闸（2026-09-11 A+B「停止开关」）。

    语义 = **一次性刹车，不做粘性封锁**：
      - `POST /api/control/stop` → 记 `stopped_at`（并清空待执行队列）；
      - 正在跑的脚本（`collect_liepin` / `detail_collect`）在**每个动作前** `GET /api/control/state`，
        拿自己的启动时间 `t0` 比对：`stopped_at > t0` 说明"停"发生在本次运行期间 → **干净收尾**
        （已采到的数据照常写盘，不留半截垃圾）；
      - 之后的新任务 / 新采集**不受影响** → 不需要"恢复"按钮，也不会因忘了解除而卡死。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stopped_at = None

    def stop(self):
        with self._lock:
            self._stopped_at = time.time()
            return self._stopped_at

    def state(self):
        with self._lock:
            return self._stopped_at


GATE = ControlGate()


class AgentRunner:
    """后台跑 agent 循环，逐步事件实时收集，供控制台轮询。"""

    def __init__(self, bridge_url):
        self.bridge_url = bridge_url
        self._lock = threading.Lock()
        self._runs = {}   # run_id -> run dict
        self._order = []

    def start(self, task_desc, max_steps, page_delay_min=2.0, page_delay_max=4.0, risk_check=True,
              tab_id=None, persist=True, sink=True):
        with self._lock:
            for rid in self._order:
                if self._runs[rid]["status"] == "running":
                    return None, "已有 agent 运行中，请等它结束"
            run_id = uuid.uuid4().hex[:10]
            run = {
                "id": run_id,
                "task": task_desc,
                "status": "running",
                "events": [],
                "final": None,
                "started_at": time.time(),
                "finished_at": None,
                "tab_id": tab_id,      # P2-5：钉住操作目标标签（不依赖激活页）
                "persist": persist,    # P3-T8：入库可选开关（False 时任务照跑不落库）
                "sink": sink,          # P4-V-T3：经验沉淀开关（成功任务自动写回经验库）
            }
            self._runs[run_id] = run
            self._order.append(run_id)

        def worker():
            def on_step(ev):
                with self._lock:
                    run["events"].append(ev)
                print(f"[agent-run {run_id}] {ev.get('type')} step={ev.get('step','')}")

            try:
                final = agent_run_loop(task_desc, self.bridge_url, max_steps=max_steps,
                                       api_key=agent_load_api_key(), on_step=on_step,
                                       page_delay_min=page_delay_min, page_delay_max=page_delay_max,
                                       risk_check=risk_check,
                                       cancel_requested=lambda: bool(run.get("cancel_requested")),
                                       pause_requested=lambda: bool(run.get("paused")),
                                       request_pause=lambda: run.__setitem__("paused", True),
                                       confirm_requested=lambda: bool(run.get("confirm_pending")),
                                       tab_id=run.get("tab_id"))
            except Exception as e:
                final = {"ok": False, "summary": f"agent 循环异常: {e}", "data": {}, "steps": 0}
            # P4-V-T3：成功任务自动沉淀经验——从事件流提取关键路径/锚点/截图写入经验库；
            # 高置信自动写回（version+1），低置信仅起草（V7 脏经验防护，待人工确认）
            if final.get("ok") and run.get("sink", True):
                try:
                    from agent.experience import sink_after_run
                    _sink = sink_after_run(run.get("events") or [], final, tab_id=run.get("tab_id"))
                except Exception as e:
                    _sink = {"written": False, "reason": f"经验沉淀异常: {e}"}
                if _sink:
                    _ev = {"type": "experience_sunk" if _sink.get("written") else "experience_draft",
                           "reason": _sink.get("reason", "")}
                    if _sink.get("written") and _sink.get("entry"):
                        _ev["message"] = (f"经验已沉淀：v{_sink['entry'].get('version')} "
                                          f"id={_sink['entry'].get('id')}（{_sink.get('reason')}）")
                    else:
                        _ev["message"] = f"经验起草待人工确认：{_sink.get('reason')}"
                    with self._lock:
                        run["events"].append(_ev)
                    print(f"[agent-run {run_id}] 经验沉淀: {_sink.get('reason')}")
            with self._lock:
                if not final.get("ok") and run.get("cancel_requested"):
                    run["status"] = "cancelled"
                else:
                    run["status"] = "done" if final.get("ok") else "failed"
                run["final"] = final
                run["finished_at"] = time.time()
            # 落盘
            try:
                path = os.path.join(AGENT_RUNS_DIR, f"{run_id}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(run, f, ensure_ascii=False, indent=2, default=str)
            except Exception:
                pass
            # P2-5：Agent finish 后 candidates 批量入库（source_id 去重，供其他 Agent 查表）
            # P3-T8：persist=False 时跳过入库（任务照跑、结果不落库，由上层自行消费 final.data）
            if DB_AVAILABLE and final.get("ok") and run.get("persist", True):
                _data = final.get("data") or {}
                _cands = _data.get("candidates") or []
                if _cands:
                    _run_url = _data.get("url") or _last_snapshot_url(run)
                    _site = db_site_for_url(_run_url) if _run_url else None
                    try:
                        _ins, _skp = db_insert_candidates(_cands, run_id=run_id,
                                                          site=_site, url=_run_url)
                        print(f"[agent-run {run_id}] 候选人入库：新增 {_ins} 条，去重跳过 {_skp} 条")
                    except Exception as e:
                        print(f"[agent-run {run_id}] ⚠️ candidates 入库失败: {e}")

        threading.Thread(target=worker, daemon=True).start()
        return run_id, None

    def cancel(self, run_id=None):
        """P2-2 紧急停止：置取消标志，run_loop 在当前步骤结束后退出。

        run_id 省略时取消当前运行中的 run（同一时刻至多一个 running）。
        返回 (run_id, err)；err 为 None 表示成功。
        """
        with self._lock:
            if run_id:
                r = self._runs.get(run_id)
                if r is None:
                    return None, "run not found"
            else:
                r = None
                for rid in self._order:
                    if self._runs[rid]["status"] == "running":
                        r = self._runs[rid]
                        run_id = rid
                        break
                if r is None:
                    return None, "没有运行中的 agent 任务"
            if r["status"] != "running":
                return None, f"run {r['id']} 不在运行中（status={r['status']}）"
            r["cancel_requested"] = True
            return run_id, None

    def pause(self, run_id=None):
        """P2-2 暂停：置 paused 标志，run_loop 在下一步开始前进入等待（可继续/紧急停止）。"""
        with self._lock:
            r, run_id, err = self._find_running(run_id)
            if err:
                return None, err
            r["paused"] = True
            return run_id, None

    def resume(self, run_id=None):
        """P2-2 继续：清除 paused 标志，run_loop 从等待中恢复。"""
        with self._lock:
            r, run_id, err = self._find_running(run_id)
            if err:
                return None, err
            r["paused"] = False
            return run_id, None

    def confirm(self, run_id=None, approve=True):
        """P3-T5 不可逆动作确认：approve=True 确认执行（清除 confirm_pending），
        approve=False 拒绝（置 cancel_requested，等同紧急停止语义）。
        run_loop 侧 confirm_requested 回调返回 run.get("confirm_pending")。"""
        with self._lock:
            r, run_id, err = self._find_running(run_id)
            if err:
                return None, err
            if approve:
                r["confirm_pending"] = False
                r["confirm_decision"] = "approved"
            else:
                r["confirm_pending"] = False
                r["confirm_decision"] = "denied"
                r["cancel_requested"] = True  # 拒绝 = 中止本动作，等同取消
            return run_id, None

    def _find_running(self, run_id):
        """按 run_id（或当前运行中）找 running run；返回 (run, run_id, err)。"""
        if run_id:
            r = self._runs.get(run_id)
            if r is None:
                return None, None, "run not found"
        else:
            r = None
            for rid in self._order:
                if self._runs[rid]["status"] == "running":
                    r = self._runs[rid]
                    run_id = rid
                    break
            if r is None:
                return None, None, "没有运行中的 agent 任务"
        if r["status"] != "running":
            return None, None, f"run {r['id']} 不在运行中（status={r['status']}）"
        return r, run_id, None

    def get(self, run_id):
        with self._lock:
            r = self._runs.get(run_id)
            return json.loads(json.dumps(r, default=str)) if r else None

    def list_recent(self, limit=20):
        with self._lock:
            ids = self._order[-limit:]
            out = []
            for i in ids:
                r = self._runs[i]
                out.append({"id": r["id"], "task": r["task"], "status": r["status"],
                            "paused": bool(r.get("paused")),
                            "steps": len(r["events"]), "started_at": r["started_at"],
                            "final": r["final"]})
            return out


RUNNER = AgentRunner(f"http://{os.environ.get('BRIDGE_BIND_HOST', '127.0.0.1')}:{os.environ.get('BRIDGE_BIND_PORT', '8080')}")


# ── 本地来源白名单（2026-09-20 加；**桥的第一道门**）────────────────────────
# 威胁（实测）：桥能 click/type（含"在猎聘聊天里发消息"），而它原先**无任何校验 + ACAO: \***
#   → 你浏览器里**任意一个网页**都能 POST 简单请求来驱使桥操作你已登录的页面。
# 治法（最小、且**不依赖"桥将来变成什么形态"**）：凡带 Origin 的请求必须来自白名单，否则 403。
#   · Python 脚本 / DSH 工具（Node 侧）→ 不发送 Origin，照旧放行；
#   · 浏览器扩展 → `chrome-extension://` 一律放行（只有装在本机浏览器里的扩展能发）；
#   · 本机界面（DSH GUI :3080 / 面板 :8501）→ 白名单。
# 故意不做（留给"桥的形态"那一场讨论）：token、权限矩阵、端口自适应。
ALLOWED_ORIGINS = {
    "http://127.0.0.1:3080", "http://localhost:3080",
    "http://127.0.0.1:8501", "http://localhost:8501",
}
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://",)


def origin_allowed(origin: str) -> bool:
    """来源是否放行（**空 = 非浏览器调用**，放行：脚本/Node/MCP 都不带 Origin）。"""
    o = (origin or "").strip()
    if not o:
        return True
    return o in ALLOWED_ORIGINS or o.startswith(ALLOWED_ORIGIN_PREFIXES)


def _last_snapshot_url(run):
    """从 run 事件里取最后一次快照的 URL（candidates 入库兜底站点信息用）。"""
    url = ""
    for ev in (run.get("events") or []):
        if ev.get("type") == "snapshot" and ev.get("url"):
            url = ev["url"]
    return url


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------- 基础 ----------
    def log_message(self, fmt, *args):
        # 精简控制台日志
        sys_stdout_write(f"[bridge] {self.address_string()} {fmt % args}")

    def _cors_headers(self):
        """只对**白名单来源**回 CORS 头（不再一律 `*`）；非白名单一律不回。"""
        o = (self.headers.get("Origin") or "").strip()
        if o and origin_allowed(o):
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _origin_blocked(self) -> bool:
        """带 Origin 且不在白名单 → 挡掉并记账（日志里能看见谁在敲门）。"""
        o = (self.headers.get("Origin") or "").strip()
        if origin_allowed(o):
            return False
        sys_stdout_write(f"[bridge] 拒绝来源 {o} → {self.path}")
        # ⚠️ 2026-09-20 实测（补丁后日志里抓到 ConnectionResetError）：回 403 前必须**把请求体读干净**
        #    并关掉这条连接——否则 HTTP/1.1 keep-alive 下残留的 body 会让下一次请求错位。
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 0:
                self.rfile.read(n)
        except Exception:  # noqa: BLE001
            pass
        self.close_connection = True
        self._send_json({"error": "origin not allowed", "origin": o,
                         "hint": "只允许本机白名单界面 / 扩展 / 不带 Origin 的本地调用"}, status=403)
        return True

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ---------- 路由 ----------
    def do_OPTIONS(self):
        if self._origin_blocked():
            return
        self._send_json({})

    def _send_html(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self._origin_blocked():
            return
        path = urlparse(self.path).path
        if path == "/" or path == "/console":
            if os.path.exists(CONSOLE_HTML):
                with open(CONSOLE_HTML, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            else:
                self._send_html("<h1>console.html 不存在</h1>", status=404)
        elif path == "/api/health":
            self._send_json({"ok": True, "service": "browser-bridge", "time": time.time(),
                             "agent": AGENT_AVAILABLE})
        elif path == "/api/agent/runs":
            self._send_json({"runs": RUNNER.list_recent()})
        elif path == "/api/agent/skills":
            # P2-5 技能注册表：调度 Agent 查询浏览器 Agent 全部动作 + 参数 Schema 后派活
            if not AGENT_AVAILABLE:
                self._send_json({"error": f"agent 模块不可用: {AGENT_IMPORT_ERROR}"}, status=500)
            else:
                self._send_json({"skills": AGENT_SKILLS, "count": len(AGENT_SKILLS)})
        elif path == "/api/candidates":
            # P2-5 查表：其他 Agent 消费候选池（site/source_id 过滤 + 分页）
            site = self._query("site")
            source_id = self._query("source_id")
            try:
                limit = min(int(self._query("limit") or 100), 500)
                offset = max(int(self._query("offset") or 0), 0)
            except ValueError:
                self._send_json({"error": "limit/offset 必须是整数"}, status=400)
                return
            if not DB_AVAILABLE:
                self._send_json({"error": f"数据库不可用: {DB_IMPORT_ERROR}"}, status=500)
            else:
                rows, total = db_query_candidates(site=site or None, source_id=source_id or None,
                                                  limit=limit, offset=offset)
                self._send_json({"candidates": rows, "total": total, "limit": limit, "offset": offset})
        elif path == "/api/db/stats":
            if not DB_AVAILABLE:
                self._send_json({"error": f"数据库不可用: {DB_IMPORT_ERROR}"}, status=500)
            else:
                self._send_json(db_stats())
        elif path.startswith("/api/agent/status/"):
            rid = unquote(path[len("/api/agent/status/"):])
            r = RUNNER.get(rid)
            if r is None:
                self._send_json({"error": "run not found"}, status=404)
            else:
                self._send_json({"run": r})
        elif path == "/api/control/state":
            # 停止开关状态：popup 显示用 + 采集脚本每轮自查用（见 ControlGate 说明）
            self._send_json({"ok": True, "stopped_at": GATE.state(),
                             "pending": STORE.pending_count(), "inflight": STORE.inflight()})
        elif path == "/api/task/poll":
            task = STORE.pick_pending()
            self._send_json({"task": task})
        elif path == "/api/tasks":
            self._send_json({"tasks": STORE.list_recent(limit=int(self._query("limit") or 50))})
        elif path.startswith("/api/task/"):
            tid = unquote(path[len("/api/task/"):])
            t = STORE.get(tid)
            if t is None:
                self._send_json({"error": "task not found"}, status=404)
            else:
                self._send_json({"task": t})
        elif path == "/api/logs":
            self._send_json({"log": read_log_tail()})
        elif path == "/api/experience/drafts":
            # P4 经验草稿：低置信沉淀未自动写回、待人工确认的条目列表
            try:
                from agent.experience import list_drafts
                _status = self._query("status") or "pending"
                drafts = list_drafts(status=_status)
            except Exception:
                drafts = []
            self._send_json({"drafts": drafts, "count": len(drafts)})
        elif path == "/api/screenshots":
            # P4-V-T1：截图清单（视觉问答验证数据表用）
            files = []
            try:
                names = sorted(os.listdir(SCREENSHOTS_DIR), reverse=True)[:100]
                for n in names:
                    if not n.endswith(".png"):
                        continue
                    fp = os.path.join(SCREENSHOTS_DIR, n)
                    try:
                        st = os.stat(fp)
                        files.append({"file": n, "path_rel": f"logs/screenshots/{n}",
                                      "bytes": st.st_size, "ts": st.st_mtime})
                    except OSError:
                        continue
            except OSError:
                pass
            self._send_json({"screenshots": files, "count": len(files),
                             "dir": SCREENSHOTS_DIR.replace("\\", "/")})
        elif path.startswith("/screenshots/"):
            # P4-V-T1：静态服务截图文件（控制台/人工直接看图）
            name = os.path.basename(unquote(path[len("/screenshots/"):]))
            fp = os.path.join(SCREENSHOTS_DIR, name)
            if name.endswith(".png") and os.path.exists(fp):
                with open(fp, "rb") as f:
                    raw = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(raw)
            else:
                self._send_json({"error": "screenshot not found"}, status=404)
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def do_POST(self):
        if self._origin_blocked():
            return
        path = urlparse(self.path).path
        if path == "/api/agent/run":
            if not AGENT_AVAILABLE:
                self._send_json({"error": f"agent 模块不可用: {AGENT_IMPORT_ERROR}"}, status=500)
                return
            body = self._read_json()
            task = (body.get("task") or "").strip()
            if not task:
                self._send_json({"error": "task 不能为空"}, status=400)
                return
            max_steps = int(body.get("max_steps") or 20)
            page_delay_min = float(body.get("page_delay_min") or 2.0)
            page_delay_max = float(body.get("page_delay_max") or 4.0)
            risk_check = str(body.get("risk_check", "on")) != "off"
            tab_id = body.get("tab_id")
            if tab_id is not None:
                try:
                    tab_id = int(tab_id)
                except (TypeError, ValueError):
                    self._send_json({"error": "tab_id 必须是整数标签页 id"}, status=400)
                    return
            # P3-T8：入库可选开关——persist=false 时任务照跑、结果不落 SQLite
            persist = str(body.get("persist", "true")).lower() != "false"
            # P4-V-T3：经验沉淀开关——sink=false 时不写经验库（默认开）
            sink = str(body.get("sink", "true")).lower() != "false"
            run_id, err = RUNNER.start(task, max_steps, page_delay_min=page_delay_min,
                                       page_delay_max=page_delay_max, risk_check=risk_check,
                                       tab_id=tab_id, persist=persist, sink=sink)
            if run_id is None:
                self._send_json({"error": err}, status=409)
            else:
                self._send_json({"run_id": run_id, "status": "running"}, status=201)
        elif path == "/api/agent/cancel":
            body = self._read_json()
            run_id, err = RUNNER.cancel(body.get("run_id") or None)
            if err:
                status = 404 if err == "run not found" else 409
                self._send_json({"error": err}, status=status)
            else:
                self._send_json({"ok": True, "run_id": run_id, "status": "cancelling"})
        elif path == "/api/agent/pause":
            body = self._read_json()
            run_id, err = RUNNER.pause(body.get("run_id") or None)
            if err:
                status = 404 if err == "run not found" else 409
                self._send_json({"error": err}, status=status)
            else:
                self._send_json({"ok": True, "run_id": run_id, "status": "paused"})
        elif path == "/api/agent/resume":
            body = self._read_json()
            run_id, err = RUNNER.resume(body.get("run_id") or None)
            if err:
                status = 404 if err == "run not found" else 409
                self._send_json({"error": err}, status=status)
            else:
                self._send_json({"ok": True, "run_id": run_id, "status": "resumed"})
        elif path == "/api/agent/confirm":
            # P3-T5 不可逆动作确认：body {run_id?, approve: true|false}
            # approve=true 确认执行；false 拒绝（中止任务）
            body = self._read_json()
            approve = bool(body.get("approve", True))
            run_id, err = RUNNER.confirm(body.get("run_id") or None, approve=approve)
            if err:
                status = 404 if err == "run not found" else 409
                self._send_json({"error": err}, status=status)
            else:
                self._send_json({"ok": True, "run_id": run_id,
                                 "status": "confirmed" if approve else "denied"})
        elif path == "/api/experience/confirm":
            # P4 经验草稿人工确认：body {draft_id, approve: true|false}
            # approve=true → 强制写回经验库（人工放行）；false → 拒绝（丢弃）
            body = self._read_json()
            draft_id = str(body.get("draft_id") or "")
            approve = bool(body.get("approve", True))
            if not draft_id:
                self._send_json({"error": "draft_id 必填（GET /api/experience/drafts 查看）"}, status=400)
                return
            try:
                from agent.experience import approve_draft
                res = approve_draft(draft_id, approve=approve)
            except Exception as e:
                self._send_json({"error": f"经验确认失败: {e}"}, status=500)
                return
            if not res.get("ok"):
                self._send_json({"error": res.get("error")}, status=404)
            else:
                self._send_json({"ok": True, "draft": res.get("draft"),
                                 "sink_result": res.get("sink_result")})
        elif path == "/api/control/stop":
            # 人工总闸：置停止标志 + 清空待执行队列（正在 executing 的动作跑完后由脚本自查收尾）
            ts = GATE.stop()
            cleared = STORE.clear_pending()
            self._send_json({"ok": True, "stopped_at": ts, "cleared": cleared,
                             "inflight": STORE.inflight(),
                             "note": "已置停止标志并清空待执行队列；正在跑的动作结束后收尾"})
        elif path == "/api/task":
            body = self._read_json()
            action = body.get("action")
            if not action:
                self._send_json({"error": "action is required"}, status=400)
                return
            task = STORE.create(action, body.get("params"), source=body.get("source", "api"))
            self._send_json({"task": task}, status=201)
        elif path == "/api/task/result":
            body = self._read_json()
            tid = body.get("task_id") or body.get("id")
            if not tid:
                self._send_json({"error": "task_id is required"}, status=400)
                return
            ok = bool(body.get("ok", False))
            STORE.finish(tid, ok, body.get("result"), body.get("error"))
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def _query(self, key):
        qs = urlparse(self.path).query
        for part in qs.split("&"):
            if part.startswith(key + "="):
                return unquote(part[len(key) + 1:])
        return None


def read_log_tail(n=200):
    if not os.path.exists(TASKS_LOG):
        return []
    with open(TASKS_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return [json.loads(l) for l in lines[-n:] if l.strip()]


def sys_stdout_write(msg):
    import sys
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    # P2-5：SQLite 存储层初始化（tasks 写穿 + candidates 入库/查表）
    if DB_AVAILABLE:
        try:
            db_init()
            print(f"[bridge] SQLite 存储就绪: {db_stats()}")
        except Exception as e:
            print(f"[bridge] ⚠️ SQLite 初始化失败（继续以内存+JSONL 运行）: {e}")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[bridge] 浏览器桥接服务已启动: http://{args.host}:{args.port}")
    print(f"[bridge] 任务日志: {TASKS_LOG}")
    print("[bridge] 按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] 已停止")
        server.server_close()


if __name__ == "__main__":
    main()
