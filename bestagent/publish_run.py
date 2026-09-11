#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_run.py — v1.6.8 📋 生成发岗文字（修复版）：字段 JSON + 本地渲染，逐格复制到猎聘发岗表单

复刻 recruitment-wails 已验证的「发岗助手」模式（数据/展示分离）：
  - LLM 只读 发岗手册 publish_manual.txt + JD（+岗前分析）→ 产 **9 字段 JSON**（小输出，不截断）
  - 本地代码：薪资换算（万+薪 → K·薪）、职位描述拼装（【岗位职责】/【任职要求】/【优先考虑】）
  - report_html.render_publish 渲染 发岗文字_<ts>.html（9 格可编辑 + 逐格复制按钮 + 一键复制全部）
  - 老板开 HTML 与猎聘发岗页并排，逐格复制粘贴即可；发布动作永远人工
  - 合规：发岗手册内置清洗规则（歧视词/广告法违禁词/内部信息/网站产品名），删了什么记 compliance_issues；
    --notes 传「本次临时要求」（优先级最高，如公司提醒海外岗用语）；要固化长期规则 → 追加进手册「公司特别提醒」区

用法（cwd = bestagent\\，解释器 lzstudy）：
  # 面板已有岗（读 data/chat/<code>/jd.txt + analyze → reports/publish_*.json + 发岗文字_*.html）
  python publish_run.py --job-code J-AUTO-xxx --env-file <path/.env>
  # 临时要求（本次生效，优先级最高）
  python publish_run.py --job-code J-AUTO-xxx --env-file <path/.env> --notes "海外岗位统一用'国际'，勿用'国外'"
  # 临时 JD（不建档，落 data/outbox）
  python publish_run.py --jd data/inbox/xxx.txt --env-file <path/.env>
  # 纯本地重渲染已有 publish_*.json（0 token，改渲染样式后重生）
  python publish_run.py --job-code J-AUTO-xxx --render-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from framework_config import (
    WORKSPACE, OUTBOX, PROMPTS, ensure_dirs, load_env_file, make_harness,
)

CHAT = WORKSPACE / "data" / "chat"
MANUAL = PROMPTS / "publish_manual.txt"
PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（猎头顾问）把岗位 JD 整理成"
    "适合发布到猎聘的合规发岗内容。做事原则：先思考再动手；输出严格按发岗手册的 JSON 契约，"
    "不擅自改动；发布动作由老板人工完成，你只产内容。"
    "【工具纪律·务必遵守】本环境 bash 工具不可用（Windows），读文件/写文件一律用文件工具"
    "（fs/str_replace_editor），**禁止调用 bash**；文件完整绝对路径会在任务里直接给出，"
    "**直接用文件工具读该路径，禁止列目录/遍历磁盘找文件**。"
)


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def latest_file(reports: Path, prefix: str, suffix: str = ".json") -> Path | None:
    if not reports.is_dir():
        return None
    cands = [p for p in reports.glob(prefix + "*" + suffix) if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


# ═══════════════════════ 本地处理（0 token）═══════════════════════

def convert_salary(salary_text: str, benefits_text: str = "") -> dict | None:
    """薪资换算：「50-120万 18薪」→ {converted: '42-100K·18薪', min_k, max_k, months}。

    规则（同 wails ConvertSalary）：匹配 X-Y万；发薪月数取 12薪/13薪/18薪 等（默认 12）。
    """
    s = (salary_text or "").strip()
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~至]\s*(\d+(?:\.\d+)?)\s*万", s)
    if not m:
        return None
    min_wan, max_wan = float(m.group(1)), float(m.group(2))
    months = 12
    mm = re.search(r"(\d{2})\s*薪", s + " " + (benefits_text or ""))
    if mm:
        months = int(mm.group(1))
    min_k = round(min_wan * 10 / months)
    max_k = round(max_wan * 10 / months)
    return {"original": s, "converted": f"{min_k}-{max_k}K·{months}薪",
            "min_k": min_k, "max_k": max_k, "months": months}


