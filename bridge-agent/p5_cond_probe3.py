#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_cond_probe3.py — 找简历页探针 v3（扩展已加 mousedown 真实事件序列后）

重测 pending 下拉控件 + 即点即搜过滤验证。
每个探针：navigate 干净 → 目标操作 → 等待 → 快照/截图 → 记录。
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
OUT_DIR = "logs/_probe_conds3"
os.makedirs(OUT_DIR, exist_ok=True)


def nav_clean():
    submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="p5-probe3")
    time.sleep(2.5)


def snap():
    r = submit_task(BRIDGE, "snapshot", {"tab_id": TAB}, source="p5-probe3")
    return r.get("result") or {}


def cbt(text, occ=1):
    r = submit_task(BRIDGE, "click_by_text", {"tab_id": TAB, "text": text, "occurrence": occ}, source="p5-probe3")
    return r


def click_idx(idx):
    return submit_task(BRIDGE, "click", {"tab_id": TAB, "index": idx}, source="p5-probe3")


def save(name, out):
    with open(os.path.join(OUT_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"  -> {name}.json 落盘")


def probe_dropdown(name, desc, clicker, wait=2.0, tail_len=700):
    print(f"\n===== [{name}] {desc} =====")
    nav_clean()
    s0 = snap()
    n0 = len(s0.get("elements") or [])
    r = clicker()
    print(f"  click ok={r.get('ok')} {json.dumps(r.get('result'), ensure_ascii=False)[:150]}")
    time.sleep(wait)
    s1 = snap()
    n1 = len(s1.get("elements") or [])
    # 找新增的有名元素（下拉选项）
    names0 = {e.get("name") for e in (s0.get("elements") or [])}
    new_named = [{"index": e.get("index"), "tag": e.get("tag"), "name": (e.get("name") or "")[:40]}
                 for e in (s1.get("elements") or []) if e.get("name") and e.get("name") not in names0]
    save(name, {"desc": desc, "n_before": n0, "n_after": n1, "url": s1.get("url"),
                "click_result": r.get("result"), "new_named": new_named[:30],
                "body_tail": (s1.get("body_preview") or "")[-tail_len:]})


def probe_years_filter():
    print("\n===== [years_filter] 即点即搜后结果是否按 3-5年 过滤（等 8 秒） =====")
    nav_clean()
    r = cbt("3-5", 1)
    print(f"  click ok={r.get('ok')}")
    time.sleep(8.0)
    s1 = snap()
    bp = s1.get("body_preview") or ""
    # 提取候选人经验样本（工作N年）
    import re
    samples = re.findall(r"工作(\d+)年", bp)[:10]
    save("years_filter", {"url": s1.get("url"), "has_results": "#session" in (s1.get("url") or ""),
                          "exp_samples": samples, "selected_tag": "3-5年" in bp,
                          "body_mid": bp[-1500:]})


def probe_chip_click(name, text, wait=5.0):
    print(f"\n===== [{name}] chip '{text}' 是否即点即搜 =====")
    nav_clean()
    s0 = snap()
    n0 = len(s0.get("elements") or [])
    r = cbt(text, 1)
    print(f"  click ok={r.get('ok')} {json.dumps(r.get('result'), ensure_ascii=False)[:130]}")
    time.sleep(wait)
    s1 = snap()
    bp = s1.get("body_preview") or ""
    save(name, {"text": text, "n_before": n0, "n_after": len(s1.get("elements") or []),
                "url": s1.get("url"), "triggered_search": "#session" in (s1.get("url") or ""),
                "selected_tag": text in bp, "body_mid": bp[-800:]})


def main():
    # 1. 统招（文本可点，之前无反应）
    probe_dropdown("tongzhao", "统招要求（click_by_text 统招）", lambda: cbt("统招", 1))
    # 2. 活跃度 combobox（现查编号）
    def activity_click():
        s = snap()
        for e in (s.get("elements") or []):
            if e.get("role") == "combobox":
                return click_idx(e.get("index"))
        return {"ok": False, "error": "未找到 combobox"}
    probe_dropdown("activity", "活跃度 combobox", activity_click)
    # 3. 求职状态（文本定位）
    probe_dropdown("jobstatus", "求职状态（click_by_text 求职状态（不限））", lambda: cbt("求职状态（不限）", 1))
    # 4. 性别（现查：院校要求 chips(75) 之后、年龄之前的 span 不限？改用文本'不限' occurrence 探测太危险，先跳——用 combobox 唯一性覆盖）
    # 5. 即点即搜过滤验证
    probe_years_filter()
    # 6. 教育经历/院校 chip 是否即点即搜
    probe_chip_click("edu_click", "本科")
    probe_chip_click("school_click", "985")
    print("\n探针 v3 全部完成")


if __name__ == "__main__":
    main()
