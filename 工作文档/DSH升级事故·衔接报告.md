# DSH 升级事故 · 衔接报告（2026-09-10）

> 定位：**事故复盘 + 现状定性 + 方案候选**。老板 2026-09-10 被动升级 deepseek-harness 后，GUI 工作区/历史对话出问题，遂删除整个 `~/.dsh` 重建；本场为设计讨论对话（**只查证 + 讨论，未动任何代码**）。
> 本报告的作用：**让下一个对话不必重新侦察** —— 本场所有实测结论全部落在 §2。
> 依据《对话交接规范》：阶段完成 → 更新 PROGRESS → 写交接 → git 提交。

---

## 0. 一句话状态

老板**被动升级** DSH（旧版 → **v0.1.5-alpha.2**）后，GUI 侧连环出问题（C++ 编译器 / 浏览器助手插件 / 历史加载失败）→ 老板删除整个 `~/.dsh` 重建并重填 key；**项目资产全部无损**（文档/代码/旧会话 JSONL/业务数据），但**项目技术底座断了** —— m3_chat / auto_job 等所有走 SDK 的脚本现在跑不起来（旧启动方式 `cordis` / `session_root` / `launch_args_override` 已被新版 API 移除）；**"退回旧版"实测走不通**，只能向前适配新版；**浏览器助手插件待老板重装**。

---

## 1. 事故经过（老板口述，2026-09-10）

1. 原 harness = **最早版本**；今日弹出升级提示 → 老板点了升级。
2. 升级后接连出现问题：① **C++ 编译器**问题 → ② **dsh 浏览器助手插件**问题 → ③ 插件升级后出现
   **「历史加载失败：session assistant stream omitted its opted-in opening baseline（gateway/internal）」**。
3. 处置：**删除整个 `.dsh` 目录** → 重新填写 key。
4. 现状：GUI 可用（本场对话即跑在新版上）；**浏览器助手插件尚未重装**。

---

## 2. 已确认事实（本场实测，别重查）

### 2.1 丢失 vs 无损

