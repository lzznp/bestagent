#!/usr/bin/env python3
"""数字合伙人 v1.0 统一入口：贴一个 JD → 全链路（岗前分析 → 采集 → 评估 → 直写库 → 老板汇报）

用法:
  # 全链路（默认）：岗前分析 → 采集 → 评估 → 直写 business.db
  python run_pipeline.py --jd data/inbox/jd_xxx.txt --env-file <path/.env>

  # 只跑单步（--step 可多次）
  python run_pipeline.py --jd ... --env-file ... --step analyze            # 只岗前分析
  python run_pipeline.py --jd ... --env-file ... --step collect --keywords GPGPU
  python run_pipeline.py --jd ... --env-file ... --step eval --skip-collect
  python run_pipeline.py --jd ... --env-file ... --step import --skip-collect

  # 常用参数
  --keywords KW1 KW2        采集关键字（默认取岗前分析报告的 search_keywords）
  --conds city_current=北京 采集条件，可多次（学历 education=博士/博士后、年限 years=应届生…）
  --requirements "..."      岗位硬性条件（评估评分依据；默认从岗前分析报告提取）
  --job-code/--job-title/--company/--salary/--city   写库岗位信息（默认从 JD 文件名/报告推断）
  --skip-collect            跳过采集（复用已有采集文件）
  --no-quota                采集跳过限速（调试用）
  --batch N                 评估分批人数上限（默认 72，HANDOFF 教训 5）
  --dry-run                 只打印计划，不执行

边界（授权矩阵）：采集限量限速（quota）；打招呼/下载联系方式等不可逆动作不在本链路。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from framework_config import (
    WORKSPACE, INBOX, OUTBOX, PROMPTS, DB_PATH,
    EVAL_BATCH, check_env, ensure_dirs, load_env_file,
)

# 各步骤模块（90% 原样复用，只做接线）
import m1_run          # analyze_job()
import m2_eval_run     # eval_pool()
import collect_liepin  # collect()
import import_to_db    # write_to_db()


def extract_keywords(report: dict) -> list[str]:
    """从岗前分析报告提取采集关键字（兼容 dict/列表/字符串多种结构），去重保序。"""
    kws: list[str] = []
    src = report.get("search_keywords") or report.get("keywords") or {}
    if isinstance(src, dict):
        for v in src.values():
            if isinstance(v, str):
                kws.extend(w.strip() for w in v.replace("，", " ").replace(",", " ").split() if w.strip())
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, str) and x.strip():
                        kws.append(x.strip())
    elif isinstance(src, list):
        for v in src:
            if isinstance(v, str) and v.strip():
                kws.extend(w.strip() for w in v.replace("，", " ").replace(",", " ").split() if w.strip())
            elif isinstance(v, dict):
                for x in v.values():
                    if isinstance(x, str) and x.strip():
                        kws.append(x.strip())
    seen: set[str] = set()
    out: list[str] = []
    for w in kws:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def extract_requirements(report: dict, fallback: str) -> str:
    """岗位硬性条件：优先报告里的难度说明（冒号后），否则用传入 fallback。"""
    try:
        d = (report.get("score") or {}).get("details") or {}
        diff = d.get("difficulty") or {}
        val = diff.get("value") or ""
        if "：" in val:
            return val.split("：", 1)[1].strip()
        if ":" in val:
            return val.split(":", 1)[1].strip()
        if val:
            return val.strip()
    except Exception:
        pass
    return fallback


def merge_eval_reports(part_files: list[Path], out: Path) -> None:
    """合并分批评估报告（同 merge_report.py 逻辑）：pool_quality + candidates 按 id 排序。"""
    pool = None
    cands: dict[int, dict] = {}
    for f in part_files:
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8-sig"))
        if data.get("pool_quality"):
            pool = data["pool_quality"]
        for c in data.get("candidates", []):
            cid = c.get("candidate_id")
            if cid is not None:
                cands[cid] = c
            else:
                cands[len(cands) + 1] = c
    ordered = [cands[k] for k in sorted(cands)]
    result: dict = {}
    if pool:
        result["pool_quality"] = pool
    result["candidates"] = ordered
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 合并 {len(part_files)} 个评估报告 → {out.name}：pool_quality={'有' if pool else '无'}，candidates={len(ordered)} 条")


def main() -> None:
    ap = argparse.ArgumentParser(description="数字合伙人 v1.0：贴 JD → 分析/采集/评估/直写库/汇报")
    ap.add_argument("--jd", type=Path, required=True, help="JD 文件路径（data/inbox/ 下）")
    ap.add_argument("--env-file", type=Path, required=True)
    ap.add_argument("--step", action="append", default=None,
                    choices=["analyze", "collect", "eval", "import"], help="只跑指定步骤（可多次）")
    ap.add_argument("--keywords", action="append", default=None, help="采集关键字，可多次")
    ap.add_argument("--conds", action="append", default=None, help="采集条件 group_id=value，可多次")
    ap.add_argument("--requirements", default=None, help="岗位硬性条件（评估评分依据）")
    ap.add_argument("--job-code", default=None)
    ap.add_argument("--job-title", default=None)
    ap.add_argument("--company", default=None)
    ap.add_argument("--salary", default=None)
    ap.add_argument("--city", default=None)
    ap.add_argument("--skip-collect", action="store_true", help="跳过采集（复用已有采集文件）")
    ap.add_argument("--no-quota", action="store_true", help="采集跳过限速（调试用）")
    ap.add_argument("--batch", type=int, default=EVAL_BATCH, help=f"评估分批人数上限（默认 {EVAL_BATCH}）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划不执行")
    args = ap.parse_args()

    ensure_dirs()
    problems = check_env()
    if problems:
        print("⚠ 环境自检发现异常（继续运行可能失败）：")
        for p in problems:
            print(f"   - {p}")

    jd = Path(args.jd)
    if not jd.is_absolute():
        jd = WORKSPACE / jd
    if not jd.exists():
        print(f"❌ JD 不存在: {jd}")
        sys.exit(1)
    base = jd.stem
    report_path = OUTBOX / f"report_{base}.json"
    collect_out = OUTBOX / f"collected_{base}.json"
    eval_out = OUTBOX / f"pool_report_{base}.json"

    steps = args.step or ["analyze", "collect", "eval", "import"]
    print("─" * 60)
    print(f"▶ JD      : {jd}")
    print(f"▶ 步骤    : {' → '.join(steps)}")
    print(f"▶ 输出    : {report_path.name} / {collect_out.name} / {eval_out.name}")
    print(f"▶ 业务库  : {DB_PATH}")
    print("─" * 60)
    if args.dry_run:
        print("✅ 计划如上（--dry-run 不执行）")
        return

    env = load_env_file(args.env_file)
    if "DEEPSEEK_API_KEY" not in env:
        print("❌ .env 里没有 DEEPSEEK_API_KEY")
        sys.exit(1)

    # 岗位信息（写库用；默认从 JD 文件名推断，可覆盖）
    job = {
        "job_code": args.job_code or base,
        "job_title": args.job_title or "",
        "link": "",
        "company_name": args.company or "",
        "salary_range": args.salary or "",
        "city": args.city or "",
        "status": "active",
    }
    report: dict = {}

    # ── ① 岗前分析 ────────────────────────────────────────────────
    if "analyze" in steps:
        print("\n════ ① 岗前分析 ════")
        env_p = dict(env)
        env_p["DSH_SYSTEM_PROMPT"] = m1_run.PERSONA
        r = m1_run.analyze_job(jd, report_path, f"pipe-analyze-{base}", env_p)
        print("\n📣 老板汇报（岗前分析）：")
        print(r.final_response)
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            job["job_title"] = args.job_title or report.get("jd_extracted", {}).get("job_title") or job["job_title"]
        else:
            print("⚠ 岗前分析报告未生成（继续将缺关键字/岗位条件）")

    # ── ② 采集 ─────────────────────────────────────────────────────
    if "collect" in steps:
        print("\n════ ② 猎聘采集 ════")
        if not report and report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        keywords = list(args.keywords) if args.keywords else extract_keywords(report)
        if not keywords:
            print("❌ 没有采集关键字：请用 --keywords 提供，或先跑 analyze 步骤")
            sys.exit(1)
        conds = args.conds or []
        print(f"▶ 关键字: {keywords}")
        print(f"▶ 条件  : {conds}")
        if args.skip_collect and collect_out.exists():
            print(f"⏭ --skip-collect，复用已有采集文件: {collect_out.name}")
        else:
            collect_liepin.collect(keywords, conds=conds, out=collect_out, no_quota=args.no_quota)

    # ── ③ 池子评估（自动分批 ≤ batch 人/批） ────────────────────────
    if "eval" in steps:
        print("\n════ ③ 池子评估 ════")
        if not report and report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        if not collect_out.exists():
            print(f"❌ 采集文件不存在: {collect_out}（先跑 collect 或 --skip-collect）")
            sys.exit(1)
        collect_data = json.loads(collect_out.read_text(encoding="utf-8-sig"))
        n = len(collect_data.get("rows", []))
        if n == 0:
            print("❌ 采集结果为空，跳过评估")
        else:
            requirements = args.requirements or extract_requirements(report, m2_eval_run.DEFAULT_REQUIREMENTS)
            print(f"▶ 候选人 {n} 位，分批 ≤{args.batch}/批")
            print(f"▶ 岗位硬性条件: {requirements[:80]}…")
            env_p = dict(env)
            env_p["DSH_SYSTEM_PROMPT"] = m2_eval_run.PERSONA
            parts: list[Path] = []
            for batch_no, start in enumerate(range(1, n + 1, args.batch), start=1):
                end = min(start + args.batch - 1, n)
                skip_pool = batch_no > 1
                part = OUTBOX / f"{eval_out.stem}_part{batch_no}.json"
                parts.append(part)
                r = m2_eval_run.eval_pool(
                    jd, collect_out, part, requirements,
                    f"pipe-eval-{base}-p{batch_no}", env_p,
                    start=start, end=end, skip_pool=skip_pool,
                )
                print(f"\n📣 老板汇报（第 {batch_no} 批）：")
                print(r.final_response)
            merge_eval_reports(parts, eval_out)

    # ── ④ 直写业务库（闭环，省掉 import_to_db 手动一步） ─────────────
    if "import" in steps:
        print("\n════ ④ 直写业务库 ════")
        if not collect_out.exists():
            print(f"❌ 无采集文件: {collect_out}")
            sys.exit(1)
        if not eval_out.exists():
            print(f"❌ 无评估报告: {eval_out}（先跑 eval）")
            sys.exit(1)
        if not report and report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        n_c, n_m = import_to_db.write_to_db(
            job, jd, [(collect_out, eval_out)],
            db_path=DB_PATH,
            analyze_report=report_path if report_path.exists() else None,
        )
        print(f"✅ 直写库完成：新增候选人 {n_c}，匹配结果 {n_m}")

    print("\n" + "═" * 60)
    print("✅ 全链路完成。产出：")
    for p in (report_path, collect_out, eval_out):
        print(f"   {p}（{p.stat().st_size if p.exists() else 0} 字节）")
    print(f"   业务库: {DB_PATH}")


if __name__ == "__main__":
    main()
