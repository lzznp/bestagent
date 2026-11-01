# -*- coding: utf-8 -*-
"""m3_chat v1.8.2 · 省 token 第二刀自测：①过程网页**本地渲染** + 长度预算（纯本地，不调 API）。

跑法（bestagent 目录，lzstudy 解释器）：python test_m3chat_v182_render.py

覆盖（2026-09-15）：
1. 渲染器对**盘上 10 份真 analyze JSON 全部**渲染成功（含没有任何 process 块的老报告）
2. 长度预算是**硬顶**：超长 process 三字段被本地截断，且截断后**不超过**上限（回归 off-by-one）
3. **判断结论不被截断**：超长的 risks / advice / 维度依据在页面上仍然是原文全文
4. 页面自洽：DOCTYPE / 7 个 h2 节 / 无 f-string 占位符残留
5. 接线：m3_chat.render_analyze_html → 落 `analyze_<ts>_过程.html`，且 local_checks 报出「过程叙述 x/600 字」
6. 回归护栏：①任务不再要求它写网页、含 process 契约；判断纪律与「请老板拍板」仍在
"""
import json
import shutil
import sys
from pathlib import Path

import m3_chat
import report_html
import local_checks
from local_checks import check_analyze

PASS = 0
FAIL = 0
CHAT_ROOT = m3_chat.WORKSPACE / "data" / "chat"


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name} {extra}")


def make_tmp_dir(tag: str) -> Path:
    root = m3_chat.WORKSPACE / "data" / "_selftest_tmp" / f"v182_{tag}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def fake_analyze(process=None, risks=None, advice="一句话建议", dim_value="普通依据") -> dict:
    return {
        "jd_extracted": {"job_title": "自测岗", "company": "某公司", "city": "南京",
                         "salary": "20K", "requirements": "本科", "description": "干活"},
        "progress": {"status": "刚发布", "recommended_count": 0, "interviewing_count": 0,
                     "offer_count": 0, "closed_reason": ""},
        "score": {"total": 10, "level": "普通", "advice": advice,
                  "details": {k: {"score": 2, "value": dim_value} for k in
                              ("commission", "hc_count", "freshness", "upstream", "difficulty")},
                  "progress_impact": "刚发布，窗口最好", "risks": risks or ["风险一", "风险二"]},
        "recommendation": "沟通",
        "search_keywords": {"精确匹配": "A B", "职能相近": "C", "竞品对标": "D", "技能导向": "E"},
        **({"process": process} if process is not None else {}),
    }


def test_real_reports() -> None:
    print("[1] 盘上真报告全部可渲染（老报告无 process 也不许炸）")
    jsons = sorted(CHAT_ROOT.glob("*/reports/analyze_*.json"))
    ok, no_proc, with_proc = 0, 0, 0
    for j in jsons:
        data = json.loads(j.read_text(encoding="utf-8-sig"))
        try:
            html = report_html.render_analyze(j.parent.parent.name, data, {"job_code": j.parent.parent.name})
        except Exception as exc:  # noqa: BLE001
            check(f"渲染 {j.name}", False, f"异常 {exc!r}")
            continue
        ok += 1
        check(f"渲染 {j.parent.parent.name} / {j.name}（{len(html.encode('utf-8'))} 字节）",
              "<!DOCTYPE html>" in html and "岗前分析过程文档" in html, "")
        if isinstance(data.get("process"), dict):
            with_proc += 1
        else:
            no_proc += 1
    check(f"真报告共 {len(jsons)} 份全部渲染成功", ok == len(jsons) and len(jsons) >= 1, f"成功{ok}")
    check("覆盖到「老报告无 process」这一形状", no_proc >= 1, f"no_proc={no_proc}")
    print(f"     （有 process {with_proc} 份 / 无 process {no_proc} 份）")


