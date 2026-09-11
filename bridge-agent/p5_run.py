#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p5_run.py — P5 3方联调运行驱动

任务描述（中文）写在 UTF-8 源文件内，避免经 PowerShell 命令行被编码破坏。
用法：
    python p5_run.py --dry-run            # 只读试跑，看 LLM 决策（默认）
    python p5_run.py                      # 正式跑
    python p5_run.py --max-steps 30 --tab-id 1890028341
事件流落盘 logs/p5_runs/<ts>.json，便于 ④ 人工判定核对。
"""
import argparse
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.core import run_loop  # noqa: E402

BRIDGE = "http://127.0.0.1:8080"

# P5-1：歌尔 MCU 固件 JD → 找简历条件页搜索条件（用户拍板：双城青岛/嵌入式/985/今日活跃/年限3-5年）
TASK_P5_1 = (
    "在猎聘找简历条件页设置搜索条件并采集候选人。必须设置以下 6 个条件，缺一不可："
    "① 在'包含全部关键词'搜索框输入'嵌入式'；"
    "② 目前城市='青岛'；"
    "③ 期望城市='青岛'；"
    "④ 工作年限='3-5年'；"
    "⑤ 院校要求='985'；"
    "⑥ 活跃度='今日活跃'（下拉框，先展开再选）。"
    "每设置一个条件后快照核对是否生效（城市必须核对选中的是'青岛'）；"
    "6 个条件全部设置完成并核对无误前，禁止提取数据；"
    "全部完成后点'搜 索'按钮触发最终搜索，等候选人列表出现，"
    "验证结果与条件一致后，以'立即沟通'为锚点提取候选人列表"
    "（fields.res_id_encode 为唯一 source_id，用于去重），"
    "统计候选人总数并汇报，然后 finish。"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab-id", type=int, default=1890028341)
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true",
                    help="只读试跑：写动作被拦截，只看 LLM 决策")
    ap.add_argument("--task", default=TASK_P5_1)
    ap.add_argument("--no-sink", action="store_true", help="关闭经验沉淀")
    args = ap.parse_args()

    events = []
    ts = time.strftime("%Y%m%d_%H%M%S")
    mode = "dryrun" if args.dry_run else "real"

    def on_step(ev):
        events.append(ev)
        t = ev.get("type")
        step = ev.get("step", "")
        if t == "start":
            print(f"[agent] 任务：{ev.get('task')}")
            print(f"[agent] 模型: {ev.get('model')} | 模式: {mode}")
        elif t == "snapshot":
            print(f"\n[第{step}步] 📸 快照: {ev.get('title')} | {ev.get('url')} | 元素={ev.get('element_count')}")
        elif t == "think":
            print(f"[第{step}步] 🧠 决策: {json.dumps(ev.get('action'), ensure_ascii=False)[:400]}")
        elif t == "act":
            status = "✅" if ev.get("ok") else "❌"
            extra = ev.get("error") or ""
            r = ev.get("result")
            if isinstance(r, dict):
                extra = json.dumps(r, ensure_ascii=False)[:300]
            print(f"[第{step}步] {status} {ev.get('action')} {extra}")
        elif t == "dry_run_blocked":
            print(f"[第{step}步] 🚫 dry-run 拦截: {json.dumps(ev.get('action'), ensure_ascii=False)[:200]}")
        elif t == "finish":
            print(f"\n🎯 finish: {ev.get('summary')}")
            print(f"   steps={ev.get('steps')} data_keys={list((ev.get('data') or {}).keys())}")
        elif t in ("stuck", "error", "step_limit", "cancelled", "site_changed", "experience_hit", "experience_miss", "experience_sunk", "experience_draft", "screenshot_auto"):
            print(f"[第{step}步] ⚠️ {t}: {json.dumps(ev, ensure_ascii=False)[:400]}")

    start = time.time()
    res = run_loop(args.task, BRIDGE, max_steps=args.max_steps, on_step=on_step,
                   tab_id=args.tab_id, dry_run=args.dry_run)
    elapsed = time.time() - start

    # P4-V-T3：成功任务自动沉淀经验（真实 run 且未关 sink 才沉淀；dry-run/mock 不污染经验库）
    if res.get("ok") and not args.dry_run and not args.no_sink:
        try:
            from agent.experience import sink_after_run
            _sink = sink_after_run(events, res, tab_id=args.tab_id)
            if _sink:
                if _sink.get("written"):
                    _e = _sink.get("entry") or {}
                    print(f"[agent] 🧠 经验沉淀：v{_e.get('version')} id={_e.get('id')}（{_sink.get('reason')}）")
                else:
                    print(f"[agent] 🧠 经验起草待人工确认：{_sink.get('reason')}")
        except Exception as e:
            print(f"[agent] ⚠️ 经验沉淀异常: {e}")
    print(f"\n=== 运行结束 {mode} | 耗时 {elapsed:.0f}s | ok={res.get('ok')} steps={res.get('steps')} ===")
    print("summary:", (res.get("summary") or "")[:800])

    os.makedirs("logs/p5_runs", exist_ok=True)
    out = {"ts": ts, "mode": mode, "tab_id": args.tab_id, "max_steps": args.max_steps,
           "task": args.task, "result": res, "events": events}
    path = f"logs/p5_runs/{ts}_{mode}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("事件流已落盘:", path)
    sys.exit(0)


if __name__ == "__main__":
    main()
