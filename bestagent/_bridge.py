#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_bridge.py — 桥的极简客户端（**只读侦察用**，本场新建）

用途：给实施在 pwsh 里直接调桥的动作（snapshot / list_tabs / extract / screenshot），
     把结果落成 JSON 方便读。**不做任何写动作**（不点发送、不改页面内容）。

用法（cwd = bestagent）：
  python _bridge.py health
  python _bridge.py tabs
  python _bridge.py snap   [tab_id]      # 快照（全文）
  python _bridge.py shot   [tab_id]      # 截图（落桥的 logs/screenshots/）
  python _bridge.py extract <anchor> [tab_id]

⚠️ 写动作（click/type）本脚本**故意不提供**——按纪律，打招呼是人工闸门。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

B = "http://127.0.0.1:8080"


def _post(path: str, obj: dict) -> dict:
    req = urllib.request.Request(B + path, data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))


def _get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(B + path, timeout=15).read().decode("utf-8"))


def submit(action: str, params: dict | None = None, source: str = "recon", timeout: int = 90):
    """投一个动作并等它跑完，返回 result（失败抛 SystemExit）。"""
    r = _post("/api/task", {"action": action, "params": params or {}, "source": source})
    t = r.get("task") or r
    tid = t.get("id")
    if not tid:
        raise SystemExit(f"❌ 投任务失败：{json.dumps(r, ensure_ascii=False)[:300]}")
    last = {}
    for _ in range(timeout):
        time.sleep(1)
        last = (_get("/api/task/" + str(tid)).get("task") or {})
        if last.get("status") in ("done", "failed", "error"):
            break
    if last.get("status") != "done":
        raise SystemExit(f"❌ {action} 未成功：status={last.get('status')} err={last.get('error')}")
    return last.get("result")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "health":
        print(json.dumps(_get("/api/health"), ensure_ascii=False, indent=1))
    elif cmd == "tabs":
        res = submit("list_tabs")
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif cmd == "snap":
        params = {"tab_id": int(sys.argv[2])} if len(sys.argv) > 2 else {}
        res = submit("snapshot", params)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif cmd == "shot":
        params = {"tab_id": int(sys.argv[2])} if len(sys.argv) > 2 else {}
        res = submit("screenshot", params, timeout=120)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif cmd == "extract":
        if len(sys.argv) < 3:
            raise SystemExit("用法：python _bridge.py extract <anchor_text> [tab_id]")
        params = {"anchor_text": sys.argv[2]}
        if len(sys.argv) > 3:
            params["tab_id"] = int(sys.argv[3])
        res = submit("extract", params, timeout=120)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        raise SystemExit(f"未知命令：{cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
