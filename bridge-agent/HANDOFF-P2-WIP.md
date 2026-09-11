# 交接包：browser-agent P2 阶段性完成 → 新对话（老师傅交接）

> 生成时间：2026-08-22 ｜ 交接方式：P2 实施对话（老师傅）→ 新对话（新徒弟）
> 新对话开场：**先读本文件** → 再读 `HANDOFF-P1-COMPLETE.md`（P1 状态与踩坑）→ `HANDOFF.md` + `DESIGN.md` → 再读代码
> ⚠️ 本文件是 P2 进行中的状态记忆，覆盖 P1 交接之后的全部进展。

---

## 1. 一句话状态

**P2 已完成的 5 项全部验证通过**：P2-1 插件去猎聘化（低风险部分 + 完整版通用 extract）、P2-2 人工介入（紧急停止 + 暂停/继续）、P2-3 多标签页管理（含 close_tab 场景闭环）、P2-4 站点知识库（含改版检测机制）、P2-6 bridge 去重。剩余：**P2-5 多 Agent 数据库桥（新对话任务，见第 9 节任务书）**。

## 2. P2 完成明细（对照验证结果）

| 任务 | 内容 | 验证结果 |
|---|---|---|
| P2-1 低风险 | manifest host_permissions 通用化（http/https *）；popup 移除测试按钮 | 扩展重载后快照回归 ✅ |
| P2-6 | agent.py ensure_bridge：端口被占但 health 失败时不重复拉起 | 代码级杜绝双进程 ✅ |
| P2-2 紧急停止 | core.py `cancel_requested` 回调（步边界中止）+ bridge `POST /api/agent/cancel` + popup「⛔紧急停止」 | 实弹测试：run 245e10f355 status=cancelled ✅ |
| P2-1 完整版 | 删 zExtractLiepin → 通用 `extract {anchor_text}`（返回 `{rows:[{text, fields:{name:value}}]}`，行内命名 input 自动成字段）；SITE_HINTS 站点知识注入 + 程序化字段映射 | 单步 30 行 res_id_encode 30/30 ✅；**T4 验收 run acf9081708：翻 3 页、total_count=90 去重正确、source_id 90/90 非空** ✅ |
| P2-4 知识库 | SITE_HINTS → `agent/knowledge.py` 结构化站点模板（version/hint/source_id_field/anchor/verify 基线规则）+ `verify_site` 内部动作 + 改版检测降级 | 快乐路径 site_verified ✅；模拟改版 site_changed + 降级纯 LLM 推理 ✅ |
| P2-2 暂停/继续 | core.py `pause_requested/request_pause`（risk_blocked 改自动暂停等人工）+ bridge `POST /api/agent/pause|resume` + popup「⏸暂停/▶继续」 | 单元测试 3 路径全过（手动暂停/风控自动暂停/暂停中紧急停止）；E2E run 0f1bb400ef：暂停→恢复→完成 total=87 ✅ |
| P2-3 多标签页 | 扩展新增后台型动作 `list_tabs`/`new_tab`/`switch_tab`/`close_tab`（chrome.tabs API，不注入页面）+ 注入型动作支持 `tab_id` 指定目标标签；core.py 工具面/规则 9/list_tabs 紧凑摘要（不走 400 字截断） | 单步全过：list_tabs 8 标签 ✅、switch_tab 后 snapshot 作用于目标 ✅、new_tab 新开激活 ✅、**close_tab 关闭（8→7）✅**、tab_id 指定注入（激活页≠目标页）✅、LLM 驱动任务正确汇报 8 标签+找简历 id ✅ |
| **场景闭环**（用户提出的通用场景：站内多页同标签 + 详情新标签用完即关） | ① 站内切换：navigate/click+快照（已实现）；② 新标签打开/切换：list_tabs/switch_tab/tab_id（已实现）；③ 用完关闭：**close_tab（本轮补上）** | 三个环节全部具备，通用（Boss直聘/智联/电商详情页同构）✅ |

