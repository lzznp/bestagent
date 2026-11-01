# -*- coding: utf-8 -*-
"""search_rounds（②搜索体检·轮次执行器）本地单测：**不起浏览器、0 token**。

跑法（bestagent 目录，lzstudy 解释器）：python test_search_rounds.py

测的都是这次新能力的**脆点**，而不是代码的表面：
1. `parse_total` —— 从页面纯文本里读「共N位人选」（这次唯一的新解析逻辑；页面写法一变就失效）
2. `load_plan` —— 小猎给的"轮次计划"契约（一轮一个关键字：多关键字必须**硬失败**，否则报告里分不清因果）
3. `summarize` —— 小猎据以写结论的 stdout（必须把"读不到"如实说出来，不许含糊）
4. `default_out` —— 产物归岗（有 job_code 就落本岗 reports）
5. 钩子接线 —— `execute_spec` 必须带 `on_step`（recipe_exec 是仓库外代码，改动要有护栏）
"""
import inspect
import json
import sys
from pathlib import Path

WS = Path(r"D:\study\bestagent\bestagent")
sys.path.insert(0, str(WS))
sys.path.insert(0, str(WS.parent / "bridge-agent"))

TMP = WS / "data" / "_selftest_tmp"
TMP.mkdir(parents=True, exist_ok=True)

import report_html as rh  # noqa: E402
import search_rounds as sr  # noqa: E402
from agent.recipe_exec import execute_spec  # noqa: E402

N = 0


def ok(cond, msg):
    global N
    assert cond, f"❌ {msg}"
    N += 1


_I = [0]


def write_plan(obj) -> Path:
    """⚠️ **不能用 tempfile.mkdtemp**：沙箱会给它的产物目录加限制 ACL（写不进、清理 WinError 5）。
    直接在 _selftest_tmp 下用递增文件名，语义等价（test_m3chat_v185_decision.py 为同一个坑绕过一次）。
    """
    _I[0] += 1
    f = TMP / f"rounds_{_I[0]}.json"
    f.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return f


# ── 1) 命中总数解析（新能力的唯一脆点）──
ok(sr.parse_total("隐藏已获取联系方式\n共3000+位人选\n智能排序") ==
   {"total": 3000, "is_plus": True, "total_raw": "共3000+位人选", "found": True},
   "parse_total：共3000+位人选 → 3000（+ 号单独标注）")
ok(sr.parse_total("……共360位人选……")["total"] == 360, "parse_total：共360位人选 → 360")
ok(sr.parse_total("共1,234位人选")["total"] == 1234, "parse_total：千分位共1,234位人选 → 1234")
ok(sr.parse_total("共 3000 位人选")["total"] == 3000, "parse_total：带空格也认")
ok(sr.parse_total("共3000+位人选，另有旧文案共42位人选")["total"] == 3000,
   "parse_total：命中多处时取第一个（页面上的那一处在前）")
bad = sr.parse_total("页面里没有这句话")
ok(bad["found"] is False and bad["total"] is None, "parse_total：读不到 → found=False、total=None（**不猜**）")
ok(sr.parse_total(None)["found"] is False, "parse_total：None 输入不炸")

# ── 2) 轮次计划契约 ──
p = sr.load_plan(write_plan({"job_code": "X", "rounds": [
    {"n": 1, "keyword": " 电气设计 输送线 ", "conds": ["city_current=南京", " education=本科 "], "reason": " 先跑基础池 "},
    {"keywords": ["电控设计 输送线"], "changed": "换叫法", "reason": "看叫法差异"},
]}))
ok([r["keyword"] for r in p["rounds"]] == ["电气设计 输送线", "电控设计 输送线"],
   "load_plan：keyword 去空格；keywords=[一个] 兜底成 keyword")
ok(p["rounds"][0]["conds"] == ["city_current=南京", "education=本科"], "load_plan：conds 去空格")
ok(p["rounds"][0]["reason"] == "先跑基础池", "load_plan：reason 去空格")
ok(p["rounds"][1]["n"] == 2, "load_plan：没写 n 就按序号补")


