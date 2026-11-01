#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reply_run.py — ⑤查看回复执行器（手）：读职聊页 → 谁回了/回了什么 → 落台账 → 重出报告

分工（承接项目铁律「**脑 = 小猎/老板，手 = 脚本**」）：
  · 脑（小猎/老板）= 定**什么算"真回复"**（本文件里的 `DEFAULT_PHRASE` / `SYSTEM_NOISE` 就是它的落地）；
  · 本脚本（手）    = 开职聊页 → 读会话列表 → 把"我们打过招呼的人"和"列表里的行"**对上号** →
                      记一条 `event_type='回复'`（只增不改）→ **重出打招呼报告**（本地渲染 0 token）。

🔴 **只读纪律（全项目只有这里在"读对方"，绝不许手滑）**：
  · 只提供这些远程动作：`list_tabs / new_tab / navigate / snapshot / page_text / close_tab`；
  · **唯一允许的"点击"是会话行**（`click_row`：只点列表里的姓名 span，且点之前**按几何再验一次**），
    因为 `--deep` 要读会话详情核对身份；**永不 type、永不 click_by_text**（能"把话发出去"的只有这两个）。
  · 采集/读取时**绝不点打招呼、绝不发消息**；读到什么记什么，**没读到就说没读到**。

数据源（2026-09-20 实测）：
  · 职聊页 = `https://h.liepin.com/im/showmsgnewpage`；**列表异步渲染**，navigate 后要等 4~8 秒并重拍；
  · 列表每行 = 姓名 + 职位 + 时间 + `[未读]/[已读]`（**候选人有没有点开我们的消息**）+ 未读数 + 最后一句；
  · 点开会话能读到：公司/职位/求职期望/**完整消息流**（我们的话带"已读/未读"回执，对方的话没有回执）；
  · `[已读]但没回` = 看过没兴趣/在犹豫 → 正是"换个说法再联系"的目标（老板：重发按天起步）。

⚠️ 本场（2026-09-20）老板对四个口径说「**先讨论**」→ 所以面板默认 **只读不记账**
   （`DEFAULT_RECORD = False`）。他点头后**改这一行**即可（或在面板按钮后面加 `--yes`）。

用法（cwd = bestagent）：
  python reply_run.py --job-code J-...                    # 只读：打印"谁回了/回了什么"（不写库、不出报告）
  python reply_run.py --job-code J-... --yes               # 记账：落台账 + 重出打招呼报告
  python reply_run.py --job-code J-... --yes --deep        # 需要时点开会话读全文（核对身份 + 拿对方原话）
  python reply_run.py --job-code J-... --tab-id 123 --keep-tab   # 复用已开的职聊页（调试用，别关它）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import WORKSPACE  # noqa: E402

import greeting_report as gr  # noqa: E402
import job_db  # noqa: E402

BRIDGE = "http://127.0.0.1:8080"
CHAT = WORKSPACE / "data" / "chat"
ACCOUNT = "杨猛"
IM_URL = "https://h.liepin.com/im/showmsgnewpage"

# 面板点一下就跑的默认行为：False = 只读（不写库）。老板拍板后改这一行。
DEFAULT_RECORD = False

# 我们发出去的"打招呼默认短语"（平台固定话术，实测原文）
DEFAULT_PHRASE = "你好~我这里有个职位很适合你，待遇优厚，了解一下吗？期待回复！"

# 系统/我们侧文本（**不算对方回复**）：命中就说明"列表最后一句不是他说的"
SYSTEM_NOISE = (
    "您可以修改打招呼语", "去修改＞＞", "我想要一份你的简历", "用户简历已设置隐私状态",
    "索要简历", "索要手机", "索要微信", "超级聊聊", "24小时内有回复",
    "30天前的消息已为您弱化提醒", "沟通职位：",
)

# 列表容器几何（实测：会话行姓名 span 固定在 left≈156，职位 span 在 left≈200，列表列宽 <360）
NAME_LEFT, NAME_W, NAME_H = 156.0, 60.0, 21.0
POS_LEFT, POS_W = 200.0, 200.0
LIST_MAX_LEFT = 360.0
BADGE_MAX_LEFT = 150.0

TAB_LABELS = {"全部", "新招呼", "我发起的", "我回复的", "有简历", "全部职位", "未读",
              "消息", "互动", "设置"}
TIME_RE = re.compile(r"^(\d{1,2}:\d{2}|\d{1,2}月\d{1,2}日|昨天|\d+天前|\d{4}-\d{2}-\d{2})$")
FLOW_TS_RE = re.compile(r"^(\d{1,2}:\d{2}|\d{1,2}月\d{1,2}日( \d{1,2}:\d{2})?|"
                        r"昨天( \d{1,2}:\d{2})?|\d{4}-\d{2}-\d{2}( \d{1,2}:\d{2})?)$")
RECEIPT = ("已读", "未读")


# ── 桥客户端（**只读**；写动作只有会话行点击这一个）──────────────────────────

def _post(path: str, obj: dict) -> dict:
    req = urllib.request.Request(BRIDGE + path, data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))


def _get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(BRIDGE + path, timeout=15).read().decode("utf-8"))


def bridge_up() -> bool:
    try:
        return bool(_get("/api/health").get("ok"))
    except Exception:  # noqa: BLE001
        return False


# ⚠️ 白名单：能"发消息"的动作（type / click_by_text）**一律不在里面**——本脚本永不提供它们。
READ_ACTIONS = ("list_tabs", "new_tab", "navigate", "snapshot", "page_text", "close_tab", "click")


def act(action: str, params: dict | None = None, *, timeout: int = 60, source: str = "reply-run") -> dict:
    """投一个桥动作并等结果。**非白名单动作直接拒绝**（安全绳）。"""
    if action not in READ_ACTIONS:
        raise RuntimeError(f"reply_run 是只读脚本：不许执行 {action}")
    r = _post("/api/task", {"action": action, "params": params or {}, "source": source})
    tid = ((r.get("task") or r) or {}).get("id")
    if not tid:
        raise RuntimeError(f"投任务失败：{json.dumps(r, ensure_ascii=False)[:200]}")
    last: dict = {}
    for _ in range(timeout):
        time.sleep(1)
        last = (_get("/api/task/" + str(tid)).get("task") or {})
        if last.get("status") in ("done", "failed", "error"):
            break
    if last.get("status") != "done":
        raise RuntimeError(f"{action} 失败：{last.get('error')}")
    return last.get("result") or {}


def find_im_tab() -> int:
    for t in (act("list_tabs").get("tabs") or []):
        if "showmsgnewpage" in str(t.get("url") or ""):
            return int(t.get("tab_id") or 0)
    return 0


# ── 解析：职聊页会话列表（**看元素列表**，不看 body_preview）──────────────────

def _r(e: dict) -> dict:
    return e.get("rect") or {}


def _norm(s: str) -> str:
    """归一化：去空白、去"[]"标记——用来比较"这句话是不是我们发的"。"""
    s = re.sub(r"\s+", "", str(s or ""))
    return s


def is_name_element(e: dict) -> bool:
    """会话行的姓名 span（几何特征：left≈156 / 宽≤60 / 高≈21）。"""
    nm = (e.get("name") or "").strip()
    if not nm or (e.get("role") or "") not in ("span", "a", "div", "p"):
        return False
    if nm in TAB_LABELS or nm.startswith("[") or nm.endswith("＞＞"):
        return False
    if TIME_RE.match(nm) or FLOW_TS_RE.match(nm) or nm.isdigit():
        return False
    r = _r(e)
    return (abs(r.get("left", 0) - NAME_LEFT) <= 6 and r.get("width", 0) <= NAME_W
            and 14 <= r.get("height", 0) <= 30 and r.get("top", 0) > 100)


def parse_rows(els: list[dict]) -> list[dict]:
    """从**元素列表**解析会话行（元素列表是"页面上有没有"的唯一依据）。

    每行：{name, position, read('未读'/'已读'/''), unread(未读数 str), preview, index, top}
    分组规则：姓名 span 的 top 到下一个姓名 span 的 top 之间，全算这一行的部件。
    """
    names = sorted([e for e in els if is_name_element(e)],
                   key=lambda e: (_r(e).get("top", 0), _r(e).get("left", 0)))
    rows: list[dict] = []
    for i, nm_e in enumerate(names):
        top = _r(nm_e).get("top", 0)
        nxt = _r(names[i + 1]).get("top", 0) if i + 1 < len(names) else 10 ** 9
        seg = [e for e in els
               if top - 1 <= _r(e).get("top", 0) < nxt - 0.5 and _r(e).get("left", 0) < LIST_MAX_LEFT]
        seg_sorted = sorted(seg, key=lambda e: (_r(e).get("top", 0), _r(e).get("left", 0)))
        pos = ""
        for e in seg_sorted:
            r = _r(e)
            if POS_LEFT - 8 <= r.get("left", 0) <= POS_LEFT + 8 and POS_W * 0.4 <= r.get("width", 0) <= POS_W:
                pos = (e.get("name") or "").strip()
                break
        read, unread, preview = "", "", ""
        preview_top = -1.0
        for e in seg_sorted:
            nm = (e.get("name") or "").strip()
            r = _r(e)
            if nm in ("[已读]", "[未读]") and not read:
                read = nm.strip("[]")
            if nm.isdigit() and r.get("left", 0) <= BADGE_MAX_LEFT and not unread:
                unread = nm
            # 预览 = 这一行里**除了姓名/职位/标记/徽标之外**最靠下的那段文字
            # ⚠️ 2026-09-20 单测抓到：不能按"宽度≥150"挑预览——短消息（如"什么职位"，实测宽 48）
            #    会被漏掉；按行内位置挑才对。
            if not nm or nm == pos or nm == (nm_e.get("name") or "").strip() or nm in ("[已读]", "[未读]"):
                continue
            if nm.isdigit() and r.get("left", 0) <= BADGE_MAX_LEFT:
                continue
            if r.get("top", 0) >= preview_top:
                preview_top = r.get("top", 0)
                preview = nm
        rows.append({"name": (nm_e.get("name") or "").strip(), "position": pos,
                     "read": read, "unread": unread, "preview": preview,
                     "index": nm_e.get("index"), "top": top, "time": ""})
    return rows


def parse_rows_from_text(lines: list[str]) -> list[dict]:
    """兜底/取时间用：从整页文本里解析（形状 = 姓名 / 职位 / 时间 / 空行 / 预览）。"""
    rows: list[dict] = []
    for i, ln in enumerate(lines):
        t = ln.strip()
        if not TIME_RE.match(t) or i < 2:
            continue
        # ⚠️ 2026-09-20 单测抓到真 bug：**姓名在时间上面、职位在中间**（姓名/职位/时间），
        #    原先写成 lines[i-1]=姓名、lines[i-2]=职位 → 两个字段整个换位（元素解析正常时看不出来）。
        nm, pos = lines[i - 2].strip(), lines[i - 1].strip()
        if not nm or not pos or len(nm) > 14 or len(pos) > 60:
            continue
        if TIME_RE.match(nm) or nm.startswith("[") or nm in TAB_LABELS:
            continue
        if pos.startswith("[") or TIME_RE.match(pos):
            continue
        preview = ""
        for k in range(i + 1, min(i + 6, len(lines))):
            if lines[k].strip():
                preview = lines[k].strip()
                break
        rows.append({"name": nm, "position": pos, "time": t, "preview": preview, "raw_line": i})
    return rows


def attach_times(rows: list[dict], lines: list[str]) -> None:
    """把整页文本里的**时间**贴回元素行（时间不是可点元素 → 元素列表里没有）。"""
    cursor = 0
    for r in rows:
        for k in range(cursor, max(0, len(lines) - 2)):
            if (lines[k].strip() == r["name"] and lines[k + 1].strip() == r["position"]
                    and TIME_RE.match(lines[k + 2].strip())):
                r["time"] = lines[k + 2].strip()
                r["line"] = k
                cursor = k + 3
                break


# ── 判定：这一行的"最后一句"是谁说的 ────────────────────────────────────────

def our_texts_for(cand: dict, report_item: dict | None = None) -> list[str]:
    """"这句话是我们发的"的比对语料：默认短语 + 该候选人的岗位介绍（报告/台账里的原文）。"""
    out = [DEFAULT_PHRASE]
    detail = cand.get("detail") or {}
    for key in ("intro_msg_sent", "intro_msg"):
        if detail.get(key):
            out.append(str(detail[key]))
    if report_item:
        if report_item.get("intro_msg"):
            out.append(str(report_item["intro_msg"]))
        if report_item.get("msg1"):
            out.append(str(report_item["msg1"]))
    return [x for x in out if x]


def judge_preview(preview: str, ours: list[str]) -> tuple[str, str]:
    """判这一行的最后一句：('reply', 原文) / ('ours', '') / ('noise', 命中词) / ('empty', '')。

    纪律：**宁可说"看不出"，也不把系统提示当成他的回复**。
    """
    p = str(preview or "").strip()
    if not p:
        return "empty", ""
    pn = _norm(p)
    for noise in SYSTEM_NOISE:
        if _norm(noise) and _norm(noise) in pn:
            return "noise", noise
    for o in ours:
        on = _norm(o)
        if not on:
            continue
        if pn.startswith(on[:10]) or (len(on) >= 12 and on[:12] in pn):
            return "ours", o[:20]
    # 我们发的岗位介绍里那句"邀请语"（即使预览被截断/换行也能认出来）
    if "跟这个岗位挺对口" in pn and "方便聊聊吗" in pn:
        return "ours", "岗位介绍邀请语"
    return "reply", p


# ── 对号：列表里的行 ↔ 我们库里的候选人 ─────────────────────────────────────

def surname(name: str) -> str:
    return re.sub(r"[\s*＊]", "", str(name or ""))[:1]


def match_rows(rows: list[dict], cands: list[dict]) -> dict:
    """把"打过招呼的人"和"列表里的行"对上号。

    判据（从严）：**姓氏必须一致** + 职位一致(5)/包含(3)，低于门槛不认；两人同分 = **不上号**（如实报）。
    返回 {matches:[{cand,row,score}], unmatched_rows, unmatched_cands, ambiguous}
    """
    pairs: list[tuple[int, dict, dict]] = []
    for c in cands:
        cs = surname(c.get("display_name") or "")
        cp = _norm(c.get("display_position") or "")
        if not cs:
            continue
        for r in rows:
            if surname(r["name"]) != cs:
                continue
            score = 10
            rp = _norm(r.get("position") or "")
            if cp and rp:
                if cp == rp:
                    score += 5
                elif cp in rp or rp in cp:
                    score += 3
            pairs.append((score, c, r))
    pairs.sort(key=lambda x: -x[0])
    # ⚠️ 单测抓到（2026-09-20）：**不能边分配边判存疑**——先被配掉的人会把同分的对手"藏起来"，
    #    导致"两个同姓同职位的人"只报一个存疑。改成先算"谁的最高分是谁"，再判这一对是不是
    #    **双方各自唯一且最高**（干净）；否则一律进"存疑"，不记账。
    best_c: dict = {}
    best_r: dict = {}
    for s, c, r in pairs:
        best_c[c["id"]] = max(best_c.get(c["id"], -1), s)
        best_r[id(r)] = max(best_r.get(id(r), -1), s)
    clean, murky = [], []
    for s, c, r in pairs:
        uniq_c = sum(1 for s2, c2, _r2 in pairs if c2 is c and s2 == s) == 1
        uniq_r = sum(1 for s2, _c2, r2 in pairs if r2 is r and s2 == s) == 1
        if s >= 10 and s == best_c[c["id"]] and s == best_r[id(r)] and uniq_c and uniq_r:
            clean.append((s, c, r))
        else:
            murky.append((s, c, r))
    used_c, used_r, matches, ambiguous = set(), set(), [], []
    for s, c, r in clean:
        if c["id"] in used_c or id(r) in used_r:
            continue
        used_c.add(c["id"])
        used_r.add(id(r))
        matches.append({"cand": c, "row": r, "score": s, "ambiguous": False})
    clean_c, clean_r = set(used_c), set(used_r)
    for s, c, r in murky:
        # 已经被"干净地上号"的人/行，交叉出来的低分对（如同姓两人的互相漏配）不再当"存疑"报出来；
        # 其余**每一条都要报**（不许因为"这一行已经报过一次"就把第二个同姓的人吞掉——单测抓到）。
        if c["id"] in clean_c or id(r) in clean_r:
            continue
        used_c.add(c["id"])
        used_r.add(id(r))
        ambiguous.append({"cand": c, "row": r, "score": s, "ambiguous": True})
    return {"matches": matches, "ambiguous": ambiguous,
            "unmatched_cands": [c for c in cands if c["id"] not in used_c],
            "unmatched_rows": [r for r in rows if id(r) not in used_r]}


# ── --deep：点开会话，读公司/职位/消息流（核对身份 + 拿对方原话）────────────

def click_row(tab: int, row: dict) -> bool:
    """**唯一允许的点击**：点会话行姓名 span。点之前按几何再验一次（防编号漂移点到别处）。"""
    res = act("snapshot", {"tab_id": tab, "preview_chars": 500})
    for e in (res.get("elements") or []):
        if (e.get("index") == row.get("index") and (e.get("name") or "").strip() == row["name"]
                and is_name_element(e)):
            act("click", {"tab_id": tab, "index": e.get("index")})
            return True
    # 编号漂了 → 按几何重新找一次（同名同职位的行）
    for e in (res.get("elements") or []):
        if is_name_element(e) and (e.get("name") or "").strip() == row["name"]:
            r = _r(e)
            if abs(r.get("top", 0) - row.get("top", 0)) < 40:
                act("click", {"tab_id": tab, "index": e.get("index")})
                return True
    return False


def find_detail_start(lines: list[str], list_end: int, name: str) -> int:
    """找"会话详情区"的起点（`--deep` 的关键一步）。

    ⚠️ 2026-09-20 单测抓到真 bug：会话行的**时间**（"9月18日"）和消息流的时间戳共用一套写法，
       所以不能"从点开的那一行往下找第一个时间戳"——那会把**列表后面的会话行**当成消息流。
       正确锚点：**列表结束之后**、点开的那位候选人名字那一行（详情区的标题），兜底用"简历预览"。
    """
    for i in range(max(0, list_end), len(lines)):
        if lines[i].strip() == name:
            return i
    for i in range(max(0, list_end), len(lines)):
        if lines[i].strip() == "简历预览":
            return i
    return max(0, list_end)


def parse_flow(lines: list[str], start: int) -> dict:
    """解析会话详情：公司/职位/期望 + 消息流（我们的话带"已读/未读"回执，对方的话没有）。

    返回 {company, position, expect, messages:[{at, from, text}], chips}
    """
    seg = lines[start:]
    out: dict = {"company": "", "position": "", "expect": [], "messages": [], "chips": []}
    tss = [i for i, ln in enumerate(seg) if FLOW_TS_RE.match(ln.strip())]
    if not tss:
        return out
    head = seg[:tss[0]]
    for i, ln in enumerate(head):
        if ln.strip() == "简历预览":
            rest = [x.strip() for x in head[i + 1:] if x.strip()]
            if rest:
                out["company"] = rest[0]
            if len(rest) > 1:
                out["position"] = rest[2] if len(rest) > 2 and rest[1] == "·" else rest[1]
        if ln.strip() == "求职期望:":
            out["expect"] = [x.strip() for x in head[i + 1:i + 5] if x.strip()]
    for k, i in enumerate(tss):
        end = tss[k + 1] if k + 1 < len(tss) else len(seg)
        body: list[str] = []
        for j, ln in enumerate(seg[i + 1:end], i + 1):
            s = ln.strip()
            if not s:
                continue
            if s in ("索要简历", "索要手机", "索要微信", "超级聊聊", "24小时内有回复", "发送"):
                if s not in out["chips"]:
                    out["chips"].append(s)
                break
            if any(_norm(n) and _norm(n) in _norm(s) for n in SYSTEM_NOISE):
                continue
            if s in RECEIPT:
                # 回执 = 我们这一条消息到此结束（"已读/未读"只跟着**我们发的**消息）
                if body:
                    out["messages"].append({"at": seg[i].strip(), "from": "我们",
                                            "text": "\n".join(body)})
                    body = []
                continue
            body.append(s)
        if body:      # 块尾还有话、且后面没有回执 → **他说的话**
            out["messages"].append({"at": seg[i].strip(), "from": "对方", "text": "\n".join(body)})
    return out


# ── 台账 / 报告 ───────────────────────────────────────────────────────────

def greeted_candidates(con, job_code: str) -> list[dict]:
    """我们打过招呼的人（台账里有过 event_type='打招呼'）+ 已有回复情况 + detail_json。"""
    sql = ("SELECT c.id, c.source_id, c.display_name, c.display_company, c.display_position, "
           "m.detail_json FROM candidates c "
           "LEFT JOIN match_results m ON m.candidate_id=c.id AND m.job_code=c.job_code "
           "WHERE c.job_code=? AND EXISTS (SELECT 1 FROM candidate_events e WHERE e.job_code=c.job_code "
           "AND e.candidate_id=c.id AND e.event_type='打招呼') ORDER BY c.id")
    out = []
    for r in con.execute(sql, (job_code,)):
        d = dict(r)
        try:
            d["detail"] = json.loads(d.pop("detail_json") or "{}")
        except Exception:  # noqa: BLE001
            d["detail"] = {}
        out.append(d)
    return out


def recorded_replies(con, job_code: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in con.execute("SELECT candidate_id, note, created_at FROM candidate_events "
                         "WHERE job_code=? AND event_type='回复' ORDER BY id", (job_code,)):
        out.setdefault(r["candidate_id"], []).append(dict(r))
    return out


def record_reply(con, job_code: str, cand_id: int, text: str, *, read: str = "", at: str = "",
                 source: str = "列表预览", deep: dict | None = None) -> str:
    """记一笔回复（**幂等**：同一句话不重复记）。返回 'created' / 'skipped'。

    只增不改：台账加一条 event_type='回复'；`detail_json` 里另存读态与最后一句（供报告/下次比对）。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = con.execute("SELECT detail_json FROM match_results WHERE job_code=? AND candidate_id=?",
                      (job_code, cand_id)).fetchone()
    try:
        detail = json.loads((row or {})["detail_json"] or "{}") if row else {}
    except Exception:  # noqa: BLE001
        detail = {}
    old = str(detail.get("last_reply_text") or "")
    action = "skipped"
    if _norm(text) and _norm(text) != _norm(old):
        note = (f"他回了：{text[:200]}"
                f"｜读到 {at or now}｜列表标记[{read or '无'}]｜来源：{source}")
        con.execute("INSERT INTO candidate_events(candidate_id,job_code,event_type,note,account,created_at)"
                    " VALUES(?,?,?,?,?,?)", (cand_id, job_code, "回复", note, ACCOUNT, now))
        con.commit()
        detail.update({"last_reply_text": text[:1000], "last_reply_at": now,
                       "reply_seen_count": int(detail.get("reply_seen_count") or 0) + 1})
        action = "created"
    detail.update({"chat_checked_at": now, "chat_read": read, "chat_last_msg": str(text or "")[:500]})
    if deep:
        detail.update({"chat_company": deep.get("company") or "",
                       "chat_position": deep.get("position") or "",
                       "chat_expect": deep.get("expect") or [],
                       "chat_flow": (deep.get("messages") or [])[-12:]})
    job_db.save_match(con, job_code, cand_id, {"detail": detail})
    return action


def latest_report(job_code: str) -> Path | None:
    reps = CHAT / job_code / "reports"
    if not reps.exists():
        return None
    got = sorted([p for p in reps.glob("打招呼报告_*.json")
                  if not p.name.startswith("greeting_plan")], key=lambda p: p.stat().st_mtime)
    return got[-1] if got else None


def latest_plan(job_code: str) -> Path | None:
    reps = CHAT / job_code / "reports"
    got = sorted(reps.glob("greeting_plan_*.json"), key=lambda p: p.stat().st_mtime) if reps.exists() else []
    return got[-1] if got else None


def rerender_report(job_code: str, *, now: datetime | None = None) -> dict:
    """重出打招呼报告（**本地渲染 0 token**）——读态/回复一进台账，报告分区立刻跟着变。

    口径来源 = 本岗最新 `greeting_plan_*.json`（"规则是数据"：脚本不替老板改口径）。
    """
    p = latest_plan(job_code)
    return gr.write_report(job_code, plan_path=str(p) if p else None, now=now)


# ── 主流程 ────────────────────────────────────────────────────────────────

def read_chat_page(*, tab_id: int = 0, keep_tab: bool = False, wait_s: int = 24) -> dict:
    """开/复用职聊页 → 等列表渲染 → 拍快照 + 读整页文本。返回 {tab, rows, lines, chars, truncated}。"""
    tab = int(tab_id or 0)
    opened = False
    if not tab:
        tab = find_im_tab()
    if not tab:
        r = act("new_tab", {"url": IM_URL})
        tab = int((r.get("tab") or {}).get("tab_id") or 0)
        opened = True
        if not tab:
            raise RuntimeError("开职聊页失败（拿不到 tab_id）")
    else:
        act("navigate", {"tab_id": tab, "url": IM_URL})
    rows: list[dict] = []
    lines: list[str] = []
    try:
        waited = 0
        while waited < wait_s:
            time.sleep(4)
            waited += 4
            snap = act("snapshot", {"tab_id": tab, "preview_chars": 1000})
            lines = _page_lines(tab)[0]
            rows = parse_rows(snap.get("elements") or [])
            if rows:
                break
        txt = act("page_text", {"tab_id": tab, "max_chars": 0})
        lines = [ln.rstrip() for ln in str(txt.get("text") or "").splitlines()]
        snap = act("snapshot", {"tab_id": tab, "preview_chars": 1000})
        rows = parse_rows(snap.get("elements") or [])
        if not rows:                                    # 元素列表没解析出 → 文本兜底（如实标注）
            rows = parse_rows_from_text(lines)
        attach_times(rows, lines)
        return {"tab": tab, "rows": rows, "lines": lines, "chars": txt.get("chars"),
                "truncated": bool(txt.get("truncated")), "opened": opened}
    finally:
        if opened and not keep_tab:
            try:
                act("close_tab", {"tab_id": tab})
            except Exception:  # noqa: BLE001
                pass


def _page_lines(tab: int) -> tuple[list[str], int]:
    txt = act("page_text", {"tab_id": tab, "max_chars": 0})
    return [ln.rstrip() for ln in str(txt.get("text") or "").splitlines()], int(txt.get("chars") or 0)


def run(job_code: str, *, record: bool = False, deep: bool = False, keep_tab: bool = False,
        tab_id: int = 0) -> dict:
    if not bridge_up():
        raise SystemExit("❌ 桥没在跑（127.0.0.1:8080）——请老板双击 bridge-agent\\start_bridge.bat")
    con = job_db.open_db(job_code)
    try:
        cands = greeted_candidates(con, job_code)
        already = recorded_replies(con, job_code)
    finally:
        con.close()
    rep_p = latest_report(job_code)
    rep = {}
    if rep_p:
        try:
            rep = json.loads(rep_p.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            rep = {}
    rep_items = {int(x.get("candidate_id") or 0): x
                 for k in ("main", "waiting", "replied", "follow_up_due") for x in (rep.get(k) or [])}

    print(f"📨 查看回复（**纯读**）｜岗位 {job_code}｜我们打过招呼 {len(cands)} 人"
          f"（已记过回复 {len(already)} 人）｜模式：{'记账' if record else '**只读（不写库）**'}")
    page = read_chat_page(tab_id=tab_id, keep_tab=keep_tab)
    rows = page["rows"]
    _tabnote = ("（新开的页，读完已关）" if page["opened"] and not keep_tab
                else "（复用已开的职聊页，**没关**）" if not page["opened"] else "（读完不关）")
    print(f"   职聊页：读到 {len(rows)} 条会话（整页 {page['chars']} 字，截断={page['truncated']}）"
          f"｜tab={page['tab']}{_tabnote}")

    m = match_rows(rows, cands)
    decisions: list[dict] = []
    for x in m["matches"]:
        c, r = x["cand"], x["row"]
        ours = our_texts_for(c, rep_items.get(c["id"]))
        kind, why = judge_preview(r["preview"], ours)
        d = {"candidate_id": c["id"], "name": c.get("display_name"), "row": r,
             "kind": kind, "why": why, "deep": None,
             "already": bool(already.get(c["id"])), "read": r.get("read") or ""}
        if deep and (kind in ("reply", "noise")):
            try:
                if click_row(page["tab"], r):
                    time.sleep(2.5)
                    lines, _ = _page_lines(page["tab"])
                    list_end = max([int(x.get("line") or -1) for x in rows] + [-1]) + 1
                    start = find_detail_start(lines, list_end, r["name"])
                    flow = parse_flow(lines, start)
                    d["deep"] = flow
                    theirs = [x2 for x2 in (flow.get("messages") or []) if x2["from"] == "对方"]
                    if theirs:
                        d["kind"], d["why"] = "reply", theirs[-1]["text"]
                    elif kind == "noise":
                        d["kind"], d["why"] = "ours", "会话里只有我们的话（系统提示不是回复）"
                    if flow.get("company"):
                        d["company_ok"] = _norm(flow["company"]) == _norm(c.get("display_company") or "")
            except Exception as e:  # noqa: BLE001
                d["deep_error"] = f"{type(e).__name__}: {e}"
        decisions.append(d)

    replies = [d for d in decisions if d["kind"] == "reply"]
    ours_only = [d for d in decisions if d["kind"] == "ours"]
    noise_only = [d for d in decisions if d["kind"] == "noise"]
    empty = [d for d in decisions if d["kind"] == "empty"]

    print(f"\n── 对号：{len(m['matches'])} 人｜存疑 {len(m['ambiguous'])}｜"
          f"列表里没找到 {len(m['unmatched_cands'])} ──")
    for d in decisions:
        r = d["row"]
        tag = {"reply": "✅ 真回复", "ours": "✉️ 没回（最后一句是我们发的）",
               "noise": "❓ 看不出（列表只给系统提示）", "empty": "❓ 列表这行没读到话"}[d["kind"]]
        extra = f"｜公司对上={'是' if d.get('company_ok') else '否'}" if "company_ok" in d else ""
        print(f"   {tag}｜{d['name']}（页面名 {r['name']}·{r['position']}·{r['time']}"
              f"·[{d['read'] or '无标记'}]）{extra}")
        if d["kind"] == "reply":
            print(f"        他说：{str(d['why'])[:120]}")
        elif d["kind"] == "noise":
            print(f"        系统提示：{d['why']}（要准就加 --deep 点开会话读全文）")
        if d.get("deep"):
            fl = d["deep"]
            print(f"        会话详情：{fl.get('company')}·{fl.get('position')}｜"
                  f"消息 {len(fl.get('messages') or [])} 条"
                  f"（对方 {sum(1 for x in fl.get('messages') or [] if x['from'] == '对方')} 条）")
        if d.get("deep_error"):
            print(f"        ⚠️ 点开会话失败：{d['deep_error']}")
    for x in m["ambiguous"]:
        print(f"   ⚠️ 对号存疑（不只一个人符合）：{x['cand'].get('display_name')} vs 页面 {x['row']['name']}"
              f"（{x['row']['position']}）→ 没敢记")
    for c in m["unmatched_cands"]:
        print(f"   ⚠️ 列表里没找到：{c.get('display_name')}（{c.get('display_position')}）"
              f"——可能列表没渲染全/在别的筛选签下（**没瞎认**）")
    others = m["unmatched_rows"]
    print(f"\n   ℹ️ 另有 {len(others)} 条会话不是我们打过招呼的人"
          f"（主动投递/别的岗）→ **只计数、不记账**（海投口径等老板定）")

    read_only = [d for d in decisions if d["kind"] != "reply" and d["read"] == "已读"]
    unread = [d for d in decisions if d["kind"] != "reply" and d["read"] == "未读"]

    out: dict = {"job_code": job_code, "recorded": record, "deep": deep,
                 "rows": len(rows), "greeted": len(cands), "matched": len(m["matches"]),
                 "ambiguous": len(m["ambiguous"]), "not_in_list": len(m["unmatched_cands"]),
                 "replies": [{"candidate_id": d["candidate_id"], "name": d["name"],
                              "text": d["why"], "read": d["read"]} for d in replies],
                 "read_no_reply": [d["name"] for d in read_only],
                 "unread_only": [d["name"] for d in unread],
                 "unclear": [d["name"] for d in noise_only + empty],
                 "other_rows": len(others), "actions": [], "report": None}

    if record:
        con = job_db.open_db(job_code)
        try:
            for d in decisions:
                if d["kind"] == "reply":
                    a = record_reply(con, job_code, int(d["candidate_id"]), str(d["why"]),
                                     read=d["read"], at=d["row"]["time"],
                                     source="会话全文" if d.get("deep") else "列表预览",
                                     deep=d.get("deep"))
                else:                      # 没回的：只把读态/最后一句存进 detail（**不记事件**）
                    a = record_reply(con, job_code, int(d["candidate_id"]), "", read=d["read"],
                                     at=d["row"]["time"], source="读态", deep=d.get("deep"))
                out["actions"].append({"name": d["name"], "kind": d["kind"], "action": a})
        finally:
            con.close()
        rp = rerender_report(job_code)
        out["report"] = str(rp.get("json") or "")
        d2 = rp.get("daily") or {}
        print(f"\n✅ 已记账（台账只增不改）｜重出报告：{Path(str(rp.get('json'))).name}"
              f"｜等回复 {d2.get('waiting')} / 有回复 {d2.get('replied')}")
    else:
        print("\n⚠️ 这是**只读**：一个字都没写库、报告也没重出。"
              "（老板拍板后加 --yes 记账，或把 reply_run.py 顶上的 DEFAULT_RECORD 改成 True）")

    print(f"\n📊 小结：真回复 {len(replies)}｜已经看过但没回 {len(read_only)}｜"
          f"未读 {len(unread)}｜看不出 {len(noise_only + empty)}｜"
          f"我们打过的共 {len(cands)} 人｜列表里另有 {len(others)} 条无关会话")
    rp_now = latest_report(job_code)
    if rp_now and not record:
        print(f"   （现在的报告：{rp_now.name}）")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="查看回复执行器（**纯读**；默认只读不记账）")
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--yes", action="store_true",
                    help="记账：落台账 event_type='回复' + 重出打招呼报告（不加就只读不写）")
    ap.add_argument("--deep", action="store_true",
                    help="需要时点开会话读全文（核对公司/职位 + 拿对方原话；只点会话行）")
    ap.add_argument("--tab-id", type=int, default=0, help="复用某个已开的标签页（调试用）")
    ap.add_argument("--keep-tab", action="store_true", help="读完不关标签页（调试用）")
    ap.add_argument("--json", action="store_true", help="把结构化结果也打出来")
    args = ap.parse_args()
    rec = bool(args.yes) or bool(DEFAULT_RECORD)
    res = run(args.job_code, record=rec, deep=args.deep, keep_tab=args.keep_tab, tab_id=args.tab_id)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
