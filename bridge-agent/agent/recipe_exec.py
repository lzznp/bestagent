#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recipe_exec.py — 配方执行器（B 计划执行骨架）

按 page_recipes.json 确定性设置找简历页条件：
- 输入：条件规格 [{group_id, value}, ...] + tab_id
- 每个条件：查配方 → 按 type 执行（input/chips/chips+panel/dropdown）→ 校验
- 全部设完 → 点'搜 索' → 等结果刷新 → 提取候选人（锚点'立即沟通'，res_id_encode 去重）
- 失败返回 {ok:false, group, error, step}，供上层归因（决策错→改规格；操作错→改配方；代码 bug→才改代码）

定位原则：全部文本定位（click_by_text），不按固定编号（页面元素数 139/141 波动）。
执行顺序原则：input/下拉先（保持页面干净，'不限' occ 映射有效）→ 城市面板（确认即搜）→ 即点即搜 chip 最后。
"""
import json
import os
import time

from agent.core import submit_task

BRIDGE = "http://127.0.0.1:8080"
RECIPES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page_recipes.json")
COND_URL = "https://h.liepin.com/search/getConditionItem"

WAIT_SHORT = 1.5
WAIT_MID = 2.5
WAIT_RESULTS = 8.0

# 执行顺序优先级：input 类=0 / dropdown/checkbox=1 / chips+panel=2 / chips=3（低的先执行，保 occ 映射）
TYPE_ORDER = {"input": 0, "input+dropdown": 0, "input×2": 0,
              "dropdown": 1, "checkbox": 1,
              "chips+panel": 2, "chips": 3}


def load_recipes(path=RECIPES_PATH, url=None):
    """加载配方表。schema2：多页面配方库。

    - 无 url → 返回默认页面配方 dict（含 groups/behaviors/pending_items），兼容旧调用。
    - 有 url → 按"URL 路径子串优先 → 域名兜底"匹配 pages（同 knowledge_config.json），
      命中返回对应页面配方；未命中返回默认页面配方（并带 _matched=None 标注）。
    返回 dict 顶层含 _recipes（完整库）、_page_key（命中的页面键）便于调用方判断。
    """
    with open(path, "r", encoding="utf-8") as f:
        recipes = json.load(f)
    if recipes.get("schema") != 2 or not isinstance(recipes.get("pages"), dict):
        # 兼容 schema1：单页结构直接当页面配方返回
        recipes = dict(recipes)
        recipes.setdefault("_page_key", recipes.get("page"))
        return recipes
    pages = recipes["pages"]
    default_key = recipes.get("default_page")
    # 没有 pages → 兜底返回一个空页面 dict
    if not pages:
        return {"groups": [], "behaviors": {}, "pending_items": [],
                "_recipes": recipes, "_page_key": None}
    # 匹配逻辑
    page_key = None
    if url:
        try:
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        path = url.split("?", 1)[0]
        # 1) URL 路径子串优先
        for k in pages:
            if "/" in k and k in path:
                page_key = k
                break
        # 2) 域名兜底
        if page_key is None:
            for k in pages:
                if "/" in k:
                    continue
                if host == k or host.endswith("." + k):
                    page_key = k
                    break
    if page_key is None:
        page_key = default_key if default_key in pages else next(iter(pages))
    page = dict(pages[page_key])
    page["_recipes"] = recipes
    page["_page_key"] = page_key
    return page


def _snap(tab_id):
    r = submit_task(BRIDGE, "snapshot", {"tab_id": tab_id}, source="recipe-exec")
    return r.get("result") or {}


def _cbt(tab_id, text, occ=1):
    return submit_task(BRIDGE, "click_by_text", {"tab_id": tab_id, "text": text, "occurrence": occ}, source="recipe-exec")


def _click(tab_id, index):
    return submit_task(BRIDGE, "click", {"tab_id": tab_id, "index": index}, source="recipe-exec")


def _type(tab_id, index, text):
    return submit_task(BRIDGE, "type", {"tab_id": tab_id, "index": index, "text": text}, source="recipe-exec")


def _selected_tag_in_body(body, value):
    """校验：已选标签区（'保存条件'前 200 字窗口）出现 value。找不到'保存条件'则退化为全文包含。"""
    idx = body.find("保存条件")
    if idx >= 0:
        return value in body[max(0, idx - 200):idx]
    return value in body


def find_input(tab_id, contains=None, pos=None):
    """按 name/placeholder 子串或位置找输入框编号。pos={top_min,top_max,min_width}"""
    s = _snap(tab_id)
    for e in (s.get("elements") or []):
        if e.get("tag") != "input":
            continue
        if contains and contains in (e.get("name") or ""):
            return e.get("index")
        if pos:
            r = e.get("rect") or {}
            top, w = r.get("top", 0), r.get("width", 0)
            if pos.get("top_min", 0) <= top <= pos.get("top_max", 99999) and w >= pos.get("min_width", 0):
                return e.get("index")
    return None


def find_input_value(tab_id, contains=None, pos=None):
    """找输入框当前值（校验用）。"""
    s = _snap(tab_id)
    for e in (s.get("elements") or []):
        if e.get("tag") != "input":
            continue
        if contains and contains in (e.get("name") or ""):
            return e.get("value") or ""
        if pos:
            r = e.get("rect") or {}
            top, w = r.get("top", 0), r.get("width", 0)
            if pos.get("top_min", 0) <= top <= pos.get("top_max", 99999) and w >= pos.get("min_width", 0):
                return e.get("value") or ""
    return None


# ---------------- 各类型执行 ----------------

def exec_input(tab_id, group, value):
    loc = group.get("locate") or {}
    contains = loc.get("input_contains") or None
    pos = loc.get("pos") or None
    idx = find_input(tab_id, contains=contains, pos=pos)
    if idx is None:
        return {"ok": False, "error": f"未找到输入框（contains={contains}, pos={pos}）"}
    r = _type(tab_id, idx, value)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    time.sleep(WAIT_SHORT)
    cur = find_input_value(tab_id, contains=contains, pos=pos)
    return {"ok": True, "verify": (cur == value), "input_value": cur}


def exec_chips(tab_id, group, value):
    ctm = (group.get("locate") or {}).get("click_text_map") or {}
    click_text = ctm.get(value, value)
    r = _cbt(tab_id, click_text, 1)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    time.sleep(WAIT_RESULTS)  # 即点即搜，等结果刷新
    body, _ = _body(tab_id)
    return {"ok": True, "verify": _selected_tag_in_body(body, value)}


def exec_city(tab_id, group, value):
    loc = group.get("locate") or {}
    other_occ = loc.get("other_occ", 1)
    r = _cbt(tab_id, "其他", other_occ)
    if not r.get("ok"):
        return {"ok": False, "error": f"点'其他'失败: {r.get('error')}"}
    time.sleep(WAIT_SHORT)
    idx = find_input(tab_id, loc.get("panel_input_contains", "搜索城市"))
    if idx is None:
        return {"ok": False, "error": "未找到城市面板搜索框"}
    r = _type(tab_id, idx, value)
    if not r.get("ok"):
        return {"ok": False, "error": f"输入城市失败: {r.get('error')}"}
    time.sleep(WAIT_SHORT)
    # 找过滤结果：输入框正下方（top 窗口内）name=value 的 span（排除 label chip）
    s = _snap(tab_id)
    input_rect = None
    for e in (s.get("elements") or []):
        if e.get("index") == idx:
            input_rect = e.get("rect") or {}
            break
    top0 = input_rect.get("top", 0)
    cand = None
    for e in (s.get("elements") or []):
        if e.get("tag") == "span" and e.get("name") == value:
            top = (e.get("rect") or {}).get("top", 0)
            if top0 and top > top0 and top < top0 + 300:
                cand = e
                break
    if cand is None:
        return {"ok": False, "error": f"未找到城市过滤结果（{value} span）"}
    r = _click(tab_id, cand.get("index"))
    if not r.get("ok"):
        return {"ok": False, "error": f"点过滤结果失败: {r.get('error')}"}
    time.sleep(WAIT_SHORT)
    r = _cbt(tab_id, "确认", 1)
    if not r.get("ok"):
        return {"ok": False, "error": f"点确认失败: {r.get('error')}"}
    time.sleep(WAIT_MID)
    body, s2 = _body(tab_id)
    url = s2.get("url") or ""
    return {"ok": True, "verify": ("#session" in url) and _selected_tag_in_body(body, value), "url": url}


def exec_dropdown(tab_id, group, value):
    loc = group.get("locate") or {}
    open_text = loc.get("open_text")
    open_occ = loc.get("open_occ", 1)
    if not open_text:
        return {"ok": False, "error": "配方缺少 open_text"}
    r = _cbt(tab_id, open_text, open_occ)
    if not r.get("ok"):
        return {"ok": False, "error": f"展开下拉失败: {r.get('error')}"}
    time.sleep(WAIT_SHORT)
    r = _cbt(tab_id, value, 1)
    if not r.get("ok"):
        return {"ok": False, "error": f"点选项失败: {r.get('error')}"}
    time.sleep(WAIT_MID)
    body, _ = _body(tab_id)
    return {"ok": True, "verify": _selected_tag_in_body(body, value)}


def exec_input_dropdown(tab_id, group, value):
    """input+dropdown：与 input 相同（按位置找输入框 type），下拉保持'全部'默认。"""
    return exec_input(tab_id, group, value)


def _parse_range(value):
    """'15-20万' / '15-20' / '不限' → (min, max) 或 None。"""
    if not value or "不限" in value:
        return None
    s = str(value).replace("万", "").replace("万元", "").strip()
    import re
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if len(nums) >= 2:
        return (nums[0], nums[1])
    if len(nums) == 1:
        return (nums[0], None)
    return None


def _find_pair_inputs(tab_id, pos):
    s = _snap(tab_id)
    inputs = []
    for e in (s.get("elements") or []):
        if e.get("tag") != "input":
            continue
        r = e.get("rect") or {}
        top, left = r.get("top", 0), r.get("left", 0)
        if pos.get("top_min", 0) <= top <= pos.get("top_max", 99999) and \
           pos.get("left_min", 0) <= left <= pos.get("left_max", 99999):
            inputs.append((e.get("index"), left))
    inputs.sort(key=lambda x: x[1])
    return inputs


def exec_input_pair(tab_id, group, value):
    """input×2：按 pair_pos 找两个输入框（左=min，右=max），type 起/止。
    ⚠️ React 重渲染：type 下限后 ant-select 重渲染编号漂移，上限必须重新快照再找。"""
    loc = group.get("locate") or {}
    pos = loc.get("pair_pos") or {}
    parsed = _parse_range(value)
    if parsed is None:
        return {"ok": True, "verify": True, "note": "值不限/无法解析，跳过"}
    inputs = _find_pair_inputs(tab_id, pos)
    if len(inputs) < 2:
        return {"ok": False, "error": f"找到 {len(inputs)} 个输入框（需要 2 个）"}
    r1 = _type(tab_id, inputs[0][0], parsed[0])
    if not r1.get("ok"):
        return {"ok": False, "error": f"输入下限失败: {r1.get('error')}"}
    time.sleep(WAIT_SHORT)
    if parsed[1]:
        # ⚠️ 重新快照找上限输入框（React 重渲染后编号已漂移）
        inputs2 = _find_pair_inputs(tab_id, pos)
        if len(inputs2) < 1:
            return {"ok": False, "error": "重新快照后找不到上限输入框"}
        # 上限 = 右侧那个（可能与下限同一索引，或新编号）
        max_idx = inputs2[-1][0]
        r2 = _type(tab_id, max_idx, parsed[1])
        if not r2.get("ok"):
            return {"ok": False, "error": f"输入上限失败: {r2.get('error')}"}
        time.sleep(WAIT_SHORT)
    return {"ok": True, "verify": True, "typed": parsed}


def exec_checkbox(tab_id, group, value):
    """checkbox：按 input name 找复选框并点击（切换）。"""
    loc = group.get("locate") or {}
    name = loc.get("checkbox_name")
    if not name:
        return {"ok": False, "error": "配方缺少 checkbox_name"}
    s = _snap(tab_id)
    idx = None
    for e in (s.get("elements") or []):
        if e.get("tag") == "input" and e.get("name") == name:
            idx = e.get("index")
            break
    if idx is None:
        return {"ok": False, "error": f"未找到复选框 {name}"}
    r = _click(tab_id, idx)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    time.sleep(WAIT_SHORT)
    return {"ok": True, "verify": True}


EXECUTORS = {
    "input": exec_input,
    "input+dropdown": exec_input_dropdown,
    "input×2": exec_input_pair,
    "chips": exec_chips,
    "chips+panel": exec_city,
    "dropdown": exec_dropdown,
    "checkbox": exec_checkbox,
}


def _body(tab_id):
    s = _snap(tab_id)
    return (s.get("body_preview") or ""), s


# ---------------- 主流程 ----------------

def execute_spec(spec, tab_id, do_search=True, do_extract=True, url=None):
    """spec: [{group_id, value}, ...]（自动按 TYPE_ORDER 排序执行）。
    url: 当前页面 URL，用于按 URL 匹配对应页面配方（None 用默认页）。"""
    recipes = load_recipes(url=url)
    groups = {g["id"]: g for g in recipes["groups"]}
    # 搜索按钮文本从配方 search 组读取（默认"搜 索"，兼容自定义）
    search_btn = "搜 索"
    sg = groups.get("search")
    if sg and sg.get("type") == "button":
        m = (sg.get("action") or "")
        import re as _re
        t = _re.search(r"click_by_text\s*'([^']+)'", m)
        if t:
            search_btn = t.group(1)
    _exec = {"_page_key": recipes.get("_page_key"), "_recipes": recipes.get("_recipes")}
    ordered = sorted(spec, key=lambda it: TYPE_ORDER.get(groups.get(it["group_id"], {}).get("type", 9), 9))
    steps = []
    for item in ordered:
        gid = item["group_id"]
        value = item["value"]
        group = groups.get(gid)
        if group is None:
            steps.append({"group_id": gid, "ok": False, "error": "配方中无此条件组"})
            return {"ok": False, "steps": steps, "failed": gid}
        gtype = group["type"]
        fn = EXECUTORS.get(gtype)
        if fn is None:
            steps.append({"group_id": gid, "ok": False, "error": f"不支持的类型 {gtype}"})
            return {"ok": False, "steps": steps, "failed": gid}
        res = fn(tab_id, group, value)
        step = {"group_id": gid, "value": value, "type": gtype, **res}
        steps.append(step)
        if not res.get("ok"):
            return {"ok": False, "steps": steps, "failed": gid, "error": res.get("error")}
    if do_search:
        r = _cbt(tab_id, search_btn, 1)
        steps.append({"action": "search", "ok": r.get("ok"),
                      "error": r.get("error") if not r.get("ok") else None})
        if not r.get("ok"):
            return {"ok": False, "steps": steps, "failed": "search", "error": r.get("error")}
        time.sleep(WAIT_RESULTS)
    result = {"ok": True, "steps": steps}
    result.update(_exec)
    if do_extract:
        ex = submit_task(BRIDGE, "extract", {"tab_id": tab_id, "anchor_text": "立即沟通"}, source="recipe-exec")
        if ex.get("ok"):
            rows = (ex.get("result") or {}).get("rows") or []
            sids = set()
            for row in rows:
                sid = (row.get("fields") or {}).get("res_id_encode")
                if sid:
                    sids.add(sid)
            result["candidates"] = len(rows)
            result["dedup"] = len(sids)
        else:
            result["extract_error"] = ex.get("error")
    return result


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    spec = [
        {"group_id": "keyword", "value": "嵌入式"},
        {"group_id": "city_current", "value": "青岛"},
        {"group_id": "city_expected", "value": "青岛"},
        {"group_id": "years", "value": "3-5年"},
        {"group_id": "school", "value": "985"},
        {"group_id": "activity", "value": "今天活跃"},
    ]
    tab = 1890028341
    submit_task(BRIDGE, "navigate", {"tab_id": tab, "url": COND_URL}, source="recipe-exec")
    time.sleep(2.5)
    res = execute_spec(spec, tab)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:4000])
