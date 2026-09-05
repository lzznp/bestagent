# 交接包：猎头 AI 操盘手系统（数字合伙人）

> 生成时间：2026-09-01 晚 ｜ 交接方式：设计讨论 + 验证周 + M2 全链路验证对话 → 新对话
> 更新时间：2026-09-01 深夜（框架整合 v1.0 完成后更新，见 §0/§3 新增小节）；2026-09 M3 设计对话收尾后更新（步骤制模型 + 授权矩阵 §7 v0.1 试用默认 + M3 界面实施要点，见 §7）；2026-09-02 M3 界面 v1 交付后更新（§0/§6/§7，详见 PROGRESS「M3 界面 v1 实施记录」与 `工作文档\M3界面v1·完工报告.md`）；2026-09-04/05 对话收尾更新（北极星=v1.6.7 实测，见 §0/§7 与 PROGRESS「2026-09-05 会话收尾」）
> 新对话开场顺序：**本文件** → `工作文档\设计方案.md` → `工作文档\SDK 技术评估.md` → `工作文档\对话交接规范.md` → `工作文档\PROGRESS.md` → `工作文档\协作工作流草案.md`（可选）→ `工作文档\授权矩阵.md`（可选）→ 再问环境

## 0. 一句话状态

**数字合伙人已从"验证脚本集"整合为 v1.0 框架**：统一入口 `run_pipeline.py` + 集中配置 `framework_config.py`；换岗试跑（中国移动 NLP 应届博士岗）全链路验证通过，业务库 307/307。**M3 对话式汇报面板已迭代到 v1.6.7（2026-09-05，m3_chat.py）**：①②③+发岗文字+入库+打招呼清单全部接入并真实验证（医药单 3 岗/311 人/311 评估已入库）；右侧报告栏（产物按步骤分组点开即用）；状态卡(state.json)兜底记忆；能力边界诚实化；成长账 records.jsonl+rules.md。**当前北极星 = 老板在 PyCharm 实测 v1.6.7**（右侧报告栏 + 💬打招呼清单：赵/章/朱话术与猎聘直达链接），详见 PROGRESS「2026-09-05 会话收尾」节。**战略定位（老板拍板）**：Streamlit = 临时壳，UI 是壳/流程产物数据是资产（产物全文件+库，换壳不废）；远期愿景=贴 JD 全自动（自动发岗/采集/评估/甚至打招呼沟通），边界问题将来单独拍板（联系类动作可能仍留人工）。v1 卡片面板 m3_ui.py 保留并存。

## 1. 背景（重要，读一遍就懂用户）

- 用户 = **非专职程序员**（Python 爱好者），做猎头业务，用 AI 改造工作一年（4 代猎头系统 + 1 个机器人项目）。
- 一年做了：岗位招聘（本地14B+向量，弃）→ 单机版（DeepSeek API，弃）→ wails 智猎助手（在用，免费产品）→ lietou-agent 多agent（M1-M5 完工，付费 exe）；另有机器人项目（ESP32 固件 + 后台，暂停）。
- 今年最深的感悟（用户原话）：**AI 加速了"做"，但没有加速"想"**——工具越快越要先想清楚，否则高效地做错（固件项目 MCP 弯路教训）。
- 用户工作方式反思（lietou-agent P6 记录 + 2026-09-01 讨论）：旧"复制粘贴循环"（PyCharm+网页版+codewhale 侦察）慢且累，容易带偏；新方向 = 人做"定目标/派活/验收/纠错"，agent 做"侦察/实施/测试/汇报"（见《协作工作流草案.md》，**可选非强制**）。

## 2. 关键决策（详见设计方案 §3，15 条）

