# DSH SDK 技术评估（数字合伙人技术底座）

> 日期：2026-08-31 ｜ 状态：✅ 可行性已验证 ｜ 关联：`工作文档\设计方案.md`、`PROGRESS.md`
> 结论先行：**DSH Python SDK 可以作为"数字合伙人"的技术底座——headless、无人值守、可定制、能力与 DSH Web agent 同源。**

---

## 1. 验证结果（Windows 本机，旧版 dev 模式，2026-08-31 实测）

| 验证项 | 结果 | 说明 |
|---|---|---|
| SDK 客户端导入 | ✅ | `deepseek_harness`（lzstudy conda 环境 + 源码 PYTHONPATH） |
| headless runtime 启动 | ✅ | dev node 模式：pnpm deploy 闭包 `.dsh-staging` + 补 16 个 workspace 插件包 |
| DeepSeek API 调用 | ✅ | `deepseek-v4-flash` 真实返回 |
| 工具调用（bash 读文件） | ✅ | 读取 `设计方案.md` 并中文总结出 5 个章节标题 |
| 会话持久化 | ✅ | JSONL 落盘（`bestagent\.sessions\`），同 session_id 可续聊 |
| 授权/无人值守 | ✅ | 纯环境变量 `DEEPSEEK_API_KEY`，无 GUI、无人工 |
| 意外发现 | ✅ | node-pty 在 Windows 有 conpty 原生支持（官方文档"不支持 Windows"已过时） |

**验证脚本**：`bestagent\sdk_verify.py`（用法：`<lzstudy python> sdk_verify.py --env-file <path/.env>`）

**Windows 踩坑记录（下次直接复用）**：
1. 官方 runtime wheel 无 Windows（旧版）→ dev node 模式：`pnpm deploy`（hoisted）生成闭包；
2. deploy 闭包缺 16 个 workspace 插件包（legacy hoist 缺陷，构建脚本靠 `restoreLegacyHoists` 补）→ 从 `python/sdk-runtime/node_modules` 旧闭包批量 robocopy（排除 node_modules 子目录）；
3. 沙箱权限：pnpm/pip 写系统目录需升级权限；venv ensurepip 也会被拦，用现成 conda 环境（lzstudy）最省事。

---

## 2. 版本状况（新旧对比 + 发布状态）

| 项 | 版本 | 状态 |
|---|---|---|
| 在用（DSH Web 运行环境） | `0.1.0-rc.8`，`C:\deepseek\deepseek-harness` | ✅ 稳定运行，**勿动**（当前对话跑在上面） |
| GitHub master 源码 | `0.1.2-alpha.2`，`参考代码\deepseek-harness-master` | 架构重构；**官方支持 Windows**（platforms.json 含 win-x64） |
| PyPI `deepseek-harness-sdk` | 挂着 `0.1.1rc1` | ⚠️ **Windows runtime wheel 未发布**，pip 只能装到 0.0.0.dev0 占位包（已卸载） |

**新旧架构差异**：

| 维度 | 旧版（已验证） | 新版（master） |
|---|---|---|
| 启动 | 独立 `dsh-jsonrpc-agent` bin + 手传 `cordis.yml` | **`dsh` CLI + `--profile sdk`** |
| 核心参数 | `cordis=`, `launch_args_override=` | `dsh_home=`（必填）, `profile=`, `patches=`, `reasoning_effort=`, `base_url=`/`api_key=` |
| 插件定制 | 手写 cordis.yml | **profile + bundle**：`dsh plugin --profile sdk add file:...` |
| Windows | 官方 non-goal（手工 dev 闭包） | 官方支持（等 wheel 发布或源码构建） |
| 系统 Node | dev 模式需要 | 不需要（runtime 自带封闭依赖） |

**升级决策**：暂不升级。理由：当前环境稳定；新版 alpha 且兼容性破坏预告；对 SDK 无即时收益（win wheel 未发布）。升级时机 = 官方稳定版 或 PyPI 出 win wheel；升级前先 git tag 备份 + 新目录试跑。

---

## 3. 能力对照：DSH Web agent（现在） vs SDK 产品（将来）

**核心结论：能力同源**——SDK 拉起的与 Web 是同一引擎（Cordis 插件体系），工具能力取决于 profile 挂载了哪些插件。当前 packages 里可挂的插件已覆盖 Web 绝大部分能力：

| 能力 | Web（现在） | SDK 产品 | 插件 |
|---|---|---|---|
| 文件读写 | ✅ | ✅ | dsh-tool-fs / dsh-fs-local / dsh-tool-str-replace-editor |
| 命令执行 | ✅ | ✅ 已验证 | dsh-tool-bash-persistent / dsh-pwsh-local |
| 网页搜索 | ✅ | ✅ | dsh-web-search-deepseek / exa / perplexity |
| 子代理 | ✅ | ✅ | dsh-tool-subagent / dsh-subagent-fork-in-process |
| 长目标 | ✅ | ✅ | dsh-tool-goal / dsh-goal-round-driver |
| 工作流编排 | ✅ | ✅ | dsh-tool-workflow |
| 技能 skill | ✅ | ✅ | dsh-tool-skill / dsh-skill-filesystem |
| 外部工具（MCP） | ✅ | ✅（runtime 内置客户端） | dsh-mcp-client |
| 会话记忆 | ✅ | ✅ 已验证 | dsh-session-persistence-jsonl / sqlite |
| 浏览器操作 | ✅ 内置 bridge | ⚠️ 需接入 | 挂 **browser-agent**（用户自有，已验证）或 DSH 浏览器插件 |
| Web UI / 客户端插件 | ✅ Web 独有 | ❌ 无 GUI（headless） | —（业务上不需要） |

**SDK 产品比 Web 更强的地方**：
- persona 完全定制（"你是猎头助理：先思考、信息不足必提问"）；
- 无人值守、可定时/事件触发、可嵌入现有 Python 流水线；
- 只装业务需要的插件（能力收敛、token 可控）。

---

## 4. 目标架构（数字合伙人第一版）

```
外部调度（Python 脚本 / 定时任务 / 事件）
        │ run(任务, session_id)
        ▼
