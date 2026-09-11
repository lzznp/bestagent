# bridge-agent = 本项目的桥（归属说明）

> 建立：2026-09-11（DSH 底座修复场）

## 一句话

**这个目录现在是 `D:\study\bestagent` 项目自己的一部分**，不再是外部工作区的东西。

- 原名/原址：`D:\study\lietou-agent\browser-agent`（**不是 git 仓库**）
- 现址：`D:\study\bestagent\bridge-agent`（**随本项目 git 版本化**，历史完整保留）
- 搬迁理由：`bestagent\collect_liepin.py` / `detail_collect.py` / `probe_detail.py` 会
  `sys.path.insert(0, framework_config.BROWSER_AGENT)` 并 **直接 import** 本目录的
  `agent.core` / `agent.recipe_exec`（配方表执行器 = 项目自己的资产）。
  目录留在仓库外 = **底座挂在别人目录上** —— 与 2026-09-10 DSH 升级事故同一种病
  （见《工作模式·备忘》§1.1 铁律 1「不许共享目录」）。

## 日常怎么用

| 干什么 | 怎么做 |
|---|---|
| 起桥 | 双击 `start_bridge.bat`（**纯 ASCII**，含 chcp 65001 + 自动找 lzstudy 解释器 + 健康检查），或由参谋长在 DSH 会话里当后台 job 起 `python bridge\server.py` |
| 查活没活 | `curl http://127.0.0.1:8080/api/health`（别信快照） |
| 浏览器扩展 | 从本目录 `extension\` 加载（实测本机是 **Edge** 在连 8080 → `edge://extensions` → 开发者模式 → 加载解压缩的扩展） |
| `.env` | 本目录 `.env`（DEEPSEEK_API_KEY）—— 全项目**唯一一份**，已被 `*.env` 忽略，不入库 |
| 配方表 | `agent\page_recipes.json`（采集条件的权威定义；`execute_spec` 按 `group_id/value` 执行） |
| 运行期数据 | `logs\`（`agent.db` / `tasks.jsonl` / 截图）—— **已加 gitignore**（此前 156 文件 93MB 被跟踪，2026-09-11 清出） |

## 注意

- 本目录内 `README.md` / `HANDOFF-P*.md` / `DESIGN*.md` 是它在**原项目**（lietou-agent）时期的历史文档，
  里面出现的 `D:\study\lietou-agent\browser-agent\...` 路径已过时（保留原样以存档，不改写历史）。
- `D:\study\lietou-agent\browser-agent`（旧活体）已不再被本项目引用，降级为**旧备份**：
  未经验证前不要删；确认本目录跑通采集后，由老板决定去留。
- 同一份桥的另一个副本仍在 `参考代码\lietouserver\browser-agent\`（那是别的工作区的快照，与项目无关，未动）。
