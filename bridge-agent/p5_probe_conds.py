#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_probe_conds.py — 找简历条件页未知控件实测探针

对快照里"看不见文本/形态不明"的控件逐个点击，看它展开什么、元素怎么变。
每个探针前 navigate 干净页重置状态。结果落盘 logs/_probe_conds/<name>.json。

用法：python p5_probe_conds.py [probe_name ...]（缺省跑全部）
"""
import argparse
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

OUT_DIR = "logs/_probe_conds"
os.makedirs(OUT_DIR, exist_ok=True)

# 探针定义：点击哪个编号（当前干净页 141 元素快照），然后看什么
PROBES = {
    # 工作年限 chip（拆节点"3-5"）——点了看有没有选中态信号
    "chip_35": {"index": 58, "desc": "工作年限 chip '3-5'（em 拆节点）"},
    # 活跃度下拉（combobox）
    "activity": {"index": 82, "desc": "活跃度 combobox"},
    # 统招要求（68-70 空 div）
    "tongzhao": {"index": 69, "desc": "统招要求区域（空 div 69）"},
    # 当前行业（76-79 div + input80）
    "industry": {"index": 80, "desc": "当前行业 combo input 80"},
    # 性别（span90 不限）
    "gender": {"index": 90, "desc": "性别 span 90"},
    # 跳槽频率（93-95 spans）
    "jobhop": {"index": 93, "desc": "跳槽频率 span 93"},
    # 展开更多条件
    "expand": {"index": 92, "desc": "展开更多条件 span 92"},
    # 求职状态（span133）
    "jobstatus": {"index": 133, "desc": "求职状态（不限）span 133"},
}


def snap(tag):
    r = submit_task(BRIDGE, "snapshot", {"tab_id": TAB}, source="p5-probe-conds")
    res = r.get("result") or {}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("probes", nargs="*", default=list(PROBES))
    args = ap.parse_args()

    for name in args.probes:
        if name not in PROBES:
            print(f"未知探针: {name}；可选: {list(PROBES)}")
            continue
        p = PROBES[name]
        print(f"\n===== 探针 [{name}] {p['desc']} =====")
        try:
            submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="p5-probe-conds")
            time.sleep(2.5)
            s0 = snap("before")
            n0 = len(s0.get("elements") or [])
            r = submit_task(BRIDGE, "click", {"tab_id": TAB, "index": p["index"]}, source="p5-probe-conds")
            print(f"  click@{p['index']} ok={r.get('ok')} {json.dumps(r.get('result'), ensure_ascii=False)[:150]}")
            time.sleep(1.8)
            s1 = snap("after")
            elems = s1.get("elements") or []
            n1 = len(elems)
            # 新增元素（编号>=原范围的或有名的）
            named_new = [{"index": e.get("index"), "tag": e.get("tag"), "name": (e.get("name") or "")[:40],
                          "value": (e.get("value") or "")[:15]} for e in elems if e.get("name")]
            out = {"probe": name, "desc": p["desc"], "click_index": p["index"],
                   "n_before": n0, "n_after": n1, "url": s1.get("url"),
                   "body_tail": (s1.get("body_preview") or "")[-800:],
                   "named_new_tail": named_new[-25:]}
            with open(os.path.join(OUT_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
            print(f"  元素 {n0} -> {n1}，结果落盘 {name}.json")
        except Exception as e:
            print(f"  探针异常: {e}")
        time.sleep(1.0)


if __name__ == "__main__":
    main()