| # | 决策 | 一句话 |
|---|---|---|
| 3 | 技术底座 | **DSH Python SDK**（已验证 Windows 全链路，headless） |
| 5 | 产品愿景 | 数字合伙人：自主+汇报+信任演进+双向成长 |
| 7 | 验证策略 | **验证周**：最小实验先行，不做大规划 |
| 8 | 协作规矩 | ①动手前对齐"目的声明" ②小步验证+回顾 |
| 11 | 记忆实现 | 三层：SDK JSONL（会话）+ SQLite（业务，复用 wails 表）+ MD（偏好） |
| 12 | 工作界面 | 文件 Inbox（验证周）→ Streamlit 面板（M2/M3）→ 语音机器人（远期） |
| 13 | 变现路线 | 后置；倾向"硬件+软件"整机，非纯软件；防复刻靠配方/数据/硬件三层 |
| 14 | SKILL 范围 | 只提炼方法论，代码资产 90% 原样复用 |

## 3. 已完成的验证（2026-09-01，全部真实跑通）

### M1.1 验证周·最小实验（岗前分析）
- 真实禾蛙 JD ×2（GPGPU 架构师 17分/优质/接单；教育岗 10分/普通/沟通）→ SDK agent 自主读手册+JD → 评分/4组关键字/报告/老板汇报，判别力成立
- 资产：`bestagent\m1_run.py`（--jd/--report/--session 参数化）

### M2 链路扩展（采集→评估→汇报→限速→入库）
- **采集**：`collect_liepin.py`（配方表 execute_spec 路径，自动发现猎聘 tab，多关键字批量+去重，限速集成）——真实搜 GPGPU/技能词，累计采集 293 条、去重 277 人
- **评估**：`m2_eval_run.py`（SDK agent 读 JD+池子+方法论 → pool_quality + match_candidate 逐人评分；支持 --start/--end/--skip-pool 分批；`merge_report.py` 合并）——30/120/144/29 人池子全评估过
- **自主闭环**：`m3_auto_run.py`（agent 用 pwsh 自己跑采集脚本→读结果→评估→汇报）一次跑通（搜"海光"29 人，如实报告池子"差"不粉饰）
- **限速**：`quota.py`（记账+限额+随机延迟；默认 20 搜索/200 提取/天，`data\usage\quota_config.json` 可调）
- **业务库**：`import_to_db.py` 复用 wails 表（jobs/candidates/match_results/candidate_events/pool_samples）→ `bestagent\data\business.db`（1 岗 + 277 候选人 + 277 评估）
- **环境突破**：bash 工具 Windows 不可用 → 补装 dsh-tool-pwsh 包 + `minimal-pwsh-nonpty.cordis.yml`（dsh-pwsh-local 非 PTY，兜底 PowerShell 5.1）→ agent 能执行命令了

### 框架整合 v1.0（2026-09-01 深夜，详见 PROGRESS.md 对应小节）

- **统一入口**：`run_pipeline.py` —— `python run_pipeline.py --jd data/inbox/xxx.txt --env-file .env` 全链路（①岗前分析 ②采集 ③评估自动分批≤72/批+自动合并 ④**直写 business.db** → 老板汇报）；`--step analyze|collect|eval|import` 单步、`--keywords/--conds/--requirements` 覆盖、`--skip-collect`、`--dry-run`
- **集中配置**：`framework_config.py` —— 所有路径相对定位或环境变量覆盖（DSP_WORKSPACE / DSH_ROOT / BROWSER_AGENT_PATH / DSP_MODEL / BRIDGE_URL），含 `check_env()` 自检、`load_env_file()`；**换电脑只改这里**
- **模块函数化（保留独立运行）**：m1_run.analyze_job / m2_eval_run.eval_pool / collect_liepin.collect / import_to_db.write_to_db
- **换岗试跑验证 ✅（北极星）**：新 JD「AI应用开发工程师（NLP）·中国移动」（应届博士/C9/QS50/≤30岁/北京）全链路通过——分析 16 分优质/建议沟通（判别力成立）；**条件筛选首次真实生效**（education=博士/博士后 + years=应届生 + city_current=北京，30/30 命中 2026-2027 毕业窗口，对比 GPGPU 轮整页端走）；评估池子「中」4高/4中/22低，捞出中科院林**/清华张**/北大吴** 真实 C9 博士；直写库 +30 → 库共 307/307
- **院校 C9/QS50 猎聘无筛选项**（school 组只有 211/985/双一流/海外留学）→ 只能后置评估过滤（预期内）；活跃度筛选对"应届生"岗有悖论（应届普遍不活跃，别设）

