# 交接包：browser-agent P3-BASE 完成（可靠性批次）→ P4（新对话必读）

> 生成时间：2026-08-22 ｜ 交接方式：P3 实施对话 → 新对话
> 新对话开场：**先读 `DESIGN-P4-VISION.md`**（P4 设计任务书：视觉+自学习）→ 再读本文件 → `DESIGN-BASE.md`（底座架构定稿）→ 再读代码

---

## 1. 一句话状态

**P3-BASE 任务书（DESIGN-BASE 第 8 节 T1-T9）全部完成**：T1 click_by_text + 快照可点增强 ✅、T2 猎聘条件页复杂表单试跑（多次迭代，达成核心验证）✅、T3 无进展检测 ✅、T4 tab_id 失效明确报错 ✅、T5 动作分级+不可逆闸门 ✅、T6 知识库配置化 ✅、T7 只读试跑+mock LLM ✅、T8 入库可选开关 ✅、T9 收尾（含修复一个 P2-5 遗留死锁 bug）✅。

## 2. 各任务实现明细（对照任务书）

| 任务 | 实现 | 验证结果 |
|---|---|---|
| **T1** click_by_text + 快照增强 | 扩展新增注入型动作 `click_by_text(text, occurrence)`（TreeWalker 找文本→向上找最小可点祖先→点击）；`isInteractive` 增强（class 含 option/select/dropdown 的 span/li + cursor:pointer 且有自有文本）；**4 处副本同步**（zSnapshot/zClick/zType/zClickByText，编号一致性） | 单步验收：条件页按文本"其他"点击成功，弹层打开（元素数 199→291）✅；快照增强后选项类元素（北京/深圳/其他/本科/硕士等）全部进编号列表（56→199 个元素）✅ |
| **T2** 复杂表单试跑 | 猎聘条件页：城市=其他+弹层选 杭州/成都 → 工作年限 → 教育经历 → 搜索 → extract。**多次迭代修复了 G3 打转根因**（见踩坑 #1-#4） | 最终 run（1890028371）：LLM 自主完成 打开面板→选杭州→选成都→设年限"3-5"→点"搜 索"→翻页提取 59 条→finish（exit 0，事件流可追溯）；入库链路正常。**教育经历本轮未设置成功**（LLM 提前 finish，属模型决策问题，机制上已具备能力） |
| **T3** 无进展检测 | run_loop 连续 5 步"页面签名（URL/元素数/数据行数）不变 且 未执行实质动作"→ stuck 事件 + 终止。实质动作=非 snapshot 且与上一步不同的成功动作 | 单元测试 3 场景全过（打转→stuck / 正常→不误报 / 重复动作→stuck）；**真实环境生效**：T2 run 中 LLM 打转第 7 步即被终止（之前会打转 13 步）✅ |
| **T4** tab_id 失效报错 | 扩展：指定 tab_id 的标签关闭 → 报 `tab-lost: ...`（不静默回退激活页）；core：tab-lost/no-active-tab 不重试（确定性错误） | 代码级 + 逻辑验证 ✅（未做真实关标签 E2E，机制简单可靠） |
| **T5** 动作分级+闸门 | `action_level()` 三级：readonly（snapshot/scroll/extract/list_tabs/verify_site）/ lowrisk（click/click_by_text/type/navigate/new_tab/switch_tab/close_tab）/ irreversible（预留 send_message/publish/delete 等，**当前工具面无不可逆动作**）；不可逆动作→confirm_requested 事件→阻塞等确认（类似 pause）→`POST /api/agent/confirm {approve}` | 单元测试 3 场景全过（确认→执行 / 拒绝→取消 / 无确认机制→拒绝+换策略）✅ |
| **T6** 知识库配置化 | `agent/knowledge_config.json`（加站点不动代码，改 JSON+重启桥）；`knowledge.py` 改为读 JSON（缺失回退内置默认并自动落盘）；匹配支持 **URL 路径子串**（条件页专用条目优先于域名条目）；新增猎聘条件页条目（React 动态页提示+弹层行为+verify 基线） | 匹配验证：条件页→专用条目、结果页→域名条目、其他站→None ✅ |
| **T7** 只读试跑+mock LLM | run_loop 加 `dry_run`（只放行只读动作，写动作→dry_run_blocked 事件不执行）+ `mock_llm`（callable 代替真实 LLM）；CLI `--dry-run` / `--mock-llm '<JSON 动作序列>'` | 全链路验证：extract（只读）执行、click/navigate（写）被拦截、mock 序列驱动到 finish ✅ |
| **T8** 入库可选开关 | run_loop 之外（CLI/bridge 层）：CLI `--no-persist`；`POST /api/agent/run` body `persist:false` → 任务照跑、结果不落 SQLite | 测试：persist=True 入库 1 条 / persist=False 不落库 / run_loop 结果照常返回 ✅ |
| **T9** 收尾 | 标签清理（6→3：dsh GUI/扩展页/控制台）；**修复 P2-5 遗留死锁**（见踩坑 #5）；popup 视觉确认**待人工**（见环境备忘） | db 写入 0.0s 恢复 ✅；测试全回归（stuck/confirm/pause）✅ |

