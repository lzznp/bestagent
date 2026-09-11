# -*- coding: utf-8 -*-
"""P2-2 暂停/恢复逻辑单元测试（临时脚本，用 fake bridge 验证 run_loop 暂停语义）。

覆盖：
  A. 手动暂停：运行中置 paused → paused 事件 + 等待 → 清除 → resumed → 正常完成
  B. 风控自动暂停：快照命中风控特征 → risk_blocked + 自动置 paused → 人工恢复后继续完成
  C. 暂停期间紧急停止：paused 等待中置 cancel → cancelled 返回
"""
import sys, os, threading, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent.core as core

# ---- fake 桥接状态 ----
state = {"risk_first": False, "snap_calls": 0}
flag = {"paused": False, "cancel": False}
events = []


def fake_submit_task(bridge_url, action, params=None, source="agent"):
    if action == "snapshot":
        state["snap_calls"] += 1
        risk_text = "请完成安全验证，拖动滑块" if (state["risk_first"] and state["snap_calls"] == 1) else ""
        body = "候选人卡片…立即沟通\n" * 5
        return {"ok": True, "result": {
            "title": "找简历", "url": "https://example.test/list",
            "elements": [{"index": 0, "tag": "li", "name": "下一页"}],
            "body_preview": risk_text + body}}
    if action == "extract":
        return {"ok": True, "result": {"rows": [{"text": f"行{i}", "fields": {"res_id_encode": f"sid{i}"}} for i in range(3)]}}
    return {"ok": False, "error": f"unexpected action {action}"}


llm_calls = {"n": 0}


def fake_llm_chat(messages, api_key):
    llm_calls["n"] += 1
    if llm_calls["n"] >= 3:
        return '{"action":"finish","summary":"完成","data":{}}'
    return '{"action":"extract","anchor_text":"立即沟通","reason":"提取"}'


core.submit_task = fake_submit_task
core.llm_chat = fake_llm_chat


def on_step(ev):
    events.append(ev)


def run_async(task):
    return core.run_loop(task, "http://fake", max_steps=10, api_key="fake", on_step=on_step,
                         cancel_requested=lambda: flag["cancel"],
                         pause_requested=lambda: flag["paused"],
                         request_pause=lambda: flag.__setitem__("paused", True))


# ---------- A. 手动暂停 ----------
events.clear(); flag.update(paused=False, cancel=False); llm_calls["n"] = 0
t = threading.Thread(target=run_async, args=("提取任务",)); t.start()
time.sleep(1.0)
flag["paused"] = True
time.sleep(0.8)
flag["paused"] = False
t.join(timeout=15)
types = [e["type"] for e in events]
assert "paused" in types and "resumed" in types, f"A 失败: {types}"
assert types.count("paused") >= 1, f"A: 无 paused 事件 {types}"
print("A 手动暂停 ✅ 事件链:", " → ".join(types))

# ---------- B. 风控自动暂停 ----------
events.clear(); flag.update(paused=False, cancel=False); llm_calls["n"] = 0
state["risk_first"] = True; state["snap_calls"] = 0
t = threading.Thread(target=run_async, args=("提取任务",)); t.start()
time.sleep(1.5)  # 等第一次快照触发风控 → request_pause
assert flag["paused"] is True, "B: 风控未自动置 paused"
assert "risk_blocked" in [e["type"] for e in events], f"B: 无 risk_blocked {[e['type'] for e in events]}"
time.sleep(0.8)
flag["paused"] = False  # 人工处理后继续
t.join(timeout=15)
types = [e["type"] for e in events]
assert "paused" in types and "resumed" in types, f"B 失败: {types}"
print("B 风控自动暂停 ✅ 事件链:", " → ".join(types))
state["risk_first"] = False

# ---------- C. 暂停期间紧急停止 ----------
events.clear(); flag.update(paused=False, cancel=False); llm_calls["n"] = 0
t = threading.Thread(target=run_async, args=("提取任务",)); t.start()
time.sleep(1.0)
flag["paused"] = True
time.sleep(0.6)
flag["cancel"] = True  # 暂停中紧急停止
t.join(timeout=15)
types = [e["type"] for e in events]
assert "cancelled" in types, f"C 失败: {types}"
print("C 暂停中紧急停止 ✅ 事件链:", " → ".join(types))

print("\n全部通过 ✅")
