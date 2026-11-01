#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""job_db.py — **岗位库**（一个岗位一个 SQLite）：采集的候选人 / 匹配结果 / 沟通记录

决策（2026-09-15 老板拍板）：
  ① **一岗一库**：`data/chat/<job_code>/job.db`（不做"总库"）；
  ② **不做跨岗复用/人才库**（明确不做，不建索引库）；
  ③ 只要保证"**本岗内候选人不重复**"。

为什么要一岗一库：数据跟岗位走（岗位目录 = 全项目对齐键）。"关闭/删除岗位"就是**挪目录**，
  库跟着走 —— 总库那种"岗位早没了、库里留孤儿行"的毛病自然消失（`data/business.db` 上就出过：
  面板只剩 3 个岗，库里躺着 3 个早就删掉的岗、311 行）。

本模块只干"存/取"这件事，**不做任何判断**（判断在 local_score / 匹配层）。
纪律：schema 唯一来源 = `schema.sql`（N 个岗位库都用它建）；全库幂等 upsert，重跑安全。

用法：
    from job_db import open_db, upsert_candidate, save_match
    con = open_db("J-CHAT-20260914-172253")
    r = upsert_candidate(con, "J-CHAT-...", {"source_id": "abc", "summary_text": "...", "local_score": 72})
    # r = {"action": "created"|"updated"|"duplicate", "id": 1, "first_time": True}
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from framework_config import WORKSPACE  # noqa: E402

SCHEMA_VERSION = 2
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# 允许调用方写入的候选人字段（白名单：防止调用方塞任意列名进 SQL）
CAND_FIELDS = ("source_platform", "source_url", "raw_content", "summary_text",
               "display_name", "display_company", "display_position", "active_badge",
               "structured", "local_score", "local_hits", "round_tag", "status",
               "collected_by", "collected_account")
JSON_FIELDS = ("structured", "local_hits")
EVENT_TYPES = ("打招呼", "回复", "面试", "offer", "入职", "不合适", "备注")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def content_hash(job_code: str, raw: str) -> str:
    """简历原文指纹：sha1(岗位号 \\x1f 原文) 前 16 位。**只在 raw 非空时用**（空则存 NULL）。"""
    h = hashlib.sha1(f"{job_code}\x1f{raw}".encode("utf-8")).hexdigest()
    return h[:16]


def db_path(job_code: str, root: Path | None = None) -> Path:
    """岗位库路径：<root>/<job_code>/job.db（root 默认 = data/chat；测试可传临时目录）。"""
    base = Path(root) if root else (WORKSPACE / "data" / "chat")
    return base / job_code / "job.db"


