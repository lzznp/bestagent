# -*- coding: utf-8 -*-
"""m3_chat v1.7.0 真跑验证（一次性自测，headless 不调 UI，M3CHAT_CHAT_DIR 隔离目录）：
①岗前分析（真 agent）→ 验证：a) 回复为「态度+理由+请拍板」判断式 b) analyze JSON + HTML 落盘
c) state 进入 decision=pending d) 模拟老板拍板「做吧」→ accept 落盘。

跑法（bestagent 目录，lzstudy 解释器）：python selftest_v170_realtime.py <jd_path>
注意：真执行需 .env（默认取 参考代码/lietou-agent/browser-agent/.env）；SDK runtime 需非沙箱/全权限。
"""
import os
import shutil
import sys
from pathlib import Path

WORKSPACE = Path(r"D:\study\bestagent\bestagent")
JD = Path(sys.argv[1]) if len(sys.argv) > 1 else WORKSPACE / "data" / "inbox" / "jd_user_002.txt"

tmp_root = WORKSPACE / "data" / "_selftest_tmp" / "realtime"
if tmp_root.exists():
    shutil.rmtree(tmp_root, ignore_errors=True)
tmp_root.mkdir(parents=True, exist_ok=True)
os.environ["M3CHAT_CHAT_DIR"] = str(tmp_root)

import m3_chat  # noqa: E402


def main() -> None:
    jd_bytes = JD.read_bytes()
    job = m3_chat.create_job(title=f"[自测] {JD.stem}", jd_bytes=jd_bytes)
    print(f"== 测试岗：{job['job_code']}（JD: {JD.name}，{len(jd_bytes)}B）")
    task = m3_chat.build_step1_task(job)
    print("== 跑 ① 岗前分析（真 agent，请等待，长任务）…")
    reply, new_files = m3_chat.run_assistant(job, task, m3_chat.DEFAULT_ENV, stub=False,
                                             max_tokens=16384)
    print("\n== 小猎回复 ==")
    print(reply)
    print("\n== 新产物 ==")
    for f in new_files:
        print("  -", f.name, f.stat().st_size, "B")
    st_ = m3_chat.load_state(job["job_code"])
    print(f"\n== state: decision={st_.get('decision')} step1_analyzed={st_.get('step1_analyzed')}")

    # 模拟老板追问 + 拍板（本地逻辑，不耗 API）
    q = m3_chat.detect_decision_intent("为什么给这个判断？评分依据是什么")
    print(f"追问「为什么…」→ 识别: {q!r}（应为空 → 走自由对话）")
    dec = m3_chat.detect_decision_intent("做吧")
    print(f"拍板「做吧」→ 识别: {dec!r}（应为 accept）")
    m3_chat.record_decision(job, dec, "做吧")
    st_ = m3_chat.load_state(job["job_code"])
    print(f"拍板后 state: decision={st_.get('decision')} note={st_.get('decision_note')}")
    print(f"确认消息：{m3_chat.build_decision_reply(dec, '做吧')[:60]}…")
    print(f"\n产物目录：{tmp_root}")


if __name__ == "__main__":
    main()
