# -*- coding: utf-8 -*-
"""test_m3chat_v180_jobname.py — v1.8.0「岗位认人」自测（不调 API、不碰真岗）

覆盖（2026-09-14 老板提：列表里只有 J-CHAT-…，人认不出是哪个岗，结果点错了岗）：
1. job_display_name 的优先级：短名 > 老板写的标题 > ①分析真名 > jd.txt 里的岗位名 > 岗位号
2. save_meta / load_last_job 落盘与回读
3. AppTest：面板起得来；「📄 岗位信息」按钮在；点它不抛异常（弹窗能开）
4. 左侧 selectbox 默认选中"上次在看的岗"（而不是列表第一个）

跑法（bestagent 目录，lzstudy 解释器）：python test_m3chat_v180_jobname.py
隔离：M3CHAT_CHAT_DIR（岗位目录）+ M3CHAT_LAST_JOB（偏好文件）都指到 data/_selftest_tmp/，
      **不碰老板的真实岗位目录、也不碰真实的 .last_job**。

⚠️ 为什么偏好文件也要环境变量隔离：AppTest 会把 m3_chat.py 当脚本**重新执行一遍**，
   所以"在测试里改 m3_chat.LAST_JOB_FILE 属性"是无效的（会被重新赋值覆盖）——
   必须走环境变量，才能让脚本重执行时也读到隔离路径。
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
SANDBOX = WORKSPACE / "data" / "_selftest_tmp" / "v180_jobname"
tempfile.tempdir = str(WORKSPACE / "data" / "_selftest_tmp")
Path(tempfile.tempdir).mkdir(parents=True, exist_ok=True)


def _plain_mkdtemp(*args, **kwargs):
    """沙箱下 tempfile.mkdtemp 的产物目录被加限制 ACL（清理时 WinError 5），用普通 os.mkdir 复刻语义。"""
    import uuid as _uuid
    base = kwargs.pop("dir", None) or tempfile.tempdir or "."
    prefix = kwargs.pop("prefix", "tmp")
    suffix = kwargs.pop("suffix", "")
    if kwargs:
        raise TypeError(f"unsupported mkdtemp kwargs: {kwargs.keys()}")
    for _ in range(100):
        name = os.path.join(base, prefix + _uuid.uuid4().hex + suffix)
        try:
            os.mkdir(name)
            return name
        except FileExistsError:
            continue
    raise FileExistsError("mkdtemp: 无法生成唯一目录名")


tempfile.mkdtemp = _plain_mkdtemp

if SANDBOX.exists():
    shutil.rmtree(SANDBOX, ignore_errors=True)
CHAT_TEST = SANDBOX / "chat"
CHAT_TEST.mkdir(parents=True, exist_ok=True)
os.environ["M3CHAT_CHAT_DIR"] = str(CHAT_TEST)
os.environ["M3CHAT_LAST_JOB"] = str(SANDBOX / ".last_job")
os.environ["M3CHAT_STUB"] = "1"

import m3_chat  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name} {extra}")


def make_job(code: str, meta_title: str = "", display_name: str = "",
             jd_text: str = "禾蛙\n职位职责：干活的\n", analyze_title: str = "") -> None:
    d = CHAT_TEST / code
    (d / "reports").mkdir(parents=True, exist_ok=True)
    meta = {"job_code": code, "title": meta_title or f"岗位 {code}", "created_at": "2026-09-14 10:00:00",
            "session_id": f"m3chat-{code}"}
    if display_name:
        meta["display_name"] = display_name
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "jd.txt").write_text(jd_text, encoding="utf-8")
    if analyze_title:
        (d / "reports" / "analyze_20260914-100000.json").write_text(
            json.dumps({"jd_extracted": {"job_title": analyze_title, "company": "某公司", "city": "南京",
                                         "salary": "10-20k", "requirements": "x", "description": "y"},
                        "progress": {"status": "刚发布"},
                        "score": {"total": 12, "level": "普通", "advice": "先沟通", "details": {}, "risks": ["r1"]},
                        "recommendation": "沟通"}, ensure_ascii=False), encoding="utf-8")


def job_of(code: str) -> dict:
    return next(j for j in m3_chat.list_jobs() if j["job_code"] == code)


def test_display_name() -> None:
    print("[1] 显示名优先级")
    make_job("J-T-1", analyze_title="①分析里的真名")
    check("①分析真名 > jd 噪音", m3_chat.job_display_name(job_of("J-T-1")) == "①分析里的真名")

    make_job("J-T-2", meta_title="老板写的标题", analyze_title="①分析里的真名")
    check("老板写的标题 > ①分析真名", m3_chat.job_display_name(job_of("J-T-2")) == "老板写的标题")

    make_job("J-T-3", meta_title="老板写的标题", display_name="短名")
    check("短名 > 老板写的标题", m3_chat.job_display_name(job_of("J-T-3")) == "短名")

    make_job("J-T-4")
    check("无①分析 + jd 全是噪音 → 退回岗位号",
          m3_chat.job_display_name(job_of("J-T-4")) == "J-T-4",
          extra=repr(m3_chat.job_display_name(job_of("J-T-4"))))

    make_job("J-T-5", jd_text='FAE/技术支持\t"岗位职责： 现场调试"\n第二行\n')
    check("无①分析 → 退回 jd 里的岗位名（tab 前那段）",
          m3_chat.job_display_name(job_of("J-T-5")) == "FAE/技术支持",
          extra=repr(m3_chat.job_display_name(job_of("J-T-5"))))


def test_meta_and_last_job() -> None:
    print("[2] 短名落盘 / 记住最后在看的岗")
    m3_chat.save_meta("J-T-1", display_name="我自己起的短名")
    check("短名写进 meta.json 并回读", m3_chat.job_display_name(job_of("J-T-1")) == "我自己起的短名")

    m3_chat.save_last_job("J-T-3")
    check("load_last_job 回读", m3_chat.load_last_job() == "J-T-3")
    m3_chat.LAST_JOB_FILE.write_text("", encoding="utf-8")
    check("文件空 → 返回空串（不是异常）", m3_chat.load_last_job() == "")


def test_apptest() -> None:
    print("[3] AppTest：面板起得来 + 岗位信息按钮 + 弹窗不报错 + 默认选中上次的岗")
    from streamlit.testing.v1 import AppTest
    m3_chat.save_last_job("J-T-2")
    at = AppTest.from_file(str(WORKSPACE / "m3_chat.py"), default_timeout=60)
    at.run()
    check("启动无异常", not at.exception, extra=str(at.exception))
    if at.exception:
        return
    keys = [b.key for b in at.button]
    check("「📄 岗位信息」按钮在", any(k.startswith("jobinfo_") for k in keys), extra=str(keys[:6]))
    check("默认选中上次在看的岗 J-T-2", at.selectbox(key="job_pick_chat").value == "J-T-2",
          extra=repr(at.selectbox(key="job_pick_chat").value))
    btn = next((b for b in at.button if b.key == "jobinfo_J-T-2"), None)
    if btn is None:
        check("找到 J-T-2 的信息按钮", False)
        return
    btn.click().run()
    check("点开弹窗不抛异常", not at.exception, extra=str(at.exception))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    test_display_name()
    test_meta_and_last_job()
    test_apptest()
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)
