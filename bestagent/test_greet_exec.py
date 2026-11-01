# -*- coding: utf-8 -*-
"""test_greet_exec（打招呼执行器）单测 —— **假桥，纯本地：不联网、不发送任何消息**。

跑法（bestagent 目录，lzstudy 解释器）：python test_greet_exec.py

覆盖（每条对应一个 2026-09-20 实测踩过的坑）：
 1. **默认 dry-run**：不加 yes → 一个人都不发（桥一个写动作都不该收到）；
 2. 没有报告 → 拒绝执行；
 3. 页面已是【继续沟通】→ 跳过（不重复骚扰）；
 4. **弹层判定看元素、不看 body_preview**（今天的假故障根因：预览被截断）；
 5. 弹层等不到（轮询超时）→ **不发送**，如实报错；
 6. 字没进输入框（回读失败）→ **不发空**；
 7. 点了发送但没生效 → **不许报成功**；
 8. 成功路径：落台账 + 话术存进 detail_json；
 9. 报告里没链接 → 跳过；报告里没 intro_msg → 停下不发。
"""
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
TMP = BASE / "data" / "_selftest_tmp" / "greet_exec"
JOB = "J-T-GREETX"

import greet_exec as ge  # noqa: E402
import job_db  # noqa: E402

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


INTRO = ("南京 机械工程师 穿梭车/提升机 12-15万·14薪 12个HC\n"
         "负责物流自动化设备结构设计\n"
         "测试甲：看到您7年经验，方便聊聊吗？")


# ── 假桥 ──────────────────────────────────────────────────────────────────

class FakeBridge:
    """记录所有动作；按脚本推进返回不同"快照"。**绝不联网**。"""

    def __init__(self, *, dialog=True, type_ok=True, send_ok=True, start="detail"):
        self.calls = []
        self.dialog, self.type_ok, self.send_ok = dialog, type_ok, send_ok
        self.stage = start

    def act(self, action, params=None, **kw):
        p = params or {}
        self.calls.append((action, p))
        if action == "new_tab":
            return {"tab": {"tab_id": 999}}
        if action == "click_by_text":
            t = str(p.get("text") or "")
            if t == "立即沟通":
                self.stage = "after_click"
            elif t == "发送" and self.send_ok:
                self.stage = "after_send"
        elif action == "click":
            if self.stage == "after_click":
                self.stage = "after_dialog_sent"
            elif self.stage == "after_dialog_sent":
                self.stage = "after_panel"          # 点【继续沟通】展开面板
        elif action == "type":
            self.stage = "after_type"
        return {"ok": True}

    def snap(self, tab_id):
        names = ["立即沟通", "超级聊聊", "查看联系方式"]
        if self.stage == "after_click":
            names = (["立即开聊", "不选择职位开聊", "修改打招呼语"] if self.dialog else ["立即沟通"])
        elif self.stage in ("after_dialog_sent", "after_panel", "after_type", "after_send"):
            names = ["继续沟通", "超级聊聊"]
        els = [{"index": i, "role": "span", "name": n,
                "rect": {"top": 300, "left": 112, "width": 48, "height": 18}}
               for i, n in enumerate(names)]
        if self.stage == "after_click" and self.dialog:
            els.append({"index": 90, "role": "button", "name": "",
                        "rect": {"top": 536, "left": 631, "width": 114, "height": 32}})
        if self.stage in ("after_panel", "after_type", "after_send"):
            val = INTRO if self.stage in ("after_type",) and self.type_ok else ""
            if self.stage == "after_send":
                val = ""
            els.append({"index": 69, "role": "textarea", "name": "请输入文字，按Enter键发送",
                        "rect": {"top": 620, "left": 522, "width": 434, "height": 60}, "value": val})
            els.append({"index": 75, "role": "span", "name": "发送",
                        "rect": {"top": 685, "left": 913, "width": 28, "height": 30}})
        return {"ok": True, "elements": els, "body_preview": "（预览被截断，脚本不许用它判断）"}


