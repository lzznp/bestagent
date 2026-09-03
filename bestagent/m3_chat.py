# -*- coding: utf-8 -*-
"""M3 界面 v1.5：对话式汇报面板（DSH Web 迷你版 · 分步骤测试用）

背景（2026-09-02 老板拍板，见 PROGRESS「M3 界面 v2 设计讨论」挂起记录）：
- 形态 = 像 DSH Web 一样"对话为主"：一个输入框（+JD 上传口）+ 回复/日志区
- 一个岗位 = 一个对话会话（SDK JSONL 会话 + 本机 transcript 双持久化）
- 执行 = B 档：真 agent 会话（复用 m1_run 已验证的 DeepSeekHarness 管路，persona=小猎）；
  阻塞式（发令→等它干完→回话），过程可见性靠"助理写 HTML 过程文档"（不追求实时流）
- 测试节奏 = 一步一回合：① 岗前分析 → ② 采集 → ③ 池子评估 → ④ 汇报（逐步来，先测①）
- 成长数据 = 纠错按 岗位→步骤 记入 data/growth/records.jsonl（原始账）+ 消化成规则进
  data/prompts/rules.md（助理每次干活会读，下次自动生效）

运行（PyCharm 终端，解释器选 lzstudy，在 bestagent\\ 目录）：
  streamlit run m3_chat.py
界面自测（不调 API）：侧栏"运行设置"→ 执行模式选「假执行(界面自测)」，或启动前设环境变量 M3CHAT_STUB=1
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

try:  # 集中配置：换电脑只改 framework_config.py / 环境变量
    from framework_config import WORKSPACE, SESSIONS, PROMPTS, OUTBOX
    from framework_config import DSH_ROOT, RUNTIME_BIN, CORDIS_MINIMAL, REQUEST_TIMEOUT
except Exception:
    WORKSPACE = Path(__file__).resolve().parent
    SESSIONS = WORKSPACE / ".sessions"
    PROMPTS = WORKSPACE / "data" / "prompts"
    OUTBOX = WORKSPACE / "data" / "outbox"
    DSH_ROOT = Path(r"C:\deepseek\deepseek-harness")
    RUNTIME_BIN = WORKSPACE / ".dsh-staging" / "node_modules" / "@deepseek-ai" / \
        "dsh-sdk-jsonrpc-demo" / "lib" / "packaged-bin.js"
    CORDIS_MINIMAL = DSH_ROOT / "examples" / "jsonrpc-agent" / "minimal.cordis.yml"
    REQUEST_TIMEOUT = 1200

# ── 数据目录 ──────────────────────────────────────────────────────
CHAT_DIR = WORKSPACE / "data" / "chat"       # 每岗位一个子目录（会话资料）
GROWTH_DIR = WORKSPACE / "data" / "growth"   # 纠错成长账
RECORDS = GROWTH_DIR / "records.jsonl"
RULES = PROMPTS / "rules.md"
DEFAULT_ENV = WORKSPACE.parent / "参考代码" / "lietou-agent" / "browser-agent" / ".env"

# 默认 env 文件（老板可侧栏覆盖）
STEPS = [
    {"no": 1, "name": "① 岗位分析", "tag": "岗前分析：读JD→接单判断→拆搜索条件→初判池子→做/放弃"},
    {"no": 2, "name": "② 采集", "tag": "采集：转猎聘关键字/条件→配方表采集→去重入库"},
    {"no": 3, "name": "③ 池子评估", "tag": "评估：池子评级+逐人评分→推荐清单"},
    {"no": 4, "name": "④ 汇报", "tag": "汇报：过程文档/结论 HTML→老板审阅"},
    {"no": 0, "name": "自由讨论", "tag": "不限定步骤：讨论/追问/纠错/别的"},
]

PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（一位猎头顾问）跑岗前分析、"
    "转搜索关键字、采集评估、写报告、做汇报。做事原则：先思考再动手；信息不足时明确提问；"
    "输出务必严格按方法论手册的格式，不擅自改动；涉及性别/年龄/婚育等违法歧视要求要提示并忽略；"
    "干完活主动向老板汇报（“老板，我弄的咋样？”的口吻）。"
    "老板在界面上用聊天跟你对话：一条岗位=一个会话，你们分步骤一起干活；"
    "当老板要求“生成 HTML 过程文档”或执行某步骤时，把你的工作过程（读了什么、怎么判断、做了什么动作）"
    "写成一份中文 HTML 过程文档保存到指定路径，方便老板查看你的工作过程。"
)

# ═══════════════════════ 纯数据层（可独立测试）══════════════════════

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def job_dir(job_code: str) -> Path:
    return CHAT_DIR / job_code


def list_jobs() -> list[dict]:
    """按创建时间倒序列出现有岗位会话。"""
    jobs = []
    if CHAT_DIR.exists():
        for d in sorted(CHAT_DIR.iterdir()):
            if not d.is_dir():
                continue
            meta_p = d / "meta.json"
            meta = {}
            if meta_p.exists():
                try:
                    meta = json.loads(meta_p.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            jobs.append({
                "job_code": meta.get("job_code", d.name),
                "title": meta.get("title", ""),
                "created_at": meta.get("created_at", ""),
                "session_id": meta.get("session_id", f"m3chat-{d.name}"),
                "dir": d,
            })
    jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return jobs


def create_job(title: str = "", jd_text: str = "", jd_bytes: bytes | None = None,
               jd_name: str = "") -> dict:
    """新建岗位会话：目录 + meta.json + jd.txt（粘贴或上传）+ 空 transcript。"""
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
    """该岗产物（reports 目录：HTML 过程文档/JSON 报告等），新的在前。"""
    d = job_dir(job_code) / "reports"
    if not d.exists():
        return []
    files = [p for p in d.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


# ── 成长账（records.jsonl + rules.md）──────────────────────────────

def append_record(job: dict, step_no: int, note: str, tags: str = "") -> dict:
    """记一笔纠错/成长（原始账，只增不改；状态=待消化，供日后提炼规则/定放手阈值）。"""
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": now_str(),
        "job_code": job["job_code"],
        "job_title": job.get("title", ""),
        "step": step_no,
        "step_name": next((s["name"] for s in STEPS if s["no"] == step_no), str(step_no)),
        "note": note.strip(),
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "status": "待消化",
    }
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
    """把某岗 待消化 记录标记为 已消化（本地小文件，整体重写）。"""
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
    """rules.md 不存在则建骨架（成长规则库：纠错消化后按步骤分节沉淀，助理干活前读）。"""
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


# ═══════════════════════ 执行通道（B 档真 agent / STUB）══════════════════════

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


def _job_dir(job: dict) -> Path:
    """job 可能来自 list_jobs（带 dir）或 create_job（meta 无 dir），统一取目录。"""
    d = job.get("dir")
    return Path(d) if d else job_dir(job["job_code"])


def build_free_task(job: dict, user_msg: str) -> str:
    """自由讨论/追问：给助理当前岗位上下文，让它读文件工具自己看。"""
    jd_path = (_job_dir(job) / "jd.txt").as_posix()
    rules_hint = ("在动手执行任何业务步骤前，先读成长规则库并遵守其中与本步骤相关的规则：\n"
                  f"  {RULES.as_posix()}\n") if RULES.exists() else ""
    return (
        f"【当前岗位会话】{job.get('title','')}（{job['job_code']}）\n"
        f"【岗位 JD 文件】{jd_path}（如需要请用文件工具读取；若该文件为空，提示老板先提供 JD）\n"
        f"{rules_hint}"
        f"【老板消息】{user_msg}\n"
        "请以「小猎」身份回复。若老板要求执行某一步骤并生成 HTML 过程文档，请把工作过程写成中文 HTML "
        "保存到该岗 reports 目录（路径请向老板确认后写入），并在回复里附上文件路径。"
    )


def build_step1_task(job: dict, analyze_method: Path | None = None) -> str:
    """步骤① 岗前分析标准任务（类似 m1_run，另加 HTML 过程文档 + 规则库）。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_json = f"{reports_dir}/analyze_{ts}.json"
    report_html = f"{reports_dir}/analyze_{ts}_过程.html"
    method = (analyze_method or PROMPTS / "analyze_job.txt").as_posix()
    rules_hint = (f"先读成长规则库 {RULES.as_posix()}，遵守其中「① 岗位分析」及流程小节的相关规则。\n"
                  ) if RULES.exists() else ""
    return f"""老板要你执行【步骤① 岗前分析】。请全程用工具完成，不要让他手动粘贴：

1. 读你的岗前分析方法论手册（必须严格按它的 JSON 输出格式，不增不减字段）：
   {method}
2. 读岗位 JD 文件：{jd}
3. 按手册完成岗前分析：提取岗位信息、判断进展、逐项评分（佣金/HC数量/新鲜度/上游靠谱度/匹配难度 各0-5）、
   算总分与等级、写清风险清单与建议、判定「接单/沟通/放弃」，并生成 4 组猎聘搜索关键字。
4. {rules_hint}
5. 把完整 JSON 结果写入：{report_json}
6. 把本次工作过程写成一份中文 HTML 过程文档（标题、做了什么判断、评分依据、关键字实验过程、
   结论与建议、风险），保存到：{report_html}
7. 最后用「老板，我弄的咋样？」口吻给我一段 ≤8 句的中文汇报：干了什么、这份 JD 值不值得接、
   我的建议、下一步。回复里给出上面两个文件的路径。"""