def test_budget_hard_cap() -> None:
    print("[2] 长度预算是硬顶（回归：截断后不许反超上限）")
    b = report_html.ANALYZE_BUDGET
    proc, usage = report_html.clip_process({"process": {
        "keyword_reasoning": "词" * 400,
        "verify_list": [f"第{i}条" + "啊" * 80 for i in range(9)],
        "next_step": "步" * 200}})
    check(f"选词思路 ≤{b['keyword_reasoning']}",
          len(proc["keyword_reasoning"]) <= b["keyword_reasoning"], f"实际{len(proc['keyword_reasoning'])}")
    check(f"待核实 ≤{b['verify_list']} 条", len(proc["verify_list"]) <= b["verify_list"],
          f"实际{len(proc['verify_list'])}")
    check(f"待核实每条 ≤{b['verify_item']}",
          all(len(x) <= b["verify_item"] for x in proc["verify_list"]), "")
    check(f"下一步 ≤{b['next_step']}", len(proc["next_step"]) <= b["next_step"],
          f"实际{len(proc['next_step'])}")
    check(f"合计 <={b['total']}", usage["total"] <= b["total"], f"实际{usage['total']}")
    check("截断被如实记录", len(usage["truncated"]) >= 3, str(usage["truncated"]))
    # 合规输入不该被截断
    _p, u2 = report_html.clip_process({"process": {"keyword_reasoning": "短", "verify_list": ["短"],
                                                   "next_step": "短"}})
    check("合规输入不截断", u2["truncated"] == [] and u2["present"], str(u2["truncated"]))


def test_judgement_not_clipped() -> None:
    print("[3] 判断结论一个字不截（预算只掐过程叙述）")
    long_risk = "风险" * 500
    long_dim = "依据" * 400
    html = report_html.render_analyze("T", fake_analyze(risks=[long_risk], advice="建议" * 300,
                                                        dim_value=long_dim), {})
    check("超长 risks 原文仍在页面上", long_risk in html, "")
    check("超长 advice 原文仍在页面上", ("建议" * 300) in html, "")
    check("超长维度依据原文仍在页面上", long_dim in html, "")
    proc, _u = report_html.clip_process({"process": {"verify_list": ["x" * 500]}})
    check("过程叙述才被截断", proc["verify_list"][0].endswith("…"), proc["verify_list"][0][:20])


def test_page_shape() -> None:
    print("[4] 页面自洽（结构 + 无占位符残留）")
    html = report_html.render_analyze("自测岗", fake_analyze(
        process={"keyword_reasoning": "先精确后职能", "verify_list": ["核实佣金"], "next_step": "先问 PM"}),
        {"job_code": "J-T-1", "created_at": "2026-09-15 09:00:00", "first_time": True,
         "jd_bytes": 123, "artifacts_count": 0, "rules_used": True})
    check("DOCTYPE", html.startswith("<!DOCTYPE html>"), "")
    check("7 个章节", html.count("<h2>") == 7, f"实际{html.count('<h2>')}")
    check("结论徽章渲染", "先沟通再定（recommendation = 沟通）" in html, "")
    check("首次/重跑口径", "首次分析" in html, "")
    check("预算用量写进页脚", "过程叙述" in html and "/600 字" in html, "")
    check("无 f-string 占位符残留",
          not any(x in html for x in ("{esc(", "{meta", "{usage", "{bud", "{title", "{rmeta")), "")
    check("HTML 转义生效", "<script>alert(1)</script>" not in
          report_html.render_analyze("T", fake_analyze(advice="<script>alert(1)</script>"), {}), "")


