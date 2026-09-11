#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_experience.py — P4-V-T3/T4/T5 单元测试（经验沉淀/记忆vs现实/截图资产）

覆盖：
  1. draft_from_events：关键路径/锚点/截图提取；高置信 vs 低置信（重试/失败 → low）
  2. sink：create v1 → update v2+history；低置信 auto 不写回；force(auto=False) 写回
  3. hint_for_experience：含关键路径与截图引用
  4. match_experience：URL 路径子串 / 域名匹配
  5. visual_confirm_same_layout：mock 视觉（same/different/异常三态）

运行：python test_experience.py（脚本内已 reconfigure UTF-8）
"""
import base64
import os
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

# 用工作区内的临时配置（沙箱只允许写工作区），避免污染真实 knowledge_config.json
_TMPDIR = os.path.join(os.path.dirname(HERE), "logs", "_exp_test")
os.makedirs(_TMPDIR, exist_ok=True)
os.environ["KNOWLEDGE_CONFIG"] = os.path.join(_TMPDIR, "knowledge_config.json")
os.environ["EXPERIENCE_DRAFTS"] = os.path.join(_TMPDIR, "experience_drafts.jsonl")

import agent.knowledge as kb          # noqa: E402
import agent.experience as exp        # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def write_cfg(cfg):
    """写临时配置并重置 knowledge 缓存。"""
    with open(kb.CONFIG_PATH, "w", encoding="utf-8") as f:
        import json
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    kb._config_cache["mtime"] = None
    kb._config_cache["cfg"] = None


def make_events(ok_actions, extra=None):
    """构造事件流：快照 + 成功动作序列 + 可选异常事件。"""
    evs = [{"type": "snapshot", "url": "https://h.liepin.com/search/getConditionItem", "element_count": 199}]
    for a in ok_actions:
        evs.append({"type": "act", "action": a["action"], "params": a.get("params", {}), "ok": True})
    evs.extend(extra or [])
    return evs


def fake_png(path):
    """写一个 1x1 透明 PNG（仅占位，视觉对比被 mock）。"""
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    with open(path, "wb") as f:
        f.write(png)


def main():
    print("== 1. draft_from_events ==")
    clean_evs = make_events([
        {"action": "click_by_text", "params": {"text": "其他", "occurrence": 1}},
        {"action": "click", "params": {"index": 271}},
        {"action": "click_by_text", "params": {"text": "确认", "occurrence": 1}},
    ])
    d = exp.draft_from_events(clean_evs, {"ok": True}, url="https://h.liepin.com/search/getConditionItem")
    check("高置信 draft 生成", d is not None)
    check("key_path 3 步", d and len(d.get("key_path", [])) == 3, str(d and len(d.get("key_path", []))))
    check("置信度 high", d and d.get("confidence") == "high")
    check("锚点含 其他/确认", d and "其他" in d.get("anchors", []) and "确认" in d.get("anchors", []),
          str(d and d.get("anchors")))
    check("site 匹配键为条件页", d and d.get("site") == "h.liepin.com/search/getConditionItem", str(d and d.get("site")))
    check("path_key = 站点|click_by_text:其他", d and d.get("path_key") == "h.liepin.com/search/getConditionItem|click_by_text:其他",
          str(d and d.get("path_key")))

    retry_evs = make_events(
        [{"action": "click", "params": {"index": 5}}],
        extra=[{"type": "retry", "action": "click", "attempt": 2, "max_retries": 2, "error": "瞬时失败"}],
    )
    d2 = exp.draft_from_events(retry_evs, {"ok": True}, url="https://h.liepin.com/search/getConditionItem")
    check("有重试 → 低置信", d2 and d2.get("confidence") == "low", str(d2 and d2.get("confidence")))

    fail_evs = make_events([], extra=[{"type": "act", "action": "click", "params": {}, "ok": False}])
    d3 = exp.draft_from_events(fail_evs, {"ok": True}, url="https://h.liepin.com/search/getConditionItem")
    check("无成功动作 → 不可沉淀", d3 is None)

    # 截图提取（act screenshot + screenshot_auto）
    shot_evs = make_events([{"action": "click_by_text", "params": {"text": "其他"}}]) + [
        {"type": "screenshot_auto", "step": 2, "file": "a.png", "path_rel": "logs/screenshots/a.png", "desc": "弹层"},
    ]
    d4 = exp.draft_from_events(shot_evs, {"ok": True}, url="https://h.liepin.com/search/getConditionItem")
    check("截图资产提取", d4 and any(s.get("file") == "a.png" for s in d4.get("screenshots", [])),
          str(d4 and d4.get("screenshots")))

    print("== 2. sink（版本/历史/置信闸门）==")
    write_cfg({"sites": {}, "experience": []})
    entry = {"id": "e1", "site": "h.liepin.com/search/getConditionItem", "key_path": [],
             "confidence": "high", "source": "auto"}
    r1 = exp.sink(entry, auto=True)
    check("create v1 写回", r1["written"] and r1["entry"]["version"] == 1, r1.get("reason"))
    cfg = kb._full_config()
    check("配置含 1 条经验", len(cfg.get("experience", [])) == 1)

    entry2 = {"id": "e1", "site": "h.liepin.com/search/getConditionItem", "key_path": [],
              "confidence": "high", "source": "auto",
              "screenshots": [{"file": "new.png", "path_rel": "logs/screenshots/new.png"}],
              "anchors": ["新锚点"]}
    r2 = exp.sink(entry2, auto=True)
    check("同 id 更新 v2", r2["written"] and r2["entry"]["version"] == 2, r2.get("reason"))
    check("旧版入 history", len((r2["entry"].get("history") or [])) == 1)
    check("截图资产合并（新旧并存）", len(r2["entry"].get("screenshots", [])) == 1
          and r2["entry"]["screenshots"][0]["file"] == "new.png")
    # 再次更新：新截图 + 旧截图应并集
    entry3 = {"id": "e1", "site": "h.liepin.com/search/getConditionItem", "key_path": [],
              "confidence": "high", "source": "auto",
              "screenshots": [{"file": "old_a.png", "path_rel": "logs/screenshots/old_a.png"},
                              {"file": "old_b.png", "path_rel": "logs/screenshots/old_b.png"}]}
    r2b = exp.sink(entry3, auto=True)
    files = {s["file"] for s in r2b["entry"].get("screenshots", [])}
    check("再次更新截图并集（new/old_a/old_b）", files == {"new.png", "old_a.png", "old_b.png"}, str(files))
    check("锚点并集", "新锚点" in r2b["entry"].get("anchors", []))

    low_entry = {"id": "e2", "site": "other.example.com", "key_path": [],
                 "confidence": "low", "confidence_reasons": ["动作重试"], "source": "auto"}
    r3 = exp.sink(low_entry, auto=True)
    check("低置信 auto 不写回（V7）", not r3["written"], r3.get("reason"))
    cfg = kb._full_config()
    check("低置信未新增条目", len(cfg.get("experience", [])) == 1)

    r4 = exp.sink(low_entry, auto=False)
    check("人工放行(auto=False)写回", r4["written"], r4.get("reason"))
    cfg = kb._full_config()
    check("人工放行后 2 条", len(cfg.get("experience", [])) == 2)

    print("== 3. hint_for_experience ==")
    ent = {"key_path": [{"action": "click_by_text", "text": "其他", "desc": "按文本点击 \"其他\""}],
           "anchors": ["确认"], "screenshots": [{"path_rel": "logs/screenshots/a.png", "desc": "弹层"}]}
    h = exp.hint_for_experience(ent)
    check("hint 含关键路径", "关键路径" in h and "其他" in h)
    check("hint 含截图引用", "a.png" in h)

    print("== 4. match_experience / match_experiences ==")
    write_cfg({"sites": {}, "experience": [
        {"id": "x", "site": "h.liepin.com", "key_path": []},
        {"id": "y", "site": "h.liepin.com/search/getConditionItem", "path_key": "p1", "key_path": []},
        {"id": "z", "site": "h.liepin.com/search/getConditionItem", "path_key": "p2", "key_path": []},
    ]})
    e, i = kb.match_experience("https://h.liepin.com/search/getConditionItem#session")
    check("路径子串优先命中条件页", e and e["id"] == "y", str(e and e.get("id")))
    e2, i2 = kb.match_experience("https://h.liepin.com/im/showmsgnewpage")
    check("域名兜底命中 h.liepin.com", e2 and e2["id"] == "x", str(e2 and e2.get("id")))
    multi = kb.match_experiences("https://h.liepin.com/search/getConditionItem#session")
    check("match_experiences 返回 路径条目(y,z) + 域名条目(x)", len(multi) == 3,
          str([m[0].get("id") for m in multi]))

    print("== 4b. path_key 区分同站点多任务（sink）==")
    write_cfg({"sites": {}, "experience": []})
    ea = {"id": "a", "site": "h.liepin.com/search/getConditionItem", "path_key": "k|act:其他",
          "confidence": "high", "key_path": [{"action": "click_by_text", "text": "其他"}]}
    eb = {"id": "b", "site": "h.liepin.com/search/getConditionItem", "path_key": "k|extract:立即沟通",
          "confidence": "high", "key_path": [{"action": "extract", "anchor_text": "立即沟通"}]}
    ra = exp.sink(ea, auto=True)
    rb = exp.sink(eb, auto=True)
    check("同站点不同 path_key → 2 条独立条目", ra["written"] and rb["written"]
          and len(kb._full_config().get("experience", [])) == 2,
          str(len(kb._full_config().get("experience", []))))
    # 再次沉淀 path_key 相同的新 draft → 应更新 a 而非新建
    ea2 = dict(ea, key_path=[{"action": "click_by_text", "text": "其他", "desc": "v2"}])
    ra2 = exp.sink(ea2, auto=True)
    check("同 path_key 更新 v2（不新建）", ra2["written"] and ra2["entry"]["version"] == 2
          and len(kb._full_config().get("experience", [])) == 2, ra2.get("reason"))

    print("== 5. visual_confirm_same_layout（mock 视觉）==")
    ref_path = os.path.join(_TMPDIR, "ref.png")
    fake_png(ref_path)
    entry_v = {"screenshots": [{"path_rel": ref_path}]}

    exp.submit_task = lambda bridge, action, params, source="": (
        {"ok": True, "result": {"path": os.path.join(_TMPDIR, "cur.png")}} if action == "screenshot"
        else {"ok": False, "error": "unexpected"})
    exp.vision_chat = lambda images, q, **kw: "same, 都是筛选页布局"
    same, detail = exp.visual_confirm_same_layout("http://x", 1, entry=entry_v)
    check("视觉 same → 同类布局", same is True, detail)

    exp.vision_chat = lambda images, q, **kw: "different, 结构完全不同"
    same2, detail2 = exp.visual_confirm_same_layout("http://x", 1, entry=entry_v)
    check("视觉 different → 不同布局", same2 is False, detail2)

    exp.vision_chat = lambda images, q, **kw: "无法确定"
    same3, detail3 = exp.visual_confirm_same_layout("http://x", 1, entry=entry_v)
    check("无法解析 → None", same3 is None, detail3)

    exp.submit_task = lambda bridge, action, params, source="": {"ok": False, "error": "shot-fail"}
    same4, detail4 = exp.visual_confirm_same_layout("http://x", 1, entry=entry_v)
    check("截图失败 → None", same4 is None, detail4)

    # ref_kind 选择：panel 优先面板截图，layout 优先常态截图
    entry_multi = {"screenshots": [
        {"path_rel": "a.png", "desc": "条件页干净态（布局常态参考）"},
        {"path_rel": "b.png", "desc": "城市面板打开态"},
    ]}
    s_layout = exp._pick_ref_screenshot(entry_multi, ("干净", "常态", "布局"))
    check("layout 参考选常态图", s_layout and s_layout["path_rel"] == "a.png", str(s_layout))
    s_panel = exp._pick_ref_screenshot(entry_multi, ("面板", "弹层", "panel"))
    check("panel 参考选面板图", s_panel and s_panel["path_rel"] == "b.png", str(s_panel))

    print("== 6. 经验草稿（人工闸门）==")
    # 清空草稿文件
    if os.path.exists(exp._drafts_path()):
        os.remove(exp._drafts_path())
    write_cfg({"sites": {}, "experience": []})
    low = {"id": "d1", "site": "x.example.com", "path_key": "x.example.com|click:1",
           "confidence": "low", "confidence_reasons": ["动作重试"], "key_path": [{"action": "click", "index": 1}]}
    did = exp.save_draft(low, reason="低置信测试")
    check("保存草稿返回 draft_id", isinstance(did, str) and did.startswith("exp-"), str(did))
    drafts = exp.list_drafts()
    check("list_drafts 有 1 条 pending", len(drafts) == 1 and drafts[0]["status"] == "pending")
    # 确认沉淀 → 强制写回经验库
    res = exp.approve_draft(did, approve=True)
    check("确认沉淀 ok", res["ok"], str(res))
    cfg = kb._full_config()
    check("确认后经验库有 1 条（source=manual-approved）", len(cfg.get("experience", [])) == 1
          and cfg["experience"][0]["source"] == "manual-approved")
    check("草稿状态 approved", exp.list_drafts(status=None)[0]["status"] == "approved")
    # 拒绝路径
    did2 = exp.save_draft(low, reason="拒绝测试")
    res2 = exp.approve_draft(did2, approve=False)
    check("拒绝草稿 ok 且不入库", res2["ok"] and len(kb._full_config().get("experience", [])) == 1, str(res2))
    check("草稿状态 rejected", exp.list_drafts(status=None)[1]["status"] == "rejected")
    # 重复确认报错
    res3 = exp.approve_draft(did, approve=True)
    check("重复确认报错", not res3["ok"], str(res3))
    # 低置信 sink_after_run 自动存草稿
    write_cfg({"sites": {}, "experience": []})
    if os.path.exists(exp._drafts_path()):
        os.remove(exp._drafts_path())
    evs_low = make_events(
        [{"action": "click_by_text", "params": {"text": "选项"}}],
        extra=[{"type": "retry", "action": "click_by_text", "attempt": 2, "max_retries": 2, "error": "瞬时失败"}])
    sr = exp.sink_after_run(evs_low, {"ok": True}, url="https://x.example.com/page")
    check("低置信 sink_after_run 不写回但存草稿", sr and not sr["written"] and sr.get("draft_id"), str(sr))
    check("草稿文件新增", len(exp.list_drafts(status=None)) >= 1)

    print(f"\n结果：PASS={PASS} FAIL={FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
