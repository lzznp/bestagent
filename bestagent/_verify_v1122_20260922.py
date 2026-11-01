# -*- coding: utf-8 -*-
"""v1.12.2 收尾总验证（只读真实岗 + 两套测试套件）。

跑法（bestagent 目录，lzstudy 解释器）：python _verify_v1122_20260922.py
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
WB = Path(r"D:\study\bestagent\bestagent")
REAL = WB / "data" / "chat" / "J-CHAT-20260921-143843"
JOB = "J-CHAT-20260921-143843"
PY = sys.executable
FAIL = 0


def h(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "(缺)"


print("═══ 1. 真实岗：只读复核（跑前）═══")
before = {p.name: (p.stat().st_size, p.stat().st_mtime) for p in REAL.rglob("*")}
b_state, b_tr, b_db = h(REAL / "state.json"), h(REAL / "transcript.json"), h(REAL / "job.db")

os.environ["M3CHAT_STUB"] = "1"
sys.path.insert(0, str(WB))
import m3_chat  # noqa: E402

st = m3_chat.load_state(JOB)
raw = json.loads((REAL / "state.json").read_text(encoding="utf-8"))
print(f"  load_state.decision       = {st.get('decision')!r}   （期望 'pending'）")
print(f"  load_state.step1_analyzed = {st.get('step1_analyzed')!r}")
print(f"  load_state.step2_collected= {st.get('step2_collected')!r}")
print(f"  盘上 state.json.decision  = {raw.get('decision')!r}   （期望 None：只改读取口径）")
print(f"  decision_note/ts          = {st.get('decision_note')!r}/{st.get('decision_ts')!r}（期望 None：不伪造历史）")
if not (st.get("decision") == "pending" and raw.get("decision") is None and not st.get("decision_note")):
    FAIL += 1

print("\n═══ 2. 测试套件 ═══")
for f in ("test_m3chat_v190_buttons.py", "test_m3chat_v182_render.py"):
    out = subprocess.run([PY, str(WB / f)], cwd=str(WB), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    last = [ln for ln in (out.stdout or "").splitlines() if ln.startswith("结果")]
    tail = last[-1] if last else "(没跑出结果)"
    ok = "FAIL=0" in tail and out.returncode == 0
    print(f"  {'[OK]' if ok else '[XX]'} {f}: {tail} (exit={out.returncode})")
    if not ok:
        FAIL += 1

print("\n═══ 3. 真实岗：跑完复核（大小+修改时间全量比对）═══")
after = {p.name: (p.stat().st_size, p.stat().st_mtime) for p in REAL.rglob("*")}
same = before == after
print(f"  state.json      {b_state} -> {h(REAL / 'state.json')}")
print(f"  transcript.json {b_tr} -> {h(REAL / 'transcript.json')}")
print(f"  job.db          {b_db} -> {h(REAL / 'job.db')}")
print(f"  本岗目录内所有文件（大小+修改时间）完全未变: {same}")
if not same:
    for k in set(before) | set(after):
        if before.get(k) != after.get(k):
            print(f"    ⚠️ 变了: {k} {before.get(k)} -> {after.get(k)}")
    FAIL += 1

print(f"\n═══ 结论：{'全部通过' if FAIL == 0 else f'有 {FAIL} 项不通过'} ═══")
sys.exit(1 if FAIL else 0)
