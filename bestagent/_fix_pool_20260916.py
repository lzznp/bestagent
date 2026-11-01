# -*- coding: utf-8 -*-
"""一次性数据修正（老板 2026-09-16 授权："人数和真全文一致就好了"）。

问题：094907 的 job.db 里有 3 行的 `raw_content` 不是简历，而是 **DSH 面板页**的文本
（根因 = `open_detail` 从 `new_tab` 返回里取错层级 → tab_id=0 → 扩展回退读"当前激活标签页"，
那次真跑有 3 次读到老板正在看的面板页）。

修法（**只降噪、不丢人**）：
  · `raw_content`/`content_hash` 置空 → 这 3 人**当"没采到全文"**（卡片/人全留着）；
  · `status` 从 'opened' 改成 'kept'（口径：只有卡片）；
  · 把"清了什么、为什么"落成一份审计 JSON 放进该岗 reports/（可追溯，不污染表）。

跑法（cwd = bestagent/）：
  python _fix_pool_20260916.py           # 只报告（dry-run）
  python _fix_pool_20260916.py --apply   # 真改
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
JOB = "J-CHAT-20260909-094907"
DB = Path(__file__).resolve().parent / "data" / "chat" / JOB / "job.db"
REPORTS = DB.parent / "reports"
MARK = "简历编号"          # 猎聘详情页正文锚点（真简历都有）


def counts(con) -> tuple:
    tot = con.execute("SELECT COUNT(*) FROM candidates WHERE job_code=?", (JOB,)).fetchone()[0]
    full = con.execute("SELECT COUNT(*) FROM candidates WHERE job_code=? "
                       "AND raw_content IS NOT NULL AND raw_content<>''", (JOB,)).fetchone()[0]
    return tot, full


def main() -> None:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    tot0, full0 = counts(con)
    print(f"改前：候选人 {tot0}｜有全文 {full0}")

    bad = con.execute("SELECT id, source_id, round_tag, local_score, status, content_hash, "
                      "raw_content FROM candidates WHERE job_code=? "
                      "AND raw_content IS NOT NULL AND raw_content<>'' "
                      "AND raw_content NOT LIKE ?", (JOB, f"%{MARK}%")).fetchall()
    print(f"要修的（全文里没有「{MARK}」= 采错页）：{len(bad)} 行")
    audit = []
    for r in bad:
        t = r["raw_content"] or ""
        rec = {"id": r["id"], "source_id": r["source_id"], "round_tag": r["round_tag"],
               "local_score": r["local_score"], "old_status": r["status"],
               "old_chars": len(t), "old_content_hash": r["content_hash"],
               "looks_like_dsh_panel": ("DSH" in t or "工作区" in t),
               "old_head": t[:80]}
        audit.append(rec)
        print(f"  · id={r['id']} {r['source_id'][:14]}… {r['round_tag']} "
              f"{len(t)}字 含DSH={'DSH' in t}")

    if not apply:
        print("\n（dry-run，没改任何东西；要真改加 --apply）")
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for rec in audit:
        con.execute("UPDATE candidates SET raw_content=NULL, content_hash=NULL, status='kept', "
                    "updated_at=? WHERE id=?", (now, rec["id"]))
    con.commit()
    tot1, full1 = counts(con)
    left = con.execute("SELECT COUNT(*) FROM candidates WHERE job_code=? AND raw_content IS NOT NULL "
                       "AND raw_content<>'' AND raw_content NOT LIKE ?", (JOB, f"%{MARK}%")).fetchone()[0]
    print(f"\n改后：候选人 {tot1}｜有全文 {full1}｜仍「不像简历」的 {left}")
    out = REPORTS / f"数据修正_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({
        "job_code": JOB, "when": now, "reason": "raw_content 采错页（DSH 面板页，非简历）",
        "root_cause": "collect_exec.open_detail 从 new_tab 返回取错层级 → tab_id=0 → 扩展回退读当前激活标签页",
        "action": "raw_content/content_hash 置空、status='opened'→'kept'（只降噪不丢人：卡片与人全留着）",
        "before": {"candidates": tot0, "with_fulltext": full0},
        "after": {"candidates": tot1, "with_fulltext": full1},
        "rows": audit}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"审计：{out.as_posix()}")
    con.close()


if __name__ == "__main__":
    main()