def run_assistant(job: dict, prompt: str, env_path: Path, stub: bool = False,
                  max_tokens: int = 8192) -> tuple[str, list[Path]]:
    """执行通道：B 档真 agent（复用 m1_run 已验证的 DeepSeekHarness）；
    stub=True 时不调 API（界面自测用）。返回 (回复文本, 新产物文件列表)。"""
    if stub:
        time.sleep(0.2)
        return (f"（假执行·界面自测）收到指令：{prompt[:60]}…\n"
                "正式使用时请把执行模式切回「真执行」并配置 .env。"), []
    # 懒加载 SDK（仅真执行时）
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
        cordis=str(CORDIS_MINIMAL),
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


# ═══════════════════════ UI 组装 ═══════════════════════

def render_sidebar() -> dict:
    """侧栏：岗位会话选择/新建、当前测试步骤、运行设置、纠错成长账。"""
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
            jd_paste = st.text_area("或直接粘贴 JD 原文", key="nj_paste", height=140)
            if st.button("创建并进入该岗", key="nj_btn", use_container_width=True):
                if jd_up is not None:
                    jd_bytes = jd_up.getvalue()
                    new_job = create_job(title, jd_bytes=jd_bytes, jd_name=jd_up.name)
                elif jd_paste.strip():
                    new_job = create_job(title, jd_text=jd_paste)
                else:
                    new_job = create_job(title)
                st.session_state["job_pick_chat"] = new_job["job_code"]
                st.success(f"已创建：{new_job['job_code']}")
                st.rerun()

        st.divider()
        step_name_map = {s["no"]: s["name"] for s in STEPS}
        step_no = st.radio("当前测试步骤", [s["no"] for s in STEPS],
                           format_func=lambda n: step_name_map[n],
                           index=0, key="cur_step")
        cur_step = next(s for s in STEPS if s["no"] == step_no)
        st.caption(cur_step["tag"])

        st.divider()
        with st.expander("⚙️ 运行设置"):
            stub = st.checkbox("假执行（界面自测，不调 API）",
                               value=os.environ.get("M3CHAT_STUB") == "1", key="stub_mode")
            env_path = st.text_input(".env 路径", value=str(DEFAULT_ENV), key="env_path")
            st.caption("真执行需要 .env 里有 DEEPSEEK_API_KEY；阻塞式，长任务请耐心等待或点页面右上角 Stop。")

        st.divider()
        with st.expander("📒 纠错成长账（原始账）"):
            total = len(list_records())
            st.caption(f"全部记录 {total} 条（data/growth/records.jsonl，只增不改）。"
                       "消化成规则后写入 data/prompts/rules.md，下次干活自动生效。")
            note = st.text_area("记一笔：助理哪里不对 / 应该怎样", key="rec_note", height=90)
            tags = st.text_input("主题标签（逗号分隔）", key="rec_tags",
                                 placeholder="如：评分口径,关键字选词,汇报形态")
            if st.button("✍️ 记录纠错（成长数据）", key="rec_btn", use_container_width=True):
                if not note.strip():
                    st.warning("批注为空，未记录。")
                else:
                    job = next((j for j in jobs if j["job_code"] == st.session_state.get("job_pick_chat")), None)
                    if job is None:
                        st.warning("请先选择岗位会话。")
                    else:
                        append_record(job, cur_step["no"], note, tags)
                        st.success("已记入成长账（待消化）。")
                        st.rerun()
            recents = list_records()[-5:][::-1]
            if recents:
                st.markdown("**最近记录**")
                for r in recents:
                    st.caption(f"· [{r['step_name']}] {r['note'][:36]}{'…' if len(r['note']) > 36 else ''} ({r['ts'][5:16]})")
        return {"jobs": jobs, "step": cur_step, "stub": stub, "env_path": Path(env_path)}


