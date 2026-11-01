# -*- coding: utf-8 -*-
"""一次性只读盘点：各岗位目录里到底有没有候选人库、有多少人、有多少份全文。"""
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CHAT = Path(__file__).resolve().parent / "data" / "chat"


def main() -> None:
    print("== data/chat/*/job.db 盘点（只读）==")
    for d in sorted(CHAT.iterdir()):
        if not d.is_dir():
            continue
        db = d / "job.db"
        reps = sorted([p.name for p in (d / "reports").glob("*.json")]) if (d / "reports").exists() else []
        collected = [n for n in reps if n.startswith("collected_")]
        collectj = [n for n in reps if n.startswith("collect_") and not n.startswith("collect_plan_")]
        plans = [n for n in reps if n.startswith("collect_plan_")]
        poolrep = [n for n in reps if n.startswith("pool_report_")]
        print(f"\n--- {d.name}")
        print(f"    reports: 采集轨迹 {len(collectj)}｜旧形态 collected_* {len(collected)}"
              f"｜计划 {len(plans)}｜③池评 {len(poolrep)}")
        if not db.exists():
            print("    job.db：**没有**")
            continue
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        try:
            tot = con.execute("SELECT COUNT(*) c FROM candidates WHERE job_code=?", (d.name,)).fetchone()["c"]
            full = con.execute("SELECT COUNT(*) c FROM candidates WHERE job_code=? "
                               "AND raw_content IS NOT NULL AND raw_content<>''", (d.name,)).fetchone()["c"]
            nofull = tot - full
            print(f"    job.db：**有** ｜候选人 {tot}（有全文 {full} / 只有卡片 {nofull}）"
                  f"｜{db.stat().st_size // 1024} KB")
            for r in con.execute("SELECT round_tag, COUNT(*) c, "
                                 "SUM(CASE WHEN raw_content<>'' THEN 1 ELSE 0 END) full_n, "
                                 "ROUND(AVG(score),1) avg_score, MIN(score) mn, MAX(score) mx "
                                 "FROM candidates WHERE job_code=? GROUP BY round_tag", (d.name,)):
                print(f"      · {r['round_tag']!r:<28} 行 {r['c']:>3}｜全文 {r['full_n']:>3}"
                      f"｜分数 avg {r['avg_score']} [{r['mn']}~{r['mx']}]")
            cols = [x[1] for x in con.execute("PRAGMA table_info(candidates)")]
            print(f"      列：{','.join(cols)}")
        except Exception as e:  # noqa: BLE001
            print(f"    读库出错：{e}")
        finally:
            con.close()

    print("\n== 跨岗同源检查（source_id 交集）==")
    sets = {}
    for d in sorted(CHAT.iterdir()):
        db = d / "job.db"
        if d.is_dir() and db.exists():
            con = sqlite3.connect(str(db))
            sets[d.name] = {r[0] for r in con.execute("SELECT source_id FROM candidates")}
            con.close()
    names = list(sets)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = sets[names[i]], sets[names[j]]
            if a and b:
                print(f"  {names[i]} ∩ {names[j]} = {len(a & b)} 个相同 source_id"
                      f"（各自 {len(a)}/{len(b)}）")


if __name__ == "__main__":
    main()
