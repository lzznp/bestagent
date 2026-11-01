# -*- coding: utf-8 -*-
"""collect_exec 端到端单测（**不碰猎聘、0 费用**：注入假"读页 / 开详情"）。

跑法（bestagent 目录，lzstudy 解释器）：python test_collect_exec.py

覆盖：
1. dry-run：只判分，**不建库、不开详情**
2. 真跑（假依赖）：读页 → 本地判分 → 按配额开详情 → **写进本岗库 job.db**（含 raw_content 全文）
3. 没开详情的人也入库（留卡）；详情全文进了 raw_content；content_hash 生效（同人第二次 = updated）
4. 轨迹结构能被 report_html.render_collect 渲染（不报错、含关键字段）
5. 停/额度/异常路径：读页失败 → 如实记 notes + error，不写库
6. 详情失败（比如 page_text 不可用）→ 如实记 error、不拿 3000 字冒充全文
"""
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
TMP = BASE / "data" / "_selftest_tmp" / "collect_exec"

import collect_exec as cx  # noqa: E402
import collect_rules as cr  # noqa: E402

PROF = cr.default_profile()   # 172253 电气岗那套兜底判据（真实页面样例就是照它采的）
import job_db  # noqa: E402
import report_html  # noqa: E402

PASS = 0
FAIL = 0


def ok(cond: bool, name: str, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name} {extra}")


CARD_IND = ("今天活跃\n汪**\n37岁\n工作15年\n本科\n南京\n求职期望：\n南京电气工程师\neplan\n控制柜设计\n"
            "电气布线\n部件选型\n\n南京新松智能装备有限公司 · 电气设计工程师\n2021.05-至今(5年4个月)\n\n"
            "江苏华章物流科技股份有限公司 · 电气工程师\n2018.07-2021.05(2年10个月)\n\n"
            "南京工程学院 · 自动化 · 本科 · 统招\n2013.09-2017.06(4年)\n\n立即沟通")
CARD_ELEC = ("在职，看看新机会\n宋**\n31岁\n工作10年\n本科\n南京-浦口区\n求职期望：\n南京电气工程师\n\n"
             "迈睿捷(南京)半导体科技有限公司 · 电气总工程师\n2023.05-至今(3年4个月)\n\n"
             "南京工程学院 · 自动化 · 本科 · 统招\n2013.09-2017.06(4年)\n\n立即沟通")
CARD_MECH = ("在线\n王**\n46岁\n工作23年\n本科\n南京\n求职期望：\n南京机械工程师\n夹具\ncad\nsolidworks\n\n"
             "江苏玖元智能科技有限公司 · 机械工程师\n2025.12-至今(9个月)\n\n"
             "北京航空航天大学 · 机械电子工程/机电一体化 · 本科 · 统招\n1996.09-2000.06(4年)\n\n立即沟通")

ROWS = [{"text": CARD_IND, "fields": {"res_id_encode": "rid_IND_1"}},
        {"text": CARD_ELEC, "fields": {"res_id_encode": "rid_ELEC_1"}},
        {"text": CARD_MECH, "fields": {"res_id_encode": "rid_MECH_1"}}]

DETAIL_TEXT = ("每日任务\n杨猛\n简历编号：rid_IND_1\n今天活跃\n汪**\n37岁\n本科\n工作15年\n"
               "工作经历\n南京新松智能装备有限公司（2021.05 - 至今）\n电气设计工程师\n职责业绩：\n"
               "1. 负责托盘输送线电气设计\n2. 电控柜布局与元器件选型\n项目经历\n输送线电控系统改造\n" * 40
               + "\n津ICP备15007986号-11\nCopyright©2006-2024 liepin.com All Rights Reserved")


def fake_read(rows=ROWS, total="共121位人选"):
    def _r(tab):
        return {"ok": True, "rows": rows, "total_raw": total, "note": ""}
    return _r


def fake_open(chars=None, truncated=False, fail=False):
    def _o(tab, rid):
        if fail:
            return {"ok": False, "error": "page_text 不可用：未知动作（需要重载扩展）"}
        t = DETAIL_TEXT
        return {"ok": True, "chars": chars or len(t), "truncated": truncated, "text": t,
                "url": cx.DETAIL_URL.format(rid=rid)}
    return _o


def clean(job: str) -> None:
    d = TMP / job
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def test_dry_run() -> None:
    clean("J-T-DRY")
    tr = cx.run_page("J-T-DRY", "电气设计工程师 输送线", ["city_current=南京"], page=1,
                     details_per_page=2, dry_run=True, tab=0, read_page=fake_read())
    st = tr["rounds"][0]["stats"]
    ok(st["n"] == 3, "dry-run：读到 3 张卡", str(st))
    ok(st["open"] == 2, "dry-run：按配额只选 2 个开详情", str(st["open"]))
    ok(st["industry"] == 1, "dry-run：行业命中 1（新松/华章/物流科技）", str(st["industry"]))
    ok(not (TMP / "J-T-DRY").exists(), "dry-run：**没有建库、没写盘**", "")
    ok(any("dry-run" in n for n in tr["notes"]), "dry-run：轨迹里如实标注", str(tr["notes"]))
    ok(all(not (j.get("detail") or {}).get("chars") for j in tr["rounds"][0]["cards"]),
       "dry-run：没有任何详情内容", "")


