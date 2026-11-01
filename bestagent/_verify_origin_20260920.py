#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_verify_origin_20260920.py — 验"桥第一道门"（Origin 白名单）是否真的生效，且**没挡住自己人**

要验四件：
  1. 不带 Origin（脚本 / Node / MCP）→ 照旧放行；
  2. 外来源（网页，如 https://evil.example）→ **403**，且**不留任务**；
  3. 白名单界面（:3080 GUI / :8501 面板）→ 放行；
  4. 扩展来源（chrome-extension://）→ 放行，并且**扩展仍能领任务、真执行、回报**（回归）。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
B = "http://127.0.0.1:8080"
OK, FAIL = [], []


def chk(name: str, cond: bool, extra: str = "") -> None:
    (OK if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [FAIL] ") + name + (f"  | {extra}" if extra and not cond else ""))


def req(path: str, method: str = "GET", origin: str | None = None, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(B + path, data=data, method=method)
    if origin:
        r.add_header("Origin", origin)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def tasks_count() -> int:
    st, txt, _ = req("/api/tasks")
    try:
        d = json.loads(txt)
        return len(d.get("tasks") or [])
    except Exception:  # noqa: BLE001
        return -1


print("=== 1. 不带 Origin（脚本/Node/MCP）===")
st, txt, hdr = req("/api/health")
chk("GET /api/health 无 Origin → 200", st == 200, f"{st} {txt[:100]}")
chk("CORS 头**不再**是 `*`（无 Origin 时干脆不回）", hdr.get("Access-Control-Allow-Origin") in (None, ""),
    str(hdr.get("Access-Control-Allow-Origin")))

print("\n=== 2. 外来源（网页）必须被挡 ===")
st, txt, hdr = req("/api/health", origin="https://evil.example")
chk("GET 外来源 → 403", st == 403, f"{st} {txt[:120]}")
st, txt, hdr = req("/api/task", method="POST", origin="https://evil.example",
                   body={"action": "list_tabs", "params": {}, "source": "evil-test"})
chk("POST /api/task 外来源 → 403", st == 403, f"{st} {txt[:120]}")
chk("被挡的请求**没有留在队列里**（不留任务）", tasks_count() == 0, f"tasks={tasks_count()}")
st, txt, hdr = req("/api/health", method="OPTIONS", origin="https://evil.example")
chk("OPTIONS 预检 外来源 → 403", st == 403, f"{st}")

print("\n=== 3. 本机白名单界面放行 ===")
for o in ("http://127.0.0.1:3080", "http://localhost:8501"):
    st, txt, hdr = req("/api/health", origin=o)
    chk(f"{o} → 200 且 CORS 回显该来源", st == 200 and hdr.get("Access-Control-Allow-Origin") == o,
        f"{st} acao={hdr.get('Access-Control-Allow-Origin')}")

print("\n=== 4. 扩展来源放行 + 扩展回归（真领任务/真执行/真回报）===")
st, txt, hdr = req("/api/health", origin="chrome-extension://abcdefghijklmnop")
chk("chrome-extension:// → 200", st == 200, f"{st}")
st, txt, _ = req("/api/task", method="POST", body={"action": "list_tabs", "params": {}, "source": "verify"})
chk("脚本投 list_tabs → 202/200 受理", st in (200, 201, 202), f"{st} {txt[:120]}")
tid = ""
try:
    tid = str((json.loads(txt).get("task") or {}).get("id") or "")
except Exception:  # noqa: BLE001
    pass
chk("拿到 task id", bool(tid), txt[:120])
if tid:
    last = {}
    for _ in range(20):
        time.sleep(1)
        _s, t2, _h = req("/api/task/" + tid)
        last = (json.loads(t2).get("task") or {})
        if last.get("status") in ("done", "failed", "error"):
            break
    chk("扩展领走并执行完（status=done）", last.get("status") == "done",
        f"status={last.get('status')} err={last.get('error')}")
    n = len(((last.get("result") or {}).get("tabs")) or [])
    chk("结果里有标签页列表（扩展真在干活）", n > 0, f"tabs={n}")

print(f"\n{'='*60}\n通过 {len(OK)}｜失败 {len(FAIL)}")
if FAIL:
    print("失败项：" + "；".join(FAIL))
    raise SystemExit(1)
