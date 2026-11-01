#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_patch_recipes_20260920.py — 把"打招呼"相关页面写进配方表（老板 2026-09-20 要求）

为什么：配方表原来只有"找简历条件页"一个键；而打招呼要经过
  ① 候选人详情页 → ② 【请选择职位开聊】弹层 → ③ 详情页内的聊天面板 → ④ 职聊页（查看回复）
这三块今天全实测过（含坑），但**一个字都没进配方表**——下个对话又得重新踩。

写法：与现有页面**同一份文件、同一 schema**（page_name/note/updated_at/groups/behaviors/pending_items），
      每条都带 locate/action/verify/pits/status，证据来自 2026-09-20 实测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TARGET = Path(r"D:\study\bestagent\bridge-agent\agent\page_recipes.json")

DETAIL = {
    "page_name": "猎聘候选人详情页",
    "note": "打招呼链路的起点（**实测 2026-09-20**）。小猎先开详情页读简历 → 关掉 → 出报告 → 再从报告链接进来打招呼。",
    "updated_at": "2026-09-20 14:30",
    "groups": [
        {"id": "btn_chat", "name": "立即沟通 / 继续沟通", "type": "button(span 文本)",
         "locate": {"text": "立即沟通｜继续沟通", "pos": {"top_min": 290, "top_max": 330, "left_min": 90, "left_max": 160}},
         "action": "click_by_text '立即沟通'（occurrence=1）。⚠️ 别点同一行那 4 个无字 button（是图标位，点不动）",
         "options": "-",
         "verify": "点后**元素列表**出现「不选择职位开聊」= 弹层开了（⚠️ 不要用 body_preview 判断：它只截前 3000/8000 字，弹层文字在页面末尾）",
         "pits": ["**页面状态即事实**：显示「立即沟通」= 没打过（可打）；显示「继续沟通」= 已打过（跳过，别重复打）",
                  "点击后元素数会从 ~50 涨到 ~170（弹层+聊天面板展开），可用它做粗判"],
         "status": "confirmed"},
        {"id": "detail_open_close", "name": "开详情页 / 用完就关", "type": "tab",
         "action": "new_tab(url) → 干活 → close_tab(tab_id)",
         "options": "URL = https://h.liepin.com/resume/showresumedetail/?res_id_encode=<source_id>",
         "verify": "关掉后 list_tabs 里不再有它",
         "pits": ["老板口径：**采集时绝不点打招呼**；打招呼在报告出来之后、由报告链接进入",
                  "别堆标签页（历史事故：详情页从不关闭，浏览器堆一排）"],
         "status": "confirmed"},
        {"id": "chat_panel", "name": "聊天面板（发岗位介绍用）", "type": "textarea+button",
         "locate": {"textarea_placeholder": "请输入文字，按Enter键发送"},
         "action": "① 若面板没展开 → 点『继续沟通』展开；② type 到该 textarea；③ click_by_text '发送'",
         "options": "-",
         "verify": "① type 后回读 textarea 的 value 含所发文字首行；② 点发送后 textarea 清空 或 会话里出现该段",
         "pits": ["⚠️ **发送必须 click_by_text '发送'**；按几何猜按钮会点错（实测点错过两次，一次点到『索要简历』）",
                  "打招呼后聊天面板是**收起**状态，必须先点『继续沟通』才出现输入框",
                  "页面底部还有其它 textarea，**按 placeholder 选**（'请输入文字'）"],
         "status": "confirmed"},
    ],
    "behaviors": {
        "状态机": "页面按钮 = 打招呼状态：立即沟通(未打) ↔ 继续沟通(已打)。可用它跟本地台账对账。",
        "打招呼两步": "点『立即沟通』→ 弹层内点『不选择职位开聊』= 用平台默认短语发出（不带走岗位卡片）；"
                      "紧接着把『岗位介绍』打进聊天面板发出 —— 老板 2026-09-20 口径：**两段一起发**（岗位留在会话里，日后查回复时才对得上号）",
        "候选人端可见性": "候选人只看得到**最后一条消息的前 15 字**；多条消息的『红点条数』本身也是提醒（老板口径：被覆盖是好事）",
        "额度": "打招呼 50/天（发岗与否都占）；同一会话内再发**不占额度**；发岗上限 30 个（上新岗要下旧岗）",
    },
    "pending_items": [
        "打招呼是否受限（平台风控）：2026-09-20 曾误判为『平台挡住』，实为工具截断误判；**真人点击 vs 合成点击是否有差异，仍未证伪**（后续若再遇，先查 body_preview 长度与元素列表，别急着下结论）",
    ],
}