| 项 | 状态 |
|---|---|
| `~/.dsh`（旧 GUI 工作区列表 + 历史对话） | ❌ 随删除丢失；**回收站无、git 无跟踪 → 不可恢复**（老板确认：**聊天记录无用**，记忆在文档，无所谓） |
| `工作文档\` 13 份 + git 仓库（事故前 HEAD `b868063`） | ✅ 全在 |
| **旧 SDK 实施对话历史 38 份 JSONL**：`bestagent\.sessions\--D-study-bestagent-bestagent--\`（2026-08-31 → 09-09） | ✅ 全在 |
| `bestagent\data\`（岗位目录 `chat\`、reports 产物、`business.db`、`usage\` 限速账本） | ✅ 全在 |
| `参考代码\` + 根目录 `智库交付侧岗位需求及说明.xlsx` | ✅ 全在（xlsx 仍为未跟踪） |
| 浏览器桥 `D:\study\lietou-agent\browser-agent`（bridge / extension / `.env` / `start_bridge.bat`） | ✅ 文件全在；**只是没在跑**（无 python 进程、8080 无监听）—— 与本次升级无关 |

> 结论：**对话是易逝的、文档是资产** —— 这次事故反向验证了《对话交接规范》有效（对话丢了，项目毫发无伤）。

### 2.2 升级事实

- 当前版本 **v0.1.5-alpha.2**（`git describe` = `dsh-v0.1.5-alpha.2`；HEAD `b2e3b2a`，2026-09-09）
- `C:\deepseek\deepseek-harness` 是**浅克隆**：`rev-list --count HEAD` = **1**，tag 总数 = **1** → 本地没有任何历史
- 新 SDK 入口包名**未变**（`from deepseek_harness import DeepSeekHarness`），但**启动参数换代**

### 2.3 底座断在哪（实测证据）

新版 `DeepSeekHarnessConfig` 接受的字段（实测打印）：

```
api_key, base_url, cwd, dsh_bin, dsh_home, env, initialize_timeout_seconds,
max_tokens, model, patches, profile, provider, reasoning_effort,
request_timeout_seconds, runtime_cwd, shutdown_timeout_seconds
```

**没有** `cordis` / `session_root` / `launch_args_override`。用 m3_chat 现在的旧参数实测构造：

```
RESULT: TypeError -> DeepSeekHarnessConfig.__init__() got an unexpected keyword argument 'session_root'
```

另：`framework_config.CORDIS_MINIMAL` = `DSH_ROOT/examples/jsonrpc-agent/minimal.cordis.yml`
→ **新版已无 `examples/` 目录**（该文件在本次 checkout 的 git 历史里从未存在过，`git log -- <path>` 为空）。

**影响面（小且集中）**：
- `bestagent\framework_config.py`（SDK 启动配置）+ `bestagent\m3_chat.py::run_assistant()`（唯一 `DeepSeekHarness(...)` 调用点）
- 修好这两处 → m3_chat / auto_job / 采集 / 评估 / 发岗**一起复活**
- **业务资产零改动**：方法论 / rules.md / 配方表 / 岗位目录 / 小 JSON + 本地 HTML 渲染 / business.db 全部与 SDK 解耦（"脚本定流程 + 数据展示分离"的红利）

### 2.4 "退回旧版" —— 实测不可行

| 退路 | 结论 |
|---|---|
| 主 checkout 用 git 退版本 | ❌ **浅克隆**（1 commit / 1 tag），无历史可退 |
| `参考代码\deepseek-harness-master`（旧快照，版本 `0.1.2-alpha.2`） | ❌ 它的 API 与新版**同代**（`profile`/`dsh_home`/`dsh_bin`，同样无 `cordis`）→ 救不了；且缺 `examples/jsonrpc-agent/minimal.cordis.yml` |
| Python 环境 / pip 缓存 | ❌ 从未安装过该包（一直 PYTHONPATH 注入源码），无副本 |

> 例外：若老板想起旧版当初**另有安装路径**（如某个全局 npm 目录），值得再挖一次。

### 2.5 新版运行时可用（好消息）

- `node -v` = **v24.13.0**；`python/sdk-runtime/runtime-bootstrap.mjs --help` **实测能起来**：
  `dsh: boot a DeepSeek Harness profile — an ordered stack of plugin-bundle patch layers under your own overrides.`
- → 新版**自带 bundled runtime**（`python/sdk-runtime`）：**以后不必再维护 `.dsh-staging` 那套 pnpm deploy 闭包**（长期更省事、更可迁移 → 对上决策 9 / 25）
- **profile 机制 = 旧 cordis 的继任者**（已摸清）：
  - `$DSH_HOME/profiles/<name>/package.json` 的 `dsh.profile.bundles` = bundle 列表
    （GUI 的 web profile 现为 `@deepseek-ai/dsh-base` + `@deepseek-ai/dsh-web-app`）
  - 同目录 `cordis.yml` = 空根条目（注释明写"勿改"）；`cordis.patch.yml` = **用户层覆盖（改这里）**
  - CLI：`--profile <name>`｜`--from-default-profile <name>`（从官方模板建自定义 profile）｜`--patch <path>`（可叠加）｜`--dump-config`
  - `dsh plugin --profile <name> add <包>` = 装插件（转发给 pnpm）

### 2.6 「历史加载失败」的真凶（已定位，**与浏览器助手插件无关**）

- 报错文本来自 `packages/api/session-controller/src/client/transport.ts:189`；同名测试
  `rejects an opted-in opening that omits its Assistant baseline`（`tests/transport.client.spec.ts:329`）
- 定性：**新版 Web 客户端拒绝加载旧格式会话**（旧会话缺它要的 "opted-in opening baseline"）= **升级自带的兼容缺口**
- **排除插件**：源码中搜不到"浏览器助手"（中/英）；官方 web profile 的两个 bundle 里也没有它
  → 它是**额外装进 `~/.dsh` 的插件**，随 `.dsh` 删除一起消失，所以现在"没注册"完全对得上
- 旧会话已删 → **此错不会再复现，可结案**

### 2.7 环境事实（新增，写进 HANDOFF §4/§5）

- **`npm.ps1` 被执行策略禁止**（SecurityError）→ 必须用 **`npm.cmd`**
- 本机**无 PowerShell 7**（延续 HANDOFF 教训 #4）
- 本沙箱内 `Get-NetTCPConnection` 不可用（端口占用查不到，需换方式）

---

## 3. 方案候选（本场**未拍板**，留待拍板）

| 层 | 内容 | 判断 |
|---|---|---|
| **手脚层**（SDK 调用） | 改 `framework_config.py` + `run_assistant()`：`cordis`/`session_root`/`launch_args_override` → `profile`/`dsh_home`（+ 可选 `dsh_bin`） | **必修，且集中一处**；先做**只读调研**（①profile 怎么组装 ②会话落盘怎么配 ③pwsh 工具 + 沙箱权限怎么给）再报工作量与风险 |
| **壳层**（对话界面） | m3_chat 1300 行界面 + v1.7.x 纪律，是否换成新版 harness 的 agent 形态（agent / goal / skills） | **可选、后置**：等老板亲手摸过新版 GUI 能力再拍板。注意：UI = 壳、产物 = 资产，换壳成本低于直觉 |
| **根因治理**（新增议题） | 本次事故根因 = **项目底座挂在 DSH 源码 checkout / 共享 `~/.dsh` 上**，GUI 一升级就把项目带崩。新版支持 `dsh_home` 参数 → 可让**项目自带运行时目录**，与 GUI **彻底解耦** | 建议纳入设计：一次投入，永久免疫同类事故 |

> **老板立场（本场）**：升级是**被提示点的**，不是主动想要新能力 → 目标 = **恢复能干活**，而不是"用上新版功能"。

---

## 4. 待办 / 下一步

1. 【老板】**重装浏览器助手插件** —— ✅ **已完成（2026-09-10 晚）**：`@yuxianglin/dsh-bridge-browser`（源码 `C:\deepseek\dsh-browser`，以 `link:` 装进 `~/.dsh/profiles/web`）；细节见 §7。
2. 【实施对话】**只读调研** —— ✅ **已完成（2026-09-10 晚）**：结论见 **§8**（新版 profile 机制 + 实测跑通 + 修复方案 + 工作量半天到一天 + 风险）。
3. 【拍板】手脚层修复方案（+ 是否让项目自带 `dsh_home` 与 GUI 解耦）。
4. 【挂起不变】本单 **J-CHAT-20260909-094907**（智库·机械工程师 12HC，已 accept）的 ②采集 / ③评估 / 发岗 —— 底座修好才能跑；
   发岗后流程设计场（见 `工作文档\发岗后流程·设计讨论衔接报告.md`）；沟通跟进 / 决策 18 展开场。
5. 【待定】根目录 `智库交付侧岗位需求及说明.xlsx` 去留。

---

## 5. 新对话开场白（复制用）

> 你是本项目的**实施工程师**（数字合伙人搭建）。
> 只读一份：`D:\study\bestagent\工作文档\DSH升级事故·衔接报告.md`
> （§2 全部是已实测事实，**别重查**；§3 方案候选；§4 待办）。
> 背景一句话：DSH 被动升级到 v0.1.5-alpha.2 → 项目 SDK 底座断（旧 cordis 启动方式被移除）；业务资产无损；退旧版不可行。
> 读完后用 3 句话确认：①当前位置 ②本次目标 ③执行计划。确认后再动手。
> 纪律：动手前对齐目的声明；小步验证+复盘；判断错不罚、不诚实必罚；禁 bash / 路径直接用 / 小 JSON+本地渲染；**改代码前先只读调研并报工作量**。

---

## 6. 附：如何安全关闭本服务（老板操作）

- 本服务 = 6 个 node 进程中的一个（本沙箱查不到端口占用，无法代定位 PID）。
- **正确关法**：回到你启动 GUI 的那个终端窗口，按 **Ctrl+C**。
- 若找不到窗口：任务管理器 → 详细信息 → 右键列头勾选"命令行" → 找含 `web` 的那个 node → 结束它。
  ⚠️ **别一把杀所有 node**（本机同时有 6 个 node 进程，可能有别的东西在用）。
- **关之前**：本对话的记录在 `C:\Users\84005\.dsh\sessions\--D-study-bestagent--\session-8312a8b5-*.jsonl`
  （可恢复，但按规矩**不指望它** —— 记忆看本报告）。
- **重开之后**：GUI 里重新打开 `D:\study\bestagent` 工作区 → 用 §5 开场白起新对话。

---

## 7. 附：`C:\deepseek` 目录勘察（2026-09-10 晚，老板装好浏览器助手插件后）

### 7.1 目录角色（**删东西前必读**）

| 路径 | 是什么 | 能否删 |
|---|---|---|
| `C:\deepseek\deepseek-harness` | **DSH 本体**（v0.1.5-alpha.2，浅克隆） | ❌ **不能删** |
| `C:\deepseek\dsh-browser` | **浏览器助手插件源码**（`@yuxianglin/dsh-bridge-browser` v0.0.4，作者 Yuxiang Lin，MIT，private） | ❌ **不能删** —— 它以 **`link:C:/deepseek/dsh-browser/packages/browser/bridge-browser`** 装进 `~/.dsh/profiles/web/package.json` 的 `dsh.profile.bundles`；删了插件即废 |
| `C:\deepseek\dsh-session-surgeon` | 第三方**会话文件修复器**（`xiaoshenming/dsh-session-surgeon` v0.2.0）：修 `~/.dsh/sessions/**/session.jsonl.zstd` 的磁盘级损坏（torn-tail / seq-gap-committed / 代理码元 / 缺消息 id 等），子命令 `scan / index / inspect / repair / compact / export` | ✅ 可删 —— **实测未装进任何 profile**（web profile 的 package.json 只列了 bridge-browser），与浏览器助手无关 |
| `C:\deepseek\sessions-backup` | 旧会话备份（7 个工作区目录，含 `--D-study-bestagent--`，mtime 2026-09-10 14:39） | 🟡 建议留（老板已确认聊天记录无用，但"升级前先备份"的习惯值得保留） |
| `C:\deepseek\cd`、`C:\deepseek\git` | 两个 **0 字节空文件**（创建于 2026-08-14 17:32:53） | ✅ 可删（命令笔误产生的垃圾） |
| `C:\deepseek\dsh-session-surgeon-分析.md` | 2026-09-10 16:06 的分析报告（另一会话产出） | 🟡 可留作参考 |

### 7.2 浏览器助手插件（对我们项目的意义）

- 形态：**token 认证的 WebSocket 载体 + Chrome 扩展 + `browser_*` 文本工具**（让 agent 驱动老板自己的 Chrome）。
- token 落 `~/.dsh/ext-bridge-token`；WebSocket 走 **DSH 自己的 web 端口**（代码：`ws://127.0.0.1:${ctx.httpServer.port}/ext/bridge`）
  → **不占独立端口，与我们项目 `browser-agent` 的 8080 桥不冲突** ✅
