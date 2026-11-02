# 小猎（bestagent）

本地招聘工作助手，用于岗位分析、候选人采集与评估，以及沟通准备和跟进记录。通过 Streamlit 面板查看任务进度与报告，浏览器操作由 Chrome/Edge 扩展和本地桥接服务执行。

## 模块

| 路径 | 内容 |
|---|---|
| `bestagent/` | 岗位分析、采集、评估、报告、业务数据库和 Streamlit 面板 |
| `bridge-agent/` | 浏览器扩展、本地桥接服务和独立 Agent 循环 |
| `工作文档/` | 架构、开发进度、运行约定和交接记录 |

`bestagent/m3_chat.py` 是对话式面板，`m3_ui.py` 是步骤汇报面板。业务数据默认位于 `bestagent/data/`，包括 SQLite 数据库、输入输出和反馈记录。

## 本地运行

现有运行流程以 Windows 和 PowerShell 为主。先准备 Python 环境：

```powershell
python -m pip install -r bestagent/requirements.txt
python -m pip install streamlit pandas
```

`requirements.txt` 固定了 Harness SDK 和配套运行时版本，界面依赖另行安装。首次使用 SDK 时需要可写的运行时缓存目录。

配置 `DEEPSEEK_API_KEY`；对话式面板默认从 `bridge-agent/.env` 读取模型服务配置。启动浏览器桥并加载扩展的步骤见 [bridge-agent/README.md](bridge-agent/README.md)。

在另一个终端启动面板：

```powershell
cd bestagent
python -m streamlit run m3_chat.py
```

如需使用步骤汇报面板，将入口换为 `m3_ui.py`。

## 配置与任务记录

路径和运行参数集中在 [framework_config.py](bestagent/framework_config.py)。常用环境变量：

| 变量 | 用途 |
|---|---|
| `DSP_WORKSPACE` | 业务工作目录 |
| `DSP_DSH_HOME` | 项目 Harness 会话目录 |
| `BROWSER_AGENT_PATH` | 浏览器桥代码目录 |
| `BRIDGE_URL` | 桥接地址，默认 `http://127.0.0.1:8080` |
| `DSP_MODEL` | 模型名称 |

任务按岗位保存分析、采集、评估和决策记录。面板根据这些记录显示可执行步骤；浏览器桥的任务日志与业务数据库分别保存。

## 开发文档

- [项目交接](工作文档/HANDOFF.md)
- [开发进度](工作文档/PROGRESS.md)
- [运行环境与协作方式](工作文档/工作模式·备忘.md)
- [浏览器桥用法和接口](bridge-agent/README.md)
