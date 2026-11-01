# -*- coding: utf-8 -*-
"""只读探针：本岗 job.db 的分数分布 + 关键字来源（不改任何文件）。
输出 _probe_jobdb_scores_20260921.txt（UTF-8）。
"""
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "chat" / "J-CHAT-20260921-143843" / "job.db"
OUT = HERE / "_probe_jobdb_scores_20260921.txt"
L = []


def o(s=""):
    L.append(str(s))


def main():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute('PRAGMA table_info("candidates")')]
    o(f"[cols] {cols}")
    o("[count] " + str(con.execute('select count(*) from "candidates"').fetchone()[0]))
    o("[score dist] local_score -> count")
    for sc, n in con.execute('select local_score, count(*) from candidates group by local_score order by local_score desc'):
        o(f"   {sc}: {n}")
    o("[round_tag dist]")
    for t, n in con.execute('select coalesce(round_tag,\'\'), count(*) from candidates group by 1 order by 2 desc'):
        o(f"   {t!r}: {n}")
    o("[status dist]")
    for t, n in con.execute('select coalesce(status,\'\'), count(*) from candidates group by 1 order by 2 desc'):
        o(f"   {t!r}: {n}")
    o("[top 8]")
    for row in con.execute('select display_name, display_company, display_position, local_score, '
                           'length(coalesce(raw_content,\'\')) from candidates '
                           'order by coalesce(local_score,-1) desc limit 8'):
        o(f"   {row}")
    o("[time range] first_seen_at / last_seen_at")
    for row in con.execute('select min(first_seen_at), max(last_seen_at) from candidates'):
        o(f"   {row}")
    con.close()
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(L))


if __name__ == "__main__":
    main()
