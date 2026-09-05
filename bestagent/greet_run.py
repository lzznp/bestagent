#!/usr/bin/env python3
"""greet_run.py — 💬 打招呼数据生成（入围者版）：小猎读 detail 完整履历 + pool_report 摘要
→ 每人输出 概况/匹配点/先核实/话术1·2 → 写 greet_part_*.json（结构化数据资产，HTML 由 report_html.py 本地渲染）

背景（2026-09-05 老板拍板）：
- 复刻老板原流程"先看详情 → 集中出打招呼报告 → 点链接人工打招呼"：详情由小猎开（detail_collect.py），
  话术基于真实履历写；人工永远把关最终动作（链接+立即沟通）。
- 数据/展示分离：本脚本只产 JSON（小输出、分批 ≤5 人/批防超限），HTML 渲染走 report_html.py（0 token）。

用法（先跑 detail_collect.py 抓详情）：
  python greet_run.py --job-code J-CHAT-xxx --env-file <path/.env> --start 1 --end 5 \
      [--batch-size 5] --session-id greet-zte-001
分批跑（如 1-5 / 6-10 / 11-15）后，用 merge_greet 合并再渲染：
  python greet_run.py --job-code J-CHAT-xxx --merge            # 合并所有 greet_part_* 为 greet_<ts>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from framework_config import (  # noqa: E402
    WORKSPACE, SESSIONS, PROMPTS, DSH_ROOT, RUNTIME_BIN, CORDIS_MINIMAL,
    REQUEST_TIMEOUT, ensure_dirs,
)
sys.path.insert(0, str(DSH_ROOT / "python" / "sdk" / "src"))  # noqa: E402
sys.path.insert(0, str(DSH_ROOT / "python" / "sdk-runtime" / "src"))  # noqa: E402
from deepseek_harness import DeepSeekHarness  # noqa: E402

CORDIS = CORDIS_MINIMAL
MAX_TOKENS_GREET = 16384
KEEP_VERDICTS = ("推荐", "待定")
CHAT = WORKSPACE / "data" / "chat"
DETAIL_URL = "https://h.liepin.com/resume/showresumedetail/?res_id_encode={rid}"

PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（猎头顾问）准备对外沟通的打招呼内容。"
    "做事原则：先思考再动手；信息不足时明确提问；输出严格按指令的 JSON 格式，不擅自改动；"
    "打招呼是人工闸门动作——你只产出内容与链接，绝不代发。"
)


def latest(reports: Path, prefix: str) -> Path | None:
    cands = [p for p in reports.glob(prefix + "*") if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL") and v.strip():
            env[k] = v.strip().strip('"').strip("'")
    return env


def shortlist(job_code: str, limit: int | None = None) -> list[dict]:
    """与 detail_collect 同口径：pool_report 推荐/待定，按分降序。"""
    d = CHAT / job_code
    reports = d / "reports"
    pool_p = latest(reports, "pool_report_")
    col_p = latest(reports, "collected_")
    if not pool_p or not col_p:
        raise FileNotFoundError(f"缺 pool_report 或 collected：{reports}")
    pool = json.loads(pool_p.read_text(encoding="utf-8-sig"))
    col = json.loads(col_p.read_text(encoding="utf-8-sig"))
    rows = col.get("rows", [])
    cand_by_id = {c.get("candidate_id"): c for c in pool.get("candidates", [])}
    out = []
    for idx, row in enumerate(rows, 1):
        c = cand_by_id.get(idx)
        if not c or c.get("verdict") not in KEEP_VERDICTS:
            continue
        rid = (row.get("fields") or {}).get("res_id_encode") or row.get("source_id") or ""
        if not rid:
            continue
        out.append({"candidate_id": idx, "score": c.get("score"), "verdict": c.get("verdict"),
                    "summary": c.get("summary") or "", "match_points": c.get("match_points") or [],
                    "concerns": c.get("concerns") or [], "res_id": rid})
    out.sort(key=lambda x: -(x.get("score") or 0))
    if limit:
        out = out[:limit]
    return out


def detail_file_for(reports: Path, candidate_id: int) -> Path | None:
    files = sorted(reports.glob(f"detail_{candidate_id:02d}_*.txt"))
    return files[-1] if files else None


def build_batch(job_code: str, start: int, end: int) -> dict:
    d = CHAT / job_code
    reports = d / "reports"
    items = shortlist(job_code)
    batch = items[start - 1:end]
    if not batch:
        raise SystemExit(f"短名单 {len(items)} 人，区间 {start}-{end} 为空")
    # 岗位要点（analyze 报告 jd_extracted/score 精简）——第一批任务里让 agent 写"岗位卖点总述"
    ana_p = latest(reports, "analyze_")
    job_hint = ""
    if ana_p:
        try:
            a = json.loads(ana_p.read_text(encoding="utf-8-sig"))
            je = a.get("jd_extracted") or {}
            job_hint = f"岗位：{je.get('job_title')}｜公司：{je.get('company')}｜地点：{je.get('city')}｜薪资：{je.get('salary')}｜建议：{(a.get('score') or {}).get('advice')}"
        except Exception:
            pass
    metas = []
    for it in batch:
        df = detail_file_for(reports, it["candidate_id"])
        flags = []
        if df:
            meta_p = df.with_name(df.stem + "_meta.json")
            if meta_p.exists():
                try:
                    flags = json.loads(meta_p.read_text(encoding="utf-8-sig")).get("flags") or []
                except Exception:
                    pass
        metas.append({"candidate_id": it["candidate_id"], "name_hint": df.name if df else "",
                      "score": it["score"], "verdict": it["verdict"],
                      "summary": it["summary"], "match_points": it["match_points"],
                      "concerns": it["concerns"], "res_id": it["res_id"],
                      "url": DETAIL_URL.format(rid=it["res_id"]),
                      "detail_file": df.as_posix() if df else None,
                      "flags": flags})
    return {"job_code": job_code, "job_hint": job_hint, "items": metas}


def build_task(job_code: str, batch: dict, out_file: Path, first: bool) -> str:
    items = batch["items"]
    files_txt = "\n".join(f"  #{it['candidate_id']}（{it['score']}分/{it['verdict']}）：履历 {it['detail_file']}" for it in items)
    job_block = ""
    if first:
        job_block = f"""
