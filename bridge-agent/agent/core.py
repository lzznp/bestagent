#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent/core.py — 浏览器 Agent 核心循环（CLI 与桥接服务共用）

LLM tool-use 循环：任务描述 → 快照 → LLM 决策 → 工具动作 → 验证 → 直到 finish。
通过 on_step 回调把每一步（快照/决策/动作/结果/错误）实时推给调用方（CLI 打印 / 控制台页面）。
"""
import json
import os
import random
import re
import time
import urllib.request
from urllib.parse import urlparse

# P2-4：站点知识库（结构化，含改版基线检测规则）
try:
    import agent.knowledge as kb   # bridge 场景（ROOT 在 sys.path）
except ImportError:                # CLI 场景（agent/ 在 sys.path）
    import knowledge as kb

# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------
MODEL = os.environ.get("AGENT_MODEL", "deepseek-chat")
LLM_URL = "https://api.deepseek.com/v1/chat/completions"
LLM_TIMEOUT = 90

SYSTEM_PROMPT = """你是浏览器操作 Agent。你通过一组浏览器工具操作真实浏览器，完成用户的自然语言任务。
每一步你会收到当前页面的快照（标题/URL/带编号的交互元素/正文预览），你只能输出一个 JSON 动作。

可用动作（必须输出其中一个）：
- {"action":"click","index":N}               点击编号 N 的元素
- {"action":"click_by_text","text":"...","occurrence":1}  按文本点击：点击包含该文本的最小可点元素（条件选项/带字按钮等快照编号点不到的；occurrence 可选=第几个匹配，默认 1）
- {"action":"type","index":N,"text":"..."}   在编号 N 的输入框输入文本
- {"action":"scroll","direction":"down|up|top|bottom","amount":600}  滚动页面
- {"action":"navigate","url":"https://..."}  跳转到 URL
- {"action":"extract","anchor_text":"..."}  提取当前页列表数据：anchor_text 为卡片内任一稳定子串（如"立即沟通"），返回所有匹配卡片行 {text, fields}；fields 含行内命名 input 的 value（拿到数据后应 finish）
- {"action":"list_tabs"}                    列出当前窗口所有标签页（tab_id/url/title/active）
- {"action":"new_tab","url":"https://..."}  打开新标签页并激活
- {"action":"switch_tab","tab_id":N}        切换到指定标签页（激活；后续操作作用于新激活页）
- {"action":"close_tab","tab_id":N}         关闭指定标签页（新开标签用完后关闭）
- {"action":"screenshot"}                   截图当前标签页（PNG 落盘 logs/screenshots/，返回文件路径）。只读动作：用于"看真实渲染"（布局/弹层/遮挡），与 DOM 快照互补，不改变页面
- {"action":"som_shot"}                     SOM 标注截图：给页面可点元素叠加红色编号徽标后截图（编号=快照同序的视觉顺序），返回截图文件路径+元素编号/坐标映射。只读动作：用于"看图选编号"（视觉模型读编号，坐标由标注层负责）
- {"action":"snapshot"}                      重新获取快照（页面变化后）
- {"action":"finish","summary":"...","data":{...}}  任务完成，输出结构化结果