## 3. 代码改动清单（P2 期间全部改动）

| 文件 | 改动 |
|---|---|
| `extension/background.js` | 删 zExtractLiepin → zExtract(anchor_text)（tr/li 优先行容器定位）；新增 zVerifySite(checks)（text_anchor/input_name/text/selector，**ok 恒 true、语义结果在 verified 字段**）；**P2-3 新增后台型动作 zListTabs/zNewTab/zSwitchTab（chrome.tabs API，BACKGROUND_ACTIONS 不走注入）+ pollOnce 支持 params.tab_id 指定目标标签**；TOOL_FUNCS: extract/verify_site/list_tabs/new_tab/switch_tab |
| `extension/manifest.json` | v0.2.0；host_permissions → http://*/* https://*/* |
| `extension/popup.html/js` | 产品化：连接状态 + 运行状态（含暂停态）+ ⏸暂停/▶继续 + ⛔紧急停止（二次点击确认） |
| `agent/core.py` | SYSTEM_PROMPT extract 工具说明 + 翻页规则 6/8 强化 + **P2-3 规则 9（多标签）**；分页标注区分可点导航与信息（共/当前/第 N 页不可点）；程序化累积 accumulated_rows（按行文本去重）+ finish 映射 candidates（source_id 按知识库字段）；SITE_HINTS→委托 knowledge.py；verify_site 基线检测（site_verified/site_changed 事件 + 降级不注入提示词）；P2-2 pause_requested/request_pause + risk_blocked 自动暂停；**P2-3 list_tabs 紧凑摘要（tab_id+短标题+激活标记，不走 400 字截断）+ params 透传 tab_id** |
| `agent/knowledge.py`（新） | 结构化站点知识库（h.liepin.com v1：hint/锚点"立即沟通"/res_id_encode/verify 规则）+ match/build_verify_checks/summarize_verify |
| `agent/agent.py` | P2-6：_bridge_port/_port_listening + ensure_bridge 端口占用检测 |
| `bridge/server.py` | AgentRunner.cancel/pause/resume（_find_running 复用）+ POST /api/agent/cancel|pause|resume；worker 传 cancel/pause 回调；list_recent 暴露 paused |
| `web/console.html` | 渲染 cancelled/site_verified/site_changed/paused/resumed 事件 + cancelled 徽章 |
| `README.md` | 工具面 extract、知识库说明、pause/resume 端点、目录 |
| `test_pause_logic.py`（新，可保留） | run_loop 暂停逻辑单元测试（fake bridge）：手动暂停/风控自动暂停/暂停中紧急停止 |

## 4. P2 踩坑/经验（新对话必读，含 P1 的仍有效）

