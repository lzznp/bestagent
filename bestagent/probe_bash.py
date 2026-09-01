#!/usr/bin/env python3
"""探针：DSH agent 的 bash 工具在 Windows 上能否执行命令（决定 B 自动化可行性）"""
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

TASK = """请测试你的命令执行工具（pwsh/powershell）在 Windows 上的可用性，分三步做：
1. 用命令执行工具执行最简单的命令：echo hello
2. 如果成功，再执行：C:/Users/84005/miniconda3/envs/lzstudy/python.exe --version
3. 如果命令执行工具报错，尝试变体（如 cmd /c echo hello、powershell -Command "echo hello"），并明确告诉我：哪个命令成功、哪个失败、失败的具体报错是什么。
最后汇报：你的命令执行工具在 Windows 上能否执行命令？能否执行 python 脚本？"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--session-id", default="probe-bash-001")
    parser.add_argument("--cordis", type=Path, default=CORDIS)
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

    session_root = Path(r"D:\study\bestagent\bestagent\.sessions")
    workspace = Path(r"D:\study\bestagent\bestagent")
    session_root.mkdir(parents=True, exist_ok=True)

    with DeepSeekHarness(
        provider="deepseek-official",
        model="deepseek-v4-flash",
        max_tokens=4096,
        cwd=str(workspace),
        session_root=str(session_root),
        cordis=str(args.cordis),
        launch_args_override=("node", str(RUNTIME_BIN)),
        env=env,
        request_timeout_seconds=300,
        shutdown_timeout_seconds=10,
    ) as harness:
        result = harness.run(TASK, session_id=args.session_id)

    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")


if __name__ == "__main__":
    main()
