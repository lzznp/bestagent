# SDK 运行时原理 · 交接文档（2026-09-12）

> **定位**：**交接给下一个新对话**。下一场的主题 = **搞懂「SDK 拉起的运行时」到底怎么回事**（老板原话：*"我就是一个司机，我也要知道发动机原理，知道转动原理啥的"*）。
> **上一场** = `工作文档\采集与沟通链路·衔接报告.md`（2026-09-11 晚 + 09-12，猎聘页面实测 + 采集流程重设计，**未写码**）。
> **更早** = `工作文档\底座修复·衔接报告.md`（09-11 底座修复，验收 ①②④ 通过）。
> **配套**：`工作模式·备忘.md`（谁是谁 / 命名 / 三层运行边界）｜`PROGRESS.md`（决策表，本场新增 **31/32**）｜`HANDOFF.md` §4（环境事实）。
> **纪律**：动手前对齐目的声明；小步验证 + 复盘；判断错不罚、不诚实必罚；**禁 bash（本机用 pwsh）**；小 JSON + 本地渲染；采集必须先出计划并经老板确认才真跑；**改代码前先只读调研并报工作量**。

---

## 0. 一句话

**新对话的任务不是写功能，是"把发动机拆开讲清楚"**——SDK 怎么把运行时拉起来、一次 `run()` 里面到底发生了什么、工具和会话是怎么运转的、哪些是稳定接口、哪些一变就作废。

⚠️ **老板明确要求**：他**不想**停在"你不必懂发动机"这个层面了；他要**懂原理**。上一场我说过"你不必懂发动机"，那是**判断错误**，本场按他的要求纠正。
（但需守住一条：**只讲"司机该懂的发动机原理"，不把注意力烧在会随版本变化的内部细节上**——两者都要讲清楚，让他自己决定深到哪。）

---

## 1. 当前项目状态（开工前必看）

### 1.1 环境（09-12 本场实测，全绿）

- `framework_config.check_env()` → **`[]`（空 = 六项全过）**
- 桥 `:8080` health ok；**扩展在线**；猎聘 tab `#1890029579` 在（登录态）
- **`GET /api/control/state` → 200** → **桥已重启**（停止开关 A 生效）
- 面板 8501 活着（老板自己的实例）

### 1.2 两单在跑

| 岗位 | 状态 |
|---|---|
| **`J-CHAT-20260909-094907`**（智库·机械工程师 12HC，已 accept） | ①✅ ｜ ④发岗文字**已存在**（09-11 16:15，顺序提前）｜ **②③⑤未做** ｜ 猎聘上**已发布** `hjobId=79866575` |
| **`J-CHAT-20260912-153231`**（FAE/技术支持 17HC，09-12 15:32 新建） | ①✅ ｜ **`decision=pending`（小猎建议「先沟通再定」，正等老板拍板）** ｜ ②③⑤未做 |

### 1.3 今天（09-12）落盘的东西

- **新增** `工作文档\采集与沟通链路·衔接报告.md`（猎聘页面实测 + 采集链诊断 + 流程定稿）
- **`PROGRESS.md`** 追加决策 **31 / 32** + 晚场会话段落
- **提交** `3e36350`（2 files，350 insertions，**原有内容零删除**）
- **代码一行没改**

---

## 2. 下一场的目标（本场交接的核心）

**把「SDK 拉起的运行时」讲透。** 建议按下面 10 问推进（一问一节，讲完一节停一次让老板消化）：
**每节都要有实测/源码证据，不许只讲抽象。**

