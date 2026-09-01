#!/usr/bin/env python3
"""M1.1 验证周最小实验：真实 JD → SDK agent 自主岗前分析 → 转猎聘关键字 → 报告 → “老板我弄的咋样”汇报

运行（用 lzstudy conda 环境）：
  C:\\Users\\84005\\miniconda3\\envs\\lzstudy\\python.exe m1_run.py --env-file <path/.env>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows 控制台可能是 GBK：强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 集中配置（换电脑只改 framework_config.py 或环境变量）
from framework_config import (
    WORKSPACE, SESSIONS, PROMPTS, DSH_ROOT, RUNTIME_BIN, CORDIS_MINIMAL,
    MAX_TOKENS_ANALYZE, REQUEST_TIMEOUT, ensure_dirs,
)

sys.path.insert(0, str(DSH_ROOT / "python" / "sdk" / "src"))
sys.path.insert(0, str(DSH_ROOT / "python" / "sdk-runtime" / "src"))

from deepseek_harness import DeepSeekHarness  # noqa: E402

CORDIS = CORDIS_MINIMAL

# 数字合伙人 persona（覆盖 cordis 默认的 software engineer 人设）
PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（一位猎头顾问）跑岗前分析、"
    "转搜索关键字、写报告、做汇报。做事原则：先思考再动手；信息不足时明确提问；"
    "输出务必严格按方法论手册的格式，不擅自改动；干完活主动向老板汇报"
    "（“老板，我弄的咋样？”的口吻）。"
)

def build_task(jd: Path, report: Path) -> str:
    """任务：只给路径与指令，JD 全文与分析方法论由 agent 自己用工具读取（验证真自主）"""
    return f"""老板往 inbox 丢了一条新 JD（禾蛙平台真实职位）。请把下面这条工作链路一次做完，全程用工具完成，不要让我手动粘贴任何内容：

1. 读取你的岗前分析方法论手册（必须严格按它的 JSON 输出格式，不增不减字段）：
   {PROMPTS.as_posix()}/analyze_job.txt

2. 读取 JD 文件：
   {jd.as_posix()}

3. 按手册完成岗前分析：提取岗位信息、判断职位进展、逐项评分（佣金/HC数量/新鲜度/上游靠谱度/匹配难度，各 0-5）、算总分与等级、写清风险清单与一句话建议、判定「接单/沟通/放弃」，并生成 4 组猎聘搜索关键字（精确匹配/职能相近/竞品对标/技能导向）。

4. 把完整 JSON 结果写入文件（用文件工具新建文件，不要用 bash 重定向）：
   {report.as_posix()}

5. 最后用「老板，我弄的咋样？」的口吻，给我一段不超过 6 句的中文汇报：干了什么、这份 JD 值不值得接、我的建议、下一步。这段汇报就是你的最终回复。"""


def load_env_file(path: Path) -> dict[str, str]:
    """从 .env 读取 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL（不打印值）。"""
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL") and v.strip():
            env[k] = v.strip().strip('"').strip("'")
    return env


def analyze_job(jd: Path, report: Path, session_id: str, env: dict,
                max_tokens: int = MAX_TOKENS_ANALYZE,
                request_timeout: int = REQUEST_TIMEOUT,
                workspace: Path = WORKSPACE, session_root: Path = SESSIONS):
    """岗前分析（可独立调用，供 run_pipeline 复用）：SDK agent 读手册+JD → 写报告 → 返回 run 结果。"""
    ensure_dirs()
    outbox = (workspace / report).parent
    outbox.mkdir(parents=True, exist_ok=True)
    with DeepSeekHarness(
        provider="deepseek-official",
        model="deepseek-v4-flash",
        max_tokens=max_tokens,
        cwd=str(workspace),
        session_root=str(session_root),
        cordis=str(CORDIS),
        launch_args_override=("node", str(RUNTIME_BIN)),
        env=env,
        request_timeout_seconds=request_timeout,
        shutdown_timeout_seconds=10,
    ) as harness:
        return harness.run(build_task(jd, report), session_id=session_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--session-id", default="m1-jd1-001")
    parser.add_argument("--jd", type=Path, default=Path("data/inbox/jd_1.txt"))
    parser.add_argument("--report", type=Path, default=Path("data/outbox/report_jd_1.json"))
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    if "DEEPSEEK_API_KEY" not in env:
        print("❌ .env 里没有 DEEPSEEK_API_KEY")
        sys.exit(1)
    env["DSH_SYSTEM_PROMPT"] = PERSONA

    workspace, session_root = WORKSPACE, SESSIONS
    ensure_dirs()

    print(f"▶ runtime: {RUNTIME_BIN.name}")
    print(f"▶ cordis : {CORDIS.name}")
    print(f"▶ model  : deepseek-v4-flash")
    print(f"▶ session: {args.session_id}")
    print(f"▶ jd     : {args.jd}")
    print(f"▶ report : {args.report}")
    print(f"▶ persona: {PERSONA[:50]}…")
    print("─" * 60)

    result = analyze_job(args.jd, args.report, args.session_id, env)

    print("─" * 60)
    print("✅ final_response:")
    print(result.final_response)
    print(f"\n✅ finish_reason: {result.finish_reason}")
    print(f"✅ session_id  : {result.session_id}")
    events = getattr(result, "events", None)
    if events:
        print(f"✅ events      : {len(events)} 个")
    report = workspace / args.report
    print(f"✅ outbox 报告存在: {report.exists()}")


if __name__ == "__main__":
    main()
