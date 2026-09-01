# -*- coding: utf-8 -*-
"""导出预演标的：岗位 JD + 对应候选人池（从参考库，只读不改）
用法: python export_pool.py --job-code J20260401154437101390
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB = Path(r"D:\study\bestagent\参考代码\岗位招聘单机版\recruitment.db")
INBOX = Path(r"D:\study\bestagent\bestagent\data\inbox")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-code", required=True)
    args = parser.parse_args()
    jc = args.job_code

    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    job = cur.execute(
        "SELECT job_title, raw_content, status FROM jobs WHERE job_code=?", (jc,)
    ).fetchone()
    if not job:
        print(f"❌ jobs 表没有 {jc}")
        sys.exit(1)
    title, raw, status = job

    jd_path = INBOX / f"jd_{jc}.txt"
    jd_path.write_text(f"【岗位】{title}\n【状态】{status}\n" + (raw or ""), encoding="utf-8")
    print(f"✅ JD  -> {jd_path} ({len(raw or '')}字符)")

    rows = cur.execute(
        "SELECT id, display_name, display_position, raw_content FROM candidates "
        "WHERE job_code=? AND raw_content IS NOT NULL ORDER BY id",
        (jc,),
    ).fetchall()
    print(f"   池子候选人数: {len(rows)}")

    pool_path = INBOX / f"pool_{jc}.txt"
    parts = []
    for cid, name, pos, content in rows:
        head = f"候选#{cid} | 姓名: {name or '匿名'} | 职位: {pos or '未知'}"
        parts.append(head + "\n" + content)
    pool_path.write_text("\n\n---\n\n".join(parts), encoding="utf-8")
    print(f"✅ 池 -> {pool_path} ({pool_path.stat().st_size} 字节)")
    con.close()


if __name__ == "__main__":
    main()
