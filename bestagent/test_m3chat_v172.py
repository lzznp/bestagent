# -*- coding: utf-8 -*-
"""m3_chat v1.7.5 歧义必问基因纪律自测（纯函数，不调 API、不碰真实 data/chat）。

跑法（bestagent 目录，lzstudy 解释器）：python test_m3chat_v172.py
覆盖（档1+档2，2026-09-09）：
1. CAPABILITIES 尾部含「歧义必问·基因纪律」与「受控追加·允许结构」两段
2. 允许结构白名单 = rules.md 按节追加 + job_profile.json 三段式（pm_notes/special_notes/events）
3. 自创文件/自造 JSON 结构/自造字段 = 明确禁止
4. 注入点：build_free_task / build_step1_task 文本均带新纪律（CAPABILITIES 内嵌）
5. 回归护栏：判断纪律「不诚实必罚」仍在；①任务「请老板拍板」仍在；拍板词表行为不变
6. 记录今日冲突现场：拍板词表对「直接往下走吧」= 不触发（落自由对话，由歧义必问纪律兜底）
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
    root = m3_chat.WORKSPACE / "data" / "_selftest_tmp" / f"v172_{tag}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_capabilities_text() -> None:
    print("[1] CAPABILITIES 含 v1.7.5 新纪律")
    cap = m3_chat.CAPABILITIES
    check("含「歧义必问·基因纪律」", "歧义必问·基因纪律" in cap, "")
    check("含「等老板明确确认后才执行」", "等老板明确确认后才执行" in cap, "")
    check("含「禁止自行解读拍板」", "自行解读拍板" in cap and "不许替老板拍板" in cap, "")
    check("含「受控追加·允许结构」", "受控追加·允许结构" in cap, "")
    check("白名单 = rules.md 按节 + job_profile 三段式",
          "rules.md" in cap and "pm_notes / special_notes / events" in cap, "")
    check("禁自创结构明文", "自创文件/自造 JSON 结构/自造字段" in cap
          and "绝不自己发明格式" in cap, "")
    check("回归：判断纪律仍在", "判断错不罚、不诚实必罚" in cap, "")


def test_task_injection() -> None:
    print("[2] 新纪律注入点（自由对话 + 步骤任务）")
    tmp = make_tmp_dir("inject")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师 岗位职责：写测试 佣金10万 本科 北京")
        ft = m3_chat.build_free_task(job, "随便聊聊这岗怎么样")
        check("自由对话任务带歧义必问", "歧义必问·基因纪律" in ft, "")
        check("自由对话任务带允许结构细则", "受控追加·允许结构" in ft, "")
        t1 = m3_chat.build_step1_task(job)
        check("①任务带歧义必问（CAPABILITIES 内嵌）", "歧义必问·基因纪律" in t1, "")
        check("回归：①任务仍请老板拍板", "请老板拍板" in t1 and "做吧" in t1, "")
        t2 = m3_chat.build_step2_plan_task(job)
        check("②任务带歧义必问", "歧义必问·基因纪律" in t2, "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_routing_unchanged() -> None:
    print("[3] 拍板路由不变（今日冲突现场留档）")
    check("「做吧」→ accept", m3_chat.detect_decision_intent("做吧") == "accept", "")
    check("「直接往下走吧」→ 不触发（落自由对话，纪律兜底）",
          m3_chat.detect_decision_intent("直接往下走吧") == "", "")
    check("追问仍不触发", m3_chat.detect_decision_intent("为什么给这个判断？") == "", "")


if __name__ == "__main__":
    test_capabilities_text()
    test_task_injection()
    test_routing_unchanged()
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)
