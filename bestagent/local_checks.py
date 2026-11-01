#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""local_checks.py — 纯本地产物校验（0 花费）：替代"让 LLM 写完自己回读+列目录核对"

为什么要它（2026-09-14 实测一次①岗位分析 8 轮 / 139,075 token）：
  · 其中 2 轮是"写完又回读自己写的 JSON + 两次列目录核对产物"，花了 43,159（31%），
    而它查的东西是**纯机械事实**：文件在不在、JSON 能不能解析、字段齐不齐、分数加不加得上。
  · 这类判断"代码算得比它准、还免费"（§2.4 纪律：能本地代码处理的就不让它操作）。
  → 所以：**校验挪本地，并把结果贴进对话**（老板要的"看得见的确认"照旧有，只是不用它花钱去查）。

边界（别越界）：
  · 本模块只做**机械校验**（存在/可解析/字段齐/算术自洽），**不判断内容好坏**——
    "这单该不该接""分数给得合不合理"是 LLM 的判断，代码不许替它拍板（§2.4 纪律②）。
  · 校验不过 ≠ 失败：只是把事实摆出来，由老板/小猎决定重跑还是接受。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ① 岗前分析报告：analyze_job.txt 的契约（字段不增不减）
ANALYZE_TOP_KEYS = ("jd_extracted", "progress", "score", "recommendation", "search_keywords")
ANALYZE_JD_KEYS = ("job_title", "company", "city", "salary", "requirements", "description")
ANALYZE_SCORE_KEYS = ("total", "level", "advice", "details", "progress_impact", "risks")
ANALYZE_DIMENSIONS = ("commission", "hc_count", "freshness", "upstream", "difficulty")
ANALYZE_LEVELS = ("顶级", "优质", "普通", "放弃")
ANALYZE_RECOMMENDATIONS = ("接单", "沟通", "放弃")


def _is_nonempty(x) -> bool:
    if x is None:
        return False
    if isinstance(x, str):
        return bool(x.strip())
    if isinstance(x, (list, dict)):
        return len(x) > 0
    return True


