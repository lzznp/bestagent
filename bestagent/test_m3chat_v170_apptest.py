# -*- coding: utf-8 -*-
"""m3_chat v1.7.0 AppTest 冒烟（无 API，M3CHAT_STUB=1）：UI 渲染 + 拍板路由 + 按钮执行显示层。

跑法（bestagent 目录，lzstudy 解释器）：python test_m3chat_v170_apptest.py
验证点：
1. 启动无异常（含进度行/按钮行/对话流渲染）
2. pending 岗：②采集/📋发岗 按钮 disabled；进度行提示「等你拍板」
3. chat_input 输入「做吧」→ 本地拍板 accept：state.decision=accept、对话出现确认消息、②按钮解锁
4. 追问「为什么是 16 分」→ 不触发拍板，落自由对话（stub 假执行）
5. decline 岗：输入「重新判断」→ 走 analyze（stub），decision 回 pending
6. 旧岗（无 decision 字段）兼容：②按钮 enabled
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

WORKSPACE = Path(r"D:\study\bestagent\bestagent")
tmp_root = WORKSPACE / "data" / "_selftest_tmp"
tmp_root.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(tmp_root)  # 沙箱下默认 TEMP 区清理受限，指到工作区


def _plain_mkdtemp(*args, **kwargs):
    """沙箱对 tempfile.mkdtemp 产物目录加限制 ACL（清理时 scandir/chmod 被拒，WinError 5），
    用普通 os.mkdir 复刻 mkdtemp 语义（目录建在 tempfile.tempdir 下）以绕开限制。"""
    import uuid as _uuid

    base = kwargs.pop("dir", None) or tempfile.tempdir or "."
    prefix = kwargs.pop("prefix", "tmp")
    suffix = kwargs.pop("suffix", "")
    if kwargs:  # 语义不支持的其他参数（Windows 下 mode 等无意义）
        raise TypeError(f"unsupported mkdtemp kwargs: {kwargs.keys()}")
    for _ in range(100):
        name = os.path.join(base, prefix + _uuid.uuid4().hex + suffix)
        try:
            os.mkdir(name)
            return name
        except FileExistsError:
            continue
    raise FileExistsError("mkdtemp: 无法生成唯一目录名")


tempfile.mkdtemp = _plain_mkdtemp  # streamlit AppTest 内部用 mkdtemp/TemporaryDirectory
os.environ["M3CHAT_STUB"] = "1"
os.environ["M3CHAT_CHAT_DIR"] = str(tmp_root)  # m3_chat.py 支持环境变量覆盖 CHAT_DIR（AppTest 隔离）

import m3_chat  # noqa: E402

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


def make_job(code: str, title: str, jd_text: str, state: dict) -> dict:
    """在临时 CHAT_DIR 建岗（AppTest 用；python 多层 mkdir 在本机沙箱可行，勿用 mkdtemp）。"""
    d = tmp_root / code
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    (d / "reports").mkdir(parents=True, exist_ok=True)
    (d / "jd.txt").write_text(jd_text, encoding="utf-8")
    meta = {"job_code": code, "title": title, "created_at": "2026-09-07 09:00:00",
            "session_id": f"m3chat-{code}"}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "transcript.json").write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    st_ = {"job_code": code, "jd_provided": True, "updated_at": "2026-09-07 09:00:00"}
    st_.update(state)
    (d / "state.json").write_text(json.dumps(st_, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"job_code": code, "title": title, "dir": d,
            "session_id": f"m3chat-{code}", "created_at": meta["created_at"]}


def main() -> None:
    from streamlit.testing.v1 import AppTest

    try:
        # 三个测试岗：pending（分析完等你拍板）/ decline（已拍板不做）/ old（旧岗无 decision 字段）
        make_job("J-PEND-001", "待拍板岗", "职位：测试 岗位职责：测试 佣金10万 北京",
                 {"step1_analyzed": True, "decision": "pending", "last_action": "岗位分析"})
        make_job("J-DECL-001", "已拒岗", "职位：测试 岗位职责：测试 佣金10万 北京",
                 {"step1_analyzed": True, "decision": "decline", "last_action": "拍板：不做"})
        make_job("J-OLD-001", "旧岗", "职位：测试 岗位职责：测试 佣金10万 北京",
                 {"step1_analyzed": True, "last_action": "岗位分析"})

        # 默认选中最新岗（list_jobs 按 created_at 倒序；三个岗同 ts → 顺序由 iterdir 定，显式指定）
        at = AppTest.from_file(str(WORKSPACE / "m3_chat.py"), default_timeout=60)
        at.session_state["job_pick_chat"] = "J-PEND-001"
        at.run()
        check("启动无异常(pending 岗)", not at.exception,
              str([e.value for e in at.exception]) if at.exception else "")
        check("pending 岗 ②按钮 disabled", at.button(key="act_collect").disabled, "")
        check("pending 岗 📋发岗 disabled", at.button(key="act_post_text").disabled, "")
        check("pending 岗 🚀按钮可用", not at.button(key="act_analyze").disabled, "")
        texts = " ".join(str(m.value) for m in at.markdown)
        check("进度行含「等你拍板」", "等你拍板" in texts, "")

        # 拍板：输入「做吧」→ 本地 accept（拍板路径含 st.rerun，AppTest 需再 run 一次消费最终渲染）
        at.chat_input[0].set_value("做吧")
        at.run()
        at.run()
        st_pend = m3_chat.load_state("J-PEND-001")
        check("拍板 accept 落盘", st_pend.get("decision") == "accept", f"→ {st_pend.get('decision')}")
        texts = " ".join(str(m.value) for m in at.markdown)
        check("对话出现确认消息", "这单咱做" in texts, "")
        check("accept 后 ②按钮解锁", not at.button(key="act_collect").disabled, "")

        # 追问「为什么是 16 分」→ 不触发拍板（决策仍是 accept），落自由对话 stub
        before = len(m3_chat.load_transcript("J-PEND-001"))
        at.chat_input[0].set_value("为什么是 16 分？评分的依据是什么")
        at.run()
        st_pend = m3_chat.load_state("J-PEND-001")
        check("追问不覆盖决策", st_pend.get("decision") == "accept", f"→ {st_pend.get('decision')}")
        tr = m3_chat.load_transcript("J-PEND-001")
        check("追问走了自由对话(stub 回复)", len(tr) > before and "假执行" in tr[-1].get("content", ""),
              f"→ {tr[-1].get('content', '')[:40] if tr else 'empty'}")

        # decline 岗：②按钮 disabled + 输入「重新判断」→ analyze(stub) → decision 回 pending
        at.session_state["job_pick_chat"] = "J-DECL-001"
        at.run()
        check("decline 岗 ②按钮 disabled", at.button(key="act_collect").disabled, "")
        at.chat_input[0].set_value("重新判断这单")
        at.run()
        st_dec = m3_chat.load_state("J-DECL-001")
        check("重新判断 → decision 回 pending", st_dec.get("decision") == "pending",
              f"→ {st_dec.get('decision')}")
        check("重新判断走了 analyze(stub)", "假执行" in str(at.markdown[-1].value)
              or any("假执行" in str(m.value) for m in at.markdown), "")

        # 旧岗兼容：decision 字段缺失 → ②按钮 enabled
        at.session_state["job_pick_chat"] = "J-OLD-001"
        at.run()
        check("旧岗(无 decision) ②按钮 enabled", not at.button(key="act_collect").disabled, "")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
