# -*- coding: utf-8 -*-
"""M3 界面 v1.6：对话式汇报面板（DSH Web 迷你版 · 分步骤测试用）

v1.7.3 变更（2026-09-07，岗位资料落盘：岗位目录 = 正式底座起步）：
1. 岗位目录新增 job_profile.json（pm_notes 口径 / special_notes 猎头关注与客户特殊要求 / events 变动时间线），
   老板发令"记到岗位资料 / 这是 PM 的口径 / 临时需求…" → 小猎把对话里的 PM 答复/口径/关注
   分类【追加】进该文件（只追加不改历史、写完回读展示）；含歧视性要求时只作内部事实记录并提示合规边界。
2. state_block 提示岗位资料文件（后续步骤涉本岗口径可读）。

v1.7.2 变更（2026-09-07，成长沉淀补丁：教学原文注入，治"它说没看到您教的规则"）：
根因 = agent 无跨 run 记忆（项目铁律：不赌会话记忆、文档是唯一记忆），老板教的经验只存在于
transcript.json（给人看的），下一次"记到成长库"发令时是全新执行、真的看不到教学原文。
修复 = build_free_task 教学分支把本会话老板最近的非任务原话（跳过任务注入文本）注入 prompt，
让它在写入 rules.md 前先读到教学原文提炼；找不到原文必须如实报告，不许脑补。

v1.7.1 变更（2026-09-07，成长沉淀：对话里教 → 小猎自助写 rules.md）：
1. 老板在自由对话里明确发令（"记到成长库/写进 rules/记住这条/沉淀下来"等）时，
   小猎被授权把规则【追加】进 data/prompts/rules.md 对应小节（详见 CAPABILITIES「成长沉淀」段
   + build_free_task 教学分支的操作步骤）——只追加不改删、按现成格式、写完回读并展示新增内容。
2. 顺带修复 rules.md 历史结构 bug（曾有两个「② 采集」节，空骨架节与有规则节并存）。

v1.7.0 变更（2026-09-07 起，P0 交互模型改造：判断对话化·骨架）：
1. 判断环节进对话（决策 20 落地骨架）：①岗前分析完成后小猎给「态度+理由」（明确 接/先沟通/别做 三选一，
   不骑墙），并请老板拍板；老板可反驳追问（自由聊天通道照旧），然后回复 做/不做/先核实 拍板。
2. 拍板 = 本地识别落盘（不耗 API）：state.json 增 decision 字段（pending/accept/decline/clarify
   + decision_note + decision_ts）；拍板动作以确认消息留在对话里（可纠正）。
3. 按钮退「执行显示层」：②采集 / 📋发岗文字 / ③评估 的可用性由 decision 驱动——①分析完先等拍板
   （decision=pending 时锁），拍板 accept 才解锁；decline 后锁并提示改主意可说「重新判断」重跑①；
   clarify 后暂锁待核实回来再定。旧岗无 decision 字段默认不锁（兼容）。
4. 「重新判断 / 重新分析」消息 = 重跑①（decision 回 pending）。

v1.6.9 变更（2026-09-06，对话产物即点即开 + 去掉右侧报告栏）：
1. 助手消息的产物不再只是 📎 文件名文字——渲染成 文件名 + 「打开 ↗」按钮（os.startfile 本机打开，
   HTML=默认浏览器打开，可直接点页面里的候选链接 / 逐格复制），取代"只给说明文字、自己翻文件夹"。
2. 去掉右侧「本岗报告」栏（产物列表不实时更新、占右上方位置不便）→ 对话流全宽，
   每步产物以可打开链接形式留在对话里（历史消息里的旧产物同样可点）。
3. 📋 生成发岗文字 完成后在对话里追加一条带打开按钮的消息（不再只是页面上一条说明文字）。

v1.6.7 变更（2026-09-05，报告栏 + 打招呼清单）：
1. 💬 生成打招呼清单（③评估后）：入围者(推荐/待定,≤15 按分排序)每人 匹配点2/先核实2/话术1(岗位亮点)/话术2(匹配理由)
   + 猎聘直达链接(<a target=_blank>) → reports/打招呼清单_*.md；老板照单点链接复制话术人工打招呼
2. 右侧报告栏：主区双栏（左对话流 3 / 右本岗报告 2），产物按步骤分组列示、点开即预览
   （HTML 内嵌 / Markdown 渲染(链接可点) / JSON 代码），打招呼清单默认展开
3. 布局目标：所有步骤都以报告收尾——"点报告干活"（据清单逐一联系候选人）

v1.6.6 变更（2026-09-04，决策入库 + 发岗文字）：
动作区第二行：📋 生成发岗文字（agent 读 JD+① → 猎聘发布文案落 reports，发布动作人工）/
📥 入库当前岗（本地调 import_chat_job.import_job，把该岗①-③产物幂等写入 business.db：
jobs UPSERT + 候选人去重 + 评估 replace，job_code=目录名对齐，重复点只刷新不新增）。

v1.6.5 变更（2026-09-04，③ 池子评估接入面板）：
③ 按钮按 ②采集完成点亮 / 聊天“评估一下这批人”类发令自动路由；agent 读 JD+最新 collected 池子
+pool_quality/match_candidate 方法论 → 池评（优/良/中/差+分布+data_valid）→ 逐人紧凑评分
（score/verdict/summary，≥60 加 match_points/concerns）→ 写 pool_report_*.json + HTML 过程 → 汇报 top；
纯文件任务走 CORDIS_MINIMAL，max_tokens 提至 32768；state 新增 step3_done（按 pool_report 推断）。

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

CHAT_DIR = (Path(os.environ["M3CHAT_CHAT_DIR"]) if os.environ.get("M3CHAT_CHAT_DIR")
            else WORKSPACE / "data" / "chat")  # 环境变量覆盖：AppTest/多实例隔离用
GROWTH_DIR = WORKSPACE / "data" / "growth"
RECORDS = GROWTH_DIR / "records.jsonl"
RULES = PROMPTS / "rules.md"
DEFAULT_ENV = WORKSPACE.parent / "参考代码" / "lietou-agent" / "browser-agent" / ".env"

# v1.7.1 成长沉淀：老板"教规则并让记进成长库"的触发词（build_free_task 检测后给写入指引）
TEACH_WORDS = ("记到成长库", "记进成长库", "写进规则", "写入规则", "记住这条", "记下来",
               "沉淀下来", "成长库", "教给你", "写进你的成长库", "记到 rules", "写进 rules")

# v1.7.3 岗位资料：老板把 PM 口径/临时需求/猎头关注"记到岗位资料"的触发词
PROFILE_WORDS = ("记到岗位资料", "记进岗位资料", "写进岗位资料", "记到岗位档案", "岗位资料里",
                 "这是 PM 的口径", "这是 PM 说的", "PM 答复", "PM 回复", "临时需求",
                 "补充到岗位", "记到岗位信息")

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
    "关键字/条件并获确认，老板已明确说\"直接跑/按计划\"除外）"
    "＋③池子评估（读采集池子按方法论逐人评分，纯文件任务）；"
    "未接入 = 联系跟进/打招呼、外部搜索、浏览器自由操作等任何其他对外动作。"
    "【判断对话化·务必遵守】判断主通道 = 对话：老板要的是你给态度+理由、他反驳追问、然后他拍板，"
    "不是丢一份报告让他自己消化。①岗前分析完必须给明确态度（接/先沟通/别做）并请老板拍板；"
    "老板回复 做吧/不做/先核实 后岗位状态会记下该决策（accept/decline/clarify），后续步骤据此放行/锁定。"
    "判断错不罚、不诚实必罚：宁可直说判断（包括\"信息不足要先问 PM\"），不许含糊骑墙、不许粉饰、"
    "不许假装执行。"
    "【成长沉淀·授权与纪律】当老板**明确发令**要你把一条经验/规则记进成长库"
    "（如说\"记到成长库/写进 rules/记住这条/沉淀下来/教给你\"）时，你有权向成长规则库追加规则。"
    "纪律：①只在老板明确发令时写，绝不自动揣测、绝不主动改；②只允许【追加】，"
    "不许删改 rules.md 里任何已有内容；③按文件内现成格式写"
    "（`- [来源 本岗/日期] 当〔情境〕时，应〔怎么做〕`），不确定放哪节就放「流程 / 工具」；"
    "④写完必须用文件工具回读确认，并在回复里展示你新增了什么、加在哪一节。"
    "除成长规则库外，不得改写任何方法论手册（analyze_job.txt / pool_quality.txt / "
    "match_candidate.txt / publish_manual.txt）或其他文件——那些仍由老板/实施对话维护。"
    "老板要求未接入能力时，必须如实说明「这一步我还没接 XX 能力」，并给替代建议"
    "（例如：打招呼/联系候选人需走人工闸门），"
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
    "【判断对话化·务必遵守】老板要的是搭档不是工具：岗前分析后你要给明确态度（接/先沟通/别做）"
    "和理由、请他拍板，他可以反驳追问；判断错不罚、不诚实必罚——不许骑墙含糊、不许粉饰、"
    "不许假装执行，信息不足就直说要先问 PM/核实什么。"
    "老板在对话里教你业务经验/规则时，认真理解；他明确说\"记到成长库/写进 rules\"时，"
    "按纪律把规则追加进成长规则库（详见任务消息里的操作步骤，只追加不改删、写完展示）。"
    "【工具纪律·务必遵守】本环境 bash 工具不可用（Windows），读文件/列目录/写文件"
    "一律用文件工具（fs/str_replace_editor）；只有【② 采集执行】时用 pwsh 工具运行 collect_liepin.py "
    "（Windows 下可用，每次调用是新进程）。岗位文件的完整绝对路径会**在每条消息里直接给出**："
    "直接用文件工具读该路径即可，**禁止去列目录/遍历磁盘找文件**（Windows 下列盘根目录会因"
    "DumpStack 等系统占用文件报错，这是正常现象，不代表文件不存在）。"
    "若文件工具已成功返回内容，就正常使用，不得声称“文件读不到/目录没挂载/被锁住”；"
    "只有按给定路径读取真实报错时才可请老板协助，且必须把报错原文贴给老板，禁止臆测原因。"
    "【② 采集纪律·务必遵守】采集=在真实猎聘上搜索（搜索次数不设紧限，但**轮间必须保持 8-20 秒真人节奏、"
    "勿连点**；平台真正统计的风控点是“查看简历数”=打开候选人详情页的数量，列表采集不开详情页、安全），禁止用自然语言让浏览器"
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
              "step2_collected": False, "step3_done": False, "last_action": None,
              "decision": None, "decision_note": None, "decision_ts": None,
              "updated_at": None}
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
    if any(p.name.startswith("pool_report_") for p in list_artifacts(job_code)):
        st_def["step3_done"] = True
    return st_def


def save_state(job_code: str, **updates) -> None:
    st_ = load_state(job_code)
    st_.update(updates)
    st_["updated_at"] = now_str()
    (job_dir(job_code) / "state.json").write_text(
        json.dumps(st_, ensure_ascii=False, indent=2), encoding="utf-8")


DECISION_TEXT = {
    None: "",
    "pending": "⚖️ ①岗前分析完成，正在等老板拍板（老板回复 做吧/不做/先核实 之一；此前可追问理由）",
    "accept": "✅ 老板已拍板：做这单",
    "decline": "⛔ 老板已拍板：不做这单（②采集/③评估/发岗已锁定；老板改主意会说「重新判断」重跑①）",
    "clarify": "📌 老板已拍板：先核实/暂缓再定（②③暂锁；核实完老板会说「做吧」或「不做」覆盖本决策）",
}


def decision_text(decision: str | None) -> str:
    return DECISION_TEXT.get(decision, "")


def state_block(job: dict) -> str:
    """状态卡文本：注入每条 prompt，让 agent 无论有没有会话记忆都掌握岗位现状。"""
    st_ = load_state(job["job_code"])
    jd_p = _job_dir(job) / "jd.txt"
    arts = list_artifacts(job["job_code"])
    jd_status = "已提供" if (st_.get("jd_provided") and jd_p.exists()) else "为空/未提供"
    dec_line = decision_text(st_.get("decision"))
    dec_extra = (f"（备注：{st_['decision_note'][:60]}）"
                 if st_.get("decision_note") else "")
    prof_p = job_profile_path(job)
    return (
        f"【岗位状态卡】{job.get('title','')}（{job['job_code']}）\n"
        f"- 岗位 JD 文件：{jd_p.as_posix()}（{jd_status}。已提供则开口前必须先读它）\n"
        f"- ① 岗前分析：{'已完成' if st_.get('step1_analyzed') else '未做'}"
        f"（最近一次动作：{st_.get('last_action') or '无'}）\n"
        f"- ⚖️ 老板决策：{dec_line or '尚未到判断点（①分析做完后老板会在对话里拍板 做/不做/先核实）'}{dec_extra}\n"
        f"- 📋 岗位资料（PM 口径/猎头关注，若已建则涉本岗口径先读它）：{prof_p.as_posix()}\n"
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

def job_profile_path(job: dict) -> Path:
    """岗位资料文件（v1.7.3，岗位目录 = 正式底座的附加信息载体）：
    {"job_code", "pm_notes": [...], "special_notes": [...], "events": [{"ts","who","note"}]}"""
    return _job_dir(job) / "job_profile.json"


def _recent_boss_text(job_code: str, limit: int = 4) -> str:
    """本会话老板最近 limit 条非任务原话（注入用；v1.7.2：agent 无跨 run 记忆，
    老板在对话里给的口径/教学原文不注入它真看不到）。"""
    msgs = load_transcript(job_code)
    boss_lines = []
    for m in msgs:
        c = (m.get("content") or "").strip()
        if m.get("role") != "user" or not c:
            continue
        if c.startswith("老板要你") or c.startswith("老板已确认"):
            continue  # 任务注入文本，非老板原话
        boss_lines.append(c)
    recent = boss_lines[-limit:]
    if not recent:
        return "〔本会话暂无可引用的老板原话〕"
    return "\n\n".join(f"〔老板消息 {i + 1}〕{c}" for i, c in enumerate(recent))


def build_free_task(job: dict, user_msg: str) -> str:
    """自由讨论/追问：注入状态卡 + 能力边界 + 完整路径，先读文件再开口（禁 bash、禁列盘、读不到不许编）。

    v1.7.1：检测"老板教规则"意图 → 追加成长沉淀操作指引（小猎自助写 rules.md，只追加不改删）。
    v1.7.3：检测"记到岗位资料/PM 口径"意图 → 追加岗位资料落盘指引（job_profile.json，只追加）。
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
    teach = any(w in user_msg for w in TEACH_WORDS)
    to_profile = any(w in user_msg for w in PROFILE_WORDS)
    inject = _recent_boss_text(job["job_code"])
    # —— 成长沉淀分支（rules.md）——
    growth_hint = ""
    if teach:
        growth_hint = (
            f"\n【老板要你沉淀规则·背景（重要，先读）】你每次都是全新执行、没有跨轮记忆，"
            "老板教你的经验原文在**本会话对话记录**里——系统已把最近几条老板原话注入如下，"
            "**先从这里找老板教过你的规则/经验原文**（通常含\"教你/说明一下/记住/这个…\"等教学话术；"
            "跳过纯岗位问答）：\n"
            f"{inject}\n"
            f"\n【老板要你沉淀规则·操作步骤】用**文件工具**完成（禁 bash）：\n"
            f"  1) 先读成长规则库全文：{RULES.as_posix()}\n"
            "  2) 判断这条规则属于哪一节（## ① 岗位分析 / ## ② 采集 / ## ③ 池子评估 / "
            "## ④ 汇报 / HTML 过程文档 / ## 流程 / 工具）——不确定就放「流程 / 工具」；\n"
            "  3) 只在该节写入：若该节只有（暂无）占位，把占位替换成你的规则行；"
            "若已有规则，则在最后一条规则后、下一个 ## 小节标题前【追加】一行，格式：\n"
            f"     `- [来源 本岗 {job['job_code']} / {datetime.now().strftime('%Y-%m-%d')}] 当〔情境〕时，应〔怎么做〕`\n"
            "  4) 规则内容**只从上面注入的老板原话里提炼归纳**成一句，不许编造老板没说的；"
            "若注入内容里找不到可提炼的教学原文，如实告诉老板「我没找到您教的规则原文，请把原话发我」，"
            "**不许脑补、不许拿猜的内容写进成长库**；\n"
            "  5) 不许删改任何已有规则行，不许动其他文件；\n"
            "  6) 写完回读确认，回复里展示你新增的行与所在节。\n"
        )
    # —— 岗位资料落盘分支（job_profile.json）——
    profile_hint = ""
    if to_profile:
        profile_hint = (
            f"\n【老板要你记到岗位资料·背景（重要，先读）】老板给的口径/临时需求/PM 答复原文"
            "在**本会话对话记录**里——系统已把最近几条老板原话注入如下，先从中找要记的内容：\n"
            f"{inject}\n"
            f"\n【记到岗位资料·操作步骤】用**文件工具**完成（禁 bash）：\n"
            f"  1) 先读岗位资料文件（不存在就按下面结构新建）：{job_profile_path(job).as_posix()}\n"
            "     结构 = {\"job_code\": \"...\", \"pm_notes\": [\"PM/发单方口径、补充、岗位变动…\"], "
            "\"special_notes\": [\"猎头内部关注、客户特殊要求、潜规则…\"], "
            "\"events\": [{\"ts\": \"日期\", \"who\": \"PM/老板\", \"note\": \"变动或补充\"}]}\n"
            "  2) 判断内容属于哪类：PM/发单方说的口径与岗位变动 → pm_notes；"
            "老板自己的关注点/客户特殊要求（含\"不招女的\"这类内部记录）→ special_notes；"
            "带时间点的变动/补充 → 同时追加一条 events；\n"
            "  3) **一律追加新条目，绝不删改已有条目**（最新口径 = 数组最后一条）；文件不存在则新建骨架；\n"
            "  4) 内容只从注入的老板原话提炼，不编造；找不到可记内容就如实说；\n"
            "  5) ⚠️ 若记录含性别/年龄/婚育/户籍等歧视性要求：属【客户口径的内部事实记录】，"
            "只写进 special_notes，**绝不用于筛选条件/搜索关键字/任何对外文案**，并在回复里提示老板这条合规边界；\n"
            "  6) 写完回读确认，回复里展示你记了什么、进哪个字段。\n"
        )
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
        f"{growth_hint}"
        f"{profile_hint}"
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
7. 最后用「老板，我弄的咋样？」口吻给我一段**判断式**回复（≤10 句，**给人读的判断，不是报告摘要**——别罗列全部字段）：
   - 第 1 句给明确态度：从「这单我建议：接 / 先沟通再定 / 别做」三选一（与你报告的 recommendation 一致，
     不许含糊骑墙）；
   - 接着给最硬的 3~4 条理由（佣金/HC/新鲜度/上游/难度里哪几项拉分、哪几项拉胯，各一句话，可引用评分）；
   - 再点 1~2 条最该注意的风险或要先跟 PM 核实/澄清的口径；
   - 最后**请老板拍板**：「您定：做 / 不做 / 先核实——也可以再问我理由。」
   注意：老板拍板后岗位状态会记决策（accept/decline/clarify），他说「做吧」才会解锁②采集等下一步；
   判断错不罚、不诚实必罚。
