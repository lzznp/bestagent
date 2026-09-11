# 交接包：browser-agent P1 完成 → P2（新对话开场必读）

> 生成时间：2026-08-22 ｜ 交接方式：P1 实施对话（老师傅）→ P2 新对话（新徒弟）
> 新对话开场顺序：**先读本文件** → 再读 `HANDOFF.md` + `DESIGN.md` + `README.md` → 再读代码
> 本文件是 P1 完成状态与 P2 待办的唯一跨对话记忆，避免新对话重走弯路。

---

## 1. 一句话状态

**P1 四任务（T1-T4）全部验收通过**，三方联调（桥接服务 + Chrome 扩展 + DeepSeek agent）已在真实已登录猎聘（诚猎通 h.liepin.com）上跑通完整闭环：搜索 → 翻 3 页 → 提取候选人（含 source_id）→ 汇总返回。

---

## 2. P1 完成明细（对照验收标准）

| 任务 | 验收标准 | 结果 |
|---|---|---|
| T1 三方联调 | ≥3 步工具调用并 finish；tasks.jsonl 完整任务链 | ✅ run `db176c03ce`：type×2→click→extract×2→finish，返回 12 位候选人；tasks.jsonl 每条任务 pending→executing→done 三段 |
| T2 wait/稳定检测 | 慢页面不误判；重试逻辑有日志 | ✅ snapshot 前 settle 等待（readyState + MutationObserver 静默 200ms，实测 waited_ms=243）；动作失败自动重试 2 次（间隔随机 1-2.5s）+ retry 事件 |
| T3 约束与风控参数化 | 风控参数 CLI 可配；验证码优雅停止 | ✅ `--page-delay-min/max`、`--risk-check on/off`；验证码/登录过期检测 5 用例全过（精确特征词，短信"获取验证码"按钮无误报） |
| T4 猎聘翻页端到端 | 翻 3 页、含条数/source_id、落 logs/agent_runs/ | ✅ run `fd000245a6`：自主点击"下一页"翻 3 页，total_count=57（source_id 去重），candidates 含 source_id，记录 132KB 落盘 |

**P1 回传汇报（第 5 节格式）已可交付**，内容见本文件第 5 节。

---

## 3. 代码改动清单（P1 期间全部改动）

| 文件 | 改动 | 目的 |
|---|---|---|
| `extension/background.js` | ① chrome.alarms 保活轮询（MV3 SW 空闲 30s 被回收）；② zSnapshot/zClick/zType 遍历逻辑内联（executeScript 只序列化目标函数，外部引用全报 ReferenceError）；③ zSnapshot 内联 settle 等待；④ zExtractLiepin 增加从卡片隐藏 input[name=res_id_encode] 提取 source_id（诚猎通结构） | T1/T2/T4 |
| `extension/manifest.json` | 增加 `alarms` 权限 | T1 保活 |
| `agent/core.py` | ① execute_with_retry 动作失败重试；② detect_risk 风控检测；③ snapshot_to_text：元素上限 80→150 + 分页元素标注（下一页/页码）+ 列表页正文预览 3000→600 字；④ 程序化累积 accumulated_candidates（extract 结果自动累积，finish 合并去重）；⑤ System Prompt 增补翻页规则 | T2/T3/T4 |
| `agent/agent.py` | ① 修复 T0 遗留语法错误（global BRIDGE_URL 位置，此前 py_compile 就报错）；② CLI 新增 --page-delay-min/max --risk-check；③ 打印 retry/risk_blocked 事件 | T3 |
| `bridge/server.py` | ① AgentRunner.start 透传风控参数；② POST /api/agent/run 解析 page_delay_min/max、risk_check | T3 |
| `web/console.html` | 渲染 retry 事件（🔁）、risk_blocked 事件（⛔） | T2/T3 |

---

## 4. 踩坑记录（新对话务必记住，避免重踩）