def check_analyze(report: Path, expect_html: bool = True) -> dict:
    """校验①岗前分析报告 + 它的过程文档。返回 {ok, problems, warnings, notes, summary}。

    ok=False 仅表示"有机械问题"（字段缺/算术不符/口径越界）；过程文档缺失只算 warning
    （展示层缺了不阻塞，且 auto_job 那条路本来就不产 HTML）。
    `expect_html=False` 供 auto_job / m1_run 那条路复用（不产过程文档是它的正常形状）。
    """
    problems: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    report = Path(report)

    if not report.exists():
        return {"ok": False, "problems": [f"报告文件不存在：{report}"], "warnings": [], "notes": [],
                "summary": "❌ 本地校验：报告文件没生成"}

    try:
        data = json.loads(report.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "problems": [f"JSON 解析失败：{exc}"], "warnings": [], "notes": [],
                "summary": f"❌ 本地校验：{report.name} 不是合法 JSON（{exc}）"}

    if not isinstance(data, dict):
        return {"ok": False, "problems": ["顶层不是对象"], "warnings": [], "notes": [],
                "summary": "❌ 本地校验：报告顶层不是 JSON 对象"}

    # 1) 顶层字段齐不齐
    missing = [k for k in ANALYZE_TOP_KEYS if k not in data]
    if missing:
        problems.append("缺顶层字段：" + "、".join(missing))

    # 2) jd_extracted 六个子字段非空
    jd = data.get("jd_extracted") or {}
    if not isinstance(jd, dict):
        problems.append("jd_extracted 不是对象")
    else:
        empty = [k for k in ANALYZE_JD_KEYS if not _is_nonempty(jd.get(k))]
        if empty:
            problems.append("jd_extracted 空字段：" + "、".join(empty))
        if _is_nonempty(jd.get("job_title")):
            notes.append(f"岗位：{str(jd['job_title'])[:30]}")

    # 3) score：总分是整数、各维度 0-5、**各项之和 == total**（机械算术，代码比它准）
    score = data.get("score") or {}
    if not isinstance(score, dict):
        problems.append("score 不是对象")
    else:
        miss_s = [k for k in ANALYZE_SCORE_KEYS if k not in score]
        if miss_s:
            problems.append("score 缺字段：" + "、".join(miss_s))
        total = score.get("total")
        if not isinstance(total, int) or isinstance(total, bool) or not (0 <= total <= 25):
            problems.append(f"score.total 不是 0-25 的整数：{total!r}")
        if _is_nonempty(score.get("level")) and score.get("level") not in ANALYZE_LEVELS:
            problems.append(f"score.level 不在 {ANALYZE_LEVELS}：{score.get('level')!r}")
        details = score.get("details") or {}
        if not isinstance(details, dict):
            problems.append("score.details 不是对象")
        else:
            miss_d = [k for k in ANALYZE_DIMENSIONS if k not in details]
            if miss_d:
                problems.append("score.details 缺维度：" + "、".join(miss_d))
            dim_sum, bad_dim = 0, []
            for k in ANALYZE_DIMENSIONS:
                v = (details.get(k) or {}).get("score")
                if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 5:
                    dim_sum += v
                else:
                    bad_dim.append(f"{k}={v!r}")
            if bad_dim:
                problems.append("维度分不是 0-5 整数：" + "、".join(bad_dim))
            elif isinstance(total, int) and not isinstance(total, bool):
                if dim_sum != total:
                    problems.append(f"算术不符：五项之和 {dim_sum} ≠ 总分 {total}")
                else:
                    notes.append(f"总分 {total}/25（五项之和 {dim_sum} ✓）")
        if not _is_nonempty(score.get("risks")):
            problems.append("score.risks 为空（风险清单是给老板看的必填项）")

    # 4) 接单判断必须在三选一里（这是给老板拍板的话，不能是别的说法）
    rec = data.get("recommendation")
    if rec not in ANALYZE_RECOMMENDATIONS:
        problems.append(f"recommendation 不在 {ANALYZE_RECOMMENDATIONS}：{rec!r}")
    else:
        notes.append(f"接单判断：{rec}")

    # 5) 过程文档在不在（展示层；缺失只算 warning，不阻塞）
    if expect_html:
        html = report.with_name(report.stem + "_过程.html")
        if not html.exists():
            # 旧岗命名不统一（如 岗前分析过程_<ts>.html）→ 退回按"含'过程'的 html"找同目录
            cands = [p for p in report.parent.glob("*.html") if "过程" in p.name]
            html = cands[0] if cands else html
        if html.exists() and html.stat().st_size > 0:
            notes.append(f"过程文档 ✓（{html.name}，{html.stat().st_size} 字节）")
            # 第二刀（2026-09-15）：过程网页现在是**本地渲染**的 → 顺手把"过程叙述"的长度用量量出来，
            # 让预算**看得见**（老板要的确认照旧有，只是不用花钱去问小猎）。缺 report_html 就跳过，不阻塞。
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import report_html
                _proc, usage = report_html.clip_process(data)
                if usage["present"]:
                    txt = f"过程叙述 {usage['total']}/{usage['budget']} 字"
                    if usage["truncated"]:
                        txt += "（超预算已截断：" + "、".join(usage["truncated"]) + "）"
                    notes.append(txt)
                else:
                    notes.append("过程叙述：老报告没有 process 块（下次①分析自动带上）")
            except Exception:
                pass
        else:
            warnings.append(f"过程文档缺失：{html.name}")

    ok = not problems
    head = "✅ 本地校验通过" if ok else f"⚠️ 本地校验发现 {len(problems)} 处问题"
    if warnings:
        head += f"（另有 {len(warnings)} 处提醒）"
    summary = f"{head}：{'｜'.join(notes)}" if notes else head
    if problems:
        summary += "｜" + "；".join(problems)
    if warnings:
        summary += "｜提醒：" + "；".join(warnings)
    return {"ok": ok, "problems": problems, "warnings": warnings, "notes": notes,
            "summary": summary}


