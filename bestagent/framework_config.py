#!/usr/bin/env python3
"""数字合伙人框架集中配置：所有环境路径/默认参数在此一处定义。

换电脑/换环境时只需：
  1) `pip install -r requirements.txt`（装 pinned 版 SDK + 自带运行时 exe，229MB）；
  2) 或用环境变量覆盖：DSP_WORKSPACE / DSP_DSH_HOME / BROWSER_AGENT_PATH / DSP_MODEL。

三层运行边界（见《工作模式·备忘》§1.1）：
  - 运行环境 = pip 锁版本的 deepseek-harness-sdk + deepseek-harness-runtime-bin + 项目自带 DSH_HOME；
  - 项目绝不读 `~/.dsh`（GUI 的家），也绝不 `sys.path.insert(... DSH 源码 ...)`（否则源码遮蔽 pip 包）；
  - 业务资产（data/ 下的岗位目录 / rules.md / 产物 / business.db）不依赖任何 SDK 版本。

2026-09-10 换代要点（详见《DSH升级事故·衔接报告》§8.9）：
  旧 = 手写 cordis 组合 + session_root + launch_args_override + 挂源码 checkout（已全部作废）；
  新 = profile="sdk" + dsh_home（项目自带）+ patches（persona）+ DSH_PERMISSION_MODE；不传 dsh_bin（走 exe）。
  调用方一律用 make_harness()，不要再自己拼 DeepSeekHarness(...)。
"""
from __future__ import annotations

import os
from pathlib import Path

# ── 项目根与数据目录（相对定位，不写死机器路径）───────────────────
WORKSPACE = Path(os.environ.get("DSP_WORKSPACE", Path(__file__).resolve().parent))
DATA = WORKSPACE / "data"
INBOX = DATA / "inbox"
OUTBOX = DATA / "outbox"
PROMPTS = DATA / "prompts"
USAGE = DATA / "usage"
DB_PATH = DATA / "business.db"

# ── 历史遗留：旧版 SDK 的会话落盘目录（新版改用 DSH_HOME/sessions，本目录只存旧 JSONL）──
SESSIONS = WORKSPACE / ".sessions"

# ── SDK 运行环境（pip wheel / exe 模式；换电脑时核对）───────────────
SDK_VERSION = "0.1.5rc1"                      # 必须与 requirements.txt 一致
REQUIREMENTS_FILE = WORKSPACE / "requirements.txt"
# 项目自带 harness home（与 GUI 的 ~/.dsh 彻底隔离；已 gitignore）
DSH_HOME = Path(os.environ.get("DSP_DSH_HOME", DATA / "dsh_home"))
# 工具面（文件工具 + pwsh 工具 + 沙箱 + 会话落盘都在这个 profile 里）
DSH_PROFILE = os.environ.get("DSP_DSH_PROFILE", "sdk")
# persona patch：由 write_persona_patch() 从调用方的 PERSONA 常量单源生成
PERSONA_PATCH = DSH_HOME / "persona.patch.yml"
# sdk profile 原生的收尾提示（patch 是整行替换 config，必须一并重述）
DEFAULT_PERSONA_SUFFIX = "Your working directory is {{cwd}}."
# 无头运行：danger-full-access 时 approval 自动为 never（见 §8.2）
PERMISSION_MODE = os.environ.get("DSP_PERMISSION_MODE", "danger-full-access")
INITIALIZE_TIMEOUT = 180.0                    # exe 首跑要自解压，给足时间
SHUTDOWN_TIMEOUT = 10.0

# ── 浏览器采集（桥 = 本仓库顶层 bridge-agent/，2026-09-11 从 D:\study\lietou-agent 搬入）──
# 为什么必须搬进仓库：采集脚本要 `sys.path.insert(BROWSER_AGENT)` 直接 import
#   `agent.core` / `agent.recipe_exec`（配方表执行器 = 我们自己的资产）→
#   目录留在仓库外就是"底座挂在别人目录上"（同 DSH 源码那次的病，见《工作模式·备忘》§1.1）。
# 桥要老板/参谋长另起 —— m3_chat/采集脚本只"连"它，不"拉"它（见《工作模式·备忘》§3）。
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8080")
BROWSER_AGENT = Path(
    os.environ.get("BROWSER_AGENT_PATH") or (WORKSPACE.parent / "bridge-agent")
)