def test_real_run(no_quota=False) -> None:
    job = "J-T-RUN"
    clean(job)
    tr = cx.run_page(job, "电气设计工程师 输送线", ["city_current=南京"], page=1,
                     details_per_page=2, dry_run=False, tab=0, no_quota=True,
                     read_page=fake_read(), open_detail=fake_open(), db_root=TMP, open_gap=(0, 0), profile=PROF)
    st = tr["rounds"][0]["stats"]
    ok(st["n"] == 3 and st["open"] == 2, "真跑：3 张卡、开 2 个详情", json.dumps(st))
    opened = [j for j in tr["rounds"][0]["cards"] if j.get("action") == "open"]
    ok(all((j.get("detail") or {}).get("ok") for j in opened), "真跑：2 个详情都成功", "")
    ok(all((j.get("detail") or {}).get("chars") == len(DETAIL_TEXT) for j in opened),
       "真跑：详情读的是**全文**（page_text 的字数）", "")

    con = job_db.open_db(job, root=TMP)
    rows = con.execute("SELECT source_id, raw_content, local_score, local_hits, status, summary_text "
                       "FROM candidates WHERE job_code=?", (job,)).fetchall()
    by = {r["source_id"]: r for r in rows}
    ok(len(rows) == 3, "库：**3 个人全入库**（开详情的带全文，没开的留卡）", str(len(rows)))
    ok(by["rid_IND_1"]["raw_content"] == DETAIL_TEXT, "库：行业对口那位有**详情全文**", "")
    ok(by["rid_MECH_1"]["raw_content"] == "", "库：没开详情的人 raw_content 为空（不拿卡片冒充全文）", "")
    ok(by["rid_MECH_1"]["summary_text"].startswith("在线"), "库：卡片原文留着（本地粗筛原料）", "")
    ok(json.loads(by["rid_IND_1"]["local_hits"]), "库：local_hits 记了命中词", by["rid_IND_1"]["local_hits"])
    ok(by["rid_IND_1"]["local_score"] > by["rid_MECH_1"]["local_score"],
       "库：行业对口分 > 机械噪声分", f'{by["rid_IND_1"]["local_score"]} vs {by["rid_MECH_1"]["local_score"]}')
    ok(all(r["status"] == "opened" for r in rows if r["raw_content"]), "库：开了详情的标记 opened", "")
    ok(by["rid_MECH_1"]["status"] == "kept", "库：留卡状态 kept", by["rid_MECH_1"]["status"])
    ok(Path(tr["db_path"]).as_posix().startswith(TMP.as_posix()), "库：路径落在传入的 root 下", tr["db_path"])

    # 幂等：同一页再跑一次（同 res_id）→ updated，不新增
    tr2 = cx.run_page(job, "电气设计工程师 输送线", ["city_current=南京"], page=1,
                      details_per_page=2, dry_run=False, tab=0, no_quota=True,
                      read_page=fake_read(), open_detail=fake_open(), db_root=TMP, open_gap=(0, 0), profile=PROF)
    con2 = job_db.open_db(job, root=TMP)
    n2 = con2.execute("SELECT COUNT(*) c FROM candidates WHERE job_code=?", (job,)).fetchone()["c"]
    ok(n2 == 3, "库：重跑同一页不新增（本岗内不重复）", str(n2))
    ok(len(tr2["rounds"][0]["cards"]) == 3, "重跑：轨迹照常生成", "")


def test_render() -> None:
    job = "J-T-RUN"
    tr = cx.run_page(job, "电气设计工程师 输送线", ["city_current=南京"], page=1,
                     details_per_page=2, dry_run=False, tab=0, no_quota=True,
                     read_page=fake_read(), open_detail=fake_open(), db_root=TMP, open_gap=(0, 0), profile=PROF)
    tr["out_file"] = "collect_x.json"
    html = report_html.render_collect("测试岗", tr, {"job_code": job, "json_name": "collect_x.json"})
    ok(len(html) > 1500 and "<html" in html, "渲染：出 HTML", str(len(html)))
    for k in ("② 正式采集", "共121位人选", "开详情", "行业命中", "进了详情页的人", "新松"):
        ok(k in html, f"渲染：含「{k}」", "")


def test_failure_paths() -> None:
    job = "J-T-FAIL"
    clean(job)
    tr = cx.run_page(job, "kw", [], page=1, dry_run=False, tab=0, no_quota=True,
                     read_page=lambda tab: {"ok": False, "error": "extract 失败：tab-lost"}, db_root=TMP)
    ok(tr["rounds"][0].get("error") == "extract 失败：tab-lost", "读页失败：轨迹如实记 error", "")
    ok(any("读页失败" in n for n in tr["notes"]), "读页失败：notes 里也有", "")
    ok(not (TMP / job / "job.db").exists(), "读页失败：**不建库**（不许假成功）", "")

    job2 = "J-T-FAIL2"
    clean(job2)
    tr2 = cx.run_page(job2, "kw", [], page=1, dry_run=False, tab=0, no_quota=True,
                      read_page=fake_read(), open_detail=fake_open(fail=True), db_root=TMP, open_gap=(0, 0), profile=PROF)
    cards = tr2["rounds"][0]["cards"]
    opened = [j for j in cards if j.get("action") == "open"]
    ok(all(not (j.get("detail") or {}).get("ok") for j in opened), "详情失败：如实标失败", "")
    ok(any("page_text 不可用" in (n or "") for n in tr2["notes"]), "详情失败：notes 说明原因（没重载扩展）", "")
    con = job_db.open_db(job2, root=TMP)
    rows = con.execute("SELECT raw_content FROM candidates WHERE job_code=?", (job2,)).fetchall()
    ok(len(rows) >= 1 and all((r["raw_content"] or "") == "" for r in rows),
       "详情失败：仍留卡入库，但 raw_content 全空（**不拿 3000 字冒充全文**）", "")


def fake_search(ok=True, fail_kw=None):
    """假"自己搜"。⚠️ **必须注入**：`run_plan` 默认 `do_search=True`，
    不注入就会去调真桥（navigate + execute_spec → 真在老板浏览器里搜索）。

    2026-09-16 实测事故：本文件少了这个注入 → 单测真的驱动了猎聘页面搜了两次。
    所以这里不仅给假的，**还断言真桥没被调用**（见 `test_no_live_bridge`）。
    """
    calls = []

    def _s(tab, keyword, conds=None):
        calls.append({"tab": tab, "keyword": keyword, "conds": list(conds or [])})
        if not ok or (fail_kw is not None and keyword == fail_kw):
            return {"ok": False, "error": "假失败：条件未生效（verify=False）", "steps": [],
                    "verify_failed": True}
        return {"ok": True, "error": None, "steps": [{"group_id": "keyword", "ok": True},
                                                     {"action": "search", "ok": True}],
                "searches": 1}
    return _s, calls


