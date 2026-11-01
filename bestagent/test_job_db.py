# -*- coding: utf-8 -*-
"""test_job_db.py — 岗位库（一岗一库）本地单测：**不碰猎聘、不调 LLM、可反复跑**。

跑法（bestagent 目录，lzstudy 解释器）：python test_job_db.py

测的是这次拍板的四条硬规矩：
1. **一岗一库**（两个岗 = 两个库文件，互不影响）
2. **本岗内候选人不重复**（三道锁：source_id 主锚点 / content_hash 兜底 / 匹配层 raw_hash 缓存）
3. **重跑安全**（全库幂等 upsert：同一个人第二次 = 更新，不新增）
4. **schema 唯一来源 + 可迁移**（user_version；重复开库不炸）
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

WS = Path(r"D:\study\bestagent\bestagent")
sys.path.insert(0, str(WS))
sys.path.insert(0, str(WS.parent / "bridge-agent"))

import job_db as jd  # noqa: E402

N = 0
TMP = WS / "data" / "_selftest_tmp"
TMP.mkdir(parents=True, exist_ok=True)
ROOT = TMP / "jobdb_case"
shutil.rmtree(ROOT, ignore_errors=True)   # 每次从干净开始


def ok(cond, msg, extra=""):
    global N
    assert cond, f"❌ {msg}" + (f"（实际：{extra}）" if extra else "")
    N += 1


JOB = "J-TEST-A"
JOB2 = "J-TEST-B"

# ── 1) 建库：表齐 + 版本对 ──
con = jd.open_db(JOB, root=ROOT)
p = jd.db_path(JOB, root=ROOT)
ok(p.exists() and p.name == "job.db", "一岗一库：建出 <岗位目录>/job.db")
tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
ok({"candidates", "match_results", "candidate_events", "pool_samples", "job_meta"} <= tables,
   "建库：5 张表齐（候选人/匹配/沟通记录/列表原文池/岗位元信息）")
ok(con.execute("PRAGMA user_version").fetchone()[0] == jd.SCHEMA_VERSION, "建库：user_version 写对")
ok(con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal", "建库：WAL 已开（多进程读写）")

# ── 2) 主锚点去重：同一个人第二次 = 更新不新增 ──
r1 = jd.upsert_candidate(con, JOB, {"source_id": "res_001", "summary_text": "张三 电气设计 南京",
                                    "local_score": 55, "local_hits": ["输送线"], "active_badge": "今天活跃"})
ok(r1["action"] == "created" and r1["first_time"], "主锚点：第一次 → created")
r2 = jd.upsert_candidate(con, JOB, {"source_id": "res_001", "local_score": 78,
                                    "structured": {"city": "南京", "edu": "本科"}})
ok(r2["action"] == "updated" and r2["id"] == r1["id"], "主锚点：同一 source_id 第二次 → updated（不新增）")
ok(jd.stats(con, JOB)["candidates"] == 1, "主锚点：库里仍只有 1 行")
row = jd.get_candidate(con, JOB, "res_001")
ok(row["local_score"] == 78, "更新：给了值的字段被刷新")
ok(row["summary_text"] == "张三 电气设计 南京" and row["active_badge"] == "今天活跃",
   "更新：**本次没给的字段保持原样**（不会把已有信息洗掉）")
ok(json.loads(row["structured"])["city"] == "南京" and json.loads(row["local_hits"]) == ["输送线"],
   "字段：dict/list 自动存成 JSON 字符串")

# ── 3) 增量：新人 → 新行；无 id 直接拒绝 ──
jd.upsert_candidate(con, JOB, {"source_id": "res_002", "local_score": 30})
ok(jd.stats(con, JOB)["candidates"] == 2, "增量：新 source_id → 新增一行")
try:
    jd.upsert_candidate(con, JOB, {"summary_text": "没有 id"})
    ok(False, "缺 source_id 必须报错")
except ValueError:
    ok(True, "缺 source_id → 直接报错（去重锚点不能缺）")

# ── 4) content_hash 复核（v2 改口径，2026-09-16）──
# 旧口径是"同 hash 就当同一人（duplicate）"→ 实测**会丢人**（两个 id 不同、原文相同的人被合并）。
# 新口径：source_id 是唯一主锚点；同 hash 只做**复核标记**（dup_of），**照样入库**。
a = jd.upsert_candidate(con, JOB, {"source_id": "res_003", "raw_content": "同一份简历全文…"})
b = jd.upsert_candidate(con, JOB, {"source_id": "res_004", "raw_content": "同一份简历全文…"})
ok(a["action"] == "created" and b["action"] == "created",
   "v2：两个不同 source_id → 都是 created（**不许因为原文相同就丢掉一个**）")
ok(b.get("dup_of") == a["id"], "v2：同 hash 只做复核标记 dup_of（记下来，但不合并）", str(b))
ok(jd.stats(con, JOB)["candidates"] == 4, "v2：两行都在（丢人比多留一行贵）")
ok(jd._migrate(con) == jd.SCHEMA_VERSION and con.execute("PRAGMA user_version").fetchone()[0] == 2,
   "schema：库已升到 v2（content_hash 不再是唯一约束）")
idx = con.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='candidates'").fetchall()
ok(not any("UNIQUE" in (r["sql"] or "").upper() and "content_hash" in (r["sql"] or "")
           for r in idx), "schema：candidates 上不再有 content_hash 唯一索引", str([r["name"] for r in idx]))

# ── 5) 空 raw 不能互撞（没开详情时 raw 为空）──
jd.upsert_candidate(con, JOB, {"source_id": "res_005"})
jd.upsert_candidate(con, JOB, {"source_id": "res_006"})
ok(jd.stats(con, JOB)["candidates"] == 6, "空 raw：content_hash 存 NULL，多条空 raw 互不冲突")

# ── 6) 粗筛名单：按本地分排序 + 过线 + 只看没评过的 ──
names = [c["source_id"] for c in jd.list_candidates(con, JOB, min_score=60)]
ok(names == ["res_001"], "list：min_score 过滤（只有 78 分那条过线）")
allc = [c["source_id"] for c in jd.list_candidates(con, JOB)]
ok(allc[0] == "res_001", "list：按 local_score 降序（粗筛先看最像的）")

# ── 7) 匹配结果：幂等 + 输入指纹缓存 ──
cid = r1["id"]
m1 = jd.save_match(con, JOB, cid, {"total_score": 82, "verdict": "推荐", "confidence": "高",
                                   "match_points": ["输送线经验"], "concerns": ["薪资偏高"]},
                   raw_hash="HASH_V1")
ok(m1["action"] == "created", "匹配：第一次 → created")
ok(jd.stats(con, JOB)["matched"] == 1, "匹配：库里 1 条")
ok(jd.get_cached_match(con, JOB, cid, "HASH_V1")["total_score"] == 82,
   "缓存：输入指纹没变 → 命中旧结果（不重复付费）")
ok(jd.get_cached_match(con, JOB, cid, "HASH_V2") is None,
   "缓存：岗位/简历文本变了（指纹不同）→ 不命中（该重评）")
jd.save_match(con, JOB, cid, {"total_score": 65, "verdict": "待定"}, raw_hash="HASH_V2")
ok(jd.stats(con, JOB)["matched"] == 1, "匹配：同一个人第二次 → 更新不新增（唯一键 (job_code,candidate_id)）")
ok(jd.get_cached_match(con, JOB, cid, "HASH_V2")["total_score"] == 65, "匹配：分数被刷新")
ok(json.loads(jd.get_cached_match(con, JOB, cid, "HASH_V2")["match_points"]) == ["输送线经验"],
   "匹配：match_points 是话术原料，更新时不被清空（本次没给则保持）")

# ── 8) 沟通记录 + 列表原文池 ──
jd.append_event(con, cid, JOB, "打招呼", note="话术1")
jd.append_event(con, cid, JOB, "回复", note="约面试")
jd.add_pool_sample(con, "列表页原文……", round_tag="r1")
s = jd.stats(con, JOB)
ok(s["events"] == 2 and s["pool_samples"] == 1, "台账/原文池：事件 2 条、原文 1 条")

# ── 9) 级联删：候选人删掉 → 匹配/事件跟着走（不留孤儿行）──
con.execute("DELETE FROM candidates WHERE id=?", (cid,))
con.commit()
ok(jd.stats(con, JOB)["matched"] == 0, "级联：候选人删除 → 匹配结果一起删（外键 ON DELETE CASCADE）")
ok(con.execute("SELECT COUNT(*) FROM candidate_events WHERE candidate_id=?", (cid,)).fetchone()[0] == 0,
   "级联：沟通记录一起删")

# ── 10) 一岗一库：两个岗两个文件，互不影响 ──
con2 = jd.open_db(JOB2, root=ROOT)
jd.upsert_candidate(con2, JOB2, {"source_id": "res_001", "local_score": 90})  # 同一个 source_id 在另一个岗
ok(jd.db_path(JOB, root=ROOT) != jd.db_path(JOB2, root=ROOT), "隔离：两个岗位 = 两个库文件")
ok(jd.stats(con2, JOB2)["candidates"] == 1 and jd.stats(con, JOB)["candidates"] == 5,
   "隔离：同一个 res_id 在另一个岗照样能入（跨岗不去重——这是拍板「不做跨岗」的直接后果）")

# ── 11) 重复开库不炸（迁移幂等）──
con3 = jd.open_db(JOB, root=ROOT)
ok(con3.execute("PRAGMA user_version").fetchone()[0] == jd.SCHEMA_VERSION and
   jd.stats(con3, JOB)["candidates"] == 5, "迁移：重复开库幂等（不炸、不丢数据）")

# ── 12) 副本库可独立带走（拷目录 = 带走全部资料）──
copy_root = TMP / "jobdb_copy"
shutil.rmtree(copy_root, ignore_errors=True)
(copy_root / JOB).mkdir(parents=True)
for suf in ("", "-wal", "-shm"):
    src = Path(str(p) + suf)
    if src.exists():
        shutil.copy2(src, copy_root / JOB / (p.name + suf))
con4 = jd.open_db(JOB, root=copy_root)
ok(jd.stats(con4, JOB)["candidates"] == 5, "搬运：整棵目录拷走 → 库打开即用（岗位资料可整体带走）")

for c in (con, con2, con3, con4):
    c.close()
shutil.rmtree(ROOT, ignore_errors=True)
shutil.rmtree(copy_root, ignore_errors=True)
print(f"\n✅ test_job_db：{N} 条断言全绿")
