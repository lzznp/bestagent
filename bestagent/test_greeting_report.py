# -*- coding: utf-8 -*-
"""greeting_report（打招呼报告）单测 —— **纯本地，不联网、不调模型**。

跑法（bestagent 目录，lzstudy 解释器）：python test_greeting_report.py

覆盖：
1. 主名单 = **未打过招呼 + 过线**（按分降序），受名额上限截断并如实报"另有 N 人没列"；
2. **分数不够的不进名单**（只给计数）—— 老板口径；
3. 分区：等回复中（含"打了几天"）/ 有回复 / 已排除；
4. 跟进冷却：到 N 天进 "该跟进"；
5. **时间窗**：工作日白天可以；午休/晚上不行；周末不行（理由要说人话）；
6. **前置检查（发脾气）**：报告没生成 → 拒绝；报告比采集旧 → 拒绝；都 OK → 放行；
7. HTML 本地渲染出得来（含姓名/话术/链接），JSON 是资产。
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
TMP = BASE / "data" / "_selftest_tmp" / "greeting_report"
JOB = "J-T-GREET"

import greeting_report as gr  # noqa: E402
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


MON = datetime(2026, 9, 14, 10, 0)      # 周一 10:00
SAT = datetime(2026, 9, 12, 10, 0)      # 周六 10:00


def setup():
    d = TMP / JOB
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    (d / "reports").mkdir(parents=True, exist_ok=True)
    (d / "jd.txt").write_text("职位：机械设计工程师（南京）", encoding="utf-8")
    con = job_db.open_db(JOB, root=TMP)
    ids = {}

    def add(key, name, raw, first_seen):
        r = job_db.upsert_candidate(con, JOB, {
            "source_id": f"sid_{key}", "display_name": name, "raw_content": raw,
            "summary_text": f"卡片 {key}", "display_company": "某公司",
            "display_position": "机械工程师", "active_badge": "今天活跃"})
        ids[key] = r["id"]
        # ⚠️ first_seen_at 由 upsert 内部写死为"现在" → 测试要用 SQL 直接改成想考的日子
        con.execute("UPDATE candidates SET first_seen_at=? WHERE id=?", (first_seen, r["id"]))

    add("A", "高分甲", "简历全文 A", "2026-09-14 09:00:00")      # 今天采到
    add("G", "新面孔庚", "简历全文 G", "2026-09-14 09:10:00")
    add("H", "也够线辛", "简历全文 H", "2026-09-14 09:20:00")
    add("B", "打过乙", "简历全文 B", "2026-09-10 09:00:00")
    add("C", "回复丙", "简历全文 C", "2026-09-09 09:00:00")
    add("D", "催跟丁", "简历全文 D", "2026-09-08 09:00:00")
    add("E", "低分戊", "", "2026-09-07 09:00:00")
    add("F", "不过线己", "简历全文 F", "2026-09-06 09:00:00")

    def match(key, score, verdict, msg1=False, card_only=False):
        job_db.save_match(con, JOB, ids[key], {
            "score": score, "verdict": verdict, "confidence": "中",
            "match_points": [f"{key} 对口"], "concerns": [f"{key} 待核"],
            "summary": f"{key} 一句话", "detail": {"on_card_only": card_only, "criteria": "标准口径",
                                                   **({"greeting_msg1": f"{key}话术1",
                                                       "greeting_msg2": f"{key}话术2"} if msg1 else {})}},
            raw_hash=f"h_{key}")

    for k, sc, v in (("A", 85, "推荐"), ("G", 73, "推荐"), ("H", 71, "推荐"), ("B", 80, "推荐"),
                     ("C", 76, "推荐"), ("D", 74, "推荐")):
        match(k, sc, v, msg1=True)
    match("E", 65, "待定", card_only=True)
    match("F", 40, "不推荐")

    def ev(key, etype, when, note=""):
        eid = job_db.append_event(con, ids[key], JOB, etype, note)
        # ⚠️ append_event 也不收 created_at（内部写"现在"）→ 同样用 SQL 改成想考的日子
        con.execute("UPDATE candidate_events SET created_at=? WHERE id=?", (when, eid))

    ev("B", "打招呼", "2026-09-12 10:00:00")     # 2 天前打过（未到冷却）
    ev("C", "打招呼", "2026-09-09 10:00:00")     # 5 天前打过 + 已回复
    ev("C", "回复", "2026-09-10 10:00:00", "说考虑中")
    ev("D", "打招呼", "2026-09-10 10:00:00")     # 4 天前打过（≥3 天 → 该跟进）
    con.commit()
    con.close()
    return ids


def plan(**kw):
    p = {"job_code": JOB, "strictness": "标准", "threshold": 70, "max_list": 2,
         "criteria": "只卡硬性条件", "follow_up_days": 3}
    p.update(kw)
    return p


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    ids = setup()

    rep = gr.build(JOB, plan(), db_root=TMP, base=TMP, now=MON)
    names = [x["name"] for x in rep["main"]]
    ok(names == ["高分甲", "新面孔庚"],
       "主名单：**未打过 + 过线**按分降序、受名额上限截断（甲 85 / 庚 73）",
       json.dumps(names, ensure_ascii=False))
    ok(names[0] == "高分甲", "主名单：最高分在最前", json.dumps(names, ensure_ascii=False))
    ok(all(x["score"] >= 70 for x in rep["main"]), "主名单：**没有低于入围线的人**",
       json.dumps([x["score"] for x in rep["main"]]))
    ok(all(x["msg1"] for x in rep["main"]), "主名单：都带**预生成的话术**", "")
    ok(rep["daily"]["hidden_by_cap"] == 1,
       "名额上限：够线 3 人、max_list=2 → 如实报「另有 1 人没列」", json.dumps(rep["daily"]))
    ok(rep["daily"]["excluded"] == 2,
       "已排除：不推荐的 F + 不过线的 E = 2（**不列名单**）", json.dumps(rep["daily"]))
    ok([w["name"] for w in rep["waiting"]] == ["打过乙", "催跟丁"] or
       sorted(w["name"] for w in rep["waiting"]) == ["催跟丁", "打过乙"],
       "等回复：B/D 两人（打过没回）", json.dumps([w["name"] for w in rep["waiting"]], ensure_ascii=False))
    ok([w["name"] for w in rep["replied"]] == ["回复丙"], "有回复：C 一人",
       json.dumps([w["name"] for w in rep["replied"]], ensure_ascii=False))
    ok([w["name"] for w in rep["follow_up_due"]] == ["催跟丁"],
       "跟进冷却：D 打了 4 天（≥3 天）→ 进「该跟进」，B 才 2 天不进",
       json.dumps([w["name"] for w in rep["follow_up_due"]], ensure_ascii=False))
    ok(rep["daily"]["new_today"] == 2,
       "日报：今天新采到的人（甲/庚进了名单）= 2", json.dumps(rep["daily"]))
    ok(rep["gate"]["time_ok"] is True, "时间窗：周一 10:00 **可以打**", rep["gate"]["time_reason"])

    # 时间窗
    ok(gr.window_ok(datetime(2026, 9, 14, 12, 30), gr.DEFAULT_WINDOW)[0] is False,
       "时间窗：工作日 12:30（午休）→ **不能打**", "")
    ok("不在允许时段" in gr.window_ok(datetime(2026, 9, 14, 20, 0), gr.DEFAULT_WINDOW)[1],
       "时间窗：晚上 20:00 → 不能打且理由说人话", "")
    ok(gr.window_ok(SAT, gr.DEFAULT_WINDOW)[0] is False,
       "时间窗：周六 → **不能打**", "")
    ok(gr.window_ok(MON, plan(time_window={}))[0] is True,
       "时间窗：计划里没设 → 不限（可以打）", "")

    # 前置检查（发脾气）
    r0 = gr.greeting_ready(JOB, plan=plan(), db_root=TMP, base=TMP, now=MON)
    ok(r0["ok"] is False and "还没生成" in " ".join(r0["problems"]),
       "前置检查：**报告还没生成 → 拒绝打**（不许自己临场挑人）", json.dumps(r0["problems"], ensure_ascii=False)[:120])
    reps = TMP / JOB / "reports"
    (reps / "打招呼报告_20260914-100000.json").write_text("{}", encoding="utf-8")
    r1 = gr.greeting_ready(JOB, plan=plan(), db_root=TMP, base=TMP, now=MON)
    ok(r1["ok"] is True, "前置检查：报告在、也没更新的采集 → 放行", json.dumps(r1["problems"], ensure_ascii=False))
    import time as _t
    _t.sleep(0.05)
    (reps / "collect_20260914-110000.json").write_text("{}", encoding="utf-8")   # 比报告新
    r2 = gr.greeting_ready(JOB, plan=plan(), db_root=TMP, base=TMP, now=MON)
    ok(r2["ok"] is False and "旧" in " ".join(r2["problems"]),
       "前置检查：**报告比采集旧 → 拒绝打**（不拿旧名单打新池子）",
       json.dumps(r2["problems"], ensure_ascii=False)[:120])
    (reps / "collect_plan_20260914-120000.json").write_text("{}", encoding="utf-8")  # 计划不算采集
    r3 = gr.greeting_ready(JOB, plan=plan(), db_root=TMP, base=TMP, now=MON)
    ok(r3["ok"] is False, "前置检查：`collect_plan_*` **不算**新采集（仍判旧）", "")
    r4 = gr.greeting_ready(JOB, plan=plan(), db_root=TMP, base=TMP, now=SAT)
    ok(r4["time_ok"] is False, "前置检查：周六 → time_ok=False（能出报告，但不能打）", "")

    # JSON 资产 + HTML 壳
    out = reps / "打招呼报告_20260914-130000.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    html = report_html.render_greeting(rep)
    ok("<html" in html and "高分甲" in html and "话术1" in html and "猎聘详情页" in html,
       "HTML 壳：渲染出姓名/话术/直达链接", str(len(html)))
    ok("今天该打" in html and "等回复中" in html and "有回复" in html and "已排除" in html,
       "HTML 壳：四个分区都在", "")
    ok("仅卡片评估" in report_html.render_greeting(
        {**rep, "main": [{"name": "卡片人", "score": 66, "on_card_only": True, "msg1": "x",
                          "url": "u", "summary": "s"}]}),
       "HTML 壳：卡片人如实标「仅卡片评估」", "")
    ok(not json.loads(out.read_text(encoding="utf-8")).get("errors"),
       "JSON 资产：可解析、无多余字段", "")

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
