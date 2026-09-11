#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_job.py — 数字合伙人 v1.6.8 档1：新岗一条龙（JD → 打招呼清单 HTML，到人工闸门停）

合成 2026-09-05 中兴微新单的**手工链路**为一条命令：
  ① 岗前分析（analyze_<ts>.json）→ ② 出采集计划（collect_plan_<ts>.json，**请老板确认才真跑**）
  → 采集（collected_<ts>.json，配方表 + 限速）→ ③ 分批评估 ≤72/批（pool_part_*.json）
  → 合并 pool_report_<ts>.json + 本地渲染 匹配报告_<ts>.html → ④ 详情深采（detail_*.txt，查看量保险丝）
  → 💬 打招呼数据 ≤5/批（greet_part_*.json → 合并 greet_<ts>.json）→ **本地渲染 打招呼清单_<ts>.html** → 停。

边界（授权矩阵）：
  - ② 采集计划 = 闸门：一条龙在出计划后停下问老板确认（--yes 无人值守跳过）；
  - ④ 详情深采 = 查看量风控点：默认再问一次（每个详情 = 1 次查看量，detail 100/天 保险丝）；
  - 打招呼 = 永远人工闸门：本脚本只产 清单 HTML（直达链接+话术），绝不代发。
  - 数据/展示分离：LLM 只产小 JSON，HTML 一律本地模板渲染（report_html.py），不让 agent 手写大文件。

用法（cwd = bestagent\\，解释器 lzstudy）：
  # 一条龙（新岗，幂等续跑）：缺啥补啥；跑完会停在闸门等你确认
  python auto_job.py --jd data/inbox/<新JD>.txt --env-file <path/.env>
  #   第 1 次：analyze + plan → 停（看计划）；同一条命令再跑：问“按计划继续？”→ y 后一路跑到打招呼清单
  # 无人值守（自动按计划跑；打招呼仍停人工）
  python auto_job.py --jd data/inbox/<新JD>.txt --env-file <path/.env> --yes
  # 复用已有岗 / 强制重跑指定步骤（--step 可多次）
  python auto_job.py --job-code J-AUTO-20260906-100000 --env-file <path/.env> --step eval --step greet
  python auto_job.py --job-code J-AUTO-20260906-100000 --step html          # 只本地渲染打招呼清单（0 token）
  # 常用参数
  --skip-detail         一条龙跳过详情深采（省查看量；打招呼只剩列表摘要口径）
  --detail-limit N      详情深采人数上限（默认 15，0=不限，100/天 保险丝兜底）
  --greet-limit N       打招呼入围上限（默认 15，0=不限）
  --keywords/--conds    覆盖计划文件的关键字/条件（如老板改主意，跳过出计划直接采集）
  --no-quota            采集/详情跳过限速（调试用）
  --batch N             评估分批人数上限（默认 72，HANDOFF 教训 5）
  --dry-run             只打印计划与产物路径，不调 API / 不碰浏览器
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 轻依赖顶层 import（m1_run/m2_eval_run/collect_liepin/detail_collect/greet_run 等在各步骤函数内延迟 import，
# 使 --help/--dry-run/纯本地步骤不依赖 SDK 与 bridge-agent）
from framework_config import (
    WORKSPACE, EVAL_BATCH, check_env, ensure_dirs, load_env_file, make_harness,
)

CHAT = WORKSPACE / "data" / "chat"

# 步骤清单（与面板步骤制对齐；业务汇报断点）
ALL_STEPS = ["analyze", "plan", "collect", "eval", "detail", "greet", "html"]
STEP_CN = {
    "analyze": "① 岗前分析", "plan": "② 采集计划", "collect": "② 采集执行",
    "eval": "③ 池子评估", "detail": "④ 详情深采", "greet": "💬 打招呼数据", "html": "HTML 渲染",
}
ONE_SHOT = ["analyze", "plan", "collect", "eval", "detail", "greet", "html"]  # 一条龙默认顺序

PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（一位猎头顾问）跑岗前分析、"
    "转搜索关键字、写报告、做汇报。做事原则：先思考再动手；信息不足时明确提问；"
    "输出务必严格按方法论手册的格式，不擅自改动；涉及性别/年龄/婚育等违法歧视要求要提示并忽略；"
    "干完活主动向老板汇报（“老板，我弄的咋样？”的口吻）。"
)


# ═══════════════════════ 工具：岗位目录 / 产物定位 ═══════════════════════

def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def job_dir(job_code: str) -> Path:
    return CHAT / job_code