def fake_turn(ok=True, page_after=2, reason=""):
    def _t(tab, direction="next", wait_ms=15000):
        return {"ok": ok, "clicked": "next-arrow" if ok else None, "page_before": 1,
                "page_after": page_after, "reason": reason,
                "error": "" if ok else "没找到可点的翻页控件（可能已是最后一页）"}
    return _t


def fake_read_pages():
    """第 1 页有行业命中、第 2 页没有（res_id 全不同）。"""
    calls = {"n": 0}

    def _r(tab):
        calls["n"] += 1
        k = calls["n"]
        if k == 1:
            return {"ok": True, "rows": ROWS, "total_raw": "共121位人选", "note": ""}
        rows = [{"text": CARD_ELEC.replace("宋**", f"张{k}**").replace("rid_ELEC_1", f"rid_p{k}_1"),
                 "fields": {"res_id_encode": f"rid_p{k}_1"}},
                {"text": CARD_ELEC.replace("宋**", f"李{k}**").replace("rid_ELEC_1", f"rid_p{k}_2"),
                 "fields": {"res_id_encode": f"rid_p{k}_2"}}]
        return {"ok": True, "rows": rows, "total_raw": "共121位人选", "note": ""}
    return _r, calls


def test_auto_paging() -> None:
    job = "J-T-AUTO"
    clean(job)
    # ① 翻不动就停：第 1 页正常，翻页失败 → 只跑 1 页
    tr = cx.run_auto(job, "电气设计工程师 输送线", ["city_current=南京"], max_pages=5, details_per_page=2,
                     tab=0, no_quota=True, read_page=fake_read(), open_detail=fake_open(),
                     turn_page_fn=fake_turn(ok=False), db_root=TMP, open_gap=(0, 0), page_gap=(0, 0), profile=PROF)
    ok(len(tr["rounds"]) == 1, "自动翻页：翻不动 → 只跑了 1 页", str(len(tr["rounds"])))
    ok("翻不动" in (tr["rounds"][0].get("stop_reason") or ""), "自动翻页：停止原因写明『翻不动』",
       tr["rounds"][0].get("stop_reason"))
    con = job_db.open_db(job, root=TMP)
    n1 = con.execute("SELECT COUNT(*) c FROM candidates WHERE job_code=?", (job,)).fetchone()["c"]
    ok(n1 == 3, "自动翻页：第 1 页 3 人全入库", str(n1))
    ok(tr["total_opened"] <= 2, "自动翻页：详情数不超每页配额", str(tr["total_opened"]))

    # ② 第 2 页行业命中=0 → 连续 1 页还不该停？规则是"连续 2 页" → 应继续翻到第 3 页再停
    job2 = "J-T-AUTO2"
    clean(job2)
    rp, calls = fake_read_pages()
    tr2 = cx.run_auto(job2, "kw", [], max_pages=5, details_per_page=1, tab=0, no_quota=True,
                      read_page=rp, open_detail=fake_open(), turn_page_fn=fake_turn(ok=True),
                      db_root=TMP, open_gap=(0, 0), page_gap=(0, 0), profile=PROF)
    ok(len(tr2["rounds"]) >= 2, "自动翻页：翻得动就继续翻（≥2 页）", str(len(tr2["rounds"])))
    ok(len([r for r in tr2["rounds"] if r["stats"]["industry"] == 0]) >= 1,
       "自动翻页：第 2 页起行业命中为 0（真数据形态）", "")

    # ③ 硬顶：max_pages=2 → 最多 2 页
    job3 = "J-T-AUTO3"
    clean(job3)
    rp3, _ = fake_read_pages()
    tr3 = cx.run_auto(job3, "kw", [], max_pages=2, details_per_page=1, tab=0, no_quota=True,
                      read_page=rp3, open_detail=fake_open(), turn_page_fn=fake_turn(ok=True),
                      db_root=TMP, open_gap=(0, 0), page_gap=(0, 0), profile=PROF)
    ok(len(tr3["rounds"]) <= 2, "自动翻页：硬顶 max_pages 生效", str(len(tr3["rounds"])))

    # ④ 同一页反复出现同一批人（翻页没生效）→ 立即停，防死循环
    job4 = "J-T-AUTO4"
    clean(job4)
    tr4 = cx.run_auto(job4, "kw", [], max_pages=5, details_per_page=1, tab=0, no_quota=True,
                      read_page=fake_read(), open_detail=fake_open(),
                      turn_page_fn=fake_turn(ok=True), db_root=TMP, open_gap=(0, 0), page_gap=(0, 0), profile=PROF)
    ok(len(tr4["rounds"]) <= 2, "自动翻页：每页都是同批人 → 立刻停（防死循环）", str(len(tr4["rounds"])))
    # 这组假数据每页都是同一批人 → 先触发"没新人"这条防死循环；两种停止原因都算对
    ok(any(("没有新人" in (r.get("stop_reason") or "")) or (r.get("stop_reason") or "").startswith("连续 2 页")
           for r in tr4["rounds"]), "自动翻页：停止原因写明（没新人 / 行业连续为 0）",
       str([r.get("stop_reason") for r in tr4["rounds"]]))

    # ⑤ 轨迹能渲染（多了 pages/mode 字段也不许崩）
    html = report_html.render_collect("测试岗", tr, {"job_code": job, "json_name": "x.json"})
    ok("<html" in html and len(html) > 1000, "自动翻页：轨迹能本地渲染", str(len(html)))