# ── 模型与 token（大池子评估分批 ≤72 人/批，32768 上限，见 HANDOFF 教训 5）─
MODEL = os.environ.get("DSP_MODEL", "deepseek-v4-flash")
MAX_TOKENS_ANALYZE = 4096   # 岗前分析（单 JD 输出小）
MAX_TOKENS_EVAL = 32768     # 池子评估（多人评分写报告）
MAX_TOKENS_AUTO = 16384     # agent 自主闭环
EVAL_BATCH = 72             # 评估分批人数上限
REQUEST_TIMEOUT = 1200      # SDK 请求超时（秒）


def ensure_dirs() -> None:
    for d in (INBOX, OUTBOX, PROMPTS, USAGE, SESSIONS, DSH_HOME):
        d.mkdir(parents=True, exist_ok=True)


def load_env_file(path) -> dict[str, str]:
    """从 .env 读取 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL（不打印值）。"""
    from pathlib import Path as _P
    env: dict[str, str] = {}
    for line in _P(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL") and v.strip():
            env[k] = v.strip().strip('"').strip("'")
    return env


# ═══════════════════════ SDK 启动（唯一入口）═══════════════════════

def write_persona_patch(persona: str, suffix: str = DEFAULT_PERSONA_SUFFIX) -> Path:
    """把 persona 文本渲染成 profile 的 system-prompt patch，返回 patch 路径。

    用途：人设单源（调用方的 PERSONA 常量）→ 落一个 YAML 文件 → 交给 make_harness(patches=…)。
    ⚠️ patch 按 id 定位会【整行替换 config】→ 必须重述要保留的每个键（故 personaSuffix 一并写）。
    """
    def block(text: str) -> str:
        lines = (text or "").strip().splitlines() or [""]
        return "\n".join(("      " + ln) if ln.strip() else "" for ln in lines)

    PERSONA_PATCH.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# 自动生成，勿手改：人设单源在各脚本的 PERSONA 常量（framework_config.write_persona_patch）\n"
        "- id: system-prompt\n"
        "  config:\n"
        "    personaPrefix: |-\n"
        f"{block(persona)}\n"
        "    personaSuffix: |-\n"
        f"{block(suffix)}\n"
    )
    PERSONA_PATCH.write_text(text, encoding="utf-8")
    return PERSONA_PATCH


# ═══════════════════════ 工具面分档（按动作给"手"）═══════════════════════
# 2026-09-14 实测依据（一次①岗位分析 8 轮）：
#   · 25 个 tool schema = 25,907 字符 ≈ 6,481 token，**每轮都付**；
#   · 8 轮里实际只调用了 read/write/glob；全项目 10 个会话只调用过 4 个工具；
#   · 首轮固定前缀 ≈ 7,430 token（system 4,627 字符 + 25 工具），与用户消息长短几乎无关。
# 机制：dsh-base 的 cordis.patch.yml 是**按 row id 分行挂载**工具插件的，
#   later layer 可按 id 覆盖/关闭 → 关掉的插件不挂载 = 工具从模型侧消失且调用被拒。
#   （注：SDK 文档里的 `toolFilter` 只作用于 subagent 子 agent，顶层 headless run 用不了它。）
# 约束：同一 npm 包里的工具是"整包"的（tool-fs 同时提供 read/write/edit/read_image），
#   所以行级分档关不掉 edit/read_image —— 无害，它俩不会被调用，只占 1,832 字符。
TOOL_PROFILES: dict[str, tuple[str, ...]] = {
    # bare：纯文件任务（①岗位分析 / ②出计划 / ③池子评估 / 打招呼 / 发岗文字 / 自由对话）
    #   保留 tool-fs（read/write）+ 文件系统底座；关掉命令/搜索/网页/分身/工作流/目标/待办等。
    "bare": (
        "tool-pwsh",                  # 跑命令（②采集执行才需要）
        "tool-jobs",                  # job_list / job_output / job_kill
        "tool-fs-search",             # glob / grep（任务里路径已写全 → 用不到，且能物理堵住"列目录找路"）
        "tool-skill",                 # 技能目录还不存在
        "tool-todo",                  # todo_write
        "tool-goal",                  # create_goal / get_goal / update_goal
        "tool-ralph",                 # ralph
        "tool-workflow",              # workflow（第二贵，3,986 字符，从没用过）
        "tool-subagent",              # subagent
        "tool-subagent-fork",         # subagent_fork
        "tool-subagent-control",      # send_message
        "tool-subagent-list-agents",  # list_agents
        "plan-mode",                  # exit_plan_mode
        "tool-web",                   # web_search / web_fetch（§2.2 点名的"只有 persona 一句话防线"）
    ),
}
TOOL_PATCHES_DIR = DSH_HOME  # 与 persona.patch.yml 同处（DSH_HOME 已 gitignore，本目录内容由本模块生成）