def latest_file(reports: Path, prefix: str, suffix: str = ".json") -> Path | None:
    if not reports.is_dir():
        return None
    cands = [p for p in reports.glob(prefix + "*" + suffix) if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def latest_final(reports: Path, prefix: str, suffix: str = ".json") -> Path | None:
    """最新“成品”文件（排除 *_part_* 分片，如 greet_part 不是合并后的 greet）。"""
    if not reports.is_dir():
        return None
    cands = [p for p in reports.glob(prefix + "*" + suffix)
             if p.is_file() and "part" not in p.name[len(prefix):]]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def find_existing_job(jd_path: Path) -> str | None:
    """同内容 JD 是否已建档（幂等续跑用）：meta.jd_sha1 + jd.txt 字节双校验。"""
    sha = _sha1(jd_path)
    if not CHAT.is_dir():
        return None
    hits = []
    for d in CHAT.iterdir():
        if not d.is_dir():
            continue
        meta_p = d / "meta.json"
        jd_p = d / "jd.txt"
        if not (meta_p.exists() and jd_p.exists()):
            continue
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("jd_sha1") == sha and jd_p.read_bytes() == jd_path.read_bytes():
            hits.append(d)
    return max(hits, key=lambda d: d.stat().st_mtime).name if hits else None


def create_job(jd_path: Path, title: str = "") -> str:
    """新岗建档：data/chat/J-AUTO-<ts>/（jd.txt + reports/ + meta.json），返回 job_code。"""
    CHAT.mkdir(parents=True, exist_ok=True)
    ts = now_ts()
    job_code = f"J-AUTO-{ts}"
    d = job_dir(job_code)
    reports = d / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    jd_bytes = Path(jd_path).read_bytes()
    d.joinpath("jd.txt").write_bytes(jd_bytes)
    meta = {"job_code": job_code, "title": title or f"岗位 {job_code}",
            "jd_sha1": hashlib.sha1(jd_bytes).hexdigest(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": f"m3chat-{job_code}"}
    d.joinpath("meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return job_code


def job_title_of(job_code: str) -> str:
    """读 analyze 的岗位名（HTML 标题用），没有则 meta title（占位则退回 job_code）。"""
    ana = latest_file(job_dir(job_code) / "reports", "analyze_")
    if ana:
        try:
            je = json.loads(ana.read_text(encoding="utf-8-sig")).get("jd_extracted") or {}
            if je.get("job_title"):
                return str(je["job_title"])[:60]
        except Exception:
            pass
    mp = job_dir(job_code) / "meta.json"
    if mp.exists():
        try:
            t = json.loads(mp.read_text(encoding="utf-8")).get("title")
            if t and not t.startswith("岗位 J-"):
                return t
        except Exception:
            pass
    return job_code


def _env_with_persona(env_file: Path) -> dict:
    """读 .env 并校验 key。

    注（2026-09-11）：persona 不再走 `DSH_SYSTEM_PROMPT` 环境变量（旧方式已作废），
    改由 `make_harness(persona=PERSONA)` 写 profile patch 注入 —— 函数名保留，避免动调用点。
    """
    env = load_env_file(env_file)
    if "DEEPSEEK_API_KEY" not in env:
        raise SystemExit("❌ .env 里没有 DEEPSEEK_API_KEY")
    return env


def _run_harness(task: str, session_id: str, env: dict, max_tokens: int):
    """起一个 headless agent（统一走 framework_config.make_harness，模块延迟 import）。

    session id 每次运行唯一：本版 SDK 在同一 home 复用同一 id 会直接报
    `session "X" already exists`（见《DSH升级事故·衔接报告》§8.8 坑 B）。
    """
    ensure_dirs()
    run_sid = f"{session_id}-{now_ts()}"
    with make_harness(env, max_tokens=max_tokens, persona=PERSONA) as harness:
        return harness.run(task, session_id=run_sid)


# ═══════════════════════ 步骤实现 ═══════════════════════

def step_analyze(job_code: str, env_file: Path, dry_run: bool = False) -> Path | None:
    """① 岗前分析：m1_run.analyze_job（复用框架，纯文件任务）→ reports/analyze_<ts>.json"""
    import m1_run
    reports = job_dir(job_code) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = reports / f"analyze_{now_ts()}.json"
    jd = job_dir(job_code) / "jd.txt"
    print(f"\n════ {STEP_CN['analyze']} ════")
    print(f"▶ JD: {jd}")
    print(f"▶ 产物: {out.name}")
    if dry_run:
        return out
    env = _env_with_persona(env_file)
    r = m1_run.analyze_job(jd, out, f"auto-{job_code}-analyze", env)
    print("\n📣 老板汇报（岗前分析）：")
    print(r.final_response)
    return out if out.exists() else None


def _plan_task(job_code: str, ana: Path | None) -> str:
    """② 出采集计划任务文本：读 JD+analyze → 拆 2~4 关键字/条件 → 写 collect_plan JSON（不真跑）。

    采集纪律要点写死在任务里（学历离散档/AND 叠词/多城不写死单城/先确认再跑），同 m3_chat 面板口径。
    """
    jd = (job_dir(job_code) / "jd.txt").as_posix()
    reports_dir = (job_dir(job_code) / "reports").as_posix()
    ana_hint = ana.as_posix() if ana else f"{reports_dir}（暂无 analyze_*.json——还没做①岗前分析）"
    ts = now_ts()
    plan_file = f"{reports_dir}/collect_plan_{ts}.json"
    return f"""老板要你执行【② 探索采集·第一步：出计划】。请全程用文件工具完成，**这一步不真跑采集（只出计划给老板确认）**：
1. 读岗位 JD：{jd}
2. 读最新岗前分析报告：{ana_hint}
   —— 从报告的 search_keywords 里挑 2~4 个最可能命中目标候选人的关键字（参考其精确/职能/竞品/技能分组；
   若报告没有关键字，从 JD 自行拆）。
3. 按 JD 硬性条件给出猎聘筛选条件建议（配方组 group_id=value，可空，如 education=博士/博士后、
   city_current=北京、years=应届生…；注意：院校 C9/QS50 猎聘筛不掉，年限对资深岗可能无对应选项，别硬凑；
   ⚠️ **学历筛只有离散档：不限/本科/硕士/博士/博士后/大专/中专/中技/高中及以下——没有“本科及以上/大专及以上”档位**，
   JD 写“本科及以上”就选“本科”或干脆不筛学历、留待③逐人把关）。
4. 把计划写成 JSON 文件：{plan_file}
   格式：{{"keywords": [关键字...], "conds": ["group_id=value"...], "reasons": "为何这样选（2~3 句）",
          "note": "口径提醒（如年限矛盾先核实）", "created_at": "..."}}
5. 用「老板，采集计划好了」口吻回复 ≤6 句：列出关键字与条件、为什么这样选、预估代价
   （每个关键字=1 次猎聘搜索；⚠️ 猎聘搜索框是“包含全部关键词”——空格分隔的词**全部要命中**，
   关键字词内别叠同义词/多词，否则极易 0 命中；同义词宁可拆成多个关键字分路跑；
   多城市大 HC 岗别把单城市写进关键字——一城一搜浪费额度，先全国捞再人工分拣）、
   以及**请老板确认**（老板回复“按计划跑/直接跑”才会执行）。"""


def step_plan(job_code: str, env_file: Path, dry_run: bool = False) -> Path | None:
    """② 出采集计划（agent 读 JD+analyze 拆关键字/条件 → collect_plan_<ts>.json；不真跑不耗额度）。"""
    reports = job_dir(job_code) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ana = latest_file(reports, "analyze_")
    out = reports / f"collect_plan_{now_ts()}.json"
    print(f"\n════ {STEP_CN['plan']} ════")
    print(f"▶ 产物: {out.name}（只出计划，等老板确认后才真跑）")
    if dry_run:
        return out
    env = _env_with_persona(env_file)
    r = _run_harness(_plan_task(job_code, ana), f"auto-{job_code}-plan", env, max_tokens=8192)
    print("\n📣 老板汇报（采集计划）：")
    print(r.final_response)
    return out if out.exists() else None


def step_collect(job_code: str, env_file: Path, keywords: list[str] | None = None,
                 conds: list[str] | None = None, no_quota: bool = False,
                 dry_run: bool = False) -> Path | None:
    """② 采集执行：读最新 collect_plan（或 --keywords/--conds 覆盖）→ collect_liepin.collect → collected_<ts>.json"""
    import collect_liepin
    reports = job_dir(job_code) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    plan = latest_file(reports, "collect_plan_")
    plan_kw, plan_conds = [], []
    if plan:
        try:
            pd = json.loads(plan.read_text(encoding="utf-8-sig"))
            plan_kw, plan_conds = pd.get("keywords") or [], pd.get("conds") or []
        except Exception:
            pass
    kws = list(keywords) if keywords else plan_kw
    cs = list(conds) if conds else plan_conds
    if not kws:
        raise SystemExit(f"❌ 没有采集关键字：先 --step plan 出计划（{plan}），或用 --keywords 直接给")
    out = reports / f"collected_{now_ts()}.json"
    print(f"\n════ {STEP_CN['collect']} ════")
    print(f"▶ 关键字: {kws}")
    print(f"▶ 条件  : {cs}")
    print(f"▶ 产物  : {out.name}（限速：搜索 80/天、提取 500/天、轮间 8-20s）")
    if dry_run:
        return out
    collect_liepin.collect(kws, conds=cs, out=out, no_quota=no_quota)
    return out if out.exists() else None


def extract_requirements(report: dict, fallback: str = "") -> str:
    """岗位硬性条件（评估评分依据）：analyze 报告 score.details.difficulty.value（冒号后）→ jd_extracted.requirements"""
    try:
        sc = report.get("score") or {}
        val = ((sc.get("details") or {}).get("difficulty") or {}).get("value") or ""
        for sep in ("：", ":"):
            if sep in val:
                return val.split(sep, 1)[1].strip()
        if val.strip():
            return val.strip()
    except Exception:
        pass
    try:
        req = (report.get("jd_extracted") or {}).get("requirements") or ""
        if req.strip():
            return str(req)[:300]
    except Exception:
        pass
    return fallback


def merge_eval_parts(part_files: list[Path], out: Path) -> None:
    """合并分批评估 part（同 run_pipeline.merge_eval_reports）：pool_quality + candidates 按 id 排序。"""
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
    print(f"✅ 合并 {len(part_files)} 个评估分片 → {out.name}：pool_quality={'有' if pool else '无'}，candidates={len(ordered)} 条")


def step_eval(job_code: str, env_file: Path, batch: int = EVAL_BATCH,
              dry_run: bool = False) -> Path | None:
    """③ 分批评估：m2_eval_run.eval_pool 自动分批 ≤batch/批 → part → 合并 pool_report_<ts>.json；
    随后本地渲染 匹配报告_<ts>.html（数据/展示分离，0 token）。"""
    import m2_eval_run
    reports = job_dir(job_code) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    collect_out = latest_file(reports, "collected_")
    ana = latest_file(reports, "analyze_")
    jd = job_dir(job_code) / "jd.txt"
    if not collect_out:
        raise SystemExit("❌ 没有 collected_*.json：先 --step collect 采到池子")
    try:
        n = len(json.loads(collect_out.read_text(encoding="utf-8-sig")).get("rows", []))
    except Exception:
        n = 0
    if n == 0:
        raise SystemExit("❌ 采集结果为空，跳过评估")
    ana_data = {}
    if ana:
        try:
            ana_data = json.loads(ana.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    requirements = extract_requirements(ana_data, m2_eval_run.DEFAULT_REQUIREMENTS)
    ts = now_ts()
    parts: list[Path] = []
    print(f"\n════ {STEP_CN['eval']} ════")
    print(f"▶ 候选人 {n} 位，分批 ≤{batch}/批（32768 token 上限，HANDOFF 教训 5）")
    print(f"▶ 岗位硬性条件: {requirements[:80]}…")
    if dry_run:
        return reports / f"pool_report_{ts}.json"
    env = _env_with_persona(env_file)
    for batch_no, start in enumerate(range(1, n + 1, batch), start=1):
        end = min(start + batch - 1, n)
        part = reports / f"pool_part{batch_no}_{start}-{end}_{ts}.json"
        parts.append(part)
        r = m2_eval_run.eval_pool(
            jd, collect_out, part, requirements,
            f"auto-{job_code}-eval-p{batch_no}", env,
            start=start, end=end, skip_pool=batch_no > 1,
        )
        print(f"\n📣 老板汇报（第 {batch_no} 批）：")
        print(r.final_response)
    merged = reports / f"pool_report_{ts}.json"
    merge_eval_parts(parts, merged)
    # 数据/展示分离：评估完自动本地渲染匹配报告 HTML（LLM 不写 HTML）
    render_match_html(job_code, merged, collect_out)
    return merged


def render_match_html(job_code: str, pool_report: Path, collect_out: Path) -> Path | None:
    """本地渲染 匹配报告_<ts>.html（report_html.render，0 token）。"""
    from report_html import render
    reports = job_dir(job_code) / "reports"
    title = job_title_of(job_code)
    try:
        pool = json.loads(pool_report.read_text(encoding="utf-8-sig"))
        rows = json.loads(collect_out.read_text(encoding="utf-8-sig")).get("rows", [])
    except Exception as e:
        print(f"⚠️ 渲染匹配报告失败：{e}")
        return None
    html = render(title, pool, pool.get("candidates") or [], rows, group="verdict")
    out = reports / f"匹配报告_{now_ts()}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 匹配报告 HTML（本地渲染）→ {out.name}（{out.stat().st_size} 字节，"
          f"{len(pool.get('candidates') or [])} 人）")
    return out


def step_detail(job_code: str, limit: int = 15, no_quota: bool = False,
                dry_run: bool = False) -> None:
    """④ 详情深采：detail_collect.collect_all（推荐/待定入围者，每个详情 = 1 次查看量，quota 保险丝）。"""
    import detail_collect
    print(f"\n════ {STEP_CN['detail']} ════")
    if dry_run:
        print(f"[dry-run] 将深采入围者前 {limit if limit else '全部'} 人（每个 = 1 次查看量，detail 100/天 保险丝）")
        return
    detail_collect.collect_all(job_code, limit=limit or None, no_quota=no_quota)


def step_greet(job_code: str, env_file: Path, limit: int = 15, batch_size: int = 5,
               dry_run: bool = False) -> Path | None:
    """💬 打招呼数据：greet_run 分批 ≤5/批（读 detail 履历 → 概况/匹配点/先核实/话术1·2）
    → 合并 greet_<ts>.json → 本地渲染 打招呼清单_<ts>.html（到人工闸门停）。"""
    import greet_run
    reports = job_dir(job_code) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    try:
        items = greet_run.shortlist(job_code)
    except FileNotFoundError as e:
        raise SystemExit(f"❌ {e}（需先 --step eval 出 pool_report）")
    items = items[:limit] if limit else items
    if not items:
        raise SystemExit("短名单为空（pool_report 里没有 推荐/待定）")
    # 无 detail 深采的入围者（--skip-detail 场景）：greet_run 内部会跳过并报缺 detail
    no_detail = [f"#{it['candidate_id']}" for it in items
                 if greet_run.detail_file_for(reports, it["candidate_id"]) is None]
    print(f"\n════ {STEP_CN['greet']} ════")
    print(f"▶ 入围 {len(items)} 人，分批 ≤{batch_size}/批（小输出防断流，教训 15）")
    if no_detail:
        print(f"⚠️ 其中 {len(no_detail)} 人无 detail 履历（{' '.join(no_detail)}）将被跳过："
              f"如需逐人话术请 --step detail 深采后再跑 greet")
    if dry_run:
        return reports / f"greet_{now_ts()}.json"
    if len(no_detail) == len(items):
        print("⏭ 全部入围者都没有 detail 深采履历，跳过打招呼数据生成。")
        print("   先跑 --step detail（深采详情页）再跑本步骤；打招呼话术必须基于真实履历（纪律）。")
        return None
    env = _env_with_persona(env_file)
    first = True
    n_batch = 0
    for start in range(1, len(items) + 1, batch_size):
        end = min(start + batch_size - 1, len(items))
        result, out_file = greet_run.run_batch(job_code, env, start, end,
                                               f"auto-{job_code}-greet", first)
        print(f"\n📣 老板汇报（打招呼第 {start}-{end} 人）：")
        print(result.final_response)
        n_batch += 1
        first = False
    print(f"\n▶ 共跑 {n_batch} 批，合并…")
    merged = greet_run.merge_greet(job_code)
    greet_run.render_html(job_code, job_title_of(job_code))
    return merged


def step_html(job_code: str) -> Path | None:
    """HTML 渲染（纯本地，0 token）：有 greet_*.json → 打招呼清单；否则有 pool_report → 匹配报告。"""
    reports = job_dir(job_code) / "reports"
    greet = latest_final(reports, "greet_")
    if greet:
        import greet_run
        return greet_run.render_html(job_code, job_title_of(job_code))
    pool = latest_file(reports, "pool_report_")
    col = latest_file(reports, "collected_")
    if pool and col:
        return render_match_html(job_code, pool, col)
    raise SystemExit("❌ 没有可渲染的产物：需 greet_*.json（打招呼清单）或 pool_report_+collected（匹配报告）")


# ═══════════════════════ 主流程（缺啥补啥 · 幂等续跑）═══════════════════════

def plan_summary(job_code: str) -> str:
    """最新采集计划摘要（老板确认前看）。"""
    reports = job_dir(job_code) / "reports"
    plan = latest_file(reports, "collect_plan_")
    if not plan:
        return "（还没有 collect_plan_*.json）"
    try:
        pd = json.loads(plan.read_text(encoding="utf-8-sig"))
    except Exception:
        return f"（读计划失败: {plan.name}）"
    lines = [
        f"  计划文件: {plan.name}",
        f"  关键字  : {pd.get('keywords')}",
        f"  条件    : {pd.get('conds') or '（无）'}",
    ]
    if pd.get("reasons"):
        lines.append(f"  理由    : {str(pd['reasons'])[:200]}")
    if pd.get("note"):
        lines.append(f"  口径提醒: {str(pd['note'])[:200]}")
    return "\n".join(lines)


def ask_confirm(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
        return ans in ("y", "yes", "是")
    except EOFError:
        return False


def _newer(a: Path | None, b: Path | None) -> bool:
    """a 比 b 新（b 不存在视为旧）。"""
    if a is None:
        return False
    if b is None:
        return True
    return a.stat().st_mtime > b.stat().st_mtime


def _list_reports(job_code: str) -> list[Path]:
    reports = job_dir(job_code) / "reports"
    if not reports.is_dir():
        return []
    return sorted((p for p in reports.iterdir() if p.is_file()),
                  key=lambda p: p.stat().st_mtime)


def _finish_note(job_code: str) -> None:
    """本次收尾：列出最新可打开产物 + 下一步。"""
    reports = job_dir(job_code) / "reports"
    greet_html = latest_file(reports, "打招呼清单_", ".html")
    pool_html = latest_file(reports, "匹配报告_", ".html")
    print("\n" + "═" * 60)
    print(f"✅ auto_job 本次处理完成（岗位 {job_code}）。")
    print(f"\n📄 本岗最新报告（{reports}）：")
    shown = []
    if greet_html:
        print(f"   💬 打招呼清单: {greet_html.name} —— 打开后照单【点链接核一眼 → 复制话术 → 人工打招呼】（闸门）")
        shown.append(greet_html)
    if pool_html:
        print(f"   📊 匹配报告: {pool_html.name}")
        shown.append(pool_html)
    if greet_html:
        return
    for p in reversed(_list_reports(job_code)):
        if p in shown:
            continue
        if p.name.startswith(("打招呼清单_", "匹配报告_")):
            continue
        print(f"   · {p.name}（{p.stat().st_size} 字节）")


def main() -> None:
    ap = argparse.ArgumentParser(description="数字合伙人 v1.6.8 档1：新岗一条龙（JD → 打招呼清单 HTML，到人工闸门停）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--jd", type=Path, default=None, help="新岗 JD 文件（data/inbox/ 下）；同内容 JD 幂等复用已有岗")
    g.add_argument("--job-code", default=None, help="复用已有岗 data/chat/<job_code>/（续跑/补步骤）")
    ap.add_argument("--env-file", type=Path, default=None, help=".env（agent/采集步骤需要；仅 --step html 或 --dry-run 可省）")
    ap.add_argument("--title", default="", help="新岗标题（默认取 JD 文件名）")
    ap.add_argument("--step", action="append", default=None,
                    choices=ALL_STEPS, help="强制跑指定步骤（可多次，跳过“缺啥补啥”判断）")
    ap.add_argument("--yes", action="store_true", help="无人值守：自动确认采集计划与详情深采（打招呼仍停人工）")
    ap.add_argument("--skip-detail", action="store_true", help="一条龙跳过详情深采（打招呼退化为列表摘要口径）")
    ap.add_argument("--detail-limit", type=int, default=15, help="详情深采人数上限（默认 15，0=不限）")
    ap.add_argument("--greet-limit", type=int, default=15, help="打招呼入围上限（默认 15，0=不限）")
    ap.add_argument("--keywords", action="append", default=None, help="覆盖采集关键字（跳过出计划，直接采集），可多次")
    ap.add_argument("--conds", action="append", default=None, help="覆盖采集条件 group_id=value，可多次")
    ap.add_argument("--no-quota", action="store_true", help="采集/详情跳过限速（调试用）")
    ap.add_argument("--batch", type=int, default=EVAL_BATCH, help=f"评估分批人数上限（默认 {EVAL_BATCH}）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划与产物路径，不调 API/不碰浏览器")
    args = ap.parse_args()

    ensure_dirs()
    problems = check_env()
    if problems:
        print("⚠ 环境自检发现异常（继续运行可能失败）：")
        for p in problems:
            print(f"   - {p}")

    # ── 定位/建档岗位 ──────────────────────────────────────────
    if args.jd:
        jd = Path(args.jd)
        if not jd.is_absolute():
            jd = WORKSPACE / jd
        if not jd.exists():
            raise SystemExit(f"❌ JD 不存在: {jd}")
        job_code = find_existing_job(jd)
        if job_code:
            print(f"▶ 复用已有岗（同 JD 内容）: {job_code}（data/chat/{job_code}）")
        elif args.dry_run:
            job_code = f"J-AUTO-{now_ts()}"  # 占位（dry-run 不建档不写盘）
            print(f"▶ [dry-run] 将建档: {job_code}（title: {args.title or jd.stem}）")
        else:
            job_code = create_job(jd, title=args.title or jd.stem)
            print(f"▶ 已建档: {job_code}")
    else:
        job_code = args.job_code
        if not job_dir(job_code).is_dir() and not args.dry_run:
            raise SystemExit(f"❌ 岗位目录不存在: {job_dir(job_code)}")

    reports = job_dir(job_code) / "reports"
    files = _list_reports(job_code) if reports.is_dir() else []
    print(f"▶ 产物目录: {reports}（现有 {len(files)} 个文件）")
    print("─" * 60)

    if args.dry_run:
        print("▶ 模式: --dry-run（只打印计划与产物路径，不调 API / 不碰浏览器 / 不写盘）")
        one = [s for s in ONE_SHOT if not (s == "detail" and args.skip_detail)]
        print(f"▶ 一条龙计划: {' → '.join(STEP_CN[s] for s in one)}")
        print()
        for s in one:
            if s == "analyze":
                print(f"  {STEP_CN['analyze']}: 建档后跑 m1_run 岗前分析 → reports/analyze_<ts>.json（agent，纯文件）")
            elif s == "plan":
                print(f"  {STEP_CN['plan']}: agent 读 JD+analyze 拆关键字/条件 → reports/collect_plan_<ts>.json（不真跑）")
            elif s == "collect":
                kw = args.keywords or ["<计划文件里的关键字>"]
                print(f"  {STEP_CN['collect']}: 配方表采集 → reports/collected_<ts>.json；关键字={kw}"
                      + (f"，条件={args.conds}" if args.conds else ""))
            elif s == "eval":
                print(f"  {STEP_CN['eval']}: m2_eval_run 分批 ≤{args.batch}/批 → pool_part_*.json → 合并 pool_report_<ts>.json"
                      " + 本地渲染 匹配报告_<ts>.html")
            elif s == "detail":
                print(f"  {STEP_CN['detail']}: detail_collect 深采入围者（limit={args.detail_limit or '全部'}，"
                      "每个=1次查看量，detail 100/天 保险丝）→ detail_*.txt")
            elif s == "greet":
                print(f"  {STEP_CN['greet']}: greet_run 分批 ≤5/批（读 detail 履历写 概况/匹配点/先核实/话术1·2）"
                      f"→ greet_part_*.json → 合并 greet_<ts>.json")
            elif s == "html":
                print(f"  {STEP_CN['html']}: report_html 本地渲染 打招呼清单_<ts>.html（0 token）→ 到人工闸门停")
        print("\n✅ dry-run 结束：以上为将执行的动作（未调 API / 未碰浏览器 / 未写任何文件）。")
        return

    # ── --step 显式强制模式 ────────────────────────────────────
    if args.step:
        # agent 步骤（analyze/plan/eval/greet）需 .env；collect/detail/html 为本地脚本/渲染，可省
        agent_steps = [s for s in args.step if s in ("analyze", "plan", "eval", "greet")]
        if agent_steps and not args.env_file:
            raise SystemExit("❌ --env-file 必填（analyze/plan/eval/greet 需要 .env；"
                             "collect/detail/html 为本地执行可省）")
        print(f"▶ 步骤: {' → '.join(f'{STEP_CN[s]}' for s in args.step)}（显式强制）")
        for s in args.step:
            if s == "analyze":
                step_analyze(job_code, args.env_file)
            elif s == "plan":
                step_plan(job_code, args.env_file)
            elif s == "collect":
                step_collect(job_code, args.env_file, args.keywords, args.conds, args.no_quota)
            elif s == "eval":
                step_eval(job_code, args.env_file, args.batch)
            elif s == "detail":
                step_detail(job_code, args.detail_limit, args.no_quota)
            elif s == "greet":
                step_greet(job_code, args.env_file, args.greet_limit)
            elif s == "html":
                step_html(job_code)
        _finish_note(job_code)
        return

    # ── 默认一条龙（缺啥补啥 · 幂等续跑）────────────────────────
    if not args.env_file:
        raise SystemExit("❌ --env-file 必填（一条龙需要 .env）")
    print(f"▶ 一条龙: {job_code}（缺啥补啥；采集计划/详情深采为闸门）")

    # 已闭环检查：打招呼清单 HTML 已存在 → 直接交付
    if latest_file(reports, "打招呼清单_", ".html"):
        _finish_note(job_code)
        print("\n💡 该岗已到打招呼清单（人工闸门）——打开上方 HTML 照单打即可；")
        print("   如需重跑某步：python auto_job.py --job-code "
              f"{job_code} --env-file {args.env_file} --step <analyze|collect|eval|detail|greet>")
        return

    # ① 岗前分析（已有则复用）
    ana = latest_file(reports, "analyze_")
    if ana:
        print(f"⏭ {STEP_CN['analyze']}: 已有 {ana.name}，复用（强制重跑用 --step analyze）")
    else:
        step_analyze(job_code, args.env_file)

    # ② 采集计划（--keywords 覆盖时跳过出计划）
    if args.keywords:
        print(f"⏭ {STEP_CN['plan']}: 检测到 --keywords 覆盖，跳过出计划，直接按覆盖关键字采集")
    else:
        plan = latest_file(reports, "collect_plan_")
        if plan:
            print(f"⏭ {STEP_CN['plan']}: 已有 {plan.name}，复用（强制重出用 --step plan）")
        else:
            step_plan(job_code, args.env_file)

    # 闸门：是否已到"可继续采集"状态？
    col = latest_file(reports, "collected_")
    pool = latest_file(reports, "pool_report_")
    need_collect = not col or not pool or _newer(col, pool)  # 无池子 / 池子未评估过
    if need_collect:
        print("\n📋 当前采集计划：")
        print(plan_summary(job_code))
        if args.keywords:
            print(f"⚠️ 将用 --keywords 覆盖: {args.keywords}" +
                  (f"，--conds: {args.conds}" if args.conds else ""))
        if not args.yes:
            if not ask_confirm("确认按此计划采集？(回复 y 开始真实猎聘采集)"):
                _finish_note(job_code)
                print("\n⏸ 已停在采集闸门。看计划没问题后重跑同一条命令（自动复用本岗继续），"
                      "或改主意：--keywords/--conds 覆盖 或 --step plan 重新出计划。")
                return
        step_collect(job_code, args.env_file, args.keywords, args.conds, args.no_quota)
        col = latest_file(reports, "collected_")

    # ③ 评估（采集比评估新才重评）
    pool = latest_file(reports, "pool_report_")
    if not pool or _newer(col, pool):
        step_eval(job_code, args.env_file, args.batch)
        pool = latest_file(reports, "pool_report_")
    else:
        print(f"⏭ {STEP_CN['eval']}: 已有 {pool.name} 且不旧于采集，复用（强制重评用 --step eval）")

    # ④ 详情深采（可跳过；默认闸门再问一次——查看量风控点）
    if args.skip_detail:
        print(f"⏭ {STEP_CN['detail']}: --skip-detail")
    else:
        detail_any = [p for p in _list_reports(job_code) if p.name.startswith("detail_")]
        need_detail = not detail_any or _newer(pool, max(detail_any, key=lambda p: p.stat().st_mtime))
        if not need_detail:
            print(f"⏭ {STEP_CN['detail']}: 详情已深采过（{len(detail_any)} 个文件），复用（--step detail 强制重采）")
        else:
            items = None
            try:
                import greet_run
                short = greet_run.shortlist(job_code)
                n_short = len(short[:args.detail_limit] if args.detail_limit else short)
            except Exception:
                n_short = args.detail_limit
            if not args.yes:
                if not ask_confirm(f"详情深采将打开候选人详情页（每个 = 1 次查看量，本批约 {n_short} 人，"
                                   f"detail 100/天 保险丝）？(y 深采 / n 跳过)"):
                    print(f"⏭ {STEP_CN['detail']}: 未确认，跳过（打招呼将只用列表摘要；可稍后 --step detail 补）")
                else:
                    step_detail(job_code, args.detail_limit, args.no_quota)
            else:
                step_detail(job_code, args.detail_limit, args.no_quota)

    # 💬 打招呼数据 + HTML（到人工闸门停）
    greet_json = latest_final(reports, "greet_")
    if greet_json:
        print(f"⏭ {STEP_CN['greet']}: 已有 {greet_json.name}，复用（--step greet 强制重跑）")
    else:
        step_greet(job_code, args.env_file, args.greet_limit)

    _finish_note(job_code)


if __name__ == "__main__":
    main()