def _expect_exit(obj, why):
    try:
        sr.load_plan(write_plan(obj))
    except SystemExit:
        ok(True, why)
        return
    ok(False, why + "（**没有**按预期硬失败）")


_expect_exit({"job_code": "X"}, "load_plan：没有 rounds → 硬失败")
_expect_exit({"rounds": []}, "load_plan：rounds 空 → 硬失败")
_expect_exit({"rounds": [{"keyword": ""}]}, "load_plan：某轮没关键字 → 硬失败")
_expect_exit({"rounds": [{"keywords": ["A", "B"]}]},
             "load_plan：一轮给 2 个关键字 → 硬失败（否则报告里分不清是哪条关键字的效果）")

# ── 3) 给小猎看的 stdout 总结 ──
trace = {
    "searches_estimate": 6, "elapsed_sec": 71.2,
    "rounds": [
        {"n": 1, "keyword": "电气设计 输送线", "conds": ["city_current=南京", "education=本科"],
         "total_raw": "共360位人选", "delta_vs_prev": None,
         "steps": [{"group_id": "city_current", "value": "南京", "type": "chips+panel",
                    "verify": True, "total_raw": "共1200位人选"},
                   {"group_id": "keyword", "value": "电气设计 输送线", "type": "input",
                    "verify": True, "total_raw": "共3000+位人选", "stale": True}]},
        {"n": 2, "keyword": "电控设计 输送线", "conds": [],
         "total_raw": "", "delta_vs_prev": None, "verify_failed": True,
         "error": "条件未生效（verify=False）：activity=今天活跃", "steps": []},
    ],
    "notes": ["第 2 轮读不到命中总数"],
}
s = sr.summarize(trace)
ok("电气设计 输送线" in s and "共360位人选" in s, "summarize：带关键字与命中人数")
ok("旧状态，未触发搜索" in s, "summarize：input 类的读数是旧状态 → 明确标注")
ok("读不到命中总数" in s and "条件未生效" in s, "summarize：读不到/条件未生效都如实说出来")

# ── 4) 产物归岗 ──
p2 = sr.load_plan(write_plan({"job_code": "J-CHAT-20260914-172253", "rounds": [{"keyword": "A"}]}))
parts = sr.default_out(p2).parts
ok("chat" in parts and "J-CHAT-20260914-172253" in parts and "reports" in parts and
   sr.default_out(p2).name.startswith("search_rounds_"), "default_out：有 job_code → 落本岗 reports")
p3 = sr.load_plan(write_plan({"job_code": "J-不存在-000000", "rounds": [{"keyword": "A"}]}))
ok("usage" in sr.default_out(p3).parts, "default_out：岗位目录不在 → 落 data/usage")

# ── 5) 钩子接线（recipe_exec 的护栏）──
ok("on_step" in inspect.signature(execute_spec).parameters,
   "execute_spec 带 on_step 钩子（默认 None = 行为不变）")
ok(sr.AUTO_SEARCH_TYPES == ("chips", "chips+panel"),
   "AUTO_SEARCH_TYPES = 配方表 behaviors 里'即点即搜'的那两类")