- ⚠️ 其 workspace / peerDependencies 钉在 dsh **0.1.2-rc.1**（最低支持），本机已 0.1.5-alpha.2（老板实测"插件好了"）。
- **新增待讨论议题（未展开）**：DSH 生态已有浏览器桥 → 我们自研的 `browser-agent`（Python bridge + Chrome 扩展 + 配方表 `execute_spec`）与之**功能重叠**：继续自研 / 借力 / 混合，是后续设计议题。

### 7.3 `dsh-session-surgeon` 与「历史加载失败」（交叉验证）

该项目的分析文档结论与本报告 §2.6 **独立一致**：全仓库 0 命中 `opening baseline` / `opted-in`；判定它更像 harness **加载/重放阶段的语义校验**问题，而非磁盘字节级损坏；建议"别手改、保留证据、上报上游"。
→ 两条独立证据同结论：**既不是会话文件坏了，也不是浏览器助手插件的锅**。

### 7.4 删除 `dsh-session-surgeon` 被"占用"的排查

- **可查到的线索**：该目录 `.git` 的 mtime = **2026-09-10 17:42:02**，而两个 node 进程（PID 2432 / 10176）**恰好也在 17:42:02 启动** → 那一刻确有进程在该仓库活动。
- **无法确定元凶**：本沙箱读不到 node 进程命令行（PS 5.1 无 `CommandLine`、WMI 不可用），`Get-NetTCPConnection` 亦不可用。
- **排查顺序（从便宜到彻底）**：
  1. 关掉所有可能开着它的窗口（资源管理器 / PyCharm / 终端 / 编辑器）→ 再删；
  2. **关闭 DSH 服务**（启动 GUI 的窗口 Ctrl+C）→ 再删 —— "原来的 node 进程"里就包含正在跑的服务本体；
  3. 还不行 → **改名**（`Rename-Item` 常能成功；**改名也失败才是真占用**）→ 改名后再删；
  4. 或换 cmd：`rmdir /s /q "C:\deepseek\dsh-session-surgeon"`；
  5. 还不行 → **重启电脑**，开机后第一件事就删（此时无任何占用）；
  6. 可选：Sysinternals `handle.exe` 精确定位持有者。

