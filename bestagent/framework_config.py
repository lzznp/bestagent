#!/usr/bin/env python3
"""数字合伙人框架集中配置：所有环境路径/默认参数在此一处定义。

换电脑/换环境时只需：
  1) 目录摆放正确（本项目代码目录 + 兄弟目录 .dsh-staging 闭包 + DSH 源码 checkout）；
  2) 或用环境变量覆盖：DSP_WORKSPACE / DSH_ROOT / BROWSER_AGENT_PATH / DSP_MODEL。

约定（相对本项目根，天然可移植）：
  - 项目根 = 本文件所在目录（bestagent/）
  - dev runtime 闭包 = <项目根>/.dsh-staging
  - DSH SDK 源码 = DSH_ROOT（默认 C:\\deepseek\\deepseek-harness，可用环境变量覆盖）
  - browser-agent 活体 = BROWSER_AGENT_PATH（默认 D:\\study\\lietou-agent\\browser-agent，可覆盖/复制进项目）
"""
from __future__ import annotations

import os
from pathlib import Path

# ── 项目根与数据目录（相对定位，不写死机器路径）───────────────────
WORKSPACE = Path(os.environ.get("DSP_WORKSPACE", Path(__file__).resolve().parent))
DATA = WORKSPACE / "data"
INBOX = DATA / "inbox"
OUTBOX = DATA / "outbox"
PROMPTS = DATA / "prompts"
USAGE = DATA / "usage"
SESSIONS = WORKSPACE / ".sessions"
DB_PATH = DATA / "business.db"

# ── SDK 运行环境（核心硬依赖，换电脑时核对）───────────────────────
# DSH 源码 checkout（python/sdk/src + python/sdk-runtime/src 注入 PYTHONPATH）
DSH_ROOT = Path(os.environ.get("DSH_ROOT", r"C:\deepseek\deepseek-harness"))
# dev node carrier：pnpm deploy 生成的完整闭包（相对项目根）
RUNTIME_BIN = (
    WORKSPACE
    / ".dsh-staging"
    / "node_modules/@deepseek-ai/dsh-sdk-jsonrpc-demo/lib/packaged-bin.js"
)
# 纯文件工具 cordis（分析/评估类任务，无需执行命令）
CORDIS_MINIMAL = DSH_ROOT / "examples/jsonrpc-agent/minimal.cordis.yml"
# 带 pwsh 命令工具 cordis（采集/自主闭环类任务，Windows 非 PTY）
CORDIS_PWSH = WORKSPACE / "minimal-pwsh-nonpty.cordis.yml"

# ── 浏览器采集（browser-agent 活体）────────────────────────────────
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8080")
BROWSER_AGENT = Path(
    os.environ.get("BROWSER_AGENT_PATH", r"D:\study\lietou-agent\browser-agent")
)

# ── 模型与 token（大池子评估分批 ≤72 人/批，32768 上限，见 HANDOFF 教训 5）─
MODEL = os.environ.get("DSP_MODEL", "deepseek-v4-flash")
MAX_TOKENS_ANALYZE = 4096   # 岗前分析（单 JD 输出小）
MAX_TOKENS_EVAL = 32768     # 池子评估（多人评分写报告）
MAX_TOKENS_AUTO = 16384     # agent 自主闭环
EVAL_BATCH = 72             # 评估分批人数上限
REQUEST_TIMEOUT = 1200      # SDK 请求超时（秒）


def ensure_dirs() -> None:
    for d in (INBOX, OUTBOX, PROMPTS, USAGE, SESSIONS):
        d.mkdir(parents=True, exist_ok=True)


def load_env_file(path) -> dict[str, str]:
    """从 .env 读取 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL（不打印值）。"""
    from pathlib import Path as _P
    env: dict[str, str] = {}
    for line in _P(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL") and v.strip():
            env[k] = v.strip().strip('"').strip("'")
    return env


def check_env() -> list[str]:
    """环境自检：返回缺失/异常项列表（空 = 全部就绪）。"""
    problems: list[str] = []
    if not DSH_ROOT.exists():
        problems.append(f"DSH_ROOT 不存在: {DSH_ROOT}（设环境变量 DSH_ROOT）")
    elif not (DSH_ROOT / "python" / "sdk" / "src").exists():
        problems.append(f"DSH SDK 源码缺失: {DSH_ROOT / 'python' / 'sdk' / 'src'}")
    if not RUNTIME_BIN.exists():
        problems.append(f"dev runtime 闭包缺失: {RUNTIME_BIN}（需 .dsh-staging）")
    if not CORDIS_PWSH.exists():
        problems.append(f"pwsh cordis 缺失: {CORDIS_PWSH}")
    if not BROWSER_AGENT.exists():
        problems.append(f"browser-agent 活体缺失: {BROWSER_AGENT}（设 BROWSER_AGENT_PATH）")
    return problems