8. 回复里给出上面两个文件的路径。
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


# ── 判断拍板意图（v1.7.0 判断对话化：老板对①岗前分析结果拍板 做/不做/先核实）──

# 拍板词表（保守：宁可不命中落自由对话，也不误触记错决策；问句一律不触发）
ACCEPT_WORDS = ("做吧", "咱做", "可以做", "值得做", "就做", "决定做", "确定做", "做这单",
                "做做看", "接单", "接吧", "接单吧", "接了", "拿下", "干吧", "干这单",
                "可以，做", "好，做", "行，做")
DECLINE_WORDS = ("不做", "别做", "放弃", "不接", "别接", "算了", "不干", "拒了", "不值得",
                 "别做了", "不做吧", "放弃吧", "不做了", "钓鱼单", "坑单", "这单不行", "别搞")
CLARIFY_WORDS = ("先核实", "先问", "先沟通", "先确认", "先跟", "核实一下", "再想想", "考虑一下",
                 "先别定", "跟pm", "问pm", "看看再说", "先放着", "先不决定")
REJUDGE_WORDS = ("重新判断", "重新分析", "重跑分析", "再分析", "重新看看", "重看一遍", "再判断")


def detect_decision_intent(msg: str) -> str:
    """识别老板对①岗前分析的拍板。返回 "accept"/"decline"/"clarify"/""（未命中=自由对话）。

    仅在 decision==pending 时由路由调用。保守规则：
    - 讨论/反问句（怎么/为什么/？/吗…）一律不触发 → 落自由对话（老板可追问理由）；
    - 「别放弃/别急着…」等反向表达不触发 decline；
    - 先查整句短词（"做"/"不做"/"可以"…），再查包含词；decline 先于 accept 查
      （"不值得做" 应判 decline 而非 accept）。
    """
    m = msg.strip()
    if not m:
        return ""
    if ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
            or "？" in m or "?" in m or m.endswith("吗") or m.endswith("么")):
        return ""
    if "别放弃" in m or "别急着" in m:
        return ""
    m_short = m.rstrip("。！!~ ")
    if m_short in ("做", "做吧", "可以", "可以做", "好", "行", "接", "干", "拿下"):
        return "accept"
    if m_short in ("不做", "别做", "算了", "放弃", "不接", "不干", "不做吧", "别做了"):
        return "decline"
    if any(w in m for w in DECLINE_WORDS):
        return "decline"
    if any(w in m for w in ACCEPT_WORDS):
        return "accept"
    if any(w in m for w in CLARIFY_WORDS):
        return "clarify"
    return ""


