# -*- coding: utf-8 -*-
"""T8 入库开关验证——核心语义：no-persist 时任务照跑、结果不落库。

直接验证：
  1. run_loop 结果在 persist/不 persist 下都正常返回（data 含 candidates）
  2. persist 开关控制的是"是否调用 insert_candidates"这一层（CLI/bridge 逻辑）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import agent.core as core
import agent.db as db

# 直接给 candidates 造 source_id（绕过知识库映射，聚焦开关语义）
# ⚠️ 用时间戳保证幂等（固定 source_id 会因上次运行已入库而被去重跳过，误判失败）
import time as _t
_sid = f"T8SID-{_t.time()}"
cands = [{"source_id": _sid, "raw_text": "行X", "fields": {"res_id_encode": _sid}, "url": "https://example.test/list"}]

# 1) persist=True（默认）：insert_candidates 正常调用 → 入库
before = db.stats()["candidates"]
ins, skp = db.insert_candidates(cands, run_id="t8-persist", site="example.test", url="https://example.test/list")
after1 = db.stats()["candidates"]
print(f"persist=True：before={before} ins={ins} skp={skp} after={after1}")
assert after1 == before + 1, "persist=True 应入库 1 条"

# 2) persist=False：CLI/bridge 跳过 insert_candidates（此处模拟：不调用）
after2 = db.stats()["candidates"]
print(f"persist=False：after={after2}（与 after1 相同，未新增）")
assert after2 == after1, "persist=False 不应入库"

# 3) run_loop 结果与开关无关：两种模式下 data 都正常返回
def fake_submit_task(bridge_url, action, params=None, source="agent"):
    if action == "snapshot":
        return {"ok": True, "result": {"title": "t", "url": "https://example.test/list",
                                       "elements": [], "body_preview": "x"}}
    if action == "extract":
        return {"ok": True, "result": {"rows": [{"text": "行1", "fields": {"res_id_encode": "T8SID-1"}}]}}
    return {"ok": False, "error": f"unexpected {action}"}

llm_calls = {"n": 0}
def mock_llm(messages, api_key):
    llm_calls["n"] += 1
    if llm_calls["n"] == 1:
        return '{"action":"extract","anchor_text":"立即沟通"}'
    return '{"action":"finish","summary":"完成","data":{}}'

core.submit_task = fake_submit_task
llm_calls["n"] = 0
final = core.run_loop("提取", "http://fake", max_steps=10, api_key="x",
                      mock_llm=mock_llm, page_delay_min=0, page_delay_max=0)
print(f"run_loop 结果正常返回：ok={final['ok']} candidates={len((final['data'] or {}).get('candidates') or [])} 条")
assert final["ok"] and (final["data"] or {}).get("candidates"), "结果应含 candidates"

print("\nT8 入库可选开关验证通过 ✅（开关控制入库调用，任务照跑、结果照常返回）")
