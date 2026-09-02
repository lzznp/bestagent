# -*- coding: utf-8 -*-
"""M3 界面 v1：数字合伙人 · Streamlit 汇报面板（信任演进界面）

设计依据（2026-09 M3 设计对话 + 授权矩阵 §7 处理结果 v0.1 试用默认 + PROGRESS「M3 设计讨论记录」）：
- 形态：本地面板，老板日常"呈报窗口"（决策 12 落地）；PyCharm 中 `streamlit run m3_ui.py` 使用
- 步骤制汇报模型：每业务步骤完成 → agent 交报告 → 老板介入（确认/纠错/放行）→ 才进下一步
- 步骤：① 岗位分析 → ② 候选人评估 → ③ 联系跟进（远期，永远人工闸门，v1 不做）
- 行为默认：agent 每步默认停住等老板；本面板只读 business.db 展示 + 记录老板的确认/纠错/放行动作
- 成长数据：纠错/采纳按"岗位→步骤"归档（JSON 账本，先落文档即可，界面不做复杂存储），供日后定放手阈值

v1 边界（HANDOFF §7 实施要点）：不做登录/多用户/美化；不做步骤③；与 DSH Web(3080) 不冲突——
本面板只读 business.db 并写自己的反馈账本，agent 跑链路（run_pipeline）照旧。

数据流：
- 读：bestagent/data/business.db（jobs / candidates / match_results，wails 表设计，307 候选人/307 评估）
      报告卡片主体数据全部来自库；岗位分析/池子评级等"agent 报告细节"若在 data/outbox/*.json 有对应文件
      则自动关联展示（v1 用文件匹配，后续 run_pipeline 直写库后自然消失）
- 写：bestagent/data/feedback/<job_code>.json（确认/纠错/放行 账本，逐条追加）

运行：
  <lzstudy python> -m streamlit run m3_ui.py     # 在 bestagent\ 目录下执行
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

try:  # 集中配置：换电脑只改 framework_config.py / 环境变量
    from framework_config import WORKSPACE, DB_PATH, OUTBOX
except Exception:  # 兜底（直接双击/别处运行时不至于崩）
    WORKSPACE = Path(__file__).resolve().parent
    DB_PATH = WORKSPACE / "data" / "business.db"
    OUTBOX = WORKSPACE / "data" / "outbox"

FEEDBACK_DIR = WORKSPACE / "data" / "feedback"

# ── 步骤制模型配置 ────────────────────────────────────────────────
STEPS = [
    {"no": 1, "name": "岗位分析", "detail": "读 JD → 接单判断 → 拆搜索条件 → 探索采集 → 池子初判 → 做/放弃结论"},
    {"no": 2, "name": "候选人评估", "detail": "池子评级 + 逐人匹配评分 → 推荐清单"},
    {"no": 3, "name": "联系跟进", "detail": "远期：永远人工闸门，v1 未纳入（占位）"},
]
ACTION_LABEL = {"确认": "已确认（采纳）", "纠错": "有纠错待消化", "放行": "已放行"}


# ═════════════════════════════ 数据层（只读 business.db）══════════════════════════

def _conn() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def load_jobs() -> list[dict]:
    """岗位列表（jobs 表全量）。"""
    con = _conn()
    cur = con.execute("SELECT * FROM jobs ORDER BY id")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return rows


def job_view(job_code: str) -> dict:
    """一岗的评估视图：候选人 × 匹配结果（join），按总分降序。"""
    con = _conn()
    cur = con.execute(
        """SELECT c.id AS cid, c.display_name AS name, c.active_badge AS active,
                  m.total_score AS score, m.verdict AS verdict, m.detail_json AS detail
           FROM candidates c
           JOIN match_results m ON m.candidate_id = c.id
           WHERE c.job_code = ? AND m.job_code = ?
           ORDER BY m.total_score DESC, c.id""",
        (job_code, job_code),
    )
    items = []
    for cid, name, active, score, verdict, detail in cur.fetchall():
        d = {}
        if detail:
            try:
                d = json.loads(detail)
            except Exception:
                d = {}
        items.append({
            "cid": cid,
            "name": name or "（未命名）",
            "active": active or "",
            "score": score if score is not None else 0,
            "verdict": verdict or "",
            "points": d.get("match_points", []),
            "concerns": d.get("concerns", []),
            "summary": d.get("summary", "") or "",
        })
    con.close()
    n = len(items)
    scores = [it["score"] for it in items] if items else [0]
    dist: dict[str, int] = {}
    for it in items:
        dist[it["verdict"]] = dist.get(it["verdict"], 0) + 1
    stats = {
        "n": n,
        "avg": round(sum(scores) / n, 1) if n else 0,
        "max": max(scores) if items else 0,
        "dist": dist,  # verdict -> 人数
    }
    return {"job_code": job_code, "items": items, "stats": stats}


def candidate_raw(cid: int) -> str:
    con = _conn()
    row = con.execute("SELECT raw_content FROM candidates WHERE id = ?", (cid,)).fetchone()
    con.close()
    return (row[0] if row else "") or ""


def parse_job_score(text: str) -> dict:
    """解析 jobs.job_score（如 "total=17 level=优质 recommendation=接单"）。"""
    m = re.search(r"total=(\d+)", text or "")
    lv = re.search(r"level=(\S+)", text or "")
    rc = re.search(r"recommendation=(\S+)", text or "")
    return {
        "total": int(m.group(1)) if m else None,
        "level": lv.group(1) if lv else "",
        "recommendation": rc.group(1) if rc else "",
    }


# ═════════════════════════ 报告文件关联（可选富化，数据仍在库为准）════════════════

def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def find_analyze_report(job: dict) -> dict:
    """在 outbox 找该岗的岗前分析报告：按 岗位名+公司 文本匹配（report_*.json）。"""
    title, company = job.get("job_title"), job.get("company_name")
    if not title:
        return {}
    for p in sorted(OUTBOX.glob("report_*.json")):
        d = _read_json(p)
        ex = d.get("jd_extracted") or {}
        if ex.get("job_title") == title and (not company or ex.get("company") == company):
            return d
    return {}


def find_pool_report(job_code: str, dist: dict) -> dict:
    """在 outbox 找该岗的池子评估报告：候选人 verdict 分布与库内完全一致才算该岗（pool_report_*.json）。

    v1 说明：business.db 当前未存池评（评级/缺口等 agent 判断），报告细节在 outbox JSON；
    库里多批合并的岗（如 GPGPU 277 人来自 3 批）无单一文件对应，则不展示池评，只展示库内统计。
    """
    if not dist:
        return {}
    want = tuple(sorted((k, v) for k, v in dist.items()))
    for p in sorted(OUTBOX.glob("pool_report_*.json")):
        d = _read_json(p)
        cands = d.get("candidates") or []
        if not cands:
            continue
        vc: dict[str, int] = {}
        for c in cands:
            v = str(c.get("verdict") or "?")
            vc[v] = vc.get(v, 0) + 1
        if tuple(sorted(vc.items())) == want:
            return d
    return {}


# ═════════════════════════ 成长账（确认/纠错/放行 → JSON 归档）════════════════════

def _ledger_path(job_code: str) -> Path:
    return FEEDBACK_DIR / f"{job_code}.json"


def read_ledger(job_code: str) -> dict:
    p = _ledger_path(job_code)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"job_code": job_code, "entries": []}
    return {"job_code": job_code, "entries": []}


def entries_of(ledger: dict) -> list[dict]:
    return ledger.get("entries") or []


def last_action_for(entries: list[dict], step_no: int) -> str | None:
    """该步骤最近一条动作（确认/纠错/放行），无则 None。"""
    last = None
    for e in entries:
        if e.get("step") == step_no:
            last = e.get("action")
    return last


def append_action(job: dict, step_no: int, step_name: str, action: str, note: str = "") -> dict:
    """记一笔账：岗位 → 步骤 → 动作（确认=采纳 / 纠错=带批注 / 放行=进下一步）。"""
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    ledger = read_ledger(job["job_code"])
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "step": step_no,
        "step_name": step_name,
        "action": action,      # 确认 | 纠错 | 放行
        "note": (note or "").strip(),
    }
    ledger.setdefault("entries", []).append(entry)
    ledger["job_title"] = job.get("job_title") or ledger.get("job_title", "")
    ledger["updated_at"] = entry["ts"]
    _ledger_path(job["job_code"]).write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def feedback_summary() -> list[dict]:
    """全岗台账汇总（供侧栏展示）：每岗每动作计数 + 最近一笔。"""
    out = []
    if not FEEDBACK_DIR.exists():
        return out
    for p in sorted(FEEDBACK_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries = d.get("entries") or []
        cnt = {"确认": 0, "纠错": 0, "放行": 0}
        for e in entries:
            a = e.get("action")
            if a in cnt:
                cnt[a] += 1
        out.append({"job_code": d.get("job_code", p.stem),
                    "job_title": d.get("job_title", ""),
                    "counts": cnt,
                    "last": entries[-1] if entries else None})
    return out


# ═════════════════════════ 展示小件（纯函数）════════════════════════

def _pill(state: str | None, step_no: int) -> str:
    if step_no == 3:
        return "🔒 远期"
    return {
        None: "⏳ 等你处理",
        "确认": "🟡 已确认（采纳）",
        "纠错": "🔧 有纠错待消化",
        "放行": "✅ 已放行",
    }.get(state, "⏳ 等你处理")


def _active_step(entries: list[dict]) -> int | None:
    """第一个未放行的业务步骤（1/2），全放行则 None。"""
    for s in (1, 2):
        if last_action_for(entries, s) != "放行":
            return s
    return None


def _action_hint(state: str | None, step: dict) -> str:
    if state is None:
        return f"现在等你：审阅「{step['name']}」报告 → 确认（采纳）或 纠错（写批注）；认可后点「放行」进入下一步。"
    if state == "确认":
        return "本步报告已确认（采纳）。若认为可进入下一步，点「放行 → 下一步」。"
    if state == "纠错":
        return "本步存在纠错批注（未消化）。请把批注转成对流程/方法论的修改（找 agent 对话修正），再回来确认或放行。"
    return "本步已放行。"


# ═════════════════════════ 交互小件：动作按钮行 ═════════════════════════

def _do_action(job: dict, step_no: int, step_name: str, action: str, note: str = "") -> None:
    append_action(job, step_no, step_name, action, note)
    st.success(f"已记录：{step_name} → {'纠错（含批注）' if action == '纠错' else ACTION_LABEL[action]}")
    st.rerun()


def action_row(job: dict, step: dict) -> None:
    """报告卡片上的动作行：确认 / 纠错（写批注）/ 放行。"""
    jc = job["job_code"]
    key = f"{jc}_{step['no']}"
    entries = entries_of(read_ledger(jc))
    state = last_action_for(entries, step["no"])

    st.markdown(f"**老板动作**　状态：{_pill(state, step['no'])}")
    c1, c2, c3 = st.columns([1.1, 1.5, 1.3])
    if c1.button("✅ 确认（采纳）", key=f"confirm_{key}", width="stretch"):
        _do_action(job, step["no"], step["name"], "确认")
    if c2.button("✏️ 纠错…（写批注）", key=f"correct_{key}", width="stretch"):
        st.session_state[f"show_correct_{key}"] = True
    release_label = ("🚀 放行 → 进入候选人评估" if step["no"] == 1
                     else "✅ 放行（本岗流程完结）")
    if c3.button(release_label, key=f"release_{key}", width="stretch"):
        _do_action(job, step["no"], step["name"], "放行")

    if st.session_state.get(f"show_correct_{key}"):
        note = st.text_area("纠错批注（写清：哪里不对 / 应该怎样 / 依据），提交后归档为成长数据：",
                            key=f"note_{key}", height=110)
        cc1, cc2 = st.columns(2)
        if cc1.button("提交纠错", key=f"submit_correct_{key}"):
            if not note.strip():
                st.warning("批注为空，未记录。请写下纠错内容，或点取消。")
            else:
                _do_action(job, step["no"], step["name"], "纠错", note)
        if cc2.button("取消", key=f"cancel_correct_{key}"):
            st.session_state.pop(f"show_correct_{key}", None)
            st.rerun()


# ═════════════════════════ 报告卡片 ═════════════════════════

def render_step1_card(job: dict) -> None:
    """① 岗位分析报告卡片：库内结论 + 可关联的完整分析报告细节。"""
    st.subheader("① 岗位分析报告")
    sc = parse_job_score(job.get("job_score") or "")
    ana = find_analyze_report(job)

    m1, m2, m3 = st.columns(3)
    m1.metric("总分", f"{sc['total']}/25" if sc["total"] is not None else "—")
    lv_color = {"优质": "green", "普通": "orange", "差": "red"}.get(sc["level"], "gray")
    m2.markdown(f"**评级**  \n:{lv_color}[{sc['level'] or '—'}]")
    rc_color = {"接单": "green", "沟通": "orange", "放弃": "red"}.get(sc["recommendation"], "gray")
    m3.markdown(f"**接单判断**  \n:{rc_color}[{sc['recommendation'] or '—'}]")

    with st.container(border=True):
        st.markdown(f"**{job.get('company_name') or '（公司未知）'}** · {job.get('job_title') or job.get('job_code')}")
        cap = []
        if job.get("salary_range"):
            cap.append(f"💰 {job['salary_range']}")
        if job.get("city"):
            cap.append(f"📍 {job['city']}")
        cap.append(f"🆔 {job.get('job_code')}")
        if job.get("created_at"):
            cap.append(f"入库 {job['created_at']}")
        st.caption("　".join(cap))
        if job.get("link"):
            st.markdown(f"禾蛙链接：{job['link']}")

    if ana and ana.get("score"):
        s = ana["score"]
        if s.get("advice"):
            st.info(f"**分析建议**：{s['advice']}")
        # 评分依据表
        details = s.get("details") or {}
        if details:
            rows = [{"维度": k, "得分": f"{v.get('score', '')} 分",
                     "依据": (v.get("value") or "")[:80]} for k, v in details.items()]
            st.markdown("**评分依据**")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        with st.expander("📄 完整岗前分析报告（分数明细 / 风险清单 / 关键字实验）"):
            if s.get("progress"):
                pr = s["progress"]
                st.markdown(f"**发布方进度**：{pr.get('status', '')}（已有推荐 {pr.get('recommended_count', 0)} / "
                            f"面试 {pr.get('interviewing_count', 0)} / Offer {pr.get('offer_count', 0)}）")
            risks = s.get("risks") or []
            if risks:
                st.markdown("**风险清单**")
                for i, r in enumerate(risks, 1):
                    st.markdown(f"{i}. {r}")
            kw = ana.get("search_keywords") or {}
            if kw:
                st.markdown("**搜索关键字（4 组）**")
                st.dataframe(pd.DataFrame({"组别": list(kw.keys()), "关键字": list(kw.values())}),
                             hide_index=True, width="stretch")
        if s.get("progress_impact"):
            st.caption("机会窗口：" + s["progress_impact"])
    else:
        st.warning("库内仅有结论摘要（job_score），未在 data/outbox/ 关联到该岗的完整岗前分析报告文件。"
                   "如需展示完整分析，请保留 run_pipeline 生成的 report_*.json。")

    with st.expander("📜 岗位原文（JD，前 3000 字）"):
        st.text((job.get("raw_content") or "（无）")[:3000])

    action_row(job, STEPS[0])


def _top_frame(job_code: str, view: dict, limit: int = 10) -> pd.DataFrame:
    rows = []
    for i, it in enumerate(view["items"][:limit], 1):
        rows.append({
            "排名": i,
            "姓名": it["name"],
            "总分": it["score"],
            "结论": it["verdict"],
            "亮点": "；".join(it["points"][:2]),
            "顾虑": "；".join(it["concerns"][:2]),
            "一句话": it["summary"][:60],
        })
    return pd.DataFrame(rows)


def render_step2_card(job: dict) -> None:
    """② 候选人评估报告卡片：库内统计 + 推荐清单 + 池评富化（如可关联）。"""
    st.subheader("② 候选人评估报告")
    view = job_view(job["job_code"])
    s = view["stats"]
    if s["n"] == 0:
        st.info("该岗位暂无候选人评估数据（business.db 中无此岗候选人/评估）。")
        action_row(job, STEPS[1])
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("池子人数", s["n"])
    m2.metric("平均分", s["avg"])
    m3.metric("最高分", s["max"])
    dist_txt = "　".join(f"{k} {v}" for k, v in sorted(s["dist"].items(), key=lambda x: -x[1]))
    m4.markdown(f"**结论分布**  \n{dist_txt or '—'}")

    # 池评富化（agent 判断，来自可唯一关联的 pool_report_*.json；无则不显示）
    pool = find_pool_report(job["job_code"], s["dist"])
    if pool and pool.get("pool_quality"):
        pq = pool["pool_quality"]
        q = pq.get("pool_quality", "")
        q_color = {"优": "green", "良": "green", "中": "orange", "差": "red"}.get(q, "gray")
        st.markdown(f"**池子评级（agent）**：:{q_color}[{q}]　·　"
                    f"匹配分布 高 {pq.get('match_distribution', {}).get('high', '—')} / "
                    f"中 {pq.get('match_distribution', {}).get('medium', '—')} / "
                    f"低 {pq.get('match_distribution', {}).get('low', '—')}")
        if pq.get("recommendation"):
            st.markdown(f"- **建议**：{pq['recommendation']}")
        if pq.get("main_gaps"):
            st.markdown("- **主要缺口**：" + "；".join(pq["main_gaps"]))
        if pq.get("strengths"):
            st.markdown("- **池内优势**：" + "；".join(pq["strengths"]))
        if pool.get("pool_quality", {}).get("data_valid") is not None:
            st.caption("数据校验：" + (pq.get("data_valid_message") or "通过"))

    with st.container(border=True):
        st.markdown(f"**推荐 Top {min(10, s['n'])}（按总分降序，结论列可见推荐/待定/不推荐）**")
        st.dataframe(_top_frame(job["job_code"], view),
                     hide_index=True, width="stretch")

        # 全部候选人：筛选 + 明细
        with st.expander(f"🗂 查看全部 {s['n']} 位候选人（库内真实数据）"):
            fc1, fc2 = st.columns(2)
            verdicts_all = sorted({it["verdict"] for it in view["items"] if it["verdict"]})
            sel_verdicts = fc1.multiselect("按结论筛选", verdicts_all, default=verdicts_all)
            min_score = fc2.slider("按最低总分筛选", 0, 100, 0)
            items = [it for it in view["items"]
                     if (it["verdict"] in sel_verdicts) and (it["score"] >= min_score)]
            sub = pd.DataFrame([{
                "排名": i + 1, "姓名": it["name"], "总分": it["score"],
                "结论": it["verdict"], "一句话": it["summary"][:70],
            } for i, it in enumerate(items)])
            st.caption(f"当前显示 {len(sub)} 位")
            st.dataframe(sub, hide_index=True, width="stretch")

            # 候选人明细（懒查原文）
            cid = st.selectbox(
                "🔎 看某位候选人（评估明细 + 简历原文）",
                [it["cid"] for it in items[:50]],
                format_func=lambda c: next(f"#{it['cid']} {it['name']} {it['score']}分 {it['verdict']}"
                                           for it in items if it["cid"] == c),
            )
            if cid:
                it = next(x for x in items if x["cid"] == cid)
                st.markdown(f"**{it['name']}**　{it['score']} 分 · {it['verdict']}　{it['active']}")
                if it["points"]:
                    st.markdown("**匹配亮点**：" + "；".join(it["points"]))
                if it["concerns"]:
                    st.markdown("**顾虑**：" + "；".join(it["concerns"]))
                if it["summary"]:
                    st.markdown(f"**评估小结**：{it['summary']}")
                with st.expander("简历原文（采集快照）"):
                    raw = candidate_raw(it["cid"])
                    st.text(raw[:2500] + ("\n…（已截断）" if len(raw) > 2500 else ""))

    action_row(job, STEPS[1])


# ═════════════════════════ 主页面 ═════════════════════════

def render_sidebar(jobs: list[dict]) -> str | None:
    with st.sidebar:
        st.markdown("## 📋 岗位列表")
        if not jobs:
            st.warning("business.db 中还没有岗位。先跑 run_pipeline 导入，或检查 DB 路径。")
            return None
        labels = {j["job_code"]: f"{j.get('job_title') or '（无标题）'}｜{j.get('company_name') or ''}"
                  for j in jobs}
        pick = st.radio("选择一个岗位（= 一条流程）", list(labels.keys()),
                        format_func=lambda c: labels[c], key="job_pick")
        if st.button("🔄 刷新数据（重新读库）", width="stretch"):
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.markdown("### 📒 纠错 / 采纳台账")
        sums = feedback_summary()
        if not sums:
            st.caption("尚无反馈记录。对报告点 确认/纠错/放行 后在此汇总（成长数据，供日后定放手阈值）。")
        for s2 in sums:
            c = s2["counts"]
            st.markdown(f"- **{s2['job_title'] or s2['job_code']}**")
            st.caption(f"  采纳 {c['确认']} ｜ 纠错 {c['纠错']} ｜ 放行 {c['放行']}")
            if s2["last"]:
                e = s2["last"]
                note = (e.get("note") or "")[:40]
                st.caption(f"  最近：{e['step_name']}·{e['action']}"
                           + (f"（{note}…）" if note else "") + f" @ {e['ts']}")

        st.divider()
        st.markdown("### 📖 使用说明")
        with st.expander("这是什么 / 怎么用 / 按钮含义"):
            st.markdown(
                "- **这是什么**：数字合伙人 M3 汇报面板 v1（信任演进界面）。读 `business.db`（只读）展示"
                " 每岗的 ① 岗位分析 / ② 候选人评估 报告卡片。\n"
                "- **怎么用**：PyCharm 终端（解释器选 lzstudy）在 `bestagent\\` 下执行\n"
                "  `streamlit run m3_ui.py`，浏览器打开本页。\n"
                "- **按钮含义**：`确认` = 采纳该步报告（记采纳账）；`纠错` = 写批注归档（成长数据，"
                "待消化成方法论规则）；`放行` = 认可进入下一步。\n"
                "- **步骤制**：agent 每步交报告后默认停住等你动作；本面板只记录你的反馈，"
                "跑链路照旧用 `run_pipeline.py`（互不冲突）。\n"
                "- 反馈账本落盘：`bestagent/data/feedback/<job_code>.json`（先落 JSON，界面不做复杂存储）。")


def render_status_bar(job: dict) -> None:
    """顶部状态条：当前卡在哪个步骤、等你什么动作。"""
    entries = entries_of(read_ledger(job["job_code"]))
    states = {s["no"]: last_action_for(entries, s["no"]) for s in STEPS}
    cols = st.columns(len(STEPS))
    for col, s2 in zip(cols, STEPS):
        with col:
            st.markdown(f"**{s2['no']} {s2['name']}**  \n{_pill(states[s2['no']], s2['no'])}")
    active = _active_step(entries)
    if active is None:
        st.info("🎉 本岗位 ① ② 两步均已放行（③ 联系跟进为远期，v1 未纳入）。新跑一轮后可继续在此审阅。")
    else:
        step = STEPS[active - 1]
        st.info(f"📍 流程现在卡在 **{step['no']} {step['name']}**。{_action_hint(states[active], step)}")


def main() -> None:
    st.set_page_config(page_title="数字合伙人 · 汇报面板", page_icon="📊", layout="wide")
    st.markdown("# 📊 数字合伙人 · 汇报面板")
    st.caption(f"M3 界面 v1（最小可用，边用边改）｜ 数据源：`{DB_PATH}`（只读）｜"
               f" 反馈账本：`{FEEDBACK_DIR}`｜ 步骤制：agent 每步交报告后停住等老板")

    jobs = load_jobs()
    render_sidebar(jobs)
    if not jobs:
        st.stop()

    picked = st.session_state.get("job_pick") or jobs[0]["job_code"]
    job = next((j for j in jobs if j["job_code"] == picked), jobs[0])

    # ── 岗位头部
    st.markdown(f"### {job.get('job_title') or '（无标题）'}")
    st.caption(f"岗位编号 {job.get('job_code')} · {job.get('company_name') or '公司未知'} · "
               f"{job.get('salary_range') or '薪资未知'} · {job.get('city') or ''}"
               f"{' · 入库 ' + str(job.get('created_at')) if job.get('created_at') else ''}")

    render_status_bar(job)

    # ── ① 岗位分析报告卡片
    with st.container(border=True):
        render_step1_card(job)

    # ── ② 候选人评估报告卡片
    with st.container(border=True):
        render_step2_card(job)

    # ── ③ 联系跟进（远期占位）
    with st.container(border=True):
        st.subheader("③ 联系跟进（远期）")
        st.markdown("🔒 永远人工闸门（打招呼 / 下载联系方式 / 约面试 / 推荐客户，见授权矩阵）。v1 未纳入。")

    st.divider()
    st.caption("数字合伙人 · M3 界面 v1（2026-09）—— 汇报卡片 + 确认/纠错按钮 = 信任演进界面；"
               "老板反馈（边用边改）驱动迭代。")


if __name__ == "__main__":
    main()
