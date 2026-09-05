#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""import_chat_job.py — 面板岗位入库：data/chat/<job_code>/ 产物 → business.db

复用 import_to_db.write_to_db（candidates 按 job_code+content_hash 去重、match_results
按 UNIQUE(job_code,candidate_id) 幂等），另对 jobs 行做 UPSERT 刷新（支持先"①决定做单入库"、
跑完②③再入库刷新岗位字段/评分）。

用法：
  python import_chat_job.py --job-code J-CHAT-20260904-154300           # 真导入
  python import_chat_job.py --job-code J-CHAT-20260904-154300 --dry-run # 只看计划
  python import_chat_job.py --job-code ... --db <临时.db>                # 导入到指定库（自测用）

面板侧栏「入库当前岗」按钮 = import_job(job_code) 的调用入口（幂等，可重复点）。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from framework_config import WORKSPACE, DB_PATH
from import_to_db import write_to_db, SCHEMA

CHAT_DIR = WORKSPACE / "data" / "chat"


def _latest(reports_dir: Path, prefix: str, suffix: str = ".json") -> Path | None:
    if not reports_dir.is_dir():
        return None
    cands = [p for p in reports_dir.glob(prefix + "*" + suffix) if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def job_plan(job_code: str) -> dict:
    """盘点岗位目录现状（不写库）：有哪些产物可入库。"""
    d = CHAT_DIR / job_code
    if not d.is_dir():
        raise FileNotFoundError(f"岗位目录不存在: {d}")
    reports = d / "reports"
    jd = d / "jd.txt"
    meta = {}
    mp = d / "meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    analyze = _latest(reports, "analyze_")
    collected = _latest(reports, "collected_")
    pool = _latest(reports, "pool_report_")
    aj = {}
    if analyze:
        try:
            aj = json.loads(analyze.read_text(encoding="utf-8-sig"))
        except Exception:
            aj = {}
    ext = aj.get("jd_extracted") or {}
    score = aj.get("score") or {}
    job = {
        "job_code": job_code,
        "job_title": ext.get("job_title") or meta.get("title") or f"岗位 {job_code}",
        "link": meta.get("link") or "",
        "company_name": ext.get("company") or "",
        "salary_range": ext.get("salary") or "",
        "city": ext.get("city") or "",
        "status": "active",
    }
    job_score = ""
    if score.get("total") is not None:
        job_score = (f"total={score.get('total')} level={score.get('level')} "
                     f"recommendation={aj.get('recommendation')}")
    return {
        "job_code": job_code, "dir": d, "jd": jd, "analyze": analyze,
        "collected": collected, "pool": pool, "job": job, "job_score": job_score,
        "analyze_data": aj,
    }


def _job_counts(db: Path, job_code: str) -> tuple[int, int]:
    """该岗在库里的 候选人/评估 计数（库不存在或表未建则 0）。"""
    if not Path(db).exists():
        return 0, 0
    try:
        con = sqlite3.connect(str(db))
        c = con.execute("SELECT COUNT(*) FROM candidates WHERE job_code=?", (job_code,)).fetchone()[0]
        m = con.execute("SELECT COUNT(*) FROM match_results WHERE job_code=?", (job_code,)).fetchone()[0]
        con.close()
        return c, m
    except sqlite3.Error:
        return 0, 0


def import_job(job_code: str, db_path: Path | None = None, dry_run: bool = False) -> dict:
    """把岗位目录产物写入业务库（幂等）。返回摘要 dict（candidates/matches=本次净新增）。"""
    db = Path(db_path) if db_path else DB_PATH
    plan = job_plan(job_code)
    d, jd, analyze, collected, pool = (plan["dir"], plan["jd"], plan["analyze"],
                                       plan["collected"], plan["pool"])
    n_col = 0
    if collected:
        try:
            n_col = len(json.loads(collected.read_text(encoding="utf-8-sig")).get("rows", []))
        except Exception:
            n_col = -1  # 读不出按行数未知处理
    summary = {
        "job_code": job_code,
        "job_title": plan["job"]["job_title"],
        "has_analyze": analyze is not None,
        "has_collected": collected is not None,
        "collected_rows": n_col,
        "has_pool": pool is not None,
        "db": str(db),
        "candidates": 0, "matches": 0, "dry_run": dry_run,
    }
    if dry_run:
        print(f"[dry-run] 岗位 {job_code}（{summary['job_title']}）→ 库 {db}")
        print(f"  analyze={summary['has_analyze']} collected={summary['has_collected']}"
              f"({n_col} 行) pool={summary['has_pool']}")
        return summary

    before_c, before_m = _job_counts(db, job_code)
    pairs: list[tuple[str, str]] = []
    if collected:
        report_path = pool if pool else collected.with_name("__no_pool_report__.json")
        pairs.append((str(collected), str(report_path)))

    write_to_db(plan["job"], jd, pairs, db_path=db, analyze_report=analyze)

    # jobs 行 UPSERT 刷新（write_to_db 只 INSERT OR IGNORE，这里补更新，保证二次入库字段最新）
    raw = jd.read_text(encoding="utf-8") if jd.exists() else ""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA)
    con.execute(
        """INSERT INTO jobs (job_code, job_title, link, raw_content, status,
                            company_name, salary_range, city, job_score)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(job_code) DO UPDATE SET
             job_title=excluded.job_title, link=excluded.link, raw_content=excluded.raw_content,
             company_name=excluded.company_name, salary_range=excluded.salary_range,
             city=excluded.city, job_score=excluded.job_score, updated_at=CURRENT_TIMESTAMP""",
        (job_code, plan["job"]["job_title"], plan["job"]["link"], raw,
         plan["job"]["status"], plan["job"]["company_name"], plan["job"]["salary_range"],
         plan["job"]["city"], plan["job_score"]),
    )
    con.commit()
    counts = {}
    for t in ("jobs", "candidates", "match_results", "candidate_events"):
        counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    con.close()
    after_c, after_m = _job_counts(db, job_code)
    summary["candidates"], summary["matches"] = after_c - before_c, after_m - before_m
    summary["counts"] = counts
    print(f"✅ 入库完成 {job_code}: 本次净新增 候选人 {summary['candidates']}，评估 {summary['matches']} → {db}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="面板岗位产物入库（幂等）")
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--db", type=Path, default=None, help="目标库（默认 business.db）")
    ap.add_argument("--dry-run", action="store_true", help="只看计划不写库")
    args = ap.parse_args()
    s = import_job(args.job_code, db_path=args.db, dry_run=args.dry_run)
    if args.dry_run:
        print(f"[dry-run] 若执行将写入岗位行 + 候选人/评估（幂等）")
    else:
        print(f"  库内计数: { {k: s.get('counts', {}).get(k) for k in ('jobs','candidates','match_results')} }")


if __name__ == "__main__":
    main()