## 4. 环境备忘 ⚠️ 新对话开局现查，勿信本快照

| 项 | 值 / 查法 |
|---|---|
| SDK 客户端 | `C:\Users\84005\miniconda3\envs\lzstudy\python.exe`（conda，已装 pydantic 2.12） |
| SDK 源码 | `C:\deepseek\deepseek-harness\python\sdk\src`（旧版 0.1.0-rc.8，PYTHONPATH 注入） |
| dev runtime | `D:\study\bestagent\bestagent\.dsh-staging`（pnpm deploy 闭包，已补 16 插件 + tool-pwsh ×2 包） |
| 默认 cordis | `C:\deepseek\deepseek-harness\examples\jsonrpc-agent\minimal.cordis.yml`（fs/editor，无需执行命令的任务用） |
| **pwsh cordis** | `D:\study\bestagent\bestagent\minimal-pwsh-nonpty.cordis.yml`（**需要执行命令的任务必须用它**；系统无 PowerShell 7，PTY 模式会崩 node-pty，勿用 minimal-pwsh.cordis.yml） |
| ⚠️ 沙箱 | **SDK runtime 跑命令类任务（m3_auto_run.py / probe）必须在 danger-full-access**，否则 node spawn 子进程 EPERM；纯 fs/editor 任务（m1/m2）默认权限即可 |
| API key | `D:\study\bestagent\参考代码\lietou-agent\browser-agent\.env`（只读，不打印） |
| 会话持久化 | `D:\study\bestagent\bestagent\.sessions\`（JSONL） |
| 浏览器桥 | 活体 `D:\study\lietou-agent\browser-agent`，bridge `http://127.0.0.1:8080`（curl /api/health 现查；不在则 `python bridge/server.py` 拉起，Chrome 扩展 + 猎聘登录态需用户在浏览器确认） |
| 猎聘 tab | `collect_liepin.py` 自动 list_tabs 现查（勿手写死 tab_id） |
| 业务库 | `D:\study\bestagent\bestagent\data\business.db`（SQLite，wails 表设计） |
| DSH Web | `http://127.0.0.1:3080`（旧版，勿动；升级决策=暂不升级） |
| 框架配置 | `bestagent\framework_config.py`（所有路径集中；环境变量 DSP_WORKSPACE/DSH_ROOT/BROWSER_AGENT_PATH/BRIDGE_URL/DSP_MODEL 覆盖；自检：`python -c "import framework_config; print(framework_config.check_env())"`） |
| git | `D:\study\bestagent` 已 git init（.dsh-staging/.sessions 已 ignore），基线提交 2026-09-01 |

## 5. 关键教训（新对话别重踩）