def install(bridge: FakeBridge):
    """把脚本里的桥调用 / sleep / 库路径都换掉（绝不碰真库、绝不联网）。"""
    ge.act = lambda action, params=None, **kw: bridge.act(action, params, **kw)
    ge.snap = lambda tab_id: bridge.snap(tab_id)
    ge.time = type("T", (), {"sleep": staticmethod(lambda *_: None)})()
    ge.bridge_up = lambda: True
    ge.CHAT = TMP
    ge.gr.CHAT = TMP          # ⚠️ greeting_ready() 读的是 greeting_report.CHAT（import 时定死）
    _open = ge.job_db.open_db
    ge.job_db.open_db = lambda job_code, root=None: _open(job_code, root=TMP)


# ── 夹具 ─────────────────────────────────────────────────────────────────

def setup(people=None):
    d = TMP / JOB
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    (d / "reports").mkdir(parents=True, exist_ok=True)
    (d / "jd.txt").write_text("机械工程师", encoding="utf-8")
    con = job_db.open_db(JOB, root=TMP)
    ids = {}
    for p in (people or [{"key": "A", "name": "测试甲"}]):
        r = job_db.upsert_candidate(con, JOB, {
            "source_id": "sid" + p["key"], "display_name": p["name"],
            "raw_content": "简历", "summary_text": "卡片", "display_company": "某公司",
            "display_position": "机械工程师", "active_badge": "今天活跃"})
        ids[p["key"]] = r["id"]
        job_db.save_match(con, JOB, r["id"], {"score": 80, "verdict": "推荐", "summary": "好"})
    con.close()
    return ids


def write_report(people):
    rep = {"job_code": JOB, "created_at": "2026-09-20 10:00:00",
           "plan": {"threshold": 70, "max_list": 20,
                    "time_window": {"days": [1, 2, 3, 4, 5, 6, 7], "slots": [["00:00", "23:59"]]}},
           "gate": {"now": "2026-09-20 10:00:00", "time_ok": True, "time_reason": "测试"},
           "job_intro": {"hook": "南京 机械工程师"}, "daily": {},
           "waiting": [], "follow_up_due": [], "replied": [], "main": people}
    return (TMP / JOB / "reports" / "打招呼报告_20260920-100000.json").write_text(
        json.dumps(rep, ensure_ascii=False), encoding="utf-8")


def person(ids):
    return {"candidate_id": ids["A"], "name": "测试甲", "score": 80, "intro_msg": INTRO,
            "url": "https://h.liepin.com/resume/showresumedetail/?res_id_encode=sidA"}


# ── 用例 ─────────────────────────────────────────────────────────────────

def t1_dry_run():
    print("\n[1] 默认 dry-run：一个人都不发")
    ge.CHAT = TMP
    ids = setup()
    write_report([person(ids)])
    b = FakeBridge()
    install(b)
    res = ge.run(JOB, yes=False)
    ok(res["dry_run"] is True and res["sent"] == [], "dry-run 不发送")
    ok(not any(a in ("new_tab", "click", "click_by_text", "type") for a, _ in b.calls),
       "dry-run 时桥一个写动作都没收到", str(b.calls[:3]))


def t2_no_report():
    print("\n[2] 没有报告 → 拒绝执行")
    ge.CHAT = TMP
    try:
        ge.run("J-T-NOREP", yes=False)
        ok(False, "应当拒绝")
    except SystemExit as e:
        ok("还没有打招呼报告" in str(e), "如实拒绝（没报告）", str(e))


def t3_already_greeted():
    print("\n[3] 页面已是【继续沟通】→ 跳过")
    b = FakeBridge(start="after_dialog_sent")
    install(b)
    got = ge.greet_one("https://x/", INTRO, name="测试甲")
    ok(got["ok"] is False and "打过招呼" in (got["error"] or ""), "已打过 → 跳过并说明", str(got))
    ok(not any(a == "click_by_text" for a, _ in b.calls), "一次点击都没发")