1. **curl.exe argv 引号陷阱（新）**：Windows 上 curl.exe 的 argv 解析器处理真实双引号会坏——`ConvertTo-Json` 输出的 JSON 直接 `-d` 传给 curl 会解析为空（`task 不能为空`）。**提交 JSON 一律用 `Invoke-RestMethod` + `[System.Text.Encoding]::UTF8.GetBytes($json)`**。含 `\"` 转义的字符串给 curl 反而能工作（curl 会反转义），但别依赖。
2. **探测动作 vs 执行动作（新）**：verify_site 这类"探测"动作，校验失败是**有效结果**不是动作失败——返回 `ok` 恒 true、语义结果放独立字段（`verified`），否则扩展按失败上报 → bridge 标记 failed → agent 侧 `submit_task` 返回 ok=False → 结论被吞。
3. **行容器定位（新）**：锚点文本向上找卡片行，**tr/li 优先**，class 含 item/card 只兜底——否则"立即沟通"按钮外层的 op-item 之类小容器被误当整卡（30 行全是按钮文本）。
4. **LLM 翻页失败三种模式（新）**：① 不翻页重复 extract（extract×9）；② 误点"共 5 页"信息元素；③ 把"共 N 页"当任务要求翻过头。修复：分页标注区分可点/信息 + extract 摘要带"第 N 次提取/新数据行数" + 规则 6/8。**设计原则：关键状态（页码/新数据量）程序化喂给 LLM，别靠它自己数。**
5. **诚猎通分页控件**："下一页"是 aria-label/class 形式，**文本节点不含**——verify 规则用 selector `[class*="next"]`，不用 text/text_anchor。
6. **list_tabs 结果必须看全（新）**：动作结果进 history 的 400 字截断会砍掉大部分标签，LLM 只看到 1 个标签。list_tabs 用紧凑摘要（tab_id+短标题+激活标记），extract 用行数摘要——**凡是 LLM 决策需要的动作结果，不能走通用 400 字截断**。
7. **后台型 vs 注入型动作（新）**：chrome.tabs API 类动作（list_tabs/new_tab/switch_tab）在 background 直接执行（BACKGROUND_ACTIONS），不注入页面、不需要目标标签页；注入型动作才解析 tab_id/激活页。加新工具时先分清两类。
6. **P1 坑仍有效**：MV3 保活（alarms）；executeScript 注入函数必须自包含（新工具函数内联全部逻辑）；双 bridge（`netstat -ano | findstr :8080` 必须 1 个 LISTENING）；**跑任务期间保持猎聘页为激活标签页**（chrome:// 页无法注入——曾因刚重载扩展导致 chrome://extensions 是激活页而失败）；快照只列交互元素、正文预览列表页截 600 字。
7. **页面状态**：跑完翻页任务浏览器停在中间页，下轮测试前需人工点回第 1 页。

## 5. 已拍板的设计决策（P2 期间）

1. **视觉模型方案关闭**（用户实测：旧视觉模型能发现按钮但无法确定位置 → Playwright 需新开实例+大量选择器+难与 LLM 交互 → 插件方案是初衷）；验证码/登录归真人处理（detect_risk 检测特征词转人工即可，不引入视觉识别）。
2. **extract 契约（老师傅 P1 对话拍板）**：`{anchor_text}` → `{rows:[{text, fields}]}`；行内命名 input 自动成字段（通用 extract 不认识任何站点字段）；CSS path 方案后置；程序化累积模式保留（P1 踩坑 #5：LLM 只转述 3 条丢 27 条）。
3. **知识库 = 用户设计核心**：站点知识固化避免每次与 LLM 讨论；**改版→更新知识库已机制化**（verify_site 基线检测 → site_changed 事件 → 人工核对更新 knowledge.py，version+1）。
4. **多 Agent 通信（第 7 节问题 2）**：数据库表方案（任务表/数据表分离 + status 驱动轮询 + source_id 唯一约束）已分析合理，P2-5 直接按此做，不需要消息队列。

## 6. P2 剩余待办

| # | 任务 | 要点 |
|---|---|---|
| P2-5 | 多 Agent 数据库桥 | SQLite（标准库）替换 JSONL：tasks 表（指令+状态机）+ candidates 表（source_id 唯一约束）；**技能注册表**（GET /api/agent/skills，调度 Agent 查询技能后派活——用户"技能上报给 LLM"设计的多 Agent 化）；浏览器标签页现状：测试多标签时新开了 8 个标签（含 liepin 首页、新建标签页等），下轮可清理 |
| 收尾 | popup 新按钮视觉确认 | 需重载扩展后人工看（⏸暂停/▶继续 按钮） |

## 7. 运行环境备忘（当前状态）

