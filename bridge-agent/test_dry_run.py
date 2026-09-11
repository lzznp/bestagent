# -*- coding: utf-8 -*-
"""T7 临时验证：dry-run + mock LLM 全链路（直接调 run_loop，绕开 CLI argv 引号坑）。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import agent.core as core

spec = ('[{"action":"extract","anchor_text":"立即沟通"},'
        '{"action":"click","index":1},'
        '{"action":"navigate","url":"https://example.com"},'
        '{"action":"snapshot"},'
        '{"action":"finish","summary":"done"}]')
seq = json.loads(spec)
state = {"i": 0}


def mock_llm(messages, api_key):
    if state["i"] < len(seq):
        act = seq[state["i"]]
        state["i"] += 1
        return json.dumps(act, ensure_ascii=False)
    return '{"action":"snapshot","reason":"mock 序列耗尽"}'

events = []
final = core.run_loop("dry-run 试跑", "http://127.0.0.1:8080", max_steps=10, api_key="x",
                      on_step=events.append, dry_run=True, mock_llm=mock_llm, tab_id=1890028341,
                      page_delay_min=0, page_delay_max=0)
blocked = [e for e in events if e["type"] == "dry_run_blocked"]
acts = [e["action"] for e in events if e["type"] == "act"]
print("执行的动作:", acts)
print("被拦截的写动作:", [e["action"] for e in blocked])
print("final.ok:", final["ok"], "| summary:", final["summary"])

assert "click" in [e["action"] for e in blocked], "click 应被 dry-run 拦截"
assert "navigate" in [e["action"] for e in blocked], "navigate 应被 dry-run 拦截"
assert "extract" in acts, "extract（只读）应执行"
assert final["ok"] is True, "最终应完成"
print("\nT7 dry-run + mock LLM 全链路验证通过 ✅")
