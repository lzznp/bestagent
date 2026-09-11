# 交接包：P4 V-T1~V-T5（视觉 + 经验自学习）完成

> 生成时间：2026-08-23 ｜ 交接方式：P4 对话 → 后续对话
> 新对话开场：先读 `DESIGN-P4-VISION.md` → `HANDOFF-P3-COMPLETE.md` → 本文件 → 再读代码

---

## 0. 一句话状态

**V-T1（screenshot）✅、V-T2（视觉问答验证）✅、V-T3（经验沉淀）✅、V-T4（记忆vs现实）✅、V-T5（截图资产）✅ 全部完成并实测验证。** 三层架构（插件=手/视觉=眼/经验=脑）闭环跑通：成功任务自动沉淀经验库（version+1/历史保留/置信度闸门），二次任务按经验路径走（少决策），改版检测带视觉复核（误报识别）。

## 2. V-T1 实现明细

| 文件 | 改动 |
|---|---|
| `extension/background.js` | 新增 `zScreenshot(tabId)`：优先 `chrome.tabs.captureTab`（Chrome 126+，可截后台标签），失败回退 `captureVisibleTab`（目标非激活时临时激活→截图→恢复原激活标签）；注册进 TOOL_FUNCS + BACKGROUND_ACTIONS + executeOnTab 派发（screenshot 走后台型动作，传 params.tab_id） |
| `extension/manifest.json` | host_permissions 增加 `"<all_urls>"`——**captureVisibleTab/captureTab 硬性要求字面 `<all_urls>` 或 activeTab 权限**（仅 http/https 通配不够，实测报 "Either the '<all_urls>' or 'activeTab' permission is required"） |
| `bridge/server.py` | `SCREENSHOTS_DIR=logs/screenshots/`；TaskStore.finish 对 screenshot 任务把 data_url base64 落盘成 PNG，结果换成 `{ok, file, path(绝对), path_rel, bytes}`（JSONL/DB 不存 base64，防膨胀）；新增 `GET /screenshots/<file>` 静态服务 + `GET /api/screenshots` 清单 |
| `agent/core.py` | screenshot 进 SKILLS / SYSTEM_PROMPT / TOOL_DESC / `ACTION_LEVEL_READONLY`（只读动作，无需闸门）；run_loop 对 screenshot 成功回报文件路径（历史反馈） |

**V-T1 验收**：单步对猎聘条件页截图成功（captureVisibleTab，PNG 134KB/1428×1035，合法 PNG 头），落盘+静态服务+路径返回全通。

**踩坑**：
1. **权限**：captureVisibleTab 要字面 `<all_urls>` 或 activeTab；activeTab 只有用户点扩展图标才授予（轮询后台拿不到），只能加 `<all_urls>`。改 manifest 需重载扩展（用户操作 2 次：一次 manifest+js，一次 <all_urls> 追加后）。
2. **captureTab 对非激活标签实测失败**（Edge 147），走 captureVisibleTab 回退（会短暂切激活再恢复——截图目标标签会变激活页，恢复逻辑只恢复非目标标签）。
3. **bridge 曾存在双实例**（8080 双 LISTENING，P2-6 隐患复现）：已全杀后单实例重启（会话 job 拉起）。

## 3. V-T2 测试结果（用户真值验证）

测试闭环 = 截图 → 提问 `deepseek-v4-flash-vision-exp` → 快照对照 → **用户真值验证** → 数据表 `logs/vision_qa.jsonl`（5 条，均带 verdict）。

