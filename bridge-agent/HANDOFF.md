# 交接包：浏览器 Agent（browser-agent）P0 → P1

> 生成时间：2026-08-20 ｜ 交接方式：本文件是"设计对话 → 实施对话"的唯一跨对话记忆
> 实施对话开场：先读本文件 + `browser-agent/DESIGN.md` + `browser-agent/README.md`，再读代码
>
> ⚠️ **2026-08-22 更新：P1（T1-T4）已全部完成，请先读 `HANDOFF-P1-COMPLETE.md`**
> 新对话必读：`HANDOFF-P1-COMPLETE.md`（P1 完成明细 / 踩坑记录 / P2 待办 / 未决架构问题）

---

## 1. 项目背景（一段话）

目标：做一个**独立的浏览器 Agent**——真人或调度 Agent 用自然语言指令驱动它操作真实已登录的猎聘浏览器（快照→推理→动作→验证的 LLM 循环）。不依赖 DeepSeek Harness、wails、Playwright。它是未来"岗找人多 Agent 数字员工"的浏览器控制底座，但**多 Agent 系统设计已明确后置，本阶段只做浏览器控制**。

## 2. 当前状态（P0 已完成 ✅）

| 项 | 状态 |
|---|---|
| 桥接服务 `bridge/server.py`（Python 标准库，:8080） | ✅ 已实现并实测：health / task 创建 / poll / result / logs 全链路通过 |
| Chrome 扩展 `extension/`（MV3） | ✅ 已实现（manifest/background/popup），语法检查通过；**尚未加载进浏览器实测** |
| Agent 循环 `agent/agent.py`（DeepSeek，标准库 urllib） | ✅ 已实现，语法检查通过；**尚未端到端实测**（需扩展加载后） |
| 设计记录 `DESIGN.md`（8 条拍板决策） | ✅ |
| 运行说明 `README.md` | ✅ |
| 独立 `.env`（DEEPSEEK_API_KEY 已复制） | ✅ agent.py 只读自己的 .env，不依赖外部 |
| 工作区清理 | ✅ GUI 脚本/Streamlit 项目已归档到 `_archive/`（与本项目无关） |

## 3. 只读清单（⚠️ 重要：控制上下文，勿漫游）

**必须读（全部在 `D:\study\lietou-agent\browser-agent\` 内）：**
```
browser-agent\DESIGN.md          # 设计决策（8 条，先读）
browser-agent\README.md          # 运行说明
browser-agent\bridge\server.py   # 桥接服务（8KB）
browser-agent\extension\background.js  # 扩展执行器（12KB，含工具函数库）
browser-agent\extension\manifest.json / popup.html / popup.js
browser-agent\agent\agent.py     # LLM 循环（11KB）
```

**禁止读**（已归档到 `_archive/`，与本任务无关）：wxPython 采集脚本、Streamlit 项目（岗位招聘）、_db_copy。不要用 glob 全目录探索。

## 4. P1 任务清单（实施对话的目标）

> 参考参考：dsh-browser（`C:\deepseek\dsh-browser`）是协议参考实现，必要时可读其 `extensions/dsh-browser/src/background/bridge.ts` 与 `protocol.ts` 借鉴，但**不得作为运行时依赖**。

**✅ T0（已完成，设计对话交付）——Agent 测试控制台**
- `web/console.html`（http://127.0.0.1:8080/console）：输入自然语言指令 → 后台跑 agent 循环 → 实时日志显示每步决策
- bridge 新增端点：`POST /api/agent/run` / `GET /api/agent/status/{run_id}` / `GET /api/agent/runs`
- agent 循环抽到 `agent/core.py`（CLI 与控制台共用）；`agent/agent.py` 自动拉起桥接服务
- 验证：run 创建/状态查询/事件收集已通过；完整循环待扩展加载后联调

| # | 任务 | 验收标准 |
|---|---|---|
| T1 | **三方联调**：启动桥接服务 + 加载扩展 + 跑 agent（控制台或 CLI），在真实猎聘页完成一次"快照→决策→动作→验证"闭环 | agent 一条指令完成至少 3 步工具调用并 finish；logs/tasks.jsonl 有完整任务链 |
| T2 | **补 wait/稳定检测**：点击/导航后等待页面加载稳定再快照（参考 dsh-browser 的 settle 思路）；动作失败时自动重试或换策略 | 慢页面操作不再误判；重试逻辑有日志 |
| T3 | **约束与风控参数化**：`--max-steps`（已有）、翻页间隔随机化、验证码/登录过期检测（快照中出现验证码特征 → 停止并提示转人工） | 风控参数在 agent.py 命令行可配；验证码场景能优雅停止 |
| T4 | **猎聘翻页任务端到端**：Agent 自主完成"搜索 Python 岗位 → 翻 3 页 → 提取候选人列表 → 汇总返回" | 一次完整任务跑通，结果含候选人条数/source_id，运行记录落 logs/agent_runs/ |

**明确不做**（用户已拍板）：采集入库（candidate_pool 落库是其他 Agent/后台的事）；多 Agent 编排；知识库/流程沉淀（P2 后置）；换 WebSocket 长连接（除非轮询暴露明显问题）。

## 5. 汇报格式（实施对话完成时按此回传）

```
P1 完成情况：
1. 完成度：（全部/部分/阻塞）
2. 质量结论：（能运行？对照 T1-T4 验收标准逐条）
3. 与设计的偏差：（如有，说明原因）
4. 下一步建议：（继续 P2 / 需设计对话拍板某点 / 需返工）
```

## 7. 工作方式约定（对话驱动开发）

- 开发循环：**用户自然语言 → 实施对话写代码 → 实施对话用浏览器助手（dsh）实际操作浏览器验证 → 讨论 → 改**
- 测试执行器：dsh 浏览器助手是**开发期测试工具**（AI 操作浏览器的"手"），不是产品组件；产品组件是 browser-agent 自己的扩展+桥接服务
- ⚠️ **浏览器单连接限制**：dsh-browser 桥同一时刻仅一个活动连接，两个对话**不能同时操作浏览器**，会互相顶掉。同一时间只有一个对话在使用浏览器助手
- 分工：实施对话 = 写代码 + 自测（主操作者）；设计对话 = 拍板 + 抽查验证（只在实施对话不操作时）；用户 = 自然语言驱动 + 汇报中转
- 验收汇报格式见第 5 节；测试时优先用控制台 http://127.0.0.1:8080/console（比 CLI 直观）

## 6. 运行环境备忘

- 桥接服务：`python bridge/server.py`（127.0.0.1:8080，标准库零依赖）
- 扩展加载：`chrome://extensions` → 开发者模式 → 加载已解压 → `browser-agent\extension`
- Agent：`python agent\agent.py "任务描述"`；`.env` 里已配 DEEPSEEK_API_KEY
- 扩展操作的是**当前激活标签页**；浏览器内置页（chrome://）无法注入
- 桥接服务进程不会常驻——联调时先启动它
