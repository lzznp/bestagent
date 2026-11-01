# -*- coding: utf-8 -*-
"""只读探针：核对小猎那份 job.db 汇报（2026-09-21 21:26）里的关键数字。
输出 _probe_verify_report_20260921.txt（UTF-8）。
"""
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "chat" / "J-CHAT-20260921-143843" / "job.db"
OUT = HERE / "_probe_verify_report_20260921.txt"
L = []


def o(s=""):
    L.append(str(s))


def main():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    q = lambda s: con.execute(s).fetchone()[0]
    o(f"[总人数] {q('select count(*) from candidates')}")
    o(f"[distinct source_id] {q('select count(distinct source_id) from candidates')}")
    o(f"[distinct content_hash] {q('select count(distinct content_hash) from candidates')}")
    o(f"[status] " + json.dumps(dict(con.execute("select status, count(*) from candidates group by 1").fetchall()), ensure_ascii=False))
    o(f"[用户版本] user_version = {q('pragma user_version')}")
    o("")
    o("[分数字段] " + str(con.execute("select min(local_score), avg(local_score), max(local_score) from candidates").fetchone()))
    o("[分数区间]")
    for lo, hi in ((80, 100), (60, 79), (40, 59), (20, 39), (0, 19)):
        n = q(f"select count(*) from candidates where local_score >= {lo} and local_score <= {hi}")
        o(f"   {lo}-{hi}: {n}")
    o("")
    o("=== 关键核对：正文含『欧姆龙』vs local_hits 标了『欧姆龙』 ===")
    n_raw_omron = q("select count(*) from candidates where raw_content like '%欧姆龙%'")
    n_hit_omron = q("select count(*) from candidates where local_hits like '%欧姆龙%'")
    n_hit_empty = q("select count(*) from candidates where local_hits is null or local_hits=''")
    n_miss = q("select count(*) from candidates where raw_content like '%欧姆龙%' "
               "and (local_hits is null or local_hits not like '%欧姆龙%')")
    n_full = q("select count(*) from candidates where length(coalesce(raw_content,''))>2000")
    o(f"[raw_content 含欧姆龙] {n_raw_omron}")
    o(f"[local_hits 含欧姆龙] {n_hit_omron}")
    o(f"[local_hits 为空/NULL] {n_hit_empty}")
    o(f"[raw 含欧姆龙 但 local_hits 不含] {n_miss}")
    o(f"[已开详情(>2000字)] {n_full}")
    o("")
    o("[公司写法数] " + str(q("select count(distinct display_company) from candidates")))
    o("[先导智能系人数] " + str(q("select count(*) from candidates where display_company like '%先导%'")))
    o("[远景动力系人数] " + str(q("select count(*) from candidates where display_company like '%远景%'")))
    o("[奥特维系人数] " + str(q("select count(*) from candidates where display_company like '%奥特维%'")))
    o("")
    o("[raw 含 先导 的人数] " + str(q("select count(*) from candidates where raw_content like '%先导%'")))
    con.close()
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(L))


if __name__ == "__main__":
    main()