| # | 要讲清的问题 |
|---|---|
| 1 | **运行时本体**：`deepseek-harness-runtime-bin`（229MB）里到底是什么？为什么首跑要自解压？`profiles\sdk` 是什么、装在哪、`node_modules` 是谁在用？ |
| 2 | **一次 `harness.run()` 的全过程**：Python 侧 ↔ 运行时怎么通信（stdio / JSON-RPC / ACP？）；session 怎么建；事件怎么流回来 |
| 3 | **`final_response` 从哪来**：`api.py` 的 `final_response(events)` / `finish_reason(events)` / `normalize_input()` 到底怎么挑事件（**这是"它说的话"与"它做的事"的分界**） |
| 4 | **agent 循环的粒度**：**turn / step 的定义**（实测：一次分析 = turn 1 / step 8）；每步是什么；工具由谁执行 |
| 5 | **工具面从哪来**：profile 如何决定工具；`sdk` profile 实测有哪些工具；**能不能定制、怎么验证真的关掉了** |
| 6 | **system prompt 怎么组装**：profile 默认 → patch **整行替换**（`personaPrefix/personaSuffix`）；`{{cwd}}` 这类模板变量谁替换 |
| 7 | **沙箱与权限**：`DSH_PERMISSION_MODE=danger-full-access` 的确切含义；approval 机制；为什么无头运行 approval=never |
| 8 | **会话落盘**：`sessions\<slug>\<sid>\session.v3.jsonl.zstd` 的结构；**`storages\session_projcache\*.json` 是什么**（未压缩投影，**我们今天就是靠它查的数**） |
| 9 | **token 与上下文怎么涨**：为什么 8 步累计 **11.2 万缓存读**；`cacheRead/cacheWrite`；`contextBreakdown` / `contextPressure` 含义 |
| 10 | **哪些接口稳定、哪些会变**：决定"该懂到多深"——**稳定**：`DeepSeekHarness(profile/dsh_home/patches/cwd/env/model/max_tokens)`、`run()`、`RunResult`；**易变**：profile 内容、事件 schema、落盘格式 |

---

## 3. 已实测的 SDK 事实（**别重查**）

### 3.1 安装与启动（09-11 实测）

- pip：`deepseek-harness-sdk` / `deepseek-harness-runtime-bin` 均 **`0.1.5rc1`**（自带 229MB 运行时 exe；**不需要 node / 不需要 checkout / 不需要 `.dsh-staging`**）
- `deepseek_harness.__file__` 在 **site-packages**（不是 checkout）——`check_env()` 里有**遮蔽检测**（铁律 2 机械化）
- **唯一入口** `framework_config.make_harness()`（全仓 11 个调用点收口）；`profile="sdk"` + `dsh_home=<项目>\data\dsh_home`（**与 GUI 的 `~/.dsh` 彻底隔离**）+ `patches=(persona.patch.yml,)` + `DSH_PERMISSION_MODE=danger-full-access` + **不传 `dsh_bin`**
- session id **每次唯一**（同 id 复用报 `session "X" already exists`）

### 3.2 一次真实运行的全部数字（09-12 实测，**新单 ① 分析**）

> 数据来源：`data\dsh_home\storages\session_projcache\sessions\m3chat-J-CHAT-20260912-153231-analyze-1789198376.json`

| 指标 | 值 |
|---|---|
| **turn** | **1** |
| **step** | **8** |
| input（**未命中**缓存） | **18,024** |
| **cacheRead** | **112,128** |
| output | **8,923** |
| 合计 | **≈129,075** |
| contextPressure | surfaceTokens ~9,612 / window **1,000,000** |
| llmRetry | `{}`（0 次重试） |
| sandboxMode | `danger-full-access` |
| 时长 | 15:32:58 起 → 15:33:51 止（**约 55 秒**） |

**口径公式**（与小画那台机器对齐过）：`totalTokens = inputTokens + cacheReadTokens + outputTokens`，其中 `inputTokens` **不含**缓存读。
⚠️ `reasoningTokens` 是 `outputTokens` 的**子集**，不要相加。

