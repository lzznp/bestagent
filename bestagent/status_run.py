#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""status_run.py — **岗位态势卡**（只读、0 token）：小猎"自己权衡"的原料。

为什么要它（老板 2026-09-17 定的意图）：**规则不该写死在代码里，也不该每次由老板口述** ——
  应该由**小猎自己权衡**（这个岗池子厚不厚？够格几个？今天打了几个？还剩多少？该不该宽松/收紧？
  该不该再去采一轮？今天先管哪个岗？）。它要权衡，就得先**看得见事实** —— 这个脚本只干这一件事。

事实（全从本地文件和本岗库读出来，**不调模型、不联网、不改任何东西**）：
  · 池子：多少人 / 多少有全文 / 多少只有卡片 / 今天新采到几个；
  · 分数：评过几个 / 分数分布 / 各档累计（够格多少人一目了然）；
  · 队列：**够格且还没打过招呼**的还剩几个（= 今天能打的存量）；
  · 联系：累计打过 / 今天打过 / 等回复 / 有回复 / 到冷却该跟进的 / 已了结；
  · 时间与报告：现在能不能打、最新报告多新、上一次采集/细筛是什么时候。

用法（cwd = bestagent/）：
  python status_run.py --job-code J-...                 # 看一个岗
  python status_run.py --all                            # 看所有岗（"今天先管哪个"）
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import WORKSPACE  # noqa: E402

import filter_run as fr  # noqa: E402
import greeting_report as gr  # noqa: E402
import job_db  # noqa: E402

CHAT = WORKSPACE / "data" / "chat"


def _latest(base: Path, pats: tuple, skip_prefix: tuple = ()) -> tuple[str, str, float]:
    """最新产物：(文件名, 时间串, mtime)。"""
    best = None
    reps = base
    if not reps.exists():
        return "", "", 0.0
    for pat in pats:
        for p in reps.glob(pat):
            if any(p.name.startswith(s) for s in skip_prefix):
                continue
            if best is None or p.stat().st_mtime > best.stat().st_mtime:
                best = p
    if best is None:
        return "", "", 0.0
    return best.name, datetime.fromtimestamp(best.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), best.stat().st_mtime


def status(job_code: str, *, plan: dict | None = None, db_root: Path | None = None,
           base: Path | None = None, now: datetime | None = None) -> dict:
    base = Path(base) if base else CHAT
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    plan = plan or {}
    threshold = int(plan.get("threshold") or fr.DEFAULTS["threshold"])
    cool = int(plan.get("follow_up_days") or 3)
    reps = base / job_code / "reports"
    con = job_db.open_db(job_code, root=db_root)
    try:
        cands = [dict(r) for r in con.execute(
            "SELECT id, first_seen_at, raw_content, status FROM candidates WHERE job_code=?",
            (job_code,))]
        matches = [dict(r) for r in con.execute(
            "SELECT candidate_id, total_score, verdict FROM match_results WHERE job_code=?",
            (job_code,))]
        evs = gr._events(con, job_code)
        jm = fr._job_meta(job_code, con, base)
    finally:
        con.close()

    scored = {}
    for m in matches:
        scored[m["candidate_id"]] = int(m["total_score"] or 0)
    dist = Counter(scored.values())
    bands = {}
    for b in (90, 80, 78, 75, 72, 70, 65, 60):
        bands[f">={b}"] = sum(1 for s in scored.values() if s >= b)

    contacted = {cid for cid, es in evs.items() if any(e["event_type"] == gr.GREET_EVENT for e in es)}
    replied = {cid for cid, es in evs.items() if any(e["event_type"] == gr.REPLY_EVENT for e in es)}
    done = {cid for cid, es in evs.items() if any(e["event_type"] in gr.DONE_EVENTS for e in es)}
    greeted_today = sum(1 for cid in contacted
                        for e in evs.get(cid, [])
                        if e["event_type"] == gr.GREET_EVENT and str(e["created_at"]).startswith(today))
    # 队列：**够格 + 没打过 + 不是不推荐 + 没了结**
    queue = [cid for cid, s in scored.items()
             if s >= threshold and cid not in contacted and cid not in done
             and next((m["verdict"] for m in matches if m["candidate_id"] == cid), "") != "不推荐"]
    waiting = [cid for cid in contacted if cid not in replied and cid not in done]
    due = []
    for cid in waiting:
        last = gr._last_event(evs.get(cid, []), (gr.GREET_EVENT,))
        if last and gr._days_between(last.get("created_at"), now) >= cool:
            due.append(cid)

    last_collect = _latest(reps, ("collect_*.json",), ("collect_plan_",))
    last_filter = _latest(reps, ("filter_run_*.json",))
    last_report = _latest(reps, ("打招呼报告_*.json",))
    last_plan = _latest(reps, ("greeting_plan_*.json",))
    ready = gr.greeting_ready(job_code, plan=plan, db_root=db_root, base=base, now=now)
    t_ok, t_why = gr.window_ok(now, plan.get("time_window") or gr.DEFAULT_WINDOW)

    out = {"job_code": job_code, "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
           "job": {**jm, "job_code": job_code, "decision": None},
           "pool": {"candidates": len(cands),
                    "with_fulltext": sum(1 for c in cands if str(c.get("raw_content") or "").strip()),
                    "card_only": sum(1 for c in cands if not str(c.get("raw_content") or "").strip()),
                    "new_today": sum(1 for c in cands if str(c.get("first_seen_at") or "").startswith(today))},
           "scoring": {"matched": len(matches), "unmatched": len(cands) - len(matches),
                       "distribution": {str(k): v for k, v in sorted(dist.items(), reverse=True)},
                       "bands": bands},
           "queue": {"threshold": threshold, "qualified_uncontacted": len(queue)},
           "contact": {"greeted_total": len(contacted), "greeted_today": greeted_today,
                       "waiting_reply": len(waiting), "replied": len(replied),
                       "follow_up_due": len(due), "done": len(done), "follow_up_days": cool},
           "artifacts": {"last_collect": last_collect, "last_filter": last_filter,
                         "last_greeting_report": last_report, "last_plan": last_plan},
           "gate": {"time_ok": t_ok, "time_reason": t_why,
                    "report_ready": ready["ok"], "report_problems": ready["problems"]},
           "notes": []}
    # 给小猎的**判断提示**（事实推论，不是命令）：它自己决定怎么做
    p, q, c = out["pool"], out["queue"], out["contact"]
    if out["scoring"]["unmatched"] > 0:
        out["notes"].append(f"有 {out['scoring']['unmatched']} 人**还没细筛** → 先跑一遍细筛"
                            f"（评过的人命中缓存、0 花费；只有新人花钱）")
    elif q["qualified_uncontacted"] == 0 and p["candidates"]:
        out["notes"].append("够格且没打过招呼的人 = 0 → 想推进这个岗，要么**放宽口径重筛**，"
                            "要么**再去采一轮**（可能有新人）")
    if p["new_today"]:
        out["notes"].append(f"今天新采到 {p['new_today']} 人 → 还没筛过的先筛（缓存会让老的人 0 花费跳过）")
    if c["follow_up_due"]:
        out["notes"].append(f"有 {c['follow_up_due']} 人打了招呼超过 {cool} 天没回 → 该跟进了")
    if c["replied"]:
        out["notes"].append(f"有 {c['replied']} 人回复了 → 该聊下一步")
    if not ready["ok"]:
        out["notes"].append("打招呼报告没过前置检查 → 先出报告/重出报告，别急着打")
    if not t_ok:
        out["notes"].append("现在不在允许时段 → 排到下一个时段")
    return out