### 7.5 基座到底自不自带浏览器桥？（2026-09-10 实测：**不自带**）

老板问"deepseek-harness 基座是不是自带这个插件功能、我们是不是不需要它了"。实测证据：

| 检查 | 结果 |
|---|---|
| 基座源码搜 `browser_snapshot` / `browser_navigate` / `registerBrowserTools` | **0 命中** |
| monorepo `packages/` 顶层 49 个包（acp/api/attachment/boot/bundle/client/code-runtime/compaction/context/core/credentials/e2b/experimental/extensions/feedback/fs/goal/guard/hooks/host/identity/interaction/jobs/llm/lsp/mcp/plan/preset/runtime-diagnostics/sandbox/schedule/sdk/session/session-query/settings/shell/skill/spill/storage/subagent/subprocess/terminal/test-support/todo/typert/util/web/webhook/workflow/workspace） | **无任何 browser 包** |
| 基座 bundle | `@deepseek-ai/dsh-base 0.1.5-alpha.2`（agent 骨架/工具/沙箱/会话等基础件） |
| `browser_*` 工具来源 | 你装的第三方插件 `@yuxianglin/dsh-bridge-browser`（其 README 自述"注册纯文本的 `browser_*` 工具集"；web profile 的 `dsh.profile.bundles` 里把它加了进去） |