| 轮 | 场景 | 视觉模型读到（要点） | 快照对照 | 用户判定 |
|---|---|---|---|---|
| r1 | 条件页干净态（基线） | 布局（导航/二级标签/筛选卡/页脚）+ 全部条件选项与状态（目前/期望城市、年限、学历、年龄、活跃度、性别、跳槽频率、展开更多）+ 按钮位置 | DOM 199 元素逐项吻合 | **全部准确** |
| r2 | 城市弹层（点"其他"后，199→291 元素） | 标题"请选择城市"、国内/海外页签、左侧省份列表、右侧搜索框+历史浏览（深圳武汉杭州西安）+热门城市（14 城）、已选(0/9)、确认按钮、居中遮罩 | DOM 弹层元素逐项吻合（搜索框 200/省份 206-268/历史 269-272/热门 274-287/确认 289） | **全部准确** |
| r3 | 弹层选中态（点杭州后） | 已选 1 城=浙江·杭州（省·市格式）、显示在底部、计数变已选(1/9)、弹层未自动关（多选面板） | DOM 新增"浙江·杭州"chip（index 289） | **全部准确**（补充：搜索城市框可输入） |
| r4 | 混合态（点确认后，URL 加 #session，710 元素） | 条件区+候选人列表结构、杭州蓝色高亮+"杭州×"标签、首候选人 朱** 24岁 工作3年 大专 杭州-余杭区 求职杭州英语教师、共3000+位、立即沟通在卡片右上、视口内无翻页 | 与 DOM/正文一致；**公司名转写"乐弗思睿"vs DOM"乐菲思睿"错 1 字**（文字精度低于 DOM） | **全部准确** |
| r5 | SOM 元素清点（视觉顺序清点条件区） | 按视觉顺序列 58 个控件（搜索条→职位/公司名称→目前城市 9 项→清空筛选条件→期望城市→年限 6 项→学历 6 项→统招/院校/行业/职位→年龄/活跃度/性别/跳槽→展开更多→杭州×→保存条件） | 与 DOM 文档顺序**基本一致，仅 1 处系统差异**：清空筛选条件视觉在目前城市行右侧，DOM 顺序在其前 | **基本一致** |

## 4. V-T2 结论（视觉能力定位）

1. **强项**：布局理解、语义、**状态变化检测**（弹层开关、选中态/计数变化——这是"确认动作准确性/改版检测"的核心能力）；视觉顺序清点控件可行（58 个仅 1 处偏移）。
2. **弱项**：文本精确提取（公司名 1 字误差）→ **数据提取永远走 DOM**（对齐设计风险 #6）；长问题触发推理耗预算（r5 首跑 finish_reason=length 空 content，max_tokens 需给足 8000）。
3. **SOM（看图选编号）结论：有条件可行，需满足一个前提——标注层编号顺序与模型感知顺序一致**。当前 zSnapshot 按 DOM 文档顺序编号，与视觉顺序约 90% 一致（清空筛选条件等视觉右置元素会偏移）。若实施 SOM：标注层改为**视觉顺序编号**（top-left→bottom-right 排序）或给模型附编号映射表；浮层（弹层）元素建议单独编号段（现有"弹层尾部标注"机制可复用）。
4. **推荐定位（对齐设计 V2）**：视觉=侦察兵，用于布局确认、改版检测（V-T4 记忆vs现实）、弹层/选中态验证、异常发现；**不替代 DOM 编号决策**。
5. **顺带发现（知识库待修正，建议 V-T3 时改）**：猎聘条件页城市面板实际是**多选（已选 x/9）+点"确认"关闭并自动搜索（URL 加 #session）**；P3 knowledge_config.json 写的"选城市自动关面板、不用点确认"不准确（实测点城市只是加入已选）。

## 5. 测试基建（新文件）

| 文件 | 用途 |
|---|---|
| `agent/vision.py` | 视觉模型调用：`vision_chat(image, question, ...)`，OpenAI 兼容 + base64 data URL；**空 content 自动重试**（reasoning 模型偶发/推理耗光预算），max_tokens 默认 8000；模型名 `deepseek-v4-flash-vision-exp`（DeepSeek API Docs news260821 确认，官方 chat/completions 端点） |
| `vision_qa.py` | V-T2 测试驱动：截图→视觉问答→快照对照→写 `logs/vision_qa.jsonl`；`--verdict-by-label` 写回用户判定；`--show` 看数据表；`--tab-id` 缺省自动找猎聘标签 |
| `vt2_drive.py` | 中文动作参数驱动（写在 UTF-8 源文件内，**避免 PowerShell 命令行/Invoke-RestMethod 把中文变 `??`**） |

