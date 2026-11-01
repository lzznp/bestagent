#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_intro2_20260920.py — 修"岗位介绍"的取数来源（老板 2026-09-20 第二次口径）

问题（实测）：第一版从 jd.txt 原文抓详细段 → 混进禾蛙网站导航 + **内部信息**
（预计佣金 / "客户最看重男生优先" / 矛盾年限 / 累计接单数）。**绝不能发给候选人**。

改法：详细段只从 **①岗前分析的 jd_extracted.description / requirements** 取（干净口径），
      并加**合规过滤器**：性别、佣金、回款、接单等内部词 → 整条丢掉。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("greeting_report.py")

BLOCK_START = 'def _uniq_lines(text: str) -> list[str]:'
BLOCK_END = 'def intro_for(item: dict, ji: dict) -> str:'

NEW_BLOCK = '''def _split_lines(text: str) -> list[str]:
    """把一段中文长句切成短行：按 ①1）(1) ①②③ 及分号分隔（老板 2026-09-20：别一大坨）。"""
    import re as _re
    s = str(text or "").replace("\\r", "")
    s = _re.sub(r"(?=[①②③④⑤⑥⑦⑧⑨⑩])", "\\n", s)
    parts = _re.split(r"[；;\\n]", s)
    return [p.strip() for p in parts if p.strip()]


def _headcount(text: str) -> int:
    """从 JD 文本里抓招聘人数（"招聘 12 人" / "HC 12人" / "HC 高达12个"）。"""
    import re as _re
    for pat in (r"招聘\\s*(\\d+)\\s*人", r"HC\\s*(?:高达)?\\s*(\\d+)\\s*(?:人|个)"):
        m = _re.search(pat, str(text or ""))
        if m:
            return int(m.group(1))
    return 0


# 🔴 合规/内部信息黑名单：命中就**整条丢掉**（不许发给候选人）
_BANNED = ("男生优先", "女生优先", "性别", "婚育", "已婚", "未婚", "孕",
           "佣金", "回款", "接单", "offer数", "面试及推荐", "顾问", "禾蛙", "禾禾",
           "客户", "发单方", "订单", "蛙贝", "咨询", "客服", "反馈")


def _safe(line: str) -> bool:
    """这一行能不能给候选人看（内部信息 / 敏感信息一律否）。"""
    s = str(line or "").strip()
    if len(s) < 2:
        return False
    return not any(b in s for b in _BANNED)


def _jd_facts(job_code: str, base: Path) -> dict:
    """岗位事实：**只从 ①岗前分析** 取（干净口径），不碰 jd.txt 原文（那里混着网站导航）。"""
    reps = base / job_code / "reports"
    ana = sorted(reps.glob("analyze_*.json")) if reps.exists() else []
    if not ana:
        return {}
    try:
        import json as _json
        d = _json.loads(ana[-1].read_text(encoding="utf-8-sig"))
        return d.get("jd_extracted") or {}
    except Exception:  # noqa: BLE001
        return {}


def job_intro(job_code: str, jm: dict, base: Path, jd_text: str = "") -> dict:
    """本岗共用的岗位介绍（**报告生成时写死**；小猎照发、不许改）。

    · 第一行（hook）= 地点 职位 薪资 名额 —— 候选人端预览只看得到**最后一条的前 15 字**，
      所以这句要**自解释**（老板 2026-09-20 口径）；
    · 详细段 = 只取①分析里的 description + requirements（过滤内部/敏感信息），每行一句；
    · **纯本地拼装，0 token**；数字全部照抄 JD/分析，不许自己算。
    """
    import re as _re
    jd = _jd_facts(job_code, base) or {}
    city = str(jd.get("city") or jm.get("city") or "").strip()
    city_main = _re.split(r"[（(；;]", city)[0].strip() if city else ""
    title = str(jd.get("job_title") or jm.get("title") or "").strip()
    salary = str(jd.get("salary") or jm.get("salary") or "").strip()
    salary_main = _re.split(r"[（(；;，,]", salary)[0].strip() if salary else ""
    hc = _headcount(str(jd.get("description") or "")) or _headcount(city)
    parts = [p for p in (city_main, title, salary_main) if p]
    if hc:
        parts.append(f"{hc}个HC")
    hook = " ".join(parts)

    detail: list[str] = []
    desc = [s for s in _split_lines(jd.get("description") or "") if _safe(s)]
    if desc:
        detail.extend(desc[:3])
    reqs = [s for s in _split_lines(jd.get("requirements") or "") if _safe(s)]
    reqs = [r for r in reqs if "男生优先" not in r]
    if reqs:
        detail.append("要求：" + "；".join(reqs[:4]) + "。")
    if city and "苏州" in city:
        detail.append("南京、苏州张家港均有用工需求。")
    text = hook + ("\\n" + "\\n".join(detail) if detail else "")
    return {"hook": hook, "detail": "\\n".join(detail), "text": text,
            "intro_msg": text, "headcount": hc}


'''


def _replace_block(src: str) -> str:
    i = src.find(BLOCK_START)
    j = src.find(BLOCK_END)
    assert i > 0 and j > i, "❌ 找不到要替换的函数块（文件未改动）"
    old = src[i:j]
    assert "def _uniq_lines" in old and "def job_intro" in old, "❌ 块内容不匹配（文件未改动）"
    print(f"  ✅ 1/2 替换 intro 函数块（{len(old)} → {len(NEW_BLOCK)} 字节）")
    return src[:i] + NEW_BLOCK + src[j:]


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字节）")
    src = _replace_block(src)
    old_call = "JOB_INTRO = job_intro(job_code, jm, _jd_text)"
    new_call = "JOB_INTRO = job_intro(job_code, jm, base, _jd_text)"
    n = src.count(old_call)
    assert n == 1, f"❌ 调用处命中 {n} 次（文件未改动）"
    src = src.replace(old_call, new_call, 1)
    print("  ✅ 2/2 调用处加 base 参数")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字节）")


if __name__ == "__main__":
    sys.exit(main())
