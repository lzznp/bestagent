#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent/agent.py — 浏览器 Agent 命令行入口（薄壳，逻辑在 agent/core.py）

用法：
    python agent/agent.py "帮我看看猎聘 Python 岗位搜索结果，提取前几条候选人"
    python agent/agent.py "打开 https://www.liepin.com" --max-steps 15
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

# Windows 管道/控制台默认 GBK 编码，on_step 打印的 emoji（📸🧠等）会 UnicodeEncodeError
# （GBK 无法编码 \U0001f4f8）。强制 UTF-8 输出，保证任意终端/管道下不崩。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8080")

from core import (  # noqa: E402  同目录导入
    run_loop,
    bridge_get,
)
from db import (  # noqa: E402  P2-5：多 Agent 数据库桥（candidates 入库）
    insert_candidates as db_insert_candidates,
    site_for_url as db_site_for_url,
)


def _bridge_port():
    """从 BRIDGE_URL 解析端口（默认 8080）。"""
    try:
        return urlparse(BRIDGE_URL).port or 8080
    except Exception:
        return 8080


def _port_listening(port):
    """探测端口是否已被占用（TCP 连接成功即视为占用）。"""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1.0):
            return True
    except OSError:
        return False


def ensure_bridge():
    """检测桥接服务是否在线；不在线则自动拉起（Windows 无窗口后台运行）。

    P2-6（根治双进程）：先健康检查，在线直接复用；health 失败但端口已被占用
    （僵死/异常实例）时不重复 Popen，避免同时存在两个 bridge 进程。
    """
    try:
        bridge_get(BRIDGE_URL, "/api/health")
        return True
    except Exception:
        pass
    port = _bridge_port()
    if _port_listening(port):
        # 端口占用但 health 失败：可能实例正在启动，短等后重试
        for _ in range(4):
            time.sleep(0.5)
            try:
                bridge_get(BRIDGE_URL, "/api/health")
                return True
            except Exception:
                continue
        print(f"[agent] ⚠️ 端口 {port} 已被占用但桥接服务无响应（可能为僵死/异常实例）。"
              f"请检查 logs/bridge.log，或结束占用 {port} 的进程后重试。")
        return False
    bridge_script = os.path.join(ROOT, "bridge", "server.py")
    log_path = os.path.join(ROOT, "logs", "bridge.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    with open(log_path, "a", encoding="utf-8") as logf:
        subprocess.Popen(
            [sys.executable, bridge_script],
            cwd=ROOT,
            stdout=logf,
            stderr=logf,
            creationflags=flags,
            close_fds=True,
        )
    for _ in range(20):  # 最多等 10 秒
        time.sleep(0.5)
        try:
            bridge_get(BRIDGE_URL, "/api/health")
            return True
        except Exception:
            continue
    return False


def save_run(task_desc, events, final):
    record = {
        "task": task_desc,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "final": final,
        "events": events,
    }
    name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    path = os.path.join(ROOT, "logs", "agent_runs", name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"\n[agent] 运行记录已保存: {path}")


def _build_mock_llm(spec):
    """P3-T7：把 --mock-llm 的 JSON 动作序列解析成 mock LLM 回调。

    spec 形如 '[{"action":"snapshot"},{"action":"finish","summary":"ok"}]'；
    循环消费序列；耗尽后默认输出 snapshot（等序列耗尽即 step_limit 或手动终止）。
    返回 None 表示不启用 mock（走真实 LLM）。
    """
    if not spec:
        return None
    try:
        seq = json.loads(spec)
        assert isinstance(seq, list) and seq
    except Exception as e:
        print(f"[agent] ⚠️ --mock-llm 解析失败（{e}），回退真实 LLM")
        return None
    state = {"i": 0}

    def mock(messages, api_key):
        if state["i"] < len(seq):
            act = seq[state["i"]]
            state["i"] += 1
            return json.dumps(act, ensure_ascii=False)
        return '{"action":"snapshot","reason":"mock 序列耗尽"}'

    return mock


def main():
    global BRIDGE_URL
    ap = argparse.ArgumentParser(description="浏览器 Agent（LLM tool-use 循环）")
    ap.add_argument("task", nargs="*", help="自然语言任务描述")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--bridge", default=BRIDGE_URL, help="桥接服务地址")
    ap.add_argument("--page-delay-min", type=float, default=2.0,
                    help="翻页间隔随机化下限（秒），click 成功后随机等待，防风控")
    ap.add_argument("--page-delay-max", type=float, default=4.0,
                    help="翻页间隔随机化上限（秒）；设 0 关闭翻页延迟")
    ap.add_argument("--risk-check", choices=("on", "off"), default="on",
                    help="验证码/登录过期检测（默认 on；off 关闭风控拦截）")
    ap.add_argument("--tab-id", type=int, default=None,
                    help="P2-5：钉住操作目标标签页 id（所有注入型动作固定作用于此标签，不依赖激活页；"
                         "多标签切换类任务不要用）")
    ap.add_argument("--dry-run", action="store_true",
                    help="P3-T7：只读试跑模式——只执行只读动作（snapshot/scroll/extract/list_tabs/verify_site），"
                         "写动作（click/type/navigate 等）被拦截，用于新站/新任务先看 LLM 决策")
    ap.add_argument("--mock-llm", default=None,
                    help="P3-T7：mock LLM 动作序列（JSON 数组，如 '[{\"action\":\"snapshot\"},{\"action\":\"finish\",\"summary\":\"ok\"}]'），"
                         "代替真实 LLM 调用，确定性测扩展链路")
    ap.add_argument("--no-persist", action="store_true",
                    help="P3-T8：关闭入库——任务照跑，结果不写 SQLite（candidates 不入库），由调用方自行消费")
    ap.add_argument("--no-sink", action="store_true",
                    help="P4-V-T3：关闭经验沉淀——成功任务不自动写回经验库（默认开；高置信自动写回，低置信仅起草）")
    args = ap.parse_args()
    if not args.task:
        ap.print_help()
        sys.exit(1)
    BRIDGE_URL = args.bridge
    task_desc = " ".join(args.task)

    if not ensure_bridge():
        print("❌ 桥接服务启动失败（日志见 logs/bridge.log）")
        sys.exit(1)

    events = []

    def on_step(ev):
        events.append(ev)
        t = ev.get("type")
        step = ev.get("step", "")
        if t == "start":
            print(f"[agent] 任务：{ev.get('task')}")
            print(f"[agent] 桥接服务: {ev.get('bridge')} | 模型: {ev.get('model')}")
        elif t == "snapshot":
            print(f"\n[第{step}步] 📸 快照: {ev.get('title')} ({ev.get('url')}) 元素数={ev.get('element_count')}")
        elif t == "think":
            print(f"[第{step}步] 🧠 决策: {json.dumps(ev.get('action'), ensure_ascii=False)[:300]}")
        elif t == "act":
            status = "✅ 成功" if ev.get("ok") else f"❌ 失败: {ev.get('error')}"
            print(f"[第{step}步] 🖱️ {ev.get('action')} {status}")
        elif t == "retry":
            print(f"[第{step}步] 🔁 {ev.get('action')} 第 {ev.get('attempt')}/{ev.get('max_retries')} 次重试（原因: {ev.get('error')}）")
        elif t == "finish":
            print(f"\n✅ 任务完成: {ev.get('summary')}")
            if ev.get("data"):
                print("结果数据:")
                print(json.dumps(ev.get("data"), ensure_ascii=False, indent=2))
        elif t == "error":
            print(f"❌ {ev.get('message')}")
        elif t == "step_limit":
            print(f"\n⚠️ {ev.get('message')}")
        elif t == "stuck":
            print(f"\n🔄 无进展终止（第{step}步）: {ev.get('message')}")
        elif t == "risk_blocked":
            print(f"\n⛔ 风控拦截（第{step}步）: {ev.get('reason')}")

    final = run_loop(task_desc, BRIDGE_URL, max_steps=args.max_steps, on_step=on_step,
                     page_delay_min=args.page_delay_min, page_delay_max=args.page_delay_max,
                     risk_check=(args.risk_check == "on"), tab_id=args.tab_id,
                     dry_run=args.dry_run, mock_llm=_build_mock_llm(args.mock_llm))
    # P4-V-T3：成功任务自动沉淀经验（真实 LLM run 且未关 sink 才沉淀；
    # mock/dry-run 不是真实执行，不污染经验库）
    if final.get("ok") and not args.no_sink and not args.dry_run and not args.mock_llm:
        try:
            from experience import sink_after_run
            _sink = sink_after_run(events, final, tab_id=args.tab_id)
            if _sink:
                if _sink.get("written"):
                    _e = _sink.get("entry") or {}
                    print(f"[agent] 🧠 经验沉淀：v{_e.get('version')} id={_e.get('id')}（{_sink.get('reason')}）")
                else:
                    print(f"[agent] 🧠 经验起草待人工确认：{_sink.get('reason')}")
        except Exception as e:
            print(f"[agent] ⚠️ 经验沉淀失败: {e}")
    # P2-5：Agent finish 后 candidates 批量入库（source_id 去重，供其他 Agent 查表）
    # P3-T8：--no-persist 时跳过入库（任务照跑、结果不落库）
    if final.get("ok") and not args.no_persist:
        data = final.get("data") or {}
        cands = data.get("candidates") or []
        if cands:
            run_url = data.get("url") or ""
            site = db_site_for_url(run_url) if run_url else None
            run_id = f"cli-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                ins, skp = db_insert_candidates(cands, run_id=run_id, site=site, url=run_url)
                print(f"[agent] 候选人入库：新增 {ins} 条，去重跳过 {skp} 条")
            except Exception as e:
                print(f"[agent] ⚠️ candidates 入库失败: {e}")
    save_run(task_desc, events, final)
    sys.exit(0 if final.get("ok") else 1)


if __name__ == "__main__":
    main()