def t4_dialog_by_elements():
    print("\n[4] 弹层判定看元素（不看 body_preview）")
    b = FakeBridge(dialog=True)
    install(b)
    got = ge.greet_one("https://x/", INTRO, name="测试甲")
    ok(got["ok"] is True and got["sent_verified"] is True, "全流程通过", str(got.get("error")))
    ok(any("元素文字" in s or "几何特征" in s for s in got["steps"]), "步骤写明弹层判定依据", str(got["steps"]))
    ok(not any("没等到" in s for s in got["steps"]), "没有误报'没等到弹层'")


def t5_dialog_timeout():
    print("\n[5] 弹层等不到 → 不发送")
    b = FakeBridge(dialog=False)
    install(b)
    got = ge.greet_one("https://x/", INTRO, name="测试甲")
    ok(got["ok"] is False and "弹层" in (got["error"] or ""), "如实报'弹层没出来'", str(got.get("error")))
    ok(not any(a == "click_by_text" and p.get("text") == "发送" for a, p in b.calls), "**没有**点发送")


def t6_type_readback_fail():
    print("\n[6] 字没进输入框 → 不发空")
    b = FakeBridge(dialog=True, type_ok=False)
    install(b)
    got = ge.greet_one("https://x/", INTRO, name="测试甲")
    ok(got["ok"] is False and "没写进输入框" in (got["error"] or ""), "回读失败 → 停下", str(got.get("error")))
    ok(not any(a == "click_by_text" and p.get("text") == "发送" for a, p in b.calls), "没点发送")


def t7_send_not_effective():
    print("\n[7] 点了发送但没生效 → 不许报成功")
    b = FakeBridge(dialog=True, send_ok=False)
    install(b)
    got = ge.greet_one("https://x/", INTRO, name="测试甲")
    ok(got["ok"] is False and "没发出去" in (got["error"] or ""), "如实报'没发出去'", str(got.get("error")))


def t8_success_records():
    print("\n[8] 成功路径：落台账 + 话术存档")
    ge.CHAT = TMP
    ids = setup()
    write_report([person(ids)])
    b = FakeBridge(dialog=True)
    install(b)
    res = ge.run(JOB, yes=True)
    ok(bool(res["sent"]) and res["sent"][0]["verified"] is True, "报成功",
       json.dumps(res["sent"], ensure_ascii=False))
    con = job_db.open_db(JOB, root=TMP)
    evs = list(con.execute("SELECT event_type, note FROM candidate_events WHERE candidate_id=?", (ids["A"],)))
    ok(any(e[0] == "打招呼" for e in evs), "台账里有'打招呼'事件", str(evs))
    row = con.execute("SELECT detail_json FROM match_results WHERE candidate_id=?", (ids["A"],)).fetchone()
    detail = json.loads(row[0] or "{}")
    ok(detail.get("intro_msg_sent") == INTRO, "detail_json 里存了发出去的原文")
    con.close()


def t9_skip_and_no_intro():
    print("\n[9] 没链接 → 跳过；没 intro_msg → 停下不发")
    ge.CHAT = TMP
    ids = setup()
    write_report([{"candidate_id": ids["A"], "name": "测试甲", "score": 80, "intro_msg": INTRO, "url": ""}])
    b = FakeBridge()
    install(b)
    res = ge.run(JOB, yes=True)
    ok(bool(res["skipped"]) and "链接" in res["skipped"][0]["why"], "没链接 → 跳过",
       json.dumps(res["skipped"], ensure_ascii=False))
    b2 = FakeBridge()
    install(b2)
    got = ge.greet_one("https://x/", "", name="测试甲")
    ok(got["ok"] is False and "intro_msg" in (got["error"] or ""), "没岗位介绍 → 停下（不硬编）", str(got.get("error")))


def main() -> None:
    print("=" * 60)
    print("test_greet_exec：打招呼执行器（假桥，不联网、不发送）")
    print("=" * 60)
    for fn in (t1_dry_run, t2_no_report, t3_already_greeted, t4_dialog_by_elements,
               t5_dialog_timeout, t6_type_readback_fail, t7_send_not_effective,
               t8_success_records, t9_skip_and_no_intro):
        fn()
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