def brief(st: dict) -> str:
    """一句话人话（给汇报用；不是机器日志腔）。"""
    p, s, q, c, a = st["pool"], st["scoring"], st["queue"], st["contact"], st["artifacts"]
    parts = [f"{st['job'].get('title') or st['job_code']}：池子 {p['candidates']} 人"
             f"（有全文 {p['with_fulltext']}／仅卡片 {p['card_only']}）"]
    parts.append(f"已评 {s['matched']}／未评 {s['unmatched']}")
    parts.append(f"够格(≥{q['threshold']})还没打招呼的 **{q['qualified_uncontacted']} 人**")
    parts.append(f"打过 {c['greeted_total']}（今天 {c['greeted_today']}）／等回复 {c['waiting_reply']}"
                 f"／有回复 {c['replied']}／该跟进 {c['follow_up_due']}")
    if a["last_collect"][0]:
        parts.append(f"上次采集 {a['last_collect'][1]}")
    if a["last_greeting_report"][0]:
        parts.append(f"最新报告 {a['last_greeting_report'][1]}")
    parts.append(("现在**可以打**" if st["gate"]["time_ok"] else "现在**不能打**")
                 + f"（{st['gate']['time_reason']}）")
    return "；".join(parts)


def _latest_plan(jc: str):
    """本岗最新口径计划（时间窗/阈值/名额都在 plan 里；"规则是数据"）。"""
    reps = CHAT / jc / "reports"
    if not reps.exists():
        return None
    got = sorted(reps.glob("greeting_plan_*.json"), key=lambda p: p.stat().st_mtime)
    return got[-1] if got else None


def main() -> None:
    ap = argparse.ArgumentParser(description="岗位态势卡（只读、0 token）：给小猎权衡用")
    ap.add_argument("--job-code", default=None)
    ap.add_argument("--all", action="store_true", help="扫所有岗（今天先管哪个）")
    ap.add_argument("--plan", default=None, help="口径计划（读它的阈值/冷却；不给就用兜底并标注）")
    ap.add_argument("--out", default=None, help="落盘 JSON（默认不落，只看）")
    args = ap.parse_args()
    if not args.job_code and not args.all:
        raise SystemExit("❌ 要么 --job-code <岗>，要么 --all")
    jobs = ([args.job_code] if args.job_code else
            [d.name for d in sorted(CHAT.iterdir()) if d.is_dir()])
    if args.plan:
        plan = fr.load_plan(args.plan)
        print(f"📄 口径来源：{args.plan}")
    elif args.job_code:
        _p = _latest_plan(args.job_code)
        plan = fr.load_plan(_p) if _p else {}
        print(f"📄 口径来源：{_p.name if _p else '（该岗还没有口径计划 → 用代码兜底）'}")
    out = []
    for jc in jobs:
        if not args.plan:
            _p = _latest_plan(jc)
            plan = fr.load_plan(_p) if _p else {}
        st = status(jc, plan=plan)
        out.append(st)
        print(f"\n📋 {jc}")
        print("   " + brief(st))
        for n in st["notes"]:
            print(f"   · {n}")
        if not st["pool"]["candidates"]:
            print("   · 这个岗还没有候选人（没采过）")
    if len(out) == 1 and args.out:
        Path(args.out).write_text(json.dumps(out[0], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n✅ 态势卡：{args.out}")
    elif args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n✅ 态势卡（{len(out)} 个岗）：{args.out}")


if __name__ == "__main__":
    main()