- **岗位要点（老板提供的口径）**：{batch['job_hint'] or '见岗位报告'}
- 第 1 步先写岗位「卖点总述」（30~60 字，供打招呼开场引用）：放进输出 JSON 的 "job" 字段。"""
    return f"""老板要为岗位 {job_code} 准备打招呼内容。请全程用文件工具完成（纯本地，不对外发任何消息）：

1. 对下面每位入围候选人，**用文件工具读取其 detail 完整履历文件**（那是刚抓的真实猎聘详情页全文，含每段工作职责业绩/项目/技能/期望等），再参考我给的 pool 评分摘要：
{files_txt}

2. 每位输出（严格按此 JSON 结构，写入文件）：
   {{
     "job": {{"title": "后端设计工程师（数字后端·中兴微·三地30HC）", "卖点": "…"}},   ← 仅第一批写 job，后续批留 {{}}
     "candidates": [
       {{
         "candidate_id": 1,
         "概况": "一句话（≤40字，基于真实履历）",
         "匹配点": ["≤3 条短句，必须来自 detail 履历实料（公司/项目/技能/工艺节点）"],
         "先核实": ["≤3 条：平台提示/口径问题/无法从简历确认的关键点（如外包驻场意愿、年限口径 0-3 vs 1-3、学历大专vs本科）"],
         "话术1": "岗位亮点开场（≤60字，含薪酬城市/三地可选/HC多等 JD 卖点）",
         "话术2": "匹配理由（≤60字，引用其真实履历亮点）",
         "link": "https://h.liepin.com/resume/showresumedetail/?res_id_encode=XXX"
       }}
     ]
   }}
3. 纪律：
   - 概况/匹配点/话术2 **只能写 detail 履历里有的实料**，列表摘要仅供参考；拿不准的绝不编造，一律写进"先核实"。
   - "先核实"必须包含 detail meta 里的平台提示（如有重叠/矛盾标注）与岗位口径冲突点。
   - 话术是给老板人工核对后复制的草稿，语气像真人猎头、勿夸大、勿承诺。
   - 岗位硬性口径：数字后端-模块交付（PNR/STA/PA/PV），先进/新进工艺实战硬性优先，三地 onsite（上海/深圳/南京），外包代招（科锐国际签约驻场），学历本科口径（列表大专冲突）、年限 1-3 年（列表 0-3 冲突）。
