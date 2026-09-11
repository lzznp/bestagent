#!/usr/bin/env python3
"""DSH Python SDK 最小验证脚本（Windows 本机, dev node 模式）

用途：证明 deepseek-harness-sdk 在本机（Windows + checkout 源码 + node carrier）
能拉起 headless agent 并完成真实任务 —— 这是"专用聪明 agent"的技术底座验证。

运行（用 lzstudy conda 环境）：
  C:\\Users\\84005\\miniconda3\\envs\\lzstudy\\python.exe sdk_verify.py --env-file <path/.env>
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows 控制台可能是 GBK：强制 UTF-8 输出，避免打印特殊字符报错
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 2026-09-11 换代：SDK = pip 装（deepseek-harness-sdk + 自带运行时 exe），不再挂 checkout 源码
from framework_config import WORKSPACE, make_harness


def load_env_file(path: Path) -> dict[str, str]:
    """从 .env 读取 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL（不打印值）。"""
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
    parser.add_argument("--env-file", type=Path, required=True, help="含 DEEPSEEK_API_KEY 的 .env 路径")
    parser.add_argument("--task", default=None, help="要 agent 执行的任务（默认：最小冒烟）")
    parser.add_argument("--session-id", default="verify-001")
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    if "DEEPSEEK_API_KEY" not in env:
        print("❌ .env 里没有 DEEPSEEK_API_KEY")
        sys.exit(1)

    task = args.task or "Please reply with a short confirmation that the SDK runtime works. Do not call tools."
    workspace = WORKSPACE

    print(f"▶ profile: sdk（pip 版 SDK 自带运行时；home = data/dsh_home）")
    print(f"▶ model  : deepseek-v4-flash")
    print(f"▶ task   : {task[:80]}{'…' if len(task) > 80 else ''}")
    session_id = f"{args.session_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"▶ session: {session_id}（每次唯一；落 home/sessions）")
    print("─" * 60)

    with make_harness(env, max_tokens=4096, cwd=workspace, request_timeout_seconds=180) as harness:
        result = harness.run(task, session_id=session_id)

    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")
    print(f"✅ session_id  : {result.session_id}")
    events = getattr(result, "events", None)
    if events:
        print(f"✅ events      : {len(events)} 个")


if __name__ == "__main__":
    main()
