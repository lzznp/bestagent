#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent/db.py — 多 Agent 数据库桥存储层（P2-5，Python 标准库 sqlite3，零第三方依赖）

设计依据（HANDOFF-P2-WIP.md 第 5 节决策 4，已拍板）：
    任务表/数据表分离 + status 驱动轮询 + source_id 唯一约束，不需要消息队列。

两张表：
    tasks       表：浏览器操作任务链（id/action/params/status/source/created_at/picked_at/
                   finished_at/result/error + paused/cancelled 兼容 P2-2），status 状态机
                   pending→executing→done/failed/timeout，驱动调度 Agent 轮询。
                   bridge TaskStore 每次变更写穿同步（JSONL 审计日志保留）。
    candidates  表：Agent finish 后的提取结果（source_id 唯一约束 + INSERT OR IGNORE
                   防重复采集；raw_text/fields/site/url/run_id/created_at）。

其他 Agent 消费入口（HTTP）：
    GET /api/candidates    查表（site/source_id 过滤、分页）
    GET /api/tasks         任务链（实时内存 + 本表持久化）

线程安全：bridge 是多线程服务（ThreadingHTTPServer + agent worker），
本模块用单一连接 + 全局锁保护（check_same_thread=False + WAL）。
"""
import json
import os
import sqlite3
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.environ.get("AGENT_DB_PATH") or os.path.join(ROOT, "logs", "agent.db")

_lock = threading.Lock()
_conn = None


def _connect():
    """创建连接（不建表）。
    isolation_level=None（autocommit）：sqlite3 默认隔离级别下 DML 需显式 commit，
    连接关闭时未提交事务会回滚——桥接进程可能随时退出，必须每步落盘。
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_schema(conn):
    """建表（幂等）；调用方需持 _lock。"""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tasks (
        id          TEXT PRIMARY KEY,
        action      TEXT NOT NULL,
        params      TEXT,             -- JSON
        source      TEXT,
        status      TEXT NOT NULL,    -- pending/executing/done/failed/timeout
        created_at  REAL,
        picked_at   REAL,
        finished_at REAL,
        result      TEXT,             -- JSON
        error       TEXT,
        paused      INTEGER DEFAULT 0,    -- P2-2 兼容字段（预留）
        cancelled   INTEGER DEFAULT 0     -- P2-2 兼容字段（预留）
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, created_at);

    CREATE TABLE IF NOT EXISTS candidates (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   TEXT,             -- 站点唯一 ID（res_id_encode 等）
        raw_text    TEXT,
        fields      TEXT,             -- JSON
        site        TEXT,             -- 知识库域名或主机名
        url         TEXT,
        run_id      TEXT,             -- 采集该批数据的 agent run
        created_at  REAL
    );
    -- source_id 唯一约束（防重复采集）；空串/NULL 不参与唯一（无法去重的行不入表）
    CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_sid
        ON candidates(source_id) WHERE source_id IS NOT NULL AND source_id <> '';
    """)


def _get_conn():
    """懒初始化单一连接 + 建表（全局锁保护，非重入结构）。"""
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = _connect()
                _ensure_schema(_conn)
    return _conn


def init_db():
    """幂等建表（显式调用入口，bridge 启动时用）。"""
    _get_conn()


def site_for_url(url):
    """站点标识：优先命中知识库域名，否则取主机名。"""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        return None
    try:
        import agent.knowledge as kb
    except ImportError:
        try:
            import knowledge as kb
        except ImportError:
            kb = None
    if kb is not None:
        try:
            dom, _entry = kb.match_knowledge(url or "")
            if dom:
                return dom
        except Exception:
            pass
    return host


# ------------------------------------------------------------
# tasks 表（写穿：bridge TaskStore 每次变更后同步；JSONL 审计保留）
# ------------------------------------------------------------

def upsert_task(task):
    """把任务记录写入/更新 tasks 表（INSERT OR REPLACE）。"""
    try:
        params = task.get("params") or {}
        result = task.get("result")
        # P3-T9：_get_conn 必须在 with _lock 之外调用——_conn 首次为 None 时
        # _get_conn 内部会拿 _lock，若此时已持有 _lock（threading.Lock 不可重入）
        # 会同线程死锁（P2-WIP 踩坑 #2 变体，CLI 独立进程首次入库必现）。
        c = _get_conn()
        with _lock:
            c.execute(
                "INSERT OR REPLACE INTO tasks"
                " (id, action, params, source, status, created_at, picked_at,"
                "  finished_at, result, error, paused, cancelled)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (task.get("id"), task.get("action"),
                 json.dumps(params, ensure_ascii=False),
                 task.get("source"), task.get("status"),
                 task.get("created_at"), task.get("picked_at"), task.get("finished_at"),
                 json.dumps(result, ensure_ascii=False) if result is not None else None,
                 task.get("error"),
                 1 if task.get("paused") else 0,
                 1 if task.get("cancelled") else 0))
        return True
    except Exception:
        return False


# ------------------------------------------------------------
# candidates 表（Agent finish 后批量入库 + 查表）
# ------------------------------------------------------------

def insert_candidates(candidates, run_id=None, site=None, url=None):
    """Agent finish 后批量入库：source_id 唯一约束，重复自动忽略（INSERT OR IGNORE）。

    Args:
        candidates: list of {source_id, raw_text, fields, url?}
        run_id:     采集该批数据的 agent run id（CLI 可为 None/自定义）
        site/url:   兜底站点信息（候选行自带 url 时优先用行内 url）
    Returns:
        (inserted, skipped): 实际新增条数 / 因去重或缺失 source_id 跳过的条数。
    """
    if not candidates:
        return 0, 0
    now = time.time()
    rows = []
    skipped_no_id = 0
    for cand in candidates:
        if not isinstance(cand, dict):
            skipped_no_id += 1
            continue
        sid = str(cand.get("source_id") or "").strip()
        if not sid:
            skipped_no_id += 1  # 无唯一 ID 的行无法去重，不入 candidates（防垃圾数据）
            continue
        row_url = cand.get("url") or url or ""
        fields = cand.get("fields") or {}
        rows.append((sid, cand.get("raw_text") or "",
                     json.dumps(fields, ensure_ascii=False),
                     site_for_url(row_url) or site,
                     row_url, run_id, now))
    if not rows:
        return 0, skipped_no_id
    # P3-T9：_get_conn 在 with _lock 之外调用（防不可重入死锁，见 upsert_task 注释）
    c = _get_conn()
    with _lock:
        before = c.total_changes
        c.execute("BEGIN")
        try:
            c.executemany(
                "INSERT OR IGNORE INTO candidates"
                " (source_id, raw_text, fields, site, url, run_id, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                rows)
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        inserted = c.total_changes - before
    return inserted, (len(rows) - inserted) + skipped_no_id


def query_candidates(site=None, source_id=None, limit=100, offset=0):
    """查表（其他 Agent 消费）：site/source_id 过滤 + 分页。返回 (rows, total)。"""
    # P3-T9：_get_conn 在 with _lock 之外调用（防不可重入死锁）
    c = _get_conn()
    with _lock:
        where, args = [], []
        if site:
            where.append("site = ?")
            args.append(site)
        if source_id:
            where.append("source_id = ?")
            args.append(source_id)
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        total = c.execute(f"SELECT COUNT(*) FROM candidates{wsql}", args).fetchone()[0]
        rows = c.execute(
            f"SELECT * FROM candidates{wsql} ORDER BY id DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)]).fetchall()
        out = [dict(r) for r in rows]
        for r in out:
            if r.get("fields"):
                try:
                    r["fields"] = json.loads(r["fields"])
                except Exception:
                    pass
        return out, total


def stats():
    """存储统计（健康/审计用）。"""
    # P3-T9：_get_conn 在 with _lock 之外调用（防不可重入死锁）
    c = _get_conn()
    with _lock:
        tasks = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        candidates = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        by_status = dict(c.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
    return {"db": DB_PATH, "tasks": tasks, "candidates": candidates, "task_status": by_status}


if __name__ == "__main__":
    # 自测：直接运行 python agent/db.py
    init_db()
    print(stats())
    ins, skp = insert_candidates([
        {"source_id": "A1", "raw_text": "行A", "fields": {"res_id_encode": "A1"}, "url": "https://h.liepin.com/x"},
        {"source_id": "A1", "raw_text": "行A(重复)", "fields": {"res_id_encode": "A1"}, "url": "https://h.liepin.com/x"},
        {"source_id": "", "raw_text": "无ID行", "fields": {}},
    ], run_id="selftest")
    print(f"inserted={ins} skipped={skp}（期望 inserted=1 skipped=2：重复1 + 无ID1）")
    rows, total = query_candidates(site="h.liepin.com")
    print(f"candidates total={total} 最近一条: {rows[0] if rows else None}")
