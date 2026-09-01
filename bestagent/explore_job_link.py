# -*- coding: utf-8 -*-
"""查 candidates 与 jobs 对应 + 关键词命中（决定预演标的）"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

DB = r"D:\study\bestagent\参考代码\岗位招聘单机版\recruitment.db"
con = sqlite3.connect(DB)
cur = con.cursor()

print("-- jobs 表岗位对应 --")
for r in cur.execute("SELECT id, job_code, job_title, status FROM jobs"):
    print(r)

print("\n-- candidates 按 job_code 的职位分布 --")
for jc, cnt in cur.execute("SELECT job_code, COUNT(*) FROM candidates GROUP BY job_code"):
    print(f"\n{jc} ({cnt}条):")
    for r in cur.execute(
        "SELECT display_position, COUNT(*) FROM candidates WHERE job_code=? GROUP BY display_position ORDER BY 2 DESC LIMIT 8",
        (jc,),
    ):
        print("   ", r)

print("\n-- raw_content 关键词命中 --")
kws = ["GPU", "芯片", "编译", "驱动", "CUDA", "架构", "ROCm", "LLVM", "车载", "测试", "大数据", "光学", "算法"]
for kw in kws:
    n = cur.execute("SELECT COUNT(*) FROM candidates WHERE raw_content LIKE ?", (f"%{kw}%",)).fetchone()[0]
    print(f"  {kw}: {n} 条")

con.close()
