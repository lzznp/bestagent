#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_apply_patch.py — 原地文本补丁器（绕过 Win32 1175 原子替换失败）

背景：本机对 m3_chat.py 这类"被 Streamlit 看着"的文件，原子替换（ReplaceFileW）会报
Win32 1175 ERROR_UNABLE_TO_REMOVE_REPLACED；但**原地读写是好的**。所以用本工具打补丁。

用法：
  python _apply_patch.py <目标文件> <补丁文件>
补丁文件格式（可多段）：
  <<<<<OLD>>>>>
  ...必须唯一出现的原文...
  <<<<<NEW>>>>>
  ...替换成...
  <<<<<END>>>>>
校验：每段 old 必须**恰好出现 1 次**，否则整体不写、报错退出（不半途改坏文件）。
成功后原地写入并删掉补丁文件。
"""
from __future__ import annotations

import sys
from pathlib import Path

OLD, NEW, END = "<<<<<OLD>>>>>", "<<<<<NEW>>>>>", "<<<<<END>>>>>"


def parse(patch_text: str) -> list[tuple[str, str]]:
    secs: list[tuple[str, str]] = []
    parts = patch_text.split(OLD)
    if parts[0].strip():
        raise SystemExit("补丁文件必须以 <<<<<OLD>>>>> 开头（前面只允许空行）")
    for chunk in parts[1:]:
        if NEW not in chunk or END not in chunk:
            raise SystemExit("补丁段缺少 <<<<<NEW>>>>> 或 <<<<<END>>>>>")
        old, rest = chunk.split(NEW, 1)
        new, _tail = rest.split(END, 1)
        secs.append((old, new))
    return secs


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    target, patch = Path(sys.argv[1]), Path(sys.argv[2])
    text = target.read_text(encoding="utf-8")
    secs = parse(patch.read_text(encoding="utf-8"))
    print(f"▶ 目标 {target.name}（{len(text)} 字符）｜补丁 {len(secs)} 段")

    # 先全部校验，再统一替换（避免改了前两段才发现第三段不匹配）
    staged = []
    for i, (old, new) in enumerate(secs, 1):
        n = text.count(old)
        if n != 1:
            head = old.strip().splitlines()[0][:70] if old.strip() else "(空)"
            raise SystemExit(f"❌ 第 {i} 段 old 出现 {n} 次（必须恰好 1 次）：{head}…")
        print(f"  [{i}] old {len(old)} 字符 → new {len(new)} 字符 ✓唯一匹配")
        staged.append((old, new))

    for old, new in staged:
        text = text.replace(old, new, 1)
    target.write_text(text, encoding="utf-8")
    print(f"✅ 已原地写入 {target.name}（{len(text)} 字符）")
    patch.unlink()
    print(f"✅ 已删除补丁文件 {patch.name}")


if __name__ == "__main__":
    main()
