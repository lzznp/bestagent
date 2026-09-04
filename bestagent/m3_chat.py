# -*- coding: utf-8 -*-
"""M3 界面 v1.6：对话式汇报面板（DSH Web 迷你版 · 分步骤测试用）

v1.6.4 变更（2026-09-04，② 探索采集接入面板）：
1. 执行通道按任务切换 cordis：纯文件任务（①/自由对话/导出）用 CORDIS_MINIMAL，
   「② 采集执行」用 CORDIS_PWSH（带 pwsh 工具，可跑 collect_liepin.py 配方表脚本）
2. ② 探索采集 = 两步走（步骤制 + 授权确认）：
   发令（点按钮或聊天说“去猎聘跑一轮”）→ 第一步 agent 读 JD+analyze 拆关键字/条件，
   写 collect_plan_*.json 计划文件并请老板确认（不真跑、不耗额度）→ 老板确认（如“按计划跑”）
   → 第二步 agent 用 pwsh 跑 collect_liepin.py（真实猎聘采集）→ 读结果汇报命中/质量
3. 聊天意图识别：含“猎聘/采集/跑一轮/搜候选人…”→ 走 ② 两步；讨论性问句（怎么/为什么/？）不触发
4. 能力边界更新：已接入 = 文件读写 + 探索采集（配方表驱动）；未接入 = ③ 池子评估等
   —— 采集纪律：禁止自然语言驱动浏览器（教训 #2），禁止改脚本，先确认再执行

v1.6.3 变更（2026-09-04，根因修复）：
自由聊天必须走 build_free_task 注入状态卡+完整路径（此前写好未接线，agent 反复“找不到岗位文件”）

v1.6 变更（2026-09-04 老板实测后反馈，逐条落实）：
1. 去掉侧栏手动「当前测试步骤」选择器 —— 改为岗位自动进度（只读，从 state/产物推断）
2. 动作按钮行由岗位状态自动算出（贴 JD→亮「开始岗位分析」；分析完→亮 重跑/导出汇报，
   ②采集/③评估 未接入则灰色+原因），按钮 = 把固定话术代打发送；聊天框照旧自由输入
3. 每岗加 state.json 状态卡，每次发令注入提示，并硬指令「先读 jd.txt / 已有报告再开口，
   禁止向老板要已存在的信息」（不赌 SDK 会话记忆——实测每轮失忆，见 PROGRESS v1.5 记录）
4. 能力边界诚实化：提示里写明已接/未接能力（只接文件读写；采集/评估未接入），
   被要求未接入能力时必须如实说明并给替代（run_pipeline），严禁找借口或假装执行
5. 过程记录自动落：步骤按钮执行即自动要求 agent 写 HTML 过程文档（不用老板开口）；
   「导出 HTML 汇报」独立按钮按需点（读已有产物整理成汇报 HTML）

v1.5 设计基础（仍有效）：形态 = DSH Web 对话样板（输入框 + JD 上传 + 回复/日志区）；
一岗一会话；执行 = B 档真 agent（DeepSeekHarness，persona=小猎，阻塞式）；
成长数据 = data/growth/records.jsonl（原始账）+ data/prompts/rules.md（消化规则库）。

运行（PyCharm 终端，解释器 lzstudy，bestagent\\ 目录）：streamlit run m3_chat.py
界面自测（不调 API）：侧栏「运行设置」→ 假执行，或设环境变量 M3CHAT_STUB=1
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

try:  # 集中配置
    from framework_config import WORKSPACE, SESSIONS, PROMPTS
    from framework_config import DSH_ROOT, RUNTIME_BIN, CORDIS_MINIMAL, CORDIS_PWSH, REQUEST_TIMEOUT
except Exception:
    WORKSPACE = Path(__file__).resolve().parent
    SESSIONS = WORKSPACE / ".sessions"
    PROMPTS = WORKSPACE / "data" / "prompts"
    DSH_ROOT = Path(r"C:\deepseek\deepseek-harness")
    RUNTIME_BIN = WORKSPACE / ".dsh-staging" / "node_modules" / "@deepseek-ai" / \
        "dsh-sdk-jsonrpc-demo" / "lib" / "packaged-bin.js"
    CORDIS_MINIMAL = DSH_ROOT / "examples" / "jsonrpc-agent" / "minimal.cordis.yml"
    CORDIS_PWSH = WORKSPACE / "minimal-pwsh-nonpty.cordis.yml"
    REQUEST_TIMEOUT = 1200

CHAT_DIR = WORKSPACE / "data" / "chat"
GROWTH_DIR = WORKSPACE / "data" / "growth"
RECORDS = GROWTH_DIR / "records.jsonl"
RULES = PROMPTS / "rules.md"
DEFAULT_ENV = WORKSPACE.parent / "参考代码" / "lietou-agent" / "browser-agent" / ".env"

# 步骤清单（业务汇报断点；0=自由讨论，仅用于纠错记录时标注）
STEPS = [
    {"no": 1, "name": "岗位分析", "tag": "读JD→接单判断→拆搜索条件→探索采集→池子初判→做/放弃"},
    {"no": 2, "name": "采集", "tag": "转关键字→配方表采集→去重"},
    {"no": 3, "name": "池子评估", "tag": "池子评级+逐人评分→推荐清单"},
    {"no": 4, "name": "汇报", "tag": "过程记录/HTML 汇报→老板审阅"},
    {"no": 0, "name": "自由讨论", "tag": "不限定步骤：讨论/追问/纠错/别的"},
]
STEP_NAME = {s["no"]: s["name"] for s in STEPS}

# 当前已接/未接能力（诚实边界，每次发令都提醒 agent）
CAPABILITIES = (
    "【能力边界·必须诚实】本会话当前：已接入 = ①文件读写（读 JD/手册/报告、写 JSON 报告与 HTML 过程文档）"
    "＋②探索采集（真实猎聘，走配方表脚本 collect_liepin.py，由 pwsh 工具执行；采集前必须先向老板展示"
    "关键字/条件并获确认，老板已明确说\"直接跑/按计划\"除外）；"
    "未接入 = ③ 候选人池评估/逐人评分、外部搜索、打招呼、浏览器自由操作等任何其他对外动作。"
    "老板要求未接入能力时，必须如实说明「这一步我还没接 XX 能力」，并给替代建议"
    "（例如：池子评估可让老板在 PyCharm 用 run_pipeline 后台跑，结果文件会出现在工作目录），"
    "严禁找其他借口、严禁假装执行。"
)

PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（一位猎头顾问）跑岗前分析、"
    "转搜索关键字、写报告、做汇报。做事原则：先思考再动手；信息不足时明确提问；"
    "输出务必严格按方法论手册的格式，不擅自改动；涉及性别/年龄/婚育等违法歧视要求要提示并忽略；"
    "干完活主动向老板汇报（“老板，我弄的咋样？”的口吻）。"
    "老板在界面上用聊天跟你对话：一条岗位=一个会话。岗位上下文一律以文件为准："
    "开口/动手前先读该岗的 jd.txt 与已有报告，禁止向老板索要已经存在的信息。"
    "当老板要求执行某步骤时，把工作过程写成中文 HTML 过程文档保存到该岗 reports 目录，"
    "方便老板事后查看（他不想盯着屏幕）。"
    "【工具纪律·务必遵守】本环境 bash 工具不可用（Windows），读文件/列目录/写文件"
    "一律用文件工具（fs/str_replace_editor）；只有【② 采集执行】时用 pwsh 工具运行 collect_liepin.py "
    "（Windows 下可用，每次调用是新进程）。岗位文件的完整绝对路径会**在每条消息里直接给出**："
    "直接用文件工具读该路径即可，**禁止去列目录/遍历磁盘找文件**（Windows 下列盘根目录会因"
    "DumpStack 等系统占用文件报错，这是正常现象，不代表文件不存在）。"
    "若文件工具已成功返回内容，就正常使用，不得声称“文件读不到/目录没挂载/被锁住”；"
    "只有按给定路径读取真实报错时才可请老板协助，且必须把报错原文贴给老板，禁止臆测原因。"
    "【② 采集纪律·务必遵守】采集=在真实猎聘上搜索（耗当日限速额度），禁止用自然语言让浏览器"
    "自己操作猎聘页面（条件会设不上），**只准用 pwsh 运行配方表脚本 collect_liepin.py**；"
    "采集前先读 analyze 报告取 search_keywords、按 JD 硬性条件给 --conds 建议，把计划写进 "
    "collect_plan_*.json 并请老板确认后才执行；执行完如实汇报命中条数/质量，不许粉饰，报错贴原文。"
)

# ═══════════════════════ 纯数据层 ═══════════════════════

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def job_dir(job_code: str) -> Path:
    return CHAT_DIR / job_code


def list_jobs() -> list[dict]:
    jobs = []
    if CHAT_DIR.exists():
        for d in sorted(CHAT_DIR.iterdir()):
            if not d.is_dir():
                continue
            meta = {}
            mp = d / "meta.json"
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            jobs.append({"job_code": meta.get("job_code", d.name),
                         "title": meta.get("title", ""),
                         "created_at": meta.get("created_at", ""),
                         "session_id": meta.get("session_id", f"m3chat-{d.name}"),
                         "dir": d})
    jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return jobs


def create_job(title: str = "", jd_text: str = "", jd_bytes: bytes | None = None) -> dict:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_code = f"J-CHAT-{ts}"
    d = job_dir(job_code)
    d.mkdir(parents=True, exist_ok=True)
    (d / "reports").mkdir(exist_ok=True)
    meta = {"job_code": job_code, "title": title or f"岗位 {job_code}",
            "created_at": now_str(), "session_id": f"m3chat-{job_code}"}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if jd_bytes is not None:
        (d / "jd.txt").write_bytes(jd_bytes)
    else:
        (d / "jd.txt").write_text(jd_text or "", encoding="utf-8")
    (d / "transcript.json").write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    save_state(job_code, jd_provided=bool(jd_bytes is not None or jd_text.strip()),
               step1_analyzed=False, last_action="新建岗位", job_title=meta["title"])
    return meta


def load_transcript(job_code: str) -> list[dict]:
    p = job_dir(job_code) / "transcript.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def append_msg(job_code: str, role: str, content: str, artifacts: list[str] | None = None) -> None:
    p = job_dir(job_code) / "transcript.json"
    msgs = load_transcript(job_code)
    msgs.append({"role": role, "content": content, "ts": now_str(),
                 "artifacts": artifacts or []})
    p.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")


def list_artifacts(job_code: str) -> list[Path]:
    d = job_dir(job_code) / "reports"
    if not d.exists():
        return []
    files = [p for p in d.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _job_dir(job: dict) -> Path:
    d = job.get("dir")
    return Path(d) if d else job_dir(job["job_code"])


# ── 岗位状态卡 state.json（不赌 SDK 会话记忆；每次发令注入提示）──

def load_state(job_code: str) -> dict:
    p = job_dir(job_code) / "state.json"
    st_def = {"job_code": job_code, "jd_provided": False, "step1_analyzed": False,
              "step2_collected": False, "last_action": None, "updated_at": None}
    if p.exists():
        try:
            st_def.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    # 兼容旧岗位（无 state.json）：从文件反推
    jd_p = job_dir(job_code) / "jd.txt"
    if jd_p.exists() and jd_p.stat().st_size > 0:
        st_def["jd_provided"] = True
    if any(p.name.startswith("analyze_") for p in list_artifacts(job_code)):
        st_def["step1_analyzed"] = True
    if any(p.name.startswith("collected_") for p in list_artifacts(job_code)):
        st_def["step2_collected"] = True
    return st_def


def save_state(job_code: str, **updates) -> None:
    st_ = load_state(job_code)
    st_.update(updates)
    st_["updated_at"] = now_str()
    (job_dir(job_code) / "state.json").write_text(
        json.dumps(st_, ensure_ascii=False, indent=2), encoding="utf-8")


def state_block(job: dict) -> str:
    """状态卡文本：注入每条 prompt，让 agent 无论有没有会话记忆都掌握岗位现状。"""
    st_ = load_state(job["job_code"])
    jd_p = _job_dir(job) / "jd.txt"
    arts = list_artifacts(job["job_code"])
    jd_status = "已提供" if (st_.get("jd_provided") and jd_p.exists()) else "为空/未提供"
    return (
        f"【岗位状态卡】{job.get('title','')}（{job['job_code']}）\n"
        f"- 岗位 JD 文件：{jd_p.as_posix()}（{jd_status}。已提供则开口前必须先读它）\n"
        f"- ① 岗前分析：{'已完成' if st_.get('step1_analyzed') else '未做'}"
        f"（最近一次动作：{st_.get('last_action') or '无'}）\n"
        f"- 现有产物 {len(arts)} 个（如需参考请读 reports 目录，最新的在前）\n"
        f"- 成长规则库：{RULES.as_posix()}（执行业务步骤前先读对应小节并遵守）\n"
    )


# ── 成长账（records.jsonl + rules.md）──────────────────────────────

def append_record(job: dict, step_no: int, note: str, tags: str = "") -> dict:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now_str(), "job_code": job["job_code"], "job_title": job.get("title", ""),
           "step": step_no, "step_name": STEP_NAME.get(step_no, str(step_no)),
           "note": note.strip(), "tags": [t.strip() for t in tags.split(",") if t.strip()],
           "status": "待消化"}
    with RECORDS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def list_records(job_code: str | None = None, pending_only: bool = False) -> list[dict]:
    if not RECORDS.exists():
        return []
    out = []
    for line in RECORDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if job_code and r.get("job_code") != job_code:
            continue
        if pending_only and r.get("status") != "待消化":
            continue
        out.append(r)
    return out


def mark_records_digested(job_code: str) -> int:
    if not RECORDS.exists():
        return 0
    lines = RECORDS.read_text(encoding="utf-8").splitlines()
    n = 0
    with RECORDS.open("w", encoding="utf-8") as f:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                f.write(line + "\n")
                continue
            if r.get("job_code") == job_code and r.get("status") == "待消化":
                r["status"] = "已消化"
                r["digested_at"] = now_str()
                n += 1
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return n


def ensure_rules() -> None:
    if RULES.exists():
        return
    PROMPTS.mkdir(parents=True, exist_ok=True)
    RULES.write_text(
        "# 成长规则库（小猎的方法论纠错沉淀）\n\n"
        "> 来源：老板与助理分步骤测试时的纠错 → 消化成规则。每条一句话：\n"
        "> 当〔情境〕时，应〔怎么做〕（来源：成长账 ts / 岗位）\n"
        "> 小猎执行涉及步骤前应阅读本文件对应小节并遵守。\n\n"
        "## ① 岗位分析\n（暂无）\n\n"
        "## ② 采集\n（暂无）\n\n"
        "## ③ 池子评估\n（暂无）\n\n"
        "## ④ 汇报 / HTML 过程文档\n（暂无）\n\n"
        "## 流程 / 工具\n（暂无）\n",
        encoding="utf-8",
    )


# ═══════════════════════ 任务构建（发令内容）══════════════════════

def build_free_task(job: dict, user_msg: str) -> str:
    """自由讨论/追问：注入状态卡 + 能力边界 + 完整路径，先读文件再开口（禁 bash、禁列盘、读不到不许编）。

    ⚠️ 2026-09-04 v1.6.2 修复：此前本函数写好却未接线，自由聊天把老板原始消息直接发给 agent，
    persona 承诺“路径每条消息都给”是假的 → agent 反复列盘找 jd.txt → “找不到岗位文件”。
    现由 render_main 对每条自由消息调用本函数，路径逐条写死。
    """
    jd_p = _job_dir(job) / "jd.txt"
    reports_dir = (_job_dir(job) / "reports").as_posix()
    latest = next((a for a in list_artifacts(job["job_code"])
                   if a.name.startswith("analyze_") and a.suffix == ".json"), None)
    analyze_hint = (latest.as_posix() if latest
                    else f"{reports_dir}（当前没有 analyze_*.json，就如实说岗前分析还没做，不用去找别的）")
    return (
        f"{state_block(job)}\n{CAPABILITIES}\n"
        "【必须先读再答】你要读的文件完整绝对路径已在上方状态卡和下面 1) 2) 里**逐条写死**——"
        "**直接用文件工具读那个路径**，不要列目录、不要遍历磁盘、不要探测或猜测任何其他路径"
        "（Windows 下列盘根目录会因系统占用文件报错，属正常现象，不代表文件不存在）。\n"
        "回答任何关于本岗的问题前，用**文件工具**（禁止用 bash/命令行）读：\n"
        f"  1) {jd_p.as_posix()}（JD，非空则不许要求老板粘贴）\n"
        f"  2) {analyze_hint}\n"
        "读完再作答，并可以引用文件内容。文件工具真实报错时，把报错原文原样贴给老板并说明读不了哪一步；"
        "只要文件工具成功返回过内容，就不得声称“读不到/目录没挂载/被锁”。\n"
        f"【老板消息】{user_msg}\n"
        "请以「小猎」身份回复。若老板要求执行某一步骤并出 HTML 过程文档，把工作过程写成中文 HTML "
        "保存到该岗 reports 目录（文件名自定，带上步骤与时间），回复里给出文件路径。"
    )


def build_step1_task(job: dict) -> str:
    """步骤① 岗前分析（含关键字实验 + HTML 过程文档）——v1.5/v1.6 唯一已接入的执行步骤。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_json = f"{reports_dir}/analyze_{ts}.json"
    report_html = f"{reports_dir}/analyze_{ts}_过程.html"
    method = (PROMPTS / "analyze_job.txt").as_posix()
    rules_hint = (f"先读成长规则库 {RULES.as_posix()}，遵守其中「① 岗位分析」及流程小节的相关规则。\n"
                  ) if RULES.exists() else ""
    return f"""老板要你执行【步骤① 岗前分析】。请全程用文件工具完成：
1. 【必须】先读岗位 JD 文件：{jd}
   —— 只要该文件非空，就不许向老板索要 JD 或要求他粘贴；JD 为空才提示老板提供。
2. 读你的岗前分析方法论手册（严格按它的 JSON 输出格式，不增不减字段）：{method}
3. 按手册完成岗前分析：提取岗位信息、判断进展、逐项评分（佣金/HC数量/新鲜度/上游靠谱度/匹配难度 各0-5）、
   算总分与等级、写清风险清单与建议、判定「接单/沟通/放弃」，并生成 4 组猎聘搜索关键字。
4. {rules_hint}
5. 把完整 JSON 结果写入：{report_json}
6. 把本次工作过程写成中文 HTML 过程文档（读了什么、关键判断、逐项评分依据、关键字实验过程、结论与风险），
   保存到：{report_html}
7. 最后用「老板，我弄的咋样？」口吻给我一段 ≤8 句的中文汇报：干了什么、这份 JD 值不值得接、
   我的建议、下一步。回复里给出上面两个文件的路径。
{CAPABILITIES}"""


