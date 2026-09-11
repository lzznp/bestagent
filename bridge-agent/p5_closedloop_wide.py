#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对照实验：只设宽条件（keyword+青岛+3-5年+大专），去掉 job_title/company/salary，验证业务层该拦哪些条件。"""
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from agent.core import submit_task
from agent.recipe_exec import execute_spec, COND_URL

BRIDGE = "http://127.0.0.1:8080"
TAB = int(sys.argv[1]) if len(sys.argv) > 1 else 1890028597

spec = [
    {"group_id": "keyword", "value": "嵌入式"},
    {"group_id": "city_current", "value": "青岛"},
    {"group_id": "city_expected", "value": "青岛"},
    {"group_id": "years", "value": "3-5年"},
    {"group_id": "education", "value": "大专"},
]

print("=== 先清空 ===")
r = submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="wide")
print("navigate:", r.get("ok"))
time.sleep(2.5)
# 先点清空筛选条件重置
r = submit_task(BRIDGE, "click_by_text", {"tab_id": TAB, "text": "清空筛选条件", "occurrence": 1}, source="wide")
print("clear:", r.get("ok"), r.get("error") or "")
time.sleep(2.0)

print("\n=== 宽条件 spec ===")
print(json.dumps(spec, ensure_ascii=False, indent=1))
res = execute_spec(spec, TAB)
print(json.dumps(res, ensure_ascii=False, indent=1)[:3000])
