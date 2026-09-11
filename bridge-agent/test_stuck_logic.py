# -*- coding: utf-8 -*-
"""P3-T3 无进展检测（G3 卡死）单元测试——用 fake bridge 验证 run_loop 卡死终止语义。

覆盖：
  A. 打转场景：LLM 连续决策 snapshot，页面签名不变 → 连续 NO_PROGRESS_LIMIT 步无实质进展
     → stuck 事件 + ok=False 终止（而不是跑满 max_steps 才 step_limit）
  B. 正常场景：页面有实质变化（extract 新行/URL 变）→ 不触发 stuck，正常完成
  C. 重复动作不算进展：LLM 反复执行同一 click（页面不变）→ 也触发 stuck
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import agent.core as core

# ---- fake 桥接状态 ----
state = {"snap_count": 0, "url": "https://example.test/list", "elements": 5}
events = []


def fake_submit_task(bridge_url, action, params=None, source="agent"):
    if action == "snapshot":
        state["snap_count"] += 1
        return {"ok": True, "result": {
            "title": "列表页", "url": state["url"],
            "elements": [{"index": i, "tag": "li", "name": f"项{i}"} for i in range(state["elements"])],
            "body_preview": "候选人卡片…立即沟通\n" * 3}}
    if action == "extract":
        return {"ok": True, "result": {"rows": [{"text": f"行{i}", "fields": {"res_id_encode": f"sid{i}"}} for i in range(3)]}}
    if action == "click":
        return {"ok": True, "result": {"clicked": {"index": params.get("index")}}}
    return {"ok": False, "error": f"unexpected action {action}"}


llm_calls = {"n": 0}
mode = {"type": "snapshot_loop"}  # snapshot_loop | normal | repeat_click


def fake_llm_chat(messages, api_key):
    llm_calls["n"] += 1
    if mode["type"] == "snapshot_loop":
        return '{"action":"snapshot","reason":"需要重新获取快照"}'
    if mode["type"] == "repeat_click":
        return '{"action":"click","index":1,"reason":"反复点同一按钮"}'
    # normal：第 2 次 LLM 调用后 finish
    if llm_calls["n"] >= 2:
        return '{"action":"finish","summary":"完成","data":{}}'
    return '{"action":"extract","anchor_text":"立即沟通","reason":"提取"}'


core.submit_task = fake_submit_task
core.llm_chat = fake_llm_chat


def on_step(ev):
    events.append(ev)


def run_async(task, max_steps=20):
    return core.run_loop(task, "http://fake", max_steps=max_steps, api_key="fake",
                         on_step=on_step, page_delay_min=0, page_delay_max=0)


# ---------- A. 打转场景（纯 snapshot）→ 应 stuck ----------
events.clear(); llm_calls["n"] = 0; mode["type"] = "snapshot_loop"
t0 = time.time()
final = run_async("看页面", max_steps=20)
types = [e["type"] for e in events]
assert "stuck" in types, f"A: 无 stuck 事件: {types}"
assert final["ok"] is False and "卡死" in final["summary"], f"A: 未按卡死终止: {final['summary']}"
assert types.count("step_limit") == 0, "A: 不应走到 step_limit（应提前卡死终止）"
print(f"A 打转→stuck ✅（{len(types)} 事件，用时 {time.time()-t0:.1f}s）：{final['summary']}")

# ---------- B. 正常场景（有实质进展）→ 不 stuck ----------
events.clear(); llm_calls["n"] = 0; mode["type"] = "normal"
final = run_async("提取任务", max_steps=20)
types = [e["type"] for e in events]
assert "stuck" not in types, f"B: 误报 stuck: {types}"
assert final["ok"] is True, f"B: 应正常完成: {final}"
print(f"B 正常完成 ✅（事件: {' → '.join(types)}）")

# ---------- C. 重复动作（同一 click 反复）→ 应 stuck ----------
events.clear(); llm_calls["n"] = 0; mode["type"] = "repeat_click"
final = run_async("点按钮", max_steps=20)
types = [e["type"] for e in events]
assert "stuck" in types, f"C: 重复动作未触发 stuck: {types}"
print(f"C 重复动作→stuck ✅：{final['summary']}")

print("\nT3 无进展检测全部通过 ✅")