## 6. 环境备忘（当前状态）

- **浏览器**：猎聘标签 1890028341 停在**混合态**（条件页+杭州已选+3000+候选，URL 带 #session）；标签数 4（dsh GUI/edge://extensions/console/猎聘）；激活标签=猎聘（用户在核实时切的）
- **扩展**：manifest 已加 `<all_urls>`，已重载（用户操作）
- **bridge**：会话 job 拉起，单实例监听 8080（PID 27008）；server.py 已含截图落盘/静态服务
- **截图**：`logs/screenshots/`（8 张，数据表对应 5 张）；静态访问 `http://127.0.0.1:8080/screenshots/<file>`
- **数据表**：`logs/vision_qa.jsonl`（5 条全带 verdict）
- **API**：`DEEPSEEK_API_KEY` 在 .env（vision.py 复用 core.load_api_key）

## 7. V-T3~V-T5 实现明细（经验自学习闭环）

### 7.1 架构（对齐 DESIGN-P4 三层：插件=手/视觉=眼/经验=脑）

```
经验库（脑）      knowledge_config.json 的 experience 列表：{站点, 关键路径, 锚点, 关键截图, version, 置信度, path_key}
    │ 命中（按记忆走，少决策少截图）→ 注入【经验沉淀】hint
    ▼
agent 循环         快照 + 触发式截图（弹层自动截图）
    │ 记忆失效（锚点找不到 → site_changed + 视觉复核"当前 vs 沉淀截图"）
    ▼
重新探索 → 成功 → 自动沉淀（高置信写回，version+1；低置信只起草待人工，V7）
```

### 7.2 代码改动（V-T3~T5）

| 文件 | 改动 |
|---|---|
| `agent/experience.py`（新） | 经验沉淀核心：`draft_from_events`（事件流→条目：关键路径/锚点/截图/置信度）、`sink`（写回 JSON，version+1+history；**置信度闸门 V7**：低置信 auto 不写回，auto=False=人工放行；**path_key 区分同站点不同任务**，防互相覆盖）、`experience_hint_for`（命中注入，同站点多路径全注入）、`visual_confirm_same_layout`（V-T4：当前截图 vs 沉淀截图 → 视觉判定同类布局？）、`sink_after_run`（CLI/bridge 收尾调用） |
| `agent/knowledge.py` | **配置热加载**（mtime 缓存，改 JSON/沉淀即时生效无需重启桥）；`get_experience`/`save_config`/`match_experience(s)`（路径子串优先+域名兜底，多条目）；`_full_config` 空 sites 视为合法（修掉"空字典回退默认丢数据"的坑） |
| `agent/knowledge_config.json` | 站点知识：条件页 hint **修正**（V-T2 实测：城市面板=多选已选x/9 + 点确认关闭并自动搜索，#session；P3 写的"自动关面板不用确认"不准确）；`experience` 列表两条种子：城市面板路径（path_key click_by_text:其他）+ 提取路径（path_key extract:立即沟通） |
| `agent/core.py` | ① 经验 hint 注入 system 提示词（knowledge_valid 时）；② **site_changed 视觉复核**（V-T4）：verify 失败先做"当前 vs 沉淀截图"对比，同类布局→疑似误报不降级继续跑，不同→真改版降级；③ **弹层自动截图**（V-T5）：页面正文（body_preview）命中弹层标志词→自动截图一次（⚠️ 不能用 snap_text，标注行含"确认"会自触发）；④ 修正 snapshot_to_text 弹层正则 `筛选(?!条件)`（裸"筛选"误匹配"清空筛选条件"） |
| `bridge/server.py` | AgentRunner 收尾自动沉淀（成功任务 `sink_after_run`，事件 experience_sunk/draft）；run 端点支持 `sink:"false"` 关闭 |
| `agent/agent.py` | `--no-sink` 关闭沉淀；成功+非 mock/dry 才沉淀（mock/dry 不污染经验库） |
| `web/console.html` | 渲染 screenshot_auto/experience_sunk/experience_draft/site_changed 视觉复核结果 |
| `agent/vision.py` | 支持**多图对比**（list 输入，V-T4 需要） |
| `test_experience.py`（新） | 31 项单元测试全过（draft/sink/版本/历史/置信闸门/截图合并/锚点合并/path_key/多条目匹配/视觉 mock 三态） |

