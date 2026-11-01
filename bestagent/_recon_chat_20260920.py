#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_recon_chat_20260920.py — ⑤查看回复 开工前**只读侦察**（不点、不发、不改页面）

把职聊页的快照落成 JSON/文本，供实施读元素列表（纪律：判断"有没有"只看元素列表）。
用法：python _recon_chat_20260920.py [tab_id]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bridge as b  # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "_recon"
OUT.mkdir(parents=True, exist_ok=True)
TAB = int(sys.argv[1]) if len(sys.argv) > 1 else 0

if not TAB:
    r = b.submit("list_tabs")
    for t in (r.get("tabs") or []):
        if "showmsgnewpage" in str(t.get("url") or ""):
            TAB = int(t.get("tab_id"))
            break
print("tab =", TAB)
res = b.submit("snapshot", {"tab_id": TAB}, timeout=120)
(OUT / "chat_snapshot.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

els = res.get("elements") or []
print("url =", res.get("url"))
print("title =", res.get("title"))
print("elements =", len(els))
print("result keys =", list(res.keys()))
# 逐行文本（元素列表，按 top 排序）
lines = []
for e in sorted(els, key=lambda x: ((x.get("rect") or {}).get("top", 0), (x.get("rect") or {}).get("left", 0))):
    r = e.get("rect") or {}
    lines.append(f"[{e.get('index')}] {e.get('role')} t={r.get('top')} l={r.get('left')} w={r.get('width')} "
                 f"h={r.get('height')} | {(e.get('name') or '')[:160]}"
                 + (f" | value={(e.get('value') or '')[:80]}" if e.get("value") else ""))
(OUT / "chat_elements.txt").write_text("\n".join(lines), encoding="utf-8")
print("saved:", (OUT / "chat_snapshot.json").as_posix(), len(lines), "lines")
bp = res.get("body_preview") or res.get("body_text") or ""
(OUT / "chat_body.txt").write_text(str(bp), encoding="utf-8")
print("body len =", len(str(bp)))
