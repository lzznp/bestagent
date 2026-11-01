#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_recon_joblist_20260920.py — 只读侦察：猎聘「职位管理」页能不能读回 hjobId（映射自动回填的前提）

背景（讨论用）：老板说"岗位最早来自禾蛙，我不得不来回跳转"。要判断"回填/映射"能不能自动化，
就得先看：**我们自己的在招职位列表页**长什么样、`hjobId` 在不在 href 里（文档 §过去说：
hjobId 页面上不显示明文、只在链接地址里；`snapshot` 的元素**带 href**，所以理论上可读）。

只读：list_tabs / new_tab / navigate / snapshot / page_text / close_tab —— 不点任何东西。
用法：python _recon_joblist_20260920.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bridge as b  # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "_recon"
OUT.mkdir(parents=True, exist_ok=True)
URLS = ["https://h.liepin.com/job/showlistpage?jobStatus=11",   # 在招职位（文档记的地址）
        "https://h.liepin.com/job/showlistpage"]

report: dict = {}
for url in URLS:
    print("=" * 70)
    print("navigate:", url)
    r = b.submit("new_tab", {"url": url}, timeout=90)
    tab = int((r.get("tab") or {}).get("tab_id") or 0)
    print("tab =", tab)
    if not tab:
        continue
    try:
        time.sleep(6)
        snap = b.submit("snapshot", {"tab_id": tab, "preview_chars": 1000}, timeout=120)
        txt = b.submit("page_text", {"tab_id": tab, "max_chars": 0}, timeout=120)
        els = snap.get("elements") or []
        hrefs = sorted({e.get("href") for e in els if e.get("href")})
        report[url] = {"tab": tab, "title": snap.get("title"), "final_url": snap.get("url"),
                       "elements": len(els), "chars": txt.get("chars"), "hrefs": hrefs}
        print("title:", snap.get("title"))
        print("final url:", snap.get("url"))
        print("elements:", len(els), "| 整页字:", txt.get("chars"))
        print("--- 元素里的链接（前 25 条）---")
        for h in hrefs[:25]:
            print("   ", h)
        (OUT / f"joblist_{abs(hash(url)) % 100000}.json").write_text(
            json.dumps({"snapshot": snap, "text": txt.get("text")}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        (OUT / "joblist_pagetext.txt").write_text((txt.get("text") or "")[:4000], encoding="utf-8")
    finally:
        try:
            b.submit("close_tab", {"tab_id": tab})
            print("（读完已关）")
        except Exception as e:  # noqa: BLE001
            print("关页失败:", e)

(OUT / "joblist_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print("=" * 70)
print("saved ->", OUT.as_posix())
