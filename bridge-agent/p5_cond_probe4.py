#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_cond_probe4.py — 下拉控件 occurrence 映射探针

Ant Design Select 展开方式 = 点可见文本 span（mousedown 冒泡到 selector）。
本探针：逐个点 '不限' 的 occurrence 5..12，记录每个打开的是什么下拉（按出现的选项特征词识别）。
另测 '（不限）' occurrence 1..3（跳槽频率/简历语言等）。
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
OUT_DIR = "logs/_probe_conds4"
os.makedirs(OUT_DIR, exist_ok=True)

# 各下拉的"特征词"（选项里出现即判定为该控件）
MARKERS = {
    "活跃度": ["今日活跃", "近3天", "近7天", "近15天", "近30天"],
    "性别": ["男", "女"],
    "跳槽频率": ["频繁跳槽", "偶尔跳槽", "稳定"],
    "当前行业": ["互联网", "计算机软件", "电子"],
    "当前职位": ["技术", "产品", "运营"],
    "期望行业": ["不限"],
    "期望职位": ["不限"],
    "语言": ["普通话", "英语"],
    "统招": ["统招本科", "统招硕士"],
    "求职状态": ["离职，正在找工作", "在职，急寻新工作"],
}


def nav_clean():
    submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="p5-probe4")
    time.sleep(2.5)


def snap():
    r = submit_task(BRIDGE, "snapshot", {"tab_id": TAB}, source="p5-probe4")
    return r.get("result") or {}


def cbt(text, occ):
    return submit_task(BRIDGE, "click_by_text", {"tab_id": TAB, "text": text, "occurrence": occ}, source="p5-probe4")


def probe_occ(text, occ):
    nav_clean()
    s0 = snap()
    names0 = {e.get("name") for e in (s0.get("elements") or [])}
    r = cbt(text, occ)
    time.sleep(1.8)
    s1 = snap()
    names1 = {e.get("name") for e in (s1.get("elements") or [])}
    new_names = [n for n in names1 if n and n not in names0]
    # 判定控件
    hits = [k for k, m in MARKERS.items() if any(x in "|".join(new_names) for x in m)]
    return {
        "text": text, "occ": occ,
        "click": {"ok": r.get("ok"), "result": r.get("result")},
        "n": len(s1.get("elements") or []),
        "new_named": new_names[:40],
        "matched_control": hits,
    }


def main():
    results = []
    print("== 探针 1：'不限' occurrence 5..12 映射 ==")
    for occ in range(5, 13):
        res = probe_occ("不限", occ)
        print(f"  不限 occ={occ}: matched={res['matched_control']} new={len(res['new_named'])}")
        results.append(res)
    print("\n== 探针 2：'（不限）' occurrence 1..3 ==")
    for occ in range(1, 4):
        res = probe_occ("（不限）", occ)
        print(f"  （不限） occ={occ}: matched={res['matched_control']} new={len(res['new_named'])}")
        results.append(res)
    with open(os.path.join(OUT_DIR, "map.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("\n结果落盘 logs/_probe_conds4/map.json")


if __name__ == "__main__":
    main()