def enrich(pub: dict) -> dict:
    """本地增强：薪资换算（+job_description 由渲染器拼，这里不重复）。"""
    out = dict(pub)
    conv = convert_salary(out.get("salary_original") or "", out.get("salary_benefits") or "")
    if conv:
        out["salary_converted"] = conv
    return out


# ═══════════════════════ agent 生成（小输出字段 JSON）═══════════════════════

def build_task(jd: Path, manual: Path, analyze_hint: str, notes: str,
               out_file: Path, job_code: str = "") -> str:
    notes_block = ""
    if notes.strip():
        notes_block = f"""
2. **本次临时要求（优先级最高，严格遵守；与手册冲突以本条为准）**：{notes.strip()}"""
    ana_block = f"（可参考岗前分析要点：{analyze_hint}）" if analyze_hint else "（无）"
    return f"""老板要你生成【发岗文字】（用于发布到猎聘，老板逐格复制粘贴，发布动作由老板人工完成）。请全程用文件工具完成（**禁止调用 bash**——本环境 bash 不可用，读文件一律用文件工具按下面给的全路径直接读，禁止列目录/探测路径）：

1. 先读**发岗手册**（字段契约 + 合规规则 + 公司特别提醒，**必须严格遵守**）：
   {manual.as_posix()}{notes_block}

3. 读岗位 JD：{jd.as_posix()} {ana_block}

4. 按手册「输出 JSON 契约」整理成一份发岗字段 JSON：
   - 逐条执行手册合规清洗（删歧视词/违禁词/内部信息/网站产品名、做改写），删了什么记进 compliance_issues；
   - JD 内部口径矛盾（年限/学历/城市）按手册 §四 处理，冲突点放进汇报提醒；
   - 识别到年龄等违法敏感筛选项：删除 + 汇报提醒已用合法口径替代；
   - **只输出手册规定的 JSON 结构，不要写整篇文案/HTML/长文**。

5. 把 JSON 写入：{out_file.as_posix()}

6. 用「老板，发岗文字好了」口吻汇报 ≤5 句：实际招聘方/职位名/城市/薪资要点、合规过滤了哪些（如有）、
   需先核实的口径矛盾（如有）、输出文件路径。"""


def generate(jd: Path, out_file: Path, env: dict, session_id: str,
             notes: str = "", analyze_hint: str = "") -> dict | None:
    """agent 读 手册+JD → 产发岗字段 JSON（小输出）。返回 dict（None=失败）。"""
    manual = MANUAL
    if not manual.exists():
        raise SystemExit(f"❌ 发岗手册不存在: {manual}")
    ensure_dirs()
    task = build_task(jd, manual, analyze_hint, notes, out_file)
    env_p = dict(env)
    with make_harness(env_p, max_tokens=16384, persona=PERSONA) as harness:
        # session id 每次唯一（同 id 复用会报 session already exists，见升级报告 §8.8 坑 B）
        result = harness.run(task, session_id=f"{session_id}-{now_ts()}")
    print("\n📣 老板汇报（发岗文字）：")
    print(result.final_response)
    if not out_file.exists():
        print("⚠️ 发岗 JSON 未生成")
        return None
    return json.loads(out_file.read_text(encoding="utf-8-sig"))


# ═══════════════════════ 主流程 ═══════════════════════

