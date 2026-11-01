#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_recon_chat4_20260920.py — 职聊页**只读侦察 第4步**：看"对方真回了话"的会话长什么样

目的：列表里 郑先生 的预览是『什么职位』（**候选人自己发的话**）→ 点开它，看消息流里
     "对方的话 / 我们的话 / 系统话" 各是什么形态（给 reply_run 的解析定规矩）。
只读：只点会话行，不发送、不输入。

用法：python _recon_chat4_20260920.py <tab_id> <要点的会话行姓名>
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
WANT = sys.argv[2] if len(sys.argv) > 2 else "郑先生"

snap = b.submit("snapshot", {"tab_id": TAB, "preview_chars": 1000}, timeout=120)
els = snap.get("elements") or []
# 会话行的姓名 span：left≈156、宽≈44、高≈21（实测特征）
cand = [e for e in els
        if (e.get("name") or "").strip() == WANT
        and abs((e.get("rect") or {}).get("left", 0) - 156) < 3
        and (e.get("rect") or {}).get("width", 0) < 60]
print("候选行:", [e.get("index") for e in cand])
if not cand:
    raise SystemExit("没找到会话行")
idx = cand[0]["index"]
print("click index =", idx)
print(b.submit("click", {"tab_id": TAB, "index": idx}, timeout=60))
time.sleep(3)
txt = b.submit("page_text", {"tab_id": TAB, "max_chars": 0}, timeout=120)
(OUT / f"chat4_{WANT}_pagetext.txt").write_text(txt.get("text") or "", encoding="utf-8")
res = b.submit("snapshot", {"tab_id": TAB, "preview_chars": 30000}, timeout=120)
(OUT / f"chat4_{WANT}_snapshot.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
lines = []
for e in sorted(res.get("elements") or [], key=lambda x: ((x.get("rect") or {}).get("top", 0), (x.get("rect") or {}).get("left", 0))):
    r = e.get("rect") or {}
    lines.append(f"[{e.get('index')}] {e.get('role')} t={round(r.get('top',0))} l={round(r.get('left',0))} "
                 f"w={round(r.get('width',0))} | {(e.get('name') or '')[:200]}")
(OUT / f"chat4_{WANT}_elements.txt").write_text("\n".join(lines), encoding="utf-8")
print("chars =", txt.get("chars"), "| elements =", len(res.get("elements") or []))
print("done")
