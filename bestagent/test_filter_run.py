# -*- coding: utf-8 -*-
"""filter_run（细筛）单测 —— **假 LLM，0 花费、不联网**。

跑法（bestagent 目录，lzstudy 解释器）：python test_filter_run.py

覆盖（每条都对应一个真会踩的坑）：
1. dry-run：只算账，**一次模型都不调、一个字都不写库**；
2. 真评：逐人调 → score/verdict/匹配点/疑虑点/总结**落 match_results**；
3. **输入指纹缓存**：同口径第二遍 = 0 次调用（老板最关心的"不重复付费"）；
4. **口径变了 → 自动重评**（宽松度/口径文字进了指纹）；
5. 缺 `job_code` → **直接报错**（不许写错岗；上一场野库 bug 的同类纪律）；
6. LLM 报错（如余额不足）→ **如实记 error、不写假分、不炸整批**；
7. 话术：**只对过线的人生成**，且存进 `detail_json`（不改 schema）；第二遍不重复生成；
8. 提示词是**动态**的（口径进了 prompt）、模板里的 `#` 说明行**不发模型**；
9. 模型给了乱七八糟的 verdict → 按分数**规范化**（并留 `verdict_raw` 供追溯）；
10. 只有卡片的人也能评（标注 `card_only`），`--limit` 能只跑小样。
"""
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
TMP = BASE / "data" / "_selftest_tmp" / "filter_run"
JOB = "J-T-FILTER"

import filter_run as fr  # noqa: E402
import job_db  # noqa: E402
import llm_client as llm  # noqa: E402

PASS = 0
FAIL = 0