### 7.3 实测验证（真实浏览器 + 真实 LLM + 真实视觉 API）

1. **V-T3 二次命中少决策**：条件页任务（城市=杭州）跑 3 次，每次 **3 步动作完成**（点其他→选杭州→点确认→#session 出结果），LLM 决策理由直接引用经验路径，几乎零探索（P3 同类任务曾打转 13 步）。
2. **V-T3 自动沉淀**：成功任务自动写回 experience（v1 种子→v2→v3→v4 迭代，history 保留旧版）；**path_key 区分**：城市面板任务只更新 city 条目、extract 任务只更新 extract 条目（同站点两条独立经验）。
3. **V-T4 误报识别（Case A）**：临时加不存在的 verify 锚点 → site_changed 触发 → 视觉复核判定"同类布局（都是找人简历搜索页）" → **不降级**，任务继续按知识库跑完 ✅
4. **V-T4 真改版识别（Case B）**：参考=dsh GUI 工作台截图 vs 当前猎聘条件页 → 视觉判定"不同布局（AI 对话工作台 vs 招聘搜索页）" ✅
5. **V-T5 截图资产**：弹层打开时自动截图（修复"后台标签截图拿旧帧"：激活+等 200ms 再截），视觉确认截图内容=「请选择城市」面板；沉淀条目含截图资产（auto+manual 合并保留）；二次命中 hint 引用截图路径。
6. **bridge 路径闭环**：POST /api/agent/run 跑任务 → 事件流含 site_verified/experience_sunk → 控制台可见。

### 7.4 踩坑（新）

1. **后台标签截图拿旧帧**：captureVisibleTab 在"激活后台标签后立即截"会拿到切换前画面——必须 `await chrome.tabs.update(active)` 后等 ~200ms 再截。
2. **弹层正则自触发**：snapshot_to_text 的弹层标注行自身含"确认"，用它检测会自触发自动截图——改为只检查页面正文 body_preview；并修 `筛选(?!条件)`（"清空筛选条件"误报弹层）。
3. **经验条目互相覆盖**：按 site 合并会丢掉同站点不同任务的关键路径——引入 path_key（site+首个实质动作签名）区分。
4. **knowledge._full_config 空 sites 回退默认**：`sites={}` 被当无效配置整份丢弃（测试/清空配置时丢 experience）——改为仅缺 sites 键才算无效。
5. **PowerShell 传 JSON 给 --mock-llm 会坏引号**：单引号包裹的 JSON 里双引号被 PS 剥掉 → 回退真实 LLM（测试用 python 文件内嵌序列，见 test_dry_run.py 做法）。

## 8. 环境备忘（当前状态）