**这次运行里它做的 6~8 个动作**（从产物与它自己的过程文档反推）：
读 `jd.txt` → 读 `analyze_job.txt` → 读 `rules.md` → 读 `meta/state.json` → 写 `analyze_*.json` → 写 `_过程.html` → 说完了。
**我们代码全程只做三件事**：拼剧本 → 起引擎 → 跑完扫 `reports\` 目录 diff。

### 3.3 工具面与 system 位（实测 + 交叉验证）

- 运行时的 `tools` 实测含 **`pwsh`** + **`str_replace_editor`（文件编辑器）**；`session_projcache` 里还有 `todos` / `plan` / `subagentCatalog` / `subagent` 等**投影行**（本次未使用：`todos: null`、`plan.active: false`）
  → ⚠️ **实际工具面比 `CAPABILITIES` 里声明的大**（我们的提示词从没提过 todo/plan/subagent）
- **system 位**：我们的 `persona.patch.yml` 把 profile 的 `system-prompt` 里 `personaPrefix` **整行替换**成 `m3_chat.PERSONA`，`personaSuffix` = `Your working directory is {{cwd}}.`
- ⚠️ **跨机对照（小画那台，08-…~09-10）**：它的 `header.system` **10 份日志全是** DSH 默认的 `"You are a helpful software engineer assistant."` + 同样两个工具 → **它从没注入过自己的 system 人设**；且它以为 `sdk-minimal` 关了工具，**实测没有，还被真调用过一次**（6 次请求 / 30,182 token）
  → **教训：profile 的工具面必须实测验证，不能假设**

### 3.4 会话落盘（**能读到什么，怎么读**）

| 路径 | 内容 | 可读性 |
|---|---|---|
| `data\dsh_home\sessions\<workspace-slug>\<session-id>\session.v3.jsonl.zstd` | **模型视角的完整记录** | ⚠️ **zstd 压缩**；环境里 `zstandard`/`zstd`/`pyzstd`/`compression.zstd` **全没装**，7-Zip 也没有 → **Python 侧读不了** |
| `data\dsh_home\storages\session_projcache\sessions\<session-id>.json` | **未压缩投影**：`title / titleInput / turnBoundary / tokenUsage / contextPressure / contextBreakdown / todos / plan / sandboxMode / permissions / subagent…` | ✅ **直接可读**（**本场所有数字都出自这里**） |
| `data\dsh_home\profiles\sdk\`（+ `node_modules\`） | profile 定义与依赖 | ✅ 可读（**下一场要挖的东西**） |

> **投影缓存里两个最有用的键**：
> - `turnBoundary` → `{openTurnStartSeq, lastStepStartSeq, lastStepBoundary, lastTurn}`
> - `tokenUsage` → `{totals:{uncachedInputTokens, outputTokens, cacheReadTokens, cacheWriteTokens}, last:{turn, step, buckets}}`

### 3.5 SDK 的 Python 接口面（读源码所得，`deepseek_harness\`）

```
api.py
  class DeepSeekHarnessConfig
  class RunResult
  class DeepSeekHarness
      __init__(...) / __enter__ / __exit__ / client() / start() / close()
      start_session(session_id) -> Session
      run(prompt, session_id=..., ...)
  class Session
      __init__(harness, session_id) / run(...)
  def normalize_input(input) -> list[JsonObject]
  def final_response(events) -> str
  def finish_reason(events) -> str | None
