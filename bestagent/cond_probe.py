#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cond_probe.py — ②采集「执行校验」：真设条件 + 真搜索，把每一步的 verify 摊开看（**不抓人**）

出处：`工作文档/省token第二刀与拍板止血·衔接报告.md` §4.1-A（2026-09-15 老板拍的顺序 A→B→C→D）。

为什么要单独搞一个"只验条件"的跑法：
  `agent/recipe_exec.py` 从 2026-09-15 起**强制 verify**（条件没真进"已选标签区"就硬失败 + 归因）。
  这条强制校验需要有人**第一次真跑**它。以前只有 `collect_liepin.py` 一条路，而它跑完就抓人（extract 落候选人 id）——
  "只想验条件"时那是多余的、也是老板明确说不做的（"不抓人、不开详情页"）。

本脚本做三件事，全部只读 + 0 token（不调 LLM）：
  1. 按计划真跑 `execute_spec(..., do_search=True, do_extract=False)`，逐步打印 `ok/verify`；
  2. **不抓人**的厚薄信号：只数结果页上"立即沟通"锚点个数 + 抄下"已选标签区"原文（不落任何候选人 id）；
  3. 附带验一个真问题（报告 §4.1-C 的事实依据）：**学历 chip 到底能不能多选**？
     做法：点『本科』→ 拍已选标签区；再点『硕士』→ 再拍。
     两个标签同时还在 = 可多选；只剩后点的那个 = 单选。（老板口径：大专+本科+硕士+博士 = 大专及以上）

用法（cwd = bestagent/）：
  python cond_probe.py --plan data/chat/<job>/reports/collect_plan_20260915-163727.json
  python cond_probe.py --plan ... --keyword-index 1 --no-probe-multi
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import BROWSER_AGENT  # noqa: E402
sys.path.insert(0, str(BROWSER_AGENT))

from agent.core import submit_task  # noqa: E402
from agent.recipe_exec import execute_spec, load_recipes, COND_URL, BRIDGE, _snap  # noqa: E402

from collect_liepin import find_liepin_tab  # noqa: E402

WAIT_NAV = 2.5
WAIT_CLEAR = 2.0
WAIT_CHIP = 8.0  # 配方表 behaviors：chip「即点即搜」，实测 8 秒后过滤才正确（2.5 秒不够）


# ---------------- 小工具 ----------------

def _body(tab_id: int) -> tuple[str, dict]:
    s = _snap(tab_id)
    return (s.get("body_preview") or ""), s


def _tag_window(body: str, span: int = 400) -> str:
    """已选标签区：'保存条件' 前 span 字的窗口（execute_spec 的 verify 用的就是这个区）。"""
    i = body.find("保存条件")
    return body[max(0, i - span):i] if i >= 0 else ""


def _anchor_count(snap: dict) -> int:
    """结果页上'立即沟通'锚点个数（**不是**总人数，只是首页列表长度——不抓人的厚薄信号）。"""
    return len([e for e in (snap.get("elements") or [])
                if (e.get("name") or "").strip() == "立即沟通"])


def _clear(tab_id: int) -> bool:
    r = submit_task(BRIDGE, "click_by_text",
                    {"tab_id": tab_id, "text": "清空筛选条件", "occurrence": 1}, source="cond-probe")
    time.sleep(WAIT_CLEAR)
    return bool(r.get("ok"))


def _split_conds(conds) -> list[dict]:
    out = []
    for c in conds:
        gid, sep, val = str(c).partition("=")
        if sep and gid.strip():
            out.append({"group_id": gid.strip(), "value": val.strip()})
    return out


# ---------------- 主流程 ----------------