def test_run_plan() -> None:
    """按计划把关键字一条条跑完（自己搜 + 多关键字循环 + 判据卡 + 去重）。"""
    job = "J-T-PLAN"
    clean(job)
    plan = {"job_code": job, "keywords": ["机械设计 非标", "AGV 机械工程师", "机械设计 非标"],
            "conds": ["city_current=南京"],
            "judge": {"industry": ["叉车", "AGV"], "skills": ["solidworks"], "role": ["机械设计"],
                      "not_role": ["电气"], "prefer": "industry"}}
    rp, _ = fake_read_pages()
    srch, scalls = fake_search()
    tr = cx.run_plan(plan, max_pages=1, details_per_page=1, tab=0, no_quota=True,
                     read_page=rp, open_detail=fake_open(), turn_page_fn=fake_turn(ok=False),
                     db_root=TMP, plan_path="fake_plan.json", search_fn=srch)
    ok(tr["mode"] == "plan", "按计划跑：模式标 plan", tr.get("mode"))
    ok(len(tr["keyword_runs"]) == 2, "按计划跑：重复关键字只跑一次（2 条去重后）",
       str([k["keyword"] for k in tr["keyword_runs"]]))
    ok(any("重复" in n for n in tr["notes"]), "按计划跑：重复关键字有说明", "")
    ok(tr.get("judge", {}).get("used_default") is False
       and tr["judge"]["industry"] == ["叉车", "AGV"], "按计划跑：判据卡进了轨迹", str(tr.get("judge", {}).get("industry")))
    ok(len(tr["rounds"]) >= 2, "按计划跑：每个关键字都产出了页记录", str(len(tr["rounds"])))
    # 🔴 v1.10.0：**每条关键字自己搜**（"老板先人工搜一次"永久消失）+ **换关键字**成立
    ok([c["keyword"] for c in scalls] == ["机械设计 非标", "AGV 机械工程师"],
       "自己搜：每条关键字各搜一次（重复那条不搜）", str([c["keyword"] for c in scalls]))
    ok(all(c["conds"] == ["city_current=南京"] for c in scalls),
       "自己搜：计划里的条件带进了搜索规格", str([c["conds"] for c in scalls]))
    ok(len(tr["searches"]) == 2 and all(s["ok"] for s in tr["searches"]),
       "自己搜：搜索过程如实进轨迹", str(len(tr.get("searches") or [])))
    con = job_db.open_db(job, root=TMP)
    n = con.execute("SELECT COUNT(*) c FROM candidates WHERE job_code=?", (job,)).fetchone()["c"]
    ok(n >= 2, "按计划跑：人都落进了本岗库", str(n))
    html = report_html.render_collect("测试岗", tr, {"job_code": job, "json_name": "x.json"})
    ok("<html" in html, "按计划跑：轨迹能本地渲染", str(len(html)))


def test_search_failure_never_collects() -> None:
    """🔴 自己搜失败 → **跳过不采**（宁可这一条空着，绝不把别人的页当成自己的页采）。

    这是"采错页"这类静默错误的正面防线：2026-09-16 实测过四次采集读到同一页、
    至少一边贴错了岗标签（见衔接报告 §2）。
    """
    job = "J-T-PLAN-FAIL"
    clean(job)
    plan = {"job_code": job, "keywords": ["机械设计 非标", "AGV 机械工程师"],
            "conds": ["city_current=南京"],
            "judge": {"industry": ["叉车"], "role": ["机械设计"], "prefer": "industry"}}
    rp, rpcalls = fake_read_pages()
    srch, scalls = fake_search(fail_kw="机械设计 非标")
    tr = cx.run_plan(plan, max_pages=1, details_per_page=1, tab=0, no_quota=True,
                     read_page=rp, open_detail=fake_open(), turn_page_fn=fake_turn(ok=True),
                     db_root=TMP, plan_path="fake_plan.json", search_fn=srch, page_gap=(0, 0))
    ok(len(scalls) == 2, "搜失败：两条关键字都试过了", str([c["keyword"] for c in scalls]))
    ok(rpcalls["n"] == 1, "搜失败：**失败那条一个字都没读**（没读页=没采错页）", str(rpcalls["n"]))
    ok(tr["keyword_runs"][0].get("search_failed") is True and tr["keyword_runs"][0]["pages"] == 0,
       "搜失败：如实记为 search_failed / 0 页", json.dumps(tr["keyword_runs"][0], ensure_ascii=False))
    ok(any("跳过不采" in n for n in tr["notes"]), "搜失败：notes 写明「跳过不采」", str(tr["notes"][:3]))
    ok(all(r["keyword"] == "AGV 机械工程师" for r in tr["rounds"]),
       "搜失败：只有搜成了的那条产出了页记录", str([r["keyword"] for r in tr["rounds"]]))


def test_no_live_bridge() -> None:
    """🔴 防回归（2026-09-16 真实事故）：单测**不许**驱动真浏览器。

    事故：`run_plan` 默认 `do_search=True`，而本文件的用例没注入假搜索 →
    运行单测时真的调了桥，在猎聘页上搜了两次（navigate + 点「搜 索」）。
    这里把桥的入口替换成"一被调用就炸"，把"测试碰真浏览器"变成**硬失败**。
    """
    job = "J-T-PLAN-NET"
    clean(job)
    plan = {"job_code": job, "keywords": ["机械设计 非标"], "conds": ["city_current=南京"],
            "judge": {"industry": ["叉车"], "role": ["机械设计"], "prefer": "industry"}}
    real_submit, real_exec = cx.submit_task, cx.execute_spec

    def _boom(*a, **k):
        raise AssertionError("单测不许碰真桥（submit_task 被调用了）")

    cx.submit_task = _boom
    cx.execute_spec = _boom
    try:
        srch, scalls = fake_search()
        rp, _ = fake_read_pages()
        tr = cx.run_plan(plan, max_pages=1, details_per_page=1, tab=0, no_quota=True,
                         read_page=rp, open_detail=fake_open(), turn_page_fn=fake_turn(ok=False),
                         db_root=TMP, plan_path="fake_plan.json", search_fn=srch,
                         dry_run=True, page_gap=(0, 0))
        ok(len(scalls) == 1 and tr.get("dry_run") is True,
           "防回归：注入假搜索后，跑 run_plan 全程不碰真桥", str(scalls))
    finally:
        cx.submit_task, cx.execute_spec = real_submit, real_exec
    ok(cx.submit_task is real_submit and cx.execute_spec is real_exec,
       "防回归：测试结束后把桥的入口还原", "")