**结论：基座无浏览器能力，浏览器工具 100% 来自该插件。** 因此要分清两个问题：

- **问题一（DSH 工作台）**：装了它，GUI 里的 AI 才能自己看页面/点按钮（登录态保留）；以前只能靠老板复制粘贴。这是**个人工作台能力扩展**，与项目无关，删了不影响 DSH 本体。
- **问题二（猎头项目）**：项目**不该依赖**它 —— 项目要的是**确定性重复**（配方表 `group_id/value`；HANDOFF 教训 #2：自然语言循环会"条件没设上、抓到残留数据"），插件给的是**模型即兴操作**（快照编号，页面一变即失效）。可作为**探路 / 应急 / 对照**工具，但**不进入项目链路**。

**另一个实测发现（重要）**：Chrome 扩展的构建产物在 `C:\deepseek\dsh-browser\extensions\dsh-browser\dist`（2026-09-10 17:35 构建）✅，但 README 里安装器会复制到的 `~/.dsh/browser-extension` **不存在** → 说明未走一键安装器的那一步；**要真能驱动 Chrome，必须在 `chrome://extensions`（开发者模式）加载这个 `dist` 目录**。"插件注册进 profile" ≠ "扩展已加载"。

---

## 8. 只读调研结论（2026-09-10 晚 · **已实测跑通** → 修复方案 + 工作量 + 风险）

### 8.1 一句话结论

**新版 SDK 不再"手写 cordis 组合"，而是"选 profile + 打 patch"。** 我们旧 `minimal-pwsh-nonpty.cordis.yml` 想要的能力（文件工具 + pwsh 工具 + `danger-full-access` 沙箱 + 会话落盘 + persona 注入），新版内置 `sdk` profile **全都有**，且**已实测跑通真模型调用**。

### 8.2 实测证据（探针目录 `bestagent\data\_probe_dshhome\`，可复用为实施模板）