- **桥接服务**：本会话以 job 方式拉起（当前 PID 见 netstat），**会话结束会停止**；下次用 `python agent/agent.py "任务"` 自动拉起（P2-6 保证不双开）
- **扩展**：最新版已加载；background.js 改动后需 chrome://extensions 重载；popup.js P2-2 改动**尚未重载验证视觉**（功能经 API E2E 验证）
- **浏览器**：激活标签页 = 猎聘诚猎通（已登录），翻页任务后停在中间页，测试前重置第 1 页
- **Agent**：`python agent/agent.py "任务" --max-steps N --page-delay-min 2 --page-delay-max 4 --risk-check on`
- **控制台**：http://127.0.0.1:8080/console
- **知识库**：`agent/knowledge.py`（h.liepin.com v1）；改版时更新并 version+1
- **logs/**：tasks.jsonl 持续增长（快照全量写入）；agent_runs/ 最新成功：acf9081708（T4 验收）、0f1bb400ef（暂停/恢复 E2E）
- **.env**：browser-agent/.env 已配 DEEPSEEK_API_KEY
- **测试**：`python test_pause_logic.py`（暂停逻辑单元测试，可复用）

## 8. P2 汇报（第 5 节格式，可转交设计对话）

```
P2 完成情况（进行中）：
1. 完成度：P2-1（低风险+完整版）✅ P2-2（紧急停止+暂停/继续）✅ P2-3（多标签页+close_tab 场景闭环）✅ P2-4 ✅ P2-6 ✅；P2-5 待做
2. 质量结论：能运行；T4 验收（翻 3 页+source_id+去重）通过；暂停/恢复 E2E 通过；知识库改版检测（快乐+降级）双路径通过；多标签（list/new/switch/close/tab_id 指定）单步+LLM 驱动全过
3. 与设计的偏差：无架构偏差；按老师傅契约实现 extract；知识库机制化为 verify_site 基线检测；多标签工具面按"后台型/注入型"两类实现
4. 下一步建议：P2-5 数据库桥（含技能注册表）——见第 9 节任务书，开新对话执行
```

---

## 9. 新对话任务书：P2-5 多 Agent 数据库桥（本对话到此交接，新对话开场读本文件 + 本任务书）

**目标**：让浏览器 Agent 的结果可被其他 Agent（调度/入库/查表）消费——SQLite 替换 JSONL 作为存储层，并提供技能注册表。

**任务清单**：
1. **SQLite 存储层**（Python 标准库 `sqlite3`，零第三方依赖，符合决策 #3/#6）：
   - `tasks` 表：任务链（id/action/params/status/source/created_at/picked_at/finished_at/result/error），status 状态机 pending→executing→done/failed/timeout（+ paused/cancelled 字段兼容 P2-2）——**status 驱动调度 Agent 轮询**
   - `candidates` 表：extract 结果（source_id **唯一约束**，ON CONFLICT IGNORE 防重复采集；raw_text/fields/site/url/created_at）
   - 保留 JSONL 作为审计日志（可选）或完全替换（建议：tasks 保留 JSONL 审计，candidates 入 SQLite；以设计对话偏好为准）
2. **数据写入路径**：agent finish 后 candidates 批量入库（source_id 去重）；任务记录入 tasks
3. **技能注册表**：`GET /api/agent/skills` 返回浏览器 agent 全部动作（snapshot/click/type/scroll/navigate/extract/list_tabs/new_tab/switch_tab/close_tab/verify_site + 参数 Schema）——**用户"技能上报给 LLM/调度者"设计的多 Agent 落地**；调度 Agent 先查技能再派活
4. **接口兼容**：现有 HTTP 接口（/api/task、/api/agent/run 等）不变，SQLite 是内部存储替换；控制台/CLI 不回归

**验收**：
- 一条完整任务：提交→扩展执行→结果入库 candidates（重复 source_id 不重复入库）
- `GET /api/agent/skills` 可查询完整技能面
- 快照/提取/翻页/暂停恢复/多标签 不回归（回归用控制台或 CLI）

**参考**：HANDOFF-P2-WIP.md 第 5 节决策 4（多 Agent 通信方案已拍板：任务表/数据表分离 + source_id 唯一约束 + 不需要消息队列）。

**环境备忘（新对话开局）**：netstat 确认 8080 唯一监听（无则 `python bridge/server.py` 或 `python agent/agent.py` 自动拉起）；扩展已加载最新版；猎聘页激活；浏览器现有 7 个标签页（含找简历/控制台/首页等，可清理）；知识库在 `agent/knowledge.py`。
