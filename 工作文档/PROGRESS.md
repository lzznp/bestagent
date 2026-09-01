# 项目进度（PROGRESS）· 猎头 AI 操盘手系统

> 项目工作区：`D:\study\bestagent\bestagent`（代码）｜ `D:\study\bestagent\工作文档`（文档）
> 设计依据：`需要讨论的工作蓝图.txt` + 参考素材（`参考代码\README.md` 索引）
> 本文件是跨对话进度档案，**每个阶段结束必须更新**（见《对话交接规范》）

## 里程碑状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 素材库整理 + 交接规范定稿 | ✅ 完成（2026-08-31） |
| M0.5 | **DSH Python SDK 最小验证（Windows 本机 dev 模式）** | ✅ 完成（2026-08-31）：headless agent 拉起 + DeepSeek API + bash 工具读文件 + 中文总结，全链路通过 |
| M1 | 蓝图讨论定稿（方向/底座/愿景/平台约束/验证策略全部决策记录化，见设计方案 §3） | ✅ 完成（2026-08-31 全天讨论） |
| M1.1 | **验证周：最小实验**（真实 JD → SDK agent 岗前分析 → 转猎聘关键字 → "老板我弄的咋样"） | ✅ 完成（2026-09-01）：样本轮（参考库 JD）+ 用户最新 JD 复测轮，两轮全通过 |
| M2 | 链路扩展：挂 browser-agent（采集）+ 池子评估 | ✅ 核心验证完成（2026-09-01）：采集（真实猎聘 30 人）+ 评估（30 人评分）闭环跑通；browser-agent 接入方案已定（配方表 execute_spec） |
| M3 | 信任演进机制：汇报粒度/闸门/放手策略 | ⬜ |

## 决策记录（防意图衰减，详见设计方案 §3 全表）

| # | 决策 | 结论 | 理由 |
|---|---|---|---|
| 1 | 新项目形态 | 用 DSH SDK 做新一代"数字合伙人"；browser-agent/领域方法作组件继承 | 一年资产不重写；SDK 已验证 |
| 3 | 技术底座 = DSH Python SDK | ✅ 已验证可行 | Windows dev 模式全链路跑通 |
| 5 | 产品愿景 | 数字合伙人：自主+汇报+信任演进+双向成长 | 用户原话具象化 |
| 7 | 验证策略 | 验证周：最小实验先行 | 固件教训：做出来才显形 |
| 8 | 协作规矩 | 动手前对齐目的声明 + 小步验证回顾 | AI 加速做不加速想 |

## DSH SDK 验证记录（2026-08-31）

- 链路：`deepseek-harness-sdk`（lzstudy conda 环境，源码 PYTHONPATH）→ dev node runtime（pnpm deploy 闭包 `.dsh-staging`，补 16 个 workspace 插件包）→ `deepseek-v4-flash` API → 真实工具调用
- 结果：✅ `harness.run()` 返回 `final_response`；✅ bash 读取 `设计方案.md` 并中文总结章节；✅ 会话持久化（JSONL）；✅ Windows 有 conpty（node-pty）支持
- 关键脚本：`bestagent\sdk_verify.py`（`--env-file` 指定 .env 路径）
- 遗留：① Windows 生产化需自建 exe（官方脚本仅 linux/macos）或跑 Linux；② `.dsh-staging`（~200MB）是 dev runtime，生产环境应从 PyPI 装官方 wheel

## M1.1 验证周·最小实验记录（2026-09-01 样本轮）