# ── 6) 过程报告渲染器（②的门面）──
_rt = {
    "job_code": "J-DEMO", "ts": "2026-09-15 18:00:00", "plan_file": "rounds.json",
    "tab_id": 1, "searches_estimate": 7, "elapsed_sec": 96.4,
    "rounds": [
        {"n": 1, "keyword": "电气设计 输送线", "conds": ["city_current=南京", "education=本科"],
         "reason": "先按 JD 硬门槛跑基础池", "changed": "", "found": True,
         "total": 360, "total_raw": "共360位人选", "is_plus": False, "ok": True,
         "steps": [{"group_id": "city_current", "value": "南京", "type": "chips+panel",
                    "verify": True, "found": True, "total": 1200, "total_raw": "共1200位人选"},
                   {"group_id": "education", "value": "本科", "type": "chips", "verify": True,
                    "found": True, "total": 360, "total_raw": "共360位人选"}]},
        {"n": 2, "keyword": "音飞储存 电气", "conds": ["city_current=南京"], "reason": "换竞品打法",
         "changed": "换关键字、撤掉学历", "found": False, "total": None, "total_raw": "",
         "ok": True, "steps": []},
        {"n": 3, "keyword": "电气设计 输送线", "conds": [],
         "reason": "验活跃度", "changed": "加活跃度", "found": False, "total": None, "total_raw": "",
         "ok": False, "verify_failed": True, "error": "条件未生效（verify=False）：activity=今天活跃",
         "steps": []},
    ],
    "conclusion": "带南京+本科那次命中 360，换「音飞储存 电气」这条竞品打法时页面读不到总数（不猜）；"
                  "活跃度那条条件没生效（verify 硬失败），本轮白跑，已如实记下。",
    "highlights": ["学历条件砍人最多", "活跃度那条没生效，需要重跑"],
}
_h = rh.render_search_rounds("示例岗位", _rt)
ok("命中总人数" in _h and "360" in _h, "render：每轮命中总人数上表")
ok("读不到" in _h, "render：读不到的轮次如实标'读不到'（不猜）")
ok("砍人最多" in _h and "-840" in _h, "render：本地算出'砍人最多的一步'（1200 → 360 = -840）")
ok("没调 extract" in _h and "不抓人" in _h, "render：页脚声明'只读、不抓人'")
ok("条件没生效" in _h and "verify=False" in _h, "render：条件未生效（硬失败）单独告警")
ok("示例岗位" in _h and "J-DEMO" in _h, "render：标题与岗位号")
_lot = dict(_rt, conclusion="长" * 500)
_hl = rh.render_search_rounds("T", _lot)
ok("已截断" in _hl and "总结论" in _hl, "render：小猎叙述超预算 → 本地硬顶并标注")
ok("500" not in _hl.split("长度预算")[0].replace("360", ""), "render：截的是叙述，不是命中人数（360 仍在）")
ok("dry-run 计划稿" in rh.render_search_rounds("T", dict(_rt, dry_run=True)),
   "render：dry-run 轨迹要明确标'没真开浏览器'")
ok("没有给结论" in rh.render_search_rounds("T", {k: v for k, v in _rt.items() if k != "conclusion"}),
   "render：小猎没给结论时不编，明说'只有事实没有判断'")
_cu = rh.clip_search_text(_lot)[1]
ok(_cu["total"] <= _cu["budget"], f"clip_search_text：合计不越硬顶（{_cu['total']}/{_cu['budget']}）")

# ── 7) 接线（面板 ↔ 体检）：任务书契约 / 动作归类 / 计划判分 / 本地渲染落盘 ──
#    导入 m3_chat 本身就是一条断言：接线没写坏、引用没断。
import m3_chat as m3  # noqa: E402

_job = {"job_code": "J-CHAT-20260914-172253", "display_name": "测试岗"}
_t = m3.build_step2_probe_task(_job)
ok("【搜索体检】" in _t, "任务书：标题就写明是搜索体检（不是②采集）")
ok("search_rounds.py" in _t and "--plan" in _t and "--out" in _t, "任务书：给了真跑命令（plan/out 都写全）")
ok("一轮只放 1 个关键字" in _t, "任务书：硬规矩『一轮一个关键字』")
ok("不许估、不许拿上一轮的数字顶替" in _t, "任务书：命中数读不到不许估、不许顶替")
ok("只读人数、不抓人" in _t and "不许 extract" in _t, "任务书：只读不抓人（与②采集划清界线）")
ok("search_probe_concl_" in _t and "conclusion" in _t, "任务书：结论小 JSON 的路径与字段都给了")
ok("可选条件清单" in _t, "任务书：注入了配方表合法值清单（不许自己编）")
ok("jd.txt" in _t and "analyze_" in _t, "任务书：JD 与①分析路径")

ok(m3.kind_of_task("老板要你执行【搜索体检】：你自己定几轮") == "probe", "归类：搜索体检 → probe")
ok(m3.kind_of_task("老板要你执行【步骤② 正式采集·第一步：出计划】") == "collect_plan",
   "归类回归：②采集出计划**没有**被搜索体检的分支吞掉")
