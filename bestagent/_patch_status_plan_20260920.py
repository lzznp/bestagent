#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_status_plan_20260920.py — 态势卡读"最新 plan"的时间窗（修今天发现的真 bug）

症状（实测 2026-09-20）：plan 里把时间窗改成"周一~周日 09:00-12:00"，
  但 `status_run.py` 不给 --plan 时用**代码默认窗口**（周一~周五 09:30-12:00）→
  同一个问题两个答案：报告说"能打"、态势卡说"不能打"。

改法：不给 --plan 时，**自动读本岗 reports 里最新的 greeting_plan_*.json**。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("status_run.py")

HELPER = '''def _latest_plan(jc: str):
    """本岗最新口径计划（时间窗/阈值/名额都在 plan 里；"规则是数据"）。"""
    reps = CHAT / jc / "reports"
    if not reps.exists():
        return None
    got = sorted(reps.glob("greeting_plan_*.json"), key=lambda p: p.stat().st_mtime)
    return got[-1] if got else None


'''

OLD_LOAD = '    plan = fr.load_plan(args.plan) if args.plan else {}'
NEW_LOAD = '''    if args.plan:
        plan = fr.load_plan(args.plan)
        print(f"📄 口径来源：{args.plan}")
    elif args.job_code:
        _p = _latest_plan(args.job_code)
        plan = fr.load_plan(_p) if _p else {}
        print(f"📄 口径来源：{_p.name if _p else '（该岗还没有口径计划 → 用代码兜底）'}")'''

OLD_LOOP = "        st = status(jc, plan=plan)"
NEW_LOOP = '''        if not args.plan:
            _p = _latest_plan(jc)
            plan = fr.load_plan(_p) if _p else {}
        st = status(jc, plan=plan)'''

ANCHOR = 'def main() -> None:'


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字符）")

    # ① 补 datetime 导入
    anchor_imp = "import job_db  # noqa: E402"
    if "from datetime import datetime" not in src:
        assert src.count(anchor_imp) == 1, "❌ import 锚点命中不为 1"
        src = src.replace(anchor_imp, "from datetime import datetime  # noqa: E402\n" + anchor_imp, 1)
        print("  ✅ 1/4 补 datetime 导入")

    # ② 插入 _latest_plan 助手
    assert src.count(ANCHOR) == 1, "❌ main 锚点命中不为 1"
    src = src.replace(ANCHOR, HELPER + ANCHOR, 1)
    print("  ✅ 2/4 插入 _latest_plan 助手")

    # ③ 不给 --plan → 读本岗最新 plan
    n = src.count(OLD_LOAD)
    assert n == 1, f"❌ plan 载入处命中 {n} 次"
    src = src.replace(OLD_LOAD, NEW_LOAD, 1)
    print("  ✅ 3/4 不给 --plan 时读本岗最新 greeting_plan")

    # ④ --all 模式逐岗各读自己的 plan
    n2 = src.count(OLD_LOOP)
    assert n2 == 1, f"❌ --all 循环命中 {n2} 次"
    src = src.replace(OLD_LOOP, NEW_LOOP, 1)
    print("  ✅ 4/4 --all 模式逐岗各读自己的 plan")

    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字符）")


if __name__ == "__main__":
    sys.exit(main())