- **输入**：真实禾蛙 JD（`data\inbox\jd_1.txt`，GPGPU 软件高级架构师，60-150万/北京/985硕/佣金189K，取自参考库 `参考代码\岗位招聘单机版\recruitment.db` jobs 表）
- **链路**：`m1_run.py`（SDK agent，deepseek-v4-flash + persona「猎头数字合伙人小猎」）→ 自主读手册 `data\prompts\analyze_job.txt` + JD → 岗前分析 → 4 组关键字 → 报告写 `data\outbox\report_jd_1.json` → 老板口吻汇报
- **结果**：✅ 一次跑通。评分 17/25「优质」、推荐**接单**（佣金189K 5分/HC1人 1分/3天前发布 5分/央企 5分/难度 1分），5 条风险清单，4 组关键字合规，汇报形态达标
- **真自主证据**（session `m1-jd1-001`，3780 events）：step1 自主并行读手册+JD → bash 路径不通 → **主动换 str_replace_editor** 写报告 → 写完回读自检
- **关键资产**：`bestagent\m1_run.py`（可复用：改 JD 文件路径即可跑新 JD）、`bestagent\dump_jd.py`（改 JOB_ID 取参考库其他样本）
- **遗留**：①bash 工具在 Windows 下路径不可用（agent 已自动绕行 editor，无碍但记录）②待用户提供最新 JD 复测一轮 ③会话 JSONL 持久化正常（可续聊）

## M1.1 复测轮（2026-09-01，用户最新 JD）

- **输入**：`data\inbox\jd_user_001.txt`（AI+在线教育辅导管理，石家庄 8-15万，佣金17.9K，三个月前发布，发单方杨顾问在线）
- **结果**：✅ 一次跑通（session `m1-jd-user-001`，5205 events）。评分 10/25「普通」、建议**沟通**（非接单）——判别力验证成立：高分单（GPGPU 17分接单）与低分单（教育岗 10分沟通）能被正确区分
- **质量抽查**：佣金17.9K→3分 / HC3→3分 / 超30天→1分 / 一般公司→2分 / 难度→1分 = 10 分，评分自洽；6 条风险贴合实际；4 组关键字合规（竞品对标用作业帮/学而思/高途/掌门）
- **结论**：M1.1 三个验证点（真自主 / 输出质量 / 汇报形态）两轮全部达标 → **验证周最小实验完成**，下一步 M2（挂 browser-agent 采集）

## M2a 池子评估离线预演（2026-09-01，不依赖猎聘）

- **标的**：中级车载测试岗（J20260401154437101390，jd 原文 1400 字符）+ 对应 19 条真实候选人池（`data\inbox\pool_J20260401154437101390.txt`，101KB）
- **方法**：`m2_run.py`（SDK agent + persona 小猎）自主读 JD + 池子 + 方法论（`pool_quality.txt` 池评 / `match_candidate.txt` 单评）→ 池子质量评估 + 19 人逐一匹配评分 → 汇总报告 `data\outbox\pool_report_J20260401154437101390.json` → 老板汇报
- **结果**：✅ 池子评「中」（分布 0 高/8 中/11 低）；**全池无人满足「Python 自动化」命门技能** → 建议补采；点名 #11 孟（73 分推荐，ADAS+座舱+大连背景）优先深挖、#20 赵（68）跟进
- **意外亮点（data_valid 闸门自主触发）**：agent 自行发现 #6 与 #1 同一简历重复采集、#7 无效占位 → 实际有效独立候选人 17 位，主动提醒复核采集页面——pool_quality 手册的 data_valid 设计真实生效
- **教训**：大输出任务（多人评估写文件）max_tokens 8192 不够（finish_reason=max-tokens，报告未落盘），调到 32768 一次跑通；后续大报告任务默认 32768
- **遗留**：①猎聘账号审核中，真采集（browser-agent）待账号可用后接 ②评估环节已验证，采集→评估闭环待接

## M2 采集→评估闭环验证（2026-09-01，猎聘账号已可用）

