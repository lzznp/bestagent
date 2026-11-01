#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_preview_20260920.py — 修"body_preview 只截前 3000 字"（老板 2026-09-20 拍板）

为什么改（实测）：打招呼弹层的文字在**页面末尾**，被 3000 字硬编码截掉 →
      调用方（小猎/脚本/agent）看不到弹层内容 → 误判"弹层没出来"。
      今天下午一连串"打招呼点不动"的假故障，根因就是它。

改法（三处，保守）：
  1. zSnapshot 接一个可选参数 previewChars（默认 8000）；
  2. `bodyText.slice(0, 3000)` → `bodyText.slice(0, 8000)`；
  3. 分发处给 snapshot 传参（默认 8000，调用方可用 params.preview_chars 指定）。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(r"D:\study\bestagent\bridge-agent\extension\background.js")

E1_OLD = "async function zSnapshot() {"
E1_NEW = "async function zSnapshot(previewChars) {"

E2_OLD = "    result.body_preview = bodyText.slice(0, 3000);"
E2_NEW = ("    // 2026-09-20：默认从 3000 → 8000（3000 会把页面末尾的弹层截掉，导致误判）\n"
          "    const _pv = (typeof previewChars === 'number' && previewChars > 0) ? previewChars : 8000;\n"
          "    result.body_preview = bodyText.slice(0, _pv);")

E3_OLD = "  if (action === 'snapshot') { /* 无参 */ }"
E3_NEW = ("  if (action === 'snapshot') args.push(p.preview_chars !== undefined ? Number(p.preview_chars) : 0);")


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字符）")
    for old, new, label in ((E1_OLD, E1_NEW, "1/3 zSnapshot 接参数"),
                            (E2_OLD, E2_NEW, "2/3 截断 3000 → 8000（可覆盖）"),
                            (E3_OLD, E3_NEW, "3/3 分发处传参")):
        n = src.count(old)
        assert n == 1, f"❌ [{label}] 命中 {n} 次（文件未改动）"
        src = src.replace(old, new, 1)
        print(f"  ✅ {label}")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字符）")


if __name__ == "__main__":
    sys.exit(main())
