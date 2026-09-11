#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_probe.py — P5 城市面板行为探针（地面真值实测）

重现：干净条件页 → 打开目前城市面板 → type 城市名 → 快照看过滤结果。
用法：python p5_probe.py <city> [--dump-elements N]
结果落盘 logs/_probe_<city>.json（UTF-8），控制台只打印摘要。
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


def snap(tag):
    r = submit_task(BRIDGE, "snapshot", {"tab_id": TAB}, source="p5-probe")
    res = r.get("result") or {}
    print(f"[{tag}] ok={res.get('ok')} url={res.get('url')} elems={len(res.get('elements') or [])}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("city", help="要输入的城市名，如 青岛")
    ap.add_argument("--dump", type=int, default=20, help="dump 面板区域元素数")
    args = ap.parse_args()

    out = {"city": args.city, "steps": []}

    r = submit_task(BRIDGE, "navigate", {"tab_id": TAB, "url": COND_URL}, source="p5-probe")
    out["steps"].append({"act": "navigate", "ok": r.get("ok")})
    time.sleep(2.5)

    s1 = snap("baseline")
    out["steps"].append({"act": "snapshot-baseline", "elems": len(s1.get("elements") or []),
                         "url": s1.get("url")})

    r = submit_task(BRIDGE, "click_by_text", {"tab_id": TAB, "text": "其他", "occurrence": 1}, source="p5-probe")
    out["steps"].append({"act": "click 其他 occ=1", "ok": r.get("ok"),
                         "result": r.get("result") if not r.get("ok") else None})
    time.sleep(1.5)

    s2 = snap("panel-open")
    # 找搜索输入框（placeholder 含 搜索城市 / 城市）
    elems2 = s2.get("elements") or []
    search_input = None
    for e in elems2:
        ph = (e.get("placeholder") or "")
        name = (e.get("name") or "")
        val = (e.get("value") or "")
        if "城市" in ph or "城市" in name or "city" in name.lower():
            search_input = e
            break
    out["steps"].append({"act": "snapshot-panel", "elems": len(elems2),
                         "search_input": search_input})

    if search_input is None:
        # 回退：找 input 元素
        inputs = [e for e in elems2 if e.get("tag") == "input"]
        out["steps"].append({"note": "未找到搜索城市框，全部 input:", "inputs": inputs[:10]})
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    idx = search_input.get("index")
    print(f"[panel] 搜索城市框 index={idx} placeholder={search_input.get('placeholder')!r}")
    r = submit_task(BRIDGE, "type", {"tab_id": TAB, "index": idx, "text": args.city}, source="p5-probe")
    out["steps"].append({"act": f"type {args.city} @{idx}", "ok": r.get("ok")})
    time.sleep(2.0)

    s3 = snap("after-type")
    elems3 = s3.get("elements") or []
    # dump 从搜索框 index 开始的元素（文本/角色）
    region = [{"index": e.get("index"), "tag": e.get("tag"), "name": e.get("name"),
               "text": (e.get("text") or "")[:40], "value": (e.get("value") or "")[:30],
               "placeholder": e.get("placeholder") or ""}
              for e in elems3 if (e.get("index") or 0) >= idx - 2]
    out["steps"].append({"act": "snapshot-after-type", "elems": len(elems3),
                         "region": region[:args.dump],
                         "body_preview": s3.get("body_preview")})

    path = f"logs/_probe_{args.city}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("探针结果落盘:", path)


if __name__ == "__main__":
    main()