def test_search_page_tolerates_navigate_timeout() -> None:
    """🔴 2026-09-16 17:07 真跑实测踩到：`navigate` 报"等待执行结果超时"。

    根因在扩展：`zNavigate` 就是 `location.href = url` —— **页面一卸载，执行脚本跟着死**，
    回执来不及送回桥 → 桥的 in-flight 被这条任务**永久占住**（之后所有动作都超时）。
    但**页面其实已经跳过去了** → 所以 `search_page` **不许**把 navigate 的失败当致命：
    地面真相由 `execute_spec` 的逐格 `verify` 判定（它失败 → 整条关键字"跳过不采"）。
    """
    real_submit, real_exec = cx.submit_task, cx.execute_spec
    calls = {"nav": 0, "clear": 0, "spec": 0}

    def _submit(bridge, action, params, source="collect-exec", timeout=60.0):
        if action == "navigate":
            calls["nav"] += 1
            return {"ok": False, "error": "等待执行结果超时（60.0s）"}
        if action == "click_by_text":
            calls["clear"] += 1
            return {"ok": True, "result": {"ok": True}}
        return {"ok": True, "result": {}}

    def _exec(spec, tab, do_search=True, do_extract=False, url=None, on_step=None):
        calls["spec"] += 1
        return {"ok": True, "steps": [{"group_id": "keyword", "ok": True, "verify": True},
                                      {"action": "search", "ok": True}]}

    cx.submit_task, cx.execute_spec = _submit, _exec

    def _pool(_tab):
        # ⚠️ 必须注入：默认的 read_pool=read_total 会**真调桥读页面**（§7-1 那次"单测驱动真浏览器"）
        return {"total": 121, "total_raw": "共121位人选", "is_plus": False, "found": True}

    # ⚠️ 两次 search_page 都要在**同一个 try** 里：v1.11.0 起 search_page 还会读池子，
    #    任何一次漏了注入都等于让单测去碰真桥（本机实测过 WinError 10061）。
    try:
        r = cx.search_page(7, "机械设计 非标", ["city_current=南京"], read_pool=_pool)
        ok(r.get("ok") is True, "navigate 超时**不当致命**：照样往下走 execute_spec",
           json.dumps(r, ensure_ascii=False)[:160])
        ok(calls["spec"] == 1 and calls["clear"] == 1,
           "navigate 超时后仍做了「清空筛选条件」+ 设条件搜索", json.dumps(calls))
        ok(any("navigate 没回执" in n for n in (r.get("notes") or [])),
           "navigate 超时有**如实记录**（不静默）", str(r.get("notes")))

        # 而 execute_spec 真失败 → 必须 ok=False（上层据此"跳过不采"）
        def _exec_fail(spec, tab, do_search=True, do_extract=False, url=None, on_step=None):
            return {"ok": False, "error": "条件未生效（verify=False）：city_current=南京",
                    "verify_failed": True, "steps": []}

        cx.execute_spec = _exec_fail
        r2 = cx.search_page(7, "机械设计 非标", ["city_current=南京"], read_pool=_pool)
        ok(r2.get("ok") is False and r2.get("verify_failed") is True,
           "条件没生效（verify=False）→ search_page 如实 ok=False（→ 上层不采）",
           json.dumps(r2, ensure_ascii=False)[:160])
    finally:
        cx.submit_task, cx.execute_spec = real_submit, real_exec


def test_preflight_blocks_bad_plan() -> None:
    """🔴 开工前体检（v1.11.0）：计划有机械问题（**尤其缺判据卡**）→ **拒绝开跑**。

    老板 2026-09-16 拍板取消「搜索体检 / 采集计划」两个子步骤 → 小猎**一个回合内**自己写完计划
    就直接开跑，面板来不及在中间拦一道；所以体检（原体检线的两块能力之一）必须在**真正开跑那一步**。
    缺判据卡 = 硬拒绝：兜底卡装的是**别的岗的行业词**，用它采出来的池子不可信（§2.9 那 28 行）。
    """
    job = "J-T-PRE"
    clean(job)
    TMP.mkdir(parents=True, exist_ok=True)
    bad = TMP / "bad_plan.json"
    bad.write_text(json.dumps({"job_code": job, "keywords": ["机械设计 非标"],
                               "conds": ["education=火星"]}, ensure_ascii=False), encoding="utf-8")
    pf = cx.preflight_plan(bad, json.loads(bad.read_text(encoding="utf-8")))
    ok(pf["ok"] is False, "体检：非法取值 + 缺判据卡 → 不通过", pf["summary"])
    ok(any("火星" in p for p in pf["problems"]),
       "体检：指出取值**不在配方表合法档**（翻译考试）", str(pf["problems"]))
    ok(any("judge" in p for p in pf["problems"]),
       "体检：**缺判据卡**算硬问题（老板拍板：硬拒绝）", str(pf["problems"]))

    good = TMP / "good_plan.json"
    good.write_text(json.dumps({"job_code": job, "keywords": ["机械设计 非标"],
                                "conds": ["education=本科"],
                                "judge": {"industry": ["叉车"], "role": ["机械设计"]}},
                               ensure_ascii=False), encoding="utf-8")
    pf2 = cx.preflight_plan(good, json.loads(good.read_text(encoding="utf-8")))
    ok(pf2["ok"] is True, "体检：关键字/条件/判据卡都合法 → 放行", pf2["summary"])

    # ⚠️ 只写个函数没人调 = 假闸门。这里直接打真跑入口 `main()`，验它**真的接上了**。
    real_run, real_tab, real_argv = cx.run_plan, cx.find_liepin_tab, sys.argv
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("体检没过还往下跑 = 闸门没接上")

    cx.run_plan, cx.find_liepin_tab, sys.argv = _boom, (lambda: 0), [
        "collect_exec.py", "--job-code", job, "--plan", str(bad)]
    try:
        raised = None
        try:
            cx.main()
        except SystemExit as e:
            raised = e
    finally:
        cx.run_plan, cx.find_liepin_tab, sys.argv = real_run, real_tab, real_argv
    ok(isinstance(raised, SystemExit) and raised.code == 2,
       "体检没过：main() 以 SystemExit(2) 退出", str(raised))
    ok(called["n"] == 0, "体检没过：`run_plan` 一次都没被调用（一个字都没采）", str(called["n"]))


