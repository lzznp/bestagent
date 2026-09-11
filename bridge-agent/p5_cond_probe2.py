#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_cond_probe2.py — 找简历条件页探针 v2（文本定位，不依赖编号）

A/B: 工作年限 chip 点击行为（是否触发搜索、条件是否选中）
C: 统招要求 点击行为
D: 截图 + 视觉问答：未知控件形态（统招/活跃度/当前行业/性别/跳槽/展开更多）
"""
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.core import submit_task

BRIDGE = "http://127.0.0.1:8080"
TAB = 1890028341
COND_URL = "https://h.liepin.com/search/getConditionItem"
OUT_DIR = "logs/_probe_conds2"
os.makedirs(OUT_DIR, exist_ok=True)


def nav_clean():
    submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="p5-probe2")
    time.sleep(2.5)


def snap(tag):
    r = submit_task(BRIDGE, "snapshot", {"tab_id": TAB}, source="p5-probe2")
    return r.get("result") or {}


def cbt(text, occ=1):
    r = submit_task(BRIDGE, "click_by_text", {"tab_id": TAB, "text": text, "occurrence": occ}, source="p5-probe2")
    return r


def save(name, out):
    with open(os.path.join(OUT_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"  -> {name}.json 落盘")


def probe_chip(name, text, occ=1):
    print(f"\n===== [{name}] click_by_text '{text}' occ={occ} =====")
    nav_clean()
    s0 = snap("before")
    n0 = len(s0.get("elements") or [])
    r = cbt(text, occ)
    print(f"  click ok={r.get('ok')} {json.dumps(r.get('result'), ensure_ascii=False)[:160]}")
    time.sleep(2.5)
    s1 = snap("after")
    n1 = len(s1.get("elements") or [])
    bp = s1.get("body_preview") or ""
    # 是否进入结果页：URL #session + 出现 立即沟通
    has_results = "#session" in (s1.get("url") or "") and "立即沟通" in bp
    # 条件区是否保留（找 工作年限 行）
    cond_area = "工作年限" in bp
    save(name, {"click_text": text, "occ": occ, "n_before": n0, "n_after": n1,
                "url": s1.get("url"), "has_results": has_results, "cond_area": cond_area,
                "body_head": bp[:600], "body_tail": bp[-500:]})


def probe_tongzhao():
    print("\n===== [tongzhao] click_by_text '统招' =====")
    nav_clean()
    s0 = snap("before")
    n0 = len(s0.get("elements") or [])
    # 先看统招区域有什么可点文本
    r = cbt("统招", 1)
    print(f"  click ok={r.get('ok')} {json.dumps(r.get('result'), ensure_ascii=False)[:160]}")
    time.sleep(2.0)
    s1 = snap("after")
    n1 = len(s1.get("elements") or [])
    save("tongzhao", {"n_before": n0, "n_after": n1, "url": s1.get("url"),
                      "click_result": r.get("result"), "body_tail": (s1.get("body_preview") or "")[-600:]})


def probe_vision():
    print("\n===== [vision] 截图 + 视觉问答：未知控件形态 =====")
    nav_clean()
    time.sleep(1.5)
    r = submit_task(BRIDGE, "screenshot", {"tab_id": TAB}, source="p5-probe2")
    res = r.get("result") or {}
    print(f"  screenshot ok={r.get('ok')} path={res.get('path_rel')}")
    if not r.get("ok"):
        save("vision", {"error": r.get("error")})
        return
    try:
        from agent.vision import vision_chat
        q = ("这是猎聘'找简历'候选人搜索条件页。请聚焦筛选条件区域，回答："
             "1) '统招要求'控件是什么形态（标签/下拉/开关）？显示什么文字？"
             "2) '活跃度'控件是什么形态？当前显示什么？"
             "3) '当前行业'和'当前职位'是什么形态（输入框/下拉）？"
             "4) '性别'选项有哪些？"
             "5) '跳槽频率'显示什么？有哪些选项？"
             "6) '展开更多条件'区域是否已展开？展开后有哪些条件组？")
        ans = vision_chat(res.get("path") or res.get("path_rel"), q)
        save("vision", {"question": q, "answer": ans})
    except Exception as e:
        import traceback
        save("vision", {"error": str(e), "trace": traceback.format_exc()})


def main():
    probe_chip("chip_35", "3-5", 1)
    probe_chip("chip_5_10", "5-10", 1)
    probe_tongzhao()
    probe_vision()
    print("\n全部探针完成")


if __name__ == "__main__":
    main()