DIALOG = {
    "page_name": "打招呼弹层【请选择职位开聊】",
    "note": "详情页点『立即沟通』后的弹层（**实测 2026-09-20**）。两个出口：选岗位开聊 / 不选岗位开聊。",
    "updated_at": "2026-09-20 14:30",
    "groups": [
        {"id": "dlg_open", "name": "弹层出现判定", "type": "modal",
         "locate": {"text": "不选择职位开聊", "pos": {"top_min": 520, "top_max": 560, "left_min": 620, "left_max": 660, "width_min": 100, "width_max": 130}},
         "action": "点『立即沟通』后**轮询快照**（最多 16 秒），直到元素列表里出现「不选择职位开聊」",
         "options": "-",
         "verify": "元素文字命中「不选择职位开聊」（回退：几何 top≈536 left≈631 w≈114）",
         "pits": ["🔴 **绝不能用 body_preview 判断弹层**：它只截前 3000/8000 字，弹层文字在页面末尾 → 必然误判『没弹出来』（2026-09-20 假故障根因）",
                  "弹层里的打招呼语是平台『打招呼语库』里的一条；实测默认那条约 30 字，文字不一定进元素列表（别把它当硬门槛）"],
         "status": "confirmed"},
        {"id": "dlg_nojob", "name": "不选择职位开聊（老板选的路）", "type": "button(无字)",
         "locate": {"pos": {"top_min": 520, "top_max": 560, "left_min": 620, "left_max": 660}},
         "action": "click 该按钮（**没有文字，只能按几何找**）。点了**立即发出**默认短语，无二次确认",
         "options": "-",
         "verify": "点后页面按钮变「继续沟通」；元素列表里出现『继续沟通』",
         "pits": ["用默认短语（平台自动替换【示例】占位），**不带走岗位卡片** —— 老板 2026-09-20 口径：一般不带岗位打招呼（发岗有 30 上限）",
                  "⚠️ 禁止暴露 AI 身份（测试期口径）：默认短语不含 AI 字样，别自己加"],
         "status": "confirmed"},
        {"id": "dlg_job", "name": "选岗位开聊（实测过，暂不走）", "type": "select+button",
         "locate": {"combobox": {"top_min": 170, "top_max": 190, "width_min": 400}, "按钮『立即开聊』": {"top_min": 530, "top_max": 550, "left_min": 510, "left_max": 545}},
         "action": "开聊职位下拉选岗位 → 点『立即开聊』",
         "options": "该账号已发布的岗位",
         "verify": "发出的招呼语由**猎聘按岗位生成**（不是短语），例如：『你好，你的简历和某XX公司正在招的XX岗位很匹配，方便聊聊吗？』",
         "pits": ["老板口径：**这条路先不走**（发岗 30 上限、上新要下旧）",
                  "实测差异：选岗位那条**没有**『您可以修改打招呼语』提示；不选岗位那条有"],
         "status": "confirmed"},
    ],
    "behaviors": {
        "两条路的区别（实测）": "不选岗位 → 走『打招呼语』（可编辑短语，可在 im/mycommonlanguage?sayhi=true 里改/新增）；"
                               "选岗位 → 由猎聘按岗位生成，**和短语无关**",
        "打招呼语设置页": "https://h.liepin.com/im/mycommonlanguage?sayhi=true —— 有『中性/急切/轻松/自定义』与『按职位设置』两个签；自定义里可加一条（这是将来放『AI 助理』开场白的位置）",
    },
    "pending_items": [
        "弹层里能否当场改文字：未验（点『修改打招呼语』会跳到设置页）",
    ],
}

