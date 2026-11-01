#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_rules.py — ②正式采集的**本地粗筛规则**（纯函数、0 token、可单测）

分工（2026-09-16 老板拍板的口径）：
  - **小猎**决定"这一轮怎么采"（关键字/条件/换词）；
  - **本模块**决定"这个人值不值得开详情页""这一轮是不是该停了"——**本地规则算，不调 LLM**；
  - 采集执行器（collect_exec.py）负责动手；本模块只管**判断**，不碰浏览器、不碰数据库。

⚠️ 设计要点（都是被真实数据逼出来的）：
  1. **两个判据分开**（2026-09-16 实测教训）：第 1 页 29 张卡里有 21 人挤在同一个分数档
     （"像电气、看不出行业对口"）→ 若只用一个分数决定"开不开详情"，会把 21 个人都开掉。
     所以：`industry_hits`（行业对口）决定**开不开详情**；`score`（成色）决定**留不留/排序**。
  2. **判据用内容，不用页码**：实测同一批人会在不同页码上重复出现（"智能排序"是动态的），
     "第几页"不是稳定坐标 → 停止规则只看**内容特征**（行业命中数）。
  3. **必须有配额**（2026-09-16 二改，实测逼出来的）：第一版"分数≥55 就开"实测开掉 20/29
     —— 因为"在南京 + 本科 + 有经验"白送 16 分，把**机械工程师**也顶到 74 分。
     一个 121 人的池子里大半是机械岗，靠阈值根本分不出来（分数全挤在 70~80）。
     → 改成 **`industry_hits` 优先 + 每页只开前 N 个（`details_per_page`）**：
       "开几个"是**老板的配额**，"开谁"是**本地的排序**；这才真做到"不用全采"。
  4. **宽进**（老板原话："我们不用过多的考虑打开详情次数的限制"）：配额定 5/页（不是 2），
     且**行业命中的人永远排在没命中的前面**。