规则：
1. 每次只输出一个动作，附 "reason" 说明为什么。
2. 找不到目标元素时，用 scroll 或 snapshot 换视角，不要乱点。
3. 输入文本后页面可能刷新，下一步先 snapshot 验证。
4. 目标达成后必须用 finish 结束，把采集/整理的结果放 data。
5. 只输出 JSON，不要输出任何其他文字。
6. 翻页任务（如"翻 N 页/采集多页"）：每提取完一页后，下一步必须找到分页区的"下一页"或页码数字元素并 click 翻页（"共 N 页"是总页数信息，点击不会翻页），再 snapshot 确认新页，然后继续 extract；重复直到翻满要求的页数。**每次 extract 前先确认页面已变化**：如果 extract 返回的新数据为 0 行（与上一页完全相同），说明还在同一页，必须先翻页再 extract，不要重复提取同一页。
7. extract 每次只返回当前页数据；若上一页数据已提取过，翻页后再次调用才会得到新数据。
8. 任务要求"翻 N 页"时，必须翻满 N 页（每页都 extract 过）才能 finish；即使当前页数据已提取，也不要提前 finish。
9. 多标签任务：用 list_tabs 查看标签页；new_tab 打开新标签、switch_tab 切换激活标签。切换标签后页面变化，下一步先 snapshot 再操作；不要操作与本任务无关的标签页。新标签（如点击链接新开的详情页）用完后用 close_tab 关闭，再 switch_tab 回原工作标签。
10. 当前快照已是最新（系统每步开始都会自动重新快照，无需你主动 snapshot 来"等页面更新"）。看到目标元素编号就直接操作；若元素编号点不到（如选项类 span/li），用 click_by_text 按文本点击。不要连续输出 snapshot 空转——页面状态与预期不符时，用 scroll/click/click_by_text 等动作推进或换策略。"""

TOOL_DESC = """工具：click(编号)/click_by_text(文本[,occurrence])/type(编号,文本)/scroll(方向)/navigate(URL)/extract(anchor_text)/list_tabs/new_tab(URL)/switch_tab(tab_id)/close_tab(tab_id)/screenshot/som_shot/snapshot/finish"""

# ------------------------------------------------------------
# P2-5：技能注册表（GET /api/agent/skills 返回，供调度 Agent 查询技能后派活）
# 与 extension/background.js 的 TOOL_FUNCS 一一对应；verify_site 是内部动作
# （知识库改版基线检测，调度 Agent 可调用），finish 是 agent 循环内部动作不算浏览器技能。
# ------------------------------------------------------------
SKILLS = [
    {"name": "snapshot",
     "description": "获取当前标签页快照：标题/URL/编号交互元素列表/正文预览（含分页元素标注），是 LLM 决策与元素编号的来源",
     "params": {"type": "object", "properties": {}, "required": []}},
    {"name": "click",
     "description": "按快照编号点击元素（点击后页面可能刷新，需重新快照）",
     "params": {"type": "object",
                "properties": {"index": {"type": "integer", "description": "快照中的元素编号"}},
                "required": ["index"]}},
    {"name": "click_by_text",
     "description": "按文本点击：点击包含该文本的最小可点元素（解决'看得见字、点不了'的选项类 span/li，如搜索条件选项；快照编号点不到时用）",
     "params": {"type": "object",
                "properties": {"text": {"type": "string", "description": "目标文本（元素内任意子串）"},
                               "occurrence": {"type": "integer", "description": "第几个匹配，默认 1（页面有多个同文本元素时指定）"}},
                "required": ["text"]}},
    {"name": "type",
     "description": "在编号输入框输入文本（兼容 React 受控组件）",
     "params": {"type": "object",
                "properties": {"index": {"type": "integer", "description": "快照中的输入框编号"},
                               "text": {"type": "string", "description": "要输入的文本"}},
                "required": ["index", "text"]}},
    {"name": "scroll",
     "description": "滚动页面",
     "params": {"type": "object",
                "properties": {"direction": {"type": "string", "enum": ["down", "up", "top", "bottom"],
                                             "description": "滚动方向"},
                               "amount": {"type": "integer", "description": "滚动像素（默认 600）"}},
                "required": ["direction"]}},
    {"name": "navigate",
     "description": "当前标签页跳转到 URL",
     "params": {"type": "object",
                "properties": {"url": {"type": "string", "description": "目标 URL"}},
                "required": ["url"]}},
    {"name": "extract",
     "description": "通用列表提取：anchor_text 为卡片内任一稳定子串（如\"立即沟通\"），返回所有匹配卡片行 {text, fields}；fields 含行内命名 input 的 value（站点唯一 ID 由 agent 侧知识库认领）",
     "params": {"type": "object",
                "properties": {"anchor_text": {"type": "string",
                                               "description": "卡片内任一稳定子串（如\"立即沟通\"）"}},
                "required": ["anchor_text"]}},
    {"name": "list_tabs",
     "description": "列出当前窗口所有标签页（tab_id/url/title/active）。后台型动作：不注入页面，直接 chrome.tabs API",
     "params": {"type": "object", "properties": {}, "required": []}},
    {"name": "new_tab",
     "description": "打开新标签页并激活（后台型动作）",
     "params": {"type": "object",
                "properties": {"url": {"type": "string", "description": "要打开的 URL"}},
                "required": ["url"]}},
    {"name": "switch_tab",
     "description": "切换激活标签页（后台型动作；切换后注入型动作作用于新激活页）",
     "params": {"type": "object",
                "properties": {"tab_id": {"type": "integer",
                                          "description": "目标标签页 id（list_tabs 获取）"}},
                "required": ["tab_id"]}},
    {"name": "close_tab",
     "description": "关闭指定标签页（后台型动作；新标签用完后关闭）",
     "params": {"type": "object",
                "properties": {"tab_id": {"type": "integer", "description": "要关闭的标签页 id"}},
                "required": ["tab_id"]}},
    {"name": "screenshot",
     "description": "截图当前标签页（PNG 落盘 logs/screenshots/，返回文件路径）。只读动作：看页面真实渲染（布局/弹层/遮挡/视觉状态），与 DOM 快照互补，不改变页面",
     "params": {"type": "object", "properties": {}, "required": []}},
    {"name": "som_shot",
     "description": "SOM 标注截图：给页面可点元素叠加红色编号徽标后截图（编号=快照同序的视觉顺序 top→left），返回截图文件路径 + 元素编号/坐标映射（rect）。只读动作：用于看图选编号（视觉模型读徽标编号，坐标由标注层 rect 负责，模型只需选号）",
     "params": {"type": "object",
                "properties": {"tab_id": {"type": "integer", "description": "目标标签页 id（缺省当前激活页）"}},
                "required": []}},
    {"name": "verify_site",
     "description": "站点结构基线检测（内部动作）：checks=[{type: text_anchor|input_name|text|selector, value}]，返回每项是否命中；任一缺失说明网站可能改版（知识库基线失效，需人工核对）",
     "params": {"type": "object",
                "properties": {"checks": {"type": "array",
                                          "items": {"type": "object",
                                                    "properties": {"type": {"type": "string",
                                                                             "enum": ["text_anchor", "input_name", "text", "selector"]},
                                                                   "value": {"type": "string"}},
                                                    "required": ["type", "value"]}}},
                "required": ["checks"]}},
]


# ------------------------------------------------------------
# P2-1/P2-4：站点知识注入（委托 agent/knowledge.py 结构化知识库）
# 按 URL 域名匹配：hint 注入 system 提示词；source_id_field 驱动
# finish 时程序化字段映射（不依赖 LLM 转述）；verify 规则做改版基线检测。
# ------------------------------------------------------------

def site_hint_for(url):
    """按 URL 匹配知识库，返回 (hint, source_id_field) 或 (None, None)。"""
    _dom, entry = kb.match_knowledge(url)
    if entry:
        return entry.get("hint"), entry.get("source_id_field")
    return None, None


# ------------------------------------------------------------
# 桥接服务调用
# ------------------------------------------------------------

def bridge_get(bridge_url, path):
    with urllib.request.urlopen(f"{bridge_url}{path}", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def bridge_post(bridge_url, path, payload):
    req = urllib.request.Request(
        f"{bridge_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def submit_task(bridge_url, action, params=None, source="agent"):
    """提交任务并等待扩展执行结果。"""
    resp = bridge_post(bridge_url, "/api/task", {"action": action, "params": params or {}, "source": source})
    task = resp["task"]
    task_id = task["id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        time.sleep(1.0)
        t = bridge_get(bridge_url, f"/api/task/{task_id}")["task"]
        if t["status"] == "done":
            return {"ok": True, "result": t["result"]}
        if t["status"] == "failed":
            return {"ok": False, "error": t.get("error") or (t.get("result") or {}).get("error", "action-failed")}
        if t["status"] == "timeout":
            return {"ok": False, "error": "任务超时"}
    return {"ok": False, "error": "等待执行结果超时"}


# ------------------------------------------------------------
# T2：动作失败自动重试（重试有日志；间隔随机化防抖）
# ------------------------------------------------------------

# 可重试的动作：元素类操作失败多为瞬时（页面未稳定/注入竞争），重试有收益；
# snapshot/navigate/finish 不重试（snapshot 失败是环境问题，navigate 重试会重复跳转）。
RETRYABLE_ACTIONS = ("click", "click_by_text", "type", "scroll", "extract")
ACTION_RETRY_TIMES = 2          # 每个动作最多额外重试次数
RETRY_DELAY_MIN = 1.0           # 重试间隔随机化下限（秒）
RETRY_DELAY_MAX = 2.5           # 重试间隔随机化上限（秒）

# ------------------------------------------------------------
# P3-T5：动作分级（D11 落地）——只读 / 低风险 / 不可逆 三级
# 只读：不改变页面状态，任意执行
# 低风险：改变页面状态但可恢复（点击/输入/跳转/开关标签），正常执行
# 不可逆：对外产生永久影响（发送/发布/删除/下单等），默认必须人工确认
#   ——LLM 决策输出不可逆动作时，先发 confirm_requested 事件等待确认
#     （confirm_requested 回调返回 True 才执行；拒绝/超时则换策略）。
#   ⚠️ 目前扩展工具面没有不可逆动作（都是只读/低风险）；本表为机制预留，
#     未来加"发送/发布/删除"类工具时在此声明即可自动生效。
# ------------------------------------------------------------
ACTION_LEVEL_READONLY = ("snapshot", "scroll", "extract", "list_tabs", "verify_site", "screenshot", "som_shot")
ACTION_LEVEL_LOWRISK = ("click", "click_by_text", "type", "navigate", "new_tab", "switch_tab", "close_tab")
IRREVERSIBLE_ACTIONS = ()  # 预留：("send_message", "publish", "delete", "confirm_order") 等

def action_level(action):
    """返回动作级别：readonly / lowrisk / irreversible。"""
    if action in IRREVERSIBLE_ACTIONS:
        return "irreversible"
    if action in ACTION_LEVEL_LOWRISK:
        return "lowrisk"
    return "readonly"


def execute_with_retry(bridge_url, action, params, on_step=None, step=None):
    """执行动作；失败自动重试（T2），每次重试通过 on_step 输出 retry 日志。

    P3-T4：tab-lost（指定标签页已关闭）是确定性错误——重试必然同样失败，
    直接返回让 LLM/调度 Agent 换策略（重新 list_tabs 确认目标标签），不浪费时间。

    Returns:
        (result, attempts): result 为 submit_task 的返回，attempts 为实际尝试次数。
    """
    attempts = 0
    while True:
        attempts += 1
        result = submit_task(bridge_url, action, params, source="agent")
        if result["ok"] or action not in RETRYABLE_ACTIONS or attempts > ACTION_RETRY_TIMES:
            return result, attempts
        err = result.get("error") or ""
        if err.startswith("tab-lost") or err.startswith("no-active-tab"):
            return result, attempts
        # 失败且可重试且未超限 → 记录日志并随机间隔后重试
        if on_step:
            on_step({"type": "retry", "step": step, "action": action,
                     "attempt": attempts, "max_retries": ACTION_RETRY_TIMES,
                     "error": result["error"]})
        time.sleep(random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX))


# ------------------------------------------------------------
# LLM 调用
# ------------------------------------------------------------

def load_api_key(env_path=None):
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    if env_path is None:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def llm_chat(messages, api_key):
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_action(raw):
    """容错解析 LLM 输出的 JSON。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                pass
    return {"action": "snapshot", "reason": "LLM 输出无法解析，重新快照"}