DSH SDK agent（headless runtime）
  ├─ profile：sdk-minimal 起步（bash + editor + JSONL 会话）
  ├─ persona：猎头业务规则（强制思考、信息不足提问、合规护栏）
  ├─ 挂载工具：
  │    ├─ browser-agent（Chrome 扩展 + bridge → MCP/工具接入）＝浏览器手脚
  │    └─ 领域方法（岗位分析/匹配/话术/清洗）＝业务判断
  ├─ 会话持久化（JSONL）＝跨任务记忆
  └─ 子代理（subagent）＝复杂任务拆解
        ▼
输出：结构化结果 / 报告文件 / 事件通知
```

**业务闭环（对应蓝图）**：贴 JD → 自动岗前分析 → browser-agent 搜人采集 → 匹配排序 → 报告 → 待人工拍板清单。可逆动作全自主，不可逆动作（打招呼/承诺）留闸门。

---

## 5. 遗留决策（进入架构讨论时定）

| # | 问题 | 现状 |
|---|---|---|
| 1 | 部署平台：Windows（dev 闭包/自建 exe）vs Linux（官方 wheel） | Windows 已通；3060 服务器电源老化是隐患 |
| 2 | 浏览器接入方式：browser-agent 包成 MCP server vs 直接工具 | browser-agent 已有 bridge（127.0.0.1:8080），包 MCP 较干净 |
| 3 | 新版迁移：等 win wheel vs 源码构建 | 暂不迁移，等发布 |
| 4 | `.dsh-staging`（~200MB dev runtime）保留/清理 | 保留（SDK 运行依赖），写进文档 |
| 5 | 模型分层（本地 vs 云端） | 未定，等蓝图讨论 |
