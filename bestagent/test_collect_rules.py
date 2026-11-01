# -*- coding: utf-8 -*-
"""collect_rules 单测（纯本地、0 费用、不碰浏览器/猎聘）。

跑法（bestagent 目录，lzstudy 解释器）：python test_collect_rules.py

覆盖：
1. 卡片解析（真实卡片格式：活跃度两种写法 / 阅标记 / 城市带区 / 期望城市+职位+技能 / 工作与教育条目）
2. 简历硬伤（两段"至今"/时间重叠）
3. 打分与排序（行业命中优先；**没有行业命中的人分数压在 40 上限内** ← 2026-09-16 二改的核心）
4. 配额（老口径：29 人只开 5 个详情；drop 的永不开）／**死命令口径：0=不限=够格就开**
5. 停止规则（连续 2 页行业 0 / 硬顶 / 全页无人可开 / **硬顶 0=不限** / **连续不值得→换关键字**）
6. stage_plan（条件拼装）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_rules as cr  # noqa: E402

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


# ── 真实卡片（2026-09-16 从猎聘结果页 extract 下来的原文，别改格式）──────────
CARD_MECH = """在线
王**
阅
46岁
工作23年
本科
南京
求职期望：
南京机械工程师
夹具
cad
产品工艺
冲压工艺
非标机械
精益生产
solidworks
机械设计
团队管理经验

江苏玖元智能科技有限公司 · 机械工程师
2025.12-至今(9个月)

江阴富仁高科股份有限公司 · 机械工程师
2025.01-2025.12(11个月)

北京航空航天大学 · 机械电子工程/机电一体化 · 本科 · 统招
1996.09-2000.06(4年)

立即沟通"""

CARD_ELEC_INDUSTRY = """今天活跃
汪**
37岁
工作15年
本科
南京
求职期望：
南京电气工程师
eplan
控制柜设计
电气布线
部件选型

南京新松智能装备有限公司 · 电气设计工程师
2021.05-至今(5年4个月)

江苏华章物流科技股份有限公司 · 电气工程师
2018.07-2021.05(2年10个月)

南京工程学院 · 自动化 · 本科 · 统招
2013.09-2017.06(4年)

立即沟通"""

CARD_HIDDEN_ACTIVITY = """隐藏
活跃状态
赵**
39岁
工作15年
本科
南京
求职期望：
南京机械结构工程师
solidworks
非标机械

南京康尼电子科技有限公司 · 技术研发工程师
2016.05-至今(10年4个月)

南京朗劲风能设备制造有限公司 · 设计主管
2015.05-至今(11年4个月)

徐州工程学院 · 机械设计制造及其自动化 · 本科 · 统招
2007.09-2011.07(4年)

立即沟通"""

CARD_SALES = """30天内活跃
赖**
15岁
工作15年
大专
南京
求职期望：
南京售前技术支持

某某科技有限公司 · 售前技术支持
2020.01-2024.01(4年)

某某学院 · 市场营销 · 大专 · 统招
2010.09-2013.06(3年)

立即沟通"""



# 机械岗样例卡（094907 形态：叉车AGV / 非标 / solidworks）
CARD_MECH_JUDGE = """今天活跃
孙**
33岁
工作10年
本科
南京
求职期望：
南京机械设计工程师
非标机械
solidworks
传动
丝杆
减速器

江苏某某智能装备有限公司 · 机械设计工程师
2021.05-至今(5年4个月)

某某物流科技有限公司 · 机械工程师
2020.01-2021.05(1年5个月)

某某叉车AGV装备有限公司 · 机械设计工程师
2018.07-2021.05(2年10个月)

南京工程学院 · 机械设计制造及其自动化 · 本科 · 统招
2013.09-2017.06(4年)