def render_main(cfg: dict) -> None:
    jobs = cfg["jobs"]
    if not jobs:
        st.info("先在左侧「➕ 新建岗位会话」创建一个岗位（粘贴/上传 JD），再开始第一步测试。")
        return
    pick = st.session_state.get("job_pick_chat") or jobs[0]["job_code"]
    job = next((j for j in jobs if j["job_code"] == pick), jobs[0])

    # ── 头部：当前岗 + 步骤
    st.markdown(f"### 🗣 {job['title'] or job['job_code']}")
    st.caption(f"岗位 {job['job_code']} · 会话 {job['session_id']} · 创建于 {job['created_at']}　|　"
               f"当前测试步骤：**{cfg['step']['name']}**")

    # 产物预览（助理生成的报告/HTML 过程文档）
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

    # ── 对话历史
    for m in load_transcript(job["job_code"]):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            for a in m.get("artifacts") or []:
                st.caption(f"📎 {a}")

    # ── 快捷指令（先测步骤①）
    quick = None
    if cfg["step"]["no"] == 1:
        quick = st.button("🚀 步骤①：执行岗前分析并生成 HTML 过程文档", key="quick_step1",
                          use_container_width=True,
                          disabled=not (_job_dir(job) / "jd.txt").exists())
        if quick:
            quick = build_step1_task(job)

    prompt = st.chat_input("跟小猎说话：发指令 / 追问 / 讨论（Enter 发送）…")
    if prompt or quick:
        msg = prompt if prompt else quick
        append_msg(job["job_code"], "user", msg)
        try:
            with st.status("小猎工作中（阻塞式，长任务请耐心等待）…", expanded=False) as status:
                reply, new_files = run_assistant(job, msg, cfg["env_path"], stub=cfg["stub"])
                status.update(label="小猎完成", state="complete")
        except Exception as e:
            reply = f"⚠️ 执行出错：{e}\n\n（若是 .env/API 问题请检查侧栏运行设置；界面自测请开「假执行」）"
            new_files = []
        append_msg(job["job_code"], "assistant", reply,
                   artifacts=[p.name for p in new_files])
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="数字合伙人 · 对话汇报（v1.5）", page_icon="🗣", layout="wide")
    st.markdown("# 🗣 数字合伙人 · 对话式汇报")
    st.caption("v1.5（DSH Web 迷你版 · 分步骤测试用）｜ 一岗一会话｜ 纠错成长账："
               "`data/growth/records.jsonl` + `data/prompts/rules.md`")
    ensure_rules()
    cfg = render_sidebar()
    render_main(cfg)


if __name__ == "__main__":
    main()
