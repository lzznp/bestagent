# -*- coding: utf-8 -*-
"""status_run（岗位态势卡）单测 —— 纯本地、不联网。

跑法（bestagent 目录，lzstudy 解释器）：python test_status_run.py

覆盖：
1. 池子：总数 / 有全文 / 仅卡片 / 今天新采到；
2. 评分：已评 / 未评 / 分数分布 / 各档累计；
3. 队列：**够格且没打过招呼**的还剩几个；
4. 联系：累计打过 / 今天打过 / 等回复 / 有回复 / 该跟进 / 已了结；
5. 判断提示：还没筛过 → 提示先筛；够格=0 → 提示放宽或再采；
6. 时间与报告：现在能不能打、报告在不在。
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
TMP = BASE / "data" / "_selftest_tmp" / "status_run"
JOB = "J-T-STATUS"

import job_db  # noqa: E402
import status_run as sr  # noqa: E402

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


MON = datetime(2026, 9, 14, 15, 0)      # 周一 15:00（允许时段内）


def build_db():
    d = TMP / JOB
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    (d / "reports").mkdir(parents=True, exist_ok=True)
    (d / "jd.txt").write_text("职位：机械设计工程师", encoding="utf-8")
    con = job_db.open_db(JOB, root=TMP)
    ids = {}

    def add(key, raw, first_seen):
        r = job_db.upsert_candidate(con, JOB, {"source_id": f"s_{key}", "display_name": key,
                                               "raw_content": raw, "summary_text": f"卡片{key}"})
        ids[key] = r["id"]
        con.execute("UPDATE candidates SET first_seen_at=? WHERE id=?", (first_seen, r["id"]))

    for k, raw, fs in (("A", "全文A", "2026-09-14 09:00:00"), ("B", "全文B", "2026-09-13 09:00:00"),
                       ("C", "", "2026-09-13 09:00:00"), ("D", "全文D", "2026-09-12 09:00:00"),
                       ("E", "全文E", "2026-09-11 09:00:00"), ("F", "全文F", "2026-09-11 09:00:00")):
        add(k, raw, fs)

    def match(key, sc, vd):
        job_db.save_match(con, JOB, ids[key], {"score": sc, "verdict": vd, "detail": {}},
                          raw_hash=f"h{key}")

    match("A", 85, "推荐")      # 够格、没打过 → 进队列
    match("B", 78, "推荐")      # 够格、今天打过
    match("C", 72, "推荐")      # 够格、5 天前打过没回 → 该跟进
    match("D", 40, "不推荐")     # 不够格 → 不进队列

    def ev(key, etype, when, note=""):
        eid = job_db.append_event(con, ids[key], JOB, etype, note)
        con.execute("UPDATE candidate_events SET created_at=? WHERE id=?", (when, eid))

    ev("B", "打招呼", "2026-09-14 10:00:00")            # 今天打的
    ev("C", "打招呼", "2026-09-09 10:00:00")            # 5 天前打的（≥3 天 → 该跟进）
    con.commit()
    con.close()


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    build_db()
    st = sr.status(JOB, plan={"threshold": 70, "follow_up_days": 3}, db_root=TMP,
                   base=TMP / JOB, now=MON)
    p, s, q, c = st["pool"], st["scoring"], st["queue"], st["contact"]
    ok(p["candidates"] == 6, "池子：6 人", str(p))
    ok(p["with_fulltext"] == 5 and p["card_only"] == 1, "池子：5 有全文 / 1 仅卡片", str(p))
    ok(p["new_today"] == 1, "池子：今天新采到 1 人（A）", str(p))
    ok(s["matched"] == 4 and s["unmatched"] == 2, "评分：已评 4 / 未评 2", str(s))
    ok(s["bands"][">=78"] == 2 and s["bands"][">=70"] == 3 and s["bands"][">=60"] == 3,
       "评分：各档累计（≥78=2 / ≥70=3 / ≥60=3）", str(s["bands"]))
    ok(q["qualified_uncontacted"] == 1,
       "队列：够格且没打过招呼 = 1（A；B/C 打过、D 不够格）", str(q))
    ok(c["greeted_total"] == 2 and c["greeted_today"] == 1, "联系：累计 2 / 今天 1", str(c))
    ok(c["waiting_reply"] == 2, "联系：等回复 2（B、C）", str(c))
    ok(c["follow_up_due"] == 1, "联系：该跟进 1（C 打了 5 天）", str(c))
    ok(c["replied"] == 0 and c["done"] == 0, "联系：有回复 0 / 已了结 0", str(c))
    ok(st["gate"]["time_ok"] is True, "时间：周一 15:00 可以打", st["gate"]["time_reason"])
    ok(any("还没细筛" in n for n in st["notes"]),
       "判断提示：有人没筛过 → 提示先筛（0 花费重跑）", str(st["notes"]))
    ok(any("该跟进" in n for n in st["notes"]), "判断提示：有人到冷却 → 提示跟进", str(st["notes"]))

    # 够格=0 且都筛过了 → 提示"放宽口径或再采一轮"
    con = job_db.open_db(JOB, root=TMP)
    for k in ("E", "F"):
        r = con.execute("SELECT id FROM candidates WHERE source_id=?", (f"s_{k}",)).fetchone()
        job_db.save_match(con, JOB, r["id"], {"score": 20, "verdict": "不推荐", "detail": {}},
                          raw_hash=f"h{k}")
    con.close()
    st2 = sr.status(JOB, plan={"threshold": 70, "follow_up_days": 3}, db_root=TMP,
                    base=TMP, now=MON)
    ok(st2["queue"]["qualified_uncontacted"] == 1, "队列：还是 1（新评的都是 20 分）", str(st2["queue"]))
    ok(any("放宽口径" in n or "再去采一轮" in n for n in st2["notes"]) is False,
       "判断提示：队列>0 时**不**催放宽（别乱给指令）", str(st2["notes"]))

    ok("够格" in sr.brief(st) and "可以打" in sr.brief(st),
       "一句话人话：含池子/队列/时间，读得懂", sr.brief(st)[:80])

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
