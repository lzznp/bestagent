# -*- coding: utf-8 -*-
"""探索 candidates 表：规模 / 岗位分布 / 内容样例（只读参考库）"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

DB = r"D:\study\bestagent\参考代码\岗位招聘单机版\recruitment.db"
con = sqlite3.connect(DB)
cur = con.cursor()

n = cur.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
print(f"总条数: {n}")

print("\n-- 按 job_code 分布 --")
for r in cur.execute("SELECT job_code, COUNT(*) FROM candidates GROUP BY job_code"):
    print(r)

print("\n-- 按 source_platform 分布 --")
for r in cur.execute("SELECT source_platform, COUNT(*) FROM candidates GROUP BY source_platform"):
    print(r)

print("\n-- display_position 统计（前 25）--")
for r in cur.execute("SELECT display_position, COUNT(*) FROM candidates GROUP BY display_position ORDER BY 2 DESC LIMIT 25"):
    print(r)

print("\n-- raw_content 长度分布 --")
for r in cur.execute("SELECT MIN(length(raw_content)), MAX(length(raw_content)), AVG(length(raw_content)) FROM candidates"):
    print(f"min={r[0]} max={r[1]} avg={r[2]:.0f}")

print("\n-- 样例：一条完整候选人的前 1500 字符 --")
row = cur.execute("SELECT id, job_code, display_name, display_company, display_position, raw_content FROM candidates WHERE raw_content IS NOT NULL AND length(raw_content) > 500 LIMIT 1").fetchone()
if row:
    print(f"id={row[0]} job_code={row[1]} name={row[2]} company={row[3]} position={row[4]}")
    print("----")
    print(row[5][:1500])

con.close()
