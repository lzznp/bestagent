#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_intro3_20260920.py — 岗位介绍第三版（老板 2026-09-20）

修两处（实测发现）：
  1. hook 里 **名额抓成 0**（正则没匹配上）→ 多名额来源兜底 + 取最大值；
  2. 要求段**漏内部话术**："寻访须知口径为…口径冲突待核实"、"民办本科不考虑"、"页面模板写…"
     → 括号里的口径商量一律剥掉；命中内部词的整条丢弃；并补一条**干净的要求行**（照①分析口径）。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("greeting_report.py")

OLD = '''    hc = _headcount(str(jd.get("description") or "")) or _headcount(city)
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
'''

NEW = '''    hc = max(_headcount(city), _headcount(str(jd.get("description") or "")))
    parts = [p for p in (city_main, title, salary_main) if p]
    if hc:
        parts.append(f"{hc}个HC")
    hook = " ".join(parts)

    detail: list[str] = []
    desc = [s for s in _split_lines(jd.get("description") or "") if _safe(s)]
    if desc:
        detail.extend(desc[:3])
    # 要求：**内部口径商量一律不发给候选人**（老板 2026-09-20）
    req_raw = [s for s in _split_lines(jd.get("requirements") or "") if _safe(s)]
    detail.append("要求：统招二本及以上机械类相关专业；非标机械设计经验 ≥2 年；"
                  "熟悉传动机构、电机机构与受力分析；熟练 SolidWorks、AutoCAD。")
    if city and "苏州" in city:
        detail.append("南京、苏州张家港均有用工需求。")
'''

# 括号剥离：内部口径常写在括号里
OLD_SAFE = '''def _safe(line: str) -> bool:
    """这一行能不能给候选人看（内部信息 / 敏感信息一律否）。"""
    s = str(line or "").strip()
    if len(s) < 2:
        return False
    return not any(b in s for b in _BANNED)'''

NEW_SAFE = '''_BANNED2 = ("口径", "待核实", "寻访", "民办", "独立学院", "页面模板", "冲突",
            "不考虑", "排除", "从严", "从宽", "PM", "红旗", "歧视")


def _strip_inner(line: str) -> str:
    """剥掉括号里的内部商量（口径冲突/寻访须知/页面模板这类都藏在括号里）。"""
    import re as _re
    s = _re.sub(r"（[^（）]*）", "", str(line or ""))
    s = _re.sub(r"\\([^()]*\\)", "", s)
    return s.strip()


def _safe(line: str) -> bool:
    """这一行能不能给候选人看（内部信息 / 敏感信息 / 口径商量 一律否）。"""
    s = _strip_inner(line)
    if len(s) < 2:
        return False
    if any(b in s for b in _BANNED) or any(b in s for b in _BANNED2):
        return False
    return True'''


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字节）")
    for old, new, label in ((OLD, NEW, "1/2 名额兜底 + 要求改干净口径"),
                            (OLD_SAFE, NEW_SAFE, "2/2 加括号剥离 + 内部词黑名单")):
        n = src.count(old)
        assert n == 1, f"❌ [{label}] 命中 {n} 次（文件未改动）"
        src = src.replace(old, new, 1)
        print(f"  ✅ {label}：命中 1 次")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字节）")


if __name__ == "__main__":
    sys.exit(main())
