#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_cond_probe5.py — occurrence 映射（body 文本对比版）

每个 occurrence 点击后，对比 body_preview 新增内容，用特征词识别打开了哪个下拉。
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
OUT_DIR = "logs/_probe_conds5"
os.makedirs(OUT_DIR, exist_ok=True)

MARKERS = [
    ("活跃度", ["今日活跃", "近3天活跃", "近7天活跃", "近30天活跃"]),
    ("性别", ["男", "女"]),
    ("跳槽频率", ["频繁跳槽", "偶尔跳槽", "较稳定"]),
    ("统招", ["统招本科", "统招硕士", "统招博士", "统招大专"]),
    ("求职状态", ["离职，正在找工作", "在职，急寻新工作"]),
    ("当前行业", ["互联网", "计算机软件", "电子/半导体"]),
    ("当前职位", ["总经理", "总监", "工程师"]),
    ("语言", ["普通话", "英语", "日语"]),
]


def nav_clean():
    submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="p5-probe5")
    time.sleep(2.5)


def snap():
    r = submit_task(BRIDGE, "snapshot", {"tab_id": TAB}, source="p5-probe5")
    return r.get("result") or {}


def cbt(text, occ):
    return submit_task(BRIDGE, "click_by_text", {"tab_id": TAB, "text": text, "occurrence": occ}, source="p5-probe5")


def probe(text, occ):
    nav_clean()
    s0 = snap()
    b0 = s0.get("body_preview") or ""
    r = cbt(text, occ)
    time.sleep(1.8)
    s1 = snap()
    b1 = s1.get("body_preview") or ""
    # 找出新增文本（粗略：用特征词直接查 b1，且 b0 中不出现的特征词）
    hit_markers = []
    new_tail = ""
    for name, kws in MARKERS:
        present_in_b1 = [k for k in kws if k in b1]
        present_in_b0 = [k for k in kws if k in b0]
        newly = [k for k in present_in_b1 if k not in present_in_b0]
        if newly:
            hit_markers.append({"control": name, "new_kws": newly, "all_present": present_in_b1})
    # 找 body 里 dropdown 特有部分：统招选项/求职状态选项等出现位置附近
    for marker in ["统招本科", "今日活跃", "离职，正在找工作", "频繁跳槽"]:
        if marker in b1:
            i = b1.find(marker)
            new_tail += f"...[{marker}附近]...{b1[max(0,i-120):i+200]}...\n"
    return {"text": text, "occ": occ, "click_ok": r.get("ok"),
            "clicked": (r.get("result") or {}).get("clicked"),
            "n": len(s1.get("elements") or []), "hit_markers": hit_markers,
            "dropdown_tail": new_tail[:600]}


def main():
    results = []
    for occ in range(5, 13):
        res = probe("不限", occ)
        print(f"不限 occ={occ}: hits={[h['control'] for h in res['hit_markers']]} clicked={res['clicked']}")
        results.append(res)
    for occ in range(1, 4):
        res = probe("（不限）", occ)
        print(f"（不限） occ={occ}: hits={[h['control'] for h in res['hit_markers']]} clicked={res['clicked']}")
        results.append(res)
    with open(os.path.join(OUT_DIR, "map.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("落盘 logs/_probe_conds5/map.json")


if __name__ == "__main__":
    main()