出处：`工作文档/②正式采集·形态计划.md` §4；真实样本 `bestagent/data/usage/_probe_*.json`。
"""
from __future__ import annotations

import re

EDU_RANK = {"高中及以下": 1, "中专/中技": 2, "大专": 3, "本科": 4, "硕士": 5, "博士/博士后": 6, "博士": 6}
ACTIVITY_BADGES = ("今天活跃", "3天内活跃", "7天内活跃", "30天内活跃", "最近三个月活跃",
                   "最近半年活跃", "最近一年活跃", "在线")

# ── 词表已全部搬进 JudgeProfile（见下方 DEFAULT_* / profile_from_plan）──────────
# ⚠️ 2026-09-16：原先这里是**写死的电气岗词表**（INDUSTRY_WORDS / SKILL_WORDS / ELEC_WORDS…），
#    换第二个岗就歪。现在词表按岗给（小猎写在计划里），代码只留一份兜底默认。


# 阈值/判据（老板可改；先给一版可解释的）
# 🔴 2026-09-16 死命令（测试阶段不设人为额度）：
#    `DETAILS_PER_PAGE = 0` = **不设配额 → 够格就开**（见 `is_worth_opening`）。
#    老口径（填 >0 = 一页最多开 N 个）**保留**，给"只想先看几个"的场合用。
UNLIMITED_DETAILS = 0     # 0 = 不限（死命令默认）
DETAILS_PER_PAGE = UNLIMITED_DETAILS
# 老板口径（2026-09-16）："**连续出现候选人的质量不太满意了，就说明以后的候选人都不会太相关了，
#   那就更换关键字**" → 一位一位往下扫，连续遇到这么多个"不值得开详情"的人，就判定这个词到头了。
TIRED_STREAK = 10

# ── 判据卡（JudgeProfile）：**按岗配置**，不把任何一个岗的词写死在代码里 ──────────
# 病根（2026-09-16 第三次复发）：第一版把"电气设计·输送线"这一个岗的行业词/技能词/职能词
#   直接写成了模块常量 → 换 094907（机械工程师）就歪：`叉车/AGV/穿梭车/提升机` 不在词表里、
#   而且"纯机械 −25 / 无行业命中封顶 40"会让机械设计师全部沉底。
# 改法：**词表由小猎在计划里给**（它读 JD 本来就得想清楚这些），本模块只负责"按卡打分"。
# 不变量（**不许模型改**，它只能给词）：
#   ① 权重写死：行业 8/个(≤24)、技能 4/个(≤12)、本行职能 +10、学历/城市只做平手参考、无行业命中封顶 40
#   ② 不丢人：not_role 命中只降噪（降分/排后/不开详情），照样入库
#   ③ 缺卡不静默：没给 judge 就用兜底，并在 trace 里标明"用了兜底判据"
DEFAULT_ELEC_INDUSTRY = ("输送线", "输送机", "输送设备", "提升设备", "提升机", "托盘输送", "物流输送",
                         "分拣", "堆垛", "立库", "立体库", "仓储", "智能仓储", "物流装备", "物流设备",
                         "物流科技", "物流机器人", "物流自动化", "agv", "amr", "穿梭车", "皮带机")
DEFAULT_ELEC_COMPANIES = ("德马科技", "兰剑", "今天国际", "音飞储存", "新松", "极智嘉", "geek+",
                          "六维", "华章", "欧力德", "安鑫物流", "昆船", "北自所", "旷视")
DEFAULT_ELEC_SKILLS = ("eplan", "电控柜", "控制柜", "电气布线", "元件选型", "元器件选型", "部件选型",
                       "bom", "变频", "伺服", "电机控制", "电气原理图", "电气图纸", "接线")
DEFAULT_ELEC_ROLE = ("电气", "电控", "自动化", "plc", "上位机", "自控", "伺服", "变频")
DEFAULT_NOT_ROLE = ("销售", "市场", "采购", "财务", "人事", "招聘", "行政", "客服", "仓管员", "司机")
# 词的来源校验：只允许中英文数字与少量符号，防止把正则/超长串塞进来
_WORD_OK = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9+#./\- ]{1,20}$")


class JudgeProfile:
    """判据卡：**一个岗一份**。字段见模块头注释；缺项用兜底默认，`used_default` 记明。"""

    def __init__(self, industry=(), companies=(), skills=(), role=(), not_role=(),
                 prefer="industry", hard=(), notes="", used_default=False, source=""):
        def clean(xs):
            out = []
            for w in (xs or []):
                w = str(w).strip()
                if w and _WORD_OK.match(w) and w not in out:
                    out.append(w)
            return out
        self.industry = clean(industry)
        self.companies = clean(companies)
        self.skills = clean(skills)
        self.role = clean(role)
        self.not_role = clean(not_role)
        self.prefer = "skill" if str(prefer).strip().lower() == "skill" else "industry"
        self.hard = [str(x).strip() for x in (hard or []) if str(x).strip()]
        self.notes = str(notes or "").strip()
        self.used_default = bool(used_default)
        self.source = str(source or "")
        # ⚠️ 2026-09-16 修正（**整卡制**）：给了卡就用它给的，**缺哪个字段就留空**，
        #    绝不能"缺 industry 就掉回电气兜底词表"——实测踩到：机械岗的卡里混进了
        #    "德马科技/兰剑"（电气行业公司名），会把机械候选人误判成行业命中。
        #    只有**整张卡都没有**（used_default=True）时，才整份用兜底默认（并在 reasons 里红字标明）。
        if self.used_default:
            self.industry = list(DEFAULT_ELEC_INDUSTRY)
            self.companies = list(DEFAULT_ELEC_COMPANIES)
            self.skills = list(DEFAULT_ELEC_SKILLS)
            self.role = list(DEFAULT_ELEC_ROLE)
            if not self.not_role:
                self.not_role = list(DEFAULT_NOT_ROLE)

    def to_dict(self) -> dict:
        return {"industry": self.industry, "companies": self.companies, "skills": self.skills,
                "role": self.role, "not_role": self.not_role, "prefer": self.prefer,
                "hard": self.hard, "notes": self.notes, "used_default": self.used_default,
                "source": self.source}


def profile_from_plan(plan: dict, source: str = "") -> JudgeProfile:
    """从计划 JSON 的 `judge` 一节做判据卡。**缺卡/全空 → 兜底 + used_default=True**（绝不静默）。"""
    j = (plan or {}).get("judge") or {}
    if not isinstance(j, dict):
        j = {}
    keys = ("industry", "companies", "skills", "role", "not_role")
    got = {k: j.get(k) for k in keys}
    has_any = any(got.get(k) for k in keys)
    prof = JudgeProfile(industry=got["industry"], companies=got["companies"], skills=got["skills"],
                        role=got["role"], not_role=got["not_role"], prefer=j.get("prefer") or "industry",
                        hard=j.get("hard") or (plan or {}).get("conds") or [],
                        notes=j.get("notes") or "", used_default=not has_any, source=source)
    return prof
NEAR_CITY_PREFIXES = ("苏州", "无锡", "常州", "镇江", "扬州", "泰州", "南通", "盐城", "淮安", "上海", "杭州", "嘉兴", "湖州")


def _lines(text: str) -> list[str]:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


def activity_of(text: str) -> str:
    """取活跃度徽章。可能是『今天活跃』一行，也可能是『隐藏 / 活跃状态』两行。"""
    L = _lines(text)
    for i, x in enumerate(L):
        for b in ACTIVITY_BADGES:
            if x == b:
                return b
        if x == "隐藏" and i + 1 < len(L) and L[i + 1] == "活跃状态":
            return "隐藏"
    return ""


def parse_card(text: str) -> dict:
    """把一张列表卡片（extract 的 row["text"]）解析成结构化字段。

    卡片真实格式（实测，字段顺序固定；活跃度与『阅』标记可有可无）：
        在线 / 阅 / 王** / 46岁 / 工作23年 / 本科 / 南京
        求职期望： / 南京机械工程师 / 夹具 / cad / …（技能词若干）
        <公司> · <职位> / <起-止>(时长)
        <学校> · <专业> · <学历> · 统招|非统招 / 起-止
        立即沟通
    ⚠️ 解析不出来**一律如实留空**（不猜）——分数会因此偏低，宁可漏开详情也不误判。
    """
    t = text or ""
    L = _lines(t)
    out: dict = {"activity": activity_of(t), "name": "", "age": None, "years": None,
                 "education": "", "edu_tongzhao": "", "city": "", "expect_city": "",
                 "expect_position": "", "skills": [], "jobs": [], "schools": [],
                 "read_mark": "阅" in L}

    m = re.search(r"([\u4e00-\u9fa5]{1,4})\*\*", t) or re.search(r"^([\u4e00-\u9fa5]{2,4})$", t, re.M)
    if m:
        out["name"] = m.group(1) + "**" if m.group(0).endswith("**") else m.group(1)
    m = re.search(r"(\d{1,2})岁", t)
    if m:
        out["age"] = int(m.group(1))
    m = re.search(r"工作(\d{1,2})年", t)
    if m:
        out["years"] = int(m.group(1))
    m = re.search(r"工作(\d{1,2})年以上", t)
    if m and out["years"] is None:
        out["years"] = int(m.group(1))
    # 学历：优先取教育经历里的 ·本科·（求职意向区不写学历），否则取年龄后面那位
    edus = [e for e in EDU_RANK if e in t]
    if edus:
        out["education"] = max(edus, key=lambda e: EDU_RANK[e])
    if "非统招" in t:
        out["edu_tongzhao"] = "非统招"
    elif "统招" in t:
        out["edu_tongzhao"] = "统招"

    # 城市 / 求职期望 区
    for i, x in enumerate(L):
        if x == "求职期望：" or x.startswith("求职期望"):
            # 期望城市+职位 = 下一行（如 "南京机械工程师"/"沈阳电气工程师"）
            if i + 1 < len(L):
                nx = L[i + 1]
                for c in NEAR_CITY_PREFIXES + ("南京", "北京", "深圳", "广州", "成都", "西安", "青岛", "武汉", "重庆", "天津"):
                    if nx.startswith(c):
                        out["expect_city"] = c
                        out["expect_position"] = nx[len(c):]
                        break
                else:
                    out["expect_position"] = nx
            # 期望后面到第一个空行/公司行之前 = 技能词
            j = i + 2
            while j < len(L) and "·" not in L[j] and "立即沟通" not in L[j]:
                out["skills"].append(L[j])
                j += 1
            break
    # 目前城市：年龄/学历那几行最后出现的城市（含 "-区"）
    m = re.search(r"^([\u4e00-\u9fa5]{2,3}(?:-[\u4e00-\u9fa5]{2,4})?)$", t, re.M)
    for x in L[:12]:
        if x in ("本科", "硕士", "大专", "博士/博士后", "中专/中技", "高中及以下"):
            continue
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}(-[\u4e00-\u9fa5]{2,4})?", x) and x not in ("求职期望",) \
                and not x.endswith("岁") and "工作" not in x and x != out["name"]:
            if x not in ACTIVITY_BADGES and x != "隐藏" and x != "活跃状态":
                out["city"] = x
                break
    if m and not out["city"]:
        out["city"] = m.group(1)

    # 工作/教育条目：<机构> · <职位/专业> [· 学历 · 统招] 换行 <起-止>(时长)
    for blk in re.split(r"\n\s*\n", t):
        bl = _lines(blk)
        if not bl or "·" not in bl[0] or "立即沟通" in bl[-1]:
            continue
        parts = [p.strip() for p in bl[0].split("·")]
        span = bl[1] if len(bl) > 1 and re.search(r"\d{4}", bl[1]) else ""
        item = {"org": parts[0], "role": parts[1] if len(parts) > 1 else "",
                "extra": parts[2:], "span": span}
        if any(e in ("本科", "硕士", "大专", "博士/博士后", "中专/中技", "高中及以下") for e in parts[2:]) \
                or any(k in parts[0] for k in ("大学", "学院", "学校")):
            out["schools"].append(item)
        else:
            out["jobs"].append(item)
    return out


def _span_years(span: str) -> tuple[int | None, int | None]:
    """'2024.10-至今(8个月)' → (2024, None)；'2025.01-2025.12(11个月)' → (2025, 2025)。"""
    m = re.search(r"(\d{4})\.(\d{1,2})\s*[-–~]\s*(\d{4})\.(\d{1,2})", span or "")
    if m:
        return int(m.group(1)), int(m.group(3))
    m = re.search(r"(\d{4})\.(\d{1,2})\s*[-–~]\s*至今", span or "")
    if m:
        return int(m.group(1)), None
    return None, None


def resume_flags(card: dict) -> list[str]:
    """简历本身的硬伤（如实标注，**不参与"开不开详情"的判断**，只让老板看得见）。"""
    flags: list[str] = []
    arcs = [_span_years(j.get("span", "")) for j in (card.get("jobs") or [])]
    for i, (s1, e1) in enumerate(arcs):
        if e1 is not None:
            continue
        for j, (s2, e2) in enumerate(arcs):
            if i == j or s2 is None:
                continue
            if e2 is None:                    # 两段都"至今"
                flags.append("两段经历都写『至今』")
                break
            if s2 < s1:
                flags.append("经历时间重叠")
                break
        if flags:
            break
    return flags


def default_profile() -> JudgeProfile:
    """兜底判据（= 172253 电气设计那套词表）。**用它就意味着"本轮没有按岗判据"**，会标红。"""
    return JudgeProfile(used_default=True, source="fallback")


def local_judge(text: str, job_keywords: list[str] | None = None, base_city: str = "南京",
                profile: "JudgeProfile | None" = None) -> dict:
    """对一张卡片做本地判断（**单人**）。返回：

    {
      "card": {...},            # 结构化字段（写库用）
      "industry_hits": [...],   # 行业对口命中（**决定排序优先级**）
      "skill_hits": [...],      # 技能命中
      "elec": True/False,       # 是不是电气这条线（JD 是电气设计；纯机械＝噪声）
      "score": 0-100,           # 成色分（**只由"像不像这岗的人"决定**）
      "decision": "keep|drop",  # 本地初判；**开不开详情由 page_plan 按配额决定**
      "reasons": [...]          # 逐条可解释
    }

    ⚠️ 2026-09-16 二改（实测教训）：第一版把"在南京 + 本科 + 有经验"也算加分，
    结果 121 人的池子里**机械工程师**也被顶到 74 分、20/29 全开。
    → 现在分数**只看**：行业命中 / 技能命中 / 电气职能 / 本科及以上；城市与活跃度只做"平手时"的参考，
    且**没有行业命中的人分数上限 40**（保证行业命中的人永远排在前面）。
    """
    card = parse_card(text)
    prof = profile or default_profile()
    kw = [str(k).strip().lower() for k in (job_keywords or []) if str(k).strip()]
    blob = (text or "").lower()
    reasons: list[str] = []

    ind_words = tuple(prof.companies) + tuple(prof.industry)
    industry = [w for w in ind_words if w.lower() in blob]
    industry = list(dict.fromkeys(industry))
    skills = [w for w in prof.skills if w.lower() in blob]
    role_hits = [w for w in prof.role if w.lower() in blob]
    not_role = [w for w in prof.not_role if w.lower() in blob]
    elec = bool(role_hits)
    kw_hits = [k for k in kw if k in blob]

    # 打分（**权重写死，模型只能给词**）；`prefer` 只决定平手时的排序，不改分
    no_role = (not role_hits)
    w_ind, w_skill = (8, 4) if prof.prefer != "skill" else (6, 6)
    score = 30
    score += min(24, w_ind * len(industry))
    score += min(12, w_skill * len(skills))
    score += 10 if role_hits else 0
    score += 4 if card.get("education") in ("本科", "硕士", "博士/博士后") else 0
    if not industry:
        score = min(score, 40)          # 没行业命中 → 封顶，绝不越过行业命中的人（排序原则，跨岗不变）
    if not industry and (no_role or not_role):
        # **非本行 + 无行业命中 → 降噪（−25；只降分，不丢人）**。对任何岗都成立：
        #   判据来自判据卡的 role / not_role —— 机械岗里"纯电气"降噪，电气岗里"纯机械"降噪。
        score -= 25
    score = max(0, min(100, score))

    decision = "keep"                 # ⚠️ 本地不 drop 任何人（丢人是③匹配层的事）
    if no_role and not industry:
        reasons.append("既没行业命中、也不在本行职能上 → 降噪，不开详情")
    elif not industry:
        reasons.append("没有行业命中 → 分数封顶、排在有行业命中的人后面")
    else:
        reasons.append("行业命中 → 优先考虑开详情")
    reasons.insert(0, "入池（开不开详情由每页配额与排名决定）")
    if prof.used_default:
        reasons.append("⚠️ 用的是**兜底判据**（计划里没给 judge 词表）——排序可能不贴本岗")
    if industry:
        reasons.append("行业命中：" + "/".join(industry[:4]))
    if role_hits:
        reasons.append("本行职能命中：" + "/".join(role_hits[:3]))
    if not_role:
        reasons.append("不是本行的职能词：" + "/".join(not_role[:3]))
    if kw_hits:
        reasons.append("搜索词命中：" + "/".join(kw_hits[:3]))
    if card.get("read_mark"):
        reasons.append("我/别人已看过（阅）")
    if not card.get("activity"):
        reasons.append("无活跃度徽章（不扣分，也不代表不活跃）")

    return {"card": card, "industry_hits": industry, "skill_hits": skills,
            "role_hits": role_hits, "not_role_hits": not_role, "elec": elec,
            "score": score, "decision": decision, "reasons": reasons,
            "resume_flags": resume_flags(card), "judge_default": prof.used_default}


def is_worth_opening(j: dict) -> bool:
    """**这个人值不值得开详情页**（本地判据，可解释）。

    老板口径（2026-09-16）："看第一个值不值得打开，值得就打开，然后继续第二个、依次类推"，
    并且**不准再设人为额度** → 判据必须是"够不够格"，**不是"排第几"**。

    够格 = ① **行业命中**（最强信号）或 ② **本行职能命中**（title 就是这岗的人）。
    两个都没有 = "既不对口、也不在本行" → 不看详情。
    ⚠️ 不够格的人**照样入库**（本地只降噪、不丢人；丢人是③匹配层的事）。
    """
    return bool(j.get("industry_hits")) or bool(j.get("role_hits"))


def tired_streak(judged_in_page_order: list[dict], need: int = TIRED_STREAK) -> tuple[bool, int]:
    """老板口径："**连续出现候选人的质量不太满意了，就说明以后的候选人都不太相关了 → 更换关键字**"。

    按**页面原始顺序**（老板眼里"往下看"的顺序，**不是**按分数排序后的顺序）一位一位扫，
    一旦出现连续 `need` 个"不值得开详情"的人 → 判定这个词到头了。
    返回 (是否到头, 触发/收尾时的连续数)。
    """
    cur = 0
    for j in judged_in_page_order:
        if is_worth_opening(j):
            cur = 0
        else:
            cur += 1
            if cur >= max(1, int(need)):
                return True, cur
    return False, cur


def page_plan(judged: list[dict], details_per_page: int = DETAILS_PER_PAGE) -> dict:
    """把一页的判断结果变成**可执行的计划**：留谁、开谁的详情、停不停。

    排序规则（可解释）：① 行业命中多的在前 ② 分数高的在前 ③ 职能/技能命中多的在前

    开详情的判据（🔴 2026-09-16 死命令改口径）：
      · `details_per_page <= 0`（**默认**）→ **不设配额：够格就开**（`is_worth_opening`
        = 行业命中 或 本行职能命中）——这就是老板要的"依次判断、值得就打开"；
      · `details_per_page > 0` → **老口径保留**：按排名取前 N 个（给"只想先看几个"用）。
    """
    items = []
    for j in judged:
        keep = j["decision"] != "drop"
        ind = len(j["industry_hits"])
        items.append({**j, "rank_key": (ind, j["score"], len(j.get("role_hits") or []),
                                        len(j["skill_hits"])) if keep else (-1, -1, -1, -1)})
    ordered = sorted(items, key=lambda x: (-x["rank_key"][0], -x["rank_key"][1],
                                           -x["rank_key"][2], -x["rank_key"][3]))
    limited = int(details_per_page) > 0
    opened = 0
    for j in ordered:
        if j["decision"] == "drop":
            j["action"] = "drop"
            continue
        take = (opened < int(details_per_page)) if limited else is_worth_opening(j)
        if take:
            j["action"] = "open"
            opened += 1
        else:
            j["action"] = "skip"
    n = len(judged)
    # ⚠️ 统计必须和"动作"读**同一份**（`ordered`）——2026-09-16 实测踩到：
    #    动作写在 `{**j}` 副本上，却去统计原列表 → open/skip 全是 0，停止规则跟着失效。
    stats = {
        "n": n,
        "industry": sum(1 for j in ordered if j["industry_hits"]),
        "worthy": sum(1 for j in ordered if is_worth_opening(j)),
        "keep": sum(1 for j in ordered if j["decision"] != "drop"),
        "drop": sum(1 for j in ordered if j["decision"] == "drop"),
        "open": sum(1 for j in ordered if j.get("action") == "open"),
        "skip": sum(1 for j in ordered if j.get("action") == "skip"),
        "avg_score": round(sum(j["score"] for j in ordered) / n, 1) if n else 0,
        "details_per_page": int(details_per_page),
        "open_rule": ("quota-top-n" if limited else "worth-it"),
    }
    return {"items": ordered, "stats": stats}


def page_stats(judged: list[dict]) -> dict:
    """只要统计（兼容旧调用）；要"开谁"用 `page_plan`。"""
    return page_plan(judged)["stats"]


def should_stop(page: dict, consecutive_blank: int, max_pages: int = 5,
                pages_done: int = 0) -> tuple[bool, str]:
    """**该不该停这一轮**（返回 (是否停, 原因)）。

    判据（2026-09-16 与老板对齐；用内容特征，**不用页码**）：
      1. 硬顶：翻够 max_pages 页 → 停（🔴 **死命令后默认 0 = 不限**；它只是"防失控"，不是额度）
      2. 内容：**连续 2 页行业命中 = 0** → 停（"后面的人不值得开详情了"）
      3. 全页无人可开（open=0）且已翻 ≥2 页 → 停（这词到头了）

    ⚠️ "翻不动 / 翻页没生效（这一页没有新人）"是**正确性保护**（防死循环），不在这里，
       由 `collect_exec.run_auto` 判——它不属于"人为额度"，死命令不拆它。
    """
    if int(max_pages or 0) > 0 and pages_done >= int(max_pages):
        return True, f"翻够硬顶 {max_pages} 页"
    if consecutive_blank >= 2:
        return True, "连续 2 页行业命中为 0（这词往后没对口的人了）"
    if pages_done >= 2 and page.get("n", 0) > 0 and page.get("open", 0) == 0:
        return True, "这一页没有值得开详情的人"
    return False, ""


def stage_plan(base_conds: list[str], keyword: str, page: int) -> list[dict]:
    """给执行器用的"设条件"规格（纯拼装，不碰浏览器）：关键字 + 条件。"""
    spec = [{"group_id": "keyword", "value": keyword}]
    for c in base_conds or []:
        gid, sep, val = str(c).partition("=")
        if sep and gid.strip() and val.strip():
            spec.append({"group_id": gid.strip(), "value": val.strip()})
    return spec