def write_tool_patch(profile: str) -> Path:
    """把工具面分档渲染成 profile 的 patch 文件，返回路径。

    单源 = 本模块 TOOL_PROFILES（同 write_persona_patch：自动生成，勿手改）。
    """
    rows = TOOL_PROFILES.get(profile)
    if rows is None:
        raise ValueError(f"未知工具面分档 '{profile}'；可选：{sorted(TOOL_PROFILES)}")
    out = TOOL_PATCHES_DIR / f"tool_{profile}.patch.yml"
    TOOL_PATCHES_DIR.mkdir(parents=True, exist_ok=True)
    text = (
        "# 自动生成，勿手改：工具面分档单源在 framework_config.TOOL_PROFILES\n"
        "# 按 row id 关闭 dsh-base 挂载的工具插件（关掉 = 不挂载 = 工具从模型侧消失且拒绝执行）\n"
        + "".join(f"- id: {rid}\n  disabled: true\n" for rid in rows)
    )
    out.write_text(text, encoding="utf-8")
    return out


def make_harness(
    env: dict[str, str] | None = None,
    max_tokens: int = MAX_TOKENS_AUTO,
    *,
    persona: str | None = None,
    tool_profile: str | None = None,
    cwd: Path | str | None = None,
    initialize_timeout_seconds: float = INITIALIZE_TIMEOUT,
    request_timeout_seconds: float = REQUEST_TIMEOUT,
    shutdown_timeout_seconds: float = SHUTDOWN_TIMEOUT,
    **overrides,
):
    """构造一次运行的 SDK 运行时（新版 API：profile + dsh_home + patches）。

    - **exe 模式**：不传 dsh_bin → SDK 自动用 pip 装的 deepseek-harness-runtime-bin
      （自带 node 运行时；不需要 DSH 源码 checkout / 不需要系统 node / 不需要 .dsh-staging）。
    - **项目自带 home**：DSH_HOME=<项目>\data\dsh_home → 会话与 GUI 的 ~/.dsh 完全隔离。
    - **persona**：传入则写 PERSONA_PATCH（单源）并注入；不传则沿用已有 patch（没有再报错）。
    - **tool_profile**：工具面分档（见 TOOL_PROFILES）。传了就按 row id 关掉用不到的工具插件，
      省下"每轮固定租金"；不传 = 沿用 profile 默认的全量工具面。
    - **沙箱**：DSH_PERMISSION_MODE=danger-full-access（无头运行，approval 自动 never）。
    - **session id**：本版对跨进程路径**不支持复用**（同 id 第二次报 `session "X" already exists`）
      → 调用方每次运行都要用新 id（如 `<job_session_id>-<step>-<时间戳>`），与「不赌会话记忆」铁律一致。

    用法：
        with make_harness(env, max_tokens=8192, persona=PERSONA, tool_profile="bare") as harness:
            result = harness.run(prompt, session_id=f"{job_id}-{int(time.time())}")
    """
    from deepseek_harness import DeepSeekHarness  # 延迟 import：只做自检时不必载 SDK

    run_env = dict(env or {})
    run_env["DSH_PERMISSION_MODE"] = PERMISSION_MODE
    patch_list: list[str] = []
    if persona:
        patch_list.append(str(write_persona_patch(persona)))
    elif "patches" in overrides:
        patch_list.extend(str(p) for p in overrides.pop("patches"))
    elif PERSONA_PATCH.is_file():
        patch_list.append(str(PERSONA_PATCH))
    else:
        raise RuntimeError(
            f"persona patch 不存在且本次未传 persona：{PERSONA_PATCH}\n"
            "调用 make_harness(persona=PERSONA) 一次即可生成（人设缺省会丢）。"
        )
    # 工具面分档（可选）：按 row id 关掉用不到的工具插件 → 工具从模型侧消失（省每轮固定租金）
    if tool_profile:
        patch_list.append(str(write_tool_patch(tool_profile)))
    patches: tuple[str, ...] = tuple(patch_list)

    return DeepSeekHarness(
        profile=DSH_PROFILE,
        dsh_home=str(DSH_HOME),          # 项目自带 home（不碰 ~/.dsh）
        patches=patches,
        cwd=str(cwd or WORKSPACE),
        provider="deepseek-official",
        model=MODEL,
        max_tokens=max_tokens,
        env=run_env,
        initialize_timeout_seconds=initialize_timeout_seconds,
        request_timeout_seconds=request_timeout_seconds,
        shutdown_timeout_seconds=shutdown_timeout_seconds,
        **overrides,
    )


