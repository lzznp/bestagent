#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""p5_closedloop_run.py — 临时脚本：JD → spec → execute_spec → 提取 全链路验证。
导航到找简历页，设置条件，搜索，提取候选人。用 UTF-8 输出。"""
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from agent.core import submit_task
from agent.jd_to_spec import jd_to_spec
from agent.recipe_exec import execute_spec, load_recipes, COND_URL

BRIDGE = "http://127.0.0.1:8080"
TAB = int(sys.argv[1]) if len(sys.argv) > 1 else 1890028597

jd = open("logs/jd_goertek.txt", encoding="utf-8").read()
spec_res = jd_to_spec(jd)
if not spec_res.get("ok"):
    print(json.dumps(spec_res, ensure_ascii=False, indent=1))
    sys.exit(1)
spec = spec_res["spec"]
print("=== LLM 生成的 spec ===")
print(json.dumps(spec, ensure_ascii=False, indent=1))

print(f"\n=== 导航到条件页 tab={TAB} ===")
r = submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="closedloop")
print("navigate:", r.get("ok"), r.get("error") or "")
time.sleep(2.5)

print("\n=== execute_spec 执行 ===")
res = execute_spec(spec, TAB)
print(json.dumps(res, ensure_ascii=False, indent=1)[:3000])
