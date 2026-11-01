#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search_rounds.py — ②「搜索体检」轮次执行器：**小猎出脑子，脚本出手**（只读人数，不抓人）

出处（2026-09-15 老板口径原话）：
  「让小猎实际操作浏览器，根据岗位的 JD 进行几轮搜索，然后他生成报告，说：我先用啥关键字、
    设定了哪些条件进行了搜索，这时候总候选人人数是 360 或者 3000+；然后又改变了什么关键字，
    修改了或者没修改活跃度，总候选人人数是多少……」
  → **脑 = 小猎**（写"轮次计划"小 JSON：搜什么、怎么改、为什么）；
    **手 = 本脚本**（确定性操作浏览器、只读命中人数）。
  → 目的 = **体检**：看小猎会不会按 JD 正确设条件/关键字、会不会操浏览器。

与 `collect_liepin.py` 的分工（别搞混）：
  - `collect_liepin.py` = **真采集**：抓人、落 `collected_*.json`、喂③池子评估；
  - `search_rounds.py`   = **体检**：**不抓人**（不调 extract、不落任何候选人 id），
    只读页面上的「共N位人选」→ 出一份"每轮关键字/条件/命中人数"的过程报告供老板看。

⚠️ 诚实边界：命中总数只能从 `body_preview`（页面纯文本**前 3000 字**）里正则读；读不到就
   `found=false` 如实标注，**绝不猜**（页面上条件很多时文本可能被截断，这是已知脆点）。

用法（cwd = bestagent/）：
  # 1) 先本地体检计划（不开浏览器、0 风险、0 token）
  python search_rounds.py --plan rounds_xxx.json --dry-run
  # 2) 真跑（逐轮：导航→清空→按配方设条件+强制 verify→搜索→只读人数）
  python search_rounds.py --plan rounds_xxx.json --out data/chat/<job>/reports/search_rounds_<ts>.json
  # 3) 跑完后把"小猎看到结果写的结论"合进来（渲染器要用）
  python search_rounds.py --plan rounds_xxx.json --out ... --conclusion-file concl_xxx.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import BROWSER_AGENT  # noqa: E402
sys.path.insert(0, str(BROWSER_AGENT))

from agent.core import submit_task  # noqa: E402
from agent.recipe_exec import BRIDGE, COND_URL, execute_spec, _snap  # noqa: E402

from collect_liepin import find_liepin_tab, stop_requested  # noqa: E402
from quota import Quota  # noqa: E402

WAIT_NAV = 2.5
WAIT_CLEAR = 2.0
MAX_ROUNDS_DEFAULT = 5
# 「共3000+位人选」→ 命中总数（页面原文，2026-09-15 只读实测确认的写法）
TOTAL_RE = re.compile(r"共\s*([\d,]+)\s*(\+?)\s*位人选")
# 配方表 behaviors：**即点即搜**的类型（这些条件点完页面自己就搜了 → 读到的数就是它的效果）
AUTO_SEARCH_TYPES = ("chips", "chips+panel")


# ---------------- 读数（只读，不抓人）----------------

def parse_total(body: str) -> dict:
    """从页面纯文本里解析「共N位人选」。

    **刻意拆成纯函数**：这条正则就是本次新能力的**唯一脆点**（页面写法一变就失效），
    所以必须能被本地单测（不起浏览器、0 token）。
    """
    m = TOTAL_RE.search(body or "")
    if not m:
        return {"total": None, "total_raw": "", "is_plus": False, "found": False}
    return {"total": int(m.group(1).replace(",", "")), "is_plus": bool(m.group(2)),
            "total_raw": m.group(0), "found": True}