1. **MV3 service worker 空闲回收**：Chrome 约 30s 无事件就终止 SW，顶层 `setInterval` 轮询随之停止，任务永远 pending。修复：`chrome.alarms` 每 25s 唤醒 + 唤醒后立即 pollOnce 并重启 interval。⚠️ Chrome <120 的 alarms 最小周期是 1 分钟，代码里有 try/catch 降级。
2. **executeScript 注入不自包含**：注入时只序列化目标函数体，函数内引用本文件其他函数/变量全部 ReferenceError（`collectElements is not defined`、`elementByIndex is not defined`）。修复：每个工具函数内部内联完整遍历逻辑。**新增工具函数必须遵守此约束**。
3. **双 bridge 进程（反复出现 ⚠️ 必读）**：有两个来源——
   ① `agent.py` 的 `ensure_bridge()` 用 **DETACHED_PROCESS** 拉起 bridge，子进程脱离对话/终端生命周期，**对话关闭后进程依然常驻**（上对话启动的 bridge 可能还在跑）；
   ② 用 `Get-NetTCPConnection -LocalPort 8080` 检测端口在受限 shell 里会**误报"未监听"**（cmdlet 失败被吞），导致重复启动新实例。
   修复：重启前 `Get-Process python* | Stop-Process -Force` 清干净再启动；检测端口用 **`netstat -ano | findstr :8080`（必须只有 1 个 LISTENING）**，不要用 Get-NetTCPConnection。
   **新对话开局第一件事**：netstat 确认 8080 状态——若已有 1 个监听（旧 bridge 常驻），直接用即可，不要重复启动；若多个，清理后启动唯一实例。
   **会话结束**：bridge 不会随对话自动停止（DETACHED 特性），可接受其常驻（便于下次联调直接复用），无需专门杀。
4. **快照截断让 LLM 看不到分页**：元素上限 80 时"下一页"（编号 110+）被截掉，LLM 想翻页也无从下手。修复：上限 150 + 分页元素单独标注行（"分页元素（翻页时点击这里）：编号128(下一页)…"）。
5. **LLM 无法"持有"提取数据**：extract 结果塞 400 字原文进 history 会污染上下文、误导 LLM 以为每页有新数据；且 LLM 上下文有限会丢数据。修复：history 只放结构化摘要（条数+累计数），完整数据由 agent 程序化累积（accumulated_candidates），finish 时合并去重。
6. **正文预览干扰**：列表页 3000 字正文会让 LLM 以为"已看到全部数据"而提前 finish。修复：元素 >40 时正文预览截到 600 字。
7. **运行期间不能切换激活标签页**：扩展操作的是"当前激活标签页"，切到 chrome:// 或 127.0.0.1:3080（本 GUI）会注入失败（无权限）。T1 有一次 run 因此失败。跑任务时提醒用户保持猎聘页激活。

---

## 5. P1 回传汇报（可直接转交设计对话）

```
P1 完成情况：
1. 完成度：全部（T1 ✅ T2 ✅ T3 ✅ T4 ✅）
2. 质量结论：能运行，对照 T1-T4 验收标准逐条通过（明细见第 2 节）
3. 与设计的偏差：
   · 修复 4 个联调缺陷（MV3 SW 保活、executeScript 自包含、快照截断致翻页不可见、双 bridge 进程）
   · extract_liepin 仍是猎聘专用工具（联调捷径，违背决策#7"不预设选择器"）——见第 7 节未决架构问题
   · agent.py 修复 T0 遗留语法错误
4. 下一步建议：见第 6、7 节（P2 任务 + 需设计对话拍板的架构问题）
```

---

## 6. P2 待办清单（按优先级）

