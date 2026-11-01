#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_intro_20260920.py — 给打招呼报告加"岗位介绍"字段（老板 2026-09-20 口径）

背景（老板原话要点）：
  · 打招呼和发岗位情况**一起发**（好让候选人知道是哪个岗位；也方便小猎日后查回复时对上号）
  · 岗位介绍**由打招呼报告生成**，小猎只负责照发，**不许临时编写**
  · 测试期**不暴露 AI 身份**
  · 格式：第一行 = 地点/职位/方向/薪资/名额（前 15 字要被候选人看到），后面详细 + 邀请语

改法（每处必须**恰好命中 1 次**，否则整文件不动）：
  1. 在 `_jlist` 之前插入 intro 生成函数
  2. `item` 里加 `intro_msg`（每人）
  3. 报告里加 `job_intro`（本岗共用）
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("greeting_report.py")

# ── 1. 插入 intro 生成函数 ─────────────────────────────────────────────────
ANCHOR1 = 'def _jlist(x) -> list[str]:'
NEW_FUNCS = '''def _uniq_lines(text: str) -> list[str]:
    """按行去重（不去空行；老板 2026-09-20：带重复的 HC 句子别重复说）。"""
    seen: set[str] = set()
    out: list[str] = []
    for ln in str(text or "").replace("\\r", "").split("\\n"):
        s = ln.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _headcount(text: str) -> int:
    """从 JD 文本里抓招聘人数（"招聘 12 人" / "HC 12人" / "HC 高达12个"）。"""
    import re as _re
    for pat in (r"招聘\\s*(\\d+)\\s*人", r"HC\\s*(?:高达)?\\s*(\\d+)\\s*(?:人|个)"):
        m = _re.search(pat, str(text or ""))
        if m:
            return int(m.group(1))
    return 0


def _is_good_hook(s: str) -> bool:
    """候选行是否适合放第一行（地点/职位/方向/薪资/名额那类），太短或太长的都不当。"""
    return 4 <= len(str(s or "").strip()) <= 48


def job_intro(job_code: str, jm: dict, jd_text: str = "") -> dict:
    """本岗共用的岗位介绍（**报告生成时写死**；小猎照发、不许改）。

    返回 {"hook", "detail", "text", "intro_msg"}；**纯本地拼装，0 token**，数字全部来自
    ①岗前分析 / JD 原文，不许自己算。
    """
    import re as _re
    city = str(jm.get("city") or "").strip()
    # 城市取主城（JD 里常是"南京（...，招6人）；苏州（...）"这种长句）
    city_main = _re.split(r"[（(；;]", city)[0].strip() if city else ""
    title = str(jm.get("title") or "").strip()
    salary = str(jm.get("salary") or "").strip()
    salary_main = _re.split(r"[（(；;，,]", salary)[0].strip() if salary else ""
    jd = jm.get("description") or jd_text or ""
    hc = _headcount(jd_text) or _headcount(city)
    parts = [p for p in (city_main, title, salary_main) if p]
    if hc:
        parts.append(f"{hc}个HC")
    hook = " ".join(parts)
    detail_lines = [s for s in _uniq_lines(jd) if not _is_good_hook(s)]
    detail = "\\n".join(detail_lines)
    text = (hook + "\\n" + detail) if detail else hook
    return {"hook": hook, "detail": detail, "text": text, "intro_msg": text, "headcount": hc}


def intro_for(item: dict, ji: dict) -> str:
    """某人的岗位介绍 = 本岗共用那段 + 一句针对他的邀请语。"""
    cand = str(item.get("name") or "").strip() or "您好"
    pts = item.get("match_points") or []
    why = str(pts[0])[:42] if pts else ""
    tail = (f"{cand}：看到您{why}，跟这个岗位挺对口，方便聊聊吗？"
            if why else f"{cand}：看到您的经历跟这个岗位挺对口，方便聊聊吗？")
    base = str(ji.get("intro_msg") or "").strip()
    return (base + "\\n" + tail) if base else tail


'''

# ── 2. item 里加 intro_msg ────────────────────────────────────────────────
ANCHOR2 = '"candidate_id": r["id"], "name": r.get("display_name") or "",'
NEW2 = ('"candidate_id": r["id"], "name": r.get("display_name") or "",\n'
        '            "intro_msg": _INTRO_TMPL,   # 岗位介绍（报告生成时写死；小猎照抄）')

# ── 3. 报告里加 job_intro + 循环前算一次 ───────────────────────────────────
ANCHOR3 = '    main, waiting, replied, excluded = [], [], [], 0'
NEW3 = ('    # 岗位介绍：本岗共用一段（**报告生成时写死**，小猎只抄不想）\n'
        '    try:\n'
        '        _jd_text = (base / job_code / "jd.txt").read_text(encoding="utf-8", errors="replace")\n'
        '    except Exception:  # noqa: BLE001\n'
        '        _jd_text = ""\n'
        '    JOB_INTRO = job_intro(job_code, jm, _jd_text)\n'
        '\n'
        '    main, waiting, replied, excluded = [], [], [], 0')

ANCHOR4 = '            "daily": daily, "main": main, "waiting": waiting, "follow_up_due": due,'
NEW4 = ('            "job_intro": JOB_INTRO,\n'
        '            "daily": daily, "main": main, "waiting": waiting, "follow_up_due": due,')


def _apply(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    assert n == 1, f"❌ [{label}] 命中 {n} 次（必须恰好 1 次）——文件未改动"
    print(f"  ✅ {label}：命中 1 次")
    return text.replace(old, new, 1)


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字节）")
    src = _apply(src, ANCHOR1, NEW_FUNCS + ANCHOR1, "1/4 插入 intro 函数")
    src = _apply(src, ANCHOR2, NEW2, "2/4 item 加 intro_msg")
    src = _apply(src, ANCHOR3, NEW3, "3/4 循环前算 JOB_INTRO")
    # 每人那句邀请语：在 item 建好之后补（item 字典结尾处）
    src = _apply(src, '            "new_today": str(r.get("first_seen_at") or "").startswith(today),\n        }',
                 '            "new_today": str(r.get("first_seen_at") or "").startswith(today),\n        }\n'
                 '        item["intro_msg"] = intro_for(item, JOB_INTRO)   # 本岗那段 + 一句针对他的邀请语', "4a/4 每人邀请语")
    src = _apply(src, ANCHOR4, NEW4, "4b/4 报告加 job_intro")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字节）")


if __name__ == "__main__":
    sys.exit(main())