def check_env() -> list[str]:
    """环境自检：返回缺失/异常项列表（空 = 全部就绪）。"""
    problems: list[str] = []

    # 1) SDK 与自带运行时（pip wheel / exe 模式）
    try:
        from importlib.metadata import version as _pkg_version
        got = _pkg_version("deepseek-harness-sdk")
        if got != SDK_VERSION:
            problems.append(
                f"deepseek-harness-sdk 版本不符：本机 {got}，应为 {SDK_VERSION}"
                f"（pip install -r {REQUIREMENTS_FILE}）")
    except Exception:
        problems.append(
            f"未安装 deepseek-harness-sdk=={SDK_VERSION}（pip install -r {REQUIREMENTS_FILE}）")
    try:
        import deepseek_harness_runtime  # noqa: F401
    except Exception:
        problems.append(
            "未安装 deepseek-harness-runtime-bin（SDK 自带的运行时 exe；"
            f"pip install -r {REQUIREMENTS_FILE}）")

    # 2) 铁律：pip 装了就不能让 DSH 源码遮蔽它
    try:
        import deepseek_harness
        where = str(getattr(deepseek_harness, "__file__", ""))
        if "site-packages" not in where:
            problems.append(
                f"deepseek_harness 被非 pip 路径遮蔽：{where}"
                "（脚本里的 sys.path.insert(… DSH 源码 …) 必须删掉）")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"import deepseek_harness 失败：{exc}")

    # 3) 项目自带 home + profile
    if not DSH_HOME.exists():
        problems.append(f"项目 harness home 不存在：{DSH_HOME}（首次 make_harness() 会自动建）")
    elif not (DSH_HOME / "profiles" / DSH_PROFILE).exists():
        problems.append(
            f"home 里 profile『{DSH_PROFILE}』尚未生成：{DSH_HOME / 'profiles' / DSH_PROFILE}"
            "（首次 make_harness() 会自动生成）")

    # 4) persona patch（人设单源产物）
    if not PERSONA_PATCH.is_file():
        problems.append(
            f"persona patch 不存在：{PERSONA_PATCH}"
            "（调用一次 make_harness(persona=PERSONA) 即生成）")

    # 5) 浏览器桥（采集链路要 import 它的 agent.core / agent.recipe_exec；"起没起"要另测 /api/health）
    if not BROWSER_AGENT.exists():
        problems.append(
            f"桥目录缺失：{BROWSER_AGENT}（默认 = 仓库顶层 bridge-agent/；可用 BROWSER_AGENT_PATH 覆盖）")
    else:
        for rel in ("agent/recipe_exec.py", "agent/page_recipes.json", "bridge/server.py"):
            if not (BROWSER_AGENT / rel).exists():
                problems.append(f"桥目录不完整，缺 {rel}：{BROWSER_AGENT}")

    return problems


if __name__ == "__main__":
    issues = check_env()
    print("\n".join(issues) if issues else "OK：SDK / home / profile / persona / 桥目录 全部就绪")
