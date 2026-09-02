# 界面借鉴调研：主流 AI Agent 工作台界面模式（2024–2026）

> 归档：2026-09-02（M3 界面 v2 设计讨论素材 A，由后台调研 subagent 产出）
> 配套素材 B：`界面借鉴调研_猎头ATS与CRM.md`（同目录）

## 正文

**① 对话与结构化内容同屏组织**：主流是"左对话/右工作区"非对称分栏（ChatGPT/Claude 桌面端）——左侧对话列承载指令、确认与历史，报告/表格/产物渲染在右侧独立宽工作区，点消息即切换内容。Manus 走"任务=页面"：每个任务一个独立标签页，上为对话流、下为实时报告/文件，产物可单独新开。备选是 Tab 组织（Projects 模式）与画布+聊天。要点：报告与对话分区隔离即可，不必在同一流里混排。

**② 进度与"等人工确认"可视化**：两条线并行——顶部/侧边步骤条（Coze 节点流）给出全局到第几步、当前点高亮；Devin/Jules 用右侧活动时间线滚动播报每步动作。等待人工的状态统一做成醒目的琥珀/黄色"待批准"块，可点击直达、卡内直接 Approve/Edit（Cursor、n8n、Paperclip 同款）；审批作为异步节点不阻塞后续步骤。注意分级设审批点、支持批量通过，防"审批疲劳"。

**③ 指令→结果→纠错→重跑**：成熟形态是结果消息带**版本轮播箭头**（ChatGPT/Claude：◀▶ 在多版结果间切换、可回滚对比）；纠错落点=对话气泡——回复引用该条消息即修正，无需另开任务；Claude Code 式终端则每步完成后自动停下，等用户 Enter 继续或给修正指令。LukeW 主张把纠错**前置**：agent 先给"可编辑分步计划清单"，用户勾改某行再放行，优于事后改长报告。重跑粒度应到"单步骤"，勿整链重跑。

**④ 非程序员审阅的信息密度**：核心是"摘要卡→展开明细"两层——卡片首行只放结论句+2–3 个关键数字+状态徽标，表格/证据/明细折叠于"展开"（Manus/Perplexity 同款），忌全屏大表；顶部总步骤条给全局长图；每张卡固定操作位（采纳/纠错/放行）形成肌肉记忆；详情支持新标签打开便于对照。Manus 主界面只列"任务列表+摘要+入口"，细节一律另开页，防止老板被细节淹没。

## 模式清单

1. 对话+工作区分栏 | ChatGPT/Claude | 左窄对话列记指令，右宽工作区渲染表格/报告 | 报告与指令同屏分区，点消息即切换内容
2. 任务=独立页面 | Manus | 每任务一标签页，上对话下实时产物 | 多步业务"任务即页面"，切任务不丢上下文
3. 顶部总步骤条 | Coze 节点流 | 一行节点显示顺序与当前执行点，可点开 | 老板一眼看到第几步，点节点直达该步
4. 活动流水时间线 | Devin/Jules | 侧栏滚动播报 agent 每步动作，逐项可展开 | 用日志流替代长对话，扫读+按需介入
5. 待批状态高亮+审批卡 | n8n/Paperclip/Cursor | 流水线中"等待审批"节点琥珀色标出，卡内嵌确认/修改 | 卡住步骤醒目直达可批，别埋进滚动区
6. 版本轮播箭头 | ChatGPT/Claude | 结果消息带 ◀▶ 在多版间切换回滚 | 纠错后留上一版可对比，老板敢点"重跑"
7. 可编辑计划清单 | LukeW 模式 | agent 先产分步计划为勾选列表，可改某行再放行 | 把纠错从"改结果"前移到"改计划"
8. 摘要卡+展开明细 | Manus/Perplexity | 卡片先给结论+关键数，展开见表格与证据 | 先扫结论后查细节，压信息密度
9. 步骤级固定操作位 | Claude Code/Devin | 每步产出旁固定"继续/修改/中止"按钮组 | 采纳/纠错/放行设为每卡标配，降低学习成本
10. 分级审批+批量通过 | Skins Factory 建议 | 只对高风险步骤强制审批，低风险默认放行 | 全链每步都停会疲劳，审批点分级

## 来源 URL（均为搜索实际返回）

1. https://www.lukew.com/ff/entry.asp?2136 — LukeW: Agentic AI Interface Improvements
2. https://www.lukew.com/ff/entry.asp?2142 — LukeW: Showing the Work of Agents in UI
3. https://manus.im/docs/zh-cn/features/projects — Manus 官方文档（Projects/任务页）
4. https://cxhub.cn/post/pYUR8kM1FeCw22H9 — 当 AI 开始"动手干活"：Manus 界面设计
5. https://www.pingwest.com/a/308356 — 测 Manus 1.5（品玩）
6. https://developer.volcengine.com/articles/7447047229900554252 — Coze 工作流搭建介绍
7. https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools.md — n8n 人审（Human-in-the-loop）文档
8. https://github.com/paperclipai/paperclip/issues/762 — Pipeline-step approvals 审批点议题
9. https://github.com/daintreehq/daintree/pull/4008 — approval-waiting 状态差异化 UI
10. https://forum.cursor.com/t/waiting-for-approval-bug/149305 — Cursor "Waiting for approval" 状态
11. https://github.com/Windy3f3f3f3f/how-claude-code-works/blob/main/en/docs/12-user-experience.md — Claude Code 用户体验文档
12. https://aiuxplayground.com/pattern/regen-carousel/ — Regeneration Carousel 模式
13. https://www.aiuxplayground.com/pattern/status-steps/ — Progress Steps/状态步骤模式
14. https://dev.to/pickuma/devin-by-cognition-review-2026-is-the-autonomous-ai-engineer-worth-it-mbc — Devin 评测
15. https://www.theskinsfactory.com/uiux-design-questions-answers/how-do-you-design-human-in-the-loop-ai-without-creating-approval-fatigue — 审批疲劳设计讨论

**可信度说明**：GitHub Jules/Google 系产品未找到一手界面截图级资料，仅将其归入"活动时间线"一类（基于二手评测）；ChatGPT Canvas 具体布局仅靠社区截图帖佐证不足，正文以"桌面端分栏"通用形态表述，未虚构细节。
