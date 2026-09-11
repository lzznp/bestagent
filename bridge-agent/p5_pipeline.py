#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_pipeline.py — JD → 候选人 完整闭环（LLM 决策 + 配方执行）

用法：python p5_pipeline.py [jd文件，默认 logs/jd_goertek.txt]
"""
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.core import submit_task
from agent.jd_to_spec import jd_to_spec
from agent.recipe_exec import execute_spec, COND_URL

BRIDGE = "http://127.0.0.1:8080"
TAB = 1890028341


def main():
    jd_path = sys.argv[1] if len(sys.argv) > 1 else "logs/jd_goertek.txt"
    with open(jd_path, encoding="utf-8") as f:
        jd = f.read()

    print("=== 1. LLM 决策：JD → 条件规格 ===")
    r = jd_to_spec(jd)
    if not r.get("ok"):
        print("❌", r.get("error"))
        return
    spec = r["spec"]
    print("LLM 输出规格:", json.dumps(spec, ensure_ascii=False))

    print("\n=== 2. 配方执行：设置条件 + 搜索 + 提取 ===")
    submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="pipeline")
    time.sleep(2.5)
    res = execute_spec(spec, TAB)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:3000])

    print("\n=== 3. 结果 ===")
    if res.get("ok"):
        print(f"✅ 闭环完成：{len(spec)} 个条件 → 候选人 {res.get('candidates')} 位（去重 {res.get('dedup')}）")
    else:
        print(f"❌ 失败于: {res.get('failed')} - {res.get('error')}")


if __name__ == "__main__":
    main()
