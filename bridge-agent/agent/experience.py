#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent/experience.py — 经验沉淀（P4-V-T3/T4/T5：自学习闭环的"脑"）

三层架构：插件=手（扩展动作）、视觉=眼（screenshot + vision）、经验=脑（本模块）。
设计要点（DESIGN-P4-VISION.md 第 4 节 V-T3~T5 + 结论 V7）：
- **自动沉淀**：成功任务结束后，从事件流提取关键路径/锚点/截图，写入 knowledge_config.json
  的 experience 条目（自动起草）。
- **置信度闸门（V7）**：高置信（一次成功无重试/无失败）自动写回；低置信（探索有误点/重试）
  只提示不写回，等人工确认（force 参数可绕过，模拟人工闸门）。
- **版本机制**：同站点同路径重复沉淀 → version+1，旧版本压入 history（可回退）。
- **记忆 vs 现实（V-T4）**：site_changed 触发时，visual_confirm_same_layout 用
  "当前截图 vs 沉淀截图"做视觉对比（是否同类布局），减少误报（锚点微调≠真改版）。
- **截图资产（V-T5）**：首次成功处理复杂交互（弹层等）时自动存关键截图入经验条目；
  二次命中时 hint 引用截图，供"疑似同类弹层"视觉对比确认。

经验条目 schema：
    {
      "id": str,                     # 稳定 id（站点+路径派生，可手写）
      "site": str,                   # 匹配键（与 knowledge_config sites 键同规则：路径子串/域名）
      "title": str,
      "key_path": [{"action","desc","params缩略",...}],   # 成功动作序列
      "anchors": [str],              # 关键锚点文本
      "screenshots": [{"path_rel","file","type","desc"}], # 沉淀截图资产
      "version": int, "confidence": "high"|"low",
      "source": "auto"|"manual", "status": "active"|"stale",
      "history": [旧版本...], "created_at": str, "updated_at": str
    }
