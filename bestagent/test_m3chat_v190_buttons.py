# -*- coding: utf-8 -*-
"""m3_chat v1.9.0 按钮层 AppTest（无 API，M3CHAT_STUB=1，隔离目录）：②改名 + 顺序 + 闸门。

跑法（bestagent 目录，lzstudy 解释器）：python test_m3chat_v190_buttons.py

出处：老板 2026-09-16 拍板「先接线吧，先把 streamlit 面板按钮做好」= 先做按钮层；
**同日 v1.9.1 执行器已接线**（collect_rules + collect_exec + job_db + rule 报告）→ `_EXEC_WIRED=True`；
**同日 v1.10.0 闭环补齐**（脚本自己设条件+搜索、够格就开、自动翻页、换关键字、**拆掉人为额度**）
→ 任务书里的"翻页人工/老板先搜好/--details 3"等过期口径已删，本套件的对应断言同步改成"验它不含旧口径"。
本文件因此覆盖**两个阶段**的行为：
  · 阶段一（按钮层）：改名/顺序/文案已落在代码里（现在仍在验）；
  · 阶段二（接线后）：②按钮按"拍板做 + 没有旧计划"解锁、`detect_collect_intent` 恢复工作。
⚠️ 若将来把闸门关回去（`_EXEC_WIRED=False`），本文件前两组断言会红——那是**故意**的：
   它就是在拦"关回去却不改测试"这种情况。

本文件覆盖（老两份套件的 ②按钮断言已按新行为并到这里，**不删覆盖**）：
1. 新按钮/新文案：② 标签含「正式采集」（旧名「探索采集」不再出现在按钮上）
2. 顺序：执行行 = 📋出采集计划 → ②正式采集 → 💬打招呼报告（v1.12.0：③池子评估已取消）
   （v1.11.0：老板拍板**取消「搜索体检/采集计划」两个子步骤** → 体检按钮摘掉、出计划另起一个按钮、
    ②= **真跑**；旧断言里的"体检在按钮行/进度行"改成"体检**不在**了"）
3. 闸门：`_EXEC_WIRED` 是唯一开关；**接线下** accept 后解锁、pending/decline/旧岗语义正确
   （2026-09-22 并进新口径：**分析完 + 无决策记录 ⇒ 等价待拍板**（`load_state` 推导，见该函数内注释）
    —— 治"09-21 那个岗①分析在自由对话里跑完 ⇒ `decision` 永远 null ⇒ 对话里记不了拍板"。
    因此 ② 按钮的锁从"无 decision 就放行"改成"无决策记录 = 没拍板 = 锁"；
    本套件里 `J-OLD-001` 旧口径断言同步改成 `J-NODEC-001` 三态 + 真·旧岗两态，**覆盖不删**）
4. 聊天里说「去猎聘跑一轮」→ 走 `collect_plan`（不再落自由对话的"假执行"）
5. 💬打招呼报告的解锁逻辑：②没采集 → 灰；有采集产物 → 亮
   （v1.12.0 还摘掉了三个按钮：③池子评估 / 旧打招呼清单 / 入库当前岗 —— 本套件断言它们**不在**）
   （v1.11.0 **认账口径**：`collect_*.json`／`job.db` 都算采过；**只有 `collect_plan_*.json` 不算**）
6. 打招呼/入库两个按钮仍在（重排不许丢功能）；**「②正式采集」无计划也能点**（一回合内自定计划+直接跑）
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
os.environ["M3CHAT_LAST_JOB"] = str(tmp_root / ".last_job")

import m3_chat  # noqa: E402
import job_db  # noqa: E402

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


def make_job(code: str, title: str, state: dict, files: tuple = ()) -> None:
    """在临时 CHAT_DIR 建岗（python 多层 mkdir 在本机沙箱可行，勿用 mkdtemp）。"""
    d = tmp_root / code
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    (d / "reports").mkdir(parents=True, exist_ok=True)
    (d / "jd.txt").write_text("职位：测试 岗位职责：测试 佣金10万 北京", encoding="utf-8")
    (d / "meta.json").write_text(json.dumps(
        {"job_code": code, "title": title, "created_at": "2026-09-16 09:00:00",
         "session_id": f"m3chat-{code}"}, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "transcript.json").write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    for f in files:
        (d / "reports" / f).write_text("{}", encoding="utf-8")
    st_ = {"job_code": code, "jd_provided": True, "step1_analyzed": True,
           "updated_at": "2026-09-16 09:00:00"}
    st_.update(state)
    (d / "state.json").write_text(json.dumps(st_, ensure_ascii=False, indent=2), encoding="utf-8")


def texts(at) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def send(at, msg: str) -> None:
    at.chat_input[0].set_value(msg)
    at.run()
    at.run()   # 本地处理分支里有 st.rerun()，再 run 一次消费最终渲染


def pick_job(at, code: str) -> None:
    """切岗（2026-09-22 修）：**必须设 selectbox 的值**，只设 `session_state` 不够。

    实测：侧栏 selectbox 带 `index=`（`load_last_job()` 指向上次在看的岗）——当 index 指到的岗
    不是 `session_state` 里那个时，AppTest 渲染的是 **index 那个岗**的页面（而 `session_state`
    里仍显示我们设的值）⇒ 之前 9 处"设 session_state 再 run"只是**碰巧**对（当时 index 恰好=0）。
    本次新增 fixture 改变了选项集合 → 最后一条断言红了，才发现。
    """
    at.session_state["job_pick_chat"] = code
    at.run()
    at.selectbox(key="job_pick_chat").set_value(code)
    at.run()


def main() -> None:
    from streamlit.testing.v1 import AppTest

    try:
        # 四个岗：待拍板 / 已拍板做 / 已拍板不做 / 旧岗(无 decision)；另一个岗带 collected 产物
        make_job("J-PEND-001", "待拍板岗", {"decision": "pending"})
        make_job("J-ACC-001", "已拍板做岗", {"decision": "accept"})
        make_job("J-DECL-001", "已拒岗", {"decision": "decline"})
        make_job("J-OLD-001", "旧岗", {})   # 2026-09-22：形状 = 分析过 + 无决策记录（下方断言已改对）
        # 2026-09-22：老 fixture「J-OLD-001」= **分析过 + 无决策记录**（= 09-21 那个真岗的形状：
        #   state 说分析完了，但没有 analyze 产物、也没有 decision）→ 推导 pending、②锁。
        #   （原本这里还想再建一个"有产物+无决策"的岗，与它形状重复，故不建——省一次 AppTest 折腾。）
        make_job("J-ACC-ANALYZED-001", "分析+已拍板岗", {"decision": "accept"},
                 files=("analyze_20260922-000000.json",))
        make_job("J-COL-001", "已采集岗", {"decision": "accept",
                                          "step2_collected": True},
                 files=("collected_20260916-090000.json",))
        # v1.9.1：另建一个"已有采集计划"的岗，用来验「按计划跑」→ collect_run
        make_job("J-PLAN-001", "有计划岗", {"decision": "accept"},
                 files=("collect_plan_20260916-090500.json",))
        _PLANNED = "J-PLAN-001"
        # v1.11.0 认账口径：新形态轨迹（collect_*.json）算采过；只有计划不算；只有 job.db 也算
        make_job("J-NEW-001", "新形态采集岗", {"decision": "accept"},
                 files=("collect_20260916-170833.json",))
        make_job("J-DBONLY-001", "只有库的岗", {"decision": "accept"})
        _con = job_db.open_db("J-DBONLY-001", path=tmp_root / "J-DBONLY-001" / "job.db")
        job_db.upsert_candidate(_con, "J-DBONLY-001", {"source_id": "rid_db_1", "name": "库里的汪**"})
        _con.close()

        assert m3_chat._EXEC_WIRED is True, "v1.9.1 执行器已接线；若关回去请把本套件一起改"

        at = AppTest.from_file(str(WORKSPACE / "m3_chat.py"), default_timeout=60)
        pick_job(at, "J-PEND-001")
        at.run()
        check("启动无异常（pending 岗）", not at.exception,
              str([e.value for e in at.exception]) if at.exception else "")
        bl = at.button(key="act_collect").label
        check("②按钮已改名（标签含「正式采集」）", "正式采集" in bl, bl)
        check("②按钮标签是「② 正式采集」", bl == "② 正式采集", bl)
        # v1.11.0：②按钮 = **真跑**（不再是"先出计划"）——help 必须讲清新口径
        _bh = str(at.button(key="act_collect").help)
        check("②按钮 help 讲清「点它就是真跑」", "点它就是真跑" in _bh, _bh[:120])
        check("②按钮 help 说明**没计划也能跑**（一回合内自定计划+留档+直接跑）",
              ("还没有计划" in _bh) and ("一个回合内" in _bh) and ("直接开跑" in _bh), _bh[-160:])
        check("②按钮 help 说明**开工前体检**（没过拒绝开跑）",
              ("开工前体检" in _bh) and ("拒绝开跑" in _bh), _bh[-160:])
        check("旧名「探索采集」不再出现在按钮上", "探索采集" not in bl, bl)
        check("pending 岗 ②按钮灰着", at.button(key="act_collect").disabled, "")

        # v1.12.0 顺序：执行行 = 📋出采集计划 → ②正式采集 → 💬打招呼报告
        prog = texts(at)
        _i = (prog.find("正式采集"), prog.find("打招呼报告"))
        check("进度行顺序：②正式采集 → 💬打招呼报告",
              all(x >= 0 for x in _i) and _i == tuple(sorted(_i)), str(_i))
        check("进度条列出「② 正式采集」这一步", "正式采集" in prog, prog[:160])
        check("进度行**不再**出现「搜索体检」（子步骤已取消）", "搜索体检" not in prog, prog[:200])
        labels = "｜".join(b.label for b in at.button)
        _j = (labels.find("出采集计划"), labels.find("正式采集"), labels.find("打招呼报告"))
        check("按钮行顺序：出计划 → 正式采集 → 💬打招呼报告",
              all(x >= 0 for x in _j) and _j == tuple(sorted(_j)), str(_j))

        # v1.11.0：体检按钮**摘掉**（老板拍板取消该子步骤，能力已并进采集）；
        # 打招呼 / 入库 / 出计划 / 正式采集 四个按钮必须在（重排不许丢功能）
        check("「🔎 搜索体检」按钮**已摘掉**（子步骤取消，脚本仍在）",
              not any(b.key == "act_probe" for b in at.button), "")
        for k in ("act_collect_plan", "act_collect", "act_greet_report"):
            check(f"按钮仍在：{k}", any(b.key == k for b in at.button), "")
        # v1.12.0：三个按钮**摘掉**（③池子评估取消；旧打招呼清单被打招呼报告取代；入库当前岗已失效）
        for k in ("act_eval", "act_greet", "act_import_db"):
            check(f"按钮已摘掉：{k}", not any(b.key == k for b in at.button), "")
        check("出计划按钮标签是「📋 出采集计划」（该岗还没有计划）",
              at.button(key="act_collect_plan").label == "📋 出采集计划",
              at.button(key="act_collect_plan").label)

        # 解锁逻辑没被改坏：该岗没有采集产物 → 灰
        check("💬打招呼报告：②还没采集 → 灰", at.button(key="act_greet_report").disabled, "")

        # v1.9.1 接线下：pending 岗说「去猎聘跑一轮」→ 走 ②出计划（agent 拿到的必须是**出计划任务书**）
        before = len(m3_chat.load_transcript("J-PEND-001"))
        send(at, "去猎聘跑一轮")
        tr = m3_chat.load_transcript("J-PEND-001")
        body = " ".join(m.get("content", "") for m in tr)
        check("说「去猎聘跑一轮」→ 对话变长", len(tr) > before, f"{before}→{len(tr)}")
        check("接线下走的是【②正式采集·第一步：出计划】任务书",
              "步骤② 正式采集·第一步" in body, body[-200:])
        _plan_txt = m3_chat.build_step2_plan_task({"job_code": "J-PEND-001", "title": "t"})
        # 🔴 v1.10.0（2026-09-16）：**翻页已自动、关键字也由脚本自己搜** →
        #    任务书里**不许**再出现"翻页要老板人工点"这种过期口径（小猎会照抄进计划）。
        check("出计划任务书**不再**说「翻页要人工」（已自动）",
              "翻页要老板人工点" not in _plan_txt, "")
        check("出计划任务书说明**不需要老板先搜/不需要人工翻页**",
              ("不需要老板人工搜关键字" in _plan_txt) and ("也不需要人工翻页" in _plan_txt), "")
        check("出计划任务书标明执行链路已全自动接通（v1.10.0）",
              ("全自动接通" in _plan_txt) and ("v1.10.0" in _plan_txt), "")
        check("出计划任务书带**死命令**（不设人为额度）",
              "不设人为额度" in _plan_txt, "")
        # 🔴 v1.10.0：**执行任务书**才是小猎真正照抄去跑的命令 —— 必须已经不再手加额度上限
        _run_txt = m3_chat.build_step2_run_task(
            {"job_code": "J-PEND-001", "title": "t"},
            Path("data/chat/J-PEND-001/reports/fake_plan.json"))
        _cmd = next((ln for ln in _run_txt.splitlines() if "collect_exec.py" in ln), "")
        check("执行任务书：命令行**不再**手加 --details / --max-pages（死命令）",
              ("collect_exec.py" in _cmd) and ("--details" not in _cmd) and ("--max-pages" not in _cmd),
              _cmd.strip())
        check("执行任务书：说明**脚本自己搜**（老板不用先搜）",
              "不需要老板先去猎聘搜一次" in _run_txt, "")
        check("执行任务书：带死命令（不设人为额度）", "不设人为额度" in _run_txt, "")
        check("执行任务书：说明搜失败会**跳过不采**（不采错页）",
              "跳过这一条不采" in _run_txt, "")
        check("执行任务书：说明**开工前体检没过就拒绝开跑**",
              ("开工前体检" in _run_txt) and ("拒绝开跑" in _run_txt), "")
        # 🔴 v1.11.0：**无计划分支** —— 「②正式采集」一次点击就真跑（不再要老板先出计划）
        _np_txt = m3_chat.build_step2_run_task({"job_code": "J-PEND-001", "title": "t"}, None)
        check("无计划分支：任务书**仍是 collect_run**（首行前缀不变）",
              m3_chat.kind_of_task(_np_txt) == "collect_run", m3_chat.kind_of_task(_np_txt))
        check("无计划分支：明确「盘上还没有采集计划 → 一回合内自定计划」",
              ("盘上还没有采集计划" in _np_txt) and ("一个回合" in _np_txt), _np_txt[:200])
        check("无计划分支：**中间不许停下来问老板**（不再要确认）",
              ("中间不许停下来问老板" in _np_txt) and ("不要老板再确认" in _np_txt), _np_txt[:400])
        check("无计划分支：仍要**写一份计划留档**（可重放）",
              ("写下来留档" in _np_txt) and ("collect_plan_" in _np_txt), "")
        _np_cmd = next((ln for ln in _np_txt.splitlines() if "collect_exec.py" in ln), "")
        check("无计划分支：命令行不带人为额度，且带 --all-keywords",
              ("collect_exec.py" in _np_cmd) and ("--all-keywords" in _np_cmd)
              and ("--details" not in _np_cmd) and ("--max-pages" not in _np_cmd), _np_cmd.strip())
        check("无计划分支：命令行里的计划路径就是它刚写的那份（同一次运行可用）",
              "collect_plan_" in _np_cmd, _np_cmd.strip())
        check("state 没被改（step2_collected 仍 False）",
              m3_chat.load_state("J-PEND-001").get("step2_collected") is False, "")
        # v1.12.0：打招呼报告任务书 —— 三条命令 + "自己定口径" + 硬纪律，缺一条小猎就会瞎干
        _gre_txt = m3_chat.build_greeting_report_task({"job_code": "J-PEND-001", "title": "t"})
        check("打招呼报告任务书：归到 greet_report（台账/工具面才对得上）",
              m3_chat.kind_of_task(_gre_txt) == "greet_report", m3_chat.kind_of_task(_gre_txt))
        for _cmd in ("status_run.py", "filter_run.py", "greeting_report.py"):
            check(f"打招呼报告任务书：要求跑 {_cmd}", _cmd in _gre_txt, "")
        check("打招呼报告任务书：明说「口径这一步归你，不要问老板」",
              "这一步归你，不要问老板" in _gre_txt, "")
        check("打招呼报告任务书：明说「规则不许写进代码」",
              "规则不许写进代码" in _gre_txt, "")
        check("打招呼报告任务书：硬纪律「话术一个字都不许改」",
              "一个字都不许改" in _gre_txt, "")
        check("打招呼报告任务书：说明打招呼仍是人工闸门",
              "人工闸门" in _gre_txt, "")
        # 对话流入口：老板原话「先生成一个打招呼的报告吧，这次宽松点」要能触发
        check("对话意图：认得出「生成一个打招呼的报告，这次宽松点」",
              m3_chat.detect_greet_report_intent(
                  "我们先生成一个打招呼的报告吧，这次弄的稍微宽松吧", {"job_code": _PLANNED}) is True, "")
        check("对话意图：闲聊/提问不误触发",
              m3_chat.detect_greet_report_intent("打招呼报告是什么？", {"job_code": _PLANNED}) is False, "")

        # 拍板 accept → ①解锁发岗/出计划；接线下 ②正式采集也解锁（**一次点击就真跑**）
        send(at, "做吧")
        check("拍板 accept 落盘", m3_chat.load_state("J-PEND-001").get("decision") == "accept", "")
        check("accept 后 ②正式采集**解锁**（v1.9.1 已接线）",
              not at.button(key="act_collect").disabled, "")
        check("accept 后 📋出采集计划已解锁（不是一刀切全锁）",
              not at.button(key="act_collect_plan").disabled, "")
        check("accept 后 📤发岗助手已解锁", not at.button(key="act_post_text").disabled, "")

        # 已采集岗：打招呼报告解锁（回归：这条逻辑不许被本次改动带坏）
        pick_job(at, "J-COL-001")
        at.run()
        check("已采集岗 💬打招呼报告已解锁", not at.button(key="act_greet_report").disabled, "")
        check("已采集岗 ②按钮变「🔁 再次采集」（老板原话口径）",
              at.button(key="act_collect").label == "🔁 再次采集",
              at.button(key="act_collect").label)

        # ⚠️ 2026-09-16 实测反馈修的：**盘上已有计划时按钮不许灰着**（否则"重新出计划"点不了）
        pick_job(at, _PLANNED)
        at.run()
        check("已有采集计划的岗：②按钮**可点**（可直接按它跑）",
              not at.button(key="act_collect").disabled, "")
        check("已有计划 + 还没采过：②按钮仍是「② 正式采集」",
              at.button(key="act_collect").label == "② 正式采集",
              at.button(key="act_collect").label)
        check("已有计划：②help 说明「按它跑；想改就点左边重新出计划」",
              ("按它跑" in str(at.button(key="act_collect").help)), "")
        check("已有计划：**出计划按钮**显示「🔄 重新出采集计划」",
              at.button(key="act_collect_plan").label == "🔄 重新出采集计划",
              at.button(key="act_collect_plan").label)
        check("已有计划：出计划 help 里说明'旧的不会被删'",
              "旧的不会被删" in str(at.button(key="act_collect_plan").help), "")
        # v1.11.0 认账口径（真 bug 修复）：只有 collect_plan_*.json **不算**采过
        check("认账：只有采集计划 → 仍算「没采过」（不许假成功）",
              m3_chat.load_state(_PLANNED).get("step2_collected") is False, "")
        check("认账：只有计划 → 💬打招呼报告仍灰着", at.button(key="act_greet_report").disabled, "")

        # 🔴 v1.11.0 认账口径（修的第二个真 bug）：新形态 collect_*.json / job.db 也算采过
        pick_job(at, "J-NEW-001")
        at.run()
        check("认账：有 collect_*.json（无 collected_*.json）→ step2_collected 置真",
              m3_chat.load_state("J-NEW-001").get("step2_collected") is True, "")
        check("认账：新形态岗 💬打招呼报告**已解锁**（094907 那个真 bug 的症状）",
              not at.button(key="act_greet_report").disabled, "")
        check("认账：新形态岗 ②按钮变「🔁 再次采集」",
              at.button(key="act_collect").label == "🔁 再次采集",
              at.button(key="act_collect").label)
        pick_job(at, "J-DBONLY-001")
        at.run()
        check("认账：只有 job.db（有候选人）→ 也算采过",
              m3_chat.load_state("J-DBONLY-001").get("step2_collected") is True, "")
        check("认账：只有库的岗 💬打招呼报告已解锁", not at.button(key="act_greet_report").disabled, "")

        # decline 岗：②一律灰（unconditional）
        pick_job(at, "J-DECL-001")
        at.run()
        check("decline 岗 ②正式采集灰着", at.button(key="act_collect").disabled, "")
        # ⚠️ 2026-09-22 改对了的老断言（**不是改软**，是原来那句在验一个不存在的行为）：
        #   老 fixture「J-OLD-001」= `step1_analyzed=True` + 无 decision ⇒ 就是"分析完但没决策记录"
        #   那一类（= 09-21 那个真岗的形状）⇒ 推导 pending、②锁。
        #   原来那句「②可点（兼容旧岗）」是**碰巧**过的：算式 `disabled = (not _EXEC_WIRED) or
        #   not (a1 and decision_ok)` ⇒ ② 要"分析过"才谈得上解锁；当时靠 `decision_ok` 里 `None` 兼容放行，
        #   才凑出"可点"。本次新口径取消了那个放行，这里如实钉住。
        #   ⚠️ 另有一条实测（2026-09-22，隔离目录探针）：`analyze_*.json` 不存在而 state.json 写
        #   `step1_analyzed=False` 的**真·旧岗** → load_state 得 `decision=None / step1_analyzed=False`
        #   （"只升级不降级"的老口径仍在）；但那种岗 ② 本来就灰着（**分析是前提**，与决策无关），
        #   所以"②可点"在那种形状下**不成立**——旧断言就是在验一个不存在的行为。
        pick_job(at, "J-OLD-001")
        at.run()
        check("老 fixture（分析过、无决策记录）⇒ 推导 decision='pending'",
              m3_chat.load_state("J-OLD-001").get("decision") == "pending",
              repr(m3_chat.load_state("J-OLD-001").get("decision")))
        check("老 fixture ⇒ ②正式采集**灰着**（没拍板不许采，旧兼容放行已取消）",
              at.button(key="act_collect").disabled, "")
        check("老 fixture ⇒ 进度行提示等你拍板",
              "等你拍板" in texts(at), texts(at)[:200])
        # 已拍板做：同一形状**不许被连带锁上**（推导只补空、不覆盖已有值）
        pick_job(at, "J-ACC-ANALYZED-001")
        at.run()
        check("已拍板做+有产物 ⇒ decision 仍是 accept（没被推导覆盖）",
              m3_chat.load_state("J-ACC-ANALYZED-001").get("decision") == "accept", "")
        check("已拍板做+有产物 ②正式采集**可点**", not at.button(key="act_collect").disabled, "")

        # 闸门唯一开关：重接线只需改 _EXEC_WIRED
        check("_EXEC_WIRED 是布尔且当前 True（v1.9.1 接线）",
              isinstance(m3_chat._EXEC_WIRED, bool) and m3_chat._EXEC_WIRED is True, "")
        check("detect_collect_intent 接线下认得出「去猎聘跑一轮」→ plan",
              m3_chat.detect_collect_intent("去猎聘跑一轮", {"job_code": "J-ACC-001"}) == "plan",
              repr(m3_chat.detect_collect_intent("去猎聘跑一轮", {"job_code": "J-ACC-001"})))
        check("detect_collect_intent：有计划的岗 + 确认词「按计划跑」→ run",
              m3_chat.detect_collect_intent("按计划跑", {"job_code": _PLANNED}) == "run",
              repr(m3_chat.detect_collect_intent("按计划跑", {"job_code": _PLANNED})))
        # ⚠️ 设计如此（别改回去）：**没计划**时只说"按计划跑" → 返回 ""，不乱触发。
        #    （道理：没有计划可跑，说明老板记错了/在说别的；宁可当普通对话，也不许凭空重跑一轮采集）
        check("detect_collect_intent：没计划的岗 + 只有确认词 → 空串（保守，不误触发）",
              m3_chat.detect_collect_intent("按计划跑", {"job_code": "J-PEND-001"}) == "",
              repr(m3_chat.detect_collect_intent("按计划跑", {"job_code": "J-PEND-001"})))
        check("detect_collect_intent：没计划的岗 + 采集词 → plan",
              m3_chat.detect_collect_intent("去猎聘跑一轮", {"job_code": "J-PEND-001"}) == "plan", "")
        check("行为锚：`looks_like_collect_cmd` 不含闸门（喊采集认得出来）",
              m3_chat.looks_like_collect_cmd("按计划跑") is True, "")
        # ⚠️ 这条是本次踩到的真坑：闸门自己把自己短路 —— detect_collect_intent 返回 ""，
        #    所以"他是不是在喊采集"必须用 **不含闸门** 的 looks_like_collect_cmd（否则拦不住）。
        check("looks_like_collect_cmd 不含闸门（喊采集认得出来）",
              m3_chat.looks_like_collect_cmd("去猎聘跑一轮") is True, "")
        check("looks_like_collect_cmd 对闲聊/提问不误判",
              m3_chat.looks_like_collect_cmd("这岗为什么值得做？") is False, "")
        check("looks_like_collect_cmd 对**问句**不误判（采集这岗怎么做？不是发令）",
              m3_chat.looks_like_collect_cmd("采集这岗怎么做？") is False, "")
        check("looks_like_collect_cmd 对确认词也认（按计划跑）",
              m3_chat.looks_like_collect_cmd("按计划跑") is True, "")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
