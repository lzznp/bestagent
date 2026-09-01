#!/usr/bin/env python3
"""合并多个采集 JSON（按 res_id_encode 去重）→ 输出合并文件
用法: python merge_collect.py in1.json in2.json ... out.json
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

files = [Path(p) for p in sys.argv[1:-1]]
out = Path(sys.argv[-1])
all_rows, seen = [], set()
for f in files:
    data = json.loads(f.read_text(encoding="utf-8"))
    n = 0
    for row in data.get("rows", []):
        sid = (row.get("fields") or {}).get("res_id_encode") or row.get("source_id")
        key = sid or (row.get("text") or "")[:50]
        if key not in seen:
            seen.add(key)
            all_rows.append(row)
            n += 1
    print(f"  {f.name}: 新增 {n}")
out.write_text(
    json.dumps({"count": len(all_rows), "rows": all_rows}, ensure_ascii=False, indent=1),
    encoding="utf-8",
)
print(f"✅ 合并 {len(files)} 个文件 → {out}：{len(all_rows)} 条")