models.py:  Notification / IncomingRequest / ServerInfo / InitializeResponse
```
→ **Python 侧的全部就是"构造 + run + 挑事件"**；**agent 循环、工具执行全在运行时（node）里**。

### 3.6 已知的三个"静默失败"（跨项目验证过）

1. **截断**：`max_tokens` 打满（小画实测 8192 打满 → `final_response` 空串）→ **默认没人告诉你**；要自己解析**事件里的 `turn/end.reason.kind == "max-tokens"`**
2. **状态归零**（小画）：参数"每次重述"而非"累积" → agent 漏写一个键就把上一轮静默还原
3. **越权**：运行时工具面开着 → 靠执行侧"不读 tool_call"兜住（**挡后果，不是禁止**）

**共通结构**：**"看起来成功"**。→ 我们项目的对应纪律：**"判断错不罚、不诚实必罚" + "报错贴原文"**。

---

## 4. 已确认的设计原理（上一场结论，本场继续用）

1. **资产 / 壳 分离**：结构化 JSON = 资产（能被重新计算）；HTML/MD = 壳（随时可重画）。
   判据：*"明天把所有代码重写，这东西还认得出来吗？"*
2. **谁生成内容、谁负责结构**：**LLM 出判断（措辞/取舍），本地代码出结构（排版/顺序/完整性）**。
   理由（`report_html.py` 原话）：*"避免让 LLM 手写整份 HTML（大输出 → 截断风险、费 token、不可控）；HTML 渲染零 token、确定性、永不断流。"*
3. **边界要在运行时，不在提示词**：能被绕过的约束，别只写在 prompt 里。
4. **状态属于系统，不属于某次回复**：参数/进度要么进状态文件、要么进日志。
5. **一件事只该有一处实现**：两个入口（面板 / CLI）应该调同一份实现。
6. **闸门只放在"不可逆"处**：可逆的全自动；采集计划确认 / 详情深采 / 打招呼 = 闸门。
7. **agent 会不会乱跑，取决于"它是谁 + 有什么工具 + 在哪儿（cwd）"**——三者任一收窄，风险立刻下降。

---

## 5. 待老板拍板（**会卡住"一期"开工**）

1. **盯槽位**：猎聘**月在线岗位上上限 30 个**、加新岗要顶旧岗 → 要不要让小猎帮盯（记 `published_at` + 状态，到点提醒下线腾槽位）？
2. **①「匹配难度」**：现在这句是从 JD 文字**猜**的（"人才池充足"不是数出来的）→ 降级标注"待实测"，还是**由采集结果回填真实人数**？
3. **一期范围**是否就按：**采集链拆分**（新建 `collect_plan.txt`、`analyze_job.txt` 卸 `search_keywords`、纯代码校验、改 `m3_chat.build_step2_plan_task` + `auto_job._plan_task` 两处）+ `state.json` 加发岗状态位（决策 31/32）？**估算约半天 + 1~2 小时。**
4. **先跑哪一单**：新单 `J-CHAT-20260912-153231`（FAE 17HC，①刚做完、待拍板）还是老单 `J-CHAT-20260909-094907`（机械工程师 12HC，猎聘已发布）？

**另有一条我建议的顺序**（上一场提过，待老板定）：**先改采集链（一期）→ 再做「②采集真跑」**，这样**一次真跑同时验两件事**（上一场遗留的**验收③：小猎用 pwsh 真跑采集** + 新的采集链）；否则现在跑就是我方已知有病的旧关键字（新单那 4 组又是长串 AND），**大概率 0 命中还白烧额度**。

---

## 6. 上一场发现、**尚未处理**的问题清单（备查，别当成已完成）

| # | 问题 | 性质 |
|---|---|---|
| 1 | **两条入口不一致**（已发现 4 例：**采集执行**／**发岗文字**／**详情深采**／**打招呼报告**） | 设计债 |
| 2 | **persona 假单源**：**8 个脚本各有一份 PERSONA**（`m3_chat:176` / `auto_job:66` / `m1_run:28` / `m2_run:28` / `m2_eval_run:31` / `m3_auto_run:26` / `greet_run:38` / `publish_run:44`），写**同一个** `persona.patch.yml` → **谁最后跑谁覆盖** | 设计债 |
| 3 | **①分析让 LLM 手写长 HTML**（`_过程.html`），与"禁 agent 手写长 HTML"的纪律冲突 | 设计债 |
| 4 | **打招呼报告**：面板让 LLM 手写 `.md`；CLI 才走 `greet_*.json` + `report_html` 本地渲染（**理想形态在 CLI**，实测产物：09-05 有 `.md` 也有 `.html`） | 设计债 |
| 5 | **工具面比 `CAPABILITIES` 声明的大**（todo/plan/subagent 未声明） | 待收口 |
| 6 | **cwd = `bestagent\`（代码库）+ 手握 pwsh**，防线只有 persona 里的"禁止列盘" → **和小画那次烧 30k 的条件同构** | 待收口（候选：分析/评估步把 cwd 收窄到岗位目录；pwsh 只在采集步开） |
| 7 | **①「匹配难度」无实证来源** | 见 §5-2 |
| 8 | **`collect_liepin.py` 关键字必 0 命中**（长串 AND）——新单现场复现 | 决策 31 已覆盖 |

---

## 7. 环境与命令（现查，别信快照）

```powershell
# 环境自检（换电脑第一件事）
C:\Users\84005\miniconda3\envs\lzstudy\python.exe -c "import framework_config; print(framework_config.check_env())"

