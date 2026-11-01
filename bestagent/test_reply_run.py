#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_reply_run.py — `reply_run.py` 的单测（**不联网、不碰桥、不碰真库**）

覆盖：
  1. 会话列表解析（元素列表 → 行；整页文本 → 时间贴回）
  2. "最后一句是谁说的"判定（我们发的 / 系统噪音 / 真回复 / 没读到）
  3. 对号（同姓 + 职位；**存疑就不认**）
  4. 落台账（幂等：同一句话不重复记；**没回的人不记事件**）
  5. 重出报告（台账一进，等回复→有回复）

夹具 = 2026-09-20 职聊页**实测**结构（元素几何 + 整页文本形状），不是编的。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import job_db  # noqa: E402
import reply_run as rr  # noqa: E402


class _Tmp:
    """临时目录（**不用 tempfile**：本机沙箱里 %TEMP% 写不进去 → 用工作区里的目录，跑完删掉）。"""

    def __enter__(self):
        self.p = (Path(__file__).resolve().parent / "data" / "_test_tmp"
                  / f"t{os.getpid()}_{int(time.time() * 1000)}")
        self.p.mkdir(parents=True, exist_ok=True)
        return self.p

    def __exit__(self, *a):
        shutil.rmtree(self.p, ignore_errors=True)
        return False

OK, FAIL = [], []


def chk(name: str, cond: bool, extra: str = "") -> None:
    (OK if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f" ｜ {extra}" if extra and not cond else ""))


# ── 夹具：元素列表（几何照实测：姓名 span left≈156/宽≤60/高≈21；职位 left≈200/宽≈102）──

def el(i, name, top, left, width, height=21.0, role="span"):
    return {"index": i, "role": role, "name": name, "value": "",
            "rect": {"top": top, "left": left, "width": width, "height": height}}


def row_els(i0, name, position, top, *, read="", unread="", preview="", preview_w=367.0, preview_left=192.0):
    els = [el(i0, name, top, 156.0, 44.0), el(i0 + 1, position, top, 200.0, 102.0)]
    i = i0 + 2
    if read:
        els.append(el(i, f"[{read}]", top + 22, 156.0, 31.0, 20.0))
        i += 1
    if unread:
        els.insert(0, el(i0 - 1, unread, top + 1, 135.0, 7.0, 13.0))
    if preview:
        els.append(el(i, preview, top + 24.7, preview_left, preview_w, 13.3))
    return els


ELEMENTS = [
    el(0, "猎聘诚猎通", 0, 35, 143, 48, "a"),
    el(1, "沟通", 0, 348, 80, 48, "a"),
    el(2, "设置", 72, 1225, 28, 15),
    el(3, "未读", 165, 118, 44),                      # 顶部筛选签（不是会话行！）
    el(4, "全部", 120, 102, 60),                       # 顶部签
    # 会话行（照实测：郭浩/赵梦霁/余先生/翁志远/朱伟俊/余洋/程先生/孙升升/董先生）
    *row_els(10, "郭浩", "机械设计工程师", 209, read="未读",
             preview="南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC", preview_w=2491.0),
    *row_els(20, "赵梦霁", "机械设计工程师", 283, read="未读",
             preview="南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC", preview_w=2702.0),
    *row_els(30, "余先生", "机械设计工程师", 357, read="未读",
             preview="南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC", preview_w=2677.0),
    *row_els(40, "翁志远", "机械工程师", 431, read="未读",
             preview="南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC", preview_w=2479.0),
    *row_els(50, "朱伟俊", "机械设计工程师", 505, read="未读",
             preview="你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！"),
    *row_els(60, "余洋", "机械设计", 653, read="未读",
             preview="你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！"),
    *row_els(70, "程先生", "非标自动化机械设计", 727, read="已读",
             preview="你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！"),
    *row_els(80, "孙升升", "机械工程师", 801, preview="您可以修改打招呼语，去修改＞＞", preview_w=180.0,
             preview_left=156.0),
    *row_els(90, "郑先生", "化学分析师", 949, preview="什么职位", preview_w=48.0, preview_left=156.0),
    *row_els(100, "董先生", "Web前端工程师 / 技术合伙人", 1647, unread="2",
             preview="这是我的简历，合适的话可以随时联系我～", preview_w=228.0, preview_left=156.0),
]

