# -*- coding: utf-8 -*-
"""m3_chat v1.7.0 纯函数自测（判断对话化骨架）：不调 API、不碰真实 data/chat。

跑法（bestagent 目录，lzstudy 解释器）：python test_m3chat_v170.py
覆盖：
1. detect_decision_intent 拍板词表用例矩阵（accept/decline/clarify/不触发）
2. detect_rejudge_intent（decline/clarify 后的改主意口子）
3. record_decision + build_decision_reply 落盘（临时 CHAT_DIR，不污染真实岗）
4. state_block 决策行注入
5. build_step1_task / build_step2_plan_task 含"请老板拍板/态度"关键句
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import m3_chat

PASS = 0
FAIL = 0


def make_tmp_dir(tag: str) -> Path:
    """自测临时目录（工作区内，跑前清旧；本机沙箱下勿用 tempfile.mkdtemp——其目录再建子目录被拒）。"""
    root = m3_chat.WORKSPACE / "data" / "_selftest_tmp" / f"v170_{tag}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name} {extra}")


def test_decision_intent() -> None:
    print("[1] detect_decision_intent")
    accept = ["做", "做吧", "可以做", "好", "可以", "咱做", "就做吧", "决定做", "值得做",
              "做吧就做", "接单", "拿下", "好，做吧", "做这单", "行，做"]
    decline = ["不做", "别做", "放弃", "不接", "算了", "不值得", "钓鱼单别做", "别做了",
               "这单不行", "坑单", "不做吧", "拒了", "先别做"]  # 先别做→decline(词表"别做")
    clarify = ["先核实", "先跟PM确认下", "先问问口径", "考虑一下", "再想想"]
    nohit = ["为什么是 16 分", "怎么评的", "这单佣金多少？", "能再讲讲难度为什么打 1 分吗",
             "别放弃这单，再挖挖", "别急着定", "按计划跑", "先出个采集计划看看", "你觉得难度打几分合适？"]
    for w in accept:
        r = m3_chat.detect_decision_intent(w)
        check(f"accept: {w}", r == "accept", f"→ {r}")
    for w in decline:
        r = m3_chat.detect_decision_intent(w)
        check(f"decline: {w}", r == "decline", f"→ {r}")
    for w in clarify:
        r = m3_chat.detect_decision_intent(w)
        check(f"clarify: {w}", r == "clarify", f"→ {r}")
    for w in nohit:
        r = m3_chat.detect_decision_intent(w)
        check(f"不触发: {w}", r == "", f"→ {r}")


def test_rejudge() -> None:
    print("[2] detect_rejudge_intent")
    for w in ["重新判断", "重新判断一下", "重新分析这单", "重跑分析", "重新看看"]:
        check(f"rejudge: {w}", m3_chat.detect_rejudge_intent(w), "→ False")
    for w in ["为什么", "做吧", "佣金核实了吗"]:
        check(f"不触发: {w}", not m3_chat.detect_rejudge_intent(w), "→ True")


def test_record_decision() -> None:
    print("[3] record_decision + build_decision_reply（临时目录）")
    tmp = make_tmp_dir("decision")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师 岗位职责：写测试 佣金10万 本科 北京")
        for dec, msg in [("accept", "做吧"), ("decline", "这单别做了，佣金太低"), ("clarify", "先核实年限口径")]:
            m3_chat.record_decision(job, dec, msg)
            st_ = m3_chat.load_state(job["job_code"])
            check(f"decision={dec} 落盘", st_.get("decision") == dec and st_.get("decision_ts"), f"→ {st_.get('decision')}")
            check(f"decision_note 截断留档", st_.get("decision_note") == msg[:80], f"→ {st_.get('decision_note')}")
            reply = m3_chat.build_decision_reply(dec, msg)
            check(f"reply 非空且含备注", len(reply) > 10 and (dec != "accept" or "备注" not in reply), "")
        # state_block 注入决策行
        m3_chat.record_decision(job, "accept", "做吧")
        sb = m3_chat.state_block(job)
        check("state_block 含决策行", "老板决策" in sb and "做这单" in sb, "")
        # 覆盖测试：clarify 后再 accept
        m3_chat.record_decision(job, "clarify", "先核实")
        st_ = m3_chat.load_state(job["job_code"])
        check("决策可被覆盖(clarify)", st_["decision"] == "clarify", "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_tasks() -> None:
    print("[4] 任务文本含判断对话化关键句")
    tmp = make_tmp_dir("task")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师 岗位职责：写测试 佣金10万 本科 北京")
        t1 = m3_chat.build_step1_task(job)
        check("①任务含「三选一态度」", "接 / 先沟通再定 / 别做" in t1, "")
        check("①任务含「请老板拍板」", "请老板拍板" in t1 and "做吧" in t1, "")
        check("①任务含判断纪律", "不诚实必罚" in t1, "")
        t2 = m3_chat.build_step2_plan_task(job)
        check("②计划含池子预期", "池子预期判断" in t2, "")
        check("②计划含请老板拍板", "请老板拍板" in t2, "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_decision_intent()
    test_rejudge()
    test_record_decision()
    test_tasks()
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)
