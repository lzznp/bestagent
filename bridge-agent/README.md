# 浏览器 Agent（browser-agent）P0

独立的浏览器控制模块：**Chrome 扩展（执行器） + 桥接服务（控制端） + LLM Agent 循环**。
不依赖 DeepSeek Harness / wails / Playwright。全部 **Python 标准库**，零 pip 依赖。

```
真人/调度Agent ──自然语言──▶ agent.py ──▶ bridge/server.py (:8080) ──轮询──▶ Chrome扩展 ──▶ 真实已登录浏览器
```

## 快速开始（3 步）

### 1. 启动桥接服务
```bash
cd D:\study\lietou-agent\browser-agent
python bridge/server.py            # 默认 127.0.0.1:8080
```
看到 `[bridge] 浏览器桥接服务已启动` 即成功。（跑 `agent.py` 时会自动拉起，无需手工。）

### 2. 加载 Chrome 扩展
1. Chrome/Edge 打开 `chrome://extensions`
2. 右上角开启「开发者模式」
3. 点「加载已解压的扩展程序」，选择目录：`D:\study\lietou-agent\browser-agent\extension`
4. 工具栏出现「🧭 浏览器助手」图标；点开 popup 应显示 🟢 桥接服务已连接

### 3. 运行 Agent（两种方式任选）

**方式 A：Agent 控制台（推荐，图形界面）**
浏览器打开 `http://127.0.0.1:8080/console` —— 输入自然语言指令 → 点「运行 Agent」→
并排观察浏览器窗口变化，下方日志实时显示 Agent 每一步决策（快照/思考/动作/结果）。

**方式 B：命令行**
```bash
python agent/agent.py "打开猎聘，搜索 Python 岗位，提取前几条候选人"
python agent/agent.py "提取当前页候选人" --tab-id 1890028342   # P2-5：钉住操作标签页
```
运行记录在 `logs/agent_runs/`。

## 手动测试（不经过 LLM）

| 方式 | 操作 |
|---|---|
| popup | 查看连接状态与运行状态；Agent 运行中可点「⛔ 紧急停止」（当前步骤结束后中止） |
| curl | `curl -X POST http://127.0.0.1:8080/api/task -H "Content-Type: application/json" -d "{\"action\":\"snapshot\"}"` → 记下 task.id → `curl http://127.0.0.1:8080/api/task/<id>` 查结果 |
| 任务列表 | `curl http://127.0.0.1:8080/api/tasks` |
| 日志 | `curl http://127.0.0.1:8080/api/logs` |

## 工具面（Agent 可用动作）

| action | 参数 | 说明 |
|---|---|---|
| snapshot | — | 页面 title/url + 编号交互元素 + 正文预览（含弹层/分页标注） |
| click | index | 按编号点击 |
| **click_by_text** | text, occurrence | **P3-T1：按文本点击包含该文本的最小可点元素**（解决"看得见字、点不了"的选项类 span/li，如搜索条件选项；occurrence=第几个匹配，默认 1） |
| type | index, text | 输入文本（兼容 React） |
| scroll | direction, amount | 滚动 |
| navigate | url | 跳转 |
| extract | anchor_text | 通用列表提取：锚点文本（卡片内任一稳定子串）→ 返回所有匹配卡片行 {text, fields}，fields 含行内命名 input 的 value（站点唯一 ID 由 agent 侧知识库认领） |
| list_tabs | — | 列出当前窗口所有标签页（tab_id/url/title/active） |
| new_tab | url | 打开新标签页并激活 |
| switch_tab | tab_id | 切换到指定标签页（激活）；注入型动作可带 tab_id 指定操作目标标签（默认激活页） |
| close_tab | tab_id | 关闭指定标签页（新标签用完后关闭） |
| finish | summary, data | 任务完成（Agent 内部） |

## 站点知识库（P3-T6 配置化：JSON 配置，加站点不动代码）