PAGE_TEXT = """首页
沟通
找人
职位
猎头服务

杨猛
全部
新招呼
我发起的
我回复的
有简历
全部职位
未读
郭浩
机械设计工程师
14:22

南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC 负责物流自动化设备结构设计

赵梦霁
机械设计工程师
14:20

[未读]南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC

余先生
机械设计工程师
14:19

[未读]南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC

翁志远
机械工程师
14:18

[未读]南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC

朱伟俊
机械设计工程师
09:11

[未读]你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！

余洋
机械设计
9月18日

[未读]你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！

程先生
非标自动化机械设计
9月18日

[已读]你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！

孙升升
机械工程师
9月18日

您可以修改打招呼语，去修改＞＞

郑先生
化学分析师
9月11日

什么职位

2
董先生
Web前端工程师 / 技术合伙人
7月16日

这是我的简历，合适的话可以随时联系我～

未选中会话
沟通职位:
设置沟通职位
用户简历已设置隐私状态
"""

INTRO = ("南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC\n"
         "负责物流自动化设备结构设计，含整体方案、三维/二维图纸与BOM输出\n"
         "郭**：看到您4年机械设计经验，符合2年及以上要求，跟这个岗位挺对口，方便聊聊吗？")

# 会话详情（--deep）夹具：照实测结构（我们的话后面跟"已读/未读"回执；对方的话后面没有）
CONV_FLOW = """郭浩
在职，看看新机会
南京
28岁
本科
工作4年
简历预览
南京木理智能科技有限公司
·
机械设计工程师
南京工业大学
·
机械工程
沟通职位:
设置沟通职位
求职期望:
南京
机械设计师
13-16k·14薪
14:21
你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！
未读
南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC
负责物流自动化设备结构设计，含整体方案、三维/二维图纸与BOM输出
郭**：看到您4年机械设计经验，符合2年及以上要求，跟这个岗位挺对口，方便聊聊吗？
未读
索要简历
索要手机
索要微信
超级聊聊
发送""".splitlines()

CONV_REPLIED = """郑先生
苏州
26岁
简历预览
昆山联滔电子有限公司
·
化学分析师
求职期望:
苏州
质量检测员/测试员
8-9k
9月11日 18:07
你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！
已读
9月11日 20:28
什么职位
索要简历
发送""".splitlines()


def cand(cid, name, position, company, detail=None):
    return {"id": cid, "source_id": f"s{cid}", "display_name": name,
            "display_company": company, "display_position": position, "detail": detail or {}}


GREETED = [
    cand(5, "郭**", "机械设计工程师", "南京木理智能科技有限公司",
         {"intro_msg_sent": INTRO}),
    cand(4, "赵**", "机械设计工程师", "南京马波斯自动化设备有限公司", {"intro_msg_sent": INTRO}),
    cand(60, "余**", "机械设计工程师", "南京埃斯顿精密装备有限公司", {"intro_msg_sent": INTRO}),
    cand(59, "翁**", "机械工程师", "南京中拓科技有限公司", {"intro_msg_sent": INTRO}),
    cand(1, "朱**", "机械设计工程师", "中船鹏力塑造", {}),
    cand(50, "余**", "机械设计", "江苏电投新能源有限公司", {}),
    cand(32, "程**", "非标自动化机械设计", "儒拉玛特自动化技术(苏州)有限公司", {}),
    cand(42, "孙**", "机械工程师", "南京国睿信维软件有限公司", {}),
]


