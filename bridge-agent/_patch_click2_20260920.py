#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_click2_20260920.py — 修桥的"点击"（第二版：内联，不引用模块级函数）

第一版教训（实测）：`executeScript({func: zClick})` **只序列化函数自己的源码**，
所以引用模块级的 `__zRealClick` 会在页面里 `ReferenceError`。
→ 本版把"真人式点击"那段**内联**进 zClick / zClickByText 各自函数体内。

改法：把
    target.scrollIntoView(...);
    target.dispatchEvent(mousedown...);
    target.dispatchEvent(mouseup...);
    target.click();
换成内联版：坐标 + 命中测试(elementFromPoint) + pointerdown/mousedown/pointerup/mouseup/click。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(r"D:\study\bestagent\bridge-agent\extension\background.js")

INLINE = """    // 2026-09-20：真人式点击（内联，不能引用模块级函数——executeScript 只序列化本函数）
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

OLD1 = """    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    // P5-2：真实事件序列——Ant Design Select 等控件监听 mousedown，仅 el.click() 打不开下拉。
    // 先派发 mousedown/mouseup 再 click（自包含内联，executeScript 只序列化本函数）
    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    target.click();"""

OLD2 = """    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    // P5-2：真实事件序列（同 zClick）——mousedown 监听控件（Ant Design Select）必须派发
    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    target.click();"""

BLOCKED1 = "    result.clicked = { index, tag: target.tagName.toLowerCase() };"
BLOCKED2 = """    result.clicked = {
      text: t,
      occurrence: want,
      total: matches.length,
      tag: target.tagName.toLowerCase(),
      matched_text: matches[want - 1].text,
    };"""


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字节，字符数）")

    # 0. 先撤掉第一版留下的坏引用（如果有）
    bad = "    const _rc = __zRealClick(target);"
    if bad in src:
        src = src.replace(bad, INLINE, 1)
        print("  ↩︎ 第一版残留已就地替换为内联版（zClick）")
    bad2 = "    if (_rc && _rc.blocked_by) result.blocked_by = _rc.blocked_by;"
    if bad2 in src:
        src = src.replace(bad2, "", 1)
        print("  ↩︎ 清掉第一版 _rc 残留")

    for old, label in ((OLD1, "zClick"), (OLD2, "zClickByText")):
        c = src.count(old)
        assert c == 1, f"❌ [{label}] 命中 {c} 次（文件未改动）"
        src = src.replace(old, INLINE, 1)
        print(f"  ✅ {label} 换成内联真人式点击")

    # 命中测试结果透出
    if "_blocked" in src and "result.blocked_by" not in src:
        for anchor, label in ((BLOCKED1, "zClick"), (BLOCKED2, "zClickByText")):
            c = src.count(anchor)
            assert c == 1, f"❌ [{label} 结果段] 命中 {c} 次"
            src = src.replace(anchor, anchor + "\n    if (_blocked) result.blocked_by = _blocked;", 1)
        print("  ✅ 结果里带 blocked_by")

    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字符）")


if __name__ == "__main__":
    sys.exit(main())
