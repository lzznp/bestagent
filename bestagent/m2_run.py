#!/usr/bin/env python3
"""M2a 预演：SDK agent 候选人池评估（离线，不依赖猎聘）

真实闭环模拟：中级车载测试岗（J20260401154437101390）→ 其 19 条真实候选人池
→ agent 自主读 JD + 池子 + 方法论（pool_quality / match_candidate）
→ 池子质量评估 + 逐位候选人匹配评分 → 汇总报告 → 老板汇报

运行：
  C:\\Users\\84005\\miniconda3\\envs\\lzstudy\\python.exe m2_run.py --env-file <path/.env>
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

JOB_CODE = "J20260401154437101390"
JD_PATH = Path(f"data/inbox/jd_{JOB_CODE}.txt")
POOL_PATH = Path(f"data/inbox/pool_{JOB_CODE}.txt")
REPORT_PATH = Path(f"data/outbox/pool_report_{JOB_CODE}.json")


def build_task() -> str:
    return f"""老板把一个候选人池交给我评估（这是为「中级车载测试」岗采集的真实池子）。请把下面这条工作一次做完，全程用工具完成：

1. 读取岗位 JD：
   D:/study/bestagent/bestagent/{JD_PATH.as_posix()}

2. 读取候选人池文件（每条候选人原始简历文本，用 --- 分隔，共 19 位）：
   D:/study/bestagent/bestagent/{POOL_PATH.as_posix()}

3. 读取你的两个方法论手册（严格按其 JSON 输出格式）：
   - 池子质量评估手册：D:/study/bestagent/bestagent/data/prompts/pool_quality.txt
   - 单候选人匹配评估手册：D:/study/bestagent/bestagent/data/prompts/match_candidate.txt

4. 先按 pool_quality 手册评估整个池子：给出池子质量（优/良/中/差）、匹配分布（high/medium/low/total）、主要缺口、优势、行动建议，并做 data_valid 校验（若候选人信息与岗位完全无关要如实标记）。

5. 再按 match_candidate 手册对池子里每一位候选人逐一评估：0-100 分 + 推荐/待定/不推荐 + 匹配点 + 疑虑点 + 一句话总结。

6. 把完整 JSON 结果写入文件：
   D:/study/bestagent/bestagent/{REPORT_PATH.as_posix()}
   建议结构：{{"pool_quality": {{...pool_quality手册的字段...}}, "candidates": [{{...每位候选人的match_candidate字段...}}, ...]}}

7. 最后用「老板，我弄的咋样？」的口吻，给我一段不超过 8 句的中文汇报：池子整体质量咋样、有没有值得深挖的人、我的建议、下一步。这段汇报就是你的最终回复。"""


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
    parser.add_argument("--session-id", default=f"m2-pool-{JOB_CODE}")
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
    print(f"▶ pool   : {POOL_PATH} ({POOL_PATH.stat().st_size} 字节)")
    print(f"▶ report : {REPORT_PATH}")
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
        request_timeout_seconds=900,
        shutdown_timeout_seconds=10,
    ) as harness:
        result = harness.run(build_task(), session_id=args.session_id)

    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")
    print(f"✅ session_id  : {result.session_id}")
    events = getattr(result, "events", None)
    if events:
        print(f"✅ events      : {len(events)} 个")
    report = workspace / REPORT_PATH
    print(f"✅ 报告存在: {report.exists()}（{report.stat().st_size if report.exists() else 0} 字节）")


if __name__ == "__main__":
    main()