def test_wiring() -> None:
    print("[5] 接线：render_analyze_html 落盘 + 本地校验报预算")
    tmp = make_tmp_dir("wiring")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师 岗位职责：写测试")
        rp = m3_chat._job_dir(job) / "reports"
        rp.mkdir(parents=True, exist_ok=True)
        jf = rp / "analyze_20260915-120000.json"
        jf.write_text(json.dumps(fake_analyze(process={
            "keyword_reasoning": "先精确后职能", "verify_list": ["核实佣金"],
            "next_step": "先问 PM"}), ensure_ascii=False), encoding="utf-8")
        out = m3_chat.render_analyze_html(job, jf)
        check("落盘名 = analyze_<ts>_过程.html", out.name == "analyze_20260915-120000_过程.html", out.name)
        check("文件存在且非空", out.exists() and out.stat().st_size > 2000, f"{out.stat().st_size}")
        check("标题用了岗位显示名", "自测岗" in out.read_text(encoding="utf-8"), "")
        res = check_analyze(jf)
        check("本地校验报出过程叙述用量", "过程叙述" in res["summary"] and "/600 字" in res["summary"],
              res["summary"])
        check("本地校验通过", res["ok"], str(res["problems"]))
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_task_text() -> None:
    print("[6] ①任务文本回归（不再手写网页 + process 契约）")
    tmp = make_tmp_dir("task")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师 岗位职责：写测试 佣金10万 本科 北京")
        t1 = m3_chat.build_step1_task(job)
        check("明确「过程网页不用你写」", "过程网页不用你写" in t1, "")
        check("含 process 契约", '"process"' in t1 and "keyword_reasoning" in t1, "")
        check("含 600 字预算", "600 字" in t1, "")
        check("不再指定 _过程.html 路径", "_过程.html" not in t1, "")
        check("回归：三选一态度仍在", "接 / 先沟通再定 / 别做" in t1, "")
        check("回归：请老板拍板仍在", "请老板拍板" in t1 and "做吧" in t1, "")
        check("回归：判断纪律仍在", "不诚实必罚" in t1, "")
        check("①工具面仍是 bare（不给 glob）", m3_chat.TOOL_PROFILE_BY_ACTION.get("analyze") == "bare", "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_profile_view() -> None:
    print("[7] 岗位资料展示块（本地渲染，0 花费；老板说的'记进岗位信息'那一环）")
    tmp = make_tmp_dir("profile")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师")
        lines = m3_chat.job_profile_summary(job)
        check("无资料时给建档指引", any("还没有岗位资料" in x for x in lines), str(lines))
        (m3_chat._job_dir(job) / "job_profile.json").write_text(json.dumps({
            "job_code": job["job_code"],
            "pm_notes": ["口径A", "口径B"],
            "special_notes": ["内部关注1"],
            "events": [{"ts": f"2026-09-{i:02d}", "who": "老板", "note": f"事{i}"} for i in range(1, 8)],
        }, ensure_ascii=False), encoding="utf-8")
        txt = "\n".join(m3_chat.job_profile_summary(job))
        check("PM 口径计数正确", "PM / 发单方口径（2 条）" in txt, "")
        check("内部关注计数正确", "客户特殊要求（1 条" in txt, "")
        check("口径原文出现", "口径A" in txt and "口径B" in txt, "")
        check("时间线只显示最新 5 条（共 7）",
              "共 7 条，显示最新 5 条" in txt and "事7" in txt and "事1" not in txt, "")
        (m3_chat._job_dir(job) / "job_profile.json").write_text("{坏 JSON", encoding="utf-8")
        bad = m3_chat.job_profile_summary(job)
        check("坏 JSON 不抛异常、如实说", len(bad) == 1 and "读不出来" in bad[0], str(bad))
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_publish_status() -> None:
    print("[8] 发布状态占位（v1.8.4：只记录不联动，默认 unknown 不许猜）")
    tmp = make_tmp_dir("publish")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师")
        st_ = m3_chat.load_state(job["job_code"])
        check("默认 unknown（不知道 ≠ 没发）", m3_chat.publish_status_of(st_) == "unknown", "")
        check("默认无发布记录", st_.get("liepin_posts") == [], "")
        check("状态位文案含「未知」", "未知" in m3_chat.publish_status_text(st_), "")
        m3_chat.append_publish_post(job["job_code"], {
            "hjob_id": "79866575", "title": "机械工程师", "city": "南京",
            "published_at": "2026-09-11 16:15", "source": "老板口述（面板录入）",
            "extra": "不该进"})
        st_ = m3_chat.load_state(job["job_code"])
        check("记一条 → published", m3_chat.publish_status_of(st_) == "published", "")
        check("记录字段固定（拒绝自造字段）",
              set(st_["liepin_posts"][0]) == set(m3_chat.PUBLISH_POST_KEYS), str(st_["liepin_posts"][0]))
        check("状态位带条数", "1 条记录" in m3_chat.publish_status_text(st_), "")
        m3_chat.append_publish_post(job["job_code"], {"hjob_id": "75383911", "title": "第二条", "city": "苏州"})
        check("双城/重发能记两条（列表结构的意义）",
              len(m3_chat.load_state(job["job_code"])["liepin_posts"]) == 2, "")
        m3_chat.set_publish_status(job["job_code"], "not_published")
        st_ = m3_chat.load_state(job["job_code"])
        check("标未发布 → 状态对且清掉记录（状态与事实不打架）",
              m3_chat.publish_status_of(st_) == "not_published" and st_["liepin_posts"] == [], "")
        check("「未发布」文案与「未知」可区分", "未发布" in m3_chat.publish_status_text(st_), "")
        m3_chat.set_publish_status(job["job_code"], "unknown")
        check("可清回「未知」",
              m3_chat.publish_status_of(m3_chat.load_state(job["job_code"])) == "unknown", "")
        try:
            m3_chat.set_publish_status(job["job_code"], "published")
            check("published 不许手工设（由发布记录决定）", False, "居然没报错")
        except ValueError:
            check("published 不许手工设（由发布记录决定）", True, "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_decision_stopgap() -> None:
    print("[9] 拍板止血（v1.8.5：疑似 → 本地反问；治「它嘴上说已记」）")
    H = m3_chat.detect_decision_hint
    check("09-15 现场「我们做这个岗位吧」→ 疑似 accept",
          H("我们做这个岗位吧") == "accept", H("我们做这个岗位吧"))
    check("09-09 现场「直接往下走吧，把这个岗位写入岗位」→ 疑似 accept",
          H("直接往下走吧，把这个岗位写入岗位") == "accept", "")
    check("问句不触发（怎么样）", H("这个岗怎么样") == "", "")
    check("问句不触发（带问号）", H("我们做这个岗位吧？") == "", "")
    check("无目标词不触发（单个「做」）", H("做") == "", "")
    check("不相关不触发（去猎聘跑一轮）", H("去猎聘跑一轮") == "", "")
    check("否定优先：「这单不做了」→ decline", H("这单不做了") == "decline", H("这单不做了"))
    check("先核实类 → clarify", H("这个岗先核实一下") == "clarify", H("这个岗先核实一下"))
    check("「别放弃这单」不触发", H("别放弃这单") == "", "")

    C = m3_chat.confirmed_intent
    check("反问后「对」= 记下 accept", C("对", "accept") == "accept", "")
    check("反问后「是」= 记下 decline", C("是", "decline") == "decline", "")
    check("反问后「不是」= 当没说", C("不是", "accept") == "cancel", "")
    check("反问后「对，不做」→ decline（否定优先）", C("对，不做", "accept") == "decline", "")
    check("没问过时「对」不触发", C("对", "") == "", "")

    ask = m3_chat.build_decision_ask("accept", "我们做这个岗位吧")
    check("反问文案带标记", m3_chat.ASK_MARK in ask, "")
    check("反问文案可解析出 decision=accept", "decision=accept" in ask, "")
    check("反问文案写明「回是/对也照记」", "不是我猜" in ask, "")

    check("现场原话被判为「声称已记」",
          m3_chat.claims_recorded_decision("老板，收到——「做吧」我记为**接单（accept）**，这岗往下走了。"), "")
    check("普通回复不算声称", not m3_chat.claims_recorded_decision("好的，我去读一下这个岗的 JD。"), "")
    check("只说 accept 不说「记」不算声称", not m3_chat.claims_recorded_decision("我建议接单，accept。"), "")

    tmp = make_tmp_dir("ask")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师")
        c = job["job_code"]
        m3_chat.append_msg(c, "user", "我们做这个岗位吧")
        m3_chat.append_msg(c, "assistant", m3_chat.build_decision_ask("accept", "我们做这个岗位吧"))
        check("last_pending_ask 认得出刚问过 accept", m3_chat.last_pending_ask(c) == "accept", "")
        m3_chat.append_msg(c, "assistant", "（中间插了别的消息）")
        check("中间插别的消息后不再认（防误确认）", m3_chat.last_pending_ask(c) == "", "")

        m3_chat.save_state(c, step1_analyzed=True, decision="pending")
        t1 = m3_chat.build_free_task(job, "我们做这个岗位吧")
        check("pending 岗注入「拍板·硬边界」", "拍板·硬边界" in t1 and "严禁说" in t1, "")
        m3_chat.save_state(c, decision="accept")
        t2 = m3_chat.build_free_task(job, "随便聊聊")
        check("非 pending 不注入（省每轮租金）", "拍板·硬边界" not in t2, "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_post_text_label() -> None:
    print("[10] 发岗助手按钮「用过了」状态（v1.8.6）")
    tmp = make_tmp_dir("post")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师")
        check("没生成过 → 无产物（按钮=📤 发岗助手）", m3_chat.latest_post_text(job) is None, "")
        rp = m3_chat._job_dir(job) / "reports"
        (rp / "publish_20260911-161450.json").write_text("{}", encoding="utf-8")
        check("只有字段 JSON 不算（那是资产不是发岗页）", m3_chat.latest_post_text(job) is None, "")
        (rp / "发岗文字_20260911-161450.html").write_text("<html>x</html>", encoding="utf-8")
        p = m3_chat.latest_post_text(job)
        check("生成过 → 认得出（按钮=🔄 重新发岗助手）",
              p is not None and p.name == "发岗文字_20260911-161450.html", str(p))
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_runs_ledger() -> None:
    print("[11] 运行台账（v1.8.7：断点/恢复第一步）")
    tmp = make_tmp_dir("runs")
    old_log = m3_chat.RUNS_LOG
    m3_chat.RUNS_LOG = tmp / "runs.jsonl"
    try:
        check("没台账文件 → 没有未收尾的 run", m3_chat.last_unfinished_run("J-X") is None, "")
        m3_chat.log_run("J-X", "analyze", "s1", "running", files_before=0)
        u = m3_chat.last_unfinished_run("J-X")
        check("running 落盘 → 认得出（含动作名）",
              u is not None and u.get("action") == "analyze" and u.get("ts"), str(u))
        m3_chat.log_run("J-X", "analyze", "s1", "done", finish_reason="completed")
        check("同 session 补 done → 不再是未收尾", m3_chat.last_unfinished_run("J-X") is None, "")
        m3_chat.log_run("J-Y", "collect_run", "s2", "running")
        check("别的岗不串", m3_chat.last_unfinished_run("J-X") is None, "")
        check("别的岗自己认得出",
              (m3_chat.last_unfinished_run("J-Y") or {}).get("action") == "collect_run", "")
        m3_chat.log_run("J-Y", "collect_run", "s2", "error", note="TimeoutError()")
        check("error 也算收尾（不会再提示）", m3_chat.last_unfinished_run("J-Y") is None, "")
        with m3_chat.RUNS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2020-01-01 00:00:00", "job_code": "J-Z", "action": "analyze",
                                "session": "s9", "status": "running"}, ensure_ascii=False) + "\n")
        check("超过时间窗的未收尾不提示", m3_chat.last_unfinished_run("J-Z", within_hours=1) is None, "")
        check("时间窗放宽就认得出",
              m3_chat.last_unfinished_run("J-Z", within_hours=24 * 365 * 10) is not None, "")
        bad = tmp / "adir"
        bad.mkdir(exist_ok=True)
        keep = m3_chat.RUNS_LOG
        m3_chat.RUNS_LOG = bad          # 故意指向目录 → open 必失败
        try:
            m3_chat.log_run("J-Q", "analyze", "sQ", "running")
            check("台账写失败不抛异常（旁路设计）", True, "")
        except Exception as exc:  # noqa: BLE001
            check("台账写失败不抛异常（旁路设计）", False, repr(exc))
        m3_chat.RUNS_LOG = keep
    finally:
        m3_chat.RUNS_LOG = old_log
        shutil.rmtree(tmp, ignore_errors=True)