IM = {
    "page_name": "猎聘职聊页（查看回复）",
    "note": "**查看回复**的数据源（实测 2026-09-20）。会话列表 + 右侧会话详情，**全是文本，可完整读回**。",
    "updated_at": "2026-09-20 14:30",
    "groups": [
        {"id": "im_list", "name": "会话列表（谁、什么时候、最后一句）", "type": "list",
         "locate": {"url": "https://h.liepin.com/im/showmsgnewpage"},
         "action": "navigate + 等 4~8 秒（列表是异步渲染的，**第一次快照常常只有『未选中会话』**，要重拍）",
         "options": "顶部签：全部 / 新招呼 / 我发起的 / 我回复的 / 有简历 / 全部职位 / 未读",
         "verify": "读到『姓名 + 职位 + 时间 + 预览』；预览里 `[未读]/[已读]` 是**候选人是否点开**的信号",
         "pits": ["[已读]但没回 = 看过没兴趣/在犹豫 → 正是『换个说法再联系』的目标（老板 2026-09-20 口径：重发按天起步）",
                  "『您可以修改打招呼语，去修改＞＞』这行 = 我们发出去的是**短语**那条路；没有这行 = 走的选岗位（平台生成）",
                  "主动投递（海投）也在这里：预览是候选人自己写的（如『这是我的简历，合适的话可以随时联系我～』）→ 老板口径：**质量一般、优先级低，放到查看回复环节再讨论**"],
         "status": "confirmed"},
        {"id": "im_detail", "name": "会话详情（右侧面板）", "type": "panel",
         "locate": {"text": "沟通职位"},
         "action": "点会话行 → 读右侧：沟通职位 / 求职期望 / 消息流 / 输入框[发送]",
         "options": "-",
         "verify": "能看到『沟通职位:』与消息流（我们发的岗位介绍全文都在里面）",
         "pits": ["⚠️ 点会话行的 **span 可能不触发切换**（SPA 不响应）→ 需要更稳的定位方式（待补）",
                  "这一页的『发送』同理：输入框 = placeholder『请输入文字，按Enter键发送』"],
         "status": "partial"},
    ],
    "behaviors": {
        "回复判定": "[未读]→对方还没点开；[已读]→点开过；会话里出现**对方发的话**=真回复",
        "读的动作不会花钱": "整页读取 = 0 token（本地解析）",
    },
    "pending_items": [
        "右侧会话详情的稳定点击/读取方式（今天点 span 有时不切换）",
        "『有简历』『未读』筛选签的实际行为（未逐个验）",
        "主动投递（海投）的处理口径 —— 等老板在查看回复环节定",
    ],
}


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    d = json.loads(src)
    print(f"补丁目标：{TARGET}（{len(src)} 字符，现有页面 {len(d['pages'])} 个）")
    assert "pages" in d and isinstance(d["pages"], dict), "❌ 结构不对"
    before = len(d["pages"])
    d["pages"]["h.liepin.com/resume/showresumedetail"] = DETAIL
    d["pages"]["h.liepin.com/im/showmsgnewpage"] = IM
    d["pages"]["h.liepin.com 打招呼弹层（挂在详情页上）"] = DIALOG
    d["recipe_version"] = int(d.get("recipe_version") or 1) + 1
    d["note"] = (str(d.get("note") or "") +
                 " ｜ 2026-09-20 新增：候选人详情页 / 打招呼弹层 / 职聊页（查看回复）——打招呼链路的实测配方。")
    TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    d2 = json.loads(TARGET.read_text(encoding="utf-8"))
    print(f"  ✅ 页面数：{before} → {len(d2['pages'])}（recipe_version={d2['recipe_version']}）")
    for k in d2["pages"]:
        print("     ·", k)
    print("✅ JSON 可解析、写入完成")


if __name__ == "__main__":
    sys.exit(main())
