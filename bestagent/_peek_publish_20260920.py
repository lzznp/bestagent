#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_peek_publish_20260920.py — 看我们自己的"发岗助手"产物长什么样（只读）"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(__file__).resolve().parent
JC = "J-CHAT-20260909-094907"
reps = BASE / "data" / "chat" / JC / "reports"
print("reports dir exists:", reps.exists())
files = sorted(reps.glob("publish_*")) + sorted(reps.glob("发岗*"))
print("产物:", [p.name for p in files])
for p in files:
    print("=" * 70)
    print(p.name, p.stat().st_size, "字节")
    if p.suffix == ".json":
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        for k, v in d.items():
            s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            print(f"  {k} = {s[:200]}")

# 我们库里有没有"发布/猎聘岗位号/禾蛙"的痕迹
import job_db  # noqa: E402
con = job_db.open_db(JC)
print("=" * 70)
print("job_meta:", dict(con.execute("SELECT * FROM job_meta").fetchone() or {}))
cols = [r[1] for r in con.execute("PRAGMA table_info(candidates)")]
print("candidates 列:", cols)
keys: set = set()
for r in con.execute("SELECT structured FROM candidates WHERE job_code=?", (JC,)):
    try:
        keys |= set(json.loads(r["structured"] or "{}").keys())
    except Exception:  # noqa: BLE001
        pass
print("card structured 里的字段:", sorted(keys))
con.close()

# 全项目里"发布/禾蛙/猎聘岗位号"的痕迹
import re
hits = []
for p in sorted(BASE.glob("*.py")):
    if p.name.startswith(("_", "test_")):
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    for kw in ("禾蛙", "liepin_job_id", "猎聘岗位号", "发布到猎聘", "发岗"):
        n = len(re.findall(kw, t))
        if n:
            hits.append((p.name, kw, n))
print("=" * 70)
print("主脚本里相关词命中：")
for h in hits:
    print("  ", h)