def test_collect_spec_check() -> None:
    print("[12] ②采集「翻译考试」：配方表合法值给全 + 本地判分（v1.8.8）")
    brief = local_checks.recipe_options_brief()
    check("清单含 years 全部合法档（含自定义）",
          all(x in brief for x in ("1-3年", "3-5年", "5-10年", "10年以上", "自定义")), "")
    check("清单含 activity 档位", all(x in brief for x in ("今天活跃", "3天内活跃", "最近一年活跃")), "")
    check("清单含「别自己编」硬话", "别自己编" in brief, "")
    check("清单点出 pending 组", "还没实测通" in brief and "当前行业" in brief, "")
    check("清单含三条已知坑",
          "全部命中" in brief and "5-8年" in brief and "自定义" in brief, "")

    g = local_checks.load_cond_groups()
    check("配方表读得到（years 是列表档）", isinstance((g.get("years") or {}).get("options"), list), "")
    check("配方表读得到（activity 有今天活跃）",
          "今天活跃" in ((g.get("activity") or {}).get("options") or []), "")
    check("配方表读不到也不炸（给假路径）", local_checks.load_cond_groups("no_such_file.json") == {}, "")

    tmp = make_tmp_dir("spec")

    def w(name, obj):
        p = tmp / name
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p

    good = w("collect_plan_good.json",
             {"keywords": ["电气设计工程师 EPLAN", "电气设计 输送线"],
              "conds": ["years=5-10年", "education=本科"], "reasons": "x", "note": "", "created_at": "t"})
    r = local_checks.check_collect_spec(good)
    check("合规计划判通过", r["ok"], r["summary"][:160])
    check("合规计划把条件逐个列 ✓", "years=5-10年 ✓" in r["summary"], "")

    bad = w("collect_plan_bad.json",
            {"keywords": ["a b c d e"], "conds": ["years=5-8年", "city=南京"],
             "reasons": "x", "note": "", "created_at": "t"})
    rb = local_checks.check_collect_spec(bad)
    check("假档「5-8年」被判问题", not rb["ok"] and "5-8年" in rb["summary"], "")
    check("给出最接近的合法档建议",
          "3-5年" in rb["summary"] and "5-10年" in rb["summary"], rb["summary"][:220])
    check("提到「自定义」是已知洞", "没记" in rb["summary"], "")
    check("不存在的条件组被判问题",
          "配方表里没有条件组" in rb["summary"] and "city" in rb["summary"], "")
    check("关键字 5 个空格词被提醒（AND 坑）", "全部命中" in rb["summary"], "")
    check("格式错的条件被指出", "group_id=value" in local_checks.check_collect_spec(
        w("collect_plan_fmt.json", {"keywords": ["x"], "conds": ["years"]}))["summary"], "")

    real = (m3_chat.WORKSPACE / "data" / "chat" / "J-CHAT-20260914-172253"
            / "reports" / "collect_plan_20260915-103006.json")
    rr = local_checks.check_collect_spec(real) if real.exists() else {"ok": True, "summary": "（该文件不在，跳过）"}
    check("回扫小猎真写的那份计划：有机械问题吗", rr["ok"], rr["summary"][:220])

    tmp2 = make_tmp_dir("spec_task")
    old_dir = m3_chat.CHAT_DIR
    m3_chat.CHAT_DIR = tmp2
    try:
        job = m3_chat.create_job(title="自测岗", jd_text="职位：测试工程师")
        t = m3_chat.build_step2_plan_task(job)
        check("②任务注入了可选条件清单", "可选条件清单" in t and "照抄" in t, "")
        check("②任务含「不许自己编」", "不许自己编" in t, "")
        check("②任务含 years 合法档（它不用再猜）", "5-10年" in t and "自定义" in t, "")
        check("回归：②任务仍含池子预期 + 请老板拍板",
              "池子预期判断" in t and "请老板拍板" in t, "")
    finally:
        m3_chat.CHAT_DIR = old_dir
        shutil.rmtree(tmp2, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_real_reports()
    test_budget_hard_cap()
    test_judgement_not_clipped()
    test_page_shape()
    test_wiring()
    test_task_text()
    test_profile_view()
    test_publish_status()
    test_decision_stopgap()
    test_post_text_label()
    test_runs_ledger()
    test_collect_spec_check()
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)
