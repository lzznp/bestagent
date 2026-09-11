# 交接包：browser-agent P2 全部完成 → P3（新对话必读）

> 生成时间：2026-08-22 ｜ 交接方式：P2 实施对话（老师傅）→ 新对话（新徒弟）
> 新对话开场：**先读本文件** → 再读 `HANDOFF-P2-WIP.md`（P2-1~P2-4/6 明细与踩坑）→ `HANDOFF-P1-COMPLETE.md` → `HANDOFF.md` + `DESIGN.md` → 再读代码
> ⚠️ 本文件是 P2 全部完成后的最终交接，覆盖 P2-WIP 之后的 P2-5 进展。

---

## 1. 一句话状态

**P2 六项任务全部完成并验证通过**：P2-1 去猎聘化、P2-2 人工介入（紧急停止+暂停/继续）、P2-3 多标签页、P2-4 站点知识库、P2-6 bridge 去重、**P2-5 多 Agent 数据库桥（本轮完成）**。

## 2. P2-5 实现明细（对照任务书）

| 任务书条目 | 实现 | 验证结果 |
|---|---|---|
| SQLite 存储层（标准库 sqlite3） | 新建 `agent/db.py`：`tasks` 表（状态机 pending→executing→done/failed/timeout + paused/cancelled 兼容字段，status 驱动轮询）+ `candidates` 表（source_id **唯一约束** + INSERT OR IGNORE 防重复）；WAL + 全局锁线程安全 | 单元自测：去重 1 插入/2 跳过 ✅；**跨进程持久化**验证（重启后数据仍在）✅ |
| 数据写入路径 | bridge AgentRunner worker 在 run_loop 返回后批量入库 candidates（run_id/site/url 落库）；CLI agent.py 同样入库；任务记录写穿 tasks 表（JSONL 审计保留） | 真实 run d46930e583：30 条候选人入库 ✅ |
| 技能注册表 | `GET /api/agent/skills`：11 个动作（snapshot/click/type/scroll/navigate/extract/list_tabs/new_tab/switch_tab/close_tab/verify_site）+ 参数 Schema，定义在 `agent/core.py` 的 `SKILLS` | 返回 count=11 全量 Schema ✅ |
| 接口兼容 | 现有 HTTP 接口全部不变；SQLite 为内部存储替换；新增 3 个消费端点（skills/candidates/db/stats） | 快照/提取/翻页/暂停/多标签回归全过 ✅ |
| run 级 tab_id 钉住（附带增强） | `POST /api/agent/run` 与 CLI 支持 `tab_id`：整个 run 的注入型动作固定作用于此标签（快照/verify_site/extract 都带 tab_id），不依赖激活标签页 | E2E 全程钉在猎聘标签，激活页被切走也不受影响 ✅ |