- **浏览器**：猎聘标签 1890028341 停在混合态（杭州已选+结果，URL #session）；标签 4 个；激活=猎聘（用户核对时切的）
- **扩展**：background.js 已含截图旧帧修复，已重载（用户操作，第 3 次）
- **bridge**：会话 job 单实例（server.py 含沉淀逻辑）；**经验/知识 JSON 热加载**，改配置无需重启桥
- **经验库**：`agent/knowledge_config.json` experience 2 条（城市面板 v2 + 提取 v1），history 保留旧版
- **截图**：`logs/screenshots/` ~14 张（含自动弹层截图）；静态服务 http://127.0.0.1:8080/screenshots/<file>
- **测试**：`python test_experience.py`（31 项）等 6 套全过；test_dry_run 的 tab_id 已更新为 1890028341
- **数据表**：`logs/vision_qa.jsonl`（V-T2 5 轮，全带用户判定）

## 9. 下一步建议

1. ~~**V-T3 收尾**：低置信起草的人工确认入口~~ → **已实现（见第 10 节 Feature A）**
2. ~~**经验召回增强**：弹层命中自动视觉对比~~ → **已实现（见第 10 节 Feature B）**
3. ~~**多站点推广**~~ → **已验证（见第 10 节 Feature C）**
4. 若做 SOM：标注层按视觉顺序编号（V-T2 结论）——需要单独设计轮（动 zSnapshot 编号顺序影响全部现有流）

## 10. 追加：经验人工闸门 + 经验召回 + 多站点（本轮）

### Feature A：低置信草稿人工确认入口（V7 第二道闸门）
- `agent/experience.py`：`save_draft`（草稿落 `logs/experience_drafts.jsonl`，draft_id=exp-时间戳-随机）、`list_drafts`、`approve_draft(draft_id, approve)`（确认→`sink(auto=False)` 人工放行写回 source=manual-approved；拒绝→status=rejected）；`sink_after_run` 增加 `draft_on_low`（低置信自动存草稿并在 reason 带 draft_id）
- `bridge/server.py`：`GET /api/experience/drafts?status=pending`、`POST /api/experience/confirm {draft_id, approve}`
- `web/console.html`：右侧新增"经验草稿（待人工确认）"面板，每条带 确认沉淀/拒绝 按钮；渲染 experience_hit/experience_miss 事件
- 实测：造草稿 → GET 列表 → POST 确认 → 经验库新增 source=manual-approved 条目 → 草稿状态 approved ✅（演示数据已清理）

### Feature B：经验召回增强（弹层命中自动视觉对比，V-T5 二次命中引用）
- `agent/experience.py`：`visual_confirm_same_layout` 支持 `current_path`（复用自动截图，不重复截）+ `ref_kind`（"layout" 改版复核优先常态参考 / "panel" 弹层命中优先面板参考）；新增 `_pick_ref_screenshot` 按 desc/type 关键词选参考图
- `agent/core.py`：弹层自动截图后，若 URL 命中经验条目且有截图 → 视觉对比当前弹层 vs 沉淀面板参考 → 事件 `experience_hit`/`experience_miss`；同类则注入上下文"按经验关键路径操作"
- 实测：城市面板任务 step2 弹层打开 → 自动截图 → 视觉判定"同类布局（same）"→ experience_hit → LLM 下一步理由写"**按经验关键路径**…关闭面板保存条件" ✅

### Feature C：多站点推广验证
- example.com（无知识库条目、无需登录）：任务成功后自动沉淀 → `example.com|navigate` 独立条目 v1（域名兜底匹配）✅——经验机制与站点无关，任何域可用

### 测试
- `test_experience.py` 扩到 **43 项全过**（新增：草稿保存/列表/确认/拒绝/重复确认报错/低置信自动存草稿/参考图选择 layout vs panel）
- 全量 6 套回归全过

### 环境备忘（本轮后）
- 经验库 3 条：城市面板 v3（6 截图）、提取 v1、example.com v1
- bridge 单实例（含 drafts API）；扩展无需再改（本轮无扩展改动）
- 草稿文件：`logs/experience_drafts.jsonl`（当前无 pending）

## 11. SOM（Set-of-Mark 看图选编号）——已完成并实测

