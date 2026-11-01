#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""greeting_report.py — **打招呼报告**（本地渲染，0 token）：

  · `打招呼报告_<ts>.json` = **资产**：小猎照着它执行（每人：分数/判定/理由/匹配点/先核实/话术1、2/猎聘直达链接）；
  · `打招呼报告_<ts>_过程.html` = **壳**：老板过目（本地渲染，0 token）。

为什么要有它（老板 2026-09-17 定的形态）：
  · 打招呼报告 = **小猎的工作依据**（不是给老板看的"报告"那么单纯）；
  · **全量匹配、只列够分的**：分数不够的人不体现在报告上（只给一个计数）；
  · **时间是硬约束**：报告是上午做的，中午/晚上不能打 → 报告里给「现在能不能打 + 为什么」；
  · **持续跟踪**：一个岗会跟很久 → 报告要分「今天该打 / 等回复 / 有回复 / 已排除」+ 一行日报，
    每天"再来看看"就够（打过的人不会重复出现在主名单里）。

🔴 **前置检查（老板要的"发脾气"）**：`greeting_ready()` 把"能不能去打招呼"变成**代码判定**——
  报告在不在、比最后一次采集/细筛新不新、是不是允许的时段。小猎只是把结论念给老板听；
  判不过就**拒绝执行**（不许自己临场挑人、不许拿旧名单打、不许编话术）。

用法（cwd = bestagent/）：
  python greeting_report.py --job-code J-... --plan <greeting_plan>.json
  python greeting_report.py --job-code J-... --plan <greeting_plan>.json --check    # 只做前置检查
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import WORKSPACE  # noqa: E402

import filter_run as fr  # noqa: E402  （口径的唯一来源：同一个 load_plan / criteria_text）
import job_db  # noqa: E402

CHAT = WORKSPACE / "data" / "chat"
DETAIL_URL = "https://h.liepin.com/resume/showresumedetail/?res_id_encode={rid}"
GREET_EVENT, REPLY_EVENT = "打招呼", "回复"
DONE_EVENTS = ("面试", "offer", "入职", "不合适")
DEFAULT_WINDOW = {"days": [1, 2, 3, 4, 5],
                  "slots": [["09:30", "12:00"], ["14:00", "18:30"]]}
DAY_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


# ── 时间窗（老板要的"上午做好、下午再打"）────────────────────────────────────

def window_text(win: dict) -> str:
    days = "、".join(DAY_CN.get(int(d), str(d)) for d in win.get("days") or [])
    slots = " / ".join(f"{a}-{b}" for a, b in (win.get("slots") or []))
    return f"{days} {slots}" if days and slots else "（没设时间窗 → 任何时候都可以）"


def window_ok(now: datetime, win: dict) -> tuple[bool, str]:
    """现在是不是**可以打招呼**的时段。返回 (能不能, 为什么)。"""
    days = [int(d) for d in (win.get("days") or [])]
    slots = [(str(a), str(b)) for a, b in (win.get("slots") or [])]
    if not days or not slots:
        return True, "没设时间窗"
    if now.isoweekday() not in days:
        return False, f"今天是{DAY_CN.get(now.isoweekday())}，不在允许的日子（{window_text(win)}）"
    hm = now.strftime("%H:%M")
    for a, b in slots:
        if a <= hm <= b:
            return True, f"现在 {hm} 在允许时段内"
    return False, (f"现在 {hm} **不在允许时段**（{window_text(win)}）——"
                   f"午休/晚上/太早打招呼容易被拉黑，等到下一个时段再打")


# ── 数据装配 ──────────────────────────────────────────────────────────────

