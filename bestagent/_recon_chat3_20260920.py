#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_recon_chat3_20260920.py — 职聊页**只读侦察 第3步**：点一个会话行，看右侧详情有什么

背景（开工书 §4.4-2）：想用**简历编号**精确对号（页面显示全名/先生，我们库里是打码名）。
本步只做一件事：点某个会话行 → 读右侧详情 → 看有没有 简历编号/res_id/沟通职位/消息流。
**不发送、不输入、不改任何东西**（只点击会话行切换会话）。

用法：python _recon_chat3_20260920.py <tab_id> <元素index>
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
TAB = int(sys.argv[1])
IDX = int(sys.argv[2]) if len(sys.argv) > 2 else 29

print(f"click 会话行 index={IDX} (tab={TAB}) …")
print(b.submit("click", {"tab_id": TAB, "index": IDX}, timeout=60))
time.sleep(3)

txt = b.submit("page_text", {"tab_id": TAB, "max_chars": 0}, timeout=120)
(OUT / "chat3_pagetext.json").write_text(json.dumps(txt, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "chat3_pagetext.txt").write_text(txt.get("text") or "", encoding="utf-8")
print("chars =", txt.get("chars"), "truncated =", txt.get("truncated"))

res = b.submit("snapshot", {"tab_id": TAB, "preview_chars": 30000}, timeout=120)
(OUT / "chat3_snapshot.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
els = res.get("elements") or []
lines = []
for e in sorted(els, key=lambda x: ((x.get("rect") or {}).get("top", 0), (x.get("rect") or {}).get("left", 0))):
    r = e.get("rect") or {}
    lines.append(f"[{e.get('index')}] {e.get('role')} t={round(r.get('top',0))} l={round(r.get('left',0))} "
                 f"w={round(r.get('width',0))} | {(e.get('name') or '')[:200]}"
                 + (f" | value={(e.get('value') or '')[:60]}" if e.get("value") else ""))
(OUT / "chat3_elements.txt").write_text("\n".join(lines), encoding="utf-8")
print("elements =", len(els))
print("saved")