# ═══════════ ② 采集计划（collect_plan_*.json）校验（v1.8.8）═══════════════
# 老板 2026-09-15 要的"能力体检"里最便宜的那半场：**翻译考试**。
# 病根（实测）：`build_step2_plan_task` 只给小猎 JD+①分析+方法论，**从来没把配方表的可选值给它**
#   → 它只能**猜**（例如把 JD 的"5-8 年"写成 `years=5-8年`，而猎聘根本没有这个档）→
#   于是"它年限迷糊"的真因是**我们没给事实**，不是它笨（§2.4 纪律②：别让它干查表的活）。
# 治法（两边一起）：① 任务文本里**把配方表的合法值一次给全**（`recipe_options_brief`）；
#   ② 拿到计划后**本地判分**（`check_collect_spec`）—— 值不在配方表里 = 硬凑，当场贴给老板。
# ⚠️ 本模块只判**机械事实**（组存不存在 / 值合不合法 / 关键字形态），**不替老板决定该怎么筛**。
COND_FREE_TEXT = ("自由文本", "自由数字", "待测", "自由文本 / 全部")


def _recipes_path(path=None) -> Path:
    """配方表位置：显式传 > BROWSER_AGENT_PATH 环境变量 > 仓库顶层 bridge-agent/agent/。"""
    if path:
        return Path(path)
    import os
    b = os.environ.get("BROWSER_AGENT_PATH")
    base = Path(b) if b else (Path(__file__).resolve().parent.parent / "bridge-agent")
    return base / "agent" / "page_recipes.json"


def load_cond_groups(path=None) -> dict[str, dict]:
    """读配方表里的"找简历条件组"：{group_id: {name, type, options(列表或None), status, pits}}。

    读不到 → 返回 {}（校验**降级**成"只说形态、不判取值"，绝不抛异常、绝不阻塞计划）。
    """
    p = _recipes_path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    pages = data.get("pages") or {}
    page = pages.get("h.liepin.com/search/getConditionItem") or (next(iter(pages.values())) if pages else {})
    out: dict[str, dict] = {}
    for g in (page.get("groups") or []):
        gid = g.get("id")
        if not gid:
            continue
        opt = g.get("options")
        out[gid] = {"name": g.get("name") or gid,
                    "type": g.get("type") or "",
                    "options": opt if isinstance(opt, list) else None,
                    "options_raw": opt if isinstance(opt, str) else "",
                    "status": g.get("status") or "",
                    "pits": g.get("pits") or []}
    return out


def _digits(s) -> set:
    return set(re.findall(r"\d+", str(s or "")))


def _nearest_values(value: str, options: list[str], k: int = 2) -> list[str]:
    """从合法档里挑最接近的（**数字重合度**优先，其次子串包含）→ 给"你大概想说的是这个"建议。"""
    v = _digits(value)
    scored = []
    for o in options:
        od = _digits(o)
        if v and od:
            score = len(v & od)
        else:
            score = 1 if (str(value) and (str(value) in str(o) or str(o) in str(value))) else 0
        scored.append((score, o))
    scored.sort(key=lambda x: -x[0])
    return [o for s, o in scored if s > 0][:k]


def recipe_options_brief(path=None, max_lines: int = 16) -> str:
    """给 agent 看的「可选条件清单」——**单源 = 配方表**，照抄合法值、别自己编。

    这解决的是实测病根：它猜 `years=5-8年`（猎聘没这个档）。给了清单，它就只能"选"，不必"编"。
    """
    groups = load_cond_groups(path)
    if not groups:
        return "\n【可选条件清单】**读不到配方表**（bridge-agent/agent/page_recipes.json）——条件请只写你有把握的，宁可留空。\n"
    ok_lines, pending = [], []
    for gid, g in groups.items():
        if gid in ("clear", "expand", "search"):
            continue
        if g["status"] == "pending":
            pending.append(g["name"])
            continue
        if g["options"]:
            ok_lines.append(f"- `{gid}`｜{g['name']}｜只能填：{' / '.join(g['options'])}")
        else:
            ok_lines.append(f"- `{gid}`｜{g['name']}｜{g['options_raw'] or '自由文本'}")
        if len(ok_lines) >= max_lines:
            break
    body = "\n".join(ok_lines)
    pend = ("\n- ⚠️ **配方表里还没实测通的组**（别写进计划）：" + "、".join(pending)) if pending else ""
    return (
        "\n【可选条件清单（**照抄这里的合法值，别自己编**；来源 = 配方表 page_recipes.json 实测）】\n"
        f"{body}{pend}\n"
        "⚠️ 三条已知坑：① `keyword` 里**空格分隔 = 全部命中（AND）**，词内别叠同义词/多词，否则极易 0 命中"
        "（同义叫法要么拆成多条关键字、要么改用「包含任意」——⚠️ 目前**代码只支持「全部」**）；"
        "② `years` **没有\"5-8年\"这种档**——JD 的年限若落在档与档之间，取**最接近**的档，别自己造值；"
        "③ `activity` 是**「今天活跃」不是「今日活跃」**，应届岗慎用（应届普遍不活跃，会筛空）。\n"
        "⚠️ 条件里**只放硬门槛**（JD 写了「必须有」的）；「有更好」的优先条件**一律不写**，否则误杀。\n"
    )