### 11.1 实现
| 文件 | 改动 |
|---|---|
| `extension/background.js` | ①**视觉顺序编号**：zSnapshot/zClick/zType 统一按元素屏幕位置（top→left）排序编号（文档序兜底），编号=截图徽标编号；②**IoU>0.8 去重叠**（四副本同步：隐藏下拉堆叠/容器同点元素只留第一个）+ **零面积过滤**（width/height<4 隐藏项跳过）；③新增 `som_shot` 动作：激活→预热截图一帧→注入红色编号徽标（嵌入元素左上角，大字号+白边）→正式截图→清徽标，返回 {截图路径, elements:[{index,tag,name,rect}]}；④**唤醒修复**：后台标签可能被浏览器休眠（Edge Memory Saver），激活后 400ms+预热帧再截，否则拿到陈旧帧（v5 实测截图缺弹层）；som_shot 改为**先激活再注入**保证测量与截图同状态 |
| `agent/core.py` | som_shot 注册进 SKILLS/提示词/只读动作；弹层标注措辞改视觉序（"弹层元素在列表中部"替代"尾部高编号"） |
| `agent/knowledge.py` + `knowledge_config.json` | 条件页 hint 改"面板内元素按视觉顺序编号" |
| `bridge/server.py` | som_shot 结果同 screenshot 落盘（保留 elements 映射） |
| `vision_qa.py` | 新增 `--som` 模式：som_shot→视觉读编号→对照标注层映射→写 vision_qa.jsonl |

### 11.2 实测数据（真实视觉 API）
| 项 | 结果 |
|---|---|
| 视觉顺序编号 | ✅ 清空筛选条件=67 排在目前城市行选项（57-66）之后，与视觉感知一致（r5 偏移修复） |
| 顶部导航徽标读数 | ✅ 100% 正确（猎聘猎通=0/首页=1/沟通=2/找人=3/职位=4/猎头服务=5） |
| 确认按钮读数 | ✅ 154=映射 154（唤醒修复+去重叠后；修复前读成 204/210/227） |
| SOM 编号→点击直通 | ✅ click 154（确认）→ 弹层关闭 + URL#session + 候选人出现 |
| 密集小元素读数 | ❌ 不稳定：搜索城市 23vs28、热门杭州 58vs101（读数与映射不一致） |
| 截图含弹层 | ✅ 唤醒修复后稳定（v5 曾因休眠标签陈旧帧缺弹层） |

### 11.3 SOM 结论（V-T2 问题终答）
**"看图选编号"有条件可行，但不足以替代 DOM 定位**：
- **可靠**：大而清晰元素（导航、大按钮、输入框、稀疏城市块）——读数与标注层一致，编号→点击直通。
- **不可靠**：密集小元素区（弹层小城市块、小标签）——VLM 读数随机偏移 5~43，存在幻觉风险（曾读 227 而实际 199）。
- **定位**：SOM 作**粗粒度定位 + 视觉验证**（布局/状态确认、改版检测——V-T4 已用）；密集交互仍走 DOM（快照编号 + click_by_text）。若未来要用 SOM 做密集区精确点击，需裁剪子区域截图放大徽标（当前无 PIL，未做）。

### 11.4 SOM 踩坑（新）
1. **休眠标签陈旧帧**：后台标签被 Edge Memory Saver 冻结后，captureVisibleTab 可能返回激活前旧帧——激活后须 400ms 等待+预热截图一帧再正式截。
2. **JS 作用域**：`let injected` 声明在 try 块内、块外引用 → "injected is not defined"（且 catch 未置 ok=false 会返回半真结果）——错误处理一律置 ok=false。
3. **重叠三来源**：隐藏下拉堆叠（同 rect）、容器与子元素同点、密集小元素——IoU>0.8+零面积过滤解决前两类，第三类靠改徽标样式缓解。
4. 测试时序：som_shot 截图前必须确认页面状态（曾因回归任务关了弹层导致读数全错）。