def build_report_task(job: dict) -> str:
    """按需「导出 HTML 汇报」：读该岗已有产物，整理成一份给人看的汇报 HTML。"""
    reports_dir = (_job_dir(job) / "reports").as_posix()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = f"{reports_dir}/汇报_{ts}.html"
    return f"""老板要一份该岗的【HTML 汇报】（给人看，不是过程流水）。
1. 先读该岗 reports 目录里最新的 analyze_*.json（岗前分析结果）；如没有就如实说还没做分析。
2. 整理成一份干净的中文 HTML（岗位概况/总分评级/接单判断/风险要点/4 组搜索关键字/下一步建议），
   适合直接发 PM 或存档。
3. 保存到：{out}
4. 用「老板，汇报好了」口吻给我 ≤5 句摘要，附文件路径。
{CAPABILITIES}"""


# ── 步骤② 探索采集（两步走：先出计划请确认 → 确认后用 pwsh 跑配方表采集）──

COLLECT_WORDS = ("猎聘", "采集", "搜候选人", "搜一轮", "跑一轮", "搜人", "捞人", "搜索")
COLLECT_CONFIRM_WORDS = ("按计划", "直接跑", "执行采集", "开始采集", "确认跑", "按这个跑")


def latest_report(job: dict, prefix: str, suffix: str = ".json") -> Path | None:
    """reports 目录里最新一个 prefix 开头、suffix 结尾的文件（list_artifacts 已按 mtime 降序）。"""
    for a in list_artifacts(job["job_code"]):
        if a.name.startswith(prefix) and a.suffix == suffix:
            return a
    return None