def main() -> None:
    print("=== 1. 会话列表解析（看元素列表）===")
    rows = rr.parse_rows(ELEMENTS)
    chk("解析出 10 条会话行", len(rows) == 10, f"实际 {len(rows)}: {[r['name'] for r in rows]}")
    names = [r["name"] for r in rows]
    chk("顶部筛选签『未读/全部』没被当成人名", "未读" not in names and "全部" not in names)
    first = rows[0]
    chk("第一行 = 郭浩/机械设计工程师/[未读]", (first["name"], first["position"], first["read"]) ==
        ("郭浩", "机械设计工程师", "未读"), json.dumps(first, ensure_ascii=False))
    chk("郭浩行的预览是我们发的岗位介绍", first["preview"].startswith("南京 机械工程师"))
    cheng = [r for r in rows if r["name"] == "程先生"][0]
    chk("程先生 = [已读]", cheng["read"] == "已读")
    dong = [r for r in rows if r["name"] == "董先生"][0]
    chk("董先生的未读徽标 = 2", dong["unread"] == "2", json.dumps(dong, ensure_ascii=False))
    zheng = [r for r in rows if r["name"] == "郑先生"][0]
    chk("郑先生行的最后一句 = 什么职位（对方的话）", zheng["preview"] == "什么职位")

    print("\n=== 2. 时间贴回（整页文本）===")
    rr.attach_times(rows, PAGE_TEXT.splitlines())
    got = {r["name"]: r["time"] for r in rows}
    chk("郭浩 14:22 / 程先生 9月18日 / 董先生 7月16日",
        got.get("郭浩") == "14:22" and got.get("程先生") == "9月18日" and got.get("董先生") == "7月16日",
        json.dumps(got, ensure_ascii=False))

    print("\n=== 3. 文本兜底解析（元素列表解析不出来时）===")
    trows = rr.parse_rows_from_text(PAGE_TEXT.splitlines())
    chk("文本兜底也能解析（≥8 行）", len(trows) >= 8, str(len(trows)))
    tn = [(r["name"], r["position"]) for r in trows]
    chk("文本兜底的姓名/职位没写反（郭浩/机械设计工程师 + 程先生/非标自动化机械设计）",
        ("郭浩", "机械设计工程师") in tn and ("程先生", "非标自动化机械设计") in tn, str(tn))
    chk("文本兜底没把详情面板的『14:21』当行", all(r["name"] not in ("机械设计师",) for r in trows))

    print("\n=== 4. 「最后一句是谁说的」判定 ===")
    ours = rr.our_texts_for(GREETED[0])
    chk("默认短语 → ours", rr.judge_preview(rr.DEFAULT_PHRASE, ours)[0] == "ours")
    chk("岗位介绍首行 → ours", rr.judge_preview("南京 机械工程师 穿梭车/提升机 年薪12-15万·14薪 12个HC 负责物流…",
                                            ours)[0] == "ours")
    chk("系统提示 → noise", rr.judge_preview("您可以修改打招呼语，去修改＞＞", ours)[0] == "noise")
    chk("索要简历 → noise", rr.judge_preview("我想要一份你的简历，你是否同意？", ours)[0] == "noise")
    chk("『什么职位』→ reply", rr.judge_preview("什么职位", ours) == ("reply", "什么职位"))
    chk("空 → empty", rr.judge_preview("", ours)[0] == "empty")
    chk("海投语（不是我们发的）→ reply", rr.judge_preview("这是我的简历，合适的话可以随时联系我～", ours)[0] == "reply")

    print("\n=== 5. 对号 ===")
    m = rr.match_rows(rows, GREETED)
    got_ids = sorted(x["cand"]["id"] for x in m["matches"])
    chk("8 个打过招呼的人全部对上号", got_ids == [1, 4, 5, 32, 42, 50, 59, 60], str(got_ids))
    by_id = {x["cand"]["id"]: x["row"]["name"] for x in m["matches"]}
    chk("余**（机械设计工程师）→ 页面『余先生』", by_id.get(60) == "余先生")
    chk("余**（机械设计）→ 页面『余洋』", by_id.get(50) == "余洋")
    chk("程**（打码名）→ 页面『程先生』", by_id.get(32) == "程先生")
    chk("没对上号的会话行 = 郑先生/董先生", sorted(r["name"] for r in m["unmatched_rows"]) == ["董先生", "郑先生"],
        str([r["name"] for r in m["unmatched_rows"]]))
    chk("没有存疑项", m["ambiguous"] == [])

    print("\n=== 6. 同姓+同职位两个人 → 判『存疑』，不许瞎认 ===")
    two = [cand(901, "翁**", "机械工程师", "A公司"), cand(902, "翁**", "机械工程师", "B公司")]
    m2 = rr.match_rows([r for r in rows if r["name"] == "翁志远"], two)
    chk("两个翁** 都不上号（存疑）", m2["matches"] == [] and len(m2["ambiguous"]) == 2,
        json.dumps([[x["cand"]["display_name"], x["row"]["name"]] for x in m2["ambiguous"]], ensure_ascii=False))
    one = [cand(901, "翁**", "机械工程师", "A公司")]
    m3 = rr.match_rows([r for r in rows if r["name"] == "翁志远"], one)
    chk("只有一个同姓同职位的人 → 正常上号", len(m3["matches"]) == 1 and m3["matches"][0]["cand"]["id"] == 901,
        json.dumps(m3["matches"], ensure_ascii=False, default=str))
    other = [cand(903, "王**", "机械工程师", "A公司")]
    m5 = rr.match_rows([r for r in rows if r["name"] == "翁志远"], other)
    chk("不同姓（王 vs 翁）→ 不上号", m5["matches"] == [] and m5["ambiguous"] == [])
    m4 = rr.match_rows([r for r in rows if r["name"] == "翁志远"], GREETED)
    chk("翁** 对 翁志远（同姓+职位一致）", m4["matches"][0]["cand"]["id"] == 59)

    print("\n=== 7. --deep：会话详情/消息流解析 ===")
    fl = rr.parse_flow(CONV_FLOW, 0)
    chk("公司 = 南京木理智能科技有限公司", fl["company"] == "南京木理智能科技有限公司", fl["company"])
    chk("职位 = 机械设计工程师", fl["position"] == "机械设计工程师", fl["position"])
    chk("期望读到南京/机械设计师", "南京" in fl["expect"] and "机械设计师" in fl["expect"], str(fl["expect"]))
    chk("消息 2 条且都算『我们』（带未读回执）",
        len(fl["messages"]) == 2 and all(x["from"] == "我们" for x in fl["messages"]),
        json.dumps(fl["messages"], ensure_ascii=False))
    chk("对方消息 0 条（郭浩没回）", sum(1 for x in fl["messages"] if x["from"] == "对方") == 0)
    fl2 = rr.parse_flow(CONV_REPLIED, 0)
    theirs = [x for x in fl2["messages"] if x["from"] == "对方"]
    chk("郑先生：对方的话被认出来 = 什么职位", len(theirs) == 1 and theirs[0]["text"] == "什么职位",
        json.dumps(fl2["messages"], ensure_ascii=False))
    chk("郑先生：我们的话 = 默认短语", fl2["messages"][0]["from"] == "我们")

    print("\n=== 7b. --deep 起点：不许把列表后面的会话行当成消息流 ===")
    combined = PAGE_TEXT.splitlines() + ["郑先生"] + CONV_REPLIED[1:]
    lrows = rr.parse_rows_from_text(combined)
    rr.attach_times(lrows, combined)
    list_end = max([int(x.get("line") or -1) for x in lrows] + [-1]) + 1
    dstart = rr.find_detail_start(combined, list_end, "郑先生")
    chk("详情起点 = 列表之后的那一行（不是列表里的郑先生行）",
        combined[dstart].strip() == "郑先生" and dstart > list_end - 1,
        f"start={dstart} list_end={list_end} line={combined[dstart].strip()!r}")
    flow2 = rr.parse_flow(combined, dstart)
    msgs2 = flow2["messages"]
    chk("消息流只认详情区的时间戳（第一句 = 我们发的默认短语）",
        msgs2 and msgs2[0]["from"] == "我们" and msgs2[0]["text"] == rr.DEFAULT_PHRASE,
        json.dumps(msgs2, ensure_ascii=False))
    chk("没把列表行当消息（列表里的『非标自动化机械设计』没进来）",
        all("非标自动化机械设计" not in x["text"] for x in msgs2),
        json.dumps(msgs2, ensure_ascii=False))
    chk("对方的那句话被认出来 = 什么职位",
        [x for x in msgs2 if x["from"] == "对方"] and
        [x for x in msgs2 if x["from"] == "对方"][-1]["text"] == "什么职位")

    print("\n=== 8. 台账：幂等 + 没回的不记事件 ===")
    with _Tmp() as td:
        root = Path(td)
        con = job_db.open_db("J-T-REPLY", root=root)
        job_db.set_job_meta(con, "J-T-REPLY", "测试岗")
        ids = {}
        for c in GREETED:
            r = job_db.upsert_candidate(con, "J-T-REPLY", {
                "source_id": c["source_id"], "display_name": c["display_name"],
                "display_company": c["display_company"], "display_position": c["display_position"]})
            ids[c["id"]] = r["id"]
            job_db.append_event(con, r["id"], "J-T-REPLY", "打招呼", "第1次问候", "杨猛")
        con.close()

        # 第 1 次：只记"没回"的人的读态（不记事件）
        con = job_db.open_db("J-T-REPLY", root=root)
        a = rr.record_reply(con, "J-T-REPLY", ids[32], "", read="已读", at="9月18日")
        n_events = con.execute("SELECT COUNT(*) FROM candidate_events WHERE event_type='回复'").fetchone()[0]
        con.close()
        chk("没回的人：不记『回复』事件（只存读态）", n_events == 0 and a == "skipped")

        # 第 2 次：他回了一句 → 记一笔；再跑一次 → 不重复记
        con = job_db.open_db("J-T-REPLY", root=root)
        a1 = rr.record_reply(con, "J-T-REPLY", ids[32], "什么职位", read="已读", at="9月18日")
        a2 = rr.record_reply(con, "J-T-REPLY", ids[32], "什么职位", read="已读", at="9月18日")
        rows_ev = [dict(r) for r in con.execute(
            "SELECT note FROM candidate_events WHERE event_type='回复'")]
        det = json.loads(con.execute("SELECT detail_json FROM match_results WHERE candidate_id=?",
                                     (ids[32],)).fetchone()["detail_json"])
        con.close()
        chk("第一次记 → created", a1 == "created")
        chk("同一句话再跑 → skipped（不重复记）", a2 == "skipped")
        chk("台账只有 1 条『回复』", len(rows_ev) == 1, str(rows_ev))
        chk("note 里有他说的原话", "什么职位" in rows_ev[0]["note"], rows_ev[0]["note"])
        chk("detail_json 存了读态与最后一句",
            det.get("chat_read") == "已读" and det.get("last_reply_text") == "什么职位",
            json.dumps(det, ensure_ascii=False))

        # 换一句新话 → 再记一笔（他说了新话就该记）
        con = job_db.open_db("J-T-REPLY", root=root)
        a3 = rr.record_reply(con, "J-T-REPLY", ids[32], "好的，方便聊聊", read="已读")
        n2 = con.execute("SELECT COUNT(*) FROM candidate_events WHERE event_type='回复'").fetchone()[0]
        con.close()
        chk("换了新话 → 再记一笔（只增不改）", a3 == "created" and n2 == 2, str(n2))

    print("\n=== 9. 只读安全绳：写动作一律拒绝 ===")
    for bad in ("type", "click_by_text", "click_by_text "):
        try:
            rr.act(bad, {})
            chk(f"动作 {bad} 被拒绝", False)
        except RuntimeError as e:
            chk(f"动作 {bad} 被拒绝", "只读" in str(e))
        except Exception as e:  # noqa: BLE001
            chk(f"动作 {bad} 被拒绝（非桥错误）", True, f"{type(e).__name__}")

    print("\n=== 10. 出报告：回复一进台账，报告从『等回复』变『有回复』===")
    with _Tmp() as td:
        root = Path(td)
        base = root / "chat"
        (base / "J-T-REP2" / "reports").mkdir(parents=True)
        con = job_db.open_db("J-T-REP2", root=base)
        job_db.set_job_meta(con, "J-T-REP2", "测试岗")
        cid = job_db.upsert_candidate(con, "J-T-REP2", {
            "source_id": "s1", "display_name": "郭**", "display_position": "机械设计工程师"})["id"]
        job_db.save_match(con, "J-T-REP2", cid, {"total_score": 80, "verdict": "推荐",
                                                 "match_points": ["4年非标机械设计"], "detail": {}})
        job_db.append_event(con, cid, "J-T-REP2", "打招呼", "第1次问候", "杨猛")
        con.close()
        import greeting_report as gr
        r1 = gr.write_report("J-T-REP2", plan={"threshold": 70}, base=base,
                             now=datetime(2026, 9, 20, 15, 0))
        chk("重出报告：1 人在『等回复』", r1["daily"]["waiting"] == 1 and r1["daily"]["replied"] == 0,
            json.dumps(r1["daily"], ensure_ascii=False))
        con = job_db.open_db("J-T-REP2", root=base)
        rr.record_reply(con, "J-T-REP2", cid, "什么职位", read="已读")
        con.close()
        r2 = gr.write_report("J-T-REP2", plan={"threshold": 70}, base=base,
                             now=datetime(2026, 9, 20, 15, 5))
        chk("他回了一句 → 报告变『有回复 1』", r2["daily"]["replied"] == 1 and r2["daily"]["waiting"] == 0,
            json.dumps(r2["daily"], ensure_ascii=False))
        chk("报告 HTML 也出了", bool(r2["html"]) and Path(r2["html"]).exists())

    print(f"\n{'='*60}\n通过 {len(OK)}｜失败 {len(FAIL)}")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
