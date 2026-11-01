# -*- coding: utf-8 -*-
"""token_meter.py — 本地 token 量具（0 花费）：读 DSH 会话缓存里的 tokenUsage。

数据源（【已实测】）：data/dsh_home/storages/session_projcache/sessions/<session_id>.json
  → record.rows.tokenUsage.val.totals = {uncachedInputTokens, outputTokens, cacheReadTokens, cacheWriteTokens}
  → 合计 = 三者之和（不含 reasoning），与 省token第一刀·衔接报告 §6.1 的口径**一字不差**
    （用它反查 09-15 09:16 那次：4,885 + 10,200 + 32,768 = 47,853 ✓）。

用法（bestagent 目录）：
  python token_meter.py                     # 列出所有会话（新→旧）
  python token_meter.py analyze             # 只看含 analyze 的会话
  python token_meter.py <session_id片段>     # 看某个会话的逐轮明细
"""
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SESS = Path(__file__).resolve().parent / "data" / "dsh_home" / "storages" / "session_projcache" / "sessions"


def rows_of(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    return (d.get("record") or {}).get("rows") or {}


def usage_of(path: Path) -> dict:
    rows = rows_of(path)
    tu = (rows.get("tokenUsage") or {}).get("val") or {}
    tot = tu.get("totals") or {}
    cp = (rows.get("contextPressure") or {}).get("val") or {}
    tb = (rows.get("turnBoundary") or {}).get("val") or {}
    tim = (rows.get("titleInput") or {}).get("val") or {}
    first = (tim.get("first") or {}).get("text") or ""
    last_step = (tb.get("lastStepStartSeq") or 0)
    return {
        "ts": datetime.fromtimestamp(path.stat().st_mtime).strftime("%m-%d %H:%M:%S"),
        "uncached": tot.get("uncachedInputTokens", 0),
        "output": tot.get("outputTokens", 0),
        "cache_read": tot.get("cacheReadTokens", 0),
        "cache_write": tot.get("cacheWriteTokens", 0),
        "total": tot.get("uncachedInputTokens", 0) + tot.get("outputTokens", 0) + tot.get("cacheReadTokens", 0),
        "turns": (tb.get("lastTurn") or 0),
        "steps": (tu.get("last") or {}).get("step") or 0,
        "surface": cp.get("surfaceTokens", 0),
        "head": first.strip().splitlines()[0][:34] if first else "",
    }


def main() -> None:
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    files = sorted((p for p in SESS.glob("*.json") if flt in p.name),
                   key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"没有匹配的会话缓存（{SESS}）")
        return
    print(f"{'时间':<14}{'轮':>3}{'步':>4}{'input':>8}{'output':>8}{'cacheR':>9}{'TOTAL':>9}  {'会话/首行'}")
    for p in files:
        u = usage_of(p)
        print(f"{u['ts']:<14}{u['turns']:>3}{u['steps']:>4}{u['uncached']:>8}{u['output']:>8}"
              f"{u['cache_read']:>9}{u['total']:>9}  {p.stem[:52]}｜{u['head']}")


if __name__ == "__main__":
    main()
