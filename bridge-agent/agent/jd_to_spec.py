#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jd_to_spec.py — LLM 决策层：JD → 搜索条件规格

LLM 只做"读 JD 出条件"的决策，输出 [{group_id, value}]；
value 必须从配方表 options 里选（防 LLM 发明不存在的值）。
执行（浏览器操作）由 recipe_exec 确定性完成，LLM 不碰浏览器。
"""
import json
import os
import re

from agent.core import llm_chat, load_api_key
from agent.recipe_exec import load_recipes

SPEC_PROMPT = """你是猎头搜索条件生成器。根据 JD 生成猎聘"找简历"页的搜索条件规格。

可用条件组及合法取值（只能从这里选，严禁发明不存在的值；未列出的条件组不要输出）：
{groups}

规则：
1. 只输出 JD 明确要求的条件；JD 未提及的条件不输出（保持默认不限）。
2. keyword 写 1 个最通用的核心技能/方向词（如"嵌入式"、"C语言"），**不要用精确职位名**（如"MCU固件开发"）——精确职位名会导致搜索结果过少；JD 有明确技能方向时提取技能词，否则不输出。
3. 城市类（city_current/city_expected）可输出任意城市名，JD 写明工作城市时输出该城市。
4. 只输出 JSON 数组，不要 markdown 代码块标记和解释文字，格式：[{{"group_id": "...", "value": "..."}}]

JD：
{jd}"""


def build_groups_text(recipes):
    lines = []
    for g in recipes["groups"]:
        if g.get("status") != "confirmed":
            continue  # 只给已实测确认、执行器支持的组，防 LLM 选 pending 控件
        opts = g.get("options")
        if isinstance(opts, list):
            o = " / ".join(str(x) for x in opts)
        elif isinstance(opts, str):
            o = opts
        else:
            continue
        lines.append(f"- {g['id']}（{g['name']}）: {o}")
    return "\n".join(lines)


def jd_to_spec(jd, api_key=None, recipes=None, url=None):
    """JD 文本 → {ok, spec:[{group_id,value}], raw}。spec 已校验 group_id 合法。
    url: 目标页面 URL，用于按 URL 取对应页面的配方 options（None 用默认页）。"""
    recipes = recipes or load_recipes(url=url)
    prompt = SPEC_PROMPT.format(groups=build_groups_text(recipes), jd=jd)
    key = api_key or load_api_key()
    raw = llm_chat([{"role": "user", "content": prompt}], key)
    raw = (raw or "").strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        raw = m.group(0)
    try:
        spec = json.loads(raw)
    except Exception as e:
        return {"ok": False, "error": f"LLM 输出解析失败: {e}", "raw": raw[:500]}
    if not isinstance(spec, list):
        return {"ok": False, "error": "LLM 输出不是数组", "raw": raw[:500]}
    valid = {g["id"] for g in recipes["groups"]}
    bad = [s for s in spec if not isinstance(s, dict) or s.get("group_id") not in valid]
    if bad:
        return {"ok": False, "error": f"非法 group_id: {bad}", "raw": raw[:500]}
    # 过滤：① 空 value（如 button 类被误当条件输出 value=""）② 非执行器支持的 type（button 等）
    from agent.recipe_exec import EXECUTORS
    exec_supported = {g["id"] for g in recipes["groups"] if g.get("type") in EXECUTORS}
    cleaned = [s for s in spec
               if isinstance(s, dict) and (s.get("value") not in (None, "", []))
               and s.get("group_id") in exec_supported]
    return {"ok": True, "spec": cleaned, "raw": raw}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    jd = open("logs/jd_goertek.txt", encoding="utf-8").read()
    r = jd_to_spec(jd)
    print(json.dumps(r, ensure_ascii=False, indent=1)[:1500])