4. 把完整 JSON 写入：{out_file.as_posix()}
5. 用「老板，打招呼内容好了」口吻汇报 ≤4 句：写了几位、谁最稳谁最需先核实、输出文件路径。{job_block}"""


def run_batch(job_code: str, env: dict, start: int, end: int, session_id: str,
              first: bool, workspace: Path = WORKSPACE, session_root: Path = SESSIONS):
    ensure_dirs()
    reports = CHAT / job_code / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    batch = build_batch(job_code, start, end)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = reports / f"greet_part_{start}-{end}_{ts}.json"
    task = build_task(job_code, batch, out_file, first)
    with DeepSeekHarness(
        provider="deepseek-official", model="deepseek-v4-flash",
        max_tokens=MAX_TOKENS_GREET, cwd=str(workspace), session_root=str(session_root),
        cordis=str(CORDIS), launch_args_override=("node", str(RUNTIME_BIN)),
        env=env, request_timeout_seconds=REQUEST_TIMEOUT, shutdown_timeout_seconds=10,
    ) as harness:
        return harness.run(task, session_id=session_id), out_file


def merge_greet(job_code: str) -> Path:
    reports = CHAT / job_code / "reports"
    parts = sorted(reports.glob("greet_part_*.json"))
    if not parts:
        raise SystemExit("没有 greet_part_*.json 可合并")
    # 校正映射：part 内 candidate_id 可能是批内 1..N（小猎偶发），按 link 里的 res_id 回填真实 pool 编号；
    # link 缺失时退回按短名单顺序定位（part 覆盖连续区段）。
    items_all = shortlist(job_code)
    by_rid = {it["res_id"]: it for it in items_all}
    job_block: dict = {}
    cands: list[dict] = []
    seen: set[int] = set()
    for pi, p in enumerate(parts):
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(data.get("job"), dict) and data["job"]:
            job_block = data["job"]
        for j, c in enumerate(data.get("candidates") or []):
            rid = ""
            link = c.get("link") or ""
            if "res_id_encode=" in link:
                rid = link.rsplit("res_id_encode=", 1)[-1].split("&")[0].strip()
            real = by_rid.get(rid)
            if not real:
                pos = pi * 5 + j  # 兜底：按短名单顺序
                real = items_all[pos] if pos < len(items_all) else None
            if not real:
                continue
            cid = real["candidate_id"]
            if cid in seen:
                continue
            seen.add(cid)
            out = dict(c)
            out["candidate_id"] = cid
            cands.append(out)
    cands.sort(key=lambda x: x.get("candidate_id", 0))
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    final = reports / f"greet_{ts}.json"
    json.dump({"job": job_block, "candidates": cands}, open(final, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"✅ 合并 {len(parts)} 份 → greet {len(cands)} 人（id 校正后）→ {final}")
    return final


def render_html(job_code: str, title: str) -> Path:
    """把 greet_*.json + pool_report 合并 → 本地渲染打招呼清单 HTML（report_html.py，0 token）。"""
    from report_html import render  # 本地渲染器（数据/展示分离）
    d = CHAT / job_code
    reports = d / "reports"
    greet_p = latest(reports, "greet_")
    pool_p = latest(reports, "pool_report_")
    col_p = latest(reports, "collected_")
    if not greet_p:
        raise SystemExit("没有 greet_*.json")
    greet = json.loads(greet_p.read_text(encoding="utf-8-sig"))
    pool = json.loads(pool_p.read_text(encoding="utf-8-sig")) if pool_p else {}
    col = json.loads(col_p.read_text(encoding="utf-8-sig")) if col_p else {}
    by_id = {c.get("candidate_id"): c for c in (pool.get("candidates") or [])}
    combined = []
    for g in (greet.get("candidates") or []):
        pc = by_id.get(g.get("candidate_id"), {})
        merged = dict(pc)
        merged.update({k: v for k, v in g.items() if k in ("概况", "匹配点", "先核实", "话术1", "话术2", "link")})
        combined.append(merged)
    title = title or f"打招呼清单 · {job_code}"
    data = {"pool_quality": pool.get("pool_quality"), "candidates": combined}
    html = render(title, data, combined, (col.get("rows") or []))
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = reports / f"打招呼清单_{ts}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 打招呼清单 HTML → {out}（{out.stat().st_size} 字节，{len(combined)} 人）")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0, help="0=到短名单末尾")
    ap.add_argument("--session-id", default="greet-001")
    ap.add_argument("--merge", action="store_true", help="只合并已有 greet_part_* → greet_*.json")
    ap.add_argument("--render-html", action="store_true", help="合并 greet 并渲染 打招呼清单.html（需 --title）")
    ap.add_argument("--title", default="", help="HTML 标题")
    args = ap.parse_args()

    if args.render_html:
        render_html(args.job_code, args.title)
        return

    if args.merge:
        merge_greet(args.job_code)
        return

    if not args.env_file:
        raise SystemExit("--env-file 必填（--merge 除外）")
    env = load_env_file(args.env_file)
    if "DEEPSEEK_API_KEY" not in env:
        raise SystemExit("❌ .env 里没有 DEEPSEEK_API_KEY")
    env["DSH_SYSTEM_PROMPT"] = PERSONA

    n = len(shortlist(args.job_code))
    end = args.end or n
    first = args.start == 1
    print(f"▶ 短名单 {n} 人｜本批 {args.start}-{end}｜first={first}")
    result, out_file = run_batch(args.job_code, env, args.start, end, args.session_id, first)
    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")
    print(f"✅ 报告存在: {out_file.exists()}（{out_file.stat().st_size if out_file.exists() else 0} 字节）")


if __name__ == "__main__":
    main()