| 验证项 | 结果 |
|---|---|
| 最小一轮（`profile="sdk"`） | ✅ `finish_reason=completed`、回复"收到"、2.3s、13 events |
| 项目自带 `dsh_home` | ✅ 会话落 `<home>\sessions\--D-study-bestagent-bestagent--\<session-id>\session.v3.jsonl.zstd`（**与 GUI 的 `~/.dsh` 彻底隔离**） |
| 启动载体 `dsh_bin=<.cmd>` | ✅ 项目内 `.cmd` 包装（`node <checkout>\python\sdk-runtime\runtime-bootstrap.mjs %*`）**可被 SDK 直接 Popen**（实测 rc=0） |
| **persona 注入（`patches=`）** | ✅ patch 覆盖 `system-prompt` 后，模型回复**真的带 `[小猎]` 前缀** —— 项目灵魂可注入 |
| pwsh 工具 | ⚠️ 报 `spawn EPERM` —— **是我这个 DSH 会话的沙箱造成的**（workspace-write 禁"命名管道/被管道 stdio"，嵌套 spawn 必挂），**不是项目配置问题**；PyCharm 里没有这层沙箱 |
| `sdk-minimal` profile | ❌ **本机必崩**：`node-pty … reading 'destroy'` —— 因它内置 `terminal-pwsh: dsh-terminal-bash + shellDialect: pwsh`，本机无 pwsh.exe（正是 HANDOFF 教训 #4）。**→ 不要用 sdk-minimal** |
| 沙箱开关 | ✅ `sdk` profile：`mode = env DSH_PERMISSION_MODE ?? 'workspace-write'`；设 `danger-full-access` 时 `approval` 自动变 `never`（适配无头运行） |
| 旧会话续跑 | ❌ 格式换代（旧 = 无压缩 `session.jsonl`；新 = 压缩 `session.v3.jsonl.zstd`）→ 旧 `.sessions` 读不回来（符合"不赌会话记忆"，影响可控） |
| 两个 profile 共用 home | ❌ 会冲突（`sdk` 用 zstd、`sdk-minimal` 用 `compression: none`）→ 一个 profile 一个 home |

### 8.3 调用形态对照（迁移就这么改）

```python
# 旧（已作废）
from deepseek_harness import DeepSeekHarness
with DeepSeekHarness(
    provider="deepseek-official", model="deepseek-v4-flash", max_tokens=max_tokens,
    cwd=str(WORKSPACE), session_root=str(SESSIONS),
    cordis=str(cordis or CORDIS_MINIMAL),                    # ← 没了
    launch_args_override=("node", str(RUNTIME_BIN)),          # ← 没了
    env=env, request_timeout_seconds=REQUEST_TIMEOUT, shutdown_timeout_seconds=10,
) as harness: ...

# 新（实测可用）
with DeepSeekHarness(
    provider="deepseek-official", model="deepseek-v4-flash", max_tokens=max_tokens,
    cwd=str(WORKSPACE),
    dsh_home=str(DSH_HOME_PROJECT),     # 项目自带 home（解耦！）
    profile="sdk",                      # 工具面 + 沙箱 + 会话落盘都在这
    dsh_bin=str(DSH_BIN_CMD),           # 项目内 dsh.cmd 包装
    patches=(str(PERSONA_PATCH),),      # persona（原 DSH_SYSTEM_PROMPT 方式失效）
    env={**env, "DSH_PERMISSION_MODE": "danger-full-access"},
    request_timeout_seconds=REQUEST_TIMEOUT, shutdown_timeout_seconds=10,
) as harness: ...
```

### 8.4 修复方案（全部集中到 `framework_config.py` 一处）