def _migrate(con: sqlite3.Connection) -> int:
    """按 user_version 升级（本文件必须幂等）。返回升级后的版本号。

    v1 → v2（2026-09-16）：删掉 `candidates` 上的 `UNIQUE(job_code, content_hash)`。
    理由（单测实测）：那条唯一约束会把**两个 source_id 不同、简历原文恰好相同**的人当成一个人，
    第二次插入直接被当成 duplicate 丢掉 —— 那是"丢人"，比"多留一行"贵得多。
    `source_id` 本身已是可靠主锚点，兜底不该是唯一约束。
    老库（v1）用"重建表 + 拷数据"的方式改约束（SQLite 不支持直接 DROP CONSTRAINT）。
    """
    cur = con.execute("PRAGMA user_version").fetchone()[0] or 0
    if cur < 1:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        con.execute("PRAGMA user_version = 1")
        cur = 1
    if cur < 2:
        # 重建 candidates（保留 id 与全部数据；只去掉 content_hash 的唯一约束）
        con.execute("PRAGMA foreign_keys=OFF")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS candidates_v2 (
              id               INTEGER PRIMARY KEY AUTOINCREMENT,
              job_code         TEXT NOT NULL,
              source_platform  TEXT NOT NULL DEFAULT 'liepin',
              source_id        TEXT NOT NULL,
              source_url       TEXT DEFAULT '',
              content_hash     TEXT,
              raw_content      TEXT DEFAULT '',
              summary_text     TEXT DEFAULT '',
              display_name     TEXT DEFAULT '',
              display_company  TEXT DEFAULT '',
              display_position TEXT DEFAULT '',
              active_badge     TEXT DEFAULT '',
              structured       TEXT DEFAULT '{}',
              local_score      REAL,
              local_hits       TEXT DEFAULT '[]',
              round_tag        TEXT DEFAULT '',
              status           TEXT DEFAULT 'new',
              collected_by     TEXT DEFAULT '',
              collected_account TEXT DEFAULT '',
              first_seen_at    TEXT DEFAULT '',
              last_seen_at     TEXT DEFAULT '',
              updated_at       TEXT DEFAULT '',
              UNIQUE(job_code, source_id)
            );
            INSERT OR IGNORE INTO candidates_v2
              SELECT id, job_code, source_platform, source_id, source_url, content_hash, raw_content,
                     summary_text, display_name, display_company, display_position, active_badge,
                     structured, local_score, local_hits, round_tag, status, collected_by,
                     collected_account, first_seen_at, last_seen_at, updated_at
              FROM candidates;
            DROP TABLE candidates;
            ALTER TABLE candidates_v2 RENAME TO candidates;
            CREATE INDEX IF NOT EXISTS idx_cand_job   ON candidates(job_code);
            CREATE INDEX IF NOT EXISTS idx_cand_score ON candidates(job_code, local_score);
            CREATE INDEX IF NOT EXISTS idx_cand_hash  ON candidates(job_code, content_hash);
        """)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA user_version = 2")
        cur = 2
    if cur < SCHEMA_VERSION:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.commit()
    return SCHEMA_VERSION


def open_db(job_code: str | None = None, path: Path | None = None,
            root: Path | None = None) -> sqlite3.Connection:
    """打开（必要时创建）岗位库：建目录 → WAL + busy_timeout + 外键 → 迁移。

    WAL/busy_timeout 是给"面板 + 采集脚本 + 匹配脚本同时读写"用的（照参考项目的做法）。
    """
    p = Path(path) if path else db_path(job_code or "", root=root)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA foreign_keys=ON")
    _migrate(con)
    return con


def _jsonize(v):
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v


def set_job_meta(con: sqlite3.Connection, job_code: str, title: str = "", created_at: str = "") -> None:
    con.execute("INSERT INTO job_meta(job_code,title,created_at) VALUES(?,?,?) "
                "ON CONFLICT(job_code) DO UPDATE SET title=excluded.title, "
                "created_at=CASE WHEN excluded.created_at='' THEN job_meta.created_at ELSE excluded.created_at END",
                (job_code, title or "", created_at or ""))
    con.commit()


# ── 候选人：本岗内去重（主锚点 = source_id；content_hash 只是复核信号）──────────

def upsert_candidate(con: sqlite3.Connection, job_code: str, cand: dict) -> dict:
    """写一个候选人。**同一个人第二次采到 = 更新，不新增**。

    去重口径（v2，2026-09-16 修正）：
      1) (job_code, source_id) 命中 → 更新（只更新本次给了值的字段）+ 刷 last_seen_at
      2) 否则 insert（content_hash 一起写，但**它不再是唯一约束**）
    返回 {"action": created|updated, "id": int, "first_time": bool, "dup_of": id|None}

    ⚠️ v1 那版还有第 3 步"撞 content_hash 就当同一个人（duplicate）"——**已删**：
    实测会把两个 source_id 不同、原文恰好相同的人当成一个、丢掉一行（"丢人"比"多留一行"贵）。
    现在只在插入时**顺手复核**：本岗库里已有同 hash 的**别人**，把 `dup_of` 记进返回值供上层判断，
    **但照样入库**（判断留给③匹配层，本地不替它丢人）。
    """
    sid = str(cand.get("source_id") or "").strip()
    if not sid:
        raise ValueError("upsert_candidate: source_id 必填（它就是本岗的去重锚点）")
    now = _now()
    raw = str(cand.get("raw_content") or "")
    h = content_hash(job_code, raw) if raw.strip() else None

    vals: dict = {}
    for k in CAND_FIELDS:
        if k in cand and cand[k] is not None:
            vals[k] = _jsonize(cand[k])
    vals["content_hash"] = h          # raw 为空 → 写回 NULL（表示"还没抓到全文指纹"）

    row = con.execute("SELECT id FROM candidates WHERE job_code=? AND source_id=?",
                      (job_code, sid)).fetchone()
    if row:
        sets = ", ".join(f"{k}=?" for k in vals)
        con.execute(f"UPDATE candidates SET {sets}, last_seen_at=?, updated_at=? WHERE id=?",
                    (*vals.values(), now, now, row["id"]))
        con.commit()
        return {"action": "updated", "id": row["id"], "first_time": False, "dup_of": None}

    dup_of = None
    if h:
        ex = con.execute("SELECT id FROM candidates WHERE job_code=? AND content_hash=?",
                         (job_code, h)).fetchone()
        if ex:
            dup_of = ex["id"]     # 复核信号：原文与库里某人相同（不同 id）——只记，不合并
    cols = ["job_code", "source_id", "first_seen_at", "last_seen_at", "updated_at", *vals.keys()]
    ph = ",".join("?" for _ in cols)
    cur = con.execute(f"INSERT INTO candidates ({','.join(cols)}) VALUES ({ph})",
                      (job_code, sid, now, now, now, *vals.values()))
    con.commit()
    return {"action": "created", "id": cur.lastrowid, "first_time": True, "dup_of": dup_of,
            **({"note": "库里已有内容相同的人（不同 id）——只做了复核标记，没有合并"} if dup_of else {})}

    cols = ["job_code", "source_id", "first_seen_at", "last_seen_at", "updated_at", *vals.keys()]
    ph = ",".join("?" for _ in cols)
    cur = con.execute(f"INSERT INTO candidates ({','.join(cols)}) VALUES ({ph})",
                      (job_code, sid, now, now, now, *vals.values()))
    con.commit()
    return {"action": "created", "id": cur.lastrowid, "first_time": True, "dup_of": dup_of,
            **({"note": "库里已有内容相同的人（不同 id）——只做了复核标记，没有合并"} if dup_of else {})}


def get_candidate(con: sqlite3.Connection, job_code: str, source_id: str) -> dict | None:
    r = con.execute("SELECT * FROM candidates WHERE job_code=? AND source_id=?",
                    (job_code, source_id)).fetchone()
    return dict(r) if r else None


def list_candidates(con: sqlite3.Connection, job_code: str, min_score: float | None = None,
                    status: str | None = None, only_unmatched: bool = False,
                    limit: int | None = None) -> list[dict]:
    """取候选人（本地粗筛后要送 LLM 的名单就从这来）。only_unmatched=只要没评过的。"""
    sql = "SELECT c.* FROM candidates c"
    args: list = []
    if only_unmatched:
        sql += " LEFT JOIN match_results m ON m.candidate_id=c.id AND m.job_code=c.job_code"
    sql += " WHERE c.job_code=?"
    args.append(job_code)
    if only_unmatched:
        sql += " AND m.id IS NULL"
    if min_score is not None:
        sql += " AND COALESCE(c.local_score,-1) >= ?"
        args.append(min_score)
    if status:
        sql += " AND c.status=?"
        args.append(status)
    sql += " ORDER BY COALESCE(c.local_score,-1) DESC, c.id ASC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in con.execute(sql, args)]


# ── 匹配结果：输入指纹缓存（同输入不重复付费）──────────────────────────────

def save_match(con: sqlite3.Connection, job_code: str, candidate_id: int, result: dict,
               raw_hash: str = "") -> dict:
    """存/更新一条匹配结果（(job_code, candidate_id) 唯一 → 幂等）。

    ⚠️ **只写本次给了值的字段**（与 `upsert_candidate` 同一条纪律）：否则"只更新分数"的调用会把
    `match_points`/`concerns`（**话术原料**）洗成空 —— 2026-09-15 单测当场抓到，已按此修正。
    """
    now = _now()
    alias = {"total_score": ("total_score", "score"),
             "verdict": ("verdict", "decision"),
             "confidence": ("confidence",),
             "score_skill": ("score_skill",), "score_exp": ("score_exp",),
             "score_edu": ("score_edu",), "score_city": ("score_city",),
             "match_points": ("match_points",), "concerns": ("concerns",),
             "summary": ("summary",),
             "detail_json": ("detail", "detail_json"),
             "special_notes_snapshot": ("special_notes", "special_notes_snapshot")}
    f: dict = {}
    for col, keys in alias.items():
        for k in keys:
            if k in result and result[k] is not None:
                f[col] = _jsonize(result[k])
                break
    if raw_hash:
        f["raw_hash"] = raw_hash
    ex = con.execute("SELECT id FROM match_results WHERE job_code=? AND candidate_id=?",
                     (job_code, candidate_id)).fetchone()
    if ex:
        f2 = dict(f, updated_at=now)  # updated_at 一起拼进赋值列表，避免"多一个逗号"这类拼串错误
        sets = ", ".join(f"{k}=?" for k in f2)
        con.execute(f"UPDATE match_results SET {sets} WHERE id=?", (*f2.values(), ex["id"]))
        con.commit()
        return {"action": "updated", "id": ex["id"]}
    cols = ["job_code", "candidate_id", "created_at", "updated_at", *f.keys()]
    cur = con.execute(f"INSERT INTO match_results ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                      (job_code, candidate_id, now, now, *f.values()))
    con.commit()
    return {"action": "created", "id": cur.lastrowid}


def get_cached_match(con: sqlite3.Connection, job_code: str, candidate_id: int,
                     raw_hash: str) -> dict | None:
    """缓存命中判断：**输入指纹没变** → 返回旧结果（别再花钱重评）；变了 → None。"""
    r = con.execute("SELECT * FROM match_results WHERE job_code=? AND candidate_id=?",
                    (job_code, candidate_id)).fetchone()
    if r and raw_hash and (r["raw_hash"] or "") == raw_hash:
        return dict(r)
    return None


# ── 沟通/跟进台账 ──────────────────────────────────────────────────────────

def append_event(con: sqlite3.Connection, candidate_id: int, job_code: str, event_type: str,
                 note: str = "", account: str = "") -> int:
    """记一条沟通事件（只增不改）。返回事件 id。"""
    cur = con.execute("INSERT INTO candidate_events(candidate_id,job_code,event_type,note,account,created_at)"
                      " VALUES(?,?,?,?,?,?)",
                      (candidate_id, job_code, event_type, note or "", account or "", _now()))
    con.commit()
    return cur.lastrowid


def add_pool_sample(con: sqlite3.Connection, raw_text: str, round_tag: str = "") -> int:
    """往"列表页原文临时池"丢一页原文（本地粗筛的原料）。"""
    cur = con.execute("INSERT INTO pool_samples(raw_text,round_tag,collected_at) VALUES(?,?,?)",
                      (raw_text or "", round_tag or "", _now()))
    con.commit()
    return cur.lastrowid


def stats(con: sqlite3.Connection, job_code: str) -> dict:
    """本岗库的一眼账：候选人数 / 留卡数 / 已开详情数 / 已评数 / 事件数。

    ⚠️ 2026-09-16 修正：`kept_by_local` 原先写死"local_score>=60"——那是**旧打分口径**
    （分数=成色，60 是过线）；新口径下没有行业命中的人分数**上限 40**，
    于是这个数**恒为 0**、看着像"一个人都没留下"，是假账。改成按 `status` 数：
    kept（留卡）/ opened（开了详情，有全文）。
    """
    def one(sql, *a):
        return con.execute(sql, a).fetchone()[0]
    return {"candidates": one("SELECT COUNT(*) FROM candidates WHERE job_code=?", job_code),
            "kept": one("SELECT COUNT(*) FROM candidates WHERE job_code=? AND status='kept'", job_code),
            "opened": one("SELECT COUNT(*) FROM candidates WHERE job_code=? AND status='opened'", job_code),
            "with_raw": one("SELECT COUNT(*) FROM candidates WHERE job_code=? AND LENGTH(COALESCE(raw_content,''))>0", job_code),
            "matched": one("SELECT COUNT(*) FROM match_results WHERE job_code=?", job_code),
            "events": one("SELECT COUNT(*) FROM candidate_events WHERE job_code=?", job_code),
            "pool_samples": one("SELECT COUNT(*) FROM pool_samples"),
            "schema_version": con.execute("PRAGMA user_version").fetchone()[0]}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="岗位库小工具（看一眼本岗库的账）")
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--root", default=None, help="岗位根目录（默认 data/chat）")
    args = ap.parse_args()
    p = db_path(args.job_code, root=Path(args.root) if args.root else None)
    print(f"▶ 岗位库：{p}（{'已存在' if p.exists() else '不存在——本次检查不建库'}）")
    if not p.exists():
        return
    con = open_db(args.job_code, root=Path(args.root) if args.root else None)
    print("   ", json.dumps(stats(con, args.job_code), ensure_ascii=False))


if __name__ == "__main__":
    main()