def detect_rejudge_intent(msg: str) -> bool:
    """老板想重跑①重新判断（decision 已非空时启用：decline 改主意 / 想再看一遍）。"""
    return any(w in msg for w in REJUDGE_WORDS)


def record_decision(job: dict, decision: str, note: str = "") -> None:
    """拍板落盘（本地动作，不调 agent）。note = 老板原话截断，留档可查。"""
    label = {"accept": "做", "decline": "不做", "clarify": "先核实"}.get(decision, decision)
    save_state(job["job_code"], decision=decision,
               decision_note=(note or "").strip()[:80] or None,
               decision_ts=now_str(), last_action=f"拍板：{label}")


def build_decision_reply(decision: str, note: str = "") -> str:
    """拍板确认消息（本地生成，留在对话里；理解错可纠正）。"""
    note_short = (note or "").strip()[:60]
    if decision == "accept":
        return ("✅ 收到：**这单咱做**。已记入岗位决策，②采集/③评估/发岗解锁。\n"
                "下一步你挑一个：说「去猎聘跑一轮」（先出采集计划请你确认）／点 📋 生成发岗文字"
                "／📥 入库当前岗。理解错了跟我说一声即可。")
    if decision == "decline":
        return ("✅ 收到：**这单不做**。已记入岗位决策，②③/发岗已锁定。\n"
                f"备注已留：{note_short or '（无）'}。想改主意或重新看一遍，说「重新判断」即可。")
    return ("📌 收到：**先核实再定**。②③/发岗暂锁，等你核实完回来说「做吧」或「不做」即可。\n"
            f"备注已留：{note_short or '（无）'}。")


