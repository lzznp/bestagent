#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_detail.py — 详情页能力探针（验证：打开候选人详情页能拿到什么信息，值不值得做"详情深采"）

流程（真实猎聘，只点开 1 个候选人详情 = 计 1 次查看量；不打招呼、不下载、不改动任何数据）：
  1. 找猎聘 tab（需已登录）
  2. 导航搜索页 → 清空条件 → 执行关键字（不加额外条件，保证有结果）
  3. extract 列表（anchor=立即沟通）→ 取第一行候选人的名字
  4. click_by_text 名字 → 等详情页加载
  5. 依次尝试多种锚点 extract + snapshot 落盘 → 对比「列表摘要 vs 详情页可拿信息」
  6. 产物存 data/probe/<ts>/：list_rows.json / detail_extract_*.json / snapshot.json / probe.txt

用法: python probe_detail.py [--keyword 生物分析总监] [--tab-id N]
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
from agent.recipe_exec import execute_spec, COND_URL, BRIDGE  # noqa: E402
from collect_liepin import find_liepin_tab  # noqa: E402

PROBE_DIR = WORKSPACE / "data" / "probe"
DETAIL_ANCHORS = ["立即沟通", "联系方式", "工作经历", "教育经历", "个人优势", "项目经历", "自我评价"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", default="生物分析总监")
    ap.add_argument("--tab-id", type=int, default=None)
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = PROBE_DIR / ts
    out.mkdir(parents=True, exist_ok=True)
    log = []
    def say(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        log.append(s)

    say(f"探针 {ts} | 关键字「{args.keyword}」")

    # 1) tab
    tab = args.tab_id or find_liepin_tab()
    say(f"[1] 猎聘 tab: {tab}")

    # 2) 导航 + 清空 + 执行关键字
    r = submit_task(BRIDGE, "navigate", {"tab_id": tab, "url": COND_URL}, source="probe")
    if not r.get("ok"):
        say(f"[2] navigate 失败: {r.get('error')}"); _dump(out, log); return
    time.sleep(2.5)
    submit_task(BRIDGE, "click_by_text", {"tab_id": tab, "text": "清空筛选条件", "occurrence": 1}, source="probe")
    time.sleep(2.0)
    res = execute_spec([{"group_id": "keyword", "value": args.keyword}], tab)
    if not res.get("ok"):
        say(f"[2] 关键字执行失败: {json.dumps(res, ensure_ascii=False)[:300]}"); _dump(out, log); return
    time.sleep(2.0)

    # 3) 列表 extract
    ex = submit_task(BRIDGE, "extract", {"tab_id": tab, "anchor_text": "立即沟通"}, source="probe")
    rows = []
    if ex.get("ok"):
        rows = (ex.get("result") or {}).get("rows") or []
    say(f"[3] 列表命中 {len(rows)} 行")
    (out / "list_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if not rows:
        say("[3] 无列表结果，终止（试试更宽关键字）"); _dump(out, log); return
    first = rows[0]
    name = _pick_name(first)
    say(f"[4] 点开第一个候选人: {name}（详情页）")
    rc = submit_task(BRIDGE, "click_by_text", {"tab_id": tab, "text": name, "occurrence": 1}, source="probe")
    say(f"    click: {rc.get('ok')} {str(rc.get('error') or '')[:120]}")
    time.sleep(4.0)

    # 5) 详情页多锚点 extract + snapshot
    got_any = False
    for anchor in DETAIL_ANCHORS:
        rr = submit_task(BRIDGE, "extract", {"tab_id": tab, "anchor_text": anchor}, source="probe")
        if rr.get("ok"):
            rws = (rr.get("result") or {}).get("rows") or []
            if rws:
                got_any = True
                (out / f"detail_{anchor}.json").write_text(
                    json.dumps(rws, ensure_ascii=False, indent=1), encoding="utf-8")
                total_chars = sum(len((x.get("text") or "")) for x in rws)
                say(f"    extract(anchor={anchor}): {len(rws)} 行, 文本 {total_chars} 字符 → 已存")
    snap = submit_task(BRIDGE, "snapshot", {"tab_id": tab}, source="probe")
    if snap.get("ok"):
        (out / "snapshot.json").write_text(json.dumps(snap.get("result") or {}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
        say(f"    snapshot 已存（约 {out.stat().st_size if False else ''}…）")
    else:
        say(f"    snapshot 失败: {str(snap.get('error'))[:120]}")
    if not got_any:
        say("[5] 详情页常见锚点 extract 都没命中——详情页可能不是卡片列表结构，需换方案（见 snapshot.json 人工判读）")

    # 6) 列表 vs 详情 信息量对比提示
    say("── 列表首行摘录 ──")
    say((first.get("text") or "")[:400].replace("\n", " | "))
    say(f"探针完成。产物目录: {out}")
    _dump(out, log)


def _pick_name(row: dict) -> str:
    import re
    text = row.get("text") or ""
    f = row.get("fields") or {}
    n = f.get("name") or ""
    if not n:
        m = re.search(r"([\u4e00-\u9fa5]{2,3})\*\*", text)
        n = m.group(1) + "**" if m else ""
    if not n:
        m = re.search(r"在线 ([\u4e00-\u9fa5]{2,3}) ", text)
        n = m.group(1) if m else ""
    return n or text.split(" ", 1)[0][:12]


def _dump(out: Path, log: list) -> None:
    (out / "probe.txt").write_text("\n".join(log), encoding="utf-8")
    print(f"日志已存: {out / 'probe.txt'}")


if __name__ == "__main__":
    main()