# 桥 + 扩展 + 猎聘 tab 飞行前检查（只读）
C:\Users\84005\miniconda3\envs\lzstudy\python.exe data/_selftest_tmp/check_bridge.py

# 只读快照任意标签页（本场新增的探针，已 gitignore）
C:\Users\84005\miniconda3\envs\lzstudy\python.exe data/_selftest_tmp/peek_page.py h.liepin.com

# 看某次运行"花了几次请求/多少 token"（未压缩投影）
#   data\dsh_home\storages\session_projcache\sessions\<session-id>.json
#   → record.rows.turnBoundary / record.rows.tokenUsage
```

- 解释器 `C:\Users\84005\miniconda3\envs\lzstudy\python.exe`；面板 `streamlit run m3_chat.py`（cwd = `bestagent\`）；桥 `bridge-agent\`（:8080）
- 本单岗位目录 `bestagent\data\chat\J-CHAT-20260909-094907\`（新单：`J-CHAT-20260912-153231`）
- **两个浏览器通道**（上一场实测，别混）：
  - **参谋长的眼睛**（DSH 第三方插件）：**只读"你当前正在看的那一页"**；`list_tabs` / `open_tab` / `follow_tab` **全被拒**；切标签页后会暂停，需在右侧面板选「跟随当前页」
  - **小猎跑腿**（项目自带）：可按 **tab_id 精确读**；**长时间不应答 = 扩展没在跑**（实测 pending 5 分半，而正常 1.5 秒被领；alarms 周期仅 25s）——**别猜"睡一会就好"**

---

## 8. 新对话开场白（复制用）

> 你是本项目的**实施工程师**（小猎助手 · 猎头 AI 操盘手系统）。
> 先读三份：`工作文档\SDK运行时原理·交接文档.md`（**本场任务书：§2 十个问题 + §3 已实测事实，别重查**）＋ `工作文档\采集与沟通链路·衔接报告.md`（§2 猎聘实测结论）＋ `工作文档\工作模式·备忘.md`（谁是谁 / 命名 / 三层运行边界）。
> **一句话背景**：项目底座 09-11 已修回并验证（SDK 换代 pip/exe + 项目自带 dsh_home + 11 调用点收口；桥搬进仓库定名「小猎跑腿」；停止开关 A+B 落地）。09-11 晚~09-12 那场**没写码**：用**参谋长的眼睛**实读了猎聘页面、重定了采集流程（决策 **31/32**）。
> **本场目标**：**把「SDK 拉起的运行时」讲透**——老板原话：*"我就是一个司机，我也要知道发动机原理、转动原理。"* 按交接文档 §2 的 **10 个问题**逐节推进，**每节都要实测/源码证据，讲完一节停一次让他消化**。
> ⚠️ 上一场我说过"你不必懂发动机"——**那是判断错误，本场按老板要求纠正**；但仍要分清"司机该懂的原理"与"会随版本作废的内部细节"，让他自己决定深到哪。
> **纪律**：动手前对齐目的声明；小步验证 + 复盘；判断错不罚、不诚实必罚；**禁 bash（本机用 pwsh）**；小 JSON + 本地渲染；采集必须先出计划并经老板确认才真跑；**改代码前先只读调研并报工作量**。
> **环境**：python `C:\Users\84005\miniconda3\envs\lzstudy\python.exe`；面板 `streamlit run m3_chat.py`（cwd = `bestagent\`）；桥 `bridge-agent\`（:8080）。
> **顺带**：交接文档 §5 有 4 件**待老板拍板**的事（会卡住"一期：采集链拆分"开工），可在他想动手时提醒。
