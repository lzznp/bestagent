# -*- coding: utf-8 -*-
"""m3_chat v1.7.1 成长沉淀自测（纯函数，不调 API、不碰真实 data/chat）。

跑法（bestagent 目录，lzstudy 解释器）：python test_m3chat_v171.py
覆盖：
1. TEACH_WORDS 命中 → build_free_task 注入写入操作步骤 + rules.md 路径
2. 普通消息 → 不注入成长沉淀段
3. CAPABILITIES / PERSONA 含成长沉淀授权与纪律
4. rules.md 结构：②采集 节唯一（v1.7.1 顺带修复的结构 bug）
"""
import shutil
import sys
from pathlib import Path

import m3_chat

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name} {extra}")


def make_tmp_dir(tag: str) -> Path:
    root = m3_chat.WORKSPACE / "data" / "_selftest_tmp" / f"v171_{tag}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> None:
    tmp = make_tmp_dir("task")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师 岗位职责：写测试 佣金10万 北京")
        print("[1] build_free_task 教学分支注入")
        teach_msgs = ["把这套角色关系记到成长库吧",
                      "明白了就写进 rules",
                      "记住这条：读禾蛙页面先剥壳",
                      "教给你：杨顾问是我本人",
                      "把这条沉淀下来"]
        for msg in teach_msgs:
            t = m3_chat.build_free_task(job, msg)
            check(f"命中→注入写入步骤: {msg[:14]}…",
                  "【老板要你沉淀规则·操作步骤】" in t and "rules.md" in t and "不许删改" in t, "")
        plain = m3_chat.build_free_task(job, "这单你觉得值不值得做？")
        check("普通追问→不注入成长段", "【老板要你沉淀规则·操作步骤】" not in plain, "")

        print("[2] CAPABILITIES / PERSONA 授权")
        caps = m3_chat.CAPABILITIES
        check("CAPABILITIES 含成长沉淀授权", "成长沉淀·授权与纪律" in caps and "只允许【追加】" in caps, "")
        check("CAPABILITIES 含禁改手册", "publish_manual.txt" in caps and "不得改写任何方法论手册" in caps, "")
        check("PERSONA 含记成长库提示", "记到成长库" in m3_chat.PERSONA and "只追加不改删" in m3_chat.PERSONA, "")

        print("[3] rules.md 结构（②采集节唯一）")
        rules_txt = m3_chat.RULES.read_text(encoding="utf-8")
        n_collect = rules_txt.count("## ② 采集")
        check("②采集 节唯一", n_collect == 1, f"→ {n_collect} 个")
        check("①/③/④/流程 节齐全", all(s in rules_txt for s in
              ("## ① 岗位分析", "## ③ 池子评估", "## ④ 汇报", "## 流程 / 工具")), "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
