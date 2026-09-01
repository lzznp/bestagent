#!/usr/bin/env python3
"""导入业务库：采集结果 + 评估报告 → SQLite（复用 wails 表设计，决策 11 记忆分层 L1）

表：jobs / candidates / match_results / candidate_events / pool_samples（schema 复制自
参考代码 recruitment-wails/internal/db/db.go）

数据源（采集文件 ↔ 评估报告成对导入，评估的 candidate_id 按采集 rows 顺序映射到 candidates.id）：
  - data/outbox/collected_gpgpu_all.json       ↔ pool_report_gpgpu_all.json       (120 人)
  - data/outbox/collected_gpgpu_skill.json     ↔ pool_report_gpgpu_skill.json     (144 人)
  - data/outbox/collected_gpgpu_haiguang.json  ↔ pool_report_gpgpu_haiguang.json  (29 人)
运行: python import_to_db.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path(r"D:\study\bestagent\bestagent\data\business.db")
ROOT = Path(r"D:\study\bestagent\bestagent")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_code TEXT UNIQUE NOT NULL,
    job_title TEXT,
    link TEXT,
    raw_content TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    job_intro TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    company_name TEXT,
    salary_range TEXT,
    city TEXT,
    pm_notes TEXT,
    special_notes TEXT,
    liepin_job_id VARCHAR(100),
    liepin_job_title VARCHAR(200),
    job_score TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_code TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    content_hash TEXT,
    source_platform TEXT,
    source_url TEXT,
    collected_by TEXT DEFAULT 'manual',
    display_name TEXT,
    display_company TEXT,
    display_position TEXT,
    status TEXT DEFAULT 'collected',
    notes TEXT,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_id VARCHAR(200),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    contact_status TEXT DEFAULT '未联系',
    structured TEXT,
    collected_account TEXT,
    active_badge TEXT,
    FOREIGN KEY (job_code) REFERENCES jobs(job_code)
);
CREATE TABLE IF NOT EXISTS match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_code TEXT NOT NULL,
    candidate_id INTEGER NOT NULL,
    total_score INTEGER,
    verdict TEXT,
    confidence TEXT,
    score_skill REAL, score_exp REAL, score_edu REAL, score_city REAL,
    detail_json TEXT,
    special_notes_snapshot TEXT,
    raw_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_code, candidate_id)
);
CREATE TABLE IF NOT EXISTS candidate_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    job_code TEXT NOT NULL,
    event_type TEXT NOT NULL,
    note TEXT,
    account TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pool_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_candidates_job_code ON candidates(job_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_candidate ON candidates(job_code, content_hash);
CREATE INDEX IF NOT EXISTS idx_match_results_job ON match_results(job_code);
CREATE INDEX IF NOT EXISTS idx_candidate_events_candidate ON candidate_events(candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidate_events_job ON candidate_events(job_code);
"""

JOB_CODE = "J20260407081446102058"  # GPGPU 软件高级架构师（禾蛙职位编号）
JOB = {
    "job_code": JOB_CODE,
    "job_title": "GPGPU 软件高级架构师",
    "link": "https://hewa.cn/jobDetails.html?job_id=jQoxjWweVKYQLP9yRQERrA_hw2_",
    "company_name": "中国航天科技集团有限公司",
    "salary_range": "60-150万（14薪）",
    "city": "北京",
    "status": "active",
}

PAIRS = [
    ("data/outbox/collected_gpgpu_all.json", "data/outbox/pool_report_gpgpu_all.json"),
    ("data/outbox/collected_gpgpu_skill.json", "data/outbox/pool_report_gpgpu_skill.json"),
    ("data/outbox/collected_gpgpu_haiguang.json", "data/outbox/pool_report_gpgpu_haiguang.json"),
]

NAME_RE = re.compile(r"([\u4e00-\u9fa5]{1,3})\*\*")


def name_of(text: str) -> str:
    m = NAME_RE.search(text)
    return (m.group(1) + "**") if m else ""


def main() -> None:
    con = sqlite3.connect(str(DB))
    con.executescript(SCHEMA)
    cur = con.cursor()

    # 1) jobs
    jd_file = ROOT / "data" / "inbox" / "jd_1.txt"
    raw = jd_file.read_text(encoding="utf-8") if jd_file.exists() else ""
    job_score = ""
    rep = ROOT / "data" / "outbox" / "report_jd_1.json"
    if rep.exists():
        try:
            d = json.loads(rep.read_text(encoding="utf-8-sig"))
            s = d.get("score", {})
            job_score = f"total={s.get('total')} level={s.get('level')} recommendation={d.get('recommendation')}"
        except Exception:
            pass
    cur.execute(
        """INSERT OR IGNORE INTO jobs
           (job_code, job_title, link, raw_content, status, company_name, salary_range, city, job_score)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (JOB["job_code"], JOB["job_title"], JOB["link"], raw, JOB["status"],
         JOB["company_name"], JOB["salary_range"], JOB["city"], job_score),
    )

    n_cand = n_match = 0
    for collect_rel, report_rel in PAIRS:
        collect_path = ROOT / collect_rel
        report_path = ROOT / report_rel
        if not collect_path.exists():
            print(f"⚠ 跳过（无采集文件）: {collect_rel}")
            continue
        collect = json.loads(collect_path.read_text(encoding="utf-8-sig"))
        rows = collect.get("rows", [])
        report = {}
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        eval_by_idx = {}
        for c in report.get("candidates", []):
            eval_by_idx[c.get("candidate_id")] = c

        print(f"▶ {collect_rel}: {len(rows)} 条")
        idx_to_cid = {}
        for i, row in enumerate(rows, start=1):
            text = row.get("text") or row.get("raw_text") or ""
            sid = (row.get("fields") or {}).get("res_id_encode") or row.get("source_id") or ""
            url = row.get("url") or ""
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
            cur.execute(
                """INSERT OR IGNORE INTO candidates
                   (job_code, raw_content, content_hash, source_platform, source_url,
                    collected_by, display_name, source_id, active_badge)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (JOB_CODE, text, h, "liepin", url, "collect_liepin", name_of(text), sid,
                 "在线" if "在线" in text else None),
            )
            if cur.rowcount:
                n_cand += 1
                cid = cur.lastrowid
            else:
                cur.execute("SELECT id FROM candidates WHERE job_code=? AND content_hash=?", (JOB_CODE, h))
                cid = cur.fetchone()[0]
            idx_to_cid[i] = cid

        for i, c in eval_by_idx.items():
            cid = idx_to_cid.get(i)
            if cid is None:
                continue
            detail = json.dumps(
                {"match_points": c.get("match_points", []), "concerns": c.get("concerns", []),
                 "summary": c.get("summary", "")},
                ensure_ascii=False,
            )
            cur.execute(
                """INSERT OR REPLACE INTO match_results
                   (job_code, candidate_id, total_score, verdict, detail_json)
                   VALUES (?,?,?,?,?)""",
                (JOB_CODE, cid, c.get("score"), c.get("verdict"), detail),
            )
            n_match += 1

    con.commit()
    print("─" * 50)
    for t in ("jobs", "candidates", "match_results", "candidate_events"):
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n}")
    print(f"✅ 本次新增候选人 {n_cand}，匹配结果 {n_match}")
    print(f"✅ 业务库: {DB}")
    con.close()


if __name__ == "__main__":
    main()
