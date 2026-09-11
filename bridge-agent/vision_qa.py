#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision_qa.py — P4-V-T2 视觉问答验证测试驱动（纯测试，不写业务代码）

测试闭环：截图 → 提问视觉模型（deepseek-v4-flash-vision-exp）→ 快照对照 →
          用户真值验证（确认动作准确性/内容正确性）→ 数据表 logs/vision_qa.jsonl

用法：
    # 一轮测试：截图 + 视觉问答 + 快照对照，记录写 logs/vision_qa.jsonl
    python vision_qa.py --tab-id 1890028341 --label "r1-条件页干净态" \
        --question "页面上有哪些搜索条件选项？布局如何？"
    # 不指定 tab-id 时自动找猎聘标签（URL 含 liepin.com，优先 getConditionItem）
    python vision_qa.py --question "..."

    # 用户真值验证：把判定写回最后一条记录
    python vision_qa.py --verdict "城市面板位置描述准确" --notes "动作能点对，内容抓对"

输出：控制台打印本轮记录 JSON；每次轮询写 logs/vision_qa.jsonl（数据表）。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from agent.core import submit_task, snapshot_to_text  # noqa: E402
from agent.vision import vision_chat, VISION_MODEL  # noqa: E402

BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8080")
QA_LOG = os.path.join(HERE, "logs", "vision_qa.jsonl")


def find_liepin_tab():
    """自动找猎聘标签：优先条件页（getConditionItem），其次任一 liepin.com 标签。"""
    r = submit_task(BRIDGE_URL, "list_tabs", {}, source="vision-qa")
    if not r["ok"]:
        return None, f"list_tabs 失败: {r.get('error')}"
    tabs = (r.get("result") or {}).get("tabs") or []
    cond = [t for t in tabs if "getConditionItem" in (t.get("url") or "")]
    if cond:
        return cond[0], None
    liepin = [t for t in tabs if "liepin.com" in (t.get("url") or "")]
    if liepin:
        return liepin[0], None
    return None, "未找到猎聘标签页（URL 含 liepin.com）。请先打开猎聘页面，或用 --tab-id 指定。"