- **环境**：活体 `D:\study\lietou-agent\browser-agent`（bridge 起在 127.0.0.1:8080，Chrome 扩展在线，猎聘登录态正常，tab_id 现查 1890029085）
- **第一步（采集）**：`collect_liepin.py` 用**配方表 execute_spec 路径**（P6 验证过的正确路径）真实搜猎聘"GPGPU"→ 采到 **30 条相关候选人**（中科芯 GPGPU driver Leader / Intel gpgpu 产品总监 / 海光 / 国产 GPGPU 芯片 AI 编译等），存 `data\outbox\collected_gpgpu.json`
  - ⚠️ 教训：**别用自然语言 agent 循环（/api/agent/run）做采集**——它条件没设上，直接 extract 了页面残留的青岛默认结果（40 条全无关）；配方表 execute_spec 一步到位
  - 教训2：tab_id 会话间会变，用 list_tabs 现查（本次 1890029085）
- **第二步（评估闭环）**：`m2_eval_run.py`（SDK agent）自主读 JD+30 条采集结果+方法论 → 池子评「中」（0 高/7 中/23 低）→ 30 人逐一评分（top：陈 78 推荐-海光+摩尔线程、李 68-壁仞超龄、李 63-Intel 产品总监）→ 报告 `data\outbox\pool_report_gpgpu.json` → 老板汇报
- **结论**：**「关键字→真采集→入池→评估→汇报」完整闭环跑通**，评分严格贴合硬性条件（985/211 硕士/8年/5年架构/43岁上限/北京）
- **遗留**：①补采目标公司定向候选人（agent 建议：华为昇腾/寒武纪/海光等 + 北京权重）②限速策略落地（50 打招呼/天 + 查看量）③采集结果入 SQLite 业务库（当前只落 JSON 文件）④DSH agent 自动调采集脚本（当前第二步手动喂采集结果，闭环可再自动化一层）

## M2 补采轮（2026-09-01，定向补采 + 120 人全量评估）

- **采集 v2**：`collect_liepin.py` 升级为多关键字批量 + tab 自动发现（list_tabs 现查）+ 合并去重；补采 GPU架构师/GPU编译器/GPU驱动 3 组 → 90 条；合并首轮 30 条 → **120 条**（`data\outbox\collected_gpgpu_all.json`，去重无重复）
- **评估**：`m2_eval_run.py` 参数化（--collect/--report/--session）+ 紧凑格式（低分只给 score/verdict/summary，≥60 给 match_points/concerns）→ **120 人全量评估**（session `m2-eval-gpgpu-all-001`，35280 events）
- **结果**：池子「中」→「良」（中匹配 7→22 人）；top：陈**78（海光+摩尔线程）、张**75（北京本地+浙大硕士+威盛 GPU 架构师）、卢**74（北京本地+联想 GPU 架构师）；识别超龄/学历卡点（Arm 首席 49 岁、英伟达 Leader 43 岁本科等）；报告 `data\outbox\pool_report_gpgpu_all.json`（31KB）
- **收获**：大池子捞真 GPU 软件背景能力验证；120 人紧凑评估在 32768 token 内一次通过（紧凑格式有效）

## M2 第三步（B 自动化，2026-09-01）：agent 自主闭环 + pwsh 工具修复

- **问题**：DSH agent 的 bash 工具在 Windows 完全不可用（连 `echo hello` 都 `File not found`——工具层起不了 shell）
- **修复**：补装 `dsh-tool-pwsh` + `dsh-tool-pwsh-persistent` 包（源码已构建，robocopy 进 staging，排除 node_modules）；新增 `minimal-pwsh-nonpty.cordis.yml`（**dsh-pwsh-local + dsh-tool-pwsh 非 PTY 组合**，系统无 PowerShell 7 时自动兜底 Windows PowerShell 5.1）
  - ⚠️ PTY 模式（terminal-bash + shellDialect: pwsh）会因无 pwsh.exe 让 node-pty 崩溃，勿用
  - ⚠️ **SDK runtime 必须在沙箱外运行（danger-full-access）**，否则 node spawn 子进程报 EPERM（fs/editor 工具不受影响，所以之前 M1/M2 任务能跑）