def publish_for_job(job_code: str, env_file: Path | None, notes: str = "",
                    dry_run: bool = False) -> tuple[Path | None, Path | None]:
    """面板已有岗：读 data/chat/<code>/jd.txt + 最新 analyze → 产 publish JSON + 渲染发岗 HTML。"""
    d = CHAT / job_code
    jd = d / "jd.txt"
    reports = d / "reports"
    if not jd.exists():
        raise SystemExit(f"❌ 岗位 JD 不存在: {jd}")
    reports.mkdir(parents=True, exist_ok=True)
    ana = latest_file(reports, "analyze_")
    analyze_hint = ""
    if ana:
        try:
            a = json.loads(ana.read_text(encoding="utf-8-sig"))
            je = a.get("jd_extracted") or {}
            analyze_hint = (f"岗位：{je.get('job_title')}｜公司：{je.get('company')}｜"
                            f"地点：{je.get('city')}｜薪资：{je.get('salary')}")
        except Exception:
            pass
    ts = now_ts()
    json_out = reports / f"publish_{ts}.json"
    html_out = reports / f"发岗文字_{ts}.html"
    print(f"▶ 岗位 {job_code}｜JD {jd.name}｜手册 {MANUAL.name}")
    if notes:
        print(f"▶ 临时要求: {notes}")
    if dry_run:
        print(f"[dry-run] 将产出 publish_{ts}.json + 发岗文字_{ts}.html")
        return json_out, html_out
    env = load_env_file(env_file)
    if "DEEPSEEK_API_KEY" not in env:
        raise SystemExit("❌ .env 里没有 DEEPSEEK_API_KEY")
    pub = generate(jd, json_out, env, f"publish-{job_code}-{ts}", notes, analyze_hint)
    if pub is None:
        return None, None
    render_publish_html(job_code, json_out, html_out, pub)
    return json_out, html_out


def render_publish_html(job_code: str, json_out: Path, html_out: Path | None = None,
                        pub: dict | None = None) -> Path:
    """本地渲染 发岗文字_<ts>.html（0 token；pub 未给则读 json_out）。"""
    from report_html import render_publish
    if pub is None:
        pub = json.loads(json_out.read_text(encoding="utf-8-sig"))
    pub = enrich(pub)
    title = job_code
    ana = latest_file(json_out.parent, "analyze_")
    if ana:
        try:
            je = json.loads(ana.read_text(encoding="utf-8-sig")).get("jd_extracted") or {}
            if je.get("job_title"):
                title = str(je["job_title"])[:60]
        except Exception:
            pass
    html = render_publish(title, pub)
    out = html_out or (json_out.with_name(f"发岗文字_{now_ts()}.html"))
    out.write_text(html, encoding="utf-8")
    print(f"✅ 发岗文字 HTML（本地渲染）→ {out.name}（{out.stat().st_size} 字节）")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="v1.6.8 生成发岗文字：字段 JSON + 本地渲染，逐格复制到猎聘")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--job-code", default=None, help="面板已有岗 data/chat/<code>/")
    g.add_argument("--jd", type=Path, default=None, help="临时 JD 文件（落 data/outbox，不建档）")
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--notes", default="", help="本次临时要求（优先级最高）")
    ap.add_argument("--render-only", action="store_true", help="只本地重渲染最新 publish_*.json（0 token）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.render_only:
        if not args.job_code:
            raise SystemExit("--render-only 需要 --job-code")
        reports = CHAT / args.job_code / "reports"
        latest = latest_file(reports, "publish_")
        if not latest:
            raise SystemExit(f"❌ 没有 publish_*.json: {reports}")
        render_publish_html(args.job_code, latest)
        return

    if args.job_code:
        publish_for_job(args.job_code, args.env_file, args.notes, args.dry_run)
    else:
        jd = Path(args.jd)
        if not jd.is_absolute():
            jd = WORKSPACE / jd
        if not jd.exists():
            raise SystemExit(f"❌ JD 不存在: {jd}")
        if not args.env_file and not args.dry_run:
            raise SystemExit("❌ --env-file 必填")
        OUTBOX.mkdir(parents=True, exist_ok=True)
        base = jd.stem
        json_out = OUTBOX / f"publish_{base}_{now_ts()}.json"
        html_out = OUTBOX / f"发岗文字_{base}_{now_ts()}.html"
        print(f"▶ JD {jd}（临时模式 → data/outbox）")
        if args.dry_run:
            print(f"[dry-run] 将产出 {json_out.name} + {html_out.name}")
            return
        env = load_env_file(args.env_file)
        if "DEEPSEEK_API_KEY" not in env:
            raise SystemExit("❌ .env 里没有 DEEPSEEK_API_KEY")
        pub = generate(jd, json_out, env, f"publish-{base}-{now_ts()}", args.notes)
        if pub is not None:
            render_publish_html(base, json_out, html_out, pub)


if __name__ == "__main__":
    main()
