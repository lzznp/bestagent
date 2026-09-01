#!/usr/bin/env python3
"""采集探针：调 browser-agent 在猎聘真实搜索采集候选人（第一步验证，不经过 DSH）

用法:
  python run_collect.py --task "<自然语言任务>" [--max-steps 40] [--tab-id 1890029085] [--timeout 600]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--tab-id", type=int, default=1890029085)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    payload = {
        "task": args.task,
        "max_steps": args.max_steps,
        "tab_id": args.tab_id,
    }
    print(f"▶ 提交 run: max_steps={args.max_steps} tab_id={args.tab_id}")
    print(f"▶ task: {args.task[:80]}…")
    try:
        resp = post("/api/agent/run", payload)
    except Exception as e:
        print(f"❌ 提交失败: {e}")
        sys.exit(1)
    run_id = resp.get("run_id") or (resp.get("run") or {}).get("id")
    print(f"▶ run_id: {run_id}")

    deadline = time.time() + args.timeout
    last = None
    while time.time() < deadline:
        time.sleep(3)
        try:
            st = get(f"/api/agent/status/{run_id}")
        except Exception as e:
            print(f"⚠ 查状态失败: {e}")
            continue
        status = st.get("status") or (st.get("run") or {}).get("status")
        events = st.get("events") or []
        if events:
            last = events[-1]
        done = status in ("done", "completed", "failed", "error", "cancelled")
        print(f"  [{time.time():.0f}] status={status} events={len(events)}")
        if done:
            print("─" * 60)
            print(f"✅ 终态: {status}")
            if last:
                print("最后事件:", json.dumps(last, ensure_ascii=False)[:500])
            # 尝试汇总结果
            try:
                summary = st.get("summary") or (st.get("result") or {}).get("summary")
                if summary:
                    print("summary:", summary[:1000])
            except Exception:
                pass
            sys.exit(0)
    print("⏰ 超时未完成")
    sys.exit(2)


if __name__ == "__main__":
    main()