def snapshot_to_text(snap):
    """把快照压缩成给 LLM 的文本。"""
    if not snap or not snap.get("ok"):
        return f"快照失败: {snap}"
    lines = [f"页面标题: {snap.get('title','')}", f"URL: {snap.get('url','')}"]
    elements = snap.get("elements") or []
    if elements:
        # T4：提高元素显示上限，确保分页按钮（页码/下一页，通常在元素列表尾部）对 LLM 可见
        # P3-T1：再次提高上限（150→400）——猎聘条件页弹层（城市选择面板）元素编号 280+，
        # 前 150 截断会把弹层内"杭州/成都/确认"全砍掉，LLM 看不到只能打转（G3 根因）。
        lines.append("交互元素（编号: 标签 | 名称 | 值）:")
        for el in elements[:400]:
            parts = [str(el["index"]), el.get("tag", ""), el.get("name", "")]
            if el.get("value"):
                parts.append(f"值={el['value']}")
            if el.get("href"):
                parts.append(el["href"])
            lines.append("  " + " | ".join(parts))
        if len(elements) > 400:
            lines.append(f"  …（共 {len(elements)} 个元素，仅显示前 400 个）")
        # T4：标注分页元素（下一页/上一页 优先，页码其次），引导 LLM 执行翻页任务。
        # P2-1：把"共 N 页"这类信息元素单独标注为不可点，避免 LLM 误当翻页按钮点击。
        page_els = [el for el in elements
                    if re.search(r"下一页|上一页|向后|向前|^\d+$|^(共|当前|第)\s*\d+\s*页$", (el.get("name") or ""))]
        if page_els:
            nav_words = [el for el in page_els if re.search(r"下一页|上一页|向后|向前|^\d+$", el.get("name") or "")]
            info_words = [el for el in page_els if re.search(r"^(共|当前|第)\s*\d+\s*页$", el.get("name") or "")]
            nav_first = nav_words + [el for el in page_els if el not in nav_words and el not in info_words]
            line = ("分页元素（翻页时点击这里，仅'下一页'或页码数字可点）："
                    + "、".join(f"编号{el['index']}({el.get('name')})" for el in nav_first[:10]))
            if info_words:
                line += "；信息(不可点)：" + "、".join(f"编号{el['index']}({el.get('name')})" for el in info_words)
            lines.append(line)
    preview = (snap.get("body_preview") or "").strip()
    if preview:
        # T4：元素多时（列表页）缩短正文预览，避免 3000 字正文淹没分页元素提示、
        # 误导 LLM 以为任务已"看到全部数据"；元素少时保留完整正文。
        # P3-T1：改成"头部600+尾部400"——弹层（城市选择面板/对话框）在正文**尾部**，
        # 只留头部会把弹层内容砍掉（G3 打转根因之一：LLM 看到编号却不知道是弹层内元素）。
        if len(elements) > 40:
            if len(preview) > 1000:
                preview = preview[:600] + "\n…（中部省略）…\n" + preview[-400:]
            lines.append("正文预览（头部600+尾部400字，列表页已截短）:")
        else:
            lines.append("正文预览（前3000字）:")
        lines.append(preview)
        # P3-T2：弹层/对话框检测标注——正文出现弹层标志词时，明确告诉 LLM
        # 当前有浮层（G3 打转根因之二：LLM 看到面板内元素编号却不知道那是弹层，
        # 反复 snapshot 等"新状态"）
        # ⚠️ P4-SOM 修正：编号改为视觉顺序（top→left），弹层元素在屏幕中部、
        # 编号位于列表中部区域（不再"尾部"）；原"尾部编号属于弹层"说法已失效。
        # ⚠️ 修正：裸"筛选"会误匹配"清空筛选条件"（常态页面文本），用 筛选(?!条件) 排除。
        if re.search(r"请选择|已选\s*[（(]?\d|确认|确定|取消|搜索城市|筛选(?!条件)", preview):
            lines.append("⚠️ 检测到页面有弹层/浮层（如城市选择面板、对话框）："
                         "弹层内元素按视觉位置编号（通常位于编号列表中部区域，标题含'请选择/已选'等），"
                         "可直接用编号或 click_by_text 点击；操作后重新快照确认。")
    return "\n".join(lines)