- **验证**：探针通过——`echo hello`✅ `python --version`✅（Python 3.11.14）内联脚本✅ .py 文件✅
- **自主闭环**：`m3_auto_run.py`（agent 自主跑采集脚本→读结果→评估→报告→汇报）一次跑通：真实搜猎聘"海光"→29 人→池子评「差」（0 高/1 中/28 低，同名公司噪音+海光体系硬件岗）→点名陈**68（摩尔线程成都 leader+现海光，唯一贴谱）→如实汇报"别在这池子花力气"（不粉饰，信任演进关键品质）→ 报告 `data\outbox\pool_report_gpgpu_haiguang.json`
- **关键字选词教训（agent 自证 + P6 印证）**：公司名做关键字会命中大量同名噪音（海光→食品/光电/贸易），技能关键字（GPGPU/ROCm/CUDA/编译器/Runtime）更准——后续补采按小猎建议换技能关键字
- **M2 结论**：采集 ✅ 评估 ✅ 自主闭环 ✅ —— 数字合伙人「分析→采集→评估→汇报」全链路自主跑通

## M2 限速落地（C，2026-09-01）

- `quota.py`：采集操作记账（JSON 日账本）+ 限额检查 + 轮间随机延迟（防账号风控）；默认每日搜索 20 轮 / 提取 200 条 / 延迟 5-15s；配置 `data\usage\quota_config.json` 可调
- `collect_liepin.py` 已集成（每轮前查额度、轮后记账、轮间延迟；`--no-quota` 调试跳过）；自测通过 + 真实 1 轮验证（ROCm 关键字 29 条，账本正确更新 search 1/20）
- 对应授权矩阵 §3 额度管理落地；打招呼（50/天）仍走闸门留人工，不在采集脚本内

## M2 补采优化轮（2026-09-01，技能关键字 + 分批评估）

- **采集**：4 个技能关键字（CUDA/GPU架构/异构计算/AI芯片）→ 116 条（限速生效：轮间延迟 6-9s，账本 search 5/20）；并 ROCm 29 条 → `collected_gpgpu_skill.json` **144 条**
- **评估分批**（教训：120 人是 32768 token 极限，144 人截断）：`m2_eval_run.py` 加 `--start/--end/--skip-pool` 分批；`merge_report.py` 合并 → `pool_report_gpgpu_skill.json`（pool_quality + 144 人）
- **结果**：Part1（1-72）池子「中」0 高/10 中/62 低，top 张**78（北京+浙大+威盛 GPU 架构师）、王**77（中科芯 driver+沐曦）、陈**75（摩尔线程 leader）；Part2（73-144）明显偏弱，仅胡**60+（字节异构计算架构师，北京/川大硕士）
- **建议（agent）**：优先深聊张/王/陈，补采北京本地编译器/驱动/Runtime 全栈候选人；对超龄/学历不符者与客户确认特批空间
- **教训**：大池子评估分批（每批 ≤72 人），用 session 区分 + merge_report.py 合并

## 业务库落地（2026-09-01，记忆分层 L1 · SQLite）

- **`import_to_db.py`**：复用 wails 表设计（jobs/candidates/match_results/candidate_events/pool_samples，schema 取自 `参考代码\recruitment-wails\internal\db\db.go`）→ 建 `bestagent\data\business.db`
- **导入**：GPGPU 岗 1 条（含岗前分析 job_score）+ 三批采集（all 120/skill 144/haiguang 29 → 去重 **277 位候选人**）+ 三份评估报告（**277 条 match_results**，candidate_id 按采集顺序映射）
- **抽查**：top5 张**78（北京/威盛）、王**77（中科芯/沐曦）、林**74（英伟达）、谢**73（英伟达）、卢**72（北京/联想）——数据完整
- **教训**：agent 写的报告 JSON 带 UTF-8 BOM，读取用 utf-8-sig
- **意义**：数字合伙人开始有"业务记忆"（L1），为 M3 界面/漏斗统计铺路；后续采集评估应直接写库（当前是先落 JSON 再导入）