def test_search_page_reports_pool() -> None:
    """体检能力①并进采集（v1.11.0）：**先报池子，再开详情**。

    `search_page` 给 `execute_spec` 传 `on_step`（体检线 2026-09-15 的做法）→ 每个条件执行完
    就地读一次「共N位人选」= "这个条件砍掉多少人"；搜索定稿后再读一次 = 这条关键字有多少人。
    读数要**进轨迹**（老板/报告要能看出"这条词厚不厚"），且 **0 token**。
    """
    real_submit, real_exec = cx.submit_task, cx.execute_spec
    rdcalls = {"n": 0}

    def _read_pool(_tab):
        rdcalls["n"] += 1
        return {"total": 121, "total_raw": "共121位人选", "is_plus": False, "found": True}

    def _submit(bridge, action, params, source="collect-exec", timeout=60.0):
        return {"ok": True, "result": {"ok": True}}

    def _exec(spec, tab, do_search=True, do_extract=False, url=None, on_step=None):
        steps = [{"group_id": "keyword", "type": "input", "ok": True, "verify": True},
                 {"group_id": "city_current", "type": "chips+panel", "ok": True, "verify": True}]
        if on_step is not None:      # 复刻 execute_spec 的行为：把读数合进该 step
            for s in steps:
                s.update(on_step(s) or {})
        return {"ok": True, "steps": steps}

    job = "J-T-POOL"
    clean(job)
    plan = {"job_code": job, "keywords": ["机械设计 非标"], "conds": ["city_current=南京"],
            "judge": {"industry": ["叉车"], "role": ["机械设计"], "prefer": "industry"}}
    rp, _ = fake_read_pages()

    def _search(tab, kw, cs, read_pool=None):
        return cx.search_page(tab, kw, cs, read_pool=_read_pool)

    cx.submit_task, cx.execute_spec = _submit, _exec
    try:
        r = cx.search_page(7, "机械设计 非标", ["city_current=南京"], read_pool=_read_pool)
        tr = cx.run_plan(plan, max_pages=1, details_per_page=1, tab=0, no_quota=True,
                         read_page=rp, open_detail=fake_open(), turn_page_fn=fake_turn(ok=False),
                         db_root=TMP, plan_path="fake_plan.json", search_fn=_search,
                         dry_run=True, page_gap=(0, 0))
    finally:
        cx.submit_task, cx.execute_spec = real_submit, real_exec
    ok(r.get("ok") is True and r.get("pool", {}).get("total") == 121,
       "开工前读数：报出「共121位人选」", json.dumps(r.get("pool"), ensure_ascii=False))
    ok(any("开工前读数" in n for n in (r.get("notes") or [])), "开工前读数：如实进 notes", str(r.get("notes")[:2]))
    bys = r.get("pool_by_step") or []
    ok(len(bys) == 2, "逐条件读数：每个条件各读一次（2 个条件 → 2 条）", str(len(bys)))
    ok(bys and bys[0].get("stale") is True,
       "逐条件读数：input 类条件**如实标 stale**（不冒充它的效果）", json.dumps(bys[0], ensure_ascii=False))
    ok(bys and not bys[1].get("stale"),
       "逐条件读数：即点即搜的条件（chips+panel）不当旧状态", json.dumps(bys[1], ensure_ascii=False))
    _se = (tr.get("searches") or [{}])[0]
    ok(_se.get("pool", {}).get("total") == 121,
       "开工前读数：**进了轨迹**（searches[0].pool）", json.dumps(_se.get("pool"), ensure_ascii=False))
    ok(len(_se.get("pool_by_step") or []) == 2,
       "开工前读数：逐条件读数也进了轨迹", str(len(_se.get("pool_by_step") or [])))
    ok(tr.get("total_opened", 0) == 0 and not job_db.db_path(job, root=TMP).exists(),
       "开工前读数：dry-run 下只报池子、不写库", str(tr.get("total_opened")))