def load_records():
    if not os.path.exists(QA_LOG):
        return []
    recs = []
    with open(QA_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
    return recs


def append_record(rec):
    os.makedirs(os.path.dirname(QA_LOG), exist_ok=True)
    with open(QA_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def update_verdict(label, verdict, notes):
    """把用户真值验证写回指定 label 的记录（label 缺省=最后一条）。"""
    recs = load_records()
    if not recs:
        print("⚠️ logs/vision_qa.jsonl 还没有记录，先跑一轮再验证")
        return None
    target = None
    if label:
        for r in reversed(recs):
            if r.get("label") == label:
                target = r
                break
        if target is None:
            print(f"⚠️ 没有 label={label} 的记录；现有 label: {[r.get('label') for r in recs]}")
            return None
    else:
        target = recs[-1]
    target["user_verdict"] = verdict
    if notes:
        target["user_notes"] = notes
    with open(QA_LOG, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return target


def run_round(tab_id, question, label, with_snapshot=True):
    """一轮：截图 → 视觉问答 →（快照对照）→ 写记录 → 返回记录 dict。"""
    tab = None
    if tab_id:
        tab = {"tab_id": tab_id}
    else:
        tab, err = find_liepin_tab()
        if err:
            return {"ok": False, "error": err}

    t0 = time.time()
    # 1) 截图
    shot = submit_task(BRIDGE_URL, "screenshot", {"tab_id": tab["tab_id"]}, source="vision-qa")
    if not shot["ok"]:
        return {"ok": False, "error": f"screenshot 失败: {shot.get('error')}"}
    shot_r = shot["result"] or {}
    if not shot_r.get("path"):
        return {"ok": False, "error": f"screenshot 未落盘: {shot_r}"}
    url = shot_r.get("url", "")
    # 2) 视觉问答
    try:
        answer = vision_chat(shot_r["path"], question)
    except Exception as e:
        return {"ok": False, "error": f"视觉模型调用失败: {e}"}
    # 3) 快照对照
    snap_excerpt = None
    snap_count = None
    if with_snapshot:
        snap = submit_task(BRIDGE_URL, "snapshot", {"tab_id": tab["tab_id"]}, source="vision-qa")
        if snap["ok"]:
            snap_r = snap["result"] or {}
            snap_count = len(snap_r.get("elements") or [])
            url = url or snap_r.get("url", "")
            snap_excerpt = snapshot_to_text(snap_r)[:2000]
        else:
            snap_excerpt = f"（快照失败: {snap.get('error')}）"

    rec = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "label": label or "",
        "tab_id": tab["tab_id"],
        "url": url,
        "screenshot": {"file": shot_r.get("file"), "path_rel": shot_r.get("path_rel"),
                       "bytes": shot_r.get("bytes")},
        "question": question,
        "vision_answer": answer,
        "snapshot_element_count": snap_count,
        "snapshot_excerpt": snap_excerpt,
        "user_verdict": None,   # 用户真值验证：动作是否点对/内容是否抓对
        "user_notes": None,
        "elapsed_sec": round(time.time() - t0, 1),
        "model": VISION_MODEL,
    }
    append_record(rec)
    return {"ok": True, "record": rec}


def run_som_round(tab_id, question=None, label=""):
    """P4-SOM 验证轮：som_shot（红色编号徽标截图）→ 视觉模型读编号 → 对照标注层映射。

    验证"看图选编号"可行性：视觉模型能否读对徽标编号、编号对应的元素是否与
    标注层（zSnapshot 同序的视觉顺序 elements）一致。
    """
    tab = None
    if tab_id:
        tab = {"tab_id": tab_id}
    else:
        tab, err = find_liepin_tab()
        if err:
            return {"ok": False, "error": err}

    t0 = time.time()
    shot = submit_task(BRIDGE_URL, "som_shot", {"tab_id": tab["tab_id"]}, source="vision-qa")
    if not shot["ok"]:
        return {"ok": False, "error": f"som_shot 失败: {shot.get('error')}"}
    shot_r = shot["result"] or {}
    elements = shot_r.get("elements") or []
    if not shot_r.get("path"):
        return {"ok": False, "error": f"som_shot 未落盘: {shot_r}"}
    q = (question or
         "这张截图的页面上叠加了红色编号徽标（数字）。请按编号从小到大，列出你能清楚读到的"
         "编号及其贴附的元素内容（按钮文字/选项文字/输入框提示等）。只列出确实看清的，"
         "看不清的编号不要编造。格式：编号=元素内容")
    try:
        answer = vision_chat(shot_r["path"], q)
    except Exception as e:
        return {"ok": False, "error": f"视觉模型调用失败: {e}"}

    rec = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "label": label or f"som-{datetime.now().strftime('%H%M%S')}",
        "kind": "som",
        "tab_id": tab["tab_id"],
        "url": shot_r.get("url", ""),
        "screenshot": {"file": shot_r.get("file"), "path_rel": shot_r.get("path_rel"),
                       "bytes": shot_r.get("bytes")},
        "question": q,
        "vision_answer": answer,
        "som_elements_count": len(elements),
        "som_elements_head": elements[:15],   # 标注层映射（前 15 条对照）
        "user_verdict": None,
        "elapsed_sec": round(time.time() - t0, 1),
        "model": VISION_MODEL,
    }
    append_record(rec)
    return {"ok": True, "record": rec}


def main():
    ap = argparse.ArgumentParser(description="P4-V-T2 视觉问答验证测试驱动")
    ap.add_argument("--tab-id", type=int, default=None, help="目标标签页 id（缺省自动找猎聘标签）")
    ap.add_argument("--question", default="请描述这张页面的整体布局，并列出页面上所有可见的搜索条件选项及其当前状态（如城市/年限/学历），以及可点击按钮的位置。",
                    help="对截图的提问")
    ap.add_argument("--label", default="", help="本轮标签（如 r1-条件页干净态）")
    ap.add_argument("--no-snapshot", action="store_true", help="跳过快照对照")
    ap.add_argument("--verdict", default=None, help="用户真值验证：写回记录（如 准确/部分准确/不准确）")
    ap.add_argument("--verdict-by-label", default=None,
                    help="按 label 定位记录并写回判定（缺省写最后一条；与 --verdict 配合）")
    ap.add_argument("--notes", default=None, help="用户备注（与 --verdict 一起写回）")
    ap.add_argument("--show", action="store_true", help="查看 logs/vision_qa.jsonl 全部记录")
    ap.add_argument("--som", action="store_true",
                    help="SOM 验证模式：som_shot（红色编号徽标截图）→ 视觉读编号 → 对照标注层映射")
    args = ap.parse_args()

    if args.show:
        for i, r in enumerate(load_records(), 1):
            print(f"[{i}] {r.get('ts')} {r.get('label','')} verdict={r.get('user_verdict')}")
            print(f"    url={r.get('url')}")
            print(f"    Q: {r.get('question')}")
            print(f"    A: {(r.get('vision_answer') or '')[:300]}")
            print(f"    截图: {r.get('screenshot', {}).get('path_rel')}")
            print()
        return

    if args.verdict is not None:
        last = update_verdict(args.verdict_by_label, args.verdict, args.notes)
        if last:
            print(json.dumps(last, ensure_ascii=False, indent=2))
        return

    if args.som:
        rec = run_som_round(args.tab_id, args.question, args.label)
        if not rec["ok"]:
            print(f"❌ {rec['error']}")
            sys.exit(1)
        print(json.dumps(rec["record"], ensure_ascii=False, indent=2))
        return

    rec = run_round(args.tab_id, args.question, args.label, with_snapshot=not args.no_snapshot)
    if not rec["ok"]:
        print(f"❌ {rec['error']}")
        sys.exit(1)
    print(json.dumps(rec["record"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
