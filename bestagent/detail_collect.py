#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detail_collect.py — ④ 详情深采（入围者版）：pool_report 推荐/待定 → collected res_id_encode
→ 直达猎聘候选人详情页抓完整履历（body_preview）→ 存 reports/detail_<candidate>_*.txt

依据探针结论：详情页内容在 snapshot.body_preview；res_id_encode 在 collected rows.fields。
用 new_tab 开详情、close_tab 关闭、switch_tab 回原 tab——不动老板现有页面。
⚠️ 每开 1 个详情 = 1 次查看量（平台风控），只对入围者跑、限量。

用法:
  python detail_collect.py --job-code J-CHAT-20260904-154300            # 默认：推荐+待定，全部
  python detail_collect.py --job-code J-CHAT-20260904-154300 --limit 2  # 只前 2（按分数降序）
  python detail_collect.py --job-code ... --dry-run                     # 只看要开谁，不开页面
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import BROWSER_AGENT, WORKSPACE  # noqa: E402
sys.path.insert(0, str(BROWSER_AGENT))

from agent.core import submit_task  # noqa: E402
from agent.recipe_exec import BRIDGE  # noqa: E402
from collect_liepin import find_liepin_tab  # noqa: E402

CHAT = WORKSPACE / "data" / "chat"
DETAIL_URL = "https://h.liepin.com/resume/showresumedetail/?res_id_encode={rid}"
KEEP_VERDICTS = ("推荐", "待定")  # 入围口径：③评估非"不推荐"


def latest(reports: Path, prefix: str) -> Path | None:
    if not reports.is_dir():
        return None
    cands = [p for p in reports.glob(prefix + "*") if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def shortlist(job_code: str, limit: int | None) -> list[dict]:
    """从 pool_report + collected 组出入围清单：[{candidate_id, name, score, verdict, res_id}]"""
    d = CHAT / job_code
    reports = d / "reports"
    pool_p = latest(reports, "pool_report_")
    col_p = latest(reports, "collected_")
    if not pool_p or not col_p:
        raise FileNotFoundError(f"缺 pool_report 或 collected：{reports}")
    pool = json.loads(pool_p.read_text(encoding="utf-8-sig"))
    col = json.loads(col_p.read_text(encoding="utf-8-sig"))
    rows = col.get("rows", [])
    out = []
    for c in sorted(pool.get("candidates", []), key=lambda x: -(x.get("score") or 0)):
        if c.get("verdict") not in KEEP_VERDICTS:
            continue
        idx = c.get("candidate_id")
        row = rows[idx - 1] if 1 <= idx <= len(rows) else {}
        rid = (row.get("fields") or {}).get("res_id_encode") or row.get("source_id") or ""
        if not rid:
            continue
        name = _name_of(row.get("text") or "", idx)
        out.append({"candidate_id": idx, "name": name, "score": c.get("score"),
                    "verdict": c.get("verdict"), "res_id": rid})
    if limit:
        out = out[:limit]
    return out


def _name_of(text: str, idx: int) -> str:
    import re
    m = re.search(r"([\u4e00-\u9fa5]{1,3})\*\*", text)
    return (m.group(1) + "**") if m else f"cand{idx}"


def collect_one(tab: int, item: dict, out_dir: Path) -> dict:
    url = DETAIL_URL.format(rid=item["res_id"])
    name_safe = (item["name"] or "").replace("*", "x")  # Windows 文件名禁 * : / 等
    new_id = 0
    try:
        nt = submit_task(BRIDGE, "new_tab", {"url": url}, source="detail-collect")
        if not nt.get("ok"):
            return {"ok": False, "error": f"new_tab 失败: {nt.get('error')}"}
        new_id = int((nt.get("result") or {}).get("tab_id") or nt.get("tab_id") or 0)
        time.sleep(6.0)  # 详情页加载（含附件简历整合）
        snap = submit_task(BRIDGE, "snapshot", {"tab_id": new_id}, source="detail-collect")
        body = ""
        url_actual = ""
        if snap.get("ok"):
            res = snap.get("result") or {}
            body = res.get("body_preview") or ""
            url_actual = res.get("url") or url
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        txt_p = out_dir / f"detail_{item['candidate_id']:02d}_{name_safe}_{ts}.txt"
        meta_p = out_dir / f"detail_{item['candidate_id']:02d}_{name_safe}_{ts}_meta.json"
        txt_p.write_text(body or "(空)", encoding="utf-8")
        meta_p.write_text(json.dumps({"candidate_id": item["candidate_id"], "name": item["name"],
                                      "score": item["score"], "verdict": item["verdict"],
                                      "res_id": item["res_id"], "url": url_actual,
                                      "chars": len(body)}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        return {"ok": True, "name": item["name"], "chars": len(body), "file": txt_p.name}
    finally:
        if new_id:
            submit_task(BRIDGE, "close_tab", {"tab_id": new_id}, source="detail-collect")
        if tab:
            submit_task(BRIDGE, "switch_tab", {"tab_id": tab}, source="detail-collect")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = shortlist(args.job_code, args.limit)
    if not items:
        print("入围清单为空（pool_report 里没有 推荐/待定 或缺 res_id）")
        return
    print(f"入围待深采 {len(items)} 人：")
    for it in items:
        print(f"  #{it['candidate_id']} {it['name']} {it['score']}分/{it['verdict']}  res_id={it['res_id'][:12]}…")
        print(f"      URL: {DETAIL_URL.format(rid=it['res_id'])}")
    if args.dry_run:
        print("[dry-run] 未打开任何页面")
        return

    out_dir = CHAT / args.job_code / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    tab = find_liepin_tab()
    print(f"\n用新 tab 逐个抓详情（每个 = 1 次查看量；抓完自动关 tab 回原页）…")
    for it in items:
        r = collect_one(tab, it, out_dir)
        if r.get("ok"):
            print(f"  ✅ {r['name']}: 抓到 {r['chars']} 字符 → {r['file']}")
        else:
            print(f"  ⚠️ {it['name']}: {r.get('error')}")
    print("完成。")


if __name__ == "__main__":
    main()