def probe(plan_p: Path, keyword_index: int, probe_multi: str, multi_values: list[str]) -> dict:
    plan = json.loads(plan_p.read_text(encoding="utf-8-sig"))
    kws = [str(k).strip() for k in (plan.get("keywords") or []) if str(k).strip()]
    if not kws:
        raise SystemExit("❌ 计划里没有 keywords，没法验")
    kw = kws[keyword_index]
    conds = [str(c).strip() for c in (plan.get("conds") or []) if str(c).strip()]

    log: dict = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "plan": plan_p.as_posix(), "keyword": kw, "conds": conds}
    tab = find_liepin_tab()
    log["tab_id"] = tab
    print(f"▶ tab: {tab}")

    r = submit_task(BRIDGE, "navigate", {"tab_id": tab, "url": COND_URL}, source="cond-probe")
    if not r.get("ok"):
        raise SystemExit(f"❌ navigate 失败: {r.get('error')}")
    time.sleep(WAIT_NAV)
    log["clear_before_ok"] = _clear(tab)

    spec = [{"group_id": "keyword", "value": kw}] + _split_conds(conds)
    print(f"▶ 执行条件：关键字「{kw}」 + {conds}")
    res = execute_spec(spec, tab, do_search=True, do_extract=False)
    body, snap = _body(tab)
    log["execute_spec"] = {"ok": res.get("ok"), "failed": res.get("failed"),
                           "verify_failed": res.get("verify_failed"), "error": res.get("error"),
                           "steps": [{k: v for k, v in s.items() if k != "input_value"} for s in res.get("steps") or []]}
    log["after_search"] = {"url": snap.get("url"), "anchors_immediate_chat": _anchor_count(snap),
                           "elements": len(snap.get("elements") or []), "tag_window": _tag_window(body)}

    # ── 学历"能不能多选"探针（C 的事实依据）──
    # ⚠️ 必须先清空：execute_spec 刚把 education=本科 选上了；chip 是**开关**，不清再点『本科』
    #    等于**反选掉** → 会把"可多选"误判成"单选"。清干净再点，才是干净实验。
    if probe_multi and multi_values:
        log["clear_before_multi_ok"] = _clear(tab)
        groups = {g["id"]: g for g in (load_recipes(url=snap.get("url") or COND_URL).get("groups") or [])}
        g = groups.get(probe_multi) or {}
        ctm = (g.get("locate") or {}).get("click_text_map") or {}
        p: dict = {"group_id": probe_multi, "group_name": g.get("name"), "group_type": g.get("type"),
                   "values": multi_values, "after_each": []}
        for v in multi_values:
            click_text = ctm.get(v, v)
            cr = submit_task(BRIDGE, "click_by_text",
                             {"tab_id": tab, "text": click_text, "occurrence": 1}, source="cond-probe")
            time.sleep(WAIT_CHIP)
            b2, s2 = _body(tab)
            win = _tag_window(b2)
            seen = [x for x in multi_values if x in win]
            p["after_each"].append({"clicked": v, "click_text": click_text, "click_ok": cr.get("ok"),
                                    "error": cr.get("error"), "seen_in_tag_area": seen,
                                    "anchors_immediate_chat": _anchor_count(s2),
                                    "url": s2.get("url"), "tag_window_tail": win[-160:]})
            print(f"   点『{v}』→ 已选标签区里看到 {seen or '（无）'}｜锚点 {_anchor_count(s2)}")
        last = p["after_each"][-1] if p["after_each"] else {}
        seen_last = last.get("seen_in_tag_area") or []
        p["verdict"] = ("multiple（可多选）" if all(x in seen_last for x in multi_values)
                        else "single（单选：新点的手替换了前一个）" if len(seen_last) <= 1
                        else "unclear（标签区没读到，看 tag_window_tail/手工快照）")
        log["multi_probe"] = p

    log["clear_after_ok"] = _clear(tab)
    return log


def summarize(log: dict) -> str:
    es = log.get("execute_spec") or {}
    lines = [f"计划：{log['plan']}",
             f"关键字：{log['keyword']}｜条件：{log['conds']}",
             f"execute_spec：ok={es.get('ok')}" + (f"｜failed={es.get('failed')}" if es.get("failed") else "")
             + (f"｜verify_failed={es.get('verify_failed')}" if es.get("verify_failed") else "")
             + (f"｜error={es.get('error')}" if es.get("error") else "")]
    for i, s in enumerate(es.get("steps") or [], 1):
        if "group_id" in s:
            lines.append(f"  [{i}] {s['group_id']}={s.get('value')}（{s.get('type')}）ok={s.get('ok')} "
                         f"verify={s.get('verify')}")
        else:
            lines.append(f"  [{i}] {s.get('action')} ok={s.get('ok')}")
    a = log.get("after_search") or {}
    lines.append(f"结果页：锚点 {a.get('anchors_immediate_chat')} 个｜元素 {a.get('elements')}｜URL {a.get('url')}")
    lines.append(f"已选标签区：{a.get('tag_window') or '（没读到 body_preview）'}")
    mp = log.get("multi_probe")
    if mp:
        lines.append(f"多选探针（{mp['group_id']}）：{mp.get('verdict')}")
    lines.append(f"收尾清空：{log.get('clear_after_ok')}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="collect_plan_*.json 路径")
    ap.add_argument("--keyword-index", type=int, default=0, help="用计划里第几个关键字（默认 0）")
    ap.add_argument("--probe-multi", default="education", help="验'能不能多选'的条件组（空串=不验）")
    ap.add_argument("--multi-values", default="本科,硕士", help="多选探针依次点的值（逗号分隔）")
    ap.add_argument("--out", default=None, help="JSON 日志输出路径（默认 data/usage/cond_probe_<ts>.json）")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else (Path(__file__).resolve().parent / "data" / "usage" / f"cond_probe_{ts}.json")
    mvals = [v.strip() for v in (args.multi_values or "").split(",") if v.strip()]

    log = probe(Path(args.plan), args.keyword_index, args.probe_multi, mvals)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + summarize(log))
    print(f"\n✅ 校验日志：{out.as_posix()}")


if __name__ == "__main__":
    main()
