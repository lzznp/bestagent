#!/usr/bin/env python3
"""合并分批评估报告：part1（含 pool_quality）+ part2（仅候选人）→ 完整报告
用法: python merge_report.py part1.json part2.json ... out.json
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

files = [Path(p) for p in sys.argv[1:-1]]
out = Path(sys.argv[-1])

pool = None
cands: dict[int, dict] = {}
for f in files:
    data = json.loads(f.read_text(encoding="utf-8"))
    if data.get("pool_quality"):
        pool = data["pool_quality"]
    for c in data.get("candidates", []):
        cid = c.get("candidate_id")
        if cid is not None:
            cands[cid] = c
        else:
            cands[len(cands) + 1] = c

ordered = [cands[k] for k in sorted(cands)]
result = {}
if pool:
    result["pool_quality"] = pool
result["candidates"] = ordered
out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"✅ 合并 {len(files)} 个报告 → {out}：pool_quality={'有' if pool else '无'}，candidates={len(ordered)} 条")
