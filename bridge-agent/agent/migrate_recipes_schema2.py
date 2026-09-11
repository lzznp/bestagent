#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：page_recipes.json schema1(单页) → schema2(多页面配方库)。
把原有 page/groups/behaviors/pending_items 包进 pages[URL]。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = "agent/page_recipes.json"
d = json.load(open(SRC, encoding="utf-8"))

if d.get("schema") == 2:
    print("已是 schema2，跳过。")
    sys.exit(0)

url = d.get("page")
if not url:
    url = "h.liepin.com/search/getConditionItem"

page_obj = {
    "page_name": d.get("page_name", "猎聘找简历条件页"),
    "note": d.get("note", ""),
    "updated_at": d.get("updated_at", ""),
    "groups": d.get("groups", []),
    "behaviors": d.get("behaviors", {}),
    "pending_items": d.get("pending_items", []),
}

new = {
    "schema": 2,
    "recipe_version": 1,
    "default_page": url,
    "note": "配方表 schema2：多页面配方库。pages 按 URL 键组织，匹配规则同 knowledge_config.json（路径子串优先→域名兜底）。load_recipes(url) 按 URL 取对应页面配方。",
    "pages": {url: page_obj},
}

with open(SRC, "w", encoding="utf-8") as f:
    json.dump(new, f, ensure_ascii=False, indent=2)

print(f"迁移完成 → schema2，pages 键: {list(new['pages'].keys())}")
print(f"groups: {len(page_obj['groups'])}，behaviors: {len(page_obj['behaviors'])}，pending_items: {len(page_obj['pending_items'])}")