1. **`framework_config.py` 新增**：`DSH_HOME_PROJECT = DATA/"dsh_home"`、`DSH_PROFILE = "sdk"`、`DSH_BIN = WORKSPACE/"tools"/"dsh.cmd"`（内容由 `DSH_ROOT` 生成）、**`make_harness(env, max_tokens)` 工厂**（内含 `DSH_PERMISSION_MODE`、`patches`、超时）；
2. **persona 单源**：`m3_chat.PERSONA`（常量）→ 运行前写入 `$DSH_HOME/profiles/sdk/cordis.patch.yml`（或临时 patch 文件），**避免两处维护**；
3. **11 个调用点替换**（`m1_run / m2_run / m2_eval_run / m3_auto_run / m3_chat / auto_job / greet_run / publish_run / probe_bash / sdk_verify` + 探针）：删 3 行 `sys.path` + import，`with DeepSeekHarness(...)` → `with make_harness(...)`；**先做 4 个主链路**（m3_chat / auto_job / publish_run / greet_run），老的一次性脚本最后再改；
4. **`check_env()` 更新**：去掉 `RUNTIME_BIN`/`CORDIS_*`，加 `dsh.cmd` + 项目 home + profile 自检。

### 8.8 实施中发现的两个必改项（2026-09-10 晚，老板在 PyCharm 实跑暴露）

**坑 A：`.cmd` 包装不能带非 ASCII 字符（已在探针里修掉）**
- 现象：PyCharm 终端里跑 → 运行时**启动即死**，stderr 是**中文 GBK** 报错 → SDK 的 stderr 读取线程按 UTF-8 解码 → `UnicodeDecodeError` → 最终误报 `TransportClosedError: runtime stdout closed`。
- ~~根因：PyCharm 终端环境变量缓存，里面没有 node~~ ⚠️ **该诊断已被证伪**：老板在**同一个 PyCharm 终端**里 `node -v` → `v24.13.0`（node 在）。
- **纠正后的根因**：`.cmd` 文件里有**中文注释**，而 cmd.exe 按 **OEM 代码页（本机 GBK/936）** 解析批处理 → UTF-8 中文注释被读乱 → cmd 报错（中文、GBK）→ 运行时启动失败 + SDK 日志线程解码崩。我在自己会话里没复现，是因为 DSH 会话的控制台代码页是 UTF-8，同一份文件被正确解析了。
- 修复（三保险，真正起作用的是前两条）：**纯 ASCII** + `chcp 65001` + 写死 node 全路径。
- 教训：**`.cmd`/`.bat` 一律只写 ASCII**（本机 `start_bridge.bat` 也有中文注释，属同类隐患，建议一并纯 ASCII 化）。


**坑 B（重要，必改）：session id 不能复用** ⚠️
- 实测（沙箱三连）：固定 id 第 1 次 ✅ → **同 id 第 2 次 ❌ `JsonRpcError: session "X" already exists`** → 换新 id ✅。
- 即 **`harness.run(prompt, session_id=X)` 在 X 已存在于该 home 时会直接报错**（文档所述"复用 harness + session id 延续对话"在本版对跨进程路径不成立）。
- **影响面（迁移必改）**：`m3_chat` 每岗固定 `session_id` 反复执行 → 第二次就废；`auto_job` 的**幂等续跑**（设计核心属性）、`m2_eval_run`/`greet_run` 的分批复用同理。
- **对策（且与项目设计一致）**：**每次运行用新 session id**（如 `<job_session_id>-<步骤>-<时间戳>`）。项目铁律是"**不赌会话记忆**"（每轮注入状态卡 + 路径），人类侧的连续性由 `transcript.json` + 产物承载 → **零损失**，反而更干净。
- 另：该行为在 **rc1（pip 版）复测同样存在** → 跨版本一致，**不是某一版的偶发 bug**，按"设计如此"对待即可（可选仍可上报上游确认）。

### 8.9 pip wheel（rc1）实测结论 + **最终方案定稿**（2026-09-10 深夜，全部由参谋长实测）