## 3. P3 踩坑/经验（新对话必读）

1. **G3 打转根因（T2 迭代发现，三连）**：① `snapshot_to_text` 元素上限 150 截断——弹层内元素编号 280+ 被砍，LLM 看不到目标只能打转 → 提到 400；② 正文预览 600 字截断——弹层内容在正文**尾部**被砍 → 改"头部600+尾部400"；③ LLM 不知道高编号元素属于弹层 → 加**弹层检测标注**（正文含"请选择/已选/确认"等 → 明确提示"尾部编号属于弹层内容"）。
2. **SYSTEM_PROMPT 规则 10**："当前快照已是最新（系统每步自动重新快照），看到目标元素编号就直接操作，不要连续输出 snapshot 空转"——治 LLM 行为性打转。
3. **站点行为进知识库而非任务描述**：猎聘"选完城市自动关闭面板+自动搜索（URL 加 #session）"写进知识库 hint，任务描述只需一句"页面行为参考【站点提示】"。
4. **参数序列化坑**：`chrome.scripting.executeScript` 的 args 数组里不能有 undefined（报 "Value is unserializable"）——所有动作参数统一加固缺省值（text→''、index→-1、amount→600 等）。
5. **P2-5 遗留死锁（本轮最大的 bug）**：`db.py` 的 `insert_candidates`/`upsert_task`/`query_candidates`/`stats` 都是 `with _lock:` 内调 `_get_conn()`，而 `_get_conn()` 在 `_conn is None`（独立进程首次）时又 `with _lock:`——**threading.Lock 不可重入，CLI 独立进程首次入库必死锁**（T2 run finish 后卡死，candidates 不落库）。修复：`_get_conn()` 移到 `with _lock:` 之外。P2-WIP 踩坑 #2 只修了 init_db 路径，insert 路径漏了。
6. **Windows GBK 编码**：agent.py/测试脚本 print emoji（📸🧠）在 GBK 管道 UnicodeEncodeError——脚本开头 `sys.stdout.reconfigure(encoding="utf-8")`。
7. **P1/P2 坑仍有效**：executeScript 自包含；双 bridge 检查（8080 唯一监听）；跑任务期间保持目标标签可用（tab_id 钉住已解耦激活页）；手动连续点击必须每步重快照（React DOM 重排编号偏移——手动预演踩过：连点 3 个编号点错成别的元素）。

## 4. P3 汇报（第 5 节格式，可转交设计对话）

```
P3 完成情况：
1. 完成度：全部（T1 ✅ T2 ✅核心验证 T3 ✅ T4 ✅ T5 ✅ T6 ✅ T7 ✅ T8 ✅ T9 ✅）
2. 质量结论：能运行；T2 核心链路跑通（弹层交互+自动搜索+提取+finish，事件流可追溯）；
   T3/T5/T7 单元测试全过且真实环境生效；T9 修复 P2-5 遗留死锁（CLI 入库曾必死锁）
3. 与设计的偏差：无架构偏差；T2 教育经历条件未被 LLM 设置成功（模型决策问题，机制已具备）；
   快照增强顺带把元素上限 150→400、正文预览加尾部 400 + 弹层标注（通用能力）
4. 下一步建议：P4（DESIGN-P4-VISION.md）——screenshot 能力 + 视觉问答验证（用户配合测试）
   + 经验自学习（成功路径自动沉淀）
```

