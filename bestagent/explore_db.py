# -*- coding: utf-8 -*-
"""临时探索脚本：列出参考代码样本库的表结构与行数（只读，不改库）"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

DB = r"D:\study\bestagent\参考代码\岗位招聘单机版\recruitment.db"

con = sqlite3.connect(DB)
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("TABLES:", tables)
for t in tables:
    cols = [c[1] for c in cur.execute(f'PRAGMA table_info("{t}")')]
    try:
        n = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    except Exception as e:
        n = f"ERR {e}"
    print(f"TABLE {t}: rows={n} cols={cols}")
con.close()