def check_collect_spec(plan: Path, path=None) -> dict:
    """校验②采集计划（collect_plan_*.json）：关键字形态 + 条件组存在性 + 取值是否合法。

    返回 {ok, problems, warnings, notes, summary}（与 check_analyze 同形，便于面板统一贴）。
    ok=False 只表示"有机械问题"（组不存在/值不在合法档/格式错），不代表这单不该这么做。
    """
    problems: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    plan = Path(plan)
    if not plan.exists():
        return {"ok": False, "problems": [f"计划文件不存在：{plan}"], "warnings": [], "notes": [],
                "summary": "❌ 本地校验：采集计划文件没生成"}
    try:
        d = json.loads(plan.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "problems": [f"JSON 解析失败：{exc}"], "warnings": [], "notes": [],
                "summary": f"❌ 本地校验：{plan.name} 不是合法 JSON"}
    if not isinstance(d, dict):
        return {"ok": False, "problems": ["顶层不是对象"], "warnings": [], "notes": [],
                "summary": "❌ 本地校验：采集计划顶层不是 JSON 对象"}

    for k in ("keywords", "conds"):
        if k not in d:
            problems.append(f"缺字段：{k}")

    # 1) 关键字形态（猎聘 = 全部命中 AND）
    kws = [str(x).strip() for x in (d.get("keywords") or []) if str(x).strip()]
    if not kws:
        problems.append("keywords 为空（没有关键字就没法搜）")
    for kw in kws:
        n = len(kw.split())
        if n > 3:
            warnings.append(f"关键字「{kw}」有 {n} 个空格词——猎聘是**全部命中 AND**，词太密极易 0 命中")
        if len(kw) > 40:
            warnings.append(f"关键字「{kw}」太长（{len(kw)} 字），像把一组词拼在一起了")
    if len(kws) > 6:
        warnings.append(f"关键字 {len(kws)} 条——每条=1 次搜索（本地限速 search 80/天、轮间 8-20 秒），轮数多会拖很久")
    if kws:
        notes.append(f"关键字 {len(kws)} 条")

    # 2) 条件：组存不存在 + 取值合不合法（单源 = 配方表）
    groups = load_cond_groups(path)
    conds = d.get("conds") or []
    if not isinstance(conds, list):
        problems.append("conds 不是数组")
        conds = []
    for c in conds:
        s = str(c)
        gid, sep, val = s.partition("=")
        gid, val = gid.strip(), val.strip()
        if not sep or not gid or not val:
            problems.append(f"条件格式应为 group_id=value：{s!r}")
            continue
        if not groups:
            warnings.append(f"读不到配方表 → 无法核对 {gid}={val}（只做了格式检查）")
            continue
        g = groups.get(gid)
        if g is None:
            problems.append(f"配方表里没有条件组 `{gid}`（{s}）——条件组名写错了？")
            continue
        if g["status"] == "pending":
            warnings.append(f"`{gid}`（{g['name']}）配方**还没实测通**，写进计划很可能跑不起来")
        if g["options"] and val not in g["options"]:
            near = _nearest_values(val, g["options"])
            hint = ("，最接近的合法档：" + " / ".join(near)) if near else ""
            extra = ""
            if gid == "years":
                extra = ("；或用「自定义」（⚠️ **点开之后怎么填起止，配方表里没记 —— 已知洞，先别用**）")
            problems.append(f"`{gid}={val}` **不在配方表的合法档里**{hint}{extra}")
        elif g["options"]:
            notes.append(f"{gid}={val} ✓")
    n_cond = len([c for c in conds if "=" in str(c)])
    if n_cond:
        notes.append(f"条件 {n_cond} 条")

    ok = not problems
    head = "✅ 本地校验通过（采集计划）" if ok else f"⚠️ 本地校验发现 {len(problems)} 处问题（采集计划）"
    if warnings:
        head += f"（另有 {len(warnings)} 处提醒）"
    summary = f"{head}：{'｜'.join(notes)}" if notes else head
    if problems:
        summary += "｜" + "；".join(problems)
    if warnings:
        summary += "｜提醒：" + "；".join(warnings)
    return {"ok": ok, "problems": problems, "warnings": warnings, "notes": notes, "summary": summary}