1. **动手前先对齐目的声明**——AI 干活快，方向错就白干（用户两次强调）。
2. **采集必须走配方表 execute_spec**（`collect_liepin.py` 已封装）——用 /api/agent/run 自然语言循环会"条件没设上、直接 extract 页面残留结果"（实测采到青岛无关 40 条）。
3. **bash 工具在 Windows 不可用**（连 echo hello 都 File not found）；**pwsh 组合**（minimal-pwsh-nonpty.cordis.yml）可用，但 **SDK runtime 需 danger-full-access** 否则 spawn EPERM。
4. **不要配 terminal-bash + shellDialect: pwsh（PTY 模式）**——系统无 pwsh.exe，node-pty 直接崩（reading 'destroy'）。
5. **大池子评估分批 ≤72 人/批**（32768 token 上限，120 人已极限）；用 m2_eval_run.py --start/--end + merge_report.py 合并。
6. **agent 写的 JSON 带 UTF-8 BOM**——读取一律 utf-8-sig。
7. **公司名做关键字有同名噪音**（"海光"→食品/光电/贸易）；技能关键字（GPGPU/ROCm/CUDA/编译器/Runtime）更准（P6 教训印证）。
8. **限速默认 20 搜索/200 提取/天**（quota.py），防账号风控；打招呼（50/天）永远留人工闸门。
9. **新版 SDK 勿用**（master 0.1.2-alpha.2 架构大改 + Windows wheel 未发布），继续旧版 API。
10. 参考代码 `D:\study\bestagent\参考代码\` 只读素材库（README.md 有索引），活体在 `D:\study\lietou*`。
11. **条件筛选配方组已验证可用**（education=博士/博士后、years=应届生、city_current=北京…）——新 JD 采集务必用，前置过滤比后置评估省 token 提准；⚠️ 院校 C9/QS50 猎聘筛不掉（school 只有 211/985/双一流/海外留学）；⚠️ 活跃度对应届岗别设（应届普遍不活跃会筛空）。
12. **run_pipeline --step 要重复 flag**（`--step eval --step import`，不能 `--step eval import`）；`--skip-collect` 复用采集时文件名必须匹配（collected_<jd 文件名>.json）。

## 6. 交接说明

- 工作区 `D:\study\bestagent`：
  - `工作文档/`（8 份：交接规范/设计方案/PROGRESS/SDK 技术评估/协作工作流草案/授权矩阵/本文件 + **M3界面v1·完工报告**）
  - `bestagent/`（活代码：**run_pipeline.py 统一入口 / framework_config.py 集中配置 / m3_ui.py M3 汇报面板（2026-09-02 新增）** / m1_run/m2_run/m2_eval_run/m3_auto_run/collect_liepin/import_to_db/quota/merge_* /dump_jd/export_pool/explore_* /probe_bash/sdk_verify + minimal-pwsh-nonpty.cordis.yml + data/）
  - `data/inbox/`（JD 输入：jd_1 GPGPU 岗 / jd_user_001 教育岗 / 车载测试岗）｜ `data/outbox/`（采集+评估报告）｜ `data/prompts/`（方法论 3 份）｜ `data/usage/`（限速账本）｜ `data/business.db`（业务库）
  - `参考代码/`（素材，只读）
- **bridge 由会话后台 job 拉起，新对话先 curl http://127.0.0.1:8080/api/health 现查**，不在就重启。

## 7. 新对话如何开始

1. 按开场顺序读文档（见文件头）。
2. 用 3 句话确认：①项目当前状态 ②本次目标 ③执行计划。**确认后再动手**。
3. 开场白模板（可直接复制给实施对话）：
   ```
   你是本项目的实施工程师（数字合伙人搭建）。
   先读交接包：D:\study\bestagent\工作文档\HANDOFF.md，按其中"开场顺序"读完相关文档。
   读完后，用 3 句话向我确认：①项目当前状态 ②本次要完成的目标 ③你的执行计划。
   确认后再动手。边界：动手前先对齐目的声明；小步验证，做完回顾。
   ```
4. 立即可以做的方向（按优先级，2026-09-05 更新；框架 v1.0 + M3 对话面板 v1.6.7 就绪）：
   - **★ M3 面板 v1.6.7 实测（当前北极星）**：`streamlit run m3_chat.py`（lzstudy 解释器）→ 一岗一会话、右侧报告栏（按步骤分组点开即用）、动作按钮按状态亮/灰、💬打招呼清单（③后生成：入围者每人 概况/匹配点/先核实/话术1·2 + 猎聘直达链接）；本轮验证：①报告栏分组/预览顺不顺手 ②打招呼清单质量（医药单 赵66/章62/朱55 应列入、杨45 排除并备注，链接可新标签打开）；实测反馈见 PROGRESS「2026-09-05 会话收尾」
   - **随后候选**：医药单真实业务闭环（澄清年限口径→补采→照清单打招呼→记 events）→ 成长账首笔+rules.md 首条 → 多岗总览（待我审阅收件箱）→ 桌面化(PySide6/wails)与全自动编排/边界讨论（远期，UI=临时壳的定位下不急）
   - **agent 自主动态优化**：agent 看评估结果 → 自己决定加/改条件 → 重采（多轮寻优闭环；工具已齐：pwsh + 配方表 + run_pipeline 参数化）
   - **补采**：技能关键字定向补采（NLP 岗 agent 建议 Agent/智能体/MCP 补一轮；限速已生效放心跑）
   - **换电脑试跑**（验收方式，不急）：框架已配置化，装环境+拷代码即可
   - 新 JD 直接用：`python run_pipeline.py --jd data/inbox/<新JD>.txt --env-file <path/.env>`（默认全链路）
   - v1 卡片面板（m3_ui.py）保留：`streamlit run m3_ui.py`（读 business.db 307 条；确认/纠错/放行 卡片形态）

### M3 界面 v1 实施要点（2026-09 设计对话产出，给实施对话）

> ✅ 状态：2026-09-02 已按此交付 v1（`bestagent\m3_ui.py`），完工报告见 `工作文档\M3界面v1·完工报告.md`；以下要点保留为设计基准，老板试用后迭代。

- **形态**：Streamlit 本地面板（老板日常"呈报窗口"；决策 12 落地），在 PyCharm 中 `streamlit run` 使用
- **数据源**：`bestagent\data\business.db`（jobs/candidates/match_results/pool_samples…，wails 表设计，307 候选人/307 评估已在库）
- **v1 功能（最小可用，边用边改）**：
  1. 岗位列表 → 点进一个岗 = 一条流程（步骤时间线：①岗位分析 → ②候选人评估 → ③联系跟进[远期]）
  2. 每步骤一份**报告卡片**（分析结论/关键字实验/池子评级/推荐 top 清单，数据从库读）
  3. 卡片上按钮：**确认 / 纠错（写批注）/ 放行**——纠错动作即"成长数据"记录（记"采纳/纠错"账，供日后定放手阈值）
  4. 顶部状态条：现在卡在哪个步骤、等你什么动作
- **行为默认（v0.1，授权矩阵 §7 处理结果）**：步骤报告后 agent 默认停住等；纠错记录按"岗位→步骤"归档 + 可提炼规则进方法论（先落文档/JSON 即可，界面不做复杂存储）
- **验收**：面板能读库展示真实 307 条数据、能对一个岗位走"看报告→确认/纠错"全流程；界面形态老板试用后反馈迭代
- **不做**：不做复杂登录/多用户/美化；步骤 ③ 联系跟进不纳入 v1；与 3080 不冲突（它读库展示，agent 跑链路照旧）

---

## 8. 设计补充（2026-08-31 晚 + 09-01，历史保留）

### 8.1 记忆分层方案（决策 11）
L0 会话记忆（SDK JSONL）→ L1 业务记忆（SQLite，复用 wails 表，**2026-09-01 已落地**）→ L2 偏好记忆（MD，MEMORY/SKILL）→ L3 海量检索（RAG，⛔ 后置）。

### 8.2 工作页面/沟通方式（分阶段）
验证周文件 Inbox/Outbox（零 UI，已实践）→ M2/M3 Streamlit 面板（汇报卡片+确认/纠错按钮）→ 远期语音机器人。

### 8.3 实体形态构想（远期）
Wails 重构小智后台 = 大脑+工作台，小智机器人固件 = 纯语音终端（STT/TTS）；验证周只做 SDK agent 本体。

### 8.4 变现与防复刻（决策 13）
变现后置；三层组合：软件层（🟡 可抄）+ 配方/数据层（🟢 服务器可下发）+ 硬件层（🔴 抄不动，小智整机）；授权复用 wails license 方案。

### 8.5 授权矩阵（决策 10 落地，2026-09-01）
`工作文档\授权矩阵.md`：可逆动作全自主 / 不可逆动作留闸门（打招呼/下载联系方式/约面试/推荐客户=🔴 待拍板清单；微信电话/谈薪资=🔴 永远人工）；执行层闸门（不挂打招呼工具）+ 输出层闸门（待拍板清单）；汇报粒度=信任刻度；限速已落地（quota.py）。
