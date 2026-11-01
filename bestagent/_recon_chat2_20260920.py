#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_recon_chat2_20260920.py — 职聊页**只读侦察 第2步**：重新加载页面后再读

要点（第1步实测）：上一场留下的职聊页标签是**旧页**（最新只到 14:20，郭** 14:22 的招呼不在）
→ reply_run 必须自己 navigate 重新加载，等 4~8 秒，再拍快照 + 读整页文本。

本步动作：navigate（只是重新加载我们自己的收件箱页，不发送、不点击任何东西）
        → 等 8 秒 → page_text（全文，不截断）+ snapshot（元素列表）
        → 落 data/_recon/chat2_*.{json,txt}

用法：python _recon_chat2_20260920.py [tab_id]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bridge as b  # noqa: E402

URL = "https://h.liepin.com/im/showmsgnewpage"
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

print("navigate ...")
print(b.submit("navigate", {"tab_id": TAB, "url": URL}, timeout=90))
time.sleep(8)

txt = b.submit("page_text", {"tab_id": TAB, "max_chars": 0}, timeout=120)
(OUT / "chat2_pagetext.json").write_text(json.dumps(txt, ensure_ascii=False, indent=1), encoding="utf-8")
text = txt.get("text") or ""
(OUT / "chat2_pagetext.txt").write_text(text, encoding="utf-8")
print("page_text chars =", txt.get("chars"), "truncated =", txt.get("truncated"))

time.sleep(1)
res = b.submit("snapshot", {"tab_id": TAB, "preview_chars": 20000}, timeout=120)
(OUT / "chat2_snapshot.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
els = res.get("elements") or []
lines = []
for e in sorted(els, key=lambda x: ((x.get("rect") or {}).get("top", 0), (x.get("rect") or {}).get("left", 0))):
    r = e.get("rect") or {}
    lines.append(f"[{e.get('index')}] {e.get('role')} t={round(r.get('top',0))} l={round(r.get('left',0))} "
                 f"w={round(r.get('width',0))} | {(e.get('name') or '')[:200]}")
(OUT / "chat2_elements.txt").write_text("\n".join(lines), encoding="utf-8")
print("elements =", len(els), "| settled =", res.get("settled"))
print("saved ->", OUT.as_posix())