# ------------------------------------------------------------
# T3：风控参数（翻页间隔随机化 + 验证码/登录过期检测）
# ------------------------------------------------------------

# 验证码/风控特征：快照正文或标题命中任一 → 停止并提示转人工。
# ⚠️ 用精确特征词：裸"验证码"太宽泛（普通页面"获取验证码"短信按钮会误报），
# 登录过期/未登录由 RISK_URL_PATTERNS 兜底（URL 命中 login 即拦截）。
RISK_TEXT_PATTERNS = [
    ("请完成安全验证", "检测到安全验证"),
    ("安全验证", "检测到安全验证"),
    ("滑动验证", "检测到滑动验证"),
    ("拖动滑块", "检测到滑块验证"),
    ("人机验证", "检测到人机验证"),
    ("图形验证码", "检测到图形验证码"),
    ("验证码错误", "检测到验证码错误"),
    ("请输入验证码", "检测到验证码输入框（登录或风控）"),
    ("captcha", "检测到 captcha"),
]
# 登录过期/未登录：URL 命中任一 → 停止并提示重新登录
RISK_URL_PATTERNS = [
    "/login", "account/login", "passport", "signin", "loginsuccess", "login?",
]


def detect_risk(snap_text, url, title=""):
    """风控检测：验证码特征 / 登录过期。命中返回 (True, 原因)，否则 (False, None)。"""
    haystack = f"{title}\n{snap_text}".lower()
    for kw, reason in RISK_TEXT_PATTERNS:
        if kw.lower() in haystack:
            return True, reason
    ul = (url or "").lower()
    for marker in RISK_URL_PATTERNS:
        if marker in ul:
            return True, f"URL 命中登录/过期特征（{marker}），请重新登录后转人工处理"
    return False, None


# ------------------------------------------------------------
# 主循环（CLI 与控制台共用；on_step 回调实时推送事件）
# ------------------------------------------------------------