"""
import json
import os
import re
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

try:
    import agent.knowledge as kb
    from agent.core import submit_task
    from agent.vision import vision_chat
except ImportError:  # 从 agent/ 目录直接运行
    import knowledge as kb
    from core import submit_task
    from vision import vision_chat

# 弹层/复杂交互标志词（V-T5：检测到即视为复杂交互，触发自动截图与锚点采集）
PANEL_MARKERS = ["请选择", "已选", "确认", "确定", "取消", "搜索城市", "热门城市"]

# 沉淀的截图默认放在 logs/screenshots/（与 V-T1 落盘目录一致）
SCREENSHOT_PREFIX = "logs/screenshots/"


# ------------------------------------------------------------
# 事件流 → 经验条目（自动起草）
# ------------------------------------------------------------

def _last_snapshot_url(events):
    url = ""
    for ev in events:
        if ev.get("type") == "snapshot" and ev.get("url"):
            url = ev["url"]
    return url


def _step_desc(act):
    """把单个动作转成人类可读描述（供 key_path 与 hint 使用）。"""
    a = act.get("action", "")
    if a == "click_by_text":
        return f"按文本点击 \"{act.get('text', '')}\""
    if a == "click":
        return f"点击编号 {act.get('index', '?')}（编号以快照为准）"
    if a == "type":
        return f"输入 \"{act.get('text', '')}\" 到编号 {act.get('index', '?')}"
    if a == "navigate":
        return f"跳转 {act.get('url', '')}"
    if a == "extract":
        return f"提取列表（锚点 \"{act.get('anchor_text', '')}\"）"
    if a == "scroll":
        return f"滚动（{act.get('direction', 'down')}）"
    if a in ("new_tab", "switch_tab", "close_tab"):
        return f"{a} tab_id={act.get('tab_id', '?')}"
    return a


def draft_from_events(events, final, url="", tab_id=None, site_key=None):
    """从一轮成功任务的事件流起草经验条目。

    Returns:
        经验条目 dict；events/final 无效时返回 None。
    """
    if not events or not final or not final.get("ok"):
        return None
    if not url:
        url = _last_snapshot_url(events)
    if not url:
        return None

    # 1) 关键路径：成功的实质动作序列（去 snapshot/finish；保留最近 15 步）
    key_path = []
    for ev in events:
        if ev.get("type") == "act" and ev.get("ok") and ev.get("action") not in ("snapshot", "finish", "screenshot", "verify_site", "list_tabs"):
            key_path.append({
                "action": ev["action"],
                "text": ev.get("params", {}).get("text", ""),
                "index": ev.get("params", {}).get("index", -1),
                "occurrence": ev.get("params", {}).get("occurrence", 1),
                "url": ev.get("params", {}).get("url", ""),
                "anchor_text": ev.get("params", {}).get("anchor_text", ""),
                "direction": ev.get("params", {}).get("direction", ""),
                "desc": _step_desc({"action": ev["action"], **ev.get("params", {})}),
            })
    if not key_path:
        return None

    # 2) 锚点：知识库 verify 的 text_anchor/text 值 + 关键路径里的文本动作
    anchors = []
    _dom, _entry = kb.match_knowledge(url)
    if _entry:
        for c in (_entry.get("verify") or []):
            if c.get("type") in ("text_anchor", "text") and c.get("value"):
                anchors.append(c["value"])
    for step in key_path:
        if step.get("action") == "click_by_text" and step.get("text"):
            anchors.append(step["text"])
        if step.get("action") == "extract" and step.get("anchor_text"):
            anchors.append(step["anchor_text"])
    anchors = list(dict.fromkeys(anchors))[:10]

    # 3) 截图资产：本 run 的 screenshot / screenshot_auto 事件
    screenshots = []
    seen_files = set()
    for ev in events:
        if ev.get("type") in ("screenshot", "screenshot_auto"):
            r = ev.get("result") or ev
            f = r.get("path_rel") or r.get("file") or ""
            if f and f not in seen_files:
                seen_files.add(f)
                screenshots.append({
                    "path_rel": f if f.startswith(SCREENSHOT_PREFIX) else f"{SCREENSHOT_PREFIX}{os.path.basename(f)}",
                    "file": os.path.basename(f),
                    "type": "auto" if ev.get("type") == "screenshot_auto" else "manual",
                    "desc": ev.get("desc", ""),
                })

    # 4) 置信度：有重试/失败/卡死 → low（V7 脏经验防护）
    confidence = "high"
    low_reasons = []
    for ev in events:
        t = ev.get("type")
        if t == "retry":
            confidence = "low"
            low_reasons.append(f"动作重试（{ev.get('action')}）")
        elif t == "error":
            confidence = "low"
            low_reasons.append(f"错误（{ev.get('message', '')[:40]}）")
        elif t == "stuck":
            confidence = "low"
            low_reasons.append("无进展终止")
        elif t == "act" and not ev.get("ok"):
            confidence = "low"
            low_reasons.append(f"动作失败（{ev.get('action')}）")

    # 5) site 匹配键：优先知识库匹配到的站点键（路径子串优先），兜底域名
    if site_key is None:
        _dom, _entry = kb.match_knowledge(url)
        site_key = _dom or _domain_of(url)
    if not site_key:
        return None

    # 关键路径签名：站点 + 首个实质动作（action:text）——区分同站点的不同任务，
    # 防止"提取任务"与"城市面板任务"互相覆盖（同站点不同路径 = 不同经验条目）
    _first = key_path[0]
    path_key = (f"{site_key}|{_first['action']}:"
                f"{_first.get('text') or _first.get('anchor_text') or _first.get('index', '')}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_id = _entry_id_for(site_key, key_path)

    return {
        "id": entry_id,
        "site": site_key,
        "path_key": path_key,
        "title": f"关键路径沉淀（{site_key}）",
        "key_path": key_path,
        "anchors": anchors,
        "screenshots": screenshots,
        "version": 1,
        "confidence": confidence,
        "confidence_reasons": low_reasons,
        "source": "auto",
        "status": "active",
        "history": [],
        "created_at": now,
        "updated_at": now,
        "url": url,
    }


def _domain_of(url):
    try:
        from urllib.parse import urlparse
        return (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def _entry_id_for(site_key, key_path):
    """稳定 id：站点键 + 首个实质动作（如 liepin条件页-打开城市面板）。"""
    first = key_path[0] if key_path else {}
    tag = re.sub(r"[^\w\u4e00-\u9fa5-]", "", first.get("desc", "") or first.get("action", ""))[:12]
    base = re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "-", site_key.lower()).strip("-") or "site"
    return f"{base}-{tag}" if tag else base


# ------------------------------------------------------------
# 写回知识库（自动沉淀 / 人工确认）
# ------------------------------------------------------------

def sink(entry, auto=True):
    """把经验条目写回 knowledge_config.json 的 experience 列表。

    Args:
        entry: draft_from_events 的产出（或人工编辑的条目）
        auto: True=自动沉淀（低置信只起草不写回，V7）；False=人工闸门放行，强制写回
    Returns:
        {"written": bool, "entry": dict(写回后条目), "reason": str}
    """
    if not entry or not entry.get("site"):
        return {"written": False, "entry": entry, "reason": "条目无效（缺 site）"}
    if auto and entry.get("confidence") != "high":
        return {"written": False, "entry": entry,
                "reason": f"低置信（{'; '.join(entry.get('confidence_reasons') or ['原因未知'])}），仅起草待人工确认（V7 脏经验防护）"}

    cfg = kb._full_config()
    exp = cfg.setdefault("experience", [])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry["updated_at"] = now
    entry["status"] = "active"

    # 同 id 或同 关键路径签名（path_key）→ 版本 +1（旧版压入 history）。
    # ⚠️ 不按 site 合并：同站点不同任务（不同关键路径）是独立经验条目，防止互相覆盖。
    idx = None
    for i, e in enumerate(exp):
        if e.get("id") == entry.get("id"):
            idx = i
            break
        if entry.get("path_key") and e.get("path_key") == entry.get("path_key"):
            idx = i
            break
    if idx is not None:
        old = dict(exp[idx])
        old.pop("history", None)
        entry["version"] = int(old.get("version", 1)) + 1
        entry["created_at"] = old.get("created_at", now)
        entry["history"] = (old.get("history") or []) + [old]
        # P4-V-T5：截图资产合并（新截图优先、旧截图保留）——沉淀资产不因更新而丢失
        merged_shots = []
        seen = set()
        for s in (entry.get("screenshots") or []) + (old.get("screenshots") or []):
            f = s.get("file") or s.get("path_rel") or ""
            if f and f not in seen:
                seen.add(f)
                merged_shots.append(s)
        entry["screenshots"] = merged_shots
        # 锚点并集去重（保留上限 10）
        entry["anchors"] = list(dict.fromkeys(
            (entry.get("anchors") or []) + (old.get("anchors") or [])))[:10]
        exp[idx] = entry
        action = f"update（v{entry['version']}，旧版入 history）"
    else:
        entry["version"] = 1
        entry["history"] = []
        exp.append(entry)
        action = f"create（v1）"

    if not kb.save_config(cfg):
        return {"written": False, "entry": entry, "reason": "写回 JSON 失败"}
    return {"written": True, "entry": entry, "reason": action}


def sink_after_run(events, final, url="", tab_id=None, auto=True, draft_on_low=True):
    """任务成功后的自动沉淀入口（bridge/CLI 调用）。

    Args:
        events: run_loop 事件流
        final: run_loop 返回 {"ok": ...}
        url: 页面 URL（缺省从事件流取）
        tab_id: 操作标签页
        auto: True=自动沉淀（低置信不写回）；False=人工放行强制写回
        draft_on_low: 低置信未写回时是否存草稿（logs/experience_drafts.jsonl，供人工确认）
    Returns:
        {"written": bool, "entry": dict|None, "reason": str, "draft_id": str|None} 或 None（无可沉淀）
    """
    if not final or not final.get("ok"):
        return None
    entry = draft_from_events(events, final, url=url, tab_id=tab_id)
    if not entry:
        return None
    res = sink(entry, auto=auto)
    if not res["written"] and draft_on_low and entry.get("confidence") != "high":
        draft_id = save_draft(entry)
        res["draft_id"] = draft_id
        res["reason"] = f"{res['reason']}（草稿已存 draft_id={draft_id}，可经 /api/experience/confirm 人工确认）"
    return res


# ------------------------------------------------------------
# 低置信经验草稿（人工闸门：V7 脏经验防护的第二道）
# ------------------------------------------------------------

def _drafts_path():
    return os.environ.get("EXPERIENCE_DRAFTS",
                          os.path.join(ROOT, "logs", "experience_drafts.jsonl"))


def save_draft(entry, reason=""):
    """把低置信经验条目存为待人工确认的草稿。

    Returns:
        draft_id（形如 exp-<时间戳>-<短随机>）
    """
    import uuid
    draft_id = f"exp-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
    rec = {
        "draft_id": draft_id,
        "status": "pending",          # pending / approved / rejected
        "reason": reason,
        "entry": entry,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": "",
    }
    try:
        os.makedirs(os.path.dirname(_drafts_path()), exist_ok=True)
        with open(_drafts_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return draft_id
    except Exception as e:
        return f"save-failed-{e}"


def list_drafts(status="pending"):
    """列出草稿（默认只列 pending；status=None 列全部）。"""
    out = []
    if not os.path.exists(_drafts_path()):
        return out
    with open(_drafts_path(), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if status is None or rec.get("status") == status:
                out.append(rec)
    return out


def approve_draft(draft_id, approve=True):
    """人工确认草稿：approve=True → 强制写回经验库（auto=False 放行）；False → 拒绝。

    Returns:
        {"ok": bool, "draft": dict|None, "sink_result": dict|None, "error": str|None}
    """
    drafts = list_drafts(status=None)
    target = None
    for rec in drafts:
        if rec.get("draft_id") == draft_id:
            target = rec
            break
    if target is None:
        return {"ok": False, "error": f"草稿不存在: {draft_id}"}
    if target.get("status") != "pending":
        return {"ok": False, "error": f"草稿已处理（status={target.get('status')}）"}
    sink_result = None
    if approve:
        entry = target.get("entry") or {}
        entry["source"] = "manual-approved"
        entry["status"] = "active"
        sink_result = sink(entry, auto=False)  # 人工放行，绕过置信度闸门
    target["status"] = "approved" if approve else "rejected"
    target["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(_drafts_path(), "w", encoding="utf-8") as f:
            for rec in drafts:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        return {"ok": False, "error": f"草稿状态写回失败: {e}", "sink_result": sink_result}
    return {"ok": True, "draft": target, "sink_result": sink_result, "error": None}


# ------------------------------------------------------------
# 记忆命中：经验 hint（少决策少截图）
# ------------------------------------------------------------

def hint_for_experience(entry):
    """把经验条目转成注入 system 提示词的文本（按记忆走，少决策）。"""
    if not entry:
        return ""
    lines = [f"【经验沉淀】本页关键路径（已实测成功，按此走可少决策；编号以最新快照为准）："]
    for i, step in enumerate(entry.get("key_path") or [], 1):
        lines.append(f"  {i}. {step.get('desc', step.get('action', ''))}")
    if entry.get("anchors"):
        lines.append("锚点：" + "、".join(entry["anchors"][:8]))
    if entry.get("screenshots"):
        lines.append("沉淀截图（视觉对比参考）：" + "；".join(
            f"{s.get('desc') or s.get('type')}={s.get('path_rel', s.get('file'))}" for s in entry["screenshots"][:3]))
    return "\n".join(lines)


def experience_hint_for(url):
    """按 URL 返回经验 hint（同站点多个关键路径条目全部注入；无经验返回空串）。"""
    entries = kb.match_experiences(url)
    if not entries:
        return ""
    return "\n\n".join(hint_for_experience(e) for e, _ in entries)


# ------------------------------------------------------------
# V-T4：记忆 vs 现实（视觉确认布局是否同类）
# ------------------------------------------------------------

def _pick_ref_screenshot(entry, prefer_keywords=()):
    """从经验条目的截图资产里挑参考截图：优先 desc/type 命中关键词的，缺省取第一张。

    场景区分：改版复核（V-T4）优先"常态/干净"参考；弹层命中（经验召回）优先"面板/弹层"参考。
    """
    refs = (entry or {}).get("screenshots") or []
    if not refs:
        return None
    if prefer_keywords:
        for s in refs:
            hay = f"{s.get('desc', '')} {s.get('type', '')}"
            if any(k in hay for k in prefer_keywords):
                return s
    return refs[0]


def visual_confirm_same_layout(bridge_url, tab_id, entry=None, url="", api_key=None,
                               current_path=None, ref_kind="layout"):
    """site_changed 触发/弹层命中的视觉复核：当前截图 vs 经验沉淀截图。

    Args:
        current_path: 已存在的当前截图路径（如自动截图产物）；None 则现场截一张。
        ref_kind: 参考截图选择——"layout"（改版复核，优先常态/干净参考）或
                  "panel"（弹层命中，优先面板/弹层参考）。
    Returns:
        (is_same, detail)：
            is_same True = 视觉判定同类布局（疑似误报/同类弹层）；
            is_same False = 判定不同布局（真改版/异类弹层）；
            is_same None = 无法判定（无截图/截图失败/视觉异常）。
    """
    if entry is None:
        entry, _ = kb.match_experience(url)
    _prefer = ("干净", "常态", "布局") if ref_kind == "layout" else ("面板", "弹层", "panel")
    ref = _pick_ref_screenshot(entry, _prefer)
    if not ref:
        return None, "经验条目无沉淀截图，无法视觉对比"
    ref_rel = ref.get("path_rel") or ref.get("file") or ""
    ref_path = ref_rel if os.path.isabs(ref_rel) else os.path.join(ROOT, ref_rel)
    if not os.path.exists(ref_path):
        return None, f"沉淀截图不存在：{ref_path}"
    if current_path:
        cur_path = current_path
    else:
        # 当前截图
        r = submit_task(bridge_url, "screenshot", {"tab_id": tab_id}, source="experience")
        if not r["ok"]:
            return None, f"当前截图失败：{r.get('error')}"
        cur_path = (r.get("result") or {}).get("path", "")
    if not cur_path:
        return None, "当前截图未落盘"
    q = ("下面第一张截图是历史沉淀的页面参考（同一网站同一功能页），第二张是当前实时页面。"
         "请判断它们是否属于同一类布局/同一功能页面：比较整体结构、功能区划分、主要控件类型是否一致，"
         "忽略文字细节、选中状态、数据内容的差异。只回答：same 或 different，并给一句简短理由。")
    try:
        ans = vision_chat([ref_path, cur_path], q, api_key=api_key, max_tokens=1500)
    except Exception as e:
        return None, f"视觉对比失败：{e}"
    low = (ans or "").strip().lower()
    if "different" in low:
        return False, f"视觉判定：不同布局（{ans[:120]}）"
    if "same" in low:
        return True, f"视觉判定：同类布局（{ans[:120]}）"
    return None, f"视觉输出无法解析（{ans[:120]}）"


if __name__ == "__main__":
    # 自测：python agent/experience.py
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fake_events = [
        {"type": "snapshot", "url": "https://h.liepin.com/search/getConditionItem", "element_count": 199},
        {"type": "act", "action": "click_by_text", "params": {"text": "其他", "occurrence": 1}, "ok": True},
        {"type": "act", "action": "click", "params": {"index": 271}, "ok": True},
        {"type": "act", "action": "click_by_text", "params": {"text": "确认", "occurrence": 1}, "ok": True},
    ]
    d = draft_from_events(fake_events, {"ok": True}, url="https://h.liepin.com/search/getConditionItem")
    print("draft:", json_dumps(d))
    if d:
        res = sink(d, auto=False)
        print("sink:", res.get("written"), res.get("reason"), "version=", (res.get("entry") or {}).get("version"))
        print("hint:\n", hint_for_experience(res.get("entry")))


def json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