- 配置在 **`agent/knowledge_config.json`**（加站点/改站点 = 编辑 JSON + 重启桥，不改代码；缺失时回退内置默认并自动落一份 JSON）
- 匹配键：**域名**（如 `h.liepin.com`，子域名同样命中）或 **URL 路径子串**（如 `h.liepin.com/search/getConditionItem`，优先于域名——同一站不同页面可配不同知识）
- 每个站点条目 = 站点模板：`hint`（注入提示词的站点知识）+ `source_id_field`（唯一 ID 字段，程序化映射）+ `anchor`（推荐锚点）+ `verify`（基线检测规则）
- **改版检测机制**：任务开始自动跑 `verify_site` 内部动作检查基线（锚点/隐藏字段/分页控件）——任一缺失 → 事件 `site_changed` + 本任务降级为纯 LLM 现场推理（不注入过时知识）→ 人工核对后更新 JSON 配置（version+1）
- 网站改版时只改 `knowledge_config.json` 对应条目，不动扩展与工具面

## 可靠性机制（P3）

| 机制 | 说明 |
|---|---|
| **无进展检测（T3）** | 连续 5 步页面签名（URL/元素数/数据）无变化且未执行实质动作 → 事件 `stuck` + 终止（防 LLM 原地打转耗尽步数） |
| **tab-lost 明确报错（T4）** | 指定 tab_id 的标签已关闭 → 报 `tab-lost` 错误（不静默回退激活页），且不重试（确定性错误） |
| **不可逆动作闸门（T5）** | 动作三级分级：只读/低风险/不可逆；不可逆动作（发送/发布/删除类，目前预留）默认需人工确认——`confirm_requested` 事件 + 阻塞等待，`POST /api/agent/confirm` 确认/拒绝 |
| **只读试跑（T7）** | `--dry-run`：只执行只读动作（snapshot/scroll/extract/list_tabs/verify_site），写动作拦截为 `dry_run_blocked` 事件——新站/新任务先看 LLM 决策再放正式任务 |
| **mock LLM（T7）** | `--mock-llm '<JSON 动作序列>'` 代替真实 LLM，确定性测扩展链路（不花 API） |

## 多 Agent 数据库桥（agent/db.py，P2-5）

**SQLite（标准库 sqlite3）作为存储层**（`logs/agent.db`，JSONL 审计保留），让浏览器 Agent 的结果可被其他 Agent（调度/入库/查表）消费：

- `tasks` 表：浏览器操作任务链（pending→executing→done/failed/timeout，status 驱动调度 Agent 轮询），bridge 每次变更写穿同步
- `candidates` 表：Agent finish 后的提取结果，**source_id 唯一约束 + INSERT OR IGNORE 防重复采集**（raw_text/fields/site/url/run_id/created_at）
- **消费入口**：`GET /api/candidates`（site/source_id 过滤 + 分页）、`GET /api/tasks`、`GET /api/db/stats`
- **技能注册表**：`GET /api/agent/skills` 返回浏览器 Agent 全部动作 + 参数 Schema——调度 Agent 先查技能再派活
- **run 级 tab_id 钉住**：`POST /api/agent/run` 带 `tab_id` 时，整个 run 的注入型动作固定作用于该标签页（不依赖激活标签页；多标签切换类任务不要用）

## 目录