# ── 步骤② 探索采集（两步走：先出计划请确认 → 确认后用 pwsh 跑配方表采集）──

COLLECT_WORDS = ("猎聘", "采集", "搜候选人", "搜一轮", "跑一轮", "搜人", "捞人", "搜索",
                 "补采", "补跑", "重采", "再采", "去采")
COLLECT_CONFIRM_WORDS = ("按计划", "直接跑", "执行采集", "开始采集", "确认跑", "按这个跑",
                         "执行计划", "按此计划", "按这个计划")
# 动作意图词（配合已落盘计划 → 判定"确认执行"，如"按补跑计划执行"）
COLLECT_ACTION_WORDS = ("执行", "继续", "开始", "确认", "按", "补", "重新")


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

    保守规则：讨论/提问（含“怎么/为什么/？”）不触发；
    - run：盘上已有 collect_plan_*.json，且消息命中 ① 明确确认词（按计划/直接跑/…）
      或 ② 采集词（采集/补采/补跑…）+ 动作词（跑/执行/按/补…）——覆盖"按补跑计划执行"
      这类自然说法（2026-09-06 实测卡点：只说"按补跑计划执行"未命中旧词表 → 走普通聊天、
      没挂 pwsh 工具 → 小猎无法真跑）；
    - plan：有采集词但还没计划（或无法判定为执行）→ 先出计划请老板确认。
    """
    m = msg.strip()
    is_question = ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
                   or m.endswith("？") or m.endswith("?") or m.endswith("吗"))
    has_plan = latest_collect_plan(job) is not None
    has_collect_word = any(w in m for w in COLLECT_WORDS)
    has_confirm_word = any(w in m for w in COLLECT_CONFIRM_WORDS)
    has_action_word = any(w in m for w in COLLECT_ACTION_WORDS)
    if is_question:
        return ""
    if has_plan and (has_confirm_word or (has_collect_word and has_action_word)):
        return "run"
    if has_collect_word:
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
    return f"""老板要你执行【步骤② 探索采集·第一步：出计划】。请全程用文件工具完成，**这一步不真跑采集（只出计划给老板确认）**：
1. 读岗位 JD：{jd}
2. 读最新岗前分析报告：{analyze_hint}
   —— 从报告的 search_keywords 里挑 2~4 个最可能命中目标候选人的关键字（参考其精确/职能/竞品/技能分组；
   若报告没有关键字，按方法论 {method} 的思路从 JD 拆）。
3. 按 JD 硬性条件给出猎聘筛选条件建议（配方组 group_id=value，可空，如 education=博士/博士后、
   city_current=杭州、years=应届生…；注意：院校 C9/QS50 猎聘筛不掉，年限对资深岗可能无对应选项，别硬凑；
   ⚠️ **学历筛只有离散档：不限/本科/硕士/博士/博士后/大专/中专/中技/高中及以下——没有“本科及以上/大专及以上”这种档位**，
   JD 写“本科及以上”就选“本科”或干脆不筛学历、留待③逐人把关）。
4. 把计划写成 JSON 文件：{plan_file}
   格式：{{"keywords": [关键字...], "conds": ["group_id=value"...], "reasons": "为何这样选（2~3 句）",
          "note": "口径提醒（如年限矛盾先核实）", "created_at": "..."}}
