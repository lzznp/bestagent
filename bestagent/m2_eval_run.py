#!/usr/bin/env python3
"""M2 第二步：DSH agent 接管「采集结果 → 池子评估 → 匹配报告 → 老板汇报」闭环

输入:
  - JD: data/inbox/jd_1.txt（GPGPU 软件高级架构师）
  - 采集结果: data/outbox/collected_gpgpu.json（30 条真实猎聘候选人）
  - 方法论: data/prompts/pool_quality.txt + match_candidate.txt
输出:
  - data/outbox/pool_report_gpgpu.json（池子评估 + 30 人逐一评分）
运行:
  python m2_eval_run.py --env-file <path/.env>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DSH_ROOT = Path(r"C:\deepseek\deepseek-harness")
sys.path.insert(0, str(DSH_ROOT / "python" / "sdk" / "src"))
sys.path.insert(0, str(DSH_ROOT / "python" / "sdk-runtime" / "src"))

from deepseek_harness import DeepSeekHarness  # noqa: E402

RUNTIME_BIN = (
    Path(r"D:\study\bestagent\bestagent\.dsh-staging")
    / "node_modules/@deepseek-ai/dsh-sdk-jsonrpc-demo/lib/packaged-bin.js"
)
CORDIS = DSH_ROOT / "examples/jsonrpc-agent/minimal.cordis.yml"

PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（一位猎头顾问）做候选人池评估、"
    "候选人匹配分析、写报告、做汇报。做事原则：先思考再动手；信息不足时明确提问；"
    "输出务必严格按方法论手册的格式，不擅自改动；干完活主动向老板汇报"
    "（“老板，我弄的咋样？”的口吻）。"
)

JD_PATH = Path("data/inbox/jd_1.txt")
COLLECT_PATH = Path("data/outbox/collected_gpgpu_all.json")
REPORT_PATH = Path("data/outbox/pool_report_gpgpu_all.json")


def build_task(collect: Path, report: Path, start: int, end: int, skip_pool: bool) -> str:
    pool_block = "" if skip_pool else """4. 先按 pool_quality 手册评估整个池子：池子质量（优/良/中/差）、匹配分布（high/medium/low/total，按 ≥80/60-79/<60）、主要缺口、优势、行动建议、data_valid 校验。

"""
    return f"""老板刚让我在猎聘上采了一批候选人（GPGPU 岗位相关，真实搜索结果，文件 {collect.name}），现在要把这批池子评估清楚。请把下面这条工作一次做完，全程用工具完成：

1. 读取岗位 JD：
   D:/study/bestagent/bestagent/{JD_PATH.as_posix()}

2. 读取猎聘采集结果（JSON，候选人数量以文件实际为准，每条含 text 摘要 / res_id_encode / url）：
   D:/study/bestagent/bestagent/{collect.as_posix()}

3. 读取你的两个方法论手册（严格按其 JSON 输出格式）：
   - 池子质量评估手册：D:/study/bestagent/bestagent/data/prompts/pool_quality.txt
   - 单候选人匹配评估手册：D:/study/bestagent/bestagent/data/prompts/match_candidate.txt

{pool_block}5. 再按 match_candidate 手册评估候选人：采集结果的 rows 数组按顺序编号 1..N，**只评估第 {start} 到第 {end} 位**（其余不评）。评估务必紧凑：
   - 每位候选人必须有：candidate_id（按采集顺序）、score（0-100）、verdict（推荐/待定/不推荐）、summary（一句话）
   - 只有 score≥60 或 verdict≠「不推荐」的候选人，才额外给 match_points（≤3 条短句）和 concerns（≤2 条短句）
   - 其余候选人只给 score/verdict/summary 三字段，保持报告精简
   - 岗位硬性条件：985/211 统招硕士、8 年以上 GPGPU/GPU 软件全栈经验、5 年以上架构设计经验、量产级架构主导经验、43 岁以内、北京（60-150 万）——评分贴合这些条件

6. 把完整 JSON 结果写入文件（只含本次评估的候选人{'' if skip_pool else '，以及 pool_quality'}）：
   D:/study/bestagent/bestagent/{report.as_posix()}
   结构：{{"pool_quality": {{...}}{'' if skip_pool else '（本次包含）'}, "candidates": [{{"candidate_id": 1, "score": 0-100, "verdict": "...", "match_points": [...], "concerns": [...], "summary": "..."}}, ...]}}

7. 最后用「老板，我弄的咋样？」的口吻，给我一段不超过 6 句的中文汇报：本次评估了几位、池子整体质量{'' if skip_pool else '、最值得深挖的 2-3 个人（点名+理由）'}、我的建议。这段汇报就是你的最终回复。"""


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--session-id", default="m2-eval-gpgpu-all-001")
    parser.add_argument("--collect", type=Path, default=COLLECT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--start", type=int, default=1, help="评估范围起始编号（rows 顺序 1..N）")
    parser.add_argument("--end", type=int, default=0, help="评估范围结束编号（0=全部）")
    parser.add_argument("--skip-pool", action="store_true", help="跳过池子质量评估（分批评估第二次起用）")
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    if "DEEPSEEK_API_KEY" not in env:
        print("❌ .env 里没有 DEEPSEEK_API_KEY")
        sys.exit(1)
    env["DSH_SYSTEM_PROMPT"] = PERSONA

    session_root = Path(r"D:\study\bestagent\bestagent\.sessions")
    workspace = Path(r"D:\study\bestagent\bestagent")
    (workspace / REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)

    print(f"▶ runtime: {RUNTIME_BIN.name}")
    print(f"▶ session: {args.session_id}")
    print(f"▶ jd     : {JD_PATH}")
    print(f"▶ collect: {args.collect} ({args.collect.stat().st_size} 字节)")
    print(f"▶ report : {args.report}")
    end = args.end or 10 ** 9
    print(f"▶ range  : 第 {args.start} ~ 第 {end} 位" + ("（含池子质量）" if not args.skip_pool else "（仅评估人，跳过池子质量）"))
    print("─" * 60)

    with DeepSeekHarness(
        provider="deepseek-official",
        model="deepseek-v4-flash",
        max_tokens=32768,
        cwd=str(workspace),
        session_root=str(session_root),
        cordis=str(CORDIS),
        launch_args_override=("node", str(RUNTIME_BIN)),
        env=env,
        request_timeout_seconds=1200,
        shutdown_timeout_seconds=10,
    ) as harness:
        result = harness.run(build_task(args.collect, args.report, args.start, end, args.skip_pool), session_id=args.session_id)

    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")
    print(f"✅ session_id  : {result.session_id}")
    events = getattr(result, "events", None)
    if events:
        print(f"✅ events      : {len(events)} 个")
    report = workspace / args.report
    print(f"✅ 报告存在: {report.exists()}（{report.stat().st_size if report.exists() else 0} 字节）")


if __name__ == "__main__":
    main()
