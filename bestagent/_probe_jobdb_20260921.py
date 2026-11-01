# -*- coding: utf-8 -*-
"""只读探针：看本岗 job.db 里到底有多少人、多少条已读全文。不改任何文件。
输出 _probe_jobdb_20260921.txt（UTF-8）。
"""
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "chat" / "J-CHAT-20260921-143843" / "job.db"
OUT = HERE / "_probe_jobdb_20260921.txt"
L = []


def o(s=""):
    L.append(str(s))


def main():
    o(f"[db] {DB} exists={DB.exists()} size={DB.stat().st_size if DB.exists() else 'NA'}")
    for suf in ("-wal", "-shm"):
        p = Path(str(DB) + suf)
        o(f"[{suf}] exists={p.exists()} size={p.stat().st_size if p.exists() else 'NA'}")
    if not DB.exists():
        OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("OK(no db)")
        return
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    o(f"[tables] {tabs}")
    for t in tabs:
        try:
            n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
        except Exception as e:
            n = f"<{e}>"
        o(f"  {t}: {n}")
    # 候选人表的样子
    for t in tabs:
        if "cand" in t.lower() or t.lower() in ("people", "resume", "pool"):
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            o(f"[cols] {t} = {cols}")
            try:
                rows = con.execute(f'select * from "{t}" limit 2').fetchall()
                o(f"[sample] {t}: {rows}")
            except Exception as e:
                o(f"[sample] {t} err {e}")
    # 有没有全文
    for t in tabs:
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        if any(c.lower() in ("raw_content", "content", "detail_text") for c in cols):
            col = next(c for c in cols if c.lower() in ("raw_content", "content", "detail_text"))
            try:
                full = con.execute(f'select count(*) from "{t}" where length(coalesce("{col}",\'\'))>2000').fetchone()[0]
                nonempty = con.execute(f'select count(*) from "{t}" where length(coalesce("{col}",\'\'))>0').fetchone()[0]
                o(f"[全文] {t}.{col}: >2000字 {full} 条 / 非空 {nonempty} 条")
            except Exception as e:
                o(f"[全文] {t}.{col} err {e}")
    con.close()
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OK ->", OUT.name, "lines:", len(L))


if __name__ == "__main__":
    main()