def latest_collect_plan(job: dict) -> Path | None:
    return latest_report(job, "collect_plan_", ".json")


def detect_collect_intent(msg: str, job: dict) -> str:
    """识别②采集发令。返回 "plan"（发令，先出计划）/ "run"（老板确认计划，执行）/ ""（普通对话）。

    保守规则：讨论/提问（含“怎么/为什么/？”）不触发；执行必须有已落盘的 collect_plan_*.json，
    且老板消息带采集词或明确确认词——避免“确认”二字误触其它话题。
    """
    m = msg.strip()
    has_collect_word = any(w in m for w in COLLECT_WORDS)
    has_confirm_word = any(w in m for w in COLLECT_CONFIRM_WORDS)
    is_question = ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
                   or m.endswith("？") or m.endswith("?") or m.endswith("吗"))
    if has_confirm_word and latest_collect_plan(job) is not None and not is_question:
        return "run"
    if has_collect_word and not is_question:
        return "plan"
    return ""


def build_step2_plan_task(job: dict) -> str:
    """② 探索采集·第一步：读 JD + analyze → 拆关键字/条件 → 写计划文件 → 请老板确认（不真跑）。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    analyze = latest_report(job, "analyze_", ".json")
    analyze_hint = analyze.as_posix() if analyze else f"{reports_dir}（暂无 analyze_*.json——还没做①岗前分析）"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan_file = f"{reports_dir}/collect_plan_{ts}.json"
    method = (PROMPTS / "analyze_job.txt").as_posix()
    return f"""老板要你执行【步骤② 探索采集·第一步：出计划】。请全程用文件工具完成，**这一步不真跑采集、不耗额度**：
