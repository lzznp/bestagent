# 浏览器桥（bridge-agent）

通过 Chrome/Edge 扩展操作已登录的浏览器。本地 Python 服务接收任务，扩展轮询执行并回传结果；任务既可以由业务脚本提交，也可以由内置 LLM Agent 生成。

桥接服务和内置 Agent 使用 Python 标准库。上层招聘业务的依赖在仓库根目录说明中单独列出。

```text
业务脚本 / Agent → 本地桥接服务 → Chrome/Edge 扩展 → 浏览器页面
```

## 启动

在仓库根目录执行：

```powershell
cd bridge-agent
python bridge/server.py
```

默认监听 `http://127.0.0.1:8080`。也可使用本目录的 `start_bridge.bat`。

打开 `chrome://extensions` 或 `edge://extensions`，启用开发者模式，加载本目录下的 `extension/`。点击扩展图标查看桥接连接状态。

业务脚本需要桥接服务已经运行。内置 Agent 的命令行入口会尝试自动启动桥接服务：

```powershell
python agent/agent.py "提取当前页面的候选人列表" --tab-id <tab_id>
```

将 `<tab_id>` 替换为实际标签页 ID；省略该参数时使用当前活动页。图形控制台位于 `http://127.0.0.1:8080/console`。内置 Agent 的模型调用使用 `DEEPSEEK_API_KEY` 环境变量或本地配置。

## 常用动作

| 动作 | 参数 | 用途 |
|---|---|---|
| `snapshot` | — | 页面标题、地址、编号元素和正文预览 |
| `click` | `index` | 按快照编号点击 |
| `click_by_text` | `text, occurrence` | 按文本及匹配次序点击 |
| `type` | `index, text` | 输入文本 |
| `scroll` | `direction, amount` | 滚动页面 |
| `navigate` | `url` | 页面跳转 |
| `extract` | `anchor_text` | 提取匹配卡片的文本和字段 |
| `list_tabs` | — | 列出标签页及 ID |
| `new_tab` | `url` | 新建标签页 |
| `switch_tab`、`close_tab` | `tab_id` | 切换或关闭标签页 |
| `finish` | `summary, data` | 结束内置 Agent 任务并返回结果 |

快照中的元素编号随页面变化。指定 run 级 `tab_id` 后，注入型动作固定作用于该标签页；标签关闭会返回 `tab-lost`。

## 调试与停止

```powershell
curl.exe http://127.0.0.1:8080/api/health
curl.exe http://127.0.0.1:8080/api/tasks
curl.exe http://127.0.0.1:8080/api/logs
```

`--dry-run` 只执行读取类动作，其他动作记录为 `dry_run_blocked`；`--mock-llm` 可用 JSON 动作序列替代模型调用。内置循环还会检测连续无进展并记录 `stuck`。

两种停止接口作用不同：

- `POST /api/control/stop` 清空待执行任务并记录停止时间，接入该检查的业务采集脚本会在动作边界收尾。
- `POST /api/agent/cancel` 停止内置 LLM Agent 循环，不覆盖业务脚本直接提交的全部任务。

不可逆动作的确认接口已有预留；发送、发布、删除等专用动作仍待接入。普通网页点击并不自动获得完整的语义确认保护。

## 站点配置与数据

[agent/knowledge_config.json](agent/knowledge_config.json) 保存站点提示、唯一 ID 字段、提取锚点和基线检查规则。匹配支持域名及 URL 路径。基线检查失败会记录 `site_changed`，该次任务改用现场推理；核对页面后再更新配置。

任务和采集结果写入 `logs/agent.db`，过程记录保留在 `logs/tasks.jsonl` 和 `logs/agent_runs/`。候选结果按 `source_id` 去重。

## 接口

| 端点 | 用途 |
|---|---|
| `GET /api/health` | 服务状态 |
| `POST /api/task` | 提交浏览器动作 |
| `GET /api/task/{id}`、`GET /api/tasks` | 读取任务结果和列表 |
| `GET /api/task/poll`、`POST /api/task/result` | 扩展领取任务和回传结果 |
| `POST /api/agent/run` | 启动内置 Agent 循环 |
| `POST /api/agent/pause`、`POST /api/agent/resume` | 暂停、继续内置循环 |
| `POST /api/agent/cancel` | 取消内置循环 |
| `POST /api/agent/confirm` | 确认或拒绝预留的不可逆动作 |
| `GET /api/agent/status/{run_id}`、`GET /api/agent/runs` | 运行状态和历史 |
| `GET /api/agent/skills` | 动作列表与参数 |
| `GET /api/candidates`、`GET /api/db/stats` | 采集结果和存储统计 |
| `POST /api/control/stop`、`GET /api/control/state` | 停止控制与状态 |
| `GET /console` | 图形控制台 |

## 常见问题

- 扩展显示未连接：检查桥接进程和 `/api/health`。
- 任务一直 pending：检查扩展是否已加载，目标标签页是否存在。
- 返回 `injection-failed`：浏览器内置页无法注入，切到普通 HTTP/HTTPS 页面。

设计与开发记录见 [DESIGN.md](DESIGN.md) 和 [HANDOFF.md](HANDOFF.md)。
