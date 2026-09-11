# -*- coding: utf-8 -*-
"""P3-T5 不可逆动作闸门单元测试——用 fake bridge 验证 run_loop 确认语义。

覆盖：
  A. 不可逆动作 + 确认机制：LLM 输出不可逆动作 → confirm_requested 事件 → 阻塞等待
     → 人工确认（confirm_pending 置 False）→ confirm_granted → 动作执行
  B. 不可逆动作 + 拒绝：confirm_pending 置 False 且 cancel_requested → cancelled 返回
  C. 不可逆动作无确认机制（confirm_requested=None）→ 拒绝执行 + 换策略（不执行动作）
"""
import sys, os, threading, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import agent.core as core

# ---- fake 桥接状态 ----
executed = []          # 记录实际执行过的动作
flag = {"confirm_pending": False, "cancel": False}
events = []


def fake_submit_task(bridge_url, action, params=None, source="agent"):
    executed.append(action)
    if action == "snapshot":
        return {"ok": True, "result": {
            "title": "页面", "url": "https://example.test/x",
            "elements": [{"index": 0, "tag": "button", "name": "发送"}],
            "body_preview": "页面内容"}}
    return {"ok": True, "result": {"done": True}}


llm_calls = {"n": 0}
mode = {"type": "confirm"}  # confirm | deny | noconfirm


def fake_llm_chat(messages, api_key):
    llm_calls["n"] += 1
    if mode["type"] == "noconfirm":
        if llm_calls["n"] == 1:
            return '{"action":"send_message","text":"hi","reason":"发送不可逆动作"}'
        return '{"action":"finish","summary":"完成","data":{}}'
    # confirm/deny：第 1 次决策输出不可逆动作，之后 finish
    if llm_calls["n"] == 1:
        return '{"action":"send_message","text":"hi","reason":"发送不可逆动作"}'
    return '{"action":"finish","summary":"完成","data":{}}'


core.submit_task = fake_submit_task
core.llm_chat = fake_llm_chat
# 测试注入：把 send_message 声明为不可逆动作（生产 IRREVERSIBLE_ACTIONS 为空=机制预留）
core.IRREVERSIBLE_ACTIONS = ("send_message", "publish", "delete")


def on_step(ev):
    events.append(ev)


def run_async(task, with_confirm=True):
    return core.run_loop(task, "http://fake", max_steps=10, api_key="fake", on_step=on_step,
                         page_delay_min=0, page_delay_max=0,
                         cancel_requested=lambda: flag["cancel"],
                         confirm_requested=(lambda: bool(flag["confirm_pending"])) if with_confirm else None)


# ---------- A. 不可逆动作 + 人工确认 → 执行 ----------
events.clear(); executed.clear(); flag.update(confirm_pending=True, cancel=False); llm_calls["n"] = 0
mode["type"] = "confirm"
t = threading.Thread(target=run_async, args=("发送任务",)); t.start()
time.sleep(1.0)
types = [e["type"] for e in events]
assert "confirm_requested" in types, f"A: 无 confirm_requested 事件: {types}"
assert "send_message" not in executed, f"A: 确认前不应执行 {executed}"
flag["confirm_pending"] = False  # 人工确认
t.join(timeout=15)
types = [e["type"] for e in events]
assert "confirm_granted" in types, f"A: 无 confirm_granted {types}"
assert "send_message" in executed, f"A: 确认后应执行 send_message: {executed}"
print(f"A 确认→执行 ✅（事件: {' → '.join(types)}；executed={executed}）")

# ---------- B. 不可逆动作 + 拒绝 → cancelled ----------
events.clear(); executed.clear(); flag.update(confirm_pending=True, cancel=False); llm_calls["n"] = 0
mode["type"] = "deny"
t = threading.Thread(target=run_async, args=("发送任务",)); t.start()
time.sleep(1.0)
flag["confirm_pending"] = False
flag["cancel"] = True  # 拒绝 = 取消
t.join(timeout=15)
types = [e["type"] for e in events]
assert "cancelled" in types, f"B: 拒绝后应 cancelled: {types}"
assert "send_message" not in executed, f"B: 拒绝后不应执行: {executed}"
print(f"B 拒绝→取消 ✅（事件: {' → '.join(types)}；executed={executed}）")

# ---------- C. 不可逆动作无确认机制 → 拒绝执行并换策略 ----------
events.clear(); executed.clear(); flag.update(confirm_pending=True, cancel=False); llm_calls["n"] = 0
mode["type"] = "noconfirm"
final = run_async("发送任务", with_confirm=False)
types = [e["type"] for e in events]
assert "confirm_denied" in types, f"C: 应拒绝并提示: {types}"
assert "send_message" not in executed, f"C: 无确认机制不应执行: {executed}"
assert final["ok"] is True, f"C: 换策略后应正常完成: {final}"
print(f"C 无确认→拒绝+换策略 ✅（事件: {' → '.join(types)}；executed={executed}）")

print("\nT5 不可逆动作闸门全部通过 ✅")