1. 读岗位 JD：{jd}
2. 读最新岗前分析报告：{analyze_hint}
   —— 从报告的 search_keywords 里挑 2~4 个最可能命中目标候选人的关键字（参考其精确/职能/竞品/技能分组；
   若报告没有关键字，按方法论 {method} 的思路从 JD 拆）。
3. 按 JD 硬性条件给出猎聘筛选条件建议（配方组 group_id=value，可空，如 education=博士/博士后、
   city_current=杭州、years=应届生…；注意：院校 C9/QS50 猎聘筛不掉，年限对资深岗可能无对应选项，别硬凑）。
4. 把计划写成 JSON 文件：{plan_file}
   格式：{{"keywords": [关键字...], "conds": ["group_id=value"...], "reasons": "为何这样选（2~3 句）",
          "note": "口径提醒（如年限矛盾先核实）", "created_at": "..."}}
5. 用「老板，采集计划好了」口吻回复 ≤6 句：列出关键字与条件、为什么这样选、预估代价
   （每个关键字=1 次猎聘搜索，今日额度有限）、以及**请老板确认**（老板回复“按计划跑/直接跑”才会执行）。
{CAPABILITIES}"""


def build_step2_run_task(job: dict, plan_file: Path) -> str:
    """② 探索采集·第二步：老板已确认 → 读计划 → 用 pwsh 跑 collect_liepin.py → 读结果汇报。"""
    plan_abs = plan_file.as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = f"{reports_dir}/collected_{ts}.json"
    py = sys.executable.replace("\\", "/")  # 面板自身解释器（lzstudy），换机器自动跟随
    return f"""老板已确认【步骤② 探索采集】计划。请执行真实采集（会耗当日猎聘搜索额度）：
