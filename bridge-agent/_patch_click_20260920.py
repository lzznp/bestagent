#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_click_20260920.py — 修桥的"点击"（老板 2026-09-20 实测：点击全局失效）

实测证据（2026-09-20）：
  · 猎聘"立即沟通" / "查看联系方式" / B站导航 —— 合成点击**都不生效**；
  · 但快照/翻页/开关标签/截图**全都正常**；真人点击**有效**；
  · 扩展还回报 ok:true → **静默失败**（最坏的一种）。

改法：把"只发 mousedown+mouseup+click"升级成**像真人的点击**：
  ① 先 scrcollIntoView + 算中心坐标；
  ② elementFromPoint 做**命中测试**：被别的元素压着就**如实报"被谁挡住"**（不再假装成功）；
  ③ 派发完整序列：pointerdown → mousedown → pointerup → mouseup → click（带 clientX/clientY）。

⚠️ 改完必须让老板在 edge://extensions/ 点一次「重新加载」，再刷新页面才生效。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(r"D:\study\bestagent\bridge-agent\extension\background.js")

ANCHOR_INSERT = 'function zClick(index) {'
HELPER = '''/** 真人式点击：带坐标的完整事件序列 + 命中测试（2026-09-20 修"点击静默失效"）
 *  ⚠️ 必须自包含：executeScript 只序列化本函数，不能引用外部变量。 */
function __zRealClick(target) {
  try { target.scrollIntoView({ block: 'center', behavior: 'instant' }); } catch (e) {}
  const r = target.getBoundingClientRect();
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;
  const at = document.elementFromPoint(cx, cy);
  let blocked = null;
  if (at && at !== target && !target.contains(at) && !at.contains(target)) {
    blocked = (at.tagName || '').toLowerCase() + (at.id ? ('#' + at.id) : '') +
              (typeof at.className === 'string' && at.className ? ('.' + at.className.trim().split(/\\s+/).join('.')) : '');
  }
  const mk = (Ctor, type, extra) => {
    try { return new Ctor(type, Object.assign({ bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, button: 0 }, extra || {})); }
    catch (e) { return null; }
  };
  const seq = [
    [typeof PointerEvent !== 'undefined' ? PointerEvent : MouseEvent, 'pointerdown', { pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 1 }],
    [MouseEvent, 'mousedown', { buttons: 1 }],
    [typeof PointerEvent !== 'undefined' ? PointerEvent : MouseEvent, 'pointerup', { pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0 }],
    [MouseEvent, 'mouseup', {}],
  ];
  for (const s of seq) {
    const ev = mk(s[0], s[1], s[2]);
    if (ev) { try { target.dispatchEvent(ev); } catch (e) {} }
  }
  try { target.click(); } catch (e) {}
  const out = { ok: true, rect: { left: r.left, top: r.top, width: r.width, height: r.height } };
  if (blocked) {
    out.blocked_by = blocked;
    out.note = '元素中心被 ' + blocked + ' 挡住（可能弹层/遮罩在上层）——已照常派发事件，但可能不生效';
  }
  return out;
}

'''

OLD_DISPATCH = """    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    // P5-2：真实事件序列——Ant Design Select 等控件监听 mousedown，仅 el.click() 打不开下拉。
    // 先派发 mousedown/mouseup 再 click（自包含内联，executeScript 只序列化本函数）
    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    target.click();"""

OLD_DISPATCH2 = """    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    // P5-2：真实事件序列（同 zClick）——mousedown 监听控件（Ant Design Select）必须派发
    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    target.click();"""

NEW_DISPATCH = """    // 2026-09-20：升级为"真人式点击"（带坐标 + 完整事件序列 + 命中测试）
    const _rc = __zRealClick(target);"""


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字节）")

    n = src.count(ANCHOR_INSERT)
    assert n == 1, f"❌ [helper 插入点] 命中 {n} 次（文件未改动）"
    src = src.replace(ANCHOR_INSERT, HELPER + ANCHOR_INSERT, 1)
    print("  ✅ 1/3 插入 __zRealClick")

    for old, label in ((OLD_DISPATCH, "zClick"), (OLD_DISPATCH2, "zClickByText")):
        c = src.count(old)
        assert c == 1, f"❌ [{label} 点击段] 命中 {c} 次（文件未改动）"
        src = src.replace(old, NEW_DISPATCH, 1)
        print(f"  ✅ 2/3 替换 {label} 的点击段")

    # 让结果里带上命中测试信息（zClick / zClickByText 各自的 result.clicked 后面补一行）
    old_r1 = "    result.clicked = { index, tag: target.tagName.toLowerCase() };"
    assert src.count(old_r1) == 1, "❌ zClick 结果段命中不为 1"
    src = src.replace(old_r1, old_r1 + "\n    if (_rc && _rc.blocked_by) result.blocked_by = _rc.blocked_by;", 1)
    old_r2 = """    result.clicked = {
      text: t,
      occurrence: want,
      total: matches.length,
      tag: target.tagName.toLowerCase(),
      matched_text: matches[want - 1].text,
    };"""
    assert src.count(old_r2) == 1, "❌ zClickByText 结果段命中不为 1"
    src = src.replace(old_r2, old_r2 + "\n    if (_rc && _rc.blocked_by) result.blocked_by = _rc.blocked_by;", 1)
    print("  ✅ 3/3 结果里带 blocked_by")

    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字节）")


if __name__ == "__main__":
    sys.exit(main())
