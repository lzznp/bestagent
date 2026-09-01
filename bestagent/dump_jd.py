# -*- coding: utf-8 -*-
"""从参考库 recruitment.db 取一条真实 JD 落到工作区 Inbox（只读参考库，不改）"""
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB = Path(r"D:\study\bestagent\参考代码\岗位招聘单机版\recruitment.db")
JOB_ID = 1  # GPGPU 软件高级架构师（8 条里信息最全）

con = sqlite3.connect(str(DB))
cur = con.cursor()
row = cur.execute(
    "SELECT id, job_title, raw_content, link FROM jobs WHERE id=?",
    (JOB_ID,),
).fetchone()
con.close()
if not row:
    print("❌ 没找到 job")
    sys.exit(1)

job_id, title, raw, link = row
out_dir = Path(r"D:\study\bestagent\bestagent\data\inbox")
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / f"jd_{job_id}.txt"
head = f"【岗位】{title}\n"
out.write_text(head + (raw or ""), encoding="utf-8")
print(f"✅ 已写入 {out}")
print(f"   标题: {title} | 长度: {len(raw or '')} 字符 | link: {link}")
