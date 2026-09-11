#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vt2_drive.py — P4-V-T2 操作驱动（临时测试基建）

中文动作参数（如 click_by_text 的 text="其他"）写在 UTF-8 源文件里，
避免经 PowerShell 命令行/Invoke-RestMethod 时被编码破坏（'其他'→'??'）。

用法：
    python vt2_drive.py <step-name>
    python vt2_drive.py list
"""
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, ".")
from agent.core import submit_task  # noqa: E402

BRIDGE = "http://127.0.0.1:8080"
TAB = 1890028341  # 猎聘条件页标签（list_tabs 现查确认）

# 命名步骤：动作 → 参数（中文在源文件内，UTF-8 安全）
STEPS = {
    # r2: 点 目前城市 行的「其他」打开城市选择弹层（occurrence=1 = 第一个匹配 = 目前城市行）
    "r2-open-city-panel": {"action": "click_by_text",
                           "params": {"tab_id": TAB, "text": "其他", "occurrence": 1}},
    # r3: 在弹层内点「杭州」（城市弹层打开后，热门城市区第一个匹配）
    "r3-pick-hangzhou": {"action": "click_by_text",
                         "params": {"tab_id": TAB, "text": "杭州", "occurrence": 1}},
    # r4: 点 工作年限 的「3-5年」
    "r4-pick-years": {"action": "click_by_text",
                      "params": {"tab_id": TAB, "text": "3-5年", "occurrence": 1}},
    # r4b: 点 教育经历 的「本科」
    "r4b-pick-education": {"action": "click_by_text",
                           "params": {"tab_id": TAB, "text": "本科", "occurrence": 1}},
    # 备用：直接点编号（用于弹层内高编号元素）
    "r3-pick-hangzhou-index": {"action": "click", "params": {"tab_id": TAB, "index": -1}},
    # 触发搜索（条件设置完成后）
    "r5-search": {"action": "click_by_text",
                  "params": {"tab_id": TAB, "text": "搜 索", "occurrence": 1}},
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        print("可用步骤:", list(STEPS))
        return
    name = sys.argv[1]
    if name not in STEPS:
        print(f"未知步骤: {name}；可用:", list(STEPS))
        sys.exit(1)
    s = STEPS[name]
    r = submit_task(BRIDGE, s["action"], s["params"], source="vt2-drive")
    ok = r.get("ok")
    print(f"[{name}] ok={ok}")
    if ok:
        print("  result:", json_dumps_short(r.get("result")))
    else:
        print("  error:", r.get("error"))
    if ok and s["action"] == "click":
        time.sleep(2.0)  # 点击后等页面稳定再截图
    sys.exit(0 if ok else 1)


def json_dumps_short(obj):
    import json
    s = json.dumps(obj, ensure_ascii=False)
    return s[:600] + ("…" if len(s) > 600 else "")


if __name__ == "__main__":
    main()
