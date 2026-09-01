#!/usr/bin/env python3
"""采集脚本 v2：多关键字批量采集 + tab 自动发现 + 合并去重（M2 补采 / DSH agent 自主采集共用）

用法:
  # 单关键字（自动找猎聘 tab）
  python collect_liepin.py --keyword "GPGPU" --out data/outbox/collected_gpgpu.json
  # 多关键字批量 + 合并去重 + 额外条件
  python collect_liepin.py --keyword "GPU架构师" --keyword "GPU编译器" --keyword "GPU驱动" \
      --conds city_current=北京 --out data/outbox/collected_gpgpu_v2.json
  # 指定 tab（跳过自动发现）
  python collect_liepin.py --keyword "GPGPU" --tab-id 1890029085 --out xxx.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import BROWSER_AGENT, BRIDGE_URL  # noqa: E402
sys.path.insert(0, str(BROWSER_AGENT))

from agent.core import submit_task  # noqa: E402
from agent.recipe_exec import execute_spec, COND_URL, BRIDGE  # noqa: E402

from quota import Quota  # noqa: E402


def find_liepin_tab() -> int:
    """自动发现猎聘找简历 tab（list_tabs 找 h.liepin.com）。"""
    r = submit_task(BRIDGE, "list_tabs", {}, source="collect-v2")
    if not r.get("ok"):
        raise RuntimeError(f"list_tabs 失败: {r.get('error')}")
    tabs = (r.get("result") or {}).get("tabs") or []
    for t in tabs:
        url = (t.get("url") or "").lower()
        if "h.liepin.com" in url:
            return int(t["tab_id"])
    raise RuntimeError(f"没找到猎聘 tab，现有: {[t.get('url') for t in tabs]}")


def collect(keywords: list[str], conds=None, out=None, no_quota: bool = False,
            tab_id: int | None = None, cond_url: str = COND_URL) -> list[dict]:
    """多关键字批量采集（可独立调用，供 run_pipeline 复用）。

    conds: 额外条件，list[tuple[group_id, value]] 或 list["group_id=value"] 或 dict
    out:   输出 JSON 路径（None 只打印前 5 条）
    返回:  合并去重后的 rows 列表
    """
    q = None if no_quota else Quota()
    if q:
        print(f"▶ 限速: {q.stats()}")

    tab = tab_id or find_liepin_tab()
    print(f"▶ tab: {tab}")

    cond_list: list[dict] = []
    if conds:
        if isinstance(conds, dict):
            conds = [(k, v) for k, v in conds.items()]
        for c in conds:
            if isinstance(c, (tuple, list)) and len(c) == 2:
                gid, val = c
            elif isinstance(c, str):
                gid, _, val = c.partition("=")
            else:
                continue
            cond_list.append({"group_id": gid, "value": val})

    all_rows: list[dict] = []
    seen: set[str] = set()
    for i, kw in enumerate(keywords):
        if q and not q.check("search"):
            print(f"\n⚠ 今日搜索额度已用完，跳过「{kw}」")
            continue
        if q and i > 0:
            q.delay()
        spec = [{"group_id": "keyword", "value": kw}] + cond_list
        print(f"\n▶ 关键字「{kw}」 导航+清空+执行")
        r = submit_task(BRIDGE, "navigate", {"tab_id": tab, "url": cond_url}, source="collect-v2")
        if not r.get("ok"):
            print(f"  ⚠ navigate 失败: {r.get('error')}")
            continue
        time.sleep(2.5)
        r = submit_task(BRIDGE, "click_by_text", {"tab_id": tab, "text": "清空筛选条件", "occurrence": 1}, source="collect-v2")
        time.sleep(2.0)
        res = execute_spec(spec, tab)
        if not res.get("ok"):
            print(f"  ❌ execute_spec 失败: {json.dumps(res, ensure_ascii=False)[:400]}")
            continue
        ex = submit_task(BRIDGE, "extract", {"tab_id": tab, "anchor_text": "立即沟通"}, source="collect-v2")
        rows = []
        if ex.get("ok"):
            rows = (ex.get("result") or {}).get("rows") or []
        added = 0
        for row in rows:
            sid = (row.get("fields") or {}).get("res_id_encode") or row.get("source_id")
            key = sid or (row.get("text") or "")[:50]
            if key not in seen:
                seen.add(key)
                all_rows.append(row)
                added += 1
        if q:
            q.record("search")
            q.record("extract", len(rows))
            print(f"  本轮 {len(rows)} 条，新增 {added} 条（累计 {len(all_rows)}）| {q.stats()}")

    print(f"\n✅ 合并去重后共 {len(all_rows)} 条")
    if out:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"keywords": keywords, "conds": cond_list, "count": len(all_rows), "rows": all_rows},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"✅ 已存 {out}")
    else:
        for row in all_rows[:5]:
            print("  -", (row.get("text") or "")[:130].replace("\n", " | "))
    return all_rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", action="append", required=True, help="搜索关键字，可多次")
    ap.add_argument("--tab-id", type=int, default=None, help="猎聘 tab_id（默认自动发现）")
    ap.add_argument("--out", default=None, help="合并结果输出 JSON 路径")
    ap.add_argument("--conds", action="append", default=None, help="额外条件 group_id=value，可多次")
    ap.add_argument("--no-quota", action="store_true", help="跳过限速（调试用，默认开）")
    args = ap.parse_args()
    collect(args.keyword, conds=args.conds, out=args.out, no_quota=args.no_quota, tab_id=args.tab_id)


if __name__ == "__main__":
    main()
