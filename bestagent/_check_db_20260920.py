#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_check_db_20260920.py — 只读复核：reply_run 的两次只读跑**有没有动过库**

判据：台账事件数/类型、`detail_json` 里有没有 chat_* 字段、报告目录最新一份的时间。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import job_db  # noqa: E402

JC = "J-CHAT-20260909-094907"
con = job_db.open_db(JC)
rows = [tuple(r) for r in con.execute(
    "SELECT event_type, COUNT(*) FROM candidate_events WHERE job_code=? GROUP BY event_type", (JC,))]
keys: set = set()
for r in con.execute("SELECT detail_json FROM match_results WHERE job_code=?", (JC,)):
    try:
        keys |= set(json.loads(r["detail_json"] or "{}").keys())
    except Exception:  # noqa: BLE001
        pass
total = con.execute("SELECT COUNT(*) FROM candidate_events WHERE job_code=?", (JC,)).fetchone()[0]
con.close()
print("台账事件：", rows, "｜总计", total)
print("detail_json 里的 chat_* 字段：", sorted(k for k in keys if k.startswith("chat_")))
print("（应为空 = 只读跑没写库）")
reps = sorted((Path(__file__).resolve().parent / "data" / "chat" / JC / "reports").glob("打招呼报告_*.json"),
              key=os.path.getmtime)
if reps:
    print("最新报告：", reps[-1].name, "｜",
          datetime.fromtimestamp(os.path.getmtime(reps[-1])).strftime("%Y-%m-%d %H:%M:%S"))
