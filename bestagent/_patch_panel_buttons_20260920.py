#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_panel_buttons_20260920.py — 面板加两个按钮（老板 2026-09-20 第 3 件）

加什么（v1.12.1）：
  · 💬 打招呼   —— 打开**最新打招呼报告** → 调 `greet_exec.py` **dry-run 列清单**（一个人都不发）
                   → 老板点「确认发送」才真发（`--yes`，一次最多 N 人）。**按钮不替小猎拍板**。
  · 📨 查看回复 —— 调 `reply_run.py`（**纯读**：职聊页 → 读会话 → 落台账 → 报告分区刷新）。
  · 报告栏加一行「打开打招呼报告」（过程 HTML）。

安全：两个动作都在**子进程**里跑（不占面板线程）；dry-run 默认；真发要再点一次确认。
⚠️ 动 m3_chat.py 用带断言补丁（老板规矩：edit 工具在这文件上会 Win32 1175）。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).with_name("m3_chat.py")

# ── 1. 子进程助手 ─────────────────────────────────────────────────────────
ANCHOR1 = 'def artifact_open_row(path: Path, key: str) -> None:'
HELPER = '''def run_script(script: str, args: list[str], *, timeout: int = 600) -> tuple[bool, str]:
    """跑一个本地脚本（**子进程**，不占面板线程），返回 (成功?, 输出尾部)。

    ⚠️ 只在面板按钮里用；脚本自己会做前置检查/校验，面板不替它判断成功。
    """
    import subprocess
    py = sys.executable
    cmd = [py, str(BASE / script)] + [str(a) for a in args]
    try:
        p = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode == 0, out
    except Exception as e:  # noqa: BLE001
        return False, f"跑 {script} 出错：{e}"


def greeting_plan_path(job_code: str) -> str:
    """本岗最新口径计划（greet_exec 要它；没有就给空串，脚本自己会拒绝）。"""
    reps = _job_dir({"job_code": job_code}) / "reports"
    got = sorted(reps.glob("greeting_plan_*.json"), key=lambda p: p.stat().st_mtime)
    return str(got[-1]) if got else ""


'''

# ── 2. 两个按钮（插在"第三行先不放"那段注释之前）────────────────────────────
ANCHOR2 = '''    # v1.12.0：第三行**先不放了**——老板口径「每个环节先做最基础的设计」，'''
BUTTONS = '''    # ── v1.12.1：④ 打招呼 / ⑤ 查看回复（老板 2026-09-20 拍板加）────────────────
    # 分工：**按钮不替小猎拍板**——面板只负责"把脚本的清单/结果端上来"；
    #   打招呼先 dry-run 列清单（一个人都不发），老板点「确认发送」才真发。
    jc = job["job_code"]
    _reps = _job_dir(job) / "reports"
    _plans = sorted(_reps.glob("greeting_plan_*.json"), key=lambda p: p.stat().st_mtime)
    _plan = str(_plans[-1]) if _plans else ""
    _greets = sorted(_reps.glob("打招呼报告_*.json"), key=lambda p: p.stat().st_mtime)
    _greet_json = _greets[-1] if _greets else None
    _greet_html = sorted(_reps.glob("打招呼报告_*_过程.html"), key=lambda p: p.stat().st_mtime)

    c8, c9 = st.columns(2)
    _g_help = ("v1.12.1：小猎读**最新打招呼报告**（谁、发什么都是报告写死的）→ 打开候选人详情页 → "
               "点【立即沟通】→ 点【不选择职位开聊】→ **紧接着发报告里的岗位介绍** → 关页面 → 记台账。"
               "｜🔴 先 dry-run **列清单、一个人都不发**；你点「确认发送」才真发（人工闸门）。"
               "｜前提：有报告 + 现在在时间窗内 + 桥在跑（双击 bridge-agent\\\\start_bridge.bat）。")
    _has_bridge = True
    if c8.button("💬 打招呼（先列清单）", key="act_greet_exec", use_container_width=True,
                 disabled=not (_greet_json and decision_ok), help=_g_help):
        ok_run, out = run_script("greet_exec.py", ["--job-code", jc], timeout=120)
        st.session_state["greet_preview"] = out
        st.session_state["greet_preview_ok"] = ok_run
    if st.session_state.get("greet_preview"):
        st.markdown("**📋 待打清单（dry-run，没发出去）**")
        st.code(st.session_state["greet_preview"], language="text")
        _n = st.number_input("本次最多打几个", min_value=1, max_value=50, value=3, step=1,
                             key="greet_confirm_n")
        if st.button(f"✅ 确认发送（最多 {int(_n)} 个，占 {int(_n)} 个额度）", key="act_greet_confirm",
                     type="primary"):
            ok2, out2 = run_script("greet_exec.py",
                                   ["--job-code", jc, "--yes", "--limit", str(int(_n))], timeout=900)
            st.session_state["greet_result"] = out2
            st.session_state["greet_preview"] = ""
    if st.session_state.get("greet_result"):
        st.markdown("**🤖 打招呼结果**")
        st.code(st.session_state["greet_result"], language="text")

    _r_help = ("v1.12.1：小猎开**职聊页**（h.liepin.com/im/showmsgnewpage）→ 读会话列表（谁、什么时候、"
               "最后一句、[已读]/[未读]）→ 落台账 → 重出报告（等回复→有回复）。**纯读，0 花费、0 风险**。")
    if c9.button("📨 查看回复（读回来记账）", key="act_reply_run", use_container_width=True,
                 disabled=not decision_ok, help=_r_help):
        ok3, out3 = run_script("reply_run.py", ["--job-code", jc], timeout=300)
        st.session_state["reply_result"] = out3
    if st.session_state.get("reply_result"):
        st.markdown("**📨 查看回复结果**")
        st.code(st.session_state["reply_result"], language="text")
    if _greet_html:
        st.caption("📄 打招呼报告（过程页）：")
        artifact_open_row(_greet_html[-1], key=f"greet_rep_{jc}_{_greet_html[-1].name}")

'''

# ── 3. 版本号/说明（v1.12.0 → v1.12.1）────────────────────────────────────
OLD_VER = 'st.set_page_config(page_title="数字合伙人 · 对话汇报（v1.12.0）", page_icon="🗣", layout="wide")'
NEW_VER = 'st.set_page_config(page_title="数字合伙人 · 对话汇报（v1.12.1）", page_icon="🗣", layout="wide")'

OLD_CAP = 'st.caption("v1.12.0｜ ③池子评估**已取消**'
NEW_CAP = 'st.caption("v1.12.1｜ ④打招呼（先列清单→确认发）/ ⑤查看回复（纯读）**已接入**｜ v1.12.0：③池子评估**已取消**'


def _apply(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    assert n == 1, f"❌ [{label}] 命中 {n} 次（必须恰好 1 次）——文件未改动"
    print(f"  ✅ {label}")
    return src.replace(old, new, 1)


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    print(f"补丁目标：{TARGET}（{len(src)} 字符）")
    src = _apply(src, ANCHOR1, HELPER + ANCHOR1, "1/4 插入 run_script 助手")
    src = _apply(src, ANCHOR2, BUTTONS + ANCHOR2, "2/4 插入两个按钮")
    src = _apply(src, OLD_VER, NEW_VER, "3/4 版本号 → v1.12.1")
    src = _apply(src, OLD_CAP, NEW_CAP, "4/4 说明行 → v1.12.1")
    TARGET.write_text(src, encoding="utf-8")
    print(f"✅ 已写入（{len(src)} 字符）")


if __name__ == "__main__":
    sys.exit(main())