5. 用「老板，采集计划好了」口吻回复 ≤8 句：列出关键字与条件、为什么这样选、预估代价
   （每个关键字=1 次猎聘搜索，搜索次数不是瓶颈；⚠️ 猎聘搜索框是“包含全部关键词”——空格分隔的词**全部要命中**，
   关键字词内别叠同义词/多词，否则极易 0 命中；同义词宁可拆成多个关键字分路跑）、
   给一句**池子预期判断**（这个池子估摸着 厚/正常/薄——薄的话说明这单捞人费劲，老板心里有数再拍板）、
   以及**请老板拍板**（老板回复“按计划跑/直接跑”才执行；他想调关键字/条件，就说“重新出采集计划”按他的意思改）。
{CAPABILITIES}"""


def build_step2_run_task(job: dict, plan_file: Path) -> str:
    """② 探索采集·第二步：老板已确认 → 读计划 → 用 pwsh 跑 collect_liepin.py → 读结果汇报。"""
    plan_abs = plan_file.as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = f"{reports_dir}/collected_{ts}.json"
    py = sys.executable.replace("\\", "/")  # 面板自身解释器（lzstudy），换机器自动跟随
    return f"""老板已确认【步骤② 探索采集】计划。请执行真实采集（真实搜索，关键字轮间保持 8-20 秒节奏，勿连点）：
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


# ── 步骤③ 池子评估（读 ② 采集池子 → 池评+逐人评分 → JSON 报告 + HTML 过程；纯文件，无外部副作用）──

EVAL_WORDS = ("评估", "评分", "评一评", "打分", "这批人", "候选人池")
FRESH_COLLECT_WORDS = ("去猎聘", "跑一轮", "搜候选人", "搜一轮", "补采", "再采", "去采", "换关键字", "放宽")


def detect_eval_intent(msg: str, job: dict) -> bool:
    """识别③评估发令（把已采池子评估一遍）。要求：有评估词、非讨论问句、盘上已有 collected 池子、
    不是“再去采集”类发令（走 ②）、不是“按计划跑/直接跑”确认（走 ② 执行）。"""
    m = msg.strip()
    if not any(w in m for w in EVAL_WORDS):
        return False
    if ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
            or m.endswith("？") or m.endswith("?") or m.endswith("吗")):
        return False
    if any(w in m for w in FRESH_COLLECT_WORDS):
        return False
    if any(w in m for w in COLLECT_CONFIRM_WORDS):
        return False
    if latest_report(job, "collected_", ".json") is None:
        return False
    return True


def build_step3_task(job: dict) -> str:
    """③ 池子评估：读 JD+最新采集池子+方法论 → 池评+逐人评分 → 写 pool_report JSON + HTML 过程 → 汇报。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    collected = latest_report(job, "collected_", ".json")
    analyze = latest_report(job, "analyze_", ".json")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    pool_report = f"{reports_dir}/pool_report_{ts}.json"
    html_out = f"{reports_dir}/评估_{ts}_过程.html"
    pq = (PROMPTS / "pool_quality.txt").as_posix()
    mc = (PROMPTS / "match_candidate.txt").as_posix()
    if collected is None:
        return (f"老板，这个岗位还没有②采集结果（reports 里没有 collected_*.json）。"
                f"请先点「② 探索采集」或说“去猎聘跑一轮”，采到池子后我再做③评估。\n{CAPABILITIES}")
    analyze_hint = analyze.as_posix() if analyze else "（暂无，直接从 JD 提炼硬性条件）"
    rules_hint = (f"先读成长规则库 {RULES.as_posix()}，遵守其中「③ 池子评估」及流程小节的相关规则。\n"
                  ) if RULES.exists() else ""
    return f"""老板要你执行【步骤③ 池子评估】。请全程用文件工具完成（纯计算，无外部动作）：
1. 读岗位 JD：{jd}
2. 读要评估的采集池子：{collected}
   —— rows 数组就是候选池，按数组顺序编号 1..N 作为 candidate_id；共 N=rows 条。若 rows 为空请如实说池子为空。
3. 读最新岗前分析：{analyze_hint}（它的硬性条件与口径提醒是你评分的依据）
4. 读你的两份方法论手册：
   池子质量手册（先评整池）：{pq}
   单候选人匹配手册（再逐人评）：{mc}
   {rules_hint}
5. 先按 pool_quality 手册评估整个池子并写进报告的 pool_quality：池子质量（优/良/中/差）、
   匹配分布 high/medium/low 数量（界线 ≥80/60-79/<60）、主要缺口、优势、行动建议、data_valid 校验
   （发现重复采集/占位/无效行要如实指出）。
6. 再按 match_candidate 手册逐人评分（紧凑格式）：每位必须有 candidate_id/score(0-100)/verdict(推荐/待定/不推荐)/
   summary(一句话)；只有 score≥60 或 verdict≠不推荐 才额外给 match_points(≤3 条)与 concerns(≤2 条)；
   其余只给三字段。评分严格贴 JD 硬性条件（学历/年限/城市/技能），年限口径矛盾等要先按 JD 原文判断并在 summary 提示。
7. 把完整 JSON 结果写入：{pool_report}
   结构：{{"pool_quality": {{...}}, "candidates": [{{"candidate_id": 1, "score": 0-100, "verdict": "...",
          "match_points": [...], "concerns": [...], "summary": "..."}}, ...]}}
8. 把本次工作过程写成一份简短中文 HTML 过程文档（池子评级+分布+Top 名单+各 3 句理由），保存到：{html_out}
9. 用「老板，池子评估好了」口吻汇报 ≤8 句：池子评级结论、分布、推荐/待定 top 名单（人名/分数/一句理由）、
   数据校验发现（如有）、下一步建议（如是否补采/深挖谁）；回复里给出上面两个文件的路径。
{CAPABILITIES}"""


# ── 发岗文字生成（① 决定做单后顺手用：读 JD+① → 猎聘发布文案，老板复制粘贴发布，发布动作留人工）──

def build_post_text_task(job: dict) -> str:
    """生成猎聘发岗文字：岗位名/亮点/职责/要求/薪酬地点 → 存 reports/发岗文字_<ts>.md 并在回复里全文给出。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    analyze = latest_report(job, "analyze_", ".json")
    analyze_hint = analyze.as_posix() if analyze else "（暂无，直接从 JD 提炼）"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = f"{reports_dir}/发岗文字_{ts}.md"
    return f"""老板要你生成【发岗文字】（用于把岗位发布到猎聘，老板会复制粘贴去发布，发布动作由老板人工完成）：
1. 读岗位 JD：{jd}
2. 读最新岗前分析：{analyze_hint}（它的 jd_extracted/评分理由/风险可用来提炼卖点与口径提醒）
3. 写一份可直接发布的猎聘职位文案，包含：
   - 职位名称（贴合 JD 叫法 + 搜索友好）
   - 一句话吸引点（卖点先行）
   - 岗位职责（4~6 条，来自 JD description）
   - 任职要求（硬性条件单列 + 加分项单列；若 JD 里有口径矛盾，如年限"博士2年 vs 10年+"，
     文案里按更宽松口径写并备注"面议/详询"，别写死自相矛盾）
   - 薪酬/地点/福利（按 JD；写"面议"的注明）
   - 结尾引导语（欢迎自荐/推荐）
4. 保存到：{out}
5. 回复里把整份文案**全文贴出**（老板直接复制），并给 ≤3 句提示（如"注意先核实年限口径再发布"）。
{CAPABILITIES}"""


