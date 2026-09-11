#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent/knowledge.py — 站点知识库（P2-4 结构化站点模板 + P3-T6 配置化）

知识库定位（D6）：关联网站的"轻量站点事实"（语义+锚点+验证基线），不是页面布局库；
快照=眼睛（现实）、知识库=经验（预期/语义）；按需沉淀。

**P3-T6 配置化**：站点条目从 `agent/knowledge_config.json` 加载（键为站点 key）——
加站点/改站点**不用改代码**，编辑 JSON + 重启桥即可。knowledge.py 内置一份默认
配置作为 JSON 缺失时的回退（首次运行会自动落一份 JSON 供编辑）。

每个站点条目（站点模板）：
    key                匹配键：域名（如 h.liepin.com，子域名同样命中）或 URL 路径特征
                       （如 h.liepin.com/search/getConditionItem，路径子串命中，优先于域名）
    version            知识库版本（网站结构变更时 +1，用于基线对照/改版记录）
    hint               注入 system 提示词的站点知识（锚点/字段/翻页/交互方式）
    source_id_field    该站点列表卡片的唯一 ID 字段名（程序化映射用，不依赖 LLM 转述）
    anchor             推荐的 extract 锚点文本
    verify             基线检测规则列表（改版检测）：全部命中 = 基线有效；
                       任一不命中 = 网站可能改版 → 降级为纯 LLM 推理 + site_changed 事件

verify 规则 type：
    text_anchor    页面文本节点包含 value（卡片锚点，如"立即沟通"）
    input_name     存在 input[name=value]（隐藏字段，如 res_id_encode）
    text           body.innerText 包含 value
    selector       querySelector(value) 命中

改版流程（机制化）：
    任务开始 → verify_site 检测 → 全部命中：正常注入 hint；
    有缺失 → on_step site_changed 事件（列出缺失项）+ 本 run 不再注入 hint（降级）
    → 人工核对后更新 JSON 配置（version+1、修正 verify/锚点/字段）。
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("KNOWLEDGE_CONFIG", os.path.join(HERE, "knowledge_config.json"))

# 内置默认（JSON 缺失时的回退；修改请编辑 knowledge_config.json）
_DEFAULT_CONFIG = {
    "sites": {
        "h.liepin.com": {
            "version": 1,
            "hint": ("猎聘诚猎通（h.liepin.com）提示：候选人列表每张卡片以\"立即沟通\"按钮收尾，"
                     "可用它做 extract 的 anchor_text；卡片内隐藏 input[name=res_id_encode] 的 value "
                     "即该候选人的唯一 source_id（extract 结果的 fields.res_id_encode 就是它，"
                     "请据此去重并统计 total_count）；翻页点击分页区的\"下一页\"或页码数字"
                     "（\"共/当前 N 页\"是信息，不可点击）。"),
            "source_id_field": "res_id_encode",
            "anchor": "立即沟通",
            "verify": [
                {"type": "text_anchor", "value": "立即沟通", "desc": "候选人卡片锚点（extract 依赖）"},
                {"type": "input_name", "value": "res_id_encode", "desc": "source_id 隐藏字段（去重/入库依赖）"},
                {"type": "selector", "value": ".pager-next, .next-page, [class*=\"next\"]", "desc": "分页控件（下一页）"},
            ],
        },
        "h.liepin.com/search/getConditionItem": {
            "version": 1,
            "hint": ("猎聘找简历条件页提示：本页是 React 动态页，每次点击后 DOM 重排、元素编号变化，"
                     "每步操作前必须先 snapshot 拿最新编号。① 城市设置：点击\"目前城市\"行后的\"其他\""
                     "打开城市选择面板（页面有多个\"其他\"，用快照编号或 click_by_text 的 occurrence 选对行）；"
                     "面板内元素按**视觉顺序编号**（P4-SOM：弹层居中，编号在列表中部区域，快照会标注弹层），"
                     "在\"热门城市\"区点击目标城市。"
                     "⚠️ 站点行为（P4 实测修正）：城市面板是**多选**面板——点城市只加入\"已选(x/9)\"，"
                     "**需点底部\"确认\"按钮才关闭面板并保存条件**（URL 加 #session）且**自动触发搜索**——"
                     "页面变成\"条件区+候选人列表\"混合态（顶部仍有条件区含\"工作年限/教育经历\"，"
                     "下方出现含\"立即沟通\"的候选人卡片）。"
                     "② 其他条件：工作年限/教育经历等选项是 label/span（如\"3-5年\"\"本科\"），"
                     "直接用编号或 click_by_text 点击。③ 搜索：点击顶部\"搜 索\"按钮（文本含空格）。"
                     "④ 若页面已自动出结果，验证条件生效后可直接 extract+finish。"),
            "source_id_field": "res_id_encode",
            "anchor": "立即沟通",
            "verify": [
                {"type": "text", "value": "工作年限", "desc": "条件区锚点"},
                {"type": "text", "value": "教育经历", "desc": "条件区锚点"},
                {"type": "text_anchor", "value": "搜 索", "desc": "搜索按钮"},
            ],
        },
    },
    # P4-V-T3~T5：经验条目（自动沉淀的"脑"）——{站点匹配键, 关键路径, 锚点, 关键截图, version, 置信度}
    "experience": [],
}