立即沟通"""

def test_parse() -> None:
    c = cr.parse_card(CARD_MECH)
    ok(c["name"] == "王**", "解析：姓名（掩码）", c["name"])
    ok(c["age"] == 46, "解析：年龄", c["age"])
    ok(c["years"] == 23, "解析：工作年限", c["years"])
    ok(c["education"] == "本科", "解析：学历", c["education"])
    ok(c["edu_tongzhao"] == "统招", "解析：统招/非统招", c["edu_tongzhao"])
    ok(c["city"] == "南京", "解析：目前城市", c["city"])
    ok(c["activity"] == "在线", "解析：活跃度徽章", c["activity"])
    ok(c["read_mark"] is True, "解析：『阅』标记", str(c["read_mark"]))
    ok(c["expect_city"] == "南京" and c["expect_position"] == "机械工程师",
       "解析：期望城市+职位", f'{c["expect_city"]}/{c["expect_position"]}')
    ok("夹具" in c["skills"] and "solidworks" in c["skills"], "解析：期望后面的技能词", str(c["skills"][:3]))
    ok(len(c["jobs"]) == 2, "解析：工作经历条数", str(len(c["jobs"])))
    ok(c["jobs"][0]["org"].startswith("江苏玖元"), "解析：公司名", c["jobs"][0]["org"])
    ok(len(c["schools"]) == 1, "解析：教育经历条数", str(len(c["schools"])))

    c2 = cr.parse_card(CARD_HIDDEN_ACTIVITY)
    ok(c2["activity"] == "隐藏", "解析：活跃度『隐藏/活跃状态』连写", c2["activity"])
    ok(c2["read_mark"] is False, "解析：没有『阅』", str(c2["read_mark"]))


def test_flags() -> None:
    c = cr.parse_card(CARD_HIDDEN_ACTIVITY)
    fl = cr.resume_flags(c)
    ok(any("至今" in x for x in fl), "硬伤：两段都写『至今』→ 标注", str(fl))
    ok(cr.resume_flags(cr.parse_card(CARD_MECH)) == [], "硬伤：正常履历不误报", "")


def test_score_and_rank() -> None:
    ind = cr.local_judge(CARD_ELEC_INDUSTRY, job_keywords=["输送线", "电气设计", "eplan"])
    ok(bool(ind["industry_hits"]), "打分：行业命中（新松/华章/物流科技）", str(ind["industry_hits"]))
    ok("eplan" in ind["skill_hits"] and "控制柜" in ind["skill_hits"], "打分：技能命中", str(ind["skill_hits"]))
    ok(ind["score"] > 50, "打分：行业+技能 → 高分", str(ind["score"]))
    ok(ind["decision"] == "keep", "判断：行业对口 → keep", ind["decision"])

    mech = cr.local_judge(CARD_MECH, job_keywords=["输送线"])
    ok(mech["score"] <= 40, "打分：**没有行业命中 → 分数压在 40 上限内**", str(mech["score"]))
    ok(mech["decision"] == "keep", "**本地不 drop 任何人**（只排序+配额，丢人是③的事）", mech["decision"])
    ok(mech["score"] < ind["score"], "打分：机械噪声 < 行业对口", f'{mech["score"]} vs {ind["score"]}')
    ok(mech["score"] <= 15, "打分：纯机械再降噪（−25）", str(mech["score"]))
    ok(any("降噪" in r for r in mech["reasons"]), "判断：降噪理由可解释", str(mech["reasons"][:2]))
    # 判据卡：不传卡 = 走电气兜底并**标红**；给了卡 = 整卡制（缺字段留空，不掉回电气词表）
    _dp = cr.profile_from_plan({"keywords": ["x"]})
    ok(_dp.used_default is True and "新松" in _dp.companies, "判据卡：缺卡 → 兜底 + used_default", "")
    _mp = cr.profile_from_plan({"judge": {"industry": ["叉车", "AGV"], "skills": ["solidworks"],
                                          "role": ["机械设计"], "not_role": ["电气"]}})
    ok(_mp.used_default is False and _mp.companies == [], "判据卡：整卡制（没给 companies 就留空）",
       str(_mp.companies))
    _m = cr.local_judge(CARD_MECH_JUDGE, profile=_mp)
    ok(_m["industry_hits"] == ["叉车", "AGV"] and _m["role_hits"] == ["机械设计"],
       "判据卡：机械岗的词能命中（叉车/AGV/机械设计）", str(_m["industry_hits"]) + str(_m["role_hits"]))
    ok(_m["score"] >= 60, "判据卡：机械岗对口的人分高（不再被电气口径压到 40）", str(_m["score"]))
    # 同一张卡、只换判据卡 → 分数立刻不同：这才证明"判据真的在起作用"（不是写死的）
    _elec_only = cr.JudgeProfile(industry=["输送线"], skills=["eplan"], role=["电气设计"],
                                 not_role=["机械"], source="test")
    _e = cr.local_judge(CARD_MECH_JUDGE, profile=_elec_only)
    ok(_e["score"] <= 40 and _e["industry_hits"] == [],
       "同一张卡换电气判据 → 行业命中 0、分数压到 40 上限", f'{_e["score"]}/{_e["industry_hits"]}')

    sales = cr.local_judge(CARD_SALES)
    ok(sales["decision"] == "keep", "判断：售前/销售 → 入池但降噪（不 drop）", sales["decision"])
    ok(any(("降噪" in r) or ("不对口" in r) for r in sales["reasons"]),
       "判断：非本行 → 降噪且理由可解释", str(sales["reasons"][:2]))


def test_quota() -> None:
    judged = [cr.local_judge(CARD_ELEC_INDUSTRY) for _ in range(3)]
    judged += [cr.local_judge(CARD_MECH) for _ in range(10)]
    plan = cr.page_plan(judged, details_per_page=5)
    st = plan["stats"]
    ok(len(judged) == 13 and st["n"] == 13, "配额：13 张卡都在", json.dumps(st))
    ok(st["open"] == 5, "配额：一页只开 5 个详情", str(st["open"]))
    ok(st["skip"] == 8, "配额：其余 8 个 skip（留卡不开页）", str(st["skip"]))
    ok(st["drop"] == 0, "配额：**本地不丢人**（drop 恒为 0，丢人在③）", str(st["drop"]))
    opened = [j for j in plan["items"] if j.get("action") == "open"]
    ok(len(opened) == 5, "配额：open 名单长度 = 配额", str(len(opened)))
    ok(all(j["industry_hits"] for j in opened[:3]), "排序：行业命中的人排在 open 最前面", "")
    ok(all(not j["industry_hits"] for j in opened[3:]), "排序：行业命中用完后才轮到没命中的", "")
    ok(st["open"] + st["skip"] + st["drop"] == st["n"], "统计自洽：open+skip+drop = n", json.dumps(st))


def test_death_order_and_streak() -> None:
    """🔴 死命令（2026-09-16）：不设人为额度 → "够格就开" + 硬顶 0=不限 + 连续不值得→换关键字。

    ⚠️ 旧断言"details_per_page=0 = 一个都不开"**已被本口径取代**（它把 0 当配额）；
       新的 0 = **不限**（`UNLIMITED_DETAILS`）。
    """
    # ① 够格判据：行业命中 或 本行职能命中
    role_only = cr.local_judge("张**\n30岁\n工作6年\n本科\n南京\n求职期望：\n自动化工程师\n")
    ind = cr.local_judge(CARD_ELEC_INDUSTRY)
    mech = cr.local_judge(CARD_MECH)
    ok(cr.is_worth_opening(ind) is True, "够格：行业命中 → 值得开", str(ind["industry_hits"]))
    ok(cr.is_worth_opening(role_only) is True,
       "够格：只有本行职能命中 → 也值得开", f'role={role_only["role_hits"]} ind={role_only["industry_hits"]}')
    ok(cr.is_worth_opening(mech) is False,
       "够格：既无行业、也不在本行 → 不值得开", f'role={mech["role_hits"]} ind={mech["industry_hits"]}')

    # ② 不限配额：只开够格的人（不够格的留卡不开页）
    judged = [cr.local_judge(CARD_ELEC_INDUSTRY) for _ in range(3)] + \
             [cr.local_judge(CARD_MECH) for _ in range(10)]
    p0 = cr.page_plan(judged, details_per_page=0)
    ok(p0["stats"]["open"] == 3, "死命令：0 = 不限 → 只开够格的 3 个", json.dumps(p0["stats"]))
    ok(p0["stats"]["skip"] == 10, "死命令：不够格的 10 个只留卡（不丢人）", str(p0["stats"]["skip"]))
    ok(p0["stats"]["open_rule"] == "worth-it", "死命令：口径标成 worth-it（不是配额）",
       p0["stats"]["open_rule"])
    ok(cr.DETAILS_PER_PAGE == cr.UNLIMITED_DETAILS == 0,
       "死命令：模块默认 DETAILS_PER_PAGE=0（不限）", str(cr.DETAILS_PER_PAGE))

    # ③ 硬顶 0 = 不限；显式设限仍然生效
    rich = {"n": 30, "industry": 3, "open": 5, "keep": 25, "drop": 5, "skip": 20, "avg_score": 50}
    ok(cr.should_stop(rich, 0, 0, 12) == (False, ""),
       "死命令：硬顶 0 = 不限（翻到第 12 页也不因硬顶停）", "")
    ok(cr.should_stop(rich, 0, 5, 5)[0] is True, "硬顶仍可显式设限（写 5 就按 5 停）", "")

    # ④ 连续"不值得" → 判定这词到头了（老板口径：换关键字）
    bad = mech
    good = ind
    ok(cr.tired_streak([good, bad, bad], need=2) == (True, 2),
       "换词：连续 2 个不值得 → 到头", "")
    ok(cr.tired_streak([bad, good, bad], need=2)[0] is False,
       "换词：中间插了一个够格的 → 连续被打断，不到头", "")
    ok(cr.tired_streak([good] * 30, need=10)[0] is False, "换词：整页都够格 → 不到头", "")
    ok(cr.tired_streak([bad] * 30, need=10) == (True, 10),
       "换词：整页都不值得 → 到第 10 个就判到头", "")


def test_stop() -> None:
    rich = {"n": 30, "industry": 3, "open": 5, "keep": 25, "drop": 5, "skip": 20, "avg_score": 50}
    blank = {"n": 30, "industry": 0, "open": 2, "keep": 28, "drop": 2, "skip": 26, "avg_score": 40}
    ok(cr.should_stop(rich, 0, 5, 1) == (False, ""), "停止：第1页有行业命中 → 继续", "")
    ok(cr.should_stop(blank, 1, 5, 3)[0] is False, "停止：只空 1 页 → 继续", "")
    s, why = cr.should_stop(blank, 2, 5, 3)
    ok(s is True and "行业" in why, "停止：连续 2 页行业=0 → 停", why)
    s2, why2 = cr.should_stop(rich, 0, 5, 5)
    ok(s2 is True and "硬顶" in why2, "停止：翻够硬顶页数 → 停", why2)
    none_open = {"n": 30, "industry": 1, "open": 0, "keep": 0, "drop": 30, "skip": 0, "avg_score": 20}
    ok(cr.should_stop(none_open, 0, 5, 2)[0] is True, "停止：整页没人值得开（且已翻≥2页）→ 停", "")


def test_stage_plan() -> None:
    spec = cr.stage_plan(["city_current=南京", "education=本科"], "电气设计 输送线", 1)
    ok(spec[0] == {"group_id": "keyword", "value": "电气设计 输送线"}, "拼装：关键字在前", str(spec[0]))
    ok(len(spec) == 3 and spec[1]["group_id"] == "city_current", "拼装：条件按 group_id=value 拆", str(spec))
    bad = cr.stage_plan(["南京", "=x", "y="], "kw", 1)
    ok(len(bad) == 1, "拼装：非法条件被丢掉（不猜）", str(bad))


def main() -> None:
    print("== collect_rules 单测 ==")
    test_parse()
    test_flags()
    test_score_and_rank()
    test_quota()
    test_death_order_and_streak()
    test_stop()
    test_stage_plan()
    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