| # | 任务 | 说明 |
|---|---|---|
| P2-1 | **插件去猎聘化（架构方向）** | popup 去掉「提取猎聘候选人」测试按钮；manifest host_permissions 通用化；删 zExtractLiepin → 通用 extract 工具（参数 {selector, fields}，LLM 从快照现场决定选择器）；猎聘知识移到 agent 侧提示词。**需回归 T4**（已验证 LLM 靠快照正文就能提取候选人，source_id 在快照元素 value 里可见） |
| P2-2 | **插件 UI 产品化** | 只显示：连接状态 + 紧急停止 + 继续（人工过验证码/重新登录后恢复）。「紧急停止」建议优先做（bridge 加 cancel run 端点 + popup 按钮，安全兜底） |
| P2-3 | **多标签页管理** | 打开/切换/指定标签操作（接口层已可留 tab_id 扩展点）。人工场景：找简历→开详情页→切回复页对话 |
| P2-4 | **网站页面知识库（流程沉淀）** | 把诚猎通页面结构/分页位置/res_id_encode 含义固化为 agent 侧模板；改版时做基线对照。素材 = 本文件第 4 节踩坑记录 |
| P2-5 | **多 Agent 数据库桥** | 调度 Agent→浏览器 Agent→入库→其他 Agent 查表。建议：任务表（指令+状态机）与数据表（候选人结果）分离；status 字段驱动轮询；source_id 唯一约束防重复采集。当前 bridge 的 task 状态机就是雏形，JSONL 换数据库即可。**任务量级小，不需要消息队列** |
| P2-6 | **ensure_bridge 启动去重（根治双进程）** | agent.py 的 ensure_bridge 先检查 8080 是否已有健康实例（GET /api/health 成功即有），有则直接复用、不重复 Popen；配合第 4 节踩坑 3 的 netstat 检测法，从代码层杜绝双 bridge 进程 |

---

## 7. 已讨论但未拍板的架构问题（新对话需找设计对话确认）

1. **插件通用化**：当前 extract_liepin 是猎聘专用（违背决策 #7）。用户倾向"插件只做通用浏览器助手"，已认可方向，但"现在重构还是 P2 做"未定（建议 P2-1，但 popup 测试按钮清理 + manifest 通用化可立即做）。
2. **多 Agent 通信**：用户提出"数据库表作为多个 Agent 沟通桥梁"——已分析合理（任务表/数据表分离 + 状态字段 + source_id 唯一约束），可拍板。
3. **人工介入接口**：验证码/登录过期/卡死时需「继续」和「紧急停止」按钮，是否现在加未定。
4. **开发期测试按钮**：popup 的快照/提取按钮是开发工具，最终产品化时移除（用户已明确"插件只显示连接情况即可"）。

---

## 8. 运行环境备忘（当前状态）

- **桥接服务**：唯一实例运行中（127.0.0.1:8080，job 由实施对话拉起）。⚠️ **进程生命周期**：若经 agent.py 的 ensure_bridge 启动则为 DETACHED 进程，对话关闭后仍常驻；当前实例是本次对话以 job 方式拉起的，会话结束时 job 被杀、实例停止。新对话开局先 `netstat -ano | findstr :8080` 确认（应为 1 个监听），有旧实例直接用，无则启动。
- **扩展**：已加载（manifest 含 alarms 权限），background.js 为最新版。
- **浏览器**：Chrome 激活标签页 = 猎聘诚猎通「找简历」结果页（已登录，用户"杨猛"），本轮联调一直用它。
- **Agent**：`python agent/agent.py "任务" --max-steps N --page-delay-min 2 --page-delay-max 4 --risk-check on`
- **控制台**：http://127.0.0.1:8080/console （输入指令 → 运行 Agent → 实时日志）
- **.env**：browser-agent/.env 已配 DEEPSEEK_API_KEY（agent.py 读这个，README 里"岗位招聘/.env"是旧文案）
- **logs/**：tasks.jsonl 已 2.1MB（每次快照全量写入），agent_runs/ 有 15 个 run 记录（最新成功：fd000245a6）
- **注意**：跑 agent 任务期间**保持猎聘页为激活标签页**，勿切到 chrome:// 或本 GUI（127.0.0.1:3080）

---

## 9. 给新徒弟的开场建议

1. 先读本文件 + HANDOFF.md + DESIGN.md（15 分钟），再读 core.py / background.js 代码
2. 验证环境：`netstat -ano | findstr :8080`（应 1 个监听）→ `curl http://127.0.0.1:8080/api/health`
3. 若需重测：控制台提交一条"提取当前页候选人"任务即可快速回归
4. P2 第一件事建议做 P2-1 的"popup 清理 + manifest 通用化"（低风险）+ P2-2 的「紧急停止」（安全兜底）
5. 任何架构改动先回本文件第 7 节与设计对话对齐，别擅自扩大范围