def _load_config():
    """从 JSON 加载站点知识；JSON 缺失/损坏时回退内置默认（并尝试落一份 JSON 供编辑）。"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            sites = cfg.get("sites") or {}
            if sites:
                return sites
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return _DEFAULT_CONFIG["sites"]


SITE_KNOWLEDGE = _load_config()

# P4-V-T3：配置热加载缓存——按 mtime 判断 JSON 是否变化，变化则重读。
# （经验沉淀运行中写回 JSON，同一进程后续 run 直接命中新经验，无需重启桥）
_config_cache = {"mtime": None, "cfg": None}


def _full_config():
    """读完整配置（sites + experience）；带 mtime 缓存，文件变更自动重读。"""
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        mtime = None
    if _config_cache["mtime"] == mtime and _config_cache["cfg"] is not None:
        return _config_cache["cfg"]
    cfg = _DEFAULT_CONFIG
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 仅当解析出的不是 dict 或缺 sites 键时才视为无效（空 sites 是合法配置）
            if not isinstance(cfg, dict) or not isinstance(cfg.get("sites"), dict):
                cfg = _DEFAULT_CONFIG
        except Exception:
            cfg = _DEFAULT_CONFIG
    # 结构兜底：sites/experience 键必须存在
    cfg.setdefault("sites", dict(_DEFAULT_CONFIG["sites"]))
    cfg.setdefault("experience", [])
    _config_cache["mtime"] = mtime
    _config_cache["cfg"] = cfg
    return cfg


def get_experience():
    """返回经验条目列表（P4-V-T3：knowledge_config.json 的 experience 数组）。"""
    return _full_config().get("experience") or []


def save_config(new_cfg):
    """把完整配置写回 JSON（经验沉淀用；写失败返回 False 不抛异常）。"""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(new_cfg, f, ensure_ascii=False, indent=2)
        _config_cache["mtime"] = os.path.getmtime(CONFIG_PATH)
        _config_cache["cfg"] = new_cfg
        return True
    except Exception:
        return False


def match_experiences(url):
    """按 URL 匹配**所有**经验条目（同站点可有多个关键路径条目）。

    Returns:
        list[(entry, index)]，按"路径子串 → 域名"两级匹配，各自按配置顺序。
    """
    try:
        from urllib.parse import urlparse
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        host = ""
    path = (url or "").split("?", 1)[0]
    exp = get_experience()
    out = []
    for i, e in enumerate(exp):
        key = e.get("site") or ""
        if "/" in key and key in path:
            out.append((e, i))
    for i, e in enumerate(exp):
        key = e.get("site") or ""
        if "/" in key:
            continue
        if host == key or host.endswith("." + key):
            if (e, i) not in out:
                out.append((e, i))
    return out


def match_experience(url):
    """按 URL 匹配经验条目（首个命中；多条目用 match_experiences）。"""
    out = match_experiences(url)
    return (out[0] if out else (None, None))


def match_knowledge(url):
    """按 URL 匹配知识库，返回 (site_key, entry) 或 (None, None)。

    匹配优先级：先按 URL 路径子串精确匹配（如条件页 /search/getConditionItem 的专用条目），
    未命中再按域名匹配（列表页通用条目）。配置热加载：JSON 变更（如经验沉淀）立即生效。
    """
    try:
        from urllib.parse import urlparse
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        host = ""
    path = (url or "").split("?", 1)[0]
    sites = _full_config().get("sites") or {}
    # 1) URL 路径子串匹配（条目 key 含 "/" 视为 URL 路径特征）
    for key, entry in sites.items():
        if "/" in key and key in path:
            return key, entry
    # 2) 域名匹配
    for domain, entry in sites.items():
        if "/" in domain:
            continue
        if host == domain or host.endswith("." + domain):
            return domain, entry
    return None, None


def build_verify_checks(entry):
    """从知识库条目构造 verify_site 动作的 checks 参数。"""
    return [{"type": r.get("type"), "value": r.get("value")} for r in (entry.get("verify") or [])]


def summarize_verify(verify_result):
    """解析 verify_site 返回，得到 (ok, missing_desc 列表)。

    verify_result: 扩展 zVerifySite 的返回 {ok(恒true), verified, checks:[{type,value,pass}], missing:[]}
    """
    checks = (verify_result or {}).get("checks") or []
    ok = bool((verify_result or {}).get("verified"))
    missing = []
    for c in checks:
        if not c.get("pass"):
            desc = c.get("value") or c.get("type")
            missing.append(f"{c.get('type')}={desc}")
    return ok, missing
