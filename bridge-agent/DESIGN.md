# 浏览器 Agent（Browser Agent）——P0 设计记录

> 日期：2026-08-20 ｜ 状态：拍板定稿（设计对话产出）
> 目标：**让"代码能运行"**——一个独立的、不依赖 DeepSeek Harness 的浏览器控制模块，
> 供真人或调度 Agent 以自然语言指令驱动，自主操作真实已登录的猎聘浏览器。

---

## 1. 拍板决策（决策记录表）

| # | 决策 | 结论 | 理由 |
|---|---|---|---|
| 1 | 是否自建浏览器助手 | **是，独立小目标（P0）** | 最终数字员工要求独立性；dsh-browser 只作协议参考，不能作运行时依赖 |
| 2 | 浏览器操作方式 | **Chrome 扩展（MV3）为执行器 + 桥接服务为控制端** | 借鉴 dsh 浏览器助手思路；插件方案无需调试端口、无自动化痕迹、人工登录一次长期复用；规避 Playwright/CDP 的麻烦（工作区 GUI 代码踩过的坑） |
| 3 | 桥接服务技术栈 | **Python 标准库 `http.server`，零第三方依赖** | 环境外网受限装不了包；标准库方案保证"能运行" |
| 4 | Agent 推理 | **DeepSeek API（`urllib` 标准库调用）** | .env 已有 DEEPSEEK_API_KEY；OpenAI 兼容接口 |
| 5 | 采集入库 | **后置，P0 不做** | 那是其他 Agent / 后台的事；P0 只验证浏览器操作效果 |
| 6 | 验证后台 | **JSONL/TXT 日志（logs/），不引 SQLite** | 最小化依赖；够验证"操作浏览器的某些效果" |
| 7 | 选择器策略 | **不预设选择器，LLM 每轮从快照现场推理** | 快照=对页面的理解（8-10k tokens/次，成本低）；页面理解知识库第二版再以"流程沉淀"形式做 |
| 8 | 指令入口 | **统一 `POST /api/task {action, params}`，真人/调度 Agent 同入口** | 工具面稳定后，上层谁调都一样 |

## 2. 架构

```
真人/调度Agent ──自然语言──▶ agent.py (LLM tool-use 循环)
                                  │ POST /api/task
                                  ▼
                        bridge/server.py (Python 标准库, :8080)
                                  │ 任务队列 + 结果表 + logs/tasks.jsonl
                                  ▼ 轮询
                        Chrome 扩展 background.js
                                  │ chrome.scripting 注入
                                  ▼
                        content.js 工具函数（快照/点击/输入/滚动/猎聘提取）
                                  │ 操作真实已登录浏览器
                                  ▼
                        猎聘页面（人工已登录，登录态长期复用）
```

## 3. 工具面契约（P0）

| action | params | 说明 |
|---|---|---|
| `snapshot` | — | 返回页面 title/url + 编号交互元素列表 + 正文摘要（AXTree 式，LLM 可读） |
| `click` | `index` | 按快照编号点击元素 |
| `type` | `index, text` | 点击元素并输入文本 |
| `scroll` | `direction, amount` | 页面滚动 |
| `navigate` | `url` | 标签页跳转（可选） |
| `extract_liepin` | `mode` | 猎聘列表页/详情页结构化提取（返回 JSON，作为采集 Agent 的接口预留） |
| `finish` | `result` | Agent 声明任务完成（结果写入日志） |

错误码：`no-active-tab` / `action-failed` / `bridge-closed` / `timeout`。

## 4. 目录

```
browser-agent/
├── DESIGN.md / README.md
├── bridge/server.py        # 桥接服务（标准库，:8080）
├── extension/              # Chrome MV3 扩展（加载此目录）
│   ├── manifest.json
│   ├── background.js       # 轮询任务 + 注入执行
│   ├── content.js          # 工具函数库（自包含，executeScript 注入）
│   └── popup.html/js       # 连接状态 + 手动测试
├── agent/agent.py          # LLM tool-use 循环（DeepSeek）
└── logs/                   # 任务/运行记录（JSONL）
```

## 5. P0 验收

1. 桥接服务 `GET /api/health` 返回 ok（标准库可运行）
2. 扩展加载后轮询到任务并执行，结果回报
3. 命令行 `python agent/agent.py "采集猎聘 Python 岗位列表第一页"` 完成一次 LLM 驱动的快照→动作→验证循环
4. logs/ 能看到任务记录与 Agent 动作序列
