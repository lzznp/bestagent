#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_intro4_20260920.py — 岗位介绍第四版（老板 2026-09-20）

修两处（实测）：
  1. `_headcount` 恒返回 0：捕获组带空白 → int() 抛异常被吞 → 加 .strip() + 多名额求和；
  2. 第一行**太长**（整个职位名都塞进去）→ 老板要"南京 java全栈 外包 10万"那种**短句**：
     城市 + 主职位名 + 方向词 + 薪资 + 名额；
  3. 明细行也过一遍"括注剥离"（防别处再漏内部口径）。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("greeting_report.py")

# ── 1. _headcount：去空白 + 多名额求和 ──────────────────────────────────────
OLD1 = '''def _headcount(text: str) -> int:
    """从 JD 文本里抓招聘人数（"招聘 12 人" / "HC 12人" / "HC 高达12个"）。"""
    import re as _re
    for pat in (r"招聘\\s*(\\d+)\\s*人", r"HC\\s*(?:高达)?\\s*(\\d+)\\s*(?:人|个)"):
        m = _re.search(pat, str(text or ""))
        if m:
            return int(m.group(1))
    return 0'''
NEW1 = '''def _headcount(text: str) -> int:
    """从 JD 文本里抓招聘人数；**多名额（双城分招）求和**。

    ⚠️ 2026-09-20 修：捕获组可能带空白（"招 6 人" → " 6 "），int() 会抛异常被吞 → 恒返回 0。
    """
    import re as _re
    s = str(text or "")
    got = [int(x.strip()) for x in _re.findall(r"招\\s*(\\d+)\\s*人", s) if x.strip().isdigit()]
    if not got:
        got = [int(x.strip()) for x in _re.findall(r"HC\\s*(?:高达)?\\s*(\\d+)", s) if x.strip().isdigit()]
    return sum(got)

'''
# ── 2. hook：短句 ──────────────────────────────────────────────────────────
OLD2 = '''    hc = max(_headcount(city), _headcount(str(jd.get("description") or "")))
    parts = [p for p in (city_main, title, salary_main) if p]
    if hc:
        parts.append(f"{hc}个HC")
    hook = " ".join(parts)

    detail: list[str] = []
    desc = [s for s in _split_lines(jd.get("description") or "") if _safe(s)]
    if desc:
        detail.extend(desc[:3])'''
NEW2 = '''    hc = _headcount(city) or _headcount(str(jd.get("description") or ""))
    # 主职位名（剥掉括注）+ 方向词（括注里前 2 个，取冒号后的部分）——老板要短句
    title_main = _re.split(r"[（(]", title)[0].strip() or title
    dirs: list[str] = []
    m_t = _re.search(r"[（(]([^（）()]*)[）)]", title)
    if m_t:
        inner = m_t.group(1).split("：")[-1].split(":")[-1]
        dirs = [d.strip() for d in _re.split(r"[、/／,，]", inner) if d.strip()][:2]
    parts = [p for p in (city_main, title_main, "/".join(dirs), salary_main) if p]
    if hc:
        parts.append(f"{hc}个HC")
    hook = " ".join(parts)

    detail: list[str] = []
    desc = [_strip_inner(s) for s in _split_lines(jd.get("description") or "")]
    desc = [s for s in desc if _safe(s)]
    if desc:
        detail.extend(desc[:3])'''


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字节）")
    for old, new, label in ((OLD1, NEW1, "1/2 修 _headcount"),
                            (OLD2, NEW2, "2/2 hook 改短句 + 明细过括注剥离")):
        n = src.count(old)
        assert n == 1, f"❌ [{label}] 命中 {n} 次（文件未改动）"
        src = src.replace(old, new, 1)
        print(f"  ✅ {label}：命中 1 次")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字节）")


if __name__ == "__main__":
    sys.exit(main())