# 同一条件组在猎聘上大多是"单选/单选面板"——**给多个值 = 要求同时满足**（且平台多不认）
SINGLE_VALUE_GROUPS = ("city_current", "city_expected", "education", "years", "activity",
                       "tongzhao", "school", "jobstatus", "gender", "jobhop")


def check_judge_card(plan: dict) -> tuple[list, list]:
    """判据卡体检（v1.9.2，本地、0 花费）：**抓那些会让整轮空跑的坑**。

    实测踩到的两个（2026-09-16）：
      ① **同一条件组给多个值**：小猎写了 `["city_current=南京", "city_current=苏州"]`
         → 猎聘那边 = "既在南京又在苏州" → **0 命中、整轮空跑**。正确做法是**分轮**（一城一轮）。
      ② **行业词写连写复合词**（如"叉车AGV"）：卡片上更常见的是分开写（"叉车"/"AGV"）
         → 连写那个命不中 → 提示拆成单字/短词。
    返回 (problems, warnings)。
    """
    problems: list[str] = []
    warnings: list[str] = []
    j = (plan or {}).get("judge") or {}
    if not isinstance(j, dict) or not any(j.get(k) for k in ("industry", "companies", "skills", "role")):
        problems.append("计划里**没有 `judge` 判据卡**（或字段全空）→ 采集会用兜底判据、排序不贴本岗；"
                        "请重新出计划并要求它给 judge")
        return problems, warnings
    groups: dict[str, list[str]] = {}
    for c in (plan.get("conds") or []):
        gid, sep, val = str(c).partition("=")
        if sep:
            groups.setdefault(gid.strip(), []).append(val.strip())
    for gid, vals in groups.items():
        if len(vals) > 1 and gid in SINGLE_VALUE_GROUPS:
            problems.append(
                f"`{gid}` 给了 {len(vals)} 个值（{'/'.join(vals)}）——猎聘会把它们当**同时满足**，"
                f"八成 0 命中。**正确做法：一个值一轮**（比如南京跑一轮、苏州再跑一轮），不要在同一轮里并排。")
    for w in (j.get("industry") or []) + (j.get("skills") or []) + (j.get("role") or []):
        w = str(w)
        if len(w) >= 5 and any(ch.isascii() and ch.isalpha() for ch in w) is False and "AGV" not in w:
            continue      # 中文长词不一定是问题（如"物流自动化"）
        if len(w) >= 4 and w.upper().endswith("AGV") and w.upper() != "AGV":
            warnings.append(f"行业词「{w}」是**连写复合词**——卡片上更常见分开写（如「叉车」「AGV」）→ "
                            f"建议拆成短词，否则命不中")
    return problems, warnings