def read_total(tab_id: int) -> dict:
    """只读页面上的「共N位人选」。**不抓人**：不调 extract、不落候选人 id。读不到 → found=False。"""
    s = _snap(tab_id)
    anchors = len([e for e in (s.get("elements") or [])
                   if (e.get("name") or "").strip() == "立即沟通"])
    out = dict(parse_total(s.get("body_preview") or ""),
               anchors_immediate_chat=anchors, url=s.get("url") or "")
    if not out["found"]:
        out["note"] = ("body_preview（页面纯文本前 3000 字）里没找到「共N位人选」——可能页面没刷新完，"
                       "或文本被截断。**不猜**，按'读不到'记。")
    return out


# ---------------- 计划（小猎写的小 JSON）----------------

def load_plan(path: Path) -> dict:
    """读并体检"轮次计划"。契约（面板任务文本会给小猎同一份）：

    {"job_code": "J-CHAT-…",
     "rounds": [
       {"n": 1, "keyword": "电气设计 输送线", "conds": ["city_current=南京", "education=本科"],
        "reason": "为什么这么设（≤80 字）"},
       {"n": 2, "keyword": "电控设计 输送线", "conds": ["city_current=南京", "activity=今天活跃"],
        "changed": "换关键字 / 撤了学历 / 加了活跃度", "reason": "…"}
     ]}
    """
    d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(d, dict):
        raise SystemExit("❌ 轮次计划顶层必须是 JSON 对象")
    rounds = d.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        raise SystemExit("❌ 轮次计划里没有 rounds（应为非空数组）")
    norm = []
    for i, r in enumerate(rounds, 1):
        if not isinstance(r, dict):
            raise SystemExit(f"❌ 第 {i} 轮不是对象")
        kw = str(r.get("keyword") or "").strip()
        kws = [str(x).strip() for x in (r.get("keywords") or []) if str(x).strip()]
        if not kw and kws:
            if len(kws) > 1:
                raise SystemExit(
                    f"❌ 第 {i} 轮给了 {len(kws)} 个关键字：**一轮只跑一个关键字**（多关键字就多写几轮）。"
                    "否则报告里分不清是哪条关键字带来的变化——这正是这次体检要看的东西。")
            kw = kws[0]
        if not kw:
            raise SystemExit(f"❌ 第 {i} 轮没有 keyword（关键字是每轮的必填项）")
        conds = [str(c).strip() for c in (r.get("conds") or []) if str(c).strip()]
        norm.append({"n": r.get("n") or i, "keyword": kw, "conds": conds,
                     "changed": str(r.get("changed") or "").strip(),
                     "reason": str(r.get("reason") or "").strip()})
    out = dict(d)
    out["rounds"] = norm
    out["_path"] = Path(path).as_posix()
    return out