def run_loop(task_desc, bridge_url, max_steps=20, api_key=None, on_step=None,
             page_delay_min=2.0, page_delay_max=4.0, risk_check=True,
             cancel_requested=None, pause_requested=None, request_pause=None,
             confirm_requested=None, tab_id=None, dry_run=False, mock_llm=None):
    """
    执行一轮 agent 循环。

    Args:
        task_desc: 自然语言任务描述
        bridge_url: 桥接服务地址
        max_steps: 最大步数
        api_key: DeepSeek API key（None 则自动从 .env 读）
        on_step: 回调 fn(event: dict)，事件类型：start/snapshot/think/act/finish/error/step_limit
        page_delay_min/page_delay_max: 翻页间隔随机化（秒），click 动作成功后随机等待
        risk_check: 是否启用验证码/登录过期检测（默认 True）
        cancel_requested: P2-2 紧急停止——可选回调，返回 True 时在下一步开始前中止循环
                          （事件 cancelled + 返回 ok=False）
        pause_requested: P2-2 暂停/继续——可选回调，返回 True 时循环暂停（事件 paused），
                         等待恢复（事件 resumed）或紧急停止
        request_pause: P2-2 风控自动暂停——可选回调，调用后置 paused 标志；
                         risk_check 命中时自动暂停等人工（而非直接失败结束）
        confirm_requested: P3-T5 不可逆动作闸门——可选回调，返回 True 表示待人工确认。
                          LLM 决策输出不可逆动作（IRREVERSIBLE_ACTIONS）时：
                          发 confirm_requested 事件 → 若 confirm_requested() 为 True 则
                          阻塞等待（人工确认/取消后置 False）→ 确认后执行，取消则换策略
        dry_run: P3-T7 只读试跑模式——只执行只读动作（snapshot/scroll/extract/list_tabs/
                 verify_site），写动作（click/type/navigate 等）被拦截并回报 dry_run_blocked
                 事件（不实际执行）。用于新站/新任务先跑一遍看 LLM 决策，再放正式任务。
        mock_llm: P3-T7 mock LLM——可传一个 callable(history, api_key)->动作 JSON 字符串，
                 代替真实 LLM 调用（确定性测扩展链路/快照/提取/翻页，不花 API）。
        tab_id: P2-5 指定操作标签页——所有注入型动作固定作用于此标签（不依赖激活页）。
                 调度 Agent 派活时可用；多标签 LLM 任务（需切换标签）不要传。

    Returns:
        {"ok": bool, "summary": str, "data": dict, "steps": int}
    """
    if api_key is None:
        api_key = load_api_key()
    if not api_key:
        if on_step:
            on_step({"type": "error", "message": "未找到 DEEPSEEK_API_KEY（请设置环境变量或确认 browser-agent/.env 存在）"})
        return {"ok": False, "summary": "缺少 DEEPSEEK_API_KEY", "data": {}, "steps": 0}

    if on_step:
        on_step({"type": "start", "task": task_desc, "bridge": bridge_url, "model": MODEL})

    history = [{"role": "user", "content": f"我的任务：{task_desc}"}]
    steps_run = 0
    # P3-T3：无进展检测（G3 根因：LLM 连续多步只发 snapshot 原地打转耗尽 max_steps）。
    # 判定：连续 NO_PROGRESS_LIMIT 步"页面无实质变化 且 未执行任何实质动作"→ 卡死终止（事件 stuck）。
    # 实质变化 = URL 或元素数或累计数据行数变化；实质动作 = 非 snapshot 动作执行成功。
    NO_PROGRESS_LIMIT = 5
    _prev_sig = None
    _no_progress = 0
    _did_work = False  # 上一步是否执行了实质动作（成功）
    _last_act = None   # 上一步动作名（重复动作不算实质进展）
    # T4/P2-1：程序化累积提取结果——extract 每页 rows 自动追加（按行文本去重），
    # finish 时合并进 data（rows 原样保留 + candidates 按 SITE_HINTS 的 source_id 字段映射），
    # 不依赖 LLM 完整转述（P1 踩坑 #5：LLM 只转述 3 条丢 27 条）
    accumulated_rows = []
    extract_calls = 0
    last_url = ""
    knowledge_valid = True  # P2-4：站点基线检测失败（疑似改版）时降级为纯 LLM 推理
    # P4-V-T5：复杂交互（弹层）自动截图——每 run 至多一次（触发式，不每步拍）
    _panel_shot_done = False

    for step in range(1, max_steps + 1):
        # P2-2：紧急停止——每步开始前检查取消标志，命中立即中止并回报 cancelled 事件
        if cancel_requested and cancel_requested():
            msg = "任务已被手动取消（紧急停止）"
            if on_step:
                on_step({"type": "cancelled", "step": step, "message": msg})
            return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}
        # P2-2：暂停/继续——人工介入（验证码/重新登录）时暂停，等待恢复或紧急停止
        if pause_requested and pause_requested():
            if on_step:
                on_step({"type": "paused", "step": step,
                         "message": "任务已暂停，等待人工处理（验证码/重新登录后点继续恢复，或紧急停止终止）"})
            while pause_requested() and not (cancel_requested and cancel_requested()):
                time.sleep(1)
            if cancel_requested and cancel_requested():
                msg = "任务已被手动取消（紧急停止）"
                if on_step:
                    on_step({"type": "cancelled", "step": step, "message": msg})
                return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}
            if on_step:
                on_step({"type": "resumed", "step": step, "message": "已恢复运行"})
        steps_run = step
        # 1. 快照（P2-5：tab_id 钉住目标标签时，快照也作用于此标签，保证 LLM 看到的页面一致）
        _snap_params = {"tab_id": tab_id} if tab_id else None
        snap = submit_task(bridge_url, "snapshot", _snap_params, source="agent")
        if not snap["ok"]:
            msg = f"快照失败: {snap['error']}（桥接服务是否运行？扩展是否加载？是否有激活标签页？）"
            if on_step:
                on_step({"type": "error", "message": msg, "step": step})
            return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}
        snap_text = snapshot_to_text(snap["result"])
        last_url = snap["result"].get("url", "")
        if on_step:
            on_step({"type": "snapshot", "step": step, "title": snap["result"].get("title", ""),
                     "url": snap["result"].get("url", ""), "element_count": len(snap["result"].get("elements") or [])})

        # P3-T3：无进展检测——比较页面签名（URL + 元素数 + 累计数据行数），
        # 连续 N 步签名不变且未执行实质动作 → 卡死终止（G3：LLM 只发 snapshot 打转）
        _sig = (snap["result"].get("url", ""),
                len(snap["result"].get("elements") or []),
                len(accumulated_rows))
        if _prev_sig is not None:
            if _sig == _prev_sig and not _did_work:
                _no_progress += 1
            else:
                _no_progress = 0
        _prev_sig = _sig
        _did_work = False  # 本步动作执行后置 True（非 snapshot 动作成功）
        if _no_progress >= NO_PROGRESS_LIMIT:
            msg = (f"检测到连续 {_no_progress} 步无实质进展"
                   f"（页面 URL/元素数/数据均无变化，且未执行有效动作），判定卡死，已终止")
            if on_step:
                on_step({"type": "stuck", "step": step, "message": msg})
            return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}

        # T3：风控检测（快照后立即拦截，避免继续操作）
        if risk_check:
            blocked, reason = detect_risk(snap_text, snap["result"].get("url", ""),
                                          snap["result"].get("title", ""))
            if blocked:
                if request_pause:
                    # P2-2：风控命中 → 自动暂停等人工（继续走循环顶部的暂停等待逻辑），
                    # 人工处理（验证码/重新登录）后点继续恢复
                    if on_step:
                        on_step({"type": "risk_blocked", "step": step, "reason": reason,
                                 "message": "风控拦截，已自动暂停：请人工处理（验证码/重新登录）后点继续，或紧急停止终止"})
                    request_pause()
                    continue
                # 旧行为（无暂停能力时）：直接失败结束
                msg = f"⚠️ 风控拦截：{reason}。请转人工处理（验证登录态/验证码）。"
                if on_step:
                    on_step({"type": "risk_blocked", "step": step, "reason": reason})
                return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}

        # P4-V-T5：复杂交互（弹层/面板）自动截图——**页面正文**（body_preview，非标注行）
        # 命中弹层标志词时触发一次。⚠️ 不能用 snap_text（snapshot_to_text 可能自行追加
        # "弹层标注"行，其含"确认"字样会自触发误截图）。
        if not _panel_shot_done and re.search(
                r"请选择|已选\s*[（(]?\d|确认|确定|搜索城市|热门城市",
                snap["result"].get("body_preview") or ""):
            _shot = submit_task(bridge_url, "screenshot", _snap_params, source="agent")
            if _shot["ok"]:
                _panel_shot_done = True
                _sr = _shot.get("result") or {}
                if on_step:
                    on_step({"type": "screenshot_auto", "step": step,
                             "file": _sr.get("file"), "path_rel": _sr.get("path_rel"),
                             "desc": "检测到弹层/复杂交互，自动沉淀截图（V-T5）"})
                # P4 经验召回：疑似同类弹层 → 用刚截的图与经验沉淀的"面板参考截图"视觉对比，
                # 确认同类则注入上下文提示（按经验路径走，不重新探索）
                try:
                    from agent.experience import visual_confirm_same_layout as _vconf
                except ImportError:
                    from experience import visual_confirm_same_layout as _vconf
                _hit = None
                try:
                    for _ee, _ in kb.match_experiences(snap["result"].get("url", "")):
                        if not (_ee.get("screenshots")):
                            continue
                        _same, _detail = _vconf(bridge_url, tab_id, entry=_ee,
                                                current_path=_sr.get("path", ""), ref_kind="panel")
                        if _same is not None:
                            _hit = {"same_layout": _same, "detail": _detail, "entry_id": _ee.get("id")}
                            break
                except Exception as e:
                    _hit = None
                if _hit:
                    if on_step:
                        on_step({"type": "experience_hit" if _hit["same_layout"] else "experience_miss",
                                 "step": step, "detail": _hit["detail"], "entry_id": _hit["entry_id"],
                                 "message": (f"弹层与经验沉淀的同类弹层一致（{_hit['detail'][:100]}），按经验路径操作"
                                             if _hit["same_layout"]
                                             else f"弹层与经验沉淀不同类（{_hit['detail'][:100]}），需现场探索")})
                    if _hit["same_layout"]:
                        history.append({"role": "user", "content":
                            "（视觉确认：当前弹层与经验沉淀的同类弹层一致，属已知交互，按经验关键路径操作即可，无需重新探索）"})

        # P2-4：任务开始（第 1 步）做站点基线检测——命中知识库的站点才检查；
        # 结构不符（锚点/隐藏字段/分页缺失）→ site_changed 事件 + 本 run 降级不注入提示词
        # P4-V-T4：site_changed 触发时先做"记忆 vs 现实"视觉复核（当前截图 vs 沉淀截图），
        # 判定同类布局 → 疑似误报（锚点微调），不降级继续按知识库跑；判定不同 → 真改版降级。
        if step == 1:
            _dom, _entry = kb.match_knowledge(last_url)
            if _entry:
                _vparams = {"checks": kb.build_verify_checks(_entry)}
                if tab_id:
                    _vparams["tab_id"] = tab_id
                _vres = submit_task(bridge_url, "verify_site", _vparams, source="agent")
                if _vres["ok"]:
                    _vok, _vmissing = kb.summarize_verify(_vres["result"])
                    if _vok:
                        if on_step:
                            on_step({"type": "site_verified", "step": step, "domain": _dom,
                                     "version": _entry.get("version")})
                    else:
                        # V-T4：视觉复核——当前截图 vs 经验沉淀截图，判断是否同类布局
                        _visual = None
                        try:
                            from agent.experience import visual_confirm_same_layout
                        except ImportError:
                            from experience import visual_confirm_same_layout
                        try:
                            _exp_entry, _ = kb.match_experience(last_url)
                            if _exp_entry and tab_id:
                                _same, _detail = visual_confirm_same_layout(bridge_url, tab_id, entry=_exp_entry)
                                _visual = {"same_layout": _same, "detail": _detail}
                        except Exception as e:
                            _visual = {"same_layout": None, "detail": f"视觉复核异常: {e}"}
                        if _visual and _visual.get("same_layout"):
                            # 视觉判定同类布局 → 疑似误报（锚点微调），保留知识注入继续跑
                            if on_step:
                                on_step({"type": "site_changed", "step": step, "domain": _dom,
                                         "missing": _vmissing, "visual_check": _visual,
                                         "message": "站点结构与知识库基线不符，但视觉复核判定为同类布局（记忆 vs 现实对比），"
                                                    "疑似误报（锚点微调）：本任务继续按知识库运行，请择机核对知识库。"})
                        else:
                            knowledge_valid = False
                            if on_step:
                                on_step({"type": "site_changed", "step": step, "domain": _dom,
                                         "missing": _vmissing, "visual_check": _visual,
                                         "message": "站点结构与知识库基线不符，可能已改版：本任务降级为纯 LLM 现场推理，请核对后更新知识库。"})

        # 2. 推理（P2-1/P2-4：命中知识库且基线有效时，把站点知识注入 system 提示词；
        #    基线检测失败降级 → 不注入，纯 LLM 现场推理）
        hint, _sid = site_hint_for(snap["result"].get("url", ""))
        if not knowledge_valid:
            hint = None
        sys_prompt = SYSTEM_PROMPT + (f"\n\n【站点提示】{hint}" if hint else "")
        # P4-V-T3：经验 hint（按记忆走，少决策）——基线有效时注入已沉淀的关键路径/锚点/截图
        if knowledge_valid:
            try:
                from agent.experience import experience_hint_for as _exp_hint
            except ImportError:
                from experience import experience_hint_for as _exp_hint
            try:
                _eh = _exp_hint(snap["result"].get("url", ""))
            except Exception:
                _eh = ""
            if _eh:
                sys_prompt += f"\n\n{_eh}"
        messages = [{"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"{TOOL_DESC}\n\n当前快照：\n{snap_text}\n\n请决定下一步动作。"}]
        for h in history[-6:]:
            messages.append(h)
        try:
            if mock_llm is not None:
                # P3-T7：mock LLM——确定性返回，不调真实 API（测扩展链路用）
                raw = mock_llm(messages, api_key)
            else:
                raw = llm_chat(messages, api_key)
        except Exception as e:
            msg = f"LLM 调用失败: {e}"
            if on_step:
                on_step({"type": "error", "message": msg, "step": step})
            return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}
        action = parse_action(raw)
        if on_step:
            on_step({"type": "think", "step": step, "action": action, "raw": raw[:500]})

        # 3. 执行或收尾
        act = action.get("action", "snapshot")
        if act == "finish":
            summary = action.get("summary", "任务完成")
            data = dict(action.get("data") or {})
            # T4/P2-1：程序化合并累积的 rows——
            # ① data["rows"] 原样保留（通用形态，不丢数据）
            # ② data["candidates"] = LLM 给的 + 按 SITE_HINTS 声明的 source_id 字段从 rows 映射（去重）
            # P2-5：rows/candidates 携带采集页 url（candidates 入库时按行 url 落 site/url）
            if accumulated_rows:
                data["rows"] = accumulated_rows
                _hint, sid_field = site_hint_for(last_url)
                merged = list(data.get("candidates") or [])
                seen_ids = {str(c.get("source_id")) for c in merged if c.get("source_id")}
                for r in accumulated_rows:
                    sid = ""
                    if sid_field and (r.get("fields") or {}).get(sid_field):
                        sid = str(r["fields"][sid_field])
                    if sid and sid in seen_ids:
                        continue
                    merged.append({"raw_text": r.get("text", ""), "source_id": sid,
                                   "fields": r.get("fields", {}),
                                   "url": r.get("url", "") or last_url})
                    if sid:
                        seen_ids.add(sid)
                data["candidates"] = merged
                data["total_count"] = len(merged)
            data["url"] = last_url
            if on_step:
                on_step({"type": "finish", "step": step, "summary": summary, "data": data})
            return {"ok": True, "summary": summary, "data": data, "steps": steps_run}

        params = {}
        for k in ("index", "text", "occurrence", "direction", "amount", "url", "anchor_text", "tab_id"):
            if k in action and action[k] is not None:
                params[k] = action[k]
        if tab_id and "tab_id" not in params:
            # P2-5：run 级钉住目标标签（LLM 未指定 tab_id 时统一作用于此标签）
            params["tab_id"] = tab_id

        # P3-T7：只读试跑模式——写动作（click/type/navigate/new_tab/switch_tab/close_tab
        # 等非只读动作）一律拦截不执行（回报 dry_run_blocked 事件），只放行只读动作。
        if dry_run and action_level(act) != "readonly" and act not in ("finish", "snapshot"):
            if on_step:
                on_step({"type": "dry_run_blocked", "step": step, "action": act, "params": params,
                         "message": f"dry-run 模式：写动作 {act} 已拦截（不实际执行）。"
                                    f"只读试跑仅允许 snapshot/scroll/extract/list_tabs/verify_site。"})
            history.append({"role": "user", "content": f"dry-run 模式拦截了写动作 {act}（不执行）。"
                                                       f"这是只读试跑，请只输出只读动作或 finish。"})
            continue

        # P3-T5：不可逆动作闸门——对外产生永久影响的动作（发送/发布/删除等）
        # 默认需人工确认：发 confirm_requested 事件，阻塞等待确认/取消（类似 pause）。
        # 确认（confirm_requested() 变 False 且未取消）→ 继续执行；取消 → 换策略。
        if action_level(act) == "irreversible":
            if on_step:
                on_step({"type": "confirm_requested", "step": step, "action": act, "params": params,
                         "message": f"检测到不可逆动作 {act}（参数：{json.dumps(params, ensure_ascii=False)[:200]}），"
                                    f"需人工确认后才会执行。确认请调用确认接口，取消则本步跳过。"})
            if confirm_requested and confirm_requested():
                # 阻塞等待：确认接口把标志置 False（确认）或取消标志置 True（拒绝）
                while confirm_requested() and not (cancel_requested and cancel_requested()):
                    time.sleep(1)
                if cancel_requested and cancel_requested():
                    msg = "不可逆动作被取消（人工拒绝），任务已中止"
                    if on_step:
                        on_step({"type": "cancelled", "step": step, "message": msg})
                    return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}
                if on_step:
                    on_step({"type": "confirm_granted", "step": step, "action": act,
                             "message": f"人工已确认，执行不可逆动作 {act}"})
            else:
                # 无确认机制（未传 confirm_requested）→ 安全起见拒绝执行并提示
                if on_step:
                    on_step({"type": "confirm_denied", "step": step, "action": act,
                             "message": f"不可逆动作 {act} 未配置确认机制，已拒绝执行。请换策略（或由调度方配置确认接口）。"})
                history.append({"role": "user", "content": f"动作 {act} 是不可逆动作且未获人工确认，已拒绝执行。请换策略（不要再次输出 {act}）。"})
                continue

        if act == "snapshot":
            history.append({"role": "user", "content": "（上一步已快照，请基于快照直接决策）"})
            continue
        result, _attempts = execute_with_retry(bridge_url, act, params, on_step=on_step, step=step)
        if on_step:
            on_step({"type": "act", "step": step, "action": act, "params": params,
                     "ok": result["ok"], "result": result.get("result"), "error": result.get("error")})
        # P3-T3：本步是否算"实质进展"——非 snapshot 且与上一步动作不同的成功动作
        # （重复动作（如反复点同一按钮/重复 extract 同一页）不算进展）
        if result["ok"] and act != _last_act:
            _did_work = True
        _last_act = act
        if result["ok"]:
            # T4/P2-1：extract 结果只放结构化摘要（行数 + 新数据行数 + 第几次提取），
            # 完整数据由 accumulated_rows 程序化累积（按行文本去重），finish 时合并——P1 踩坑 #5
            if act == "extract":
                rows = (result.get("result") or {}).get("rows") or []
                extract_calls += 1
                _page_url = (result.get("result") or {}).get("url") or ""
                seen_text = {r.get("text", "") for r in accumulated_rows}
                new_rows = 0
                for r in rows:
                    if r.get("text") and r["text"] not in seen_text:
                        # P2-5：行内标注采集页 url（candidates 入库时按行 url 落 site/url）
                        accumulated_rows.append({"text": r["text"],
                                                 "fields": r.get("fields") or {},
                                                 "url": _page_url})
                        seen_text.add(r["text"])
                        new_rows += 1
                summary = (f"extract 成功（第 {extract_calls} 次提取，即第 {extract_calls} 页）："
                           f"本页提取 {len(rows)} 行，其中新数据 {new_rows} 行，"
                           f"累计 {len(accumulated_rows)} 行（去重）。"
                           f"若任务要求翻满 N 页：请将第 {extract_calls} 次与 N 比较，"
                           f"未满则点击分页区的'下一页'或页码数字翻页（'共 N 页'是信息不可点击）；"
                           f"已翻满或已是最后一页（无'下一页'）则 finish。")
                history.append({"role": "user", "content": summary})
            elif act == "list_tabs":
                # P2-3：list_tabs 结果 LLM 必须看全（标签数不多），用紧凑摘要，不走 400 字截断
                tabs = (result.get("result") or {}).get("tabs") or []
                parts = []
                for t in tabs:
                    mark = "（激活）" if t.get("active") else ""
                    parts.append(f"tab_id={t.get('tab_id')}({(t.get('title') or '')[:20]}{mark})")
                summary = f"list_tabs 成功：共 {len(tabs)} 个标签。" + ("；".join(parts))
                history.append({"role": "user", "content": summary})
            elif act == "screenshot":
                # P4-V-T1：截图成功 → 报告文件路径（视觉模型/人工查看用；截图不改变页面状态）
                _r = result.get("result") or {}
                summary = (f"screenshot 成功：已保存 {_r.get('path_rel') or _r.get('file', '')} "
                           f"（{_r.get('bytes', 0)} 字节）。截图是真实渲染的参考（布局/弹层/遮挡），"
                           f"DOM 快照仍是决策依据；截图不影响页面状态。")
                history.append({"role": "user", "content": summary})
            elif act == "som_shot":
                # P4-SOM：标注截图成功 → 报告文件路径 + 元素映射摘要（视觉模型看图选号用）
                _r = result.get("result") or {}
                _n = len(_r.get("elements") or [])
                summary = (f"som_shot 成功：已保存 {_r.get('path_rel') or _r.get('file', '')} "
                           f"（{_r.get('bytes', 0)} 字节，{_n} 个可点元素带视觉序编号徽标）。"
                           f"编号与快照同序（top→left），模型看图读编号即可，坐标由标注层 rect 负责；"
                           f"截图不影响页面状态。")
                history.append({"role": "user", "content": summary})
            else:
                history.append({"role": "user", "content": f"执行 {act} 成功：{json.dumps(result['result'], ensure_ascii=False)[:400]}"})
            # T3：翻页间隔随机化——click（翻页通常由 click 触发）成功后随机等待，防风控
            if act == "click" and page_delay_max > 0:
                time.sleep(random.uniform(page_delay_min, page_delay_max))
        else:
            history.append({"role": "user", "content": f"执行 {act} 失败：{result['error']}。请换策略（重新快照或改用其他动作）。"})
        time.sleep(0.5)

    msg = f"达到最大步数 {max_steps}，任务未完成"
    if on_step:
        on_step({"type": "step_limit", "message": msg, "steps": max_steps})
    return {"ok": False, "summary": msg, "data": {}, "steps": steps_run}
