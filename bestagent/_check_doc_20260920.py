#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_check_doc_20260920.py — 量一下新报告：总字节 + ★速查卡字节（规范 §11.2 要求 ≤1.5KB）"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = Path(__file__).resolve().parents[1] / "工作文档" / "小猎·协同形态与后续四题·讨论开工书.md"
raw = p.read_bytes()
text = raw.decode("utf-8")
lines = text.splitlines()
start = next(i for i, ln in enumerate(lines) if "速查卡" in ln and ln.startswith("## "))
end = next(i for i, ln in enumerate(lines[start + 1:], start + 1) if ln.startswith("## "))
card = "\n".join(lines[start:end])
print("文件:", p.name)
print("总字节:", len(raw), "| 总行数:", len(lines), "| 估算词元:", round(len(raw) / 2.5))
print("速查卡字节:", len(card.encode('utf-8')), "(上限 1536)", "| 行:", len(card.splitlines()))
print("速查卡字符数:", len(card))
print("分节标题:")
for ln in lines:
    if ln.startswith("## ") or ln.startswith("### "):
        print("   ", ln)