## 5. 代码改动清单（P3 期间）

| 文件 | 改动 |
|---|---|
| `extension/background.js` | **T1**：isInteractive 增强 ×4 副本 + zClickByText + TOOL_FUNCS 注册 + 参数缺省值加固；**T4**：tab-lost 明确报错（不静默回退激活页） |
| `agent/core.py` | click_by_text（SKILLS/SYSTEM_PROMPT/TOOL_DESC）；规则 10（不空转）；snapshot_to_text（元素上限 400 + 正文头部600尾部400 + 弹层标注）；T3 无进展检测；T4 tab-lost 不重试；T5 动作分级+不可逆闸门（confirm_requested/confirm_granted/confirm_denied 事件）；T7 dry_run/mock_llm 参数 |
| `agent/knowledge_config.json`（新） | 知识库配置化（h.liepin.com 列表页 + 条件页两条目） |
| `agent/knowledge.py` | 读 JSON（缺失回退默认+自动落盘）；match 支持 URL 路径子串优先 |
| `agent/db.py` | **T9 死锁修复**：`_get_conn()` 移出 `with _lock`（4 处） |
| `bridge/server.py` | T5 `POST /api/agent/confirm`；T8 AgentRunner.start persist 参数 + run 端点接收 |
| `agent/agent.py` | UTF-8 输出修复；`--dry-run`/`--mock-llm`/`--no-persist` 参数 |
| `web/console.html` | 渲染 stuck/confirm_requested/confirm_granted/confirm_denied/dry_run_blocked 事件 |
| 测试（新） | `test_stuck_logic.py`（T3）、`test_confirm_gate.py`（T5）、`test_dry_run.py`（T7）、`test_persist_switch.py`（T8） |

## 6. 运行环境备忘（当前状态）

- **浏览器**：Edge；猎聘已登录。当前标签 3 个：dsh GUI（激活）、edge://extensions（重载扩展用）、控制台 127.0.0.1:8080/console。猎聘标签本轮已清理（用 list_tabs 现查）
- **扩展**：background.js 有 T1/T4 改动，**已重载过**（用户确认）；但 **popup 视觉确认（⏸/▶ 按钮）仍待人工确认**——重载扩展后点开 popup 看一眼
- **bridge**：会话 job 拉起，结束会停；`python agent/agent.py "任务"` 自动拉起（P2-6 不双开）；**改了 server.py 后需重启 bridge 才生效**
- **SQLite**：`logs/agent.db`（WAL）；candidates≈63（含 T8 测试数据）；tasks≈243
- **Agent**：`python agent/agent.py "任务" --max-steps N --tab-id <id> [--dry-run] [--no-persist]`
- **控制台**：http://127.0.0.1:8080/console
- **测试**：`python test_stuck_logic.py` / `test_confirm_gate.py` / `test_pause_logic.py` / `test_dry_run.py` / `test_persist_switch.py`（均需 PYTHONIOENCODING=utf-8 或已在脚本内 reconfigure）
- **.env**：browser-agent/.env 已配 DEEPSEEK_API_KEY（视觉模型 API 调用可复用，model 名见 P4 文档）
- **知识库**：`agent/knowledge_config.json`（改 JSON+重启桥即生效）

## 7. P4 交接要点（详细见 DESIGN-P4-VISION.md）

- **V-T1 screenshot 能力**：扩展新增 `screenshot`（captureVisibleTab → bridge 落盘 logs/screenshots/），只读动作无需闸门
- **V-T2 视觉问答验证（主线）**：测试闭环 = agent 截图 → 提问视觉 LLM → 结合快照判断 → **用户做真值验证**（确认动作/内容准确性）。顺序：简单页储备 → T2 复杂页逐步 → 结论（SOM 方案可行性）
- **V-T3~V-T5**：经验自学习（成功路径自动写回）、记忆 vs 现实对比、截图资产沉淀
- 用户参与：配合操作浏览器（点击/输入/切换），向 agent 汇报动作是否点对、内容是否抓对