ok(m3.kind_of_task("老板已确认【步骤② 正式采集】计划。") == "collect_run", "归类回归：②采集执行")
ok(m3.kind_of_task("老板要你执行【步骤① 岗前分析】") == "analyze", "归类回归：①分析")

_good = write_plan({"job_code": "X", "rounds": [
    {"n": 1, "keyword": "电气设计 输送线", "conds": ["city_current=南京", "education=本科"], "reason": "基础盘"},
    {"n": 2, "keyword": "电控设计 输送线", "conds": ["city_current=南京", "activity=今天活跃"], "reason": "换叫法"},
]})
_cg = m3.local_checks.check_probe_plan(_good)
ok(_cg["ok"] is True and "本地校验通过" in _cg["summary"], "判分：合规体检计划 → 通过")
_bad = write_plan({"job_code": "X", "rounds": [
    {"n": 1, "keyword": "电气设计 输送线", "conds": ["years=5-8年"], "reason": "乱写档位"},
    {"n": 2, "keyword": "电气设计 输送线", "conds": ["years=5-8年"], "reason": "原样再来一次"},
]})
_cb = m3.local_checks.check_probe_plan(_bad)
ok(_cb["ok"] is False and "不在配方表的合法档里" in _cb["summary"], "判分：假档位（5-8年）被判问题")
ok(any("一模一样" in w for w in _cb["warnings"]), "判分：两轮完全相同 → 提醒（白烧一次搜索）")
_mk = write_plan({"rounds": [{"keywords": ["A", "B"]}]})
ok(m3.local_checks.check_probe_plan(_mk)["ok"] is False, "判分：一轮 2 个关键字 → 判问题")

# 本地渲染落盘（面板那段接线的真身）：轨迹 + 小猎的结论小 JSON → *_过程.html
_trp = TMP / "wire_probe_trace.json"
_trp.write_text(Path(WS, "data", "usage", "_smoke_rounds_demo.json").read_text(encoding="utf-8"),
                encoding="utf-8")
_cfp = TMP / "wire_probe_concl.json"
_cfp.write_text(json.dumps({"conclusion": "小猎的结论：南京+本科=360，活跃度最狠", "highlights": ["要点一"]},
                           ensure_ascii=False), encoding="utf-8")
_hp = m3.render_probe_html(_job, _trp, _cfp)
_hx = _hp.read_text(encoding="utf-8")
ok(_hp.exists() and _hp.name.endswith("_过程.html"), "接线：本地渲染落盘成 search_rounds_*_过程.html")
ok("小猎的结论：南京+本科=360，活跃度最狠" in _hx, "接线：小猎的结论小 JSON 被并进报告")
ok("360" in _hx and "读不到" in _hx, "接线：报告里有真数字，也有'读不到'的如实标注")
ok(m3.latest_probe_trace(_job) is None or m3.latest_probe_trace(_job).name.startswith("search_rounds_"),
   "接线：轨迹发现函数只认 search_rounds_*.json")

# ── 8) stale 读数不许参与"砍人最多"（2026-09-15 真跑踩到的假因果）──
_kt = {"rounds": [{
    "n": 1, "keyword": "K", "conds": ["city_current=南京"], "reason": "", "changed": "",
    "found": True, "total": 142, "total_raw": "共142位人选",
    "steps": [
        {"group_id": "keyword", "value": "K", "type": "input", "verify": True, "found": True,
         "total": 3000, "total_raw": "共3000+位人选", "stale": True},
        {"group_id": "city_current", "value": "南京", "type": "chips+panel", "verify": True,
         "found": True, "total": 142, "total_raw": "共142位人选"},
    ]}]}
_kh = rh.render_search_rounds("T", _kt)
ok("-2858" not in _kh, "render：旧状态读数**不参与**'砍人最多'（否则算出 3000→142 = -2858 的假因果）")
ok("3000" in _kh and "旧状态" in _kh, "render：旧状态读数仍**如实列出**（只是不算进减法）")

print(f"\n✅ test_search_rounds：{N} 条断言全绿")