def test_open_detail_pins_tab_and_closes_it() -> None:
    """🔴 2026-09-17 修的两个真 bug（老板实测：**标签页堆了一排** + 3 份"全文"是别的页面）：

    ① `new_tab` 的返回是 `{ok:true, tab:{tab_id:N}}`，老代码读 `result["tab_id"]` → **永远 0**；
       扩展把 0 当"没指定"→ **回退读当前激活标签页**（那次读到老板正在看的 DSH 面板页）。
    ② `finally` 里 `if new_id:` 也因 0 不成立 → **详情页从来没被关掉**。

    现在：tab_id 必须取到并**钉住**；读完**必关**；读到的必须**像简历**（含「简历编号」）。
    """
    real = cx.submit_task
    calls = []
    DETAIL_TXT = "杨猛\n简历编号：rid_X1\n工作经历\n南京新松智能装备有限公司\n" * 6

    def _submit(bridge, action, params, source="collect-exec", timeout=60.0):
        calls.append({"action": action, "params": dict(params or {})})
        if action == "new_tab":
            # ⚠️ 就是扩展的真实形状：tab_id 在 result.tab 里（不是 result.tab_id）
            return {"ok": True, "result": {"ok": True, "tab": {"tab_id": 77, "active": True}}}
        if action == "snapshot":
            return {"ok": True, "result": {"url": cx.DETAIL_URL.format(rid="rid_X1")}}
        if action == "page_text":
            return {"ok": True, "result": {"text": DETAIL_TXT, "chars": len(DETAIL_TXT),
                                           "truncated": False}}
        return {"ok": True, "result": {"ok": True}}

    cx.submit_task = _submit
    try:
        r = cx.open_detail(5, "rid_X1", wait=0, reread_wait=0)
    finally:
        cx.submit_task = real
    ok(r.get("ok") is True and r.get("chars") == len(DETAIL_TXT),
       "开详情：拿到全文（判成功）", json.dumps({k: r.get(k) for k in ("ok", "chars", "error")}, ensure_ascii=False))
    injected = [c for c in calls if c["action"] in ("snapshot", "page_text", "click_by_text")]
    ok(bool(injected) and all(c["params"].get("tab_id") == 77 for c in injected),
       "开详情：所有注入动作都**钉住 new_tab 回的 77**（不再是 0→回退激活页）",
       json.dumps([c["params"].get("tab_id") for c in injected]))
    closes = [c for c in calls if c["action"] == "close_tab"]
    ok(len(closes) == 1 and closes[0]["params"].get("tab_id") == 77,
       "开详情：读完**把详情页关掉**（老板口径：看一个关一个）", json.dumps(closes, ensure_ascii=False))
    ok(any(c["action"] == "switch_tab" and c["params"].get("tab_id") == 5 for c in calls),
       "开详情：随后切回列表页", json.dumps([c for c in calls if c["action"] == "switch_tab"], ensure_ascii=False))
    ok(all(c["params"].get("tab_id") != 0 for c in calls),
       "开详情：**没有任何一次用 tab_id=0**（0 = 让扩展自己挑激活页 = 采错页）",
       json.dumps([c["params"].get("tab_id") for c in calls]))


def test_open_detail_rejects_wrong_page() -> None:
    """读到**不像简历**的文本（那次是 DSH 面板页）→ 判失败、**不写库**，但人按"只有卡片"留着。"""
    real = cx.submit_task
    calls = []
    PANEL_TXT = "DSH 本地构建\n0.1.5-alpha.2\n新会话\n工作区\nbestagent\n机械岗094907首次真跑准备" * 20

    def _submit(bridge, action, params, source="collect-exec", timeout=60.0):
        calls.append({"action": action, "params": dict(params or {})})
        if action == "new_tab":
            return {"ok": True, "result": {"ok": True, "tab": {"tab_id": 88}}}
        if action == "snapshot":
            return {"ok": True, "result": {"url": cx.DETAIL_URL.format(rid="rid_Y1")}}
        if action == "page_text":
            return {"ok": True, "result": {"text": PANEL_TXT, "chars": len(PANEL_TXT)}}
        return {"ok": True, "result": {"ok": True}}

    cx.submit_task = _submit
    try:
        r = cx.open_detail(5, "rid_Y1", wait=0, reread_wait=0)
    finally:
        cx.submit_task = real
    ok(r.get("ok") is False and r.get("wrong_page") is True,
       "读到别的页面：**判失败**并标 wrong_page（不拿面板文本冒充简历）",
       json.dumps(r, ensure_ascii=False)[:200])
    ok("不像简历" in str(r.get("error")), "读到别的页面：报错说清「不像简历」", str(r.get("error")))
    ok(any(c["action"] == "close_tab" and c["params"].get("tab_id") == 88 for c in calls),
       "读到别的页面：**照样把详情页关掉**（失败也要收尾，别留标签页）", "")


def test_open_detail_refuses_without_tab_id() -> None:
    """`new_tab` 没回 tab_id → **不猜**（不当 0 往下走）：这次这份全文放弃，一次读页都不发。"""
    real = cx.submit_task
    calls = []

    def _submit(bridge, action, params, source="collect-exec", timeout=60.0):
        calls.append({"action": action, "params": dict(params or {})})
        if action == "new_tab":
            return {"ok": True, "result": {"ok": True, "tab": {}}}   # 没 tab_id
        return {"ok": True, "result": {}}

    cx.submit_task = _submit
    try:
        r = cx.open_detail(5, "rid_Z1", wait=0, reread_wait=0)
    finally:
        cx.submit_task = real
    ok(r.get("ok") is False and r.get("wrong_page") is False,
       "没回 tab_id：如实失败（不是 wrong_page，是'拿不到目标'）", json.dumps(r, ensure_ascii=False)[:200])
    ok(not any(c["action"] in ("page_text", "snapshot") for c in calls),
       "没回 tab_id：**一次读页都没发**（宁可漏全文，也不读错页）",
       json.dumps([c["action"] for c in calls]))


def test_open_detail_rejects_url_mismatch() -> None:
    """钉住的标签页停在**别的**页面（URL 对不上 res_id）→ 判失败、连正文都不读。"""
    real = cx.submit_task
    calls = []

    def _submit(bridge, action, params, source="collect-exec", timeout=60.0):
        calls.append({"action": action, "params": dict(params or {})})
        if action == "new_tab":
            return {"ok": True, "result": {"ok": True, "tab": {"tab_id": 99}}}
        if action == "snapshot":
            return {"ok": True, "result": {"url": "https://h.liepin.com/search/getConditionItem#session"}}
        return {"ok": True, "result": {"text": "简历编号：别人的"}}

    cx.submit_task = _submit
    try:
        r = cx.open_detail(5, "rid_W1", wait=0, reread_wait=0)
    finally:
        cx.submit_task = real
    ok(r.get("ok") is False and r.get("wrong_page") is True,
       "URL 对不上：判失败（没读到这个人的页）", json.dumps(r, ensure_ascii=False)[:200])
    ok(not any(c["action"] == "page_text" for c in calls),
       "URL 对不上：**连正文都不读**（省一次误判）", json.dumps([c["action"] for c in calls]))
    ok(any(c["action"] == "close_tab" and c["params"].get("tab_id") == 99 for c in calls),
       "URL 对不上：照样关掉这个标签页", "")