**验收结果（对照任务书）**：
1. ✅ 一条完整任务：提交→扩展执行→结果入库 candidates（**重复 source_id 不重复入库**：同任务重跑 cfcc8b3a7b，30 条全部去重跳过，candidates 保持 30）
2. ✅ `GET /api/agent/skills` 可查询完整技能面
3. ✅ 快照/提取/**翻页**（run 77eb21e772 翻 2 页 60 条去重正确）/暂停恢复（test_pause_logic 3 路径全过 + API 409 优雅报错）/多标签（list_tabs/switch_tab 实测）不回归

## 3. 代码改动清单（P2-5 期间）

| 文件 | 改动 |
|---|---|
| `agent/db.py`（新） | SQLite 存储层：tasks/candidates 表 + source_id 唯一索引（非空部分索引）+ upsert_task/insert_candidates/query_candidates/stats/site_for_url；autocommit（isolation_level=None）+ 批量显式事务 |
| `agent/core.py` | 新增 `SKILLS` 技能注册表（11 动作 + JSON Schema）；run_loop 新增 `tab_id` 参数（快照/verify_site/动作 params 全部透传）；extract 行内标注采集页 url；finish 时 candidates 带 url + data["url"] |
| `bridge/server.py` | TaskStore 写穿 tasks 表（create/pick/finish 后 _sync_db）；AgentRunner 透传 tab_id + worker 入库 candidates；新增 GET /api/agent/skills、GET /api/candidates（site/source_id/limit/offset）、GET /api/db/stats；启动时 init_db |
| `agent/agent.py` | `--tab-id` 参数透传 run_loop；CLI 路径 candidates 入库 |
| `README.md` | 多 Agent 数据库桥章节 + 新端点 + --tab-id |

## 4. P2-5 踩坑/经验（新对话必读，P2-WIP 第 4 节仍有效）

1. **sqlite3 默认不自动提交（本轮最大坑）**：Python sqlite3 默认隔离级别下 DML 需显式 commit，连接关闭时未提交事务**回滚**——自测同连接内"看到"数据，重启后全丢。修复：`isolation_level=None`（autocommit）+ 批量插入用显式 BEGIN/COMMIT。**验证跨进程持久化**（跑两次脚本，第二次应 inserted=0）。
2. **threading.Lock 不可重入**：`init_db()` 拿锁后调 `_get_conn()`，而 `_get_conn()` 里又调 `init_db()` → 同线程死锁卡死 120s。修复：拆成 `_connect()` + `_ensure_schema(conn)`，`_get_conn` 懒建表，无重入。
3. **诚猎通搜索交互（新配方）**：找简历条件页 = SPA，搜索后 URL 不变（加 `#session`）。**关键词输入框是第 18 号元素（index 17 是别的输入，type 不生效），搜索按钮是 19 号**。配方：type→18 + click→19 → 结果页（139 元素，"共3000+位"）。历史 run 都是"页面已有结果"直接 extract，从未演示过搜索——此配方本轮实测得出。
4. **run 级 tab_id 钉住是 E2E 可靠性关键**：P1 踩坑 #7（激活标签页被切走导致注入失败）在本轮复现（GUI 页 127.0.0.1:3080 会"抢"激活位）。钉住 tab_id 后 run 与激活页解耦，LLM 看到的快照始终是目标标签页。
5. **run 事件里没有完整元素列表**：on_step snapshot 事件只带 title/url/element_count（LLM 决策用快照文本），调试页面结构要自己 POST snapshot 任务拿 elements。

## 5. P2 汇报（第 5 节格式，可转交设计对话）

```
P2 完成情况：
1. 完成度：全部（P2-1 ✅ P2-2 ✅ P2-3 ✅ P2-4 ✅ P2-5 ✅ P2-6 ✅）
2. 质量结论：能运行；P2-5 验收全过——完整任务入库（30 条）、重复 source_id 去重（重跑 0 新增）、
   skills 注册表（11 技能）、翻页回归（2 页 60 条）；暂停/多标签/快照/提取全回归
3. 与设计的偏差：无架构偏差；按任务书实现（tasks 保留 JSONL 审计，candidates 入 SQLite）；
   附带增强 run 级 tab_id 钉住（调度 Agent 可指定操作标签页，落地 P2-3 的 tab_id 扩展点）
4. 下一步建议：P2 全部完成，可进 P3（多 Agent 编排：调度 Agent 查 /api/agent/skills → 派活 → 轮询 /api/tasks → 消费 /api/candidates）
```

## 6. 运行环境备忘（当前状态）

- **桥接服务**：当前实例为会话 job 拉起（PID 见 netstat），**会话结束会停止**；下次 `python agent/agent.py "任务"` 自动拉起（P2-6 保证不双开）
- **SQLite**：`logs/agent.db`（WAL 模式，tasks=49 / candidates=60 为 P2-5 验收数据，可保留作演示或清空）
- **浏览器**：猎聘诚猎通已登录；本轮搜索了 **Python 关键词（结果页 3000+ 位）**，标签页 1890028342（tab_id 每次会话可能变化，用 list_tabs 现查）；另有 8 个标签可清理
- **Agent**：`python agent/agent.py "任务" --max-steps N --tab-id <猎聘标签id>`（钉住标签防激活页被切走）
- **控制台**：http://127.0.0.1:8080/console
- **测试**：`python test_pause_logic.py`（暂停回归）；db 层自测 `python agent/db.py`
- **.env**：browser-agent/.env 已配 DEEPSEEK_API_KEY
