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
import re
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
from quota import Quota  # noqa: E402

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


# 详情页折叠提示（展开再抓，否则项目经历等被折叠丢失）
TOGGLE_RE = re.compile(r"(显示其他\s*\d+\s*段[^\n]{0,24}|查看更多[^\n]{0,16}|查看全部\s*\(?\d*\)?[^\n]{0,8})")
# 猎聘平台简历自检信号（重叠/矛盾提示 → 标为"需向候选人核实项"，不直接否决）
FLAG_RE = re.compile(r"(有重叠[^\n]{0,20}|重叠[^\n]{0,12}去问他|时间[^\n]{0,8}矛盾|去问他)")


def _snap_body(tab_id: int) -> str:
    snap = submit_task(BRIDGE, "snapshot", {"tab_id": tab_id}, source="detail-collect")
    if not snap.get("ok"):
        return ""
    return (snap.get("result") or {}).get("body_preview") or ""


def _expand_all(tab_id: int, first_body: str) -> str:
    """循环点开“显示其他N段…/查看更多/查看全部”折叠项，合并去重抓全主简历。"""
    bodies = [first_body]
    clicked_toggles: set[str] = set()
    for _ in range(12):
        cur = bodies[-1]
        toggles = []
        for m in TOGGLE_RE.finditer(cur):
            t = (m.group(1) or "").strip()
            if t and t not in clicked_toggles:
                toggles.append(t)
        if not toggles:
            break
        hit = False
        for t in toggles:
            rc = submit_task(BRIDGE, "click_by_text",
                             {"tab_id": tab_id, "text": t, "occurrence": 1}, source="detail-collect")
            clicked_toggles.add(t)
            if rc.get("ok"):
                hit = True
        if not hit:
            break
        time.sleep(2.2)
        b = _snap_body(tab_id)
        if not b or b == cur:
            if not hit:
                break
            continue
        bodies.append(b)
    # 按行合并去重（保留首次出现顺序）
    seen: set[str] = set()
    lines = []
    for b in bodies:
        for ln in b.splitlines():
            s = ln.strip()
            if s and s not in seen:
                seen.add(s)
                lines.append(s)
    return "\n".join(lines)


def _find_flags(text: str) -> list[str]:
    return sorted({m.group(0).strip() for m in FLAG_RE.finditer(text)})


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
        body0 = _snap_body(new_id)
        url_actual = url
        snap0 = submit_task(BRIDGE, "snapshot", {"tab_id": new_id}, source="detail-collect")
        if snap0.get("ok"):
            res = snap0.get("result") or {}
            url_actual = res.get("url") or url
        merged = _expand_all(new_id, body0 or "")
        flags = _find_flags(merged)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        txt_p = out_dir / f"detail_{item['candidate_id']:02d}_{name_safe}_{ts}.txt"
        meta_p = out_dir / f"detail_{item['candidate_id']:02d}_{name_safe}_{ts}_meta.json"
        txt_p.write_text(merged or "(空)", encoding="utf-8")
        meta_p.write_text(json.dumps({"candidate_id": item["candidate_id"], "name": item["name"],
                                      "score": item["score"], "verdict": item["verdict"],
                                      "res_id": item["res_id"], "url": url_actual,
                                      "chars": len(merged), "flags": flags},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        return {"ok": True, "name": item["name"], "chars": len(merged),
                "flags": flags, "file": txt_p.name}
    finally:
        if new_id:
            submit_task(BRIDGE, "close_tab", {"tab_id": new_id}, source="detail-collect")
        if tab:
            submit_task(BRIDGE, "switch_tab", {"tab_id": tab}, source="detail-collect")


def collect_all(job_code: str, limit: int | None = None, dry_run: bool = False,
                no_quota: bool = False) -> list[dict]:
    """批量详情深采（可独立调用，供 auto_job 一条龙复用）。

    每开 1 个详情 = 1 次查看量（平台风控点）→ 默认走 Quota detail 账本（100/天 保险丝），
    --no-quota 跳过（调试用）。返回每条结果 [{ok, name, chars, flags, file} | {ok:False, error}].
    """
    items = shortlist(job_code, limit)
    if not items:
        print("入围清单为空（pool_report 里没有 推荐/待定 或缺 res_id）")
        return []
    print(f"入围待深采 {len(items)} 人：")
    for it in items:
        print(f"  #{it['candidate_id']} {it['name']} {it['score']}分/{it['verdict']}  res_id={it['res_id'][:12]}…")
        print(f"      URL: {DETAIL_URL.format(rid=it['res_id'])}")
    if dry_run:
        print("[dry-run] 未打开任何页面")
        return []

    q = None if no_quota else Quota()
    if q:
        print(f"▶ 查看量账本: {q.stats()}")

    out_dir = CHAT / job_code / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    tab = find_liepin_tab()
    print(f"\n用新 tab 逐个抓详情（每个 = 1 次查看量；抓完自动关 tab 回原页）…")
    results: list[dict] = []
    for it in items:
        if q and not q.check("detail"):
            print(f"⚠ 今日查看简历额度已用完（detail {q.config.get('detail_daily_limit')}/天），停止深采")
            break
        r = collect_one(tab, it, out_dir)
        if r.get("ok"):
            if q:
                q.record("detail")
                print(f"  ⏱ detail 记账后: {q.stats()}")
            flag_note = f"｜平台提示 {len(r['flags'])} 条: {'; '.join(r['flags'][:3])}" if r.get("flags") else ""
            print(f"  ✅ {r['name']}: 抓到 {r['chars']} 字符{flag_note} → {r['file']}")
        else:
            print(f"  ⚠️ {it['name']}: {r.get('error')}")
        results.append(r)
    print("完成。")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-quota", action="store_true", help="跳过查看量限额（调试用）")
    args = ap.parse_args()
    collect_all(args.job_code, limit=args.limit, dry_run=args.dry_run, no_quota=args.no_quota)


if __name__ == "__main__":
    main()