def default_out(plan: dict) -> Path:
    """产物默认落本岗 reports（有 job_code 且目录在 → 归岗；否则落 data/usage）。"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    here = Path(__file__).resolve().parent
    code = str(plan.get("job_code") or "").strip()
    if code and (here / "data" / "chat" / code).is_dir():
        d = here / "data" / "chat" / code / "reports"
    else:
        d = here / "data" / "usage"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"search_rounds_{ts}.json"


# ---------------- 真跑 ----------------

def run_rounds(plan: dict, tab: int, q: Quota | None, max_rounds: int) -> dict:
    started = time.time()
    rounds = plan["rounds"][:max_rounds]
    trace = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "job_code": plan.get("job_code") or "", "plan_file": plan.get("_path") or "",
             "tab_id": tab, "max_rounds": max_rounds, "rounds": [], "notes": []}
    if len(plan["rounds"]) > max_rounds:
        trace["notes"].append(f"计划给了 {len(plan['rounds'])} 轮，本次只跑前 {max_rounds} 轮（--max-rounds 硬顶）")
    prev_total, searches = None, 0

    for idx, r in enumerate(rounds):
        if stop_requested(started):
            trace["notes"].append("⛔ 人工停止（老板点了「停小猎跑腿」）——本轮在此收尾")
            break
        cond_list, bad = [], []
        for c in r["conds"]:
            gid, sep, val = c.partition("=")
            if sep and gid.strip() and val.strip():
                cond_list.append({"group_id": gid.strip(), "value": val.strip()})
            else:
                bad.append(c)
        if bad:
            trace["notes"].append(f"第 {r['n']} 轮有 {len(bad)} 条条件格式不对（应 group_id=value）已跳过：{bad}")

        rec = {"n": r["n"], "keyword": r["keyword"], "conds": r["conds"], "changed": r["changed"],
               "reason": r["reason"], "steps": [], "ok": False, "error": None, "verify_failed": None,
               "total": None, "total_raw": "", "found": False, "is_plus": False,
               "anchors_immediate_chat": 0, "delta_vs_prev": None, "url": "", "searches": 0}
        t0 = time.time()
        print(f"\n▶ 第 {r['n']} 轮：关键字「{r['keyword']}」｜条件 {r['conds'] or '（无）'}")

        nav = submit_task(BRIDGE, "navigate", {"tab_id": tab, "url": COND_URL}, source="search-rounds")
        if not nav.get("ok"):
            rec["error"] = f"navigate 失败：{nav.get('error')}"
            trace["rounds"].append(rec)
            print(f"   ❌ {rec['error']}")
            break
        time.sleep(WAIT_NAV)
        submit_task(BRIDGE, "click_by_text",
                    {"tab_id": tab, "text": "清空筛选条件", "occurrence": 1}, source="search-rounds")
        time.sleep(WAIT_CLEAR)

        def _hook(step, _tab=tab):
            """每个条件执行完就地读一次人数 = 「这个条件砍掉多少人」。"""
            auto = step.get("type") in AUTO_SEARCH_TYPES
            rd = read_total(_tab)
            if not auto:
                rd["stale"] = True  # input 类不触发搜索 → 这个读数是上一次搜索的旧状态（如实标注）
            return rd

        spec = [{"group_id": "keyword", "value": r["keyword"]}] + cond_list
        res = execute_spec(spec, tab, do_search=True, do_extract=False, on_step=_hook)
        rec["steps"] = res.get("steps") or []
        rec["ok"] = bool(res.get("ok"))
        rec["error"] = res.get("error")
        rec["verify_failed"] = res.get("verify_failed")

        final = read_total(tab)  # 最后一次"搜 索"之后的定稿读数
        rec.update({k: final[k] for k in ("total", "total_raw", "found", "is_plus",
                                          "anchors_immediate_chat", "url")})
        if final.get("note"):
            rec["note"] = final["note"]
        if rec["total"] is not None and prev_total is not None:
            rec["delta_vs_prev"] = rec["total"] - prev_total
        if rec["total"] is not None:
            prev_total = rec["total"]
        rec["searches"] = 1 + len([s for s in rec["steps"] if s.get("type") in AUTO_SEARCH_TYPES])
        searches += rec["searches"]
        rec["elapsed_sec"] = round(time.time() - t0, 1)
        trace["rounds"].append(rec)

        if rec["verify_failed"]:
            print(f"   ❌ 条件没生效（verify=False）：{rec['error']}")
        print(f"   → 命中总数：{rec['total_raw'] or '（读不到）'}"
              f"｜首页可见 {rec['anchors_immediate_chat']} 人｜{rec['searches']} 次搜索｜{rec['elapsed_sec']}s")
        if q:
            q.record("search", rec["searches"])
            print(f"   {q.stats()}")
        if idx < len(rounds) - 1:
            if q:
                q.delay()
            else:
                time.sleep(8)

    trace["searches_estimate"] = searches
    trace["elapsed_sec"] = round(time.time() - started, 1)
    return trace


def summarize(t: dict) -> str:
    """给小猎看的 stdout 总结（它据此写结论；**带全部事实**，不用它再猜）。"""
    L = [f"轮次体检：{len(t['rounds'])} 轮｜共 {t.get('searches_estimate', 0)} 次搜索"
         f"｜用时 {t.get('elapsed_sec', '—')}s"]
    for r in t["rounds"]:
        L.append(f"第{r['n']}轮｜关键字「{r['keyword']}」｜条件 {r['conds'] or '（无）'}"
                 f" → {r['total_raw'] or '（读不到命中总数）'}"
                 + (f"（相对上轮 {r['delta_vs_prev']:+d}）" if r.get("delta_vs_prev") is not None else ""))
        for s in r["steps"]:
            if "group_id" not in s:
                continue
            tag = ""
            if s.get("stale"):
                tag = "（旧状态，未触发搜索）"
            L.append(f"    · {s['group_id']}={s.get('value')}（{s.get('type')}）"
                     f" verify={s.get('verify')} → {s.get('total_raw') or '读不到'}{tag}")
        if r.get("verify_failed"):
            L.append(f"    ❌ 条件未生效：{r.get('error')}")
    for n in t.get("notes") or []:
        L.append(f"⚠️ {n}")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="轮次计划 JSON（小猎写的）")
    ap.add_argument("--out", default=None, help="轨迹输出路径（默认落本岗 reports/search_rounds_<ts>.json）")
    ap.add_argument("--max-rounds", type=int, default=MAX_ROUNDS_DEFAULT, help="硬顶轮数（默认 5）")
    ap.add_argument("--tab-id", type=int, default=None, help="猎聘 tab_id（默认自动发现）")
    ap.add_argument("--dry-run", action="store_true", help="只体检计划、不开浏览器、不记账")
    ap.add_argument("--conclusion-file", default=None, help="跑完后小猎写的结论小 JSON（合并进轨迹）")
    ap.add_argument("--no-quota", action="store_true", help="不记账（调试用）")
    args = ap.parse_args()

    plan = load_plan(Path(args.plan))
    out = Path(args.out) if args.out else default_out(plan)
    print(f"▶ 计划：{plan['_path']}｜岗位 {plan.get('job_code') or '（未标）'}｜"
          f"{len(plan['rounds'])} 轮（硬顶 {args.max_rounds}）")
    for r in plan["rounds"]:
        print(f"   第{r['n']}轮：关键字「{r['keyword']}」｜条件 {r['conds'] or '（无）'}"
              + (f"｜改动：{r['changed']}" if r["changed"] else ""))

    if args.dry_run:
        trace = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dry_run": True,
                 "job_code": plan.get("job_code") or "", "plan_file": plan["_path"],
                 "max_rounds": args.max_rounds,
                 "rounds": [{"n": r["n"], "keyword": r["keyword"], "conds": r["conds"],
                             "changed": r["changed"], "reason": r["reason"],
                             "steps": [], "ok": None, "total": None, "total_raw": "",
                             "found": False, "delta_vs_prev": None} for r in plan["rounds"]],
                 "notes": ["dry-run：只体检计划，未开浏览器、未记账"]}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n✅ dry-run 通过：计划合法，未开浏览器。")
        print(f"✅ 计划轨迹（占位）：{out.as_posix()}")
        return

    q = None if args.no_quota else Quota()
    if q:
        print(f"▶ 限速：{q.stats()}")

    tab = args.tab_id or find_liepin_tab()
    trace = run_rounds(plan, tab, q, args.max_rounds)

    if args.conclusion_file:
        cf = Path(args.conclusion_file)
        if cf.exists():
            extra = json.loads(cf.read_text(encoding="utf-8-sig"))
            if isinstance(extra, dict):
                for k in ("conclusion", "highlights"):
                    if extra.get(k):
                        trace[k] = extra[k]
                print(f"▶ 已并入小猎的结论：{cf.as_posix()}")
        else:
            print(f"⚠️ 结论文件不存在：{cf.as_posix()}（跳过，不影响轨迹落盘）")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + summarize(trace))
    print(f"\n✅ 轮次轨迹：{out.as_posix()}")


if __name__ == "__main__":
    main()