1. 先用文件工具读计划文件：{plan_abs}
   —— 取它的 keywords 与 conds；若读不到该文件，如实说明并请老板重新发令（“去猎聘跑一轮”）。
2. 用 **pwsh 工具**（不是 bash）在当前工作目录（bestagent，collect_liepin.py 所在目录）运行采集脚本，
   每个关键字一个 --keyword、每个条件一个 --conds，输出到本岗 reports：
   {py} collect_liepin.py --keyword "关键字1" --keyword "关键字2" --conds city_current=杭州 --out "{out_file}"
   —— 命令里的关键字/条件必须来自计划文件；条件没有就不加 --conds。
   —— 脚本会自动发现猎聘 tab、逐个关键字导航+清空条件+配方表执行+提取、合并去重、限额与延迟。
3. 命令跑完后，用文件工具读结果：{out_file}
   格式 {{"keywords":..., "conds":..., "count": 去重后总人数, "rows": [...]}}。
4. 如实汇报（≤8 句）：每个关键字命中情况、去重后总人数、相关性初判（哪些像目标候选人，点名 top 几位）、
   是否建议补关键字/加条件（如命中差）——**不要自动重跑**，等老板指示；报错就把报错原文贴给老板。
5. 回复里给出结果文件路径。
{CAPABILITIES}"""


# ═══════════════════════ 执行通道 ═══════════════════════

def _env_from_file(env_path: Path) -> dict:
    env: dict[str, str] = {}
    if env_path and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL") and v.strip():
                env[k] = v.strip().strip('"').strip("'")
    return env


def run_assistant(job: dict, prompt: str, env_path: Path, stub: bool = False,
                  max_tokens: int = 8192, cordis: Path | None = None) -> tuple[str, list[Path]]:
    """跑一次真 agent（阻塞式）。cordis 按任务切换：默认纯文件（CORDIS_MINIMAL）；
    「② 采集执行」传 CORDIS_PWSH（带 pwsh 工具跑配方表脚本）。"""
    if stub:
        time.sleep(0.2)
        return (f"（假执行·界面自测）收到指令：{prompt[:60]}…\n"
                "正式使用时请把执行模式切回「真执行」并配置 .env。"), []
    sys.path.insert(0, str(DSH_ROOT / "python" / "sdk" / "src"))
    sys.path.insert(0, str(DSH_ROOT / "python" / "sdk-runtime" / "src"))
    from deepseek_harness import DeepSeekHarness  # noqa: E402

    env = _env_from_file(env_path)
    if "DEEPSEEK_API_KEY" not in env:
        raise RuntimeError("没有找到 DEEPSEEK_API_KEY：请检查侧栏「运行设置」里的 .env 路径")
    env["DSH_SYSTEM_PROMPT"] = PERSONA

    reports_dir = _job_dir(job) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in reports_dir.iterdir()}

    with DeepSeekHarness(
        provider="deepseek-official",
        model="deepseek-v4-flash",
        max_tokens=max_tokens,
        cwd=str(WORKSPACE),
        session_root=str(SESSIONS),
        cordis=str(cordis or CORDIS_MINIMAL),
        launch_args_override=("node", str(RUNTIME_BIN)),
        env=env,
        request_timeout_seconds=REQUEST_TIMEOUT,
        shutdown_timeout_seconds=10,
    ) as harness:
        result = harness.run(prompt, session_id=job["session_id"])

    reply = (getattr(result, "final_response", "") or "").strip()
    after = {p.name for p in reports_dir.iterdir()}
    new_files = [reports_dir / n for n in sorted(after - before)]
    new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return reply, new_files


# ═══════════════════════ UI ═══════════════════════

def render_sidebar() -> dict:
    with st.sidebar:
        st.markdown("## 🎯 岗位会话")
        jobs = list_jobs()
        options = [j["job_code"] for j in jobs]
        labels = {j["job_code"]: (j["title"] or j["job_code"]) + f"　{j['job_code']}" for j in jobs}
        if not options:
            st.caption("还没有岗位会话，先在下面新建一个。")
        else:
            pick = st.selectbox("当前岗位（=一条对话线程）", options,
                                format_func=lambda c: labels[c], key="job_pick_chat")
        with st.expander("➕ 新建岗位会话", expanded=not bool(options)):
            title = st.text_input("岗位标题（可空）", key="nj_title",
                                  placeholder="如：中国移动 NLP 应届博士岗")
            jd_up = st.file_uploader("上传 JD（.txt）", type=["txt"], key="nj_up")
            jd_paste = st.text_area("或直接粘贴 JD 原文（推荐贴完整页面快照）", key="nj_paste", height=160)
            if st.button("创建并进入该岗", key="nj_btn", use_container_width=True):
                if jd_up is not None:
                    new_job = create_job(title, jd_bytes=jd_up.getvalue())
                elif jd_paste.strip():
                    new_job = create_job(title, jd_text=jd_paste)
                else:
                    new_job = create_job(title)
                st.session_state["job_pick_chat"] = new_job["job_code"]
                st.success(f"已创建：{new_job['job_code']}")
                st.rerun()

        st.divider()
        with st.expander("⚙️ 运行设置"):
            stub = st.checkbox("假执行（界面自测，不调 API）",
                               value=os.environ.get("M3CHAT_STUB") == "1", key="stub_mode")
            env_path = st.text_input(".env 路径", value=str(DEFAULT_ENV), key="env_path")
            st.caption("真执行阻塞式：发令后耐心等待（页面右上角可 Stop）。")

        st.divider()
        with st.expander("📒 纠错成长账（原始账）"):
            st.caption(f"累计 {len(list_records())} 条 → data/growth/records.jsonl；"
                       "消化成规则写 data/prompts/rules.md，下次干活自动生效。")
            # 步骤下拉：默认按当前岗状态给建议（①分析已完成→默认①；否则自由讨论）
            cur_job_code = st.session_state.get("job_pick_chat") or (jobs[0]["job_code"] if jobs else None)
            default_no = 1
            if cur_job_code:
                stt = load_state(cur_job_code)
                default_no = 1 if stt.get("step1_analyzed") else 0
            rec_step = st.selectbox("这笔纠错属于哪一步？",
                                    [s["no"] for s in STEPS],
                                    format_func=lambda n: STEP_NAME[n],
                                    index=next(i for i, s in enumerate(STEPS) if s["no"] == default_no),
                                    key="rec_step")
            note = st.text_area("记一笔：助理哪里不对 / 应该怎样", key="rec_note", height=90)
            tags = st.text_input("主题标签（逗号分隔）", key="rec_tags",
                                 placeholder="如：评分口径,关键字选词,诚实边界")
            if st.button("✍️ 记录纠错（成长数据）", key="rec_btn", use_container_width=True):
                if not note.strip():
                    st.warning("批注为空，未记录。")
                else:
                    job = next((j for j in jobs if j["job_code"] == cur_job_code), None)
                    if job is None:
                        st.warning("请先选择岗位会话。")
                    else:
                        append_record(job, rec_step, note, tags)
                        st.success("已记入成长账（待消化）。")
                        st.rerun()
            recents = list_records()[-5:][::-1]
            if recents:
                st.markdown("**最近记录**")
                for r in recents:
                    st.caption(f"· [{r['step_name']}] {r['note'][:36]}{'…' if len(r['note']) > 36 else ''} ({r['ts'][5:16]})")

        st.divider()
        with st.expander("📖 怎么用（1 分钟）"):
            st.markdown(
                "- **建岗**：新建岗位时贴 JD（完整页面快照最稳）→ 选它进入对话\n"
                "- **干活**：点上方动作按钮（系统按岗位状态自动亮/灰）或直接打字发令\n"
                "- **看过程**：每步执行自动落 HTML 过程文档，展开「工作产物」查看，不用盯屏\n"
                "- **纠错**：侧栏记一笔 → 成长账；消化成规则后可让助理写进 rules.md\n"
                "- **能力边界**：②采集/③评估按钮未接入（灰+原因）；自由聊天里也会如实说明")

    return {"jobs": jobs, "stub": stub, "env_path": Path(env_path)}


def render_progress_line(job: dict) -> None:
    """岗位自动进度（只读，不用手动维护）。"""
    stt = load_state(job["job_code"])
    jd_ok = stt.get("jd_provided")
    a1 = stt.get("step1_analyzed")
    c2 = stt.get("step2_collected")
    jd_chip = "📥 JD 已收" if jd_ok else "📥 等 JD"
    a1_chip = "✅ ① 岗前分析完成" if a1 else "⬜ ① 岗前分析未做"
    c2_chip = "✅ ② 已采集一轮" if c2 else "② 探索采集（可点按钮发令）"
    st.markdown(f"**流程进度**：{jd_chip}　→　{a1_chip}　→　{c2_chip}　→　🔒 ③ 池子评估（未接入）")
    hint = []
    if not jd_ok:
        hint.append("先上传/粘贴 JD（新建岗位时），或直接在下方输入框把 JD 原文发来。")
    elif not a1:
        hint.append("点下方「🚀 开始岗位分析」跑第一步。")
    else:
        hint.append("①分析已出：可确认/追问/纠错，或点「重跑/导出汇报」；"
                    "②探索采集已接入：点按钮或直接说“去猎聘跑一轮”（先出计划你确认后再真跑）。")
    st.caption("　".join(hint))


def render_action_row(job: dict) -> str | None:
    """动作按钮行：由岗位状态自动亮/灰；返回要发送的任务文本（无则 None）。"""
    stt = load_state(job["job_code"])
    jd_ok = stt.get("jd_provided") and (_job_dir(job) / "jd.txt").exists()
    arts = list_artifacts(job["job_code"])

    c1, c2, c3, c4 = st.columns(4)
    task = None
    if not jd_ok:
        st.info("岗位 JD 还没就位：请先在左侧新建岗位时粘贴/上传 JD。")
        return None
    label1 = "🔄 重跑岗位分析" if stt.get("step1_analyzed") else "🚀 开始岗位分析"
    if c1.button(label1, key="act_analyze", use_container_width=True,
                 help="读 JD+方法论+成长规则 → 评分/接单判断/4组关键字 → 自动写 JSON + HTML 过程文档"):
        task = build_step1_task(job)
    if c2.button("📤 导出 HTML 汇报", key="act_report", use_container_width=True,
                 disabled=len(arts) == 0,
                 help="读已有分析产物，整理成一份给人看的 HTML 汇报（按需点）"):
        task = build_report_task(job)
    if c3.button("② 探索采集", key="act_collect", use_container_width=True,
                 disabled=not stt.get("step1_analyzed"),
                 help="已接入：第一步先出计划（关键字/条件请你确认，不耗额度）→ 你回复“按计划跑”才真跑猎聘采集"):
        task = build_step2_plan_task(job)
    if c4.button("🔒 ③ 池子评估", key="act_eval", use_container_width=True, disabled=True,
                 help="未接入：评估需要接池子数据与评估方法论，后续版本接"):
        pass
    return task


def render_main(cfg: dict) -> None:
    jobs = cfg["jobs"]
    if not jobs:
        st.info("先在左侧「➕ 新建岗位会话」创建一个岗位（粘贴/上传 JD），再开始第一步测试。")
        return
    pick = st.session_state.get("job_pick_chat") or jobs[0]["job_code"]
    job = next((j for j in jobs if j["job_code"] == pick), jobs[0])

    st.markdown(f"### 🗣 {job['title'] or job['job_code']}")
    st.caption(f"岗位 {job['job_code']} · 会话 {job['session_id']} · 创建于 {job['created_at']}")
    render_progress_line(job)

    # 产物预览
    arts = list_artifacts(job["job_code"])
    if arts:
        with st.expander(f"📄 工作产物（{len(arts)} 个，最新在前）", expanded=False):
            fname = st.selectbox("选择产物查看", [p.name for p in arts], key="art_pick")
            fpath = _job_dir(job) / "reports" / fname
            if fpath.name.endswith(".html"):
                html = fpath.read_text(encoding="utf-8", errors="replace")
                st.components.v1.html(html, height=620, scrolling=True)
            else:
                txt = fpath.read_text(encoding="utf-8", errors="replace")
                st.code(txt[:6000] + ("\n…（过长已截断）" if len(txt) > 6000 else ""),
                        language="json" if fpath.suffix == ".json" else None)

    # 对话历史
    for m in load_transcript(job["job_code"]):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            for a in m.get("artifacts") or []:
                st.caption(f"📎 {a}")

    # 动作按钮行 + 自由输入
    task = render_action_row(job)
    prompt = st.chat_input("跟小猎说话：发指令 / 追问 / 讨论；也可以直接粘贴 JD 原文…")

    def kind_of_task(t: str) -> str:
        if t.startswith("老板要你执行【步骤①"):
            return "analyze"
        if t.startswith("老板要你执行【步骤②"):
            return "collect_plan"
        if t.startswith("老板已确认【步骤②"):
            return "collect_run"
        return "report"

    to_send = None
    agent_prompt = None
    action_kind = None
    if task:
        action_kind = kind_of_task(task)
        agent_prompt = task
        to_send = task
    elif prompt:
        # 若输入疑似整段 JD 且 jd.txt 为空 → 顺手存档为岗位 JD
        if not load_state(job["job_code"]).get("jd_provided") and len(prompt) > 200 and ("职位" in prompt or "岗位" in prompt):
            (_job_dir(job) / "jd.txt").write_text(prompt, encoding="utf-8")
            save_state(job["job_code"], jd_provided=True)
        to_send = prompt
        # v1.6.3 修复：自由聊天必须走 build_free_task，注入状态卡+完整路径+能力边界+硬指令
        # （历史 bug：build_free_task 定义了没接线，agent 反复“找不到岗位文件”）
        # v1.6.4：先识别 ② 采集发令（去猎聘/采集/跑一轮…）→ 走“出计划→确认→执行”两步；讨论性问句不触发
        if load_state(job["job_code"]).get("step1_analyzed"):
            coll = detect_collect_intent(prompt, job)
        else:
            coll = ""
        if coll == "plan":
            action_kind, agent_prompt = "collect_plan", build_step2_plan_task(job)
        elif coll == "run":
            plan_f = latest_collect_plan(job)
            action_kind = "collect_run"
            agent_prompt = build_step2_run_task(job, plan_f) if plan_f else build_free_task(job, prompt)
        else:
            action_kind, agent_prompt = "chat", build_free_task(job, prompt)

    if to_send:
        append_msg(job["job_code"], "user", to_send)
        try:
            with st.status("小猎工作中（阻塞式，长任务请耐心等待）…", expanded=False) as status:
                cordis = CORDIS_PWSH if action_kind == "collect_run" else None
                reply, new_files = run_assistant(job, agent_prompt, cfg["env_path"],
                                                 stub=cfg["stub"], cordis=cordis)
                status.update(label="小猎完成", state="complete")
        except Exception as e:
            reply = f"⚠️ 执行出错：{e}\n\n（若是 .env/API 问题请检查侧栏运行设置；界面自测请开「假执行」）"
            new_files = []
        append_msg(job["job_code"], "assistant", reply,
                   artifacts=[p.name for p in new_files])
        # 更新状态卡
        label_map = {"analyze": "岗位分析", "report": "导出汇报", "chat": "自由对话",
                     "collect_plan": "②采集·出计划", "collect_run": "②采集·执行"}
        upd = {"last_action": label_map.get(action_kind, action_kind)}
        if action_kind == "analyze":
            upd["step1_analyzed"] = True
        if action_kind == "collect_run":
            upd["step2_collected"] = bool(any(p.name.startswith("collected_")
                                              for p in list_artifacts(job["job_code"])))
        save_state(job["job_code"], **upd)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="数字合伙人 · 对话汇报（v1.6.4）", page_icon="🗣", layout="wide")
    st.markdown("# 🗣 数字合伙人 · 对话式汇报")
    st.caption("v1.6.4｜ 一岗一会话｜ 状态卡自动记忆｜ 过程自动落 HTML｜ ①②已接入（分析/探索采集），③评估未接入｜ "
               "纠错成长账：`data/growth/records.jsonl` + `data/prompts/rules.md`")
    ensure_rules()
    cfg = render_sidebar()
    render_main(cfg)


if __name__ == "__main__":
    main()