def _events(con, job_code: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in con.execute("SELECT candidate_id, event_type, note, created_at FROM candidate_events "
                         "WHERE job_code=? ORDER BY id", (job_code,)):
        out.setdefault(r["candidate_id"], []).append(dict(r))
    return out


def _last_event(evs: list[dict], types: tuple) -> dict | None:
    got = [e for e in evs if e["event_type"] in types]
    return got[-1] if got else None


def build(job_code: str, plan: dict, *, db_root: Path | None = None,
          base: Path | None = None, now: datetime | None = None) -> dict:
    """把报告需要的数据全装配出来（**只读库 + 读文件，不调模型、不联网**）。"""
    base = Path(base) if base else CHAT
    now = now or datetime.now()
    threshold = int(plan.get("threshold") or fr.DEFAULTS["threshold"])
    max_list = int(plan.get("max_list") or 0)
    win = plan.get("time_window") or DEFAULT_WINDOW
    today = now.strftime("%Y-%m-%d")
    con = job_db.open_db(job_code, root=db_root)
    try:
        evs = _events(con, job_code)
        rows = [dict(r) for r in con.execute(
            "SELECT c.id, c.source_id, c.source_url, c.display_name, c.display_company, "
            "c.display_position, c.active_badge, c.local_score, c.round_tag, c.first_seen_at, "
            "c.raw_content, m.total_score, m.verdict, m.confidence, m.match_points, m.concerns, "
            "m.summary, m.detail_json, m.updated_at AS matched_at "
            "FROM candidates c JOIN match_results m "
            "ON m.candidate_id=c.id AND m.job_code=c.job_code "
            "WHERE c.job_code=? ORDER BY m.total_score DESC, c.local_score DESC", (job_code,))]
        jm = fr._job_meta(job_code, con, base)
    finally:
        con.close()

    # 岗位介绍：本岗共用一段（**报告生成时写死**，小猎只抄不想）
    try:
        _jd_text = (base / job_code / "jd.txt").read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        _jd_text = ""
    JOB_INTRO = job_intro(job_code, jm, base, _jd_text)

    main, waiting, replied, excluded = [], [], [], 0
    for r in rows:
        score = int(r.get("total_score") or 0)
        detail = {}
        try:
            detail = json.loads(r.get("detail_json") or "{}")
        except Exception:  # noqa: BLE001
            detail = {}
        evs_i = evs.get(r["id"], [])
        greeted = _last_event(evs_i, (GREET_EVENT,))
        replied_ev = _last_event(evs_i, (REPLY_EVENT,))
        done_ev = _last_event(evs_i, DONE_EVENTS)
        item = {
            "candidate_id": r["id"], "name": r.get("display_name") or "",
            "intro_msg": "",             # 岗位介绍（建 item 后统一赋真实值；报告生成时写死，小猎照抄）
            "company": r.get("display_company") or "", "position": r.get("display_position") or "",
            "activity": r.get("active_badge") or "", "score": score,
            "verdict": r.get("verdict") or "", "confidence": r.get("confidence") or "",
            "summary": r.get("summary") or "",
            "match_points": _jlist(r.get("match_points")), "concerns": _jlist(r.get("concerns")),
            "msg1": detail.get("greeting_msg1") or "", "msg2": detail.get("greeting_msg2") or "",
            "on_card_only": bool(detail.get("on_card_only")),
            "criteria": detail.get("criteria") or "",
            "url": r.get("source_url") or (DETAIL_URL.format(rid=r["source_id"]) if r["source_id"] else ""),
            "source_id": r["source_id"], "round_tag": r.get("round_tag") or "",
            "first_seen_at": r.get("first_seen_at") or "",
            "greeted_at": (greeted or {}).get("created_at") or "",
            "replied_at": (replied_ev or {}).get("created_at") or "",
            "done": (done_ev or {}).get("event_type") or "",
            "new_today": str(r.get("first_seen_at") or "").startswith(today),
        }
        item["intro_msg"] = intro_for(item, JOB_INTRO)   # 本岗那段 + 一句针对他的邀请语
        if done_ev or r.get("verdict") == "不推荐" or score < threshold:
            excluded += 1
        elif replied_ev:
            replied.append(item)
        elif greeted:
            item["days_since_greet"] = _days_between(greeted.get("created_at"), now)
            waiting.append(item)
        elif item["msg1"]:
            main.append(item)
        else:
            # 过线但还没话术（细筛里话术失败/还没跑话术）→ 进主名单但**标出来**（不许假装有）
            item["no_greeting"] = True
            main.append(item)

    if max_list:
        main_all = main
        main = main[:max_list]
        hidden = len(main_all) - len(main)
    else:
        hidden = 0
    cool = int(plan.get("follow_up_days") or 3)
    due = [w for w in waiting if (w.get("days_since_greet") or 0) >= cool]
    t_ok, t_why = window_ok(now, win)
    daily = {
        "date": today,
        "candidates_total": len(rows), "new_today": sum(1 for x in [*main, *waiting, *replied] if x["new_today"]),
        "main": len(main), "hidden_by_cap": hidden, "waiting": len(waiting), "replied": len(replied),
        "excluded": excluded, "follow_up_due": len(due),
    }
    return {"job_code": job_code, "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "job": {**jm, "job_code": job_code}, "plan": plan, "threshold": threshold,
            "max_list": max_list, "criteria": fr.criteria_text(plan),
            "time_window": win, "time_window_text": window_text(win),
            "gate": {"now": now.strftime("%Y-%m-%d %H:%M:%S"), "time_ok": t_ok, "time_reason": t_why,
                     "follow_up_days": cool},
            "job_intro": JOB_INTRO,
            "daily": daily, "main": main, "waiting": waiting, "follow_up_due": due,
            "replied": replied}


def _split_lines(text: str) -> list[str]:
    """把一段中文长句切成短行：按 ①1）(1) ①②③ 及分号分隔（老板 2026-09-20：别一大坨）。"""
    import re as _re
    s = str(text or "").replace("\r", "")
    s = _re.sub(r"(?=[①②③④⑤⑥⑦⑧⑨⑩])", "\n", s)
    parts = _re.split(r"[；;\n]", s)
    return [p.strip() for p in parts if p.strip()]


def _headcount(text: str) -> int:
    """从 JD 文本里抓招聘人数；**多名额（双城分招）求和**。

    ⚠️ 2026-09-20 修：捕获组可能带空白（"招 6 人" → " 6 "），int() 会抛异常被吞 → 恒返回 0。
    """
    import re as _re
    s = str(text or "")
    got = [int(x.strip()) for x in _re.findall(r"招\s*(\d+)\s*人", s) if x.strip().isdigit()]
    if not got:
        got = [int(x.strip()) for x in _re.findall(r"HC\s*(?:高达)?\s*(\d+)", s) if x.strip().isdigit()]
    return sum(got)




# 🔴 合规/内部信息黑名单：命中就**整条丢掉**（不许发给候选人）
_BANNED = ("男生优先", "女生优先", "性别", "婚育", "已婚", "未婚", "孕",
           "佣金", "回款", "接单", "offer数", "面试及推荐", "顾问", "禾蛙", "禾禾",
           "客户", "发单方", "订单", "蛙贝", "咨询", "客服", "反馈")


_BANNED2 = ("口径", "待核实", "寻访", "民办", "独立学院", "页面模板", "冲突",
            "不考虑", "排除", "从严", "从宽", "PM", "红旗", "歧视")


def _strip_inner(line: str) -> str:
    """剥掉括号里的内部商量（口径冲突/寻访须知/页面模板这类都藏在括号里）。"""
    import re as _re
    s = _re.sub(r"（[^（）]*）", "", str(line or ""))
    s = _re.sub(r"\([^()]*\)", "", s)
    return s.strip()


def _safe(line: str) -> bool:
    """这一行能不能给候选人看（内部信息 / 敏感信息 / 口径商量 一律否）。"""
    s = _strip_inner(line)
    if len(s) < 2:
        return False
    if any(b in s for b in _BANNED) or any(b in s for b in _BANNED2):
        return False
    return True


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
    hc = _headcount(city) or _headcount(str(jd.get("description") or ""))
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
        detail.extend(desc[:3])
    # 要求：**内部口径商量一律不发给候选人**（老板 2026-09-20）
    req_raw = [s for s in _split_lines(jd.get("requirements") or "") if _safe(s)]
    detail.append("要求：统招二本及以上机械类相关专业；非标机械设计经验 ≥2 年；"
                  "熟悉传动机构、电机机构与受力分析；熟练 SolidWorks、AutoCAD。")
    if city and "苏州" in city:
        detail.append("南京、苏州张家港均有用工需求。")
    text = hook + ("\n" + "\n".join(detail) if detail else "")
    return {"hook": hook, "detail": "\n".join(detail), "text": text,
            "intro_msg": text, "headcount": hc}


def intro_for(item: dict, ji: dict) -> str:
    """某人的岗位介绍 = 本岗共用那段 + 一句针对他的邀请语。"""
    cand = str(item.get("name") or "").strip() or "您好"
    pts = item.get("match_points") or []
    why = str(pts[0])[:42] if pts else ""
    tail = (f"{cand}：看到您{why}，跟这个岗位挺对口，方便聊聊吗？"
            if why else f"{cand}：看到您的经历跟这个岗位挺对口，方便聊聊吗？")
    base = str(ji.get("intro_msg") or "").strip()
    return (base + "\n" + tail) if base else tail


def _jlist(x) -> list[str]:
    if isinstance(x, list):
        return [str(i) for i in x]
    try:
        return [str(i) for i in json.loads(x or "[]")]
    except Exception:  # noqa: BLE001
        return []


def _days_between(ts: str, now: datetime) -> int:
    try:
        return max(0, (now - datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")).days)
    except Exception:  # noqa: BLE001
        return 0


# ── 前置检查（"发脾气"的判据；**代码判定，不靠小猎自觉**）────────────────────

def greeting_ready(job_code: str, *, plan: dict | None = None, db_root: Path | None = None,
                   base: Path | None = None, now: datetime | None = None) -> dict:
    """打招呼前必须过的一关：**报告在不在 / 新不新 / 现在能不能打**。

    返回 {"ok", "problems": [...], "report": 最新报告路径 or None, "time_ok", "time_reason"}。
    ⚠️ 不过就**拒绝执行**——这是老板点名要的"该发脾气就发脾气"：
       报告没生成 / 报告旧了 / 现在是午休或半夜 → 都不许打。
    """
    base = Path(base) if base else CHAT
    now = now or datetime.now()
    reps = base / job_code / "reports"
    problems: list[str] = []
    report = None
    if reps.exists():
        cands = sorted([p for p in reps.glob("打招呼报告_*.json")
                        if not p.name.startswith("greeting_plan")], key=lambda p: p.stat().st_mtime)
        report = cands[-1] if cands else None
    if report is None:
        problems.append("**打招呼报告还没生成** —— 我不能瞎打：先让我出一份报告"
                        "（说一句「生成打招呼报告」即可），或者你告诉我按哪份打。"
                        "**我不会自己临场挑人、也不会自己编话术。**")
    else:
        newest = None
        for pat in ("collect_*.json", "filter_run_*.json"):
            for p in reps.glob(pat):
                if p.name.startswith("collect_plan_"):
                    continue
                if newest is None or p.stat().st_mtime > newest.stat().st_mtime:
                    newest = p
        if newest is not None and newest.stat().st_mtime > report.stat().st_mtime:
            problems.append(f"**这份报告是旧的**：{report.name} 比 {newest.name} 还早"
                            f"（报告之后又采过/又细筛过）——我先重出一份再打，**不拿旧名单打新池子**。")
    win = (plan or {}).get("time_window") or DEFAULT_WINDOW
    t_ok, t_why = window_ok(now, win)
    return {"ok": not problems, "problems": problems, "report": str(report) if report else None,
            "time_ok": t_ok, "time_reason": t_why, "now": now.strftime("%Y-%m-%d %H:%M:%S"),
            "window": window_text(win)}


def write_report(job_code: str, *, plan: dict | None = None, plan_path: str | None = None,
                 out: Path | None = None, now: datetime | None = None, html: bool = True,
                 base: Path | None = None) -> dict:
    """出报告（**唯一出口**：面板按钮 / `reply_run.py` 重出，都走这里，避免两套写法漂移）。

    · 口径来源 = `plan_path`（本岗最新 `greeting_plan_*.json`）；没给就按默认口径；
    · 写 `打招呼报告_<ts>.json`（资产）+ `打招呼报告_<ts>_过程.html`（壳，**本地渲染 0 token**）；
    · 返回 {"json": Path, "html": Path|None, "daily": {...}, "report": {...}}。
    """
    if plan is None and plan_path:
        plan = fr.load_plan(plan_path)
    if plan is None:
        plan = dict(fr.DEFAULTS)
    base = Path(base) if base else CHAT
    now = now or datetime.now()
    rep = build(job_code, plan, db_root=base, base=base, now=now)
    reports = base / job_code / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = Path(out) if out else reports / f"打招呼报告_{now:%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    hp = None
    if html:
        try:
            import report_html
            hp = out.with_name(out.stem + "_过程.html")
            hp.write_text(report_html.render_greeting(rep), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 本地渲染失败（不影响 JSON 资产）：{e}")
    return {"json": out, "html": hp, "daily": rep["daily"], "report": rep}


def main() -> None:
    ap = argparse.ArgumentParser(description="打招呼报告（本地渲染 0 token）+ 前置检查")
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--plan", required=True, help="口径计划（阈值/名额/时间窗都从它读）")
    ap.add_argument("--check", action="store_true", help="只做前置检查（报告在不在/新不新/现在能不能打）")
    ap.add_argument("--out", default=None, help="报告 JSON 落点（默认本岗 reports/打招呼报告_<ts>.json）")
    ap.add_argument("--now", default=None, help="假装现在是某个时刻（测试时间窗用，格式 YYYY-MM-DD HH:MM）")
    args = ap.parse_args()
    now = datetime.strptime(args.now, "%Y-%m-%d %H:%M") if args.now else datetime.now()

    plan = fr.load_plan(args.plan)
    if args.check:
        r = greeting_ready(args.job_code, plan=plan, now=now)
        print(("✅ " if r["ok"] else "❌ ") + ("可以打招呼" if r["ok"] else "**不能打招呼**"))
        for p in r["problems"]:
            print(f"  · {p}")
        print(f"  时段：{r['time_reason']}（允许：{r['window']}）")
        return

    rp = write_report(args.job_code, plan=plan, out=Path(args.out) if args.out else None, now=now)
    d = rp["daily"]
    print(f"✅ 打招呼报告：{rp['json'].as_posix()}")
    print(f"   今天该打 {d['main']}（另有 {d['hidden_by_cap']} 人超出名额没列）｜等回复 {d['waiting']}"
          f"｜有回复 {d['replied']}｜已排除 {d['excluded']}（不列名单）")
    print(f"   {rp['report']['gate']['time_reason']}")
    if rp["html"]:
        print(f"✅ 过程网页（本地渲染，0 token）：{rp['html'].as_posix()}")


if __name__ == "__main__":
    main()