def test_dry_run_plan_is_really_dry() -> None:
    """🔴 修掉的真 bug：`--plan --dry-run` 过去会**真开详情、真写库**（跑完才写 dry_run=true）。

    现在 `run_plan(dry_run=True)` → run_auto 不开详情、不写库，**轨迹也如实记 dry_run**。
    """
    job = "J-T-PLAN-DRY"
    clean(job)
    plan = {"job_code": job, "keywords": ["机械设计 非标"], "conds": [],
            "judge": {"industry": ["新松"], "role": ["电气"], "prefer": "industry"}}
    srch, _ = fake_search()
    rp, _ = fake_read_pages()
    dcalls = {"n": 0}

    def _open(tab, sid):
        dcalls["n"] += 1
        return {"ok": True, "chars": 10, "truncated": False, "text": "x"}

    tr = cx.run_plan(plan, max_pages=1, details_per_page=1, tab=0, no_quota=True,
                     read_page=rp, open_detail=_open, turn_page_fn=fake_turn(ok=False),
                     db_root=TMP, plan_path="fake_plan.json", search_fn=srch, dry_run=True,
                     page_gap=(0, 0))
    ok(dcalls["n"] == 0, "dry-run（--plan）：**一次详情都没开**", str(dcalls["n"]))
    ok(tr.get("dry_run") is True, "dry-run（--plan）：轨迹如实记 dry_run=True", str(tr.get("dry_run")))
    ok(tr.get("db_path") is None, "dry-run（--plan）：没写库（无 db_path）", str(tr.get("db_path")))
    ok(not job_db.db_path(job, root=TMP).exists(), "dry-run（--plan）：库文件根本没建出来", "")


def test_brake_is_wired() -> None:
    """🔴 修掉的真 bug（2026-09-16 真跑实测）：⛔「停小猎跑腿」以前**只接在 `run_page` 里**，
    `run_auto` / `--plan` 那条路**根本不查它** → 老板点停完全无效，最后只能**硬杀进程**
    （代价：这次跑的轨迹/报告没生成）。
    现在 `run_auto`（每页开头 + 每两个详情之间）和 `run_plan`（每开一条新关键字之前）都查。
    """
    job = "J-T-BRAKE"
    clean(job)
    plan = {"job_code": job, "keywords": ["机械设计 非标"], "conds": ["city_current=南京"],
            "judge": {"industry": ["叉车"], "role": ["机械设计"], "prefer": "industry"}}
    rp, rpcalls = fake_read_pages()
    srch, _ = fake_search()
    dcalls = {"n": 0}

    def _open(tab, sid):
        dcalls["n"] += 1
        return {"ok": True, "chars": 10, "truncated": False, "text": "x"}

    real_stop = cx.stop_requested
    cx.stop_requested = lambda since: True          # 假装老板刚点了「停小猎跑腿」
    try:
        tr = cx.run_plan(plan, max_pages=1, details_per_page=1, tab=0, no_quota=True,
                         read_page=rp, open_detail=_open, turn_page_fn=fake_turn(ok=True),
                         db_root=TMP, plan_path="fake_plan.json", search_fn=srch, page_gap=(0, 0))
        # run_auto 那条路也要接上（直接从 run_auto 进）
        job2 = "J-T-BRAKE2"
        clean(job2)
        tr2 = cx.run_auto(job2, "kw", [], max_pages=3, details_per_page=1, tab=0, no_quota=True,
                          read_page=fake_read(), open_detail=_open, turn_page_fn=fake_turn(ok=True),
                          db_root=TMP, open_gap=(0, 0), page_gap=(0, 0), profile=PROF)
    finally:
        cx.stop_requested = real_stop
    ok(dcalls["n"] == 0, "⛔刹车：一点停就**一个详情都不开**", str(dcalls["n"]))
    ok(rpcalls["n"] == 0, "⛔刹车(run_plan)：连页都不读（在开新关键字那步就停）", str(rpcalls["n"]))
    ok(any("人工停止" in n for n in tr["notes"]), "⛔刹车：轨迹如实记「人工停止」", str(tr["notes"][:3]))
    ok(len(tr2["rounds"]) == 0, "⛔刹车(run_auto)：读页之前就停（0 页）", str(len(tr2["rounds"])))


def main() -> None:
    print("== collect_exec 端到端单测（假依赖，不碰猎聘）==")
    TMP.mkdir(parents=True, exist_ok=True)
    # ⚠️ `stop_requested` 会**真发一个 HTTP 到桥**（读 stopped_at）。测试一律不许碰网络/kill 桥，
    #    所以整场替换成"永远没被停过"；专用用例 `test_brake_is_wired` 会临时改成 True 来验刹车。
    cx.stop_requested = lambda since: False
    try:
        test_dry_run()
        test_real_run()
        test_render()
        test_failure_paths()
        test_auto_paging()
        test_run_plan()
        test_search_failure_never_collects()
        test_no_live_bridge()
        test_search_page_tolerates_navigate_timeout()
        test_preflight_blocks_bad_plan()
        test_search_page_reports_pool()
        test_open_detail_pins_tab_and_closes_it()
        test_open_detail_rejects_wrong_page()
        test_open_detail_refuses_without_tab_id()
        test_open_detail_rejects_url_mismatch()
        test_dry_run_plan_is_really_dry()
        test_brake_is_wired()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