## 框架整合 v1.0（2026-09-01，统一入口 + 闭环直写库 + 通用化）

- **背景**：M1/M2 各环节是独立脚本、手动串联、硬编码本机路径与 GPGPU 岗位条件——按决策 14（代码 90% 原样复用）整合成可交付框架
- **新增**：
  - `framework_config.py`：集中配置（WORKSPACE/DSH_ROOT/RUNTIME_BIN/CORDIS/BRIDGE/模型/token/分批上限），全部相对定位或环境变量覆盖（DSP_WORKSPACE/DSH_ROOT/BROWSER_AGENT_PATH）→ **换电脑只改配置**；含 `check_env()` 环境自检、`load_env_file()`
  - `run_pipeline.py`：统一入口 `python run_pipeline.py --jd data/inbox/xxx.txt --env-file .env` → 全链路 ①岗前分析 ②采集 ③评估（自动分批 ≤72/批 + 自动合并）④**直写 business.db** → 老板汇报；支持 `--step` 单步、`--keywords/--conds/--requirements` 覆盖、`--skip-collect`、`--dry-run`
- **改造（保持独立运行能力）**：m1_run（抽 `analyze_job()`）、m2_eval_run（JD/岗位条件参数化，抽 `eval_pool()`）、collect_liepin（browser-agent 路径 config 化，抽 `collect()`）、import_to_db（岗位/路径参数化，抽 `write_to_db()`，供闭环直写）
- **换岗试跑验证（北极星达成 ✅）**：新 JD「AI应用开发工程师（NLP）·中国移动」（应届博士/C9/QS50/≤30岁/北京）走完 ①分析（16分优质/建议沟通：佣金高+央企+72h新发→满分，博士+C9门槛+HC1→难度0分，判别力成立）→ ②采集（条件筛选首验：education=博士/博士后 + years=应届生 + city_current=北京 全部生效，30/30 命中 2026-2027 毕业窗口）→ ③评估（池子「中」4高/4中/22低，捞出中科院林**/清华张**/北大吴**真实 C9 博士）→ ④直写库（+30 候选人/+30 评估 → 库共 307/307）
- **条件筛选首次真实启用**：GPGPU 轮"整页端走事后滤噪音"→ 本轮"前置过滤"（education/years/city_current 配方组验证通过）；院校 C9/QS50 猎聘无筛选项，只能后置评估过滤（预期内）
- **遗留**：m3_auto_run 仍为实验脚本（硬编码路径未参数化，保留作 agent 自主演示）；Streamlit 界面（M3）未做

## 工作方式记录（2026-09-01）

- 新增 `工作文档\协作工作流草案.md`（v0.1）：5 步循环（人定目标/派活/验收/纠错，agent 实施/测试/汇报）——**可选、非强制**的工作方式提议，刚考虑不成熟，后续按需取用；《对话交接规范》纪律照旧必守

## 环境备忘（新对话现查，勿信快照）

- 活体工作区：`D:\study\lietou`（wails/streamlit 产品线）、`D:\study\lietou-agent`（多 agent）、`D:\study\lietouserver`（岗位采集）
- 参考素材：`D:\study\bestagent\参考代码\`（只读，含 README 索引）
- 交接规范：`D:\study\bestagent\工作文档\对话交接规范.md`

## 下一步

1. **M3 界面**：Streamlit 汇报面板（读 business.db；汇报卡片+确认/纠错按钮 = 信任演进界面）
2. **agent 自主动态优化**：让 agent 看评估结果→自己决定加/改条件重采（多轮寻优闭环，工具已齐：pwsh+配方表）
3. **补采优化**：技能关键字定向补采（本单 agent 建议：Agent/智能体/MCP 关键字补一轮）
4. **换电脑试跑**（验收方式）：框架已配置化（framework_config.py），新电脑装环境+拷代码即可；.env 从参考代码处取