def ok(cond: bool, name: str, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [XX] {name} {extra}")


def setup_job(cands: list[tuple]) -> None:
    """cands = [(source_id, name, raw_content, summary_text), …]"""
    d = TMP / JOB
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    (d / "reports").mkdir(parents=True, exist_ok=True)
    (d / "jd.txt").write_text("职位：机械设计工程师（南京）\n要求：非标机械设计，Solidworks", encoding="utf-8")
    con = job_db.open_db(JOB, root=TMP)
    for sid, name, raw, summ in cands:
        job_db.upsert_candidate(con, JOB, {"source_id": sid, "display_name": name,
                                           "raw_content": raw, "summary_text": summ})
    con.close()


def reset_db() -> None:
    """删掉本岗库（setup_job 会 rmtree 整个岗目录，所以一般用不到；留着手工清场用）。"""
    db = job_db.db_path(JOB, root=TMP)
    for p in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
        if p.exists():
            p.unlink()


def plan(**kw) -> dict:
    p = {"job_code": JOB, "strictness": "标准", "threshold": 70, "criteria": "按 JD 硬性条件评",
         "boss_words": "先生成一份打招呼报告吧"}
    p.update(kw)
    return p


def fake_llm(scores: dict, *, fail_markers=(), calls=None):
    """假 LLM：按 prompt 里出现的候选人标记（CAND1…）返回预定分数；话术调用另认。"""
    def _chat(env, prompt, **kw):
        if calls is not None:
            calls.append(prompt)
        if "打招呼文案" in prompt:          # 话术模板
            return {"content": json.dumps({"msg1": "南京机械设计岗，非标方向，薪资可谈",
                                           "msg2": "看到您做过非标设计，正对口"},
                                          ensure_ascii=False),
                    "tokens": 100, "model": "fake", "elapsed": 0.1}
        for mk in fail_markers:
            if mk in prompt:
                raise llm.LLMError("余额不足", "INSUFFICIENT_BALANCE", 402)
        for mk, sc in scores.items():
            if mk in prompt:
                v = "推荐" if sc >= 70 else ("待定" if sc >= 50 else "不推荐")
                return {"content": json.dumps({"score": sc, "verdict": v, "confidence": "中",
                                               "match_points": [f"{mk} 对口"], "concerns": ["年限待核"],
                                               "summary": f"{mk} 一句话总结"}, ensure_ascii=False),
                        "tokens": 500, "model": "fake", "elapsed": 0.1}
        return {"content": json.dumps({"score": 50, "verdict": "待定", "summary": "兜底"},
                                      ensure_ascii=False), "tokens": 500, "model": "fake", "elapsed": 0.1}
    return _chat


def rows_of(job=JOB):
    con = job_db.open_db(job, root=TMP)
    out = [dict(r) for r in con.execute("SELECT * FROM match_results WHERE job_code=?", (job,))]
    con.close()
    return out


C1 = ("sid1", "汪**", "CAND1 简历全文：非标机械设计 8 年，南京，Solidworks", "CAND1 卡片")
C2 = ("sid2", "宋**", "CAND2 简历全文：电气工程师 10 年，南京", "CAND2 卡片")
C3 = ("sid3", "王**", "", "CAND3 卡片：机械工程师 5 年，常州")


def main() -> None:
    from framework_config import PROMPTS
    if TMP.exists():
        shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    ENV = {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "fake"}

    # ① dry-run
    setup_job([C1, C2, C3])
    calls: list[str] = []
    tr = fr.run(JOB, plan(), env=ENV, chat_fn=fake_llm({}, calls=calls), db_root=TMP,
                chat_dir=TMP, prompts_dir=PROMPTS, dry_run=True)
    ok(not calls, "dry-run：**一次模型都没调**", str(len(calls)))
    ok(tr["counts"]["targets"] == 3, "dry-run：算了要评 3 人", json.dumps(tr["counts"]))
    ok(not rows_of(), "dry-run：**一个字都没写库**", str(len(rows_of())))
    ok(tr["estimate"]["input_tokens"] > 0, "dry-run：给出输入 token 数量级估算", str(tr["estimate"]))

    # ② 真评 + ③ 缓存
    calls.clear()
    tr = fr.run(JOB, plan(), env=ENV, chat_fn=fake_llm({"CAND1": 82, "CAND2": 45, "CAND3": 71},
                                                       calls=calls), db_root=TMP,
                chat_dir=TMP, prompts_dir=PROMPTS)
    ms = rows_of()
    ok(len(ms) == 3, "真评：3 人都落进 match_results", str(len(ms)))
    got = {r["candidate_id"]: r for r in ms}
    sc = sorted(int(r["total_score"]) for r in ms)
    ok(sc == [45, 71, 82], "真评：分数如实落库（82/45/71）", str(sc))
    ok(all(r["raw_hash"] for r in ms), "真评：都写了输入指纹 raw_hash", "")
    ok(len(tr["greetings"]) == 2, "话术：只对**过线**（82/71 ≥ 70）生成 2 条，45 分不生成",
       json.dumps([g.get("candidate_id") for g in tr["greetings"]]))
    det = json.loads(got[ms[0]["candidate_id"]]["detail_json"])
    _with_greet = [m for m in ms if "greeting_msg1" in json.loads(m["detail_json"] or "{}")]
    ok(len(_with_greet) == 2 and all(json.loads(m["detail_json"])["greeting_msg1"] for m in _with_greet),
       "话术：**存进 detail_json**（不改 schema，小猎可直接用）",
       json.dumps([list(json.loads(m["detail_json"]).keys())[:3] for m in _with_greet], ensure_ascii=False))
    ok(all(json.loads(m["detail_json"]).get("criteria") for m in ms),
       "留痕：每人 detail 里记了**本次口径**（可追溯/可重放）", "")

    n_first = len([c for c in calls if "打招呼文案" not in c])
    calls.clear()
    tr2 = fr.run(JOB, plan(), env=ENV, chat_fn=fake_llm({"CAND1": 82, "CAND2": 45, "CAND3": 71},
                                                        calls=calls), db_root=TMP,
                 chat_dir=TMP, prompts_dir=PROMPTS)
    ok(not calls, "缓存：**同口径第二遍 0 次调用**（不重复付费）", f"第一遍 {n_first} 次，第二遍 {len(calls)} 次")
    ok(tr2["counts"]["skipped_cached"] == 3, "缓存：3 人都被判为'已评过且口径没变'",
       json.dumps(tr2["counts"]))

    # ④ 口径变了 → 重评
    calls.clear()
    fr.run(JOB, plan(strictness="宽松", criteria="这次口径：年限/学历不卡，沾边就算相关"),
           env=ENV, chat_fn=fake_llm({"CAND1": 88, "CAND2": 66, "CAND3": 75}, calls=calls),
           db_root=TMP, chat_dir=TMP, prompts_dir=PROMPTS)
    ok(len([c for c in calls if "打招呼文案" not in c]) == 3,
       "口径变了：**自动重评 3 人**（口径进了输入指纹）", str(len(calls)))
    after = sorted(int(r["total_score"]) for r in rows_of())
    ok(after == [66, 75, 88], "口径变了：新分数覆盖旧分数（88/66/75）", str(after))

    # ⑤ 缺 job_code
    try:
        fr.run("", plan(job_code=""), env=ENV, chat_fn=fake_llm({}), db_root=TMP,
               chat_dir=TMP, prompts_dir=PROMPTS)
        ok(False, "缺 job_code：必须报错", "没报错")
    except ValueError as e:
        ok("job_code" in str(e), "缺 job_code：直接报错（不许写错岗）", str(e)[:80])

    # ⑥ LLM 报错 → 如实记、不写假分、不炸批
    setup_job([C1, C2, C3])
    calls.clear()
    tr3 = fr.run(JOB, plan(), env=ENV, chat_fn=fake_llm({"CAND1": 80, "CAND3": 72},
                                                       fail_markers=("CAND2",), calls=calls),
                 db_root=TMP, chat_dir=TMP, prompts_dir=PROMPTS)
    ok(len(tr3["errors"]) == 1 and "余额" in tr3["errors"][0]["error"],
       "报错：如实记 error（含'余额不足'人话）", json.dumps(tr3["errors"], ensure_ascii=False)[:160])
    ok(len(rows_of()) == 2, "报错：**失败那个人不写假分**（库里只有 2 行）", str(len(rows_of())))
    ok(len([c for c in calls if "打招呼文案" not in c]) == 3,
       "报错：**不炸整批**，另外两人照样评完", str(len(calls)))

    # ⑦ 提示词动态 + # 注释行不发模型 + 卡片人也能评
    setup_job([C1, C2, C3])
    calls.clear()
    fr.run(JOB, plan(criteria="本次口径：只要机械设计对口即可，年限不卡"),
           env=ENV, chat_fn=fake_llm({"CAND1": 80, "CAND2": 80, "CAND3": 80}, calls=calls),
           db_root=TMP, chat_dir=TMP, prompts_dir=PROMPTS)
    match_prompts = [c for c in calls if "打招呼文案" not in c]
    ok(all("本次口径：只要机械设计对口即可，年限不卡" in c for c in match_prompts),
       "动态提示词：**老板的口径进了发给模型的提示词**", "")
    ok(all("模板占位符" not in c and "不会发给模型" not in c for c in match_prompts),
       "动态提示词：模板里 `#` 说明行**没发给模型**", "")
    ok(all("{criteria}" not in c and "{job_raw_text}" not in c for c in match_prompts),
       "动态提示词：占位符都被替换（没漏）", "")
    card_prompt = [c for c in match_prompts if "CAND3" in c]
    ok(card_prompt and "CAND3 卡片" in card_prompt[0],
       "只有卡片的人：用卡片文本评（不假装有全文）", "")
    r3 = [r for r in rows_of() if json.loads(r["detail_json"] or "{}").get("on_card_only")]
    ok(len(r3) == 1, "只有卡片的人：detail 里标了 on_card_only", str(len(r3)))

    # ⑧ verdict 规范化（模型给了乱七八糟的词）
    def _weird(env, prompt, **kw):
        if "打招呼文案" in prompt:
            return {"content": json.dumps({"msg1": "a", "msg2": "b"}), "tokens": 10,
                    "model": "fake", "elapsed": 0}
        return {"content": json.dumps({"score": 91, "verdict": "非常棒", "summary": "s"},
                                      ensure_ascii=False), "tokens": 10, "model": "fake", "elapsed": 0}

    setup_job([C1])
    tr4 = fr.run(JOB, plan(threshold=95), env=ENV, chat_fn=_weird, db_root=TMP,
                 chat_dir=TMP, prompts_dir=PROMPTS)
    r = rows_of()[0]
    ok(r["verdict"] == "推荐", "规范化：模型给的怪 verdict「非常棒」→ 按分数归为「推荐」", str(r["verdict"]))
    ok(json.loads(r["detail_json"])["verdict_raw"] == "非常棒",
       "规范化：原始 verdict 留在 detail 里（可追溯，不偷偷改）", "")
    ok(not tr4["greetings"], "规范化：91 分但入围线 95 → **不生成话术**（口径说了算）",
       json.dumps(tr4["greetings"], ensure_ascii=False))

    # ⑨ --limit（小样试水）
    setup_job([C1, C2, C3])
    calls.clear()
    fr.run(JOB, plan(), env=ENV, chat_fn=fake_llm({"CAND1": 80, "CAND2": 80, "CAND3": 80}, calls=calls),
           db_root=TMP, chat_dir=TMP, prompts_dir=PROMPTS, limit=1)
    ok(len(rows_of()) == 1, "--limit 1：**只评 1 个人**（省钱小样）", str(len(rows_of())))

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