| 验证项 | 结果 |
|---|---|
| `pip install deepseek-harness-sdk` | ✅ 同时装 `deepseek-harness-runtime-bin 0.1.5rc1` = **229 MB 单文件 exe**（`…/site-packages/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-win-x64.exe`） |
| **exe 模式**起运行时（**不传 `dsh_bin` / 不注入 `sys.path` / 不用 node / 不用 checkout**） | ✅ `finish=completed`、5.3 s、persona 前缀 `[小猎]` 生效、会话落项目 home |
| persona patch 在 rc1 同样生效 | ✅（先排除过一次嫌疑：停用 patch 后报的是同一个沙箱错，与 patch 无关） |
| session 复用（rc1 复测） | ❌ 同样 `already exists` → **必改项确认，与版本无关** |
| profiles / patches / 沙箱 / 会话格式 | 与 alpha.2 checkout 一致（`profile="sdk"`、`DSH_PERMISSION_MODE`、`patches`、`<home>/sessions/<slug>/<sid>/session.v3.jsonl.zstd`） |
| ⚠️ 交付细节 | **exe 首跑要把内置文件自解压到 `%USERPROFILE%\.cache\pkg\<hash>`**（实测约 20 MB）→ 目标机器该位置必须可写（受限/只读环境需注意）。参谋长本会话沙箱不允许写那里，是靠探针里把 `USERPROFILE` 重定向到工作区才验通的 |

**最终方案（定稿，交实施场执行）**

1. **首选（pip wheel / exe 模式）**：`requirements.txt` 固定 `deepseek-harness-sdk==0.1.5rc1`；
   `framework_config.make_harness()` 内：`profile="sdk"`、`dsh_home=<项目>\data\dsh_home`、`patches=(persona patch,)`、`env={DEEPSEEK_API_KEY…, DSH_PERMISSION_MODE: "danger-full-access"}`、**不传 `dsh_bin`**；
   同时**删掉全部 `sys.path.insert(…checkout…)`** —— 否则 checkout 源码会**遮蔽** pip 装的包。
2. **兜底（checkout + `tools\dsh.cmd`）**：仅在目标机器不能 pip 时启用（已实测；`.cmd` 必须纯 ASCII + `chcp 65001` + 写死 node 路径）。
3. **必改：session id 每次运行唯一**（如 `<job_session_id>-<step>-<ts>`），与"不赌会话记忆"铁律一致，零损失。
4. 11 个调用点统一走工厂；`check_env()` 自检（SDK 版本 / 项目 home / profile / persona patch 是否存在）。
5. **剩余风险**：目标机器 `%USERPROFILE%\.cache` 可写；pip 源可达（内网需镜像）；`.bat/.cmd` 一律 ASCII。



### 8.5 顺带扔掉两个旧包袱

- **不用再按任务切 cordis**（旧：`CORDIS_MINIMAL` 纯文件 / `CORDIS_PWSH` 采集）→ `sdk` profile 两个工具面都有（副作用：分析类任务也能看到 pwsh，可选收窄，非必须）；
- **不用再维护 `.dsh-staging` 闭包**（pnpm deploy 那套）→ 新版自带 runtime。

### 8.6 工作量（诚实估计）

| 阶段 | 内容 | 估计 |
|---|---|---|
| A 核心改造 | framework_config 工厂 + `dsh.cmd` + persona patch 单源 | 1–2 h |
| B 调用点替换 | 11 文件机械替换（先 4 个主链路） | 1–2 h |
| C 冒烟 | 起 streamlit → 小猎对话一轮 → ②采集真跑（需桥 + 猎聘登录态） | 1–2 h |
| D 缓冲 | profile / 会话 / 未知坑 | 半天 |
| **合计** | **主链路恢复**（不含跑真单） | **半天到一天** |

### 8.7 风险与待老板确认

1. **pwsh 工具必须你在 PyCharm 里冒烟一次**（我的沙箱必然 EPERM）—— 这是唯一"我验不了"的环节，也是采集链路的关键；
2. **会话格式换代**：老岗的历史对话读不回来（影响可控，因每轮都注入状态卡）；
3. **`dsh.cmd` 内含 checkout 路径** → 由 `framework_config` 生成 + `check_env()` 自检；**将来若 `pip install deepseek-harness-sdk`（exe 模式）可彻底退休**（我这边 pip 查询超时 = 沙箱无网，请你在 PyCharm 试一次该命令）；
4. 工具面变宽可后续收窄（给 `sdk-minimal` 打 patch 关掉 `pty` / `terminal-pwsh`，额外工作）；
5. 探针目录 `bestagent\data\_probe_dshhome\` 为临时产物（已 gitignore），实施时可复用其 `dsh.cmd` / `smoke.py` / `persona.patch.yml` 作模板，用完清理。


