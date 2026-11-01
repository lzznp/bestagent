#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""filter_run.py — **细筛**：逐人调 LLM 给候选人打分（老板 2026-09-17 拍板）

分工（承接项目铁律「**脑 = 小猎，手 = 脚本**」）：
  · `collect_exec.py`（采集）= **粗筛**：本地规则 + 关键词、0 token，负责把池子捞回来 + 值得开详情的开详情；
  · **本脚本** = **细筛**：把 JD + 该候选人的简历**逐人**发给 LLM → score/verdict/匹配点/疑虑点/总结
    → 落本岗库 `match_results`（**带输入指纹缓存**：同输入第二次跑 = 0 花费）；
  · 打招呼报告 = 读 `match_results` 渲染（下一步，另写）。

⚠️ 参考实现（老板指定的两份参考代码，都读过、细节照抄）：
  · `参考代码/recruitment-streamlit-v2/services/deepseek_service.py` = **蓝图**（两段式：规则粗筛 → LLM 精筛；
    重试/错误分类/`#` 注释行剥离/```json 围栏容错）；
  · `参考代码/recruitment-wails/` = **实现**（逐人一次调用 + `sha256(岗位␟候选人␟口径)` 缓存 + 高分才生成话术）。

🔴 口径是**数据**不是代码（老板要的"弹性"）：阈值/宽松度/名额/口径文字**全部从 `--plan` 的 JSON 读**，
提示词按它动态拼（`match_prompt.txt` 的 `{criteria}` 段）。改口径 = 改 JSON，**代码一行不动**。

用法（cwd = bestagent/）：
  # 0 花费：只算"这轮要评几人、大概多少 token"（不联网、不写库）
  python filter_run.py --job-code J-... --plan data/chat/<岗>/reports/greeting_plan_xxx.json --dry-run
  # 先小样（只评前 5 个，省钱试水）
  python filter_run.py --job-code J-... --plan <plan>.json --limit 5
  # 全量（已评过且口径没变的人自动跳过 → 增量）
  python filter_run.py --job-code J-... --plan <plan>.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import PROMPTS, WORKSPACE  # noqa: E402

import job_db  # noqa: E402
import llm_client as llm  # noqa: E402

CHAT = WORKSPACE / "data" / "chat"
MATCH_TPL = "match_prompt.txt"
GREET_TPL = "greeting_prompt.txt"
VERDICTS = ("推荐", "待定", "不推荐")

# 口径默认值（**都可以被 plan 覆盖**；plan 里没写的用这里的）
DEFAULTS = {"strictness": "标准", "threshold": 70, "max_list": 15, "scope": "incremental",
            "include_card_only": True, "criteria": "", "special_notes": "", "boss_words": ""}


# ── 计划（小猎写的小 JSON；口径的唯一来源）──────────────────────────────────

def load_plan(plan_path) -> dict:
    p = Path(plan_path)
    if not p.exists():
        raise SystemExit(f"❌ 口径计划不存在：{p}（先让小猎写一份 greeting_plan_*.json）")
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"❌ 口径计划不是合法 JSON：{p}｜{e}")
    if not isinstance(d, dict):
        raise SystemExit(f"❌ 口径计划顶层必须是对象：{p}")
    for k, v in DEFAULTS.items():
        d.setdefault(k, v)
    return d


def criteria_text(plan: dict) -> str:
    """把计划里的口径拼成**发给模型的那段话**（= 老板说的"提示词动态生成"）。"""
    parts: list[str] = []
    st = str(plan.get("strictness") or "").strip()
    if st:
        parts.append(f"宽松度：{st}（严格=硬性条件不满足即「不推荐」；标准=按默认标准；"
                     f"宽松=硬性条件只作参考，不满足可降档、只记进 concerns）")
    if str(plan.get("criteria") or "").strip():
        parts.append(str(plan["criteria"]).strip())
    if str(plan.get("boss_words") or "").strip():
        parts.append(f"老板原话：{plan['boss_words']}（上面这句是老板本人说的，按他的意图来）")
    if str(plan.get("special_notes") or "").strip():
        parts.append(f"特别提醒：{plan['special_notes']}")
    return "\n".join(parts) if parts else "（本次没有额外口径，按默认评分标准打分）"


def input_hash(job_text: str, cand_text: str, criteria: str) -> str:
    """匹配输入指纹：**岗位原文 ␟ 候选人原文 ␟ 本次口径** 任一变化 → 缓存自动失效（要重评）。"""
    h = hashlib.sha256()
    h.update(f"{job_text}\x1f{cand_text}\x1f{criteria}".encode("utf-8"))
    return h.hexdigest()


def candidate_text(row: dict) -> str:
    """给模型的"候选人信息"：有全文用全文；只有卡片就用卡片（**如实标注**，不假装是全文）。"""
    raw = str(row.get("raw_content") or "").strip()
    if raw:
        return raw
    return str(row.get("summary_text") or "").strip()


def build_prompt(tpl: str, job_text: str, cand_text: str, crit: str,
                 special: str = "") -> str:
    return llm.fill(tpl, job_raw_text=job_text, candidate_raw_text=cand_text,
                    criteria=crit, special_notes=special or "（本次无）")


# ── 库读写（细筛结果的落点）────────────────────────────────────────────────

def fetch_rows(con, job_code: str) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT id, source_id, display_name, raw_content, summary_text, local_score, "
        "local_hits, round_tag, status FROM candidates WHERE job_code=? ORDER BY id", (job_code,))]


def cached_row(con, job_code: str, cand_id: int) -> dict | None:
    r = con.execute("SELECT * FROM match_results WHERE job_code=? AND candidate_id=?",
                    (job_code, cand_id)).fetchone()
    return dict(r) if r else None


def _detail_of(match: dict | None) -> dict:
    if not match:
        return {}
    try:
        d = json.loads(match.get("detail_json") or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _norm_verdict(v, score: int) -> str:
    s = str(v or "").strip()
    if s in VERDICTS:
        return s
    return "推荐" if score >= 70 else ("待定" if score >= 50 else "不推荐")


def _strlist(x) -> list[str]:
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    if isinstance(x, str) and x.strip():
        return [x.strip()]
    return []


def evaluate_one(*, con, job_code: str, row: dict, job_text: str, crit: str,
                 tpl: str, env: dict, chat_fn, plan: dict, model: str | None = None) -> dict:
    """评一个人：调 LLM → 规范化 → 落 match_results。返回本次记录（含 error/tokens）。"""
    text = candidate_text(row)
    card_only = not str(row.get("raw_content") or "").strip()
    h = input_hash(job_text, text, crit)
    prompt = build_prompt(tpl, job_text, text, crit)
    rec = {"candidate_id": row["id"], "source_id": row["source_id"],
           "name": row.get("display_name") or "", "card_only": card_only, "tokens": 0}
    try:
        got = chat_fn(env, prompt, temperature=0.3, max_tokens=1200, json_mode=True,
                      model=model)
    except llm.LLMError as e:
        rec["error"] = e.human()
        rec["error_code"] = e.code
        return rec
    rec["tokens"] = int(got.get("tokens") or 0)
    try:
        out = llm.parse_json(got.get("content") or "")
    except llm.LLMError as e:
        rec["error"] = e.human()
        rec["error_code"] = e.code
        return rec
    try:
        score = int(round(float(out.get("score") or 0)))
    except Exception:  # noqa: BLE001
        score = 0
    score = max(0, min(100, score))
    verdict_raw = out.get("verdict", out.get("decision"))
    verdict = _norm_verdict(verdict_raw, score)
    detail = {"tokens": rec["tokens"], "model": got.get("model") or (model or ""),
              "criteria": crit, "strictness": str(plan.get("strictness") or ""),
              "threshold": int(plan.get("threshold") or 0),
              "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "on_card_only": card_only, "verdict_raw": str(verdict_raw or ""),
              "score_raw": out.get("score")}
    job_db.save_match(con, job_code, row["id"], {
        "score": score, "verdict": verdict, "confidence": out.get("confidence") or "",
        "match_points": _strlist(out.get("match_points")), "concerns": _strlist(out.get("concerns")),
        "summary": str(out.get("summary") or ""), "detail": detail,
    }, raw_hash=h)
    rec.update({"score": score, "verdict": verdict, "raw_hash": h[:16]})
    return rec


def greeting_for(*, con, job_code: str, cand_id: int, name: str, score: int,
                 match: dict, job_title: str, job_meta: dict, crit: str,
                 tpl: str, env: dict, chat_fn, model: str | None = None) -> dict:
    """给入围者预生成 2 条话术，**存进 detail_json**（不改 schema；老板要"话术预先做好、小猎直接用"）。"""
    detail = _detail_of(match)
    if detail.get("greeting_msg1"):
        return {"candidate_id": cand_id, "skipped": "已有话术"}
    brief = (match.get("summary") or "")[:120]
    prompt = llm.fill(tpl, candidate_name=name or "这位候选人", candidate_brief=brief,
                      job_title=job_title or "", company=job_meta.get("company") or "",
                      city=job_meta.get("city") or "", salary=job_meta.get("salary") or "",
                      score=score, match_points="；".join(_strlist(match.get("match_points"))) or "（无）",
                      criteria=crit)
    try:
        got = chat_fn(env, prompt, temperature=0.7, max_tokens=600, json_mode=True, model=model)
        out = llm.parse_json(got.get("content") or "")
    except llm.LLMError as e:
        return {"candidate_id": cand_id, "error": e.human()}
    detail.update({"greeting_msg1": str(out.get("msg1") or "").strip(),
                   "greeting_msg2": str(out.get("msg2") or "").strip(),
                   "greeting_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "greeting_tokens": int(got.get("tokens") or 0)})
    job_db.save_match(con, job_code, cand_id, {"detail": detail})
    return {"candidate_id": cand_id, "tokens": int(got.get("tokens") or 0),
            "msg1": detail["greeting_msg1"][:40]}


# ── 主流程 ────────────────────────────────────────────────────────────────

def run(job_code: str, plan: dict, *, env: dict | None = None, chat_fn=None,
        db_root: Path | None = None, dry_run: bool = False, limit: int = 0,
        model: str | None = None, prompts_dir: Path | None = None,
        chat_dir: Path | None = None, plan_path=None) -> dict:
    """细筛主流程（`chat_fn` 可注入 → 单测用假 LLM，**绝不真联网**）。"""
    env = env if env is not None else llm.load_env()
    chat_fn = chat_fn or llm.chat
    pd = Path(prompts_dir) if prompts_dir else PROMPTS
    base = Path(chat_dir) if chat_dir else CHAT
    jc = str(job_code or plan.get("job_code") or "").strip()
    if not jc:
        # 与采集同一个纪律（上一场 bug①：缺 job_code 会把数据写进野库）→ 宁可跑不起来
        raise ValueError("filter_run: 缺 job_code（计划里没有、命令行也没给）——宁可报错，不写错岗")
    started = time.time()
    crit = criteria_text(plan)
    threshold = int(plan.get("threshold") or DEFAULTS["threshold"])
    jd_path = base / jc / "jd.txt"
    job_text = jd_path.read_text(encoding="utf-8") if jd_path.exists() else ""
    if not job_text.strip():
        raise SystemExit(f"❌ 这个岗没有 jd.txt（{jd_path}）——没有 JD 就没法细筛")
    tpl = llm.load_prompt(pd / MATCH_TPL)
    gtpl = llm.load_prompt(pd / GREET_TPL)
    trace = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "job_code": jc,
             "plan_file": str(plan_path or ""), "plan": plan, "criteria": crit,
             "threshold": threshold, "dry_run": bool(dry_run),
             "model": model or env.get("DEEPSEEK_MODEL"),
             "evaluated": [], "skipped_cached": [], "skipped_empty": [],
             "greetings": [], "errors": [], "notes": []}
    con = job_db.open_db(jc, root=db_root)
    try:
        rows = fetch_rows(con, jc)
        targets, plan_tokens = [], 0
        for r in rows:
            text = candidate_text(r)
            if not text:
                trace["skipped_empty"].append(r["id"])
                continue
            if not plan.get("include_card_only", True) and not str(r.get("raw_content") or "").strip():
                trace["skipped_empty"].append(r["id"])
                continue
            h = input_hash(job_text, text, crit)
            hit = job_db.get_cached_match(con, jc, r["id"], h)
            if hit and str(plan.get("scope")) != "all":
                trace["skipped_cached"].append(r["id"])
                continue
            targets.append((r, text, h))
            plan_tokens += llm.estimate_tokens(build_prompt(tpl, job_text, text, crit))
        if limit:
            targets = targets[:limit]
        trace["counts"] = {"candidates": len(rows), "targets": len(targets),
                           "skipped_cached": len(trace["skipped_cached"]),
                           "skipped_empty": len(trace["skipped_empty"])}
        trace["estimate"] = {"input_tokens": plan_tokens, "note": "**数量级估算**（字节/2.5），非精确值"}
        print(f"▶ 细筛 {jc}｜口径：{plan.get('strictness')}｜入围线 {threshold}｜"
              f"名单上限 {plan.get('max_list')}")
        print(f"  {crit}")
        print(f"  候选人 {len(rows)}｜本轮要评 {len(targets)}｜"
              f"已评过且口径没变（跳过、0 花费）{len(trace['skipped_cached'])}｜"
              f"没简历文本跳过 {len(trace['skipped_empty'])}")
        print(f"  预计输入 ~{plan_tokens} 词元（数量级估算）｜模型 {trace['model']}")
        if dry_run:
            for r, _t, _h in targets[:20]:
                print(f"    · {r.get('display_name') or r['source_id'][:12]}"
                      f"（{'仅卡片' if not str(r.get('raw_content') or '').strip() else '有全文'}）")
            if len(targets) > 20:
                print(f"    …… 另有 {len(targets) - 20} 人")
            trace["notes"].append("dry-run：只算账，没调 LLM、没写库")
            print("\n（dry-run：一分钱没花、一个模型都没调）")
            return trace

        for i, (r, text, h) in enumerate(targets, 1):
            rec = evaluate_one(con=con, job_code=jc, row=r, job_text=job_text, crit=crit,
                               tpl=tpl, env=env, chat_fn=chat_fn, plan=plan, model=model)
            trace["evaluated"].append(rec)
            if rec.get("error"):
                trace["errors"].append({"candidate_id": rec["candidate_id"], "error": rec["error"]})
                print(f"  [{i}/{len(targets)}] ❌ {rec.get('name') or rec['source_id'][:12]}"
                      f"：{rec['error']}")
            else:
                print(f"  [{i}/{len(targets)}] ✅ {rec.get('name') or rec['source_id'][:12]}"
                      f"｜{rec['score']} 分 {rec['verdict']}"
                      f"（{'仅卡片' if rec['card_only'] else '全文'}）")

        # 话术：只对**过线**的人生成（老板口径：分数不够的不进报告，也就不生成话术）
        jm = _job_meta(jc, con, base)
        for rec in trace["evaluated"]:
            if rec.get("error") or (rec.get("score") or 0) < threshold:
                continue
            match = cached_row(con, jc, rec["candidate_id"]) or {}
            g = greeting_for(con=con, job_code=jc, cand_id=rec["candidate_id"],
                             name=rec.get("name") or "", score=rec.get("score") or 0,
                             match=match, job_title=jm.get("title") or "", job_meta=jm,
                             crit=crit, tpl=gtpl, env=env, chat_fn=chat_fn, model=model)
            trace["greetings"].append(g)
        trace["tokens_total"] = sum(int(x.get("tokens") or 0) for x in trace["evaluated"]) + \
            sum(int(x.get("tokens") or 0) for x in trace["greetings"])
        rate = str(env.get("DEEPSEEK_COST_PER_1K") or "").strip()
        try:
            trace["cost_total"] = round(trace["tokens_total"] / 1000 * float(rate), 4) if rate else None
        except ValueError:
            trace["cost_total"] = None      # 费率写错了就不报钱（宁可不报，也不报假数）
        trace["limit"] = limit
        trace["elapsed_sec"] = round(time.time() - started, 1)
        trace["db_path"] = str(job_db.db_path(jc, root=db_root))
        good = [x for x in trace["evaluated"] if not x.get("error")]
        trace["summary"] = {
            "evaluated": len(good), "failed": len(trace["errors"]),
            "推荐": sum(1 for x in good if x["verdict"] == "推荐"),
            "待定": sum(1 for x in good if x["verdict"] == "待定"),
            "不推荐": sum(1 for x in good if x["verdict"] == "不推荐"),
            "入围(≥%d)" % threshold: sum(1 for x in good if (x.get("score") or 0) >= threshold),
            "话术": len([g for g in trace["greetings"] if g.get("tokens")]),
            "tokens": trace["tokens_total"], "cost": trace["cost_total"],
            "elapsed_sec": trace["elapsed_sec"]}
        print(f"\n✅ 细筛完成：评了 {len(good)}｜推荐 {(trace['summary'])['推荐']}｜"
              f"待定 {(trace['summary'])['待定']}｜不推荐 {(trace['summary'])['不推荐']}｜"
              f"入围(≥{threshold}) {(trace['summary'])['入围(≥%d)' % threshold]}｜"
              f"话术 {trace['summary']['话术']}｜{trace['tokens_total']} 词元"
              + (f"｜约 ¥{trace['cost_total']}" if trace["cost_total"] is not None else ""))
        return trace
    finally:
        con.close()


def _job_meta(job_code: str, con, base: Path) -> dict:
    """岗位元信息（发话术要用到公司/城市/薪资）：优先分析报告（analyze_*.json 的 jd_extracted）。"""
    out = {"title": "", "company": "", "city": "", "salary": ""}
    reps = base / job_code / "reports"
    ana = sorted(reps.glob("analyze_*.json")) if reps.exists() else []
    if ana:
        try:
            d = json.loads(ana[-1].read_text(encoding="utf-8-sig"))
            jd = d.get("jd_extracted") or {}
            out.update({"title": jd.get("job_title") or "", "company": jd.get("company") or "",
                        "city": jd.get("city") or "", "salary": jd.get("salary") or ""})
        except Exception:  # noqa: BLE001
            pass
    try:
        r = con.execute("SELECT title FROM job_meta WHERE job_code=?", (job_code,)).fetchone()
        if r and r["title"] and not out["title"]:
            out["title"] = r["title"]
    except Exception:  # noqa: BLE001
        pass
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="细筛：逐人调 LLM 打分（口径从 --plan 读）")
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--plan", required=True, help="口径计划 greeting_plan_*.json（阈值/宽松度/口径文字）")
    ap.add_argument("--env-file", default=None, help=".env 路径（默认 = bridge-agent/.env）")
    ap.add_argument("--model", default=None, help="覆盖模型名（默认读 .env / deepseek-chat）")
    ap.add_argument("--dry-run", action="store_true", help="只算账：要评几人、大概多少 token（0 花费）")
    ap.add_argument("--limit", type=int, default=0, help="只评前 N 人（小样试水，省钱）")
    ap.add_argument("--force", action="store_true", help="口径没变也重评（scope=all）")
    ap.add_argument("--out", default=None, help="轨迹 JSON 落点（默认本岗 reports/filter_run_<ts>.json）")
    args = ap.parse_args()

    plan = load_plan(args.plan)
    if args.force:
        plan["scope"] = "all"
    env = llm.load_env(args.env_file)
    if not args.dry_run and not env.get("DEEPSEEK_API_KEY"):
        raise SystemExit(f"❌ .env 里没有 DEEPSEEK_API_KEY：{env.get('_env_file')}")
    trace = run(args.job_code, plan, env=env, dry_run=args.dry_run, limit=args.limit,
                model=args.model, plan_path=args.plan)
    if args.dry_run:
        return
    reports = CHAT / args.job_code / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else reports / f"filter_run_{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 轨迹：{out.as_posix()}")


if __name__ == "__main__":
    main()
