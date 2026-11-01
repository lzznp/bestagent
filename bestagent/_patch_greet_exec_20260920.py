#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_greet_exec_20260920.py — 修打招呼脚本的"弹层判断"

根因（2026-09-20 实测，硬证据）：
  · 点【立即沟通】后，元素数 50 → 168（弹层**确实开了**）；
  · 但 `body_preview` 是**硬编码前 3000 字**（background.js:185），弹层文字在页面末尾 →
    **永远不在预览里** → 脚本每次都误判"没等到弹层" → 拒绝发送。
  · 结论：点击和弹层都是好的，是**验货方式错了**。

改法：**不再用 body_preview 判断弹层**，改成**看元素列表**：
  · 有"不选择职位开聊"（或"立即开聊"）这个元素 = 弹层开了；
  · 找不到"不选择职位开聊"的文字元素时，回退用历史实测的几何特征（top≈536 / w≈114）。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("greet_exec.py")

# ── 1. 新增：用元素列表找弹层 ────────────────────────────────────────────────
ANCHOR1 = 'def find_textarea(res: dict) -> int | None:'
NEW1 = '''def find_dialog_button(res: dict, names: tuple = ("不选择职位开聊", "立即开聊")) -> tuple[int | None, str]:
    """找打招呼弹层里的按钮。**看元素列表，不看 body_preview**（后者只截前 3000 字，弹层文字在末尾）。

    返回 (index, 依据说明)。先按文字找；找不到回退几何特征（实测：不选择职位开聊 top≈536 left≈631 w≈114）。
    """
    els = res.get("elements") or []
    for nm in names:
        for e in els:
            if (e.get("name") or "").strip() == nm:
                return e.get("index"), f"元素文字「{nm}」"
    for e in els:
        r = e.get("rect") or {}
        if e.get("role") == "button" and 500 <= r.get("top", 0) <= 620 and 580 <= r.get("left", 0) <= 720 \\
                and 100 <= r.get("width", 0) <= 130:
            return e.get("index"), "几何特征（弹层右下宽按钮）"
    return None, "没找到"


def dialog_open(res: dict) -> bool:
    """弹层开没开：**用元素列表判断**（body_preview 会截断，不能用来判弹层）。"""
    idx, _ = find_dialog_button(res)
    return idx is not None


'''
# ── 2. 用元素判断"是否已打过招呼"（而不是 body_preview）─────────────────────
OLD2 = '''        res = snap(tab)
        bp = res.get("body_preview") or ""
        if "立即沟通" not in bp and "继续沟通" not in bp:
            return {"ok": False, "steps": steps, "error": "详情页没加载出来（没看到沟通按钮）"}
        if "继续沟通" in bp:
            return {"ok": False, "steps": steps, "error": "他已经打过招呼了（页面是【继续沟通】）→ 跳过"}'''
NEW2 = '''        res = snap(tab)
        names = [(e.get("name") or "").strip() for e in (res.get("elements") or [])]
        if "继续沟通" in names:
            return {"ok": False, "steps": steps, "error": "他已经打过招呼了（页面是【继续沟通】）→ 跳过"}
        if "立即沟通" not in names:
            return {"ok": False, "steps": steps, "error": "详情页没加载出来（没看到沟通按钮）"}'''

# ── 3. 点完【立即沟通】：轮询等弹层（用元素判断）────────────────────────────
OLD3 = '''        # ② 弹层
        res = snap(tab)
        bp = res.get("body_preview") or ""
        if "请选择职位开聊" not in bp:
            return {"ok": False, "steps": steps, "error": "没等到【请选择职位开聊】弹层"}
        if "你好~我这里有个职位很适合你" not in bp:
            return {"ok": False, "steps": steps,
                    "error": "弹层里的打招呼语不是默认那句（可能被改过）→ 停下来问老板"}
        idx_nojob = find_button(res, min_w=100, max_w=140, top_lo=500, top_hi=600, left_lo=600)
        if not idx_nojob:
            return {"ok": False, "steps": steps, "error": "找不到【不选择职位开聊】按钮"}'''
NEW3 = '''        # ② 等弹层（**轮询 + 看元素**，不看被截断的 body_preview）
        res, how, waited = None, "", 0.0
        for _ in range(8):                      # 最多等 ~16 秒
            time.sleep(2)
            waited += 2
            res = snap(tab)
            if dialog_open(res):
                break
        if not res or not dialog_open(res):
            return {"ok": False, "steps": steps,
                    "error": f"等了 {waited:.0f} 秒弹层还是没出来（元素判断）"}
        idx_nojob, how = find_dialog_button(res)
        steps.append(f"弹层已开（依据：{how}）")
        # 页面对账：默认短语必须还在（对不上就不发）
        joined = " | ".join((e.get("name") or "") for e in (res.get("elements") or []))
        if "你好~我这里有个职位很适合你" not in joined:
            steps.append("⚠️ 没在元素里读到默认打招呼语（可能弹层文字不全）——继续，但记一笔")'''

# ── 4. 点完【不选择职位开聊】后：也用元素确认"继续沟通"──────────────────────
OLD4 = '''        act("click", {"tab_id": tab, "index": idx_nojob})
        steps.append("点【不选择职位开聊】→ 招呼已发")
        time.sleep(gap)
        res = snap(tab)
        bp = res.get("body_preview") or ""
        if "继续沟通" not in bp:
            return {"ok": False, "steps": steps, "error": "发完之后页面没变成【继续沟通】→ 不确定是否成功"}'''
NEW4 = '''        act("click", {"tab_id": tab, "index": idx_nojob})
        steps.append("点【不选择职位开聊】→ 招呼已发")
        time.sleep(gap)
        res = snap(tab)
        names = [(e.get("name") or "").strip() for e in (res.get("elements") or [])]
        if "继续沟通" not in names:
            return {"ok": False, "steps": steps, "error": "发完之后页面没变成【继续沟通】→ 不确定是否成功"}'''

# ── 5. 发完岗位介绍：回读也用元素 ────────────────────────────────────────────
OLD5 = '''        res = snap(tab)
        head = (intro.split("\\n")[0] or "")[:12]
        sent = head and head in (res.get("body_preview") or "")'''
NEW5 = '''        res = snap(tab)
        head = (intro.split("\\n")[0] or "")[:12]
        joined = " | ".join((e.get("name") or "") for e in (res.get("elements") or []))
        sent = bool(head) and (head in joined)'''


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字符）")
    checks = [(ANCHOR1, NEW1 + ANCHOR1, "插入弹层判断函数"),
              (OLD2, NEW2, "是否打过招呼：改看元素"),
              (OLD3, NEW3, "等弹层：轮询+元素判断"),
              (OLD4, NEW4, "发完确认：改看元素"),
              (OLD5, NEW5, "回读：改看元素")]
    for old, new, label in checks:
        n = src.count(old)
        assert n == 1, f"❌ [{label}] 命中 {n} 次（文件未改动）"
        src = src.replace(old, new, 1)
        print(f"  ✅ {label}")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字符）")


if __name__ == "__main__":
    sys.exit(main())