def check_probe_plan(plan: Path, path=None) -> dict:
    """校验②搜索体检计划（`search_probe_plan_*.json`）：**逐轮**关键字形态 + 条件合法性。

    为什么要有它：结构问题（没 rounds / 一轮塞多个关键字）由 `search_rounds.py` **硬失败**兜住；
    但"条件值不在配方表合法档"若等真开了浏览器才发现，就白烧一次搜索 —— 本地先判，0 花费。
    规则与 `check_collect_spec` 同一套；**暂不抽公共函数**（那条老路径有 111 条断言压着，先不动它）。
    """
    problems: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    plan = Path(plan)
    if not plan.exists():
        return {"ok": False, "problems": [f"计划文件不存在：{plan}"], "warnings": [], "notes": [],
                "summary": "❌ 本地校验：体检计划文件没生成"}
    try:
        d = json.loads(plan.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "problems": [f"JSON 解析失败：{exc}"], "warnings": [], "notes": [],
                "summary": f"❌ 本地校验：{plan.name} 不是合法 JSON"}
    rounds = d.get("rounds") if isinstance(d, dict) else None
    if not isinstance(rounds, list) or not rounds:
        return {"ok": False, "problems": ["没有 rounds（应是非空数组）"], "warnings": [], "notes": [],
                "summary": "❌ 本地校验：体检计划里没有 rounds"}

    groups = load_cond_groups(path)
    seen: list[tuple] = []
    for i, r in enumerate(rounds, 1):
        if not isinstance(r, dict):
            problems.append(f"第 {i} 轮不是对象")
            continue
        kw = str(r.get("keyword") or "").strip()
        kws = [str(x).strip() for x in (r.get("keywords") or []) if str(x).strip()]
        if not kw and kws:
            if len(kws) > 1:
                problems.append(f"第 {i} 轮塞了 {len(kws)} 个关键字——**一轮只放 1 个**（多关键字拆成多轮，"
                                "否则报告里分不清是哪条关键字的效果）")
            kw = kws[0] if kws else ""
        if not kw:
            problems.append(f"第 {i} 轮没有 keyword")
        else:
            n = len(kw.split())
            if n > 3:
                warnings.append(f"第 {i} 轮关键字「{kw}」有 {n} 个空格词——猎聘是**全部命中 AND**，极易 0 命中")
            if len(kw) > 40:
                warnings.append(f"第 {i} 轮关键字太长（{len(kw)} 字），像把一组词拼在一起了")
        conds = [str(c).strip() for c in (r.get("conds") or []) if str(c).strip()]
        for c in conds:
            gid, sep, val = c.partition("=")
            gid, val = gid.strip(), val.strip()
            if not sep or not gid or not val:
                problems.append(f"第 {i} 轮条件格式应为 group_id=value：{c!r}")
                continue
            if not groups:
                warnings.append(f"读不到配方表 → 无法核对 {gid}={val}（只做了格式检查）")
                continue
            g = groups.get(gid)
            if g is None:
                problems.append(f"第 {i} 轮配方表里没有条件组 `{gid}`（{c}）——组名写错了？")
                continue
            if g["status"] == "pending":
                warnings.append(f"第 {i} 轮 `{gid}`（{g['name']}）配方**还没实测通**，很可能跑不起来")
            if g["options"] and val not in g["options"]:
                near = _nearest_values(val, g["options"])
                hint = ("，最接近的合法档：" + " / ".join(near)) if near else ""
                problems.append(f"第 {i} 轮 `{gid}={val}` **不在配方表的合法档里**{hint}")
        sig = (kw, tuple(conds))
        if seen and sig == seen[-1]:
            warnings.append(f"第 {i} 轮跟上一轮**一模一样**（关键字+条件全同）→ 看不出改了什么，白烧一次搜索")
        seen.append(sig)
        notes.append(f"第{i}轮：{kw or '（无关键字）'}｜条件 {len(conds)} 条")

    if len(rounds) > 5:
        warnings.append(f"计划有 {len(rounds)} 轮——脚本硬顶 5 轮（多出来的不会被跑）")

    ok = not problems
    head = "✅ 本地校验通过（搜索体检计划）" if ok else f"⚠️ 本地校验发现 {len(problems)} 处问题（搜索体检计划）"
    if warnings:
        head += f"（另有 {len(warnings)} 处提醒）"
    summary = f"{head}：{'｜'.join(notes)}" if notes else head
    if problems:
        summary += "｜" + "；".join(problems)
    if warnings:
        summary += "｜提醒：" + "；".join(warnings)
    return {"ok": ok, "problems": problems, "warnings": warnings, "notes": notes, "summary": summary}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for arg in sys.argv[1:]:
        _p = Path(arg)
        r = check_collect_spec(_p) if _p.name.startswith("collect_plan") else check_analyze(_p)
        print(r["summary"])