# ── ④ 打招呼准备清单（③评估后：入围者(推荐/待定) → 话术1/2 + 猎聘直达链接 → .md，老板照单点链接打）──

def build_step4_greet_task(job: dict) -> str:
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    pool = latest_report(job, "pool_report_", ".json")
    collected = latest_report(job, "collected_", ".json")
    if pool is None or collected is None:
        return (f"老板，③评估（pool_report）还没做，先点「③ 池子评估」或说“把这批人评估一遍”，"
                f"出结果后我再生成打招呼清单。\n{CAPABILITIES}")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = f"{reports_dir}/打招呼清单_{ts}.md"
    rules_hint = (f"先读成长规则库 {RULES.as_posix()}，遵守其中「④ 汇报 / HTML 过程文档」及流程小节相关规则。\n"
                  ) if RULES.exists() else ""
    return f"""老板要你生成【打招呼准备清单】——老板照着一行行点链接、复制话术去猎聘打招呼（打招呼动作由老板人工执行，你只产出清单，不代发）：
1. 读岗位 JD：{jd}
2. 读池子评估：{pool}（candidates 数组按 candidate_id 对应采集顺序；含 score/verdict/match_points/concerns/summary）
3. 读采集池子：{collected}——rows[candidate_id-1].fields.res_id_encode 是该候选人猎聘 ID，
   详情链接 = https://h.liepin.com/resume/showresumedetail/?res_id_encode=该ID
{rules_hint}
4. 只列【入围者】= verdict ∈ {{推荐, 待定}}，按 score 降序，**最多 15 人**；verdict=不推荐 的不进清单
   （文件末尾一行备注“另有 N 人不推荐未列入”）。
5. 每人生成一个小节（Markdown，链接用 HTML 锚点以便新标签打开）：
   ### N. 姓名 — score分（verdict）　<a href="https://h.liepin.com/resume/showresumedetail/?res_id_encode=XXX" target="_blank">▶ 打开猎聘详情</a>
   - 一句话概况（现职/城市/最相关点）
   - 匹配点：最多 2 条（从 match_points 精选最硬的）
   - 先核实：最多 2 条（从 concerns 精选最可能影响沟通的，如年限口径/重叠提示/专业错配/薪资预期；措辞要能在打招呼里自然问出）
   - 话术1（岗位亮点，含一句卖点+薪酬城市，可直接复制发送）
   - 话术2（针对此人匹配理由，自然带出 1 个核实点）
6. 文件头部先写岗位一句话卖点总述（每个招呼前都能用），再写“今日建议先打：…2-3 人（理由）”。
7. 保存到：{out}
8. 回复 ≤6 句：共几个入围者、先打哪 2-3 人及理由、文件路径。
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
                                format_func=lambda c: labels.get(c, str(c)), key="job_pick_chat")
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
                "- **判断在对话里**：🚀 岗前分析完，小猎给「接 / 先沟通 / 别做」态度 + 理由，"
                "你回复 做吧/不做/先核实 拍板，或直接追问「为什么」反驳；拍板后才解锁②采集/发岗\n"
                "- **按钮=执行显示层**：也可点按钮快捷发令（系统按岗位状态 + 你的拍板自动亮/灰）\n"
                "- **看过程**：每步执行自动落 HTML 过程文档，对话里点产物「打开 ↗」即看，不用盯屏\n"
                "- **教它规则（成长）**：对话里教完说「把这条记到成长库」——它会按格式追加进 rules.md"
                "（只追加不改删，写完展示新增内容，你随时可审）；要改设计/手册则找实施对话\n"
                "- **纠错**：侧栏记一笔 → 成长账；消化成规则后可让助理写进 rules.md\n"
                "- **发岗/入库**：第二行按钮——①拍板做后「生成发岗文字」复制去猎聘发布；任意时点「入库当前岗」"
                "把该岗产物幂等写入 business.db（台账/统计用）\n"
                "- **能力边界**：①②③已接入（分析/采集/评估），联系候选人=人工闸门（未接入）；自由聊天里也会如实说明")

    return {"jobs": jobs, "stub": stub, "env_path": Path(env_path)}


def render_progress_line(job: dict) -> None:
    """岗位自动进度（只读，不用手动维护）。v1.7.0：①分析完进入「等你拍板」判断点。"""
    stt = load_state(job["job_code"])
    jd_ok = stt.get("jd_provided")
    a1 = stt.get("step1_analyzed")
    c2 = stt.get("step2_collected")
    c3 = stt.get("step3_done")
    dec = stt.get("decision")
    jd_chip = "📥 JD 已收" if jd_ok else "📥 等 JD"
    if not a1:
        a1_chip = "⬜ ① 岗前分析未做"
    elif dec == "pending":
        a1_chip = "⚖️ ① 分析完 · 等你拍板"
    elif dec == "accept":
        a1_chip = "✅ ① 分析完 · 已拍板：做"
    elif dec == "decline":
        a1_chip = "⛔ ① 分析完 · 已拍板：不做"
    elif dec == "clarify":
        a1_chip = "📌 ① 分析完 · 已拍板：先核实"
    else:  # 旧岗无 decision 字段 → 兼容不锁
        a1_chip = "✅ ① 岗前分析完成（旧岗，未走拍板）"
    c2_chip = "✅ ② 已采集" if c2 else "② 探索采集（拍板做后解锁）"
    c3_chip = "✅ ③ 池子已评估" if c3 else "③ 池子评估（②采完才可点）"
    st.markdown(f"**流程进度**：{jd_chip}　→　{a1_chip}　→　{c2_chip}　→　{c3_chip}")
    hint = []
    if not jd_ok:
        hint.append("先上传/粘贴 JD（新建岗位时），或直接在下方输入框把 JD 原文发来。")
    elif not a1:
        hint.append("点下方「🚀 开始岗位分析」——小猎会真分析并给「接/先沟通/别做」的态度和理由，等你拍板。")
    elif dec == "pending":
        hint.append("小猎的判断在上一条消息里：回复「做吧 / 不做 / 先核实」拍板，或直接追问「为什么」反驳。"
                    "（②采集要等你拍板做才解锁）")
    elif dec in ("decline", "clarify"):
        hint.append("②③/发岗已按你的拍板锁定。改主意/核实完了：说「做吧」「不做」，或「重新判断」重跑①。")
    elif dec is None:
        hint.append("旧岗兼容（未走拍板流程）：可继续按按钮走；想重新过一遍判断说「重新判断」。")
    elif not c2:
        hint.append("①已拍板做：②探索采集已解锁——点按钮或说「去猎聘跑一轮」（先出计划你确认后再真跑）。")
    elif not c3:
        hint.append("②已采集：可点「③ 池子评估」给这批人评分（读方法论逐人打分，纯计算）。")
    else:
        hint.append("③评估已出：看 top 清单可追问/纠错/重跑；联系候选人=人工闸门（未接入）。")
    st.caption("　".join(hint))


def render_action_row(job: dict, cfg: dict | None = None) -> str | None:
    """动作按钮行：由岗位状态自动亮/灰；返回要发送的任务文本（无则 None）。

    v1.7.0 按钮 = 「执行显示层」：判断主通道在对话（小猎给态度+理由 → 老板拍板）。
    ①分析完先等拍板（decision=pending 锁②③/发岗）；accept 才解锁；decline/clarify 锁；
    旧岗无 decision 字段（None）不锁（兼容）。
    v1.6.8：📋 生成发岗文字按钮改为本地驱动 publish_run（agent 产字段 JSON →
    本地渲染 发岗文字_<ts>.html，逐格复制到猎聘），不再走聊天 agent 手写整篇 md。
    """
    stt = load_state(job["job_code"])
    jd_ok = stt.get("jd_provided") and (_job_dir(job) / "jd.txt").exists()
    arts = list_artifacts(job["job_code"])
    stub = bool(cfg and cfg.get("stub"))
    env_path = (cfg or {}).get("env_path")
    a1 = stt.get("step1_analyzed")
    dec = stt.get("decision")

    c1, c2, c3, c4 = st.columns(4)
    task = None
    if not jd_ok:
        st.info("岗位 JD 还没就位：请先在左侧新建岗位时粘贴/上传 JD。")
        return None
    # v1.7.0：判断点提示——按钮是执行显示层，拍板在对话里
    if a1 and dec == "pending":
        st.info("⚖️ **判断点**：小猎已给态度和理由（见上一条消息）。请回复「做吧 / 不做 / 先核实」拍板，"
                "或先追问「为什么」——②采集/发岗要等你拍板做才解锁。")
    elif a1 and dec == "decline":
        st.info("⛔ 已拍板**不做**这单：②③/发岗已锁定。改主意或重看一遍，回复「重新判断」。")
    elif a1 and dec == "clarify":
        st.info("📌 已拍板**先核实再定**：②③/发岗暂锁。核实完回复「做吧」或「不做」。")
    decision_ok = dec in (None, "accept")  # None=旧岗兼容
    label1 = "🔄 重跑岗位分析（重新给判断）" if a1 else "🚀 开始岗位分析"
    if c1.button(label1, key="act_analyze", use_container_width=True,
                 help="读 JD+方法论+成长规则 → 评分/接单判断/4组关键字 → JSON+HTML 落盘 → "
                      "对话里给「接/先沟通/别做」态度与理由，等你拍板"):
        task = build_step1_task(job)
    if c2.button("📤 导出 HTML 汇报", key="act_report", use_container_width=True,
                 disabled=len(arts) == 0,
                 help="读已有分析产物，整理成一份给人看的 HTML 汇报（按需点）"):
        task = build_report_task(job)
    if c3.button("② 探索采集", key="act_collect", use_container_width=True,
                 disabled=not (a1 and decision_ok),
                 help="已接入：第一步先出计划（关键字/条件 + 池子厚薄预期请你拍板）→ 你回复“按计划跑”才真跑猎聘采集"):
        task = build_step2_plan_task(job)
    if c4.button("③ 池子评估", key="act_eval", use_container_width=True,
                 disabled=not (stt.get("step2_collected") and decision_ok),
                 help="已接入：读②采集池子+方法论 → 池评+逐人评分 → JSON 报告+HTML 过程（纯计算）"):
        task = build_step3_task(job)

    # 第二行动作行：发岗文字（v1.6.8 走 publish_run 本地渲染）/ ④打招呼清单 / 入库当前岗
    c5, c6, c7 = st.columns(3)
    if c5.button("📋 生成发岗文字", key="act_post_text", use_container_width=True,
                 disabled=not (a1 and decision_ok),
                 help="v1.6.8：读 JD+①+发岗手册 → 发岗字段 JSON → 本地渲染 HTML（9 格逐格复制到猎聘发岗页，发布人工）"):
        if stub:
            st.info("假执行模式：跳过 API（真执行会产发岗字段 JSON + 渲染 发岗文字_*.html）")
        elif not env_path:
            st.warning("未配置 .env 路径（侧栏「运行设置」）。")
        else:
            try:
                import publish_run
                with st.status("小猎整理发岗文字中（读发岗手册+JD → 字段 JSON → 本地渲染）…",
                               expanded=False) as status:
                    jf, hf = publish_run.publish_for_job(job["job_code"], env_path)
                    status.update(label="发岗文字完成", state="complete")
                files = [Path(p) for p in (jf, hf) if p and Path(p).exists()]
                if files:
                    # v1.6.9：产物以「可打开」消息留在对话里（HTML 打开即逐格复制，不再只给说明文字）
                    append_msg(job["job_code"], "assistant",
                               f"📋 发岗文字已生成（{now_str()}）——点下方「打开 ↗」用浏览器打开，"
                               "逐格复制到猎聘发岗页（发布动作人工）。",
                               artifacts=[p.name for p in files])
                    save_state(job["job_code"], last_action="发岗文字")
                    st.success("✅ 发岗文字已生成：见对话里最新一条消息（点「打开 ↗」直接看）。")
                    st.rerun()
                else:
                    st.warning("发岗文字未生成：看上方汇报定位问题（可重跑/纠错）。")
            except Exception as e:
                st.error(f"⚠️ 生成发岗文字失败：{e}")
    if c6.button("💬 生成打招呼清单", key="act_greet", use_container_width=True,
                 disabled=not stt.get("step3_done"),
                 help="③评估后：入围者(推荐/待定)每人 话术1/2 + 猎聘直达链接 → reports/打招呼清单_*.md，"
                      "老板照单点链接、复制话术去打招呼（打招呼动作人工）"):
        task = build_step4_greet_task(job)
    if c7.button("📥 入库当前岗", key="act_import_db", use_container_width=True,
                 help="把该岗①-③产物幂等写入 business.db（jobs/候选人/评估），可重复点，重复只刷新不新增"):
        try:
            import import_chat_job
            res = import_chat_job.import_job(job["job_code"])
            st.success(f"✅ 已入库 {res['job_code']}：岗位行已写/刷新；本次净新增候选人 "
                       f"{res['candidates']}、评估 {res['matches']} → {res['db']}")
        except Exception as e:
            st.error(f"⚠️ 入库失败：{e}")
    return task


# ── 对话产物即点即开（v1.6.9：取代右侧报告栏；产物以可打开链接留在对话里）──

def artifact_open_row(path: Path, key: str) -> None:
    """一条产物的可打开行：文件名 + 「打开 ↗」按钮（os.startfile 本机打开，HTML=默认浏览器）。

    HTML 网页产物（发岗文字/打招呼清单/匹配报告/过程文档等）打开后可直接点页面里的链接操作，
    不用先看说明文字再手动去翻文件夹。
    """
    name = path.name
    if not path.exists():
        st.caption(f"📎 {name}")
        return
    is_html = path.suffix.lower() == ".html"
    c1, c2 = st.columns([7, 1], vertical_alignment="center")
    c1.markdown(f"📄 **{name}**")
    c1.caption("网页产物：打开后在浏览器里查看/点页面里的链接" if is_html
               else "点「打开 ↗」用本机默认程序查看")
    if c2.button("打开 ↗", key=key, use_container_width=True,
                 help="用本机默认程序打开（HTML=默认浏览器）"):
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as e:
            st.error(f"打开失败：{e}")


def render_artifacts(job: dict, msg_index: int, artifacts: list[str]) -> None:
    """助手消息下方的产物行：每个都是可点「打开 ↗」的链接。"""
    reports_dir = _job_dir(job) / "reports"
    for a in artifacts:
        artifact_open_row(reports_dir / a,
                          key=f"art_open_{job['job_code']}_{msg_index}_{a}")


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

    # v1.6.9 布局：对话流全宽；每步产物以「可打开」行留在对话里（右侧报告栏已去掉）
    for mi, m in enumerate(load_transcript(job["job_code"])):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            render_artifacts(job, mi, m.get("artifacts") or [])

    # 动作按钮行 + 自由输入
    task = render_action_row(job, cfg)
    prompt = st.chat_input("跟小猎说话：发指令 / 追问 / 讨论；也可以直接粘贴 JD 原文…")

    def kind_of_task(t: str) -> str:
        if t.startswith("老板要你执行【步骤①"):
            return "analyze"
        if t.startswith("老板要你执行【步骤②"):
            return "collect_plan"
        if t.startswith("老板已确认【步骤②"):
            return "collect_run"
        if t.startswith("老板要你执行【步骤③"):
            return "eval"
        if t.startswith("老板要你生成【发岗文字】"):
            return "post_text"
        if t.startswith("老板要你生成【打招呼准备清单】"):
            return "greet"
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
        stt_now = load_state(job["job_code"])
        # v1.7.0 判断对话化：①分析完 & 等你拍板 → 先识别拍板（本地处理，不调 agent；可纠正）
        if stt_now.get("step1_analyzed") and stt_now.get("decision") == "pending":
            dec_action = detect_decision_intent(prompt)
            if dec_action:
                append_msg(job["job_code"], "user", to_send)
                record_decision(job, dec_action, prompt)
                append_msg(job["job_code"], "assistant", build_decision_reply(dec_action, prompt))
                st.rerun()
                return
        # 已拍板（decline/clarify）后想重跑①重新判断 → 走 analyze（decision 自动回 pending）
        if (stt_now.get("step1_analyzed") and stt_now.get("decision") in ("decline", "clarify")
                and detect_rejudge_intent(prompt)):
            action_kind, agent_prompt = "analyze", build_step1_task(job)
        else:
            # v1.6.3 修复：自由聊天必须走 build_free_task，注入状态卡+完整路径+能力边界+硬指令
            # （历史 bug：build_free_task 定义了没接线，agent 反复“找不到岗位文件”）
            # v1.6.4/1.6.5：先识别意图——③评估（纯计算，优先）→ ②采集两步（出计划/确认后执行）；讨论性问句不触发
            ev, coll = False, ""
            if stt_now.get("step1_analyzed"):
                ev = detect_eval_intent(prompt, job)
                if not ev:
                    coll = detect_collect_intent(prompt, job)
            if ev:
                action_kind, agent_prompt = "eval", build_step3_task(job)
            elif coll == "plan":
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
                max_tok = 32768 if action_kind == "eval" else (16384 if action_kind == "greet" else 8192)
                reply, new_files = run_assistant(job, agent_prompt, cfg["env_path"],
                                                 stub=cfg["stub"], max_tokens=max_tok, cordis=cordis)
                status.update(label="小猎完成", state="complete")
        except Exception as e:
            reply = f"⚠️ 执行出错：{e}\n\n（若是 .env/API 问题请检查侧栏运行设置；界面自测请开「假执行」）"
            new_files = []
        append_msg(job["job_code"], "assistant", reply,
                   artifacts=[p.name for p in new_files])
        # 更新状态卡
        label_map = {"analyze": "岗位分析", "report": "导出汇报", "chat": "自由对话",
                     "collect_plan": "②采集·出计划", "collect_run": "②采集·执行",
                     "eval": "③池子评估", "post_text": "发岗文字", "greet": "打招呼清单"}
        upd = {"last_action": label_map.get(action_kind, action_kind)}
        if action_kind == "analyze":
            # v1.7.0：①分析完 → 进入「等你拍板」判断点（重跑清掉旧决策）
            upd["step1_analyzed"] = True
            upd["decision"] = "pending"
            upd["decision_note"] = None
            upd["decision_ts"] = None
        if action_kind == "collect_run":
            upd["step2_collected"] = bool(any(p.name.startswith("collected_")
                                              for p in list_artifacts(job["job_code"])))
        if action_kind == "eval":
            upd["step3_done"] = bool(any(p.name.startswith("pool_report_")
                                         for p in list_artifacts(job["job_code"])))
        save_state(job["job_code"], **upd)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="数字合伙人 · 对话汇报（v1.7.3）", page_icon="🗣", layout="wide")
    st.markdown("# 🗣 数字合伙人 · 对话式汇报")
    st.caption("v1.7.3｜ 判断对话化（①分析完 → 小猎给态度+理由 → 你拍板 做/不做/先核实）｜ "
               "对话里教规则 → 说「记到成长库」小猎自助写 rules.md；PM 口径/临时需求 → 说「记到岗位资料」"
               "小猎写 job_profile.json（均只追加）｜ "
               "一岗一会话｜ 对话里产物即点即开（HTML 用浏览器打开）｜ "
               "①②③+发岗/打招呼清单/入库已接入｜ 纠错成长账：`data/growth/records.jsonl` + `data/prompts/rules.md`")
    ensure_rules()
    cfg = render_sidebar()
    render_main(cfg)


if __name__ == "__main__":
    main()
