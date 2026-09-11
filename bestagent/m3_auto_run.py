#!/usr/bin/env python3
"""M2 第三步（B 自动化）：DSH agent 自主完成「调采集脚本 → 读结果 → 评估 → 报告 → 汇报」闭环

关键：必须用 minimal-pwsh-nonpty.cordis.yml（dsh-pwsh-local，Windows 非 PTY）
且 SDK runtime 需在沙箱外运行（danger-full-access），否则 node spawn 子进程被 EPERM。

运行:
  python m3_auto_run.py --env-file <path/.env>
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 集中配置（2026-09-11 换代：pip 版 SDK + make_harness；pwsh 工具现由 sdk profile 自带）
from framework_config import WORKSPACE, ensure_dirs, make_harness

PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（一位猎头顾问）自主跑采集、"
    "做候选人评估、写报告、做汇报。做事原则：先思考再动手；信息不足时明确提问；"
    "输出务必严格按方法论手册的格式；干完活主动向老板汇报（“老板，我弄的咋样？”的口吻）。"
)

KEYWORD = "海光"  # 定向补采：目标公司（海光信息，GPGPU 目标公司名单内）
COLLECT_OUT = Path("data/outbox/collected_gpgpu_haiguang.json")
REPORT_OUT = Path("data/outbox/pool_report_gpgpu_haiguang.json")


def build_task() -> str:
    return f"""老板要你针对 GPGPU 岗位的目标公司定向补采一批候选人并评估。请把下面这条链路一次做完（这是验证你的自主能力，全程用工具，不要让我手动粘贴）：

1. 用你的命令执行工具（PowerShell）运行采集脚本，真实搜索猎聘并提取候选人（脚本会自动发现猎聘标签页、清空旧条件、按关键字搜索、提取；运行需要一点时间，请等待它完成）：
   C:/Users/84005/miniconda3/envs/lzstudy/python.exe D:/study/bestagent/bestagent/collect_liepin.py --keyword "{KEYWORD}" --out D:/study/bestagent/bestagent/{COLLECT_OUT.as_posix()}
   如果报错，把报错原文读出来并如实汇报，不要假装成功。

2. 用文件工具读取采集结果 JSON：
   D:/study/bestagent/bestagent/{COLLECT_OUT.as_posix()}

3. 读取岗位 JD 和两个方法论手册：
   - JD：D:/study/bestagent/bestagent/data/inbox/jd_1.txt
   - 池子质量评估：D:/study/bestagent/bestagent/data/prompts/pool_quality.txt
   - 单候选人匹配评估：D:/study/bestagent/bestagent/data/prompts/match_candidate.txt

4. 按方法论评估这批新采集的候选人：先池子质量（pool_quality 格式），再逐一匹配评分（match_candidate 格式；人数少就都给完整评估，人多就按紧凑格式：低分只给 score/verdict/summary）。

5. 把完整 JSON 报告写入：
   D:/study/bestagent/bestagent/{REPORT_OUT.as_posix()}
   结构：{{"pool_quality": {{...}}, "candidates": [{{"candidate_id": 1, "score": 0-100, "verdict": "...", "match_points": [...], "concerns": [...], "summary": "..."}}, ...]}}

6. 最后用「老板，我弄的咋样？」的口吻，给我一段不超过 8 句的中文汇报：采到几位候选人、池子质量如何、最值得深挖的 1-2 个人（点名+理由）、我的建议、下一步。这段汇报就是你的最终回复。"""


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
    parser.add_argument("--session-id", default="m3-auto-haiguang-001")
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    if "DEEPSEEK_API_KEY" not in env:
        print("❌ .env 里没有 DEEPSEEK_API_KEY")
        sys.exit(1)
    # persona 由 make_harness(persona=PERSONA) 注入（旧的 DSH_SYSTEM_PROMPT 方式已作废）

    workspace = WORKSPACE
    ensure_dirs()
    (workspace / REPORT_OUT).parent.mkdir(parents=True, exist_ok=True)

    print(f"▶ profile: sdk（pip 版 SDK 自带运行时；home = data/dsh_home）")
    print(f"▶ session: {args.session_id}")
    print(f"▶ keyword: {KEYWORD}")
    print("─" * 60)

    with make_harness(env, max_tokens=16384, persona=PERSONA, cwd=workspace,
                      request_timeout_seconds=1200) as harness:
        # session id 每次唯一（同 id 复用会报 session already exists，见升级报告 §8.8 坑 B）
        result = harness.run(build_task(),
                             session_id=f"{args.session_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")

    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")
    print(f"✅ session_id  : {result.session_id}")
    events = getattr(result, "events", None)
    if events:
        print(f"✅ events      : {len(events)} 个")
    for p in (COLLECT_OUT, REPORT_OUT):
        f = workspace / p
        print(f"✅ {p}: 存在={f.exists()}（{f.stat().st_size if f.exists() else 0} 字节）")


if __name__ == "__main__":
    main()
