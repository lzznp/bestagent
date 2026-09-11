#!/usr/bin/env python3
"""探针：DSH agent 的 bash 工具在 Windows 上能否执行命令（决定 B 自动化可行性）"""
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

# 2026-09-11 换代：统一走 framework_config.make_harness（pwsh 工具在 sdk profile 里自带）
from framework_config import WORKSPACE, make_harness

TASK = """请测试你的命令执行工具（pwsh/powershell）在 Windows 上的可用性，分三步做：
1. 用命令执行工具执行最简单的命令：echo hello
2. 如果成功，再执行：C:/Users/84005/miniconda3/envs/lzstudy/python.exe --version
3. 如果命令执行工具报错，尝试变体（如 cmd /c echo hello、powershell -Command "echo hello"），并明确告诉我：哪个命令成功、哪个失败、失败的具体报错是什么。
最后汇报：你的命令执行工具在 Windows 上能否执行命令？能否执行 python 脚本？"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--session-id", default="probe-bash-001")
    parser.add_argument("--cordis", type=Path, default=None,
                        help="已废弃（新版不传 cordis；保留参数兼容旧命令）")
    args = parser.parse_args()

    env = {}
    for line in args.env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL") and v.strip():
            env[k] = v.strip().strip('"').strip("'")
    if "DEEPSEEK_API_KEY" not in env:
        print("❌ no key")
        sys.exit(1)

    workspace = WORKSPACE

    print(f"▶ profile: sdk（pip 版 SDK 自带运行时；home = data/dsh_home）")
    with make_harness(env, max_tokens=4096, cwd=workspace, request_timeout_seconds=300) as harness:
        # session id 每次唯一（同 id 复用会报 session already exists，见升级报告 §8.8 坑 B）
        result = harness.run(TASK,
                             session_id=f"{args.session_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}")

    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")


if __name__ == "__main__":
    main()
