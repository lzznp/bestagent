#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_send_20260920.py — 按实测修"发岗位介绍"这一段

实测（2026-09-20，翁** 会话为证）：
  · 打招呼（不选职位开聊）后，页面**没有**聊天输入框 → 必须先点【继续沟通】把面板打开；
  · 面板打开后：textarea（占位"请输入文字，按Enter键发送"）+ 可点的 **"发送"** 文字元素；
  · **点"发送"（click_by_text）才真发**；用几何猜按钮会点错（我实测点错两次）；
  · 发完：textarea 清空 + 会话里出现该段文字 → 这两个就是**校验点**。

改法：把 ④ 段（发岗位介绍）整体替换为：
  ① 找可见 textarea（占位含"请输入文字"的优先）；
  ② type 进去 → **回读 value 校验真的进去了**；
  ③ click_by_text "发送" → 等 textarea 清空 / 会话出现该段 → 校验发成功。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("greet_exec.py")

OLD = '''        # ④ 发岗位介绍
        if not intro.strip():
            return {"ok": False, "steps": steps, "error": "报告里没有 intro_msg（岗位介绍）→ 不硬编，先停下"}
        ti = find_textarea(res)
        if not ti:
            return {"ok": False, "steps": steps, "error": "没找到会话输入框（聊天面板没展开）"}
        act("type", {"tab_id": tab, "index": ti, "text": intro})
        steps.append(f"输入岗位介绍（{len(intro)} 字）")
        time.sleep(gap)
        res = snap(tab)
        # 发送按钮 = 输入框正下方那个按钮（取 left 最接近输入框、top 更大的）
        ta = next((e for e in res.get("elements") or [] if e.get("index") == ti), {})
        tl, tt = (ta.get("rect") or {}).get("left", 0), (ta.get("rect") or {}).get("top", 0)
        btn = None
        for e in res.get("elements") or []:
            r = e.get("rect") or {}
            if e.get("role") == "button" and r.get("top", 0) > tt and abs(r.get("left", 0) - tl) < 60:
                btn = e.get("index")
                break
        if not btn:
            return {"ok": False, "steps": steps, "error": "找不到【发送】按钮"}
        act("click", {"tab_id": tab, "index": btn})
        steps.append("点【发送】→ 岗位介绍已发")
        time.sleep(gap + 1)
        res = snap(tab)
        head = (intro.split("\\n")[0] or "")[:12]
        joined = " | ".join((e.get("name") or "") for e in (res.get("elements") or []))
        sent = bool(head) and (head in joined)
        steps.append("页面回读：岗位介绍" + ("已在会话里 ✅" if sent else "**没读到**（需人工确认）"))'''

NEW = '''        # ④ 发岗位介绍（实测路径：面板要先打开 → type → 点文字"发送" → 两处校验）
        if not intro.strip():
            return {"ok": False, "steps": steps, "error": "报告里没有 intro_msg（岗位介绍）→ 不硬编，先停下"}
        # 4.1 面板可能还没展开（打招呼后是收起状态）→ 点【继续沟通】把它打开
        if not find_textarea(res):
            more = next((e for e in (res.get("elements") or [])
                         if (e.get("name") or "").strip() == "继续沟通"), None)
            if more:
                act("click", {"tab_id": tab, "index": more.get("index")})
                steps.append("点【继续沟通】展开聊天面板")
                time.sleep(gap)
                res = snap(tab)
        ti = find_textarea(res)
        if not ti:
            return {"ok": False, "steps": steps, "error": "没找到会话输入框（聊天面板没展开）"}
        # 4.2 输入 + **回读校验**（写进去了才算数）
        act("type", {"tab_id": tab, "index": ti, "text": intro})
        time.sleep(gap)
        res = snap(tab)
        ta = next((e for e in (res.get("elements") or []) if e.get("index") == ti), {})
        val = str(ta.get("value") or "")
        head = (intro.split("\\n")[0] or "")[:12]
        if head and head not in val:
            return {"ok": False, "steps": steps,
                    "error": f"岗位介绍没写进输入框（回读只有 {len(val)} 字）→ 不发，避免发空"}
        steps.append(f"输入岗位介绍并回读校验通过（{len(val)} 字）")
        # 4.3 点文字"发送"（**实测唯一可靠的路径**；几何猜按钮会点错）
        act("click_by_text", {"tab_id": tab, "text": "发送", "occurrence": 1})
        time.sleep(gap + 1)
        res = snap(tab)
        ta2 = next((e for e in (res.get("elements") or []) if e.get("role") == "textarea"), {})
        v2 = str(ta2.get("value") or "")
        joined = " | ".join((e.get("name") or "") for e in (res.get("elements") or []))
        cleared = len(v2) < len(val) / 2
        seen = bool(head) and (head in joined)
        if cleared or seen:
            steps.append("点【发送】→ 岗位介绍已发 ✅" + ("（输入框已清空）" if cleared else "（会话里已出现）"))
        else:
            return {"ok": False, "steps": steps,
                    "error": "点了【发送】但输入框没清空、会话也没出现 → 这条没发出去"}'''


OLD_TA = '''def find_textarea(res: dict) -> int | None:
    """会话输入框 = 页面上最大的 textarea（打招呼后详情页下部会展开聊天面板）。"""
    cands = []
    for e in res.get("elements") or []:
        if e.get("role") == "textarea":
            r = e.get("rect") or {}
            cands.append((r.get("width", 0), e.get("index")))
    return max(cands)[1] if cands else None'''

NEW_TA = '''def find_textarea(res: dict) -> int | None:
    """会话输入框。优先占位含"请输入文字"的那个（实测：详情页底部还有别的 textarea，别抓错）。"""
    tas = [e for e in (res.get("elements") or []) if e.get("role") == "textarea"]
    if not tas:
        return None
    for e in tas:
        if "请输入文字" in (e.get("name") or ""):
            return e.get("index")
    return max(tas, key=lambda e: (e.get("rect") or {}).get("width", 0)).get("index")'''


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字符）")
    for old, new, label in ((OLD, NEW, "④ 段：实测发送路径"),
                            (OLD_TA, NEW_TA, "find_textarea：优先'请输入文字'那个")):
        n = src.count(old)
        assert n == 1, f"❌ [{label}] 命中 {n} 次（文件未改动）"
        src = src.replace(old, new, 1)
        print(f"  ✅ {label}")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字符）")


if __name__ == "__main__":
    sys.exit(main())
