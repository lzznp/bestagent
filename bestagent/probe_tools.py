#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_tools.py — 工具面分档预飞（不改任何业务文件，只量一件事：这一档下模型看到几个工具）

为什么要它：工具面是"每轮固定租金"（25 个 = 25,907 字符 ≈ 6,481 token/轮）。
改分档属于动底座，**改错了所有动作一起坏**，所以先孤立验一次：能不能起来 + 工具数对不对。

跑法（cwd = bestagent\\，解释器 lzstudy）：
  python probe_tools.py                       # 全量（对照，25 个）
  python probe_tools.py --tool-profile bare   # 分档（预期 read/write/edit/read_image 4 个）
  python probe_tools.py --tool-profile bare --env-file <path/.env>

读法：工具清单与首轮 inputTokens 都印出来；同时把这次会话 id 印出来，
      可再用 token_ledger 从会话日志里复核（`request/header.tools` 是权威口径）。
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
    BROWSER_AGENT, TOOL_PROFILES, TOOL_PATCHES_DIR, WORKSPACE, ensure_dirs,
    load_env_file, make_harness, write_tool_patch,
)

DEFAULT_ENV = BROWSER_AGENT / ".env"
PERSONA = "你是猎头数字合伙人「小猎」。只回一个字，不要调用任何工具。"
TASK = "回一个字：好"


def main() -> None:
    ap = argparse.ArgumentParser(description="工具面分档预飞：量这一档下模型看到几个工具")
    ap.add_argument("--tool-profile", default=None,
                    help=f"分层名（{sorted(TOOL_PROFILES)}）；不传=全量对照")
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    ap.add_argument("--stub-patch-only", action="store_true",
                    help="只生成 patch 文件并打印内容，不调 API（0 花费）")
    args = ap.parse_args()

    ensure_dirs()
    if args.tool_profile:
        p = write_tool_patch(args.tool_profile)
        print(f"▶ patch 文件：{p}")
        print(p.read_text(encoding="utf-8"))
    if args.stub_patch_only:
        return

    env = load_env_file(args.env_file)
    if "DEEPSEEK_API_KEY" not in env:
        raise SystemExit(f"❌ {args.env_file} 里没有 DEEPSEEK_API_KEY")

    sid = f"probe-tools-{args.tool_profile or 'full'}-{int(datetime.now().timestamp())}"
    print(f"▶ 分档：{args.tool_profile or '（全量，不传 tool_profile）'}｜session {sid}")
    with make_harness(env, max_tokens=512, persona=PERSONA,
                      tool_profile=args.tool_profile) as harness:
        result = harness.run(TASK, session_id=sid)

    print(f"✅ 回复：{(getattr(result, 'final_response', '') or '').strip()[:80]}")

    # 权威口径：本次会话日志里的 request/header.tools（tool_ledger 同源）
    log = TOOL_PATCHES_DIR / "sessions"
    hits = sorted(log.rglob(f"{sid}/session.v3.jsonl.zstd")) if log.exists() else []
    if not hits:
        print("⚠️ 没找到本次会话日志，工具清单请用 token_ledger 复核")
        return
    print(f"▶ 会话日志：{hits[0]}")
    print("   用 `python token_ledger.py --session %s` 可量工具清单与首轮 token" % sid)


if __name__ == "__main__":
    main()