```
browser-agent/
├── DESIGN.md          # 设计记录（决策表）
├── DESIGN-BASE.md     # 底座架构定稿（P2 后：通用可靠浏览器自动化 + 下一阶段任务书）
├── HANDOFF.md         # 交接包（P0→P1，新对话先读这个）
├── bridge/server.py   # 桥接服务（标准库，含 agent 后台运行端点）
├── extension/         # Chrome 扩展（加载此目录）
│   ├── manifest.json
│   ├── background.js  # 轮询 + 注入执行（click_by_text 等 12 个动作）
│   └── popup.html/js  # 状态 + 紧急停止
├── agent/core.py      # Agent 核心循环（CLI 与控制台共用；动作分级/无进展检测/dry-run/mock LLM）
├── agent/knowledge.py # 站点知识库加载器（P3-T6：读 knowledge_config.json，配置缺失回退内置默认）
├── agent/knowledge_config.json  # 站点知识库配置（P3-T6：加站点/改站点改这里，不动代码）
├── agent/db.py        # 多 Agent 数据库桥（P2-5：SQLite tasks/candidates 表 + 技能注册表数据源）
├── agent/agent.py     # 命令行入口（自动拉起桥接服务；--dry-run/--mock-llm/--tab-id）
├── web/console.html   # Agent 控制台页面（http://127.0.0.1:8080/console）
├── test_pause_logic.py    # P2-2 暂停逻辑单元测试（fake bridge）
├── test_stuck_logic.py    # P3-T3 无进展检测单元测试
├── test_confirm_gate.py   # P3-T5 不可逆动作闸门单元测试
└── logs/              # agent.db(SQLite) + tasks.jsonl(审计) + agent_runs/ + bridge.log
```

## API 一览

| 端点 | 说明 |
|---|---|
| GET /api/health | 健康检查（含 agent 模块可用性） |
| **POST /api/control/stop** | **人工总闸（2026-09-11 A+B）：置 `stopped_at` + 清空待执行队列。正在跑的采集脚本（`collect_liepin` / `detail_collect`）在每个动作前自查 → 干净收尾（已采数据照常写盘）。一次性刹车：不影响之后新发起的采集，无需"恢复"** |
| **GET /api/control/state** | **`{stopped_at, pending, inflight}`——popup 状态行 + 脚本自查都用它** |
| POST /api/task | 提交浏览器操作任务 {action, params, source?} |
| GET /api/task/poll | 扩展轮询取任务 |
| POST /api/task/result | 扩展回报结果 |
| GET /api/task/{id} / GET /api/tasks | 查任务（写穿 SQLite tasks 表） |
| POST /api/agent/run | 后台启动 agent 循环 {task, max_steps, tab_id?} |
| POST /api/agent/cancel | 停止 agent 循环 {run_id?}——省略 run_id 时停止当前运行中的循环（**注意：只管桥自带 LLM 循环，管不到小猎的 /api/task 链路**） |
| POST /api/agent/pause | 暂停 agent 循环 {run_id?}（步骤边界生效；控制台在用） |
| POST /api/agent/resume | 继续 agent 循环 {run_id?}（控制台在用；**小猎链路不用暂停/继续**——确定性脚本失败重跑即可） |
| **POST /api/agent/confirm** | **P3-T5 不可逆动作确认 {run_id?, approve: true/false}——approve=true 确认执行，false 拒绝（中止任务）** |
| GET /api/agent/status/{run_id} | 实时状态 + 逐步事件 |
| GET /api/agent/runs | 历史运行列表 |
| **GET /api/agent/skills** | **技能注册表（P2-5）：全部动作 + 参数 Schema，调度 Agent 查技能用** |
| **GET /api/candidates** | **候选池查表（P2-5）：?site=&source_id=&limit=&offset=，其他 Agent 消费** |
| **GET /api/db/stats** | **SQLite 存储统计（P2-5）：tasks/candidates 数量与状态分布** |
| GET /console | Agent 控制台页面 |

## 常见问题

- **popup 显示🔴未启动**：先运行 `python bridge/server.py`
- **任务一直 pending**：扩展是否加载？浏览器是否有激活标签页？页面是否可注入（http/https）？
- **报错 injection-failed**：当前页是浏览器内置页（chrome:// 等）无法注入，切到普通网页
- **没有 DEEPSEEK_API_KEY**：设置环境变量，或确保 `D:\study\lietou-agent\岗位招聘\.env` 存在（agent 会自动读取）
