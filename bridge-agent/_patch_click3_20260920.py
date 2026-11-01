#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_click3_20260920.py — 修桥的"点击"（第三版：把调用点换成内联实现）

现状（第二版断言保住后的真实状态）：
  · 第 197 行有个模块级 `__zRealClick`（**没用**——executeScript 只序列化函数自己）；
  · 295 / 455 两处调用它 → 页面里会 ReferenceError（已实测）。
本版：把这两处调用**就地换成内联的真人式点击**，并删掉无用的模块级函数。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(r"D:\study\bestagent\bridge-agent\extension\background.js")

INLINE = """    // 2026-09-20：真人式点击（**必须内联**：executeScript 只序列化本函数，引用模块级函数会 ReferenceError）
    try { target.scrollIntoView({ block: 'center', behavior: 'instant' }); } catch (e) {}
    const _r = target.getBoundingClientRect();
    const _cx = _r.left + _r.width / 2;
    const _cy = _r.top + _r.height / 2;
    let _blocked = null;
    try {
      const _at = document.elementFromPoint(_cx, _cy);
      if (_at && _at !== target && !target.contains(_at) && !_at.contains(target)) {
        _blocked = (_at.tagName || '').toLowerCase() + (_at.id ? ('#' + _at.id) : '');
      }
    } catch (e) {}
    const _mk = (Ctor, type, extra) => {
      try { return new Ctor(type, Object.assign({ bubbles: true, cancelable: true, view: window, clientX: _cx, clientY: _cy, button: 0 }, extra || {})); }
      catch (e) { return null; }
    };
    const _PE = (typeof PointerEvent !== 'undefined') ? PointerEvent : MouseEvent;
    for (const _s of [
      [_PE, 'pointerdown', { pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 1 }],
      [MouseEvent, 'mousedown', { buttons: 1 }],
      [_PE, 'pointerup', { pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0 }],
      [MouseEvent, 'mouseup', {}],
    ]) {
      const _ev = _mk(_s[0], _s[1], _s[2]);
      if (_ev) { try { target.dispatchEvent(_ev); } catch (e) {} }
    }
    try { target.click(); } catch (e) {}"""

CALL = "    const _rc = __zRealClick(target);"
MODULE_FUNC_START = "/** 真人式点击：带坐标的完整事件序列 + 命中测试（2026-09-20 修\"点击静默失效\"）"
MODULE_FUNC_END = "}\n\nfunction zClick(index) {"


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字符）")

    # ① 删掉无用的模块级函数（executeScript 用不到，还容易误以为生效）
    if MODULE_FUNC_START in src:
        i = src.find(MODULE_FUNC_START)
        j = src.find(MODULE_FUNC_END, i)
        assert i > 0 and j > i, "❌ 找不到模块级函数边界（文件未改动）"
        src = src[:i] + "function zClick(index) {" + src[j + len(MODULE_FUNC_END):]
        print("  ✅ 1/2 删掉无用的模块级 __zRealClick")

    # ② 两处调用 → 内联实现
    n = src.count(CALL)
    assert n == 2, f"❌ 调用点命中 {n} 次（应为 2，文件未改动）"
    src = src.replace(CALL, INLINE)
    print(f"  ✅ 2/2 {n} 处调用点换成内联真人式点击")

    # ③ 命中测试结果透出（两处 result.clicked 后面）
    for anchor in ("    result.clicked = { index, tag: target.tagName.toLowerCase() };",):
        c = src.count(anchor)
        assert c == 1, f"❌ zClick 结果段命中 {c}"
        src = src.replace(anchor, anchor + "\n    if (_blocked) result.blocked_by = _blocked;", 1)
    anchor2 = """      matched_text: matches[want - 1].text,
    };"""
    c2 = src.count(anchor2)
    assert c2 == 1, f"❌ zClickByText 结果段命中 {c2}"
    src = src.replace(anchor2, anchor2 + "\n    if (_blocked) result.blocked_by = _blocked;", 1)
    print("  ✅ 命中测试结果透出 blocked_by")

    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字符）")


if __name__ == "__main__":
    sys.exit(main())
