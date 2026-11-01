# -*- coding: utf-8 -*-
"""M3 界面 v1.6：对话式汇报面板（DSH Web 迷你版 · 分步骤测试用）

v1.12.2 变更（2026-09-22，拍板止血·第二刀：**"分析完却没有决策记录"⇒ 等价待拍板**）：
实测现场（09-21，本岗 J-CHAT-20260921-143843）：①分析做完（`analyze_20260921-145316.json`）、
  `load_state` 也认"已分析"，但 `state.json` 的 `decision` 是 **null** ⇒
  **对话里没有任何说法能记下拍板**（四个分类器的门都写着 `decision == "pending"`）。
根因（本次查实，比"词表太窄"更靠上一层）：
  · 写入口只有一处 —— `decision="pending"` 只在 `action_kind == "analyze"` 跑完时写（render_main）；
  · 而本岗的①分析是在**自由对话**里跑完的（`runs.jsonl` 里那次是 `action="chat"`），
    因为 `kind_of_task()` 只按任务书首行字符串分档，自由对话一律归 `report` ⇒ 那条写入分支没走到。
连带真事故：`decision_ok = dec in (None, "accept")` 把 `null` 当"旧岗兼容、不锁" ⇒
  09-21 16:19「按计划跑」就这么跑掉了 70 分钟采集（**没拍板却被当成放行**）。
本版修（**只改读取口径，不写 state、不伪造历史**）：`load_state` 里推导 ——
  分析过（`analyze_*.json` 在）且没有决策记录 ⇒ `decision = "pending"`。
  单源：全项目读 decision 只走 `load_state` ⇒ 一处修、四处齐（分类器门 / 进度条 / 按钮锁 / 状态卡）；
  `decision_note` / `decision_ts` 仍为空、`state.json` 仍是 dry 的（不写假事实）。
连带（**故意**）：无决策记录 ⇒ ②按钮由"不锁"变"锁"（这才是"没拍板不许采"的本意）。
验证：`test_m3chat_v190_buttons.py` PASS=83 FAIL=0（含新口径断言）；
  端到端（隔离副本）"说「做吧」→ decision=accept 真落盘 + 按钮解锁 + 无假成功警告" 17/17。

v1.7.4 变更（2026-09-07，结构性修改硬边界）：
老板原则确认：下发指令 ≠ 自由对话。自由对话只允许 读 + 受控追加（记到成长库/记到岗位资料）；
老板要求删除/取消/修改已有记录、动代码/脚本/配置等结构性修改时，小猎一律如实说明"由老板/实施对话
处理"，禁止自己上手删改文件（技术上能写≠设计上该开；即使让它写代码改自己也"也许并不是好主意"）。
结构性修正（删/作废条目等罕见操作）= 人工/实施侧。

v1.7.3 变更（2026-09-07，岗位资料落盘：岗位目录 = 正式底座起步）：
1. 岗位目录新增 job_profile.json（pm_notes 口径 / special_notes 猎头关注与客户特殊要求 / events 变动时间线），
   老板发令"记到岗位资料 / 这是 PM 的口径 / 临时需求…" → 小猎把对话里的 PM 答复/口径/关注
   分类【追加】进该文件（只追加不改历史、写完回读展示）；含歧视性要求时只作内部事实记录并提示合规边界。
2. state_block 提示岗位资料文件（后续步骤涉本岗口径可读）。

v1.7.2 变更（2026-09-07，成长沉淀补丁：教学原文注入，治"它说没看到您教的规则"）：
根因 = agent 无跨 run 记忆（项目铁律：不赌会话记忆、文档是唯一记忆），老板教的经验只存在于
transcript.json（给人看的），下一次"记到成长库"发令时是全新执行、真的看不到教学原文。
修复 = build_free_task 教学分支把本会话老板最近的非任务原话（跳过任务注入文本）注入 prompt，
让它在写入 rules.md 前先读到教学原文提炼；找不到原文必须如实报告，不许脑补。

v1.7.1 变更（2026-09-07，成长沉淀：对话里教 → 小猎自助写 rules.md）：
1. 老板在自由对话里明确发令（"记到成长库/写进 rules/记住这条/沉淀下来"等）时，
   小猎被授权把规则【追加】进 data/prompts/rules.md 对应小节（详见 CAPABILITIES「成长沉淀」段
   + build_free_task 教学分支的操作步骤）——只追加不改删、按现成格式、写完回读并展示新增内容。
2. 顺带修复 rules.md 历史结构 bug（曾有两个「② 采集」节，空骨架节与有规则节并存）。

v1.7.0 变更（2026-09-07 起，P0 交互模型改造：判断对话化·骨架）：
1. 判断环节进对话（决策 20 落地骨架）：①岗前分析完成后小猎给「态度+理由」（明确 接/先沟通/别做 三选一，
   不骑墙），并请老板拍板；老板可反驳追问（自由聊天通道照旧），然后回复 做/不做/先核实 拍板。
2. 拍板 = 本地识别落盘（不耗 API）：state.json 增 decision 字段（pending/accept/decline/clarify
   + decision_note + decision_ts）；拍板动作以确认消息留在对话里（可纠正）。
3. 按钮退「执行显示层」：②采集 / 📋发岗文字 / ③评估 的可用性由 decision 驱动——①分析完先等拍板
   （decision=pending 时锁），拍板 accept 才解锁；decline 后锁并提示改主意可说「重新判断」重跑①；
   clarify 后暂锁待核实回来再定。旧岗无 decision 字段默认不锁（兼容）。
4. 「重新判断 / 重新分析」消息 = 重跑①（decision 回 pending）。

v1.6.9 变更（2026-09-06，对话产物即点即开 + 去掉右侧报告栏）：
1. 助手消息的产物不再只是 📎 文件名文字——渲染成 文件名 + 「打开 ↗」按钮（os.startfile 本机打开，
   HTML=默认浏览器打开，可直接点页面里的候选链接 / 逐格复制），取代"只给说明文字、自己翻文件夹"。
2. 去掉右侧「本岗报告」栏（产物列表不实时更新、占右上方位置不便）→ 对话流全宽，
   每步产物以可打开链接形式留在对话里（历史消息里的旧产物同样可点）。
3. 📋 生成发岗文字 完成后在对话里追加一条带打开按钮的消息（不再只是页面上一条说明文字）。

v1.6.7 变更（2026-09-05，报告栏 + 打招呼清单）：
1. 💬 生成打招呼清单（③评估后）：入围者(推荐/待定,≤15 按分排序)每人 匹配点2/先核实2/话术1(岗位亮点)/话术2(匹配理由)
   + 猎聘直达链接(<a target=_blank>) → reports/打招呼清单_*.md；老板照单点链接复制话术人工打招呼
2. 右侧报告栏：主区双栏（左对话流 3 / 右本岗报告 2），产物按步骤分组列示、点开即预览
   （HTML 内嵌 / Markdown 渲染(链接可点) / JSON 代码），打招呼清单默认展开
3. 布局目标：所有步骤都以报告收尾——"点报告干活"（据清单逐一联系候选人）

v1.6.6 变更（2026-09-04，决策入库 + 发岗文字）：
动作区第二行：📋 生成发岗文字（agent 读 JD+① → 猎聘发布文案落 reports，发布动作人工）/
📥 入库当前岗（本地调 import_chat_job.import_job，把该岗①-③产物幂等写入 business.db：
jobs UPSERT + 候选人去重 + 评估 replace，job_code=目录名对齐，重复点只刷新不新增）。

v1.9.1 变更（2026-09-16，**②正式采集·按钮层接线**：改名 + 顺序 + 先灰着）：
老板拍板「先接线吧，先把 streamlit 面板按钮做好」= 只做**看得见的那层**，执行器留到下一轮。
  ① 改名：「② 探索采集」→「**② 正式采集**」（形态变了：翻页 + 本地粗筛 + 写本岗库，不再是"抓首页 30 人"）；
  ② 顺序：执行行 **🔎 搜索体检 → ② 正式采集 → ③ 池子评估**（老板衔接报告 §3-9 的口径）；
  ③ **按钮先禁用**：`_EXEC_WIRED=False`（文件中部有专门说明）——执行器还没接线
     （翻页 + 本地粗筛打分 + upsert 进本岗库 + 本地渲染采集报告，见《②正式采集·形态计划》）；
  ④ 聊天里说「去猎聘跑一轮」也**不接旧采集**：面板本地如实回「执行链路未接线」（0 token，不调 agent）。
⚠️ 为什么宁可灰着：旧的 `collect_liepin.py` 只抓**每个关键字首页 30 人**、不翻页、不进本岗库
  → 跑出来跟老板刚过目的形态不是一回事，**那才叫假成功**。下一轮把那三件做完 → 改一个常量即开。

v1.8.9 变更（2026-09-15，**②搜索体检**：小猎亲手跑几轮搜索 → 本地渲染过程报告）：
老板口径原话：「让小猎实际操作浏览器，根据岗位的 JD 进行几轮搜索，然后他生成报告，说：我先用啥关键字、
设定了哪些条件进行了搜索，这时候总候选人人数是 360 或者 3000+；然后又改变了什么关键字，修改了或者没修改
活跃度，总候选人人数是多少…」→ 目的 = **体检小猎**（会不会按 JD 正确设条件/关键字、会不会操浏览器）。
三个零件各写各的、互不越权：**脑 = 小猎**（`build_step2_probe_task` 任务书 → 写轮次计划 + 结论小 JSON）；
**手 = `search_rounds.py`**（确定性操作浏览器：逐轮 导航→清空→按配方表设条件【**强制 verify**】→搜索→
**只读**页面上的「共N位人选」——**绝不 extract、不抓人、不开详情页**）；
**嘴 = `report_html.render_search_rounds`**（本地渲染，0 token；440 字预算只掐小猎的叙述）。
与②采集的区别：②采集会**真抓人**落 `collected_*.json` 喂③评估；体检只读人数 → 所以**另设按钮、不顶替②**。
诚实边界：命中总数只能从页面纯文本**前 3000 字**里读；读不到就如实标"读不到"（**不猜、不拿上一轮顶替**）。

v1.8.8 变更（2026-09-15，②采集"翻译考试"：把配方表合法值给全 + 本地判分）：
病根（实测）：`build_step2_plan_task` 只给小猎 JD+①分析+方法论，**从来没把配方表的可选值给它**
  → 它只能猜（把 JD 的"5-8年"写成 `years=5-8年`，而猎聘只有 1-3/3-5/5-10/10年以上/自定义）
  → **"它年限迷糊"的真因是我们没给事实，不是它笨**（§2.4 纪律②：别让它干查表的活）。
两处修（**都不花 token、不碰猎聘**；单源 = `local_checks.recipe_options_brief` → `page_recipes.json`）：
  ① 任务文本注入**可选条件清单**（照抄合法值，含三条已知坑：AND 空格 / 没有"5-8年"档 / "今天活跃"）；
  ② 计划落盘后**本地判分**（`check_collect_spec`）：组存不存在、值在不在合法档、关键字形态，
     不合法就**给出最接近的合法档建议**（如 5-8年 → 3-5年 / 5-10年）并贴进对话。
⚠️ 第二场（执行校验：真跑一遍看 verify 全绿）仍要动猎聘页面，另行出计划请老板确认。

v1.8.7 变更（2026-09-15，**运行台账**＝断点/恢复的第一步）：
老板问："网络卡了/电脑出问题，全自动语境下小猎怎么记得走到哪了？" → 见 `log_run` 上方注释：
**恢复能力 = 落盘粒度**（小猎每轮失忆是设计前提，所以问题在"盘上写全了没有"）。
本版只做最便宜的第一条：`data/usage/runs.jsonl` 记 run 的 **running / done / error**（含 finish_reason、
新产物名），面板在流程进度区提示"上次某个 run 没正常收尾"。
⚠️ 还没做（下一批，等真需要）：②采集**边跑边落盘**（`collect_liepin.py` 现在只在全部关键字跑完后
才写 JSON → 中途崩=前几个关键字全丢）；"接着跑剩下的"自动化；卡死心跳（`REQUEST_TIMEOUT=1200` 秒，
现在"在跑"和"卡死"视觉上一样）。

v1.8.6 变更（2026-09-15，发岗助手按钮显示"用过了"）：
老板要求："点过发岗助手之后，应该像岗位分析那样**显示重新发**——既让人知道这功能用过了，也顺手"。
做法：`latest_post_text()` 从产物推导（`发岗文字_*.html` 在不在）→ 有则按钮变
「🔄 重新发岗助手」并把"上次生成时间 + 文件名"塞进 tooltip；没有则是「📤 发岗助手」。
⚠️ **不新增 state 字段、不做迁移**：这是**展示层**，按决策 4「记录不可改、展示可重算」从产物算最稳
（顺带：老岗只要盘上有旧产物，刷新后立刻就是"重新发"——本单 `J-CHAT-20260909-094907` 09-11 那份就在）。

v1.8.5 变更（2026-09-15，拍板止血：**闸门挪进门里的第一步**）：
实测现场（09-15 10:30，老板在 J-CHAT-20260914-172253 说「**我们做这个岗位吧**」）：
  · `detect_decision_intent` **一个词都没命中** → 落自由对话（`last_action='自由对话'`）；
  · 小猎回的第一句是「收到——**「做吧」我记为接单（accept）**」——而 `state.decision` **仍是 pending**。
    也就是：**它嘴上说记了，系统里没记**（假事实）；且它**无权**记（结构性修改不在自由对话授权内）。
  · 同一个坑第二次：09-09「直接往下走吧，把这个岗位写入岗位」也是没命中 → 它当时**自行解读 accept**。
  · 它的其它表现是好的：**没真跑采集**、**没动 state.json**、判断与关键字拆分理由都对，
    还自创了一份 `collect_plan_*.json`（内容质量高，但**超出自由对话白名单** → 另案处理）。
根因（§2.4 纪律②原话）：**"词表漏一个词，就等于代码替你拍了板"** —— 自然语言穷举不完。
本版三处修（**都不花 token、都不动判断层**）：
  1. **疑似拍板 → 面板本地反问**（`detect_decision_hint` / `confirmed_intent` / `last_pending_ask`
     / `build_decision_ask`）：精确词命中 → 照旧直接记；**疑似命中 → 当场问一句**（绝不替老板记）；
     老板回「是/对」= 对一个**已明确陈述的动作**点头（记下），回「不是」= 当没说。
  2. **面板事实核对**（`claims_recorded_decision`）：跑完自由对话后本地核一次——它若声称"已记决策"
     而 `state.decision` 没变 → **面板贴一条纠正**（与 §2.6「面板不许假成功」同一套机制，闸门在门里）。
  3. **拍板硬边界注入**（只在 `decision == pending` 时注入，**其它时候 0 成本**）：
     明说"记录拍板不是你的手；只能说『请回 做吧/不做/先核实 确认』，严禁说『我记为 accept』"。
⚠️ 大方向（09-13 重走复盘 §4.2-第六件「闸门挪进门里：词表 → 让 LLM 判意图」）**仍排在②采集跑通之后**；
   本条只是"止血"，不是那件事的替代。

v1.8.4 变更（2026-09-15，发布状态**占位**）：
老板定的方向："发岗与否和后面的打招呼/查看回复关联，但现在还没走到那个流程、没法测 → **先占个位置**，
等走到打招呼那步再完善"。所以本版**只占位**：
  · `state.json` 增 `publish_status`（`unknown`/`published`/`not_published`，**默认 unknown**）
    + `liepin_posts`（**列表**：一条发布=一条记录，双城/重发/换壳都装得下）；
  · 面板：流程进度行一个**状态位** +「📄 岗位信息」弹窗里一块**可录入**的区（4 格，0 token，纯本地写 state）；
  · **不做**联动（带岗位卡片 vs 不选职位开聊）、**不做**自动读回 —— 那是打招呼那一步的事。
⚠️ 为什么是"列表"不是文档里的单值 `liepin_hjob_id`：本单是"南京6+苏州6 共用一份 JD"，很可能发了**两条**；
   单值装不下第二条，而现在定错、以后改就是结构性返工（`自造/改结构`是纪律明令禁止的）。
   文档那四个单值字段**被本结构取代**，留档在案。
⚠️ 为什么现在**不注入**给小猎（状态卡）：注入要每轮付钱（≈60 字/轮），而**现在还没有消费者**（打招呼流程未到）
   → 等走到那一步再注入，免得白付。这是"占位"与"完善"的分界。

v1.8.3 变更（2026-09-15，「发岗助手」挪到①分析正后面）：
老板要求"在岗位分析按钮之后增加发岗助手" → 查证：它**早就存在**（面板上叫「📋 生成发岗文字」，
v1.6.8 起走 `publish_run.publish_for_job` 本地渲染、**0 token**；本单 09-11 真跑过——
`reports/发岗文字_20260911-161450.html`（11,679 字节，逐格复制到猎聘发岗表单））。
只是位置在**第二行第 1 格**，跟业务顺序（分析→**发岗**→采集→评估）拧着 →
**挪到第一行第 2 格**（①分析正后面），并按它的正名改叫「📤 发岗助手」
（`publish_run.py` 文件头自述"复刻 recruitment-wails 已验证的「发岗助手」模式"，
它生成的页面标题也一直是"📤 <岗> · 发岗助手"）。
⚠️ 按钮 key 仍是 `act_post_text`（自测 `test_m3chat_v170_apptest` 按 key 引用它），功能与判据（①拍板做后亮）不变。
第二行动作行随之变 2 列：💬 打招呼清单 / 📥 入库当前岗。

v1.8.2 变更（2026-09-15，摘掉「📤 导出 HTML 汇报」按钮）：
老板问"这个按钮还要吗？我也忘记原来设计它的目的了" → 查证后**摘掉**。三条理由（留档，别当没发生过）：
  1. **它出生时没有业务目的**：v1.6（09-04）"老板实测后反馈"那批的第 5 条顺手加的，用途是**验证按钮闭环**
     （PROGRESS.md §206 原话："按钮全流程闭环（🚀分析→JSON+HTML过程→📤导出HTML汇报，state.json 自动流转）"）。
     链路证明完就再没用过：盘上 11 天只产出 **1 份** 汇报_*.html（09-04 15:35，就是那次验收），
     同期①过程网页 9 份、发岗文字 4 份；**全项目 grep：0 处消费者**。
  2. **它定位自相矛盾**：任务书写"适合直接发 PM 或存档"，内容却要"接单判断/总分评级/风险要点"——
     那是我们的**内部判断**，恰好最不该发给 PM（发给 PM 要的是"待核实口径 + 提问"，不是我们的评分）。
     当"发 PM"不合适、当"存档"又与 analyze_*.json + ①过程网页重复 → 两头都不占，所以没人用。
  3. **它是面板上最后一个让 LLM 手写整页 HTML 的按钮**（`report` 动作在 TOOL_PROFILE_BY_ACTION 里没有档
     → 全量 25 个工具 ≈6,481 token/轮的固定租金 + 无上限的输出）——正是省 token 第二刀要治的形状。
→ "给 PM 发一份东西"是**真需求但从未被设计过**（要的是提问口径）；等它真出现时单独设计，别用错的壳占位。
   三个"给人看"的出口已都在：①过程网页（本地渲染）、📄岗位信息弹窗摘要（本地）、发岗文字（本地渲染）。

v1.8.1 变更（2026-09-15，省 token 第二刀：过程网页改本地渲染 + 长度预算）：
①过程网页改**本地渲染**（`render_analyze_html` → `report_html.render_analyze`），它只交 analyze JSON 里
`process` 三个短字段（合计硬顶 600 字，本地会量、超了截断并标注）；**判断结论一个字不截**。
实测（同 JD 严格 A/B：2,245 字节 / sha 相同 / 都是首次跑 / 都是 bare 档）：**47,853 → 27,709（−42%）**，
对基线 139,075 累计 **−80%**；它写的文件从 2 个变 1 个（顺带根除 09-14"一次写两大文件被截断、全丢"的事故形状）。

v1.12.0 变更（2026-09-17，老板拍板的新工作步骤「岗位分析 → 发岗助手 → 正式采集 → 打招呼报告 → 打招呼 → 查看回复」）：
**③ 池子评估取消**，这一步换成 **💬 打招呼报告**。打招呼报告 = **小猎自己的工作依据**（不只是给老板看的报告）：
先看态势（`status_run.py`：池子多大/够格几个/打过几个/还剩多少/现在能不能打）→ **自己定口径**
（写 `greeting_plan_*.json` 留痕）→ 跑细筛（`filter_run.py`：**逐人调 LLM**，评过的人命中缓存 0 花费）
→ 出报告（`greeting_report.py`：**本地渲染** JSON+HTML，0 token）→ 按时间窗排队打（打招呼动作仍是人工闸门）。
同时摘掉旧的「💬 生成打招呼清单」按钮（它读 `pool_report`，已被打招呼报告取代）。
🔴 **规则不进代码**：阈值/名额/宽松度/时间窗**全在小猎写的 plan JSON 里**（老板要的"弹性"）。
state：`step3_done` → **`step3_report`**（按 `打招呼报告_*.json` 推断）。

v1.6.5 变更（2026-09-04，③ 池子评估接入面板）：
③ 按钮按 ②采集完成点亮 / 聊天“评估一下这批人”类发令自动路由；agent 读 JD+最新 collected 池子
+pool_quality/match_candidate 方法论 → 池评（优/良/中/差+分布+data_valid）→ 逐人紧凑评分
（score/verdict/summary，≥60 加 match_points/concerns）→ 写 pool_report_*.json + HTML 过程 → 汇报 top；
纯文件任务与采集任务同用 sdk profile（含 pwsh 工具），max_tokens 提至 32768；state 新增 step3_done（按 pool_report 推断）。

v1.6.4 变更（2026-09-04，② 探索采集接入面板）：
1. 执行通道：2026-09-10 换代后**不再按任务切 cordis** —— 统一走 profile="sdk"
   （文件工具 + pwsh 工具都有，见 framework_config.make_harness）；
2. ② 探索采集 = 两步走（步骤制 + 授权确认）：
   发令（点按钮或聊天说“去猎聘跑一轮”）→ 第一步 agent 读 JD+analyze 拆关键字/条件，
   写 collect_plan_*.json 计划文件并请老板确认（不真跑、不耗额度）→ 老板确认（如“按计划跑”）
   → 第二步 agent 用 pwsh 跑 collect_liepin.py（真实猎聘采集）→ 读结果汇报命中/质量
3. 聊天意图识别：含“猎聘/采集/跑一轮/搜候选人…”→ 走 ② 两步；讨论性问句（怎么/为什么/？）不触发
4. 能力边界更新：已接入 = 文件读写 + 探索采集（配方表驱动）；未接入 = ③ 池子评估等
   —— 采集纪律：禁止自然语言驱动浏览器（教训 #2），禁止改脚本，先确认再执行

v1.6.3 变更（2026-09-04，根因修复）：
自由聊天必须走 build_free_task 注入状态卡+完整路径（此前写好未接线，agent 反复“找不到岗位文件”）

v1.6 变更（2026-09-04 老板实测后反馈，逐条落实）：
1. 去掉侧栏手动「当前测试步骤」选择器 —— 改为岗位自动进度（只读，从 state/产物推断）
2. 动作按钮行由岗位状态自动算出（贴 JD→亮「开始岗位分析」；分析完→亮 重跑/导出汇报，
   ②采集/③评估 未接入则灰色+原因），按钮 = 把固定话术代打发送；聊天框照旧自由输入
3. 每岗加 state.json 状态卡，每次发令注入提示，并硬指令「先读 jd.txt / 已有报告再开口，
   禁止向老板要已存在的信息」（不赌 SDK 会话记忆——实测每轮失忆，见 PROGRESS v1.5 记录）
4. 能力边界诚实化：提示里写明已接/未接能力（只接文件读写；采集/评估未接入），
   被要求未接入能力时必须如实说明并给替代（run_pipeline），严禁找借口或假装执行
5. 过程记录自动落：步骤按钮执行即自动要求 agent 写 HTML 过程文档（不用老板开口）；
   「导出 HTML 汇报」独立按钮按需点（读已有产物整理成汇报 HTML）
   —— ⚠️ **v1.8.2（2026-09-15）已摘除**：它出生时只是"验证按钮闭环"的验收样板，11 天用 1 次、
   0 消费者、内容定位自相矛盾（详情见文件头 v1.8.2 段）。此处保留原文仅为留档。

v1.5 设计基础（仍有效）：形态 = DSH Web 对话样板（输入框 + JD 上传 + 回复/日志区）；
一岗一会话；执行 = B 档真 agent（DeepSeekHarness，persona=小猎，阻塞式）；
成长数据 = data/growth/records.jsonl（原始账）+ data/prompts/rules.md（消化规则库）。

运行（PyCharm 终端，解释器 lzstudy，bestagent\\ 目录）：streamlit run m3_chat.py
界面自测（不调 API）：侧栏「运行设置」→ 假执行，或设环境变量 M3CHAT_STUB=1
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

try:  # 集中配置（新版 SDK：pip wheel / exe 模式 + 项目自带 dsh_home，见 framework_config.make_harness）
    from framework_config import WORKSPACE, PROMPTS, BROWSER_AGENT, make_harness
except Exception:  # 兜底：极端情况下界面仍起得来（只读 + 假执行）
    WORKSPACE = Path(__file__).resolve().parent
    PROMPTS = WORKSPACE / "data" / "prompts"
    BROWSER_AGENT = WORKSPACE.parent / "bridge-agent"
    make_harness = None

try:  # 纯本地产物校验（0 花费；替代"让 LLM 写完自己回读确认"，见 local_checks 文件头）
    import local_checks
except Exception:  # 兜底：校验器缺失不影响面板起得来，只是不贴校验结果
    local_checks = None

# 工具面分档（按动作给"手"）：见 framework_config.TOOL_PROFILES
# 2026-09-14：先只给 ①岗位分析 上分档（纯文件任务，实测它 8 轮里只用了 read/write）；
# 其余动作维持全量，等各自改到位再逐个收（一个动作一个动作改）。
TOOL_PROFILE_BY_ACTION = {"analyze": "bare"}

# 本次 run_assistant 的元信息（finish_reason / session / 是否假执行）。
# 为什么用模块级字典：run_assistant 的返回签名是 3 元组（多处调用 + 自测都在解包），
# 不能随便加返回值；而面板必须在**紧接着的同一轮脚本执行里**判断"真成功还是被截断"。
LAST_RUN: dict = {}

CHAT_DIR = (Path(os.environ["M3CHAT_CHAT_DIR"]) if os.environ.get("M3CHAT_CHAT_DIR")
            else WORKSPACE / "data" / "chat")  # 环境变量覆盖：AppTest/多实例隔离用
GROWTH_DIR = WORKSPACE / "data" / "growth"
RECORDS = GROWTH_DIR / "records.jsonl"
RUNS_LOG = WORKSPACE / "data" / "usage" / "runs.jsonl"   # v1.8.7 运行台账（断点/恢复的第一步）
RULES = PROMPTS / "rules.md"
DEFAULT_ENV = BROWSER_AGENT / ".env"   # 桥家的一把钥匙：本项目唯一的 .env（见 工作模式·备忘 §6）

# v1.7.1 成长沉淀：老板"教规则并让记进成长库"的触发词（build_free_task 检测后给写入指引）
TEACH_WORDS = ("记到成长库", "记进成长库", "写进规则", "写入规则", "记住这条", "记下来",
               "沉淀下来", "成长库", "教给你", "写进你的成长库", "记到 rules", "写进 rules")

# v1.7.3 岗位资料：老板把 PM 口径/临时需求/猎头关注"记到岗位资料"的触发词
PROFILE_WORDS = ("记到岗位资料", "记进岗位资料", "写进岗位资料", "记到岗位档案", "岗位资料里",
                 "这是 PM 的口径", "这是 PM 说的", "PM 答复", "PM 回复", "临时需求",
                 "补充到岗位", "记到岗位信息")

# v1.7.4 结构性修改硬边界：自由对话只读 + 受控追加；删/改已有记录、动代码/配置 → 拒绝并指向实施侧
STRUCT_OBJ_WORDS = ("岗位资料", "成长库", "规则", "rules", "代码", "脚本", "job_profile",
                    "方法论", "手册", "配置", "纪律", "persona")
STRUCT_ACT_WORDS = ("取消", "删除", "删掉", "作废", "去掉", "移除", "修改", "改掉", "撤销",
                    "回退", "清空", "别再记", "不要这条")

# 步骤清单（业务汇报断点；0=自由讨论，仅用于纠错记录时标注）
STEPS = [
    {"no": 1, "name": "岗位分析", "tag": "读JD→接单判断→拆搜索条件→探索采集→池子初判→做/放弃"},
    {"no": 2, "name": "采集", "tag": "转关键字→配方表采集→去重"},
    {"no": 3, "name": "池子评估", "tag": "池子评级+逐人评分→推荐清单"},
    {"no": 4, "name": "汇报", "tag": "过程记录/HTML 汇报→老板审阅"},
    {"no": 0, "name": "自由讨论", "tag": "不限定步骤：讨论/追问/纠错/别的"},
]
STEP_NAME = {s["no"]: s["name"] for s in STEPS}

# 能力边界（2026-09-14 改，见报告 §4.4-F）：把"已接入①②③ / 未接入…"那段**状态**搬走——
# 它按岗、按步会过期，却贴在 10 个任务串里每轮收钱。能力现在由「给不给它那个工具」物理决定，
# 不再靠文字声明（§2.7：词表/声明真正干的是决定给不给它手）；这里只留**纪律**。
CAPABILITIES = (
    "【能力边界·必须诚实（纪律）】你手里的工具清单 = 你这个动作的真实能力；"
    "**清单里没有的，就是你真的做不到**——被要求时如实说明并给替代路径，严禁找借口、严禁假装执行。"
    "对外动作与结构性修改（联系/打招呼候选人、发岗、改代码与手册）一律不在你手里，"
    "由老板人工或实施对话处理。"
    "【判断对话化·务必遵守】判断主通道 = 对话：老板要的是你给态度+理由、他反驳追问、然后他拍板，"
    "不是丢一份报告让他自己消化。①岗前分析完必须给明确态度（接/先沟通/别做）并请老板拍板；"
    "老板回复 做吧/不做/先核实 后岗位状态会记下该决策（accept/decline/clarify），后续步骤据此放行/锁定。"
    "判断错不罚、不诚实必罚：宁可直说判断（包括\"信息不足要先问 PM\"），不许含糊骑墙、不许粉饰、"
    "不许假装执行。"
    "【成长沉淀·授权与纪律】当老板**明确发令**要你把一条经验/规则记进成长库"
    "（如说\"记到成长库/写进 rules/记住这条/沉淀下来/教给你\"）时，你有权向成长规则库追加规则。"
    "纪律：①只在老板明确发令时写，绝不自动揣测、绝不主动改；②只允许【追加】，"
    "不许删改 rules.md 里任何已有内容；③按文件内现成格式写"
    "（`- [来源 本岗/日期] 当〔情境〕时，应〔怎么做〕`），不确定放哪节就放「流程 / 工具」；"
    "④写完必须用文件工具回读确认，并在回复里展示你新增了什么、加在哪一节。"
    "除成长规则库外，不得改写任何方法论手册（analyze_job.txt / pool_quality.txt / "
    "match_candidate.txt / publish_manual.txt）或其他文件——那些仍由老板/实施对话维护。"
    "【结构性修改·硬边界】自由对话里你只做两件事：读文件 + 受控追加（老板发令\"记到成长库/记到岗位资料\"时）；"
    "老板要求**删除/取消/修改已有记录、动代码/脚本/配置**等结构性修改时，一律如实说明"
    "\"结构性修改由老板或实施对话处理，我不在自由对话里执行\"并给替代路径，**绝不自己上手删改任何文件**"
    "（即使技术上你能写文件——写代码改自己/改规则不是好主意，能力边界由设计决定不由技术决定）。"
    "老板要求未接入能力时，必须如实说明「这一步我还没接 XX 能力」，并给替代建议"
    "（例如：打招呼/联系候选人需走人工闸门），"
    "严禁找其他借口、严禁假装执行。"
    "【歧义必问·基因纪律（不因任何授权/词表扩展而豁免）】当老板一句话的意图不明、或你要执行的动作带副作用但拿不准时（拿不准是不是拍板/是不是发令/写到哪里/怎么写），一律先停下：用 1~2 句复述你的理解并给可选项（如「您是要 A 还是 B？确认后我再动手」），等老板明确确认后才执行。禁止：自行解读拍板（accept/decline/clarify 只能由老板明确说出触发词，你不许替老板拍板）、把模糊指令当执行令直接干、自创文件/自造 JSON 结构/自造字段、擅自新建任何未约定结构。【受控追加·允许结构（硬边界细则）】自由对话里你能写的只有两类、且只在老板明确发令时：①成长规则库 rules.md——按现成小节【追加】一行（格式照文件内示例）；②岗位资料 job_profile.json——按固定三段式 pm_notes / special_notes / events【追加】条目（仅当文件不存在时才按此三段结构新建）。除此之外的任何新建/新结构/新字段/改已有内容 = 超出自由对话授权：如实说明、给出「由老板或实施对话处理」的替代路径并先问老板，绝不自己发明格式。"
)

PERSONA = (
    "你是猎头数字合伙人「小猎」，一位资深猎头助理，替老板（一位猎头顾问）跑岗前分析、"
    "转搜索关键字、写报告、做汇报。做事原则：先思考再动手；信息不足时明确提问；"
    "输出务必严格按方法论手册的格式，不擅自改动；涉及性别/年龄/婚育等违法歧视要求要提示并忽略；"
    "干完活主动向老板汇报（“老板，我弄的咋样？”的口吻）。"
    "老板在界面上用聊天跟你对话：一条岗位=一个会话。岗位上下文一律以文件为准："
    "开口/动手前先读该岗的 jd.txt 与已有报告，禁止向老板索要已经存在的信息。"
    "过程文档＝展示层，别浪费输出：①岗前分析的过程网页由面板本地渲染（你不写 HTML，"
    "只交 JSON 里的 process 三个短字段，合计 ≤600 字）；其他步骤若任务里点名要过程文档，再写。"
    "【判断对话化·务必遵守】老板要的是搭档不是工具：岗前分析后你要给明确态度（接/先沟通/别做）"
    "和理由、请他拍板，他可以反驳追问；判断错不罚、不诚实必罚——不许骑墙含糊、不许粉饰、"
    "不许假装执行，信息不足就直说要先问 PM/核实什么。"
    "老板在对话里教你业务经验/规则时，认真理解；他明确说\"记到成长库/写进 rules\"时，"
    "按纪律把规则追加进成长规则库（详见任务消息里的操作步骤，只追加不改删、写完展示）。"
    "【工具纪律·务必遵守】本环境 bash 工具不可用（Windows），读文件/列目录/写文件"
    "一律用文件工具（fs/str_replace_editor）；【② 采集执行】走 pwsh 运行采集执行器 "
    "`collect_exec.py --job-code <岗> --plan <计划> --all-keywords`（v1.11.0 **一键真跑**："
    "盘上没计划时你**一个回合内**自己定 关键字/条件/判据卡 → **写一份计划留档** → **直接开跑**（中间不停）；"
    "脚本自己设条件+点搜索 → **开工前先报池子** → 逐页本地粗筛打分 → **够格就开详情**读全文 → "
    "写本岗库 job.db → **自动翻页** → 连续一批人不值得开就**换下一条关键字**）；"
    "**不需要老板先去猎聘搜一次、也不需要人工翻页、更不需要老板为计划再点一次确认**"
    "（Windows 下 pwsh 每次调用是新进程）。"
    "岗位文件的完整绝对路径会**在每条消息里直接给出**："
    "直接用文件工具读该路径即可，**禁止去列目录/遍历磁盘找文件**（Windows 下列盘根目录会因"
    "DumpStack 等系统占用文件报错，这是正常现象，不代表文件不存在）。"
    "若文件工具已成功返回内容，就正常使用，不得声称“文件读不到/目录没挂载/被锁住”；"
    "只有按给定路径读取真实报错时才可请老板协助，且必须把报错原文贴给老板，禁止臆测原因。"
    "【② 采集纪律·务必遵守】采集=在真实猎聘上搜索（🔴 **不设人为额度**：不卡每日上限/每页配额/页数硬顶——"
    "2026-09-16 死命令；但**轮间必须保持 8-20 秒真人节奏、勿连点**；平台真正统计的风控点是"
    "“查看简历数”=打开候选人详情页的数量，**这是真代价**，所以本岗库里已有全文的人不重复开），"
    "禁止用自然语言让浏览器自己操作猎聘页面（条件会设不上），**只准用 pwsh 运行采集执行器 `collect_exec.py`**"
    "（它自己走桥的 `execute_spec` 设条件+搜索、走 `click_paging` 翻页；**模型不许自己碰页面**）；"
    "采集前先读 analyze 报告取 search_keywords、按 JD 硬性条件定条件，把计划写进 "
    "collect_plan_*.json **留档（这是可重放的那一份）**；"
    "⚠️ **要不要真跑，以本次任务书为准**：任务书说「真跑」→ **写完计划就立刻开跑**"
    "（老板点「② 正式采集」= **已经确认要跑**，中间**不许再停下来问**）；"
    "任务书说「只出计划」→ 就只出计划、请老板过目，**不要**偷偷开跑；"
    "执行器**开搜之前有一道开工前体检**（关键字形态/条件取值/判据卡），**没过会拒绝开跑并打印原因** → "
    "按原因改计划再跑一次（仍不过就如实报老板，别绕过）；"
    "执行完如实汇报命中条数/质量，不许粉饰，报错贴原文。"
    "【pwsh 工具实况·2026-09-11 实测，务必按此写命令】①本机 pwsh 工具实际是 **Windows PowerShell 5.1**"
    "（不是 PowerShell 7）→ 命令只写 5.1 兼容写法：**不许用 `&&` / `||` 串联、不许用三元 `?:`**"
    "（要串联就分次调用，或写 `;` 加显式判断）。②**退出码不可信**：工具把任何非零退出码都归一化成 "
    "`[exit code: 1]`（实测退出 7 也报 1）→ **判断成功/失败只看输出内容与产物文件**（如采集脚本打印的"
    "“✅ 合并去重后共 N 条”、或 --out 文件是否生成），必要时显式打印 `$LASTEXITCODE`，"
    "**绝不许仅凭退出码就对老板说“跑失败了”或“跑成功了”**。③需要看中文输出时，命令前加一行编码修正："
    "`$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8;`"
    "（collect_liepin.py 自身已强制 UTF-8，通常无需；你自己写内联命令打印中文时才加）。"
)

# ═══════════════════════ v1.9.1 接线闸门 ═══════════════════════
# 2026-09-16：老板拍板「先接线，先把面板按钮做好」= 老板选项 1 —— **本轮只做按钮层**：
#   ①「②探索采集」改名「②**正式采集**」；②执行行顺序 = 体检 → 正式采集 → ③评估；
#   ③正式采集按钮**先禁用**（执行器未接线，见下）。
# ⚠️ 为什么要有这个开关：老板现在**还点不到真的采集**（翻页 + 本地粗筛 + upsert 进本岗库 + 本地渲染
#   采集报告都还没接）→ 若按钮亮着、或它在聊天里把"去猎聘跑一轮"接上 `collect_liepin.py`，
#   就会跑出**旧形态**的采集（只抓首页 30 人、不翻页、不进本岗库）→ 老板拿到的东西与刚过目的
#   《②正式采集·形态计划》不一致，还以为新形态已经生效了。**宁可先灰着，也不许假成功。**
# ⚠️ 打开前必须满足：扩展已重载（`page_text` 动作可用）—— 否则详情只能拿到 3000 字预览，
#   而 collect_exec 会**如实报错**（不拿预览冒充全文），老板会看到"开详情失败"。
# 2026-09-16 v1.9.1：**执行器已接线**（collect_rules 判分 + collect_exec 执行 + job_db 落库 +
#   report_html.render_collect 本地报告），所以这里打开。
# 2026-09-16 晚 v1.10.0（老板重定方向）：**闭环补齐** —— ①`search_page` 接 `execute_spec`
#   （每条关键字**自己设条件+搜索** → "老板先人工搜一次"永久消失，"换关键字"成立）；
#   ②判据改成"**够格就开**"（`details_per_page=0` = 不限）；③🔴 **死命令：拆掉人为额度**
#   （`--max-pages/--details/--total-details` 默认 0=不限；quota 只记账不拦）；
#   ④连续一批人不值得开 → 换关键字；⑤本岗库已有全文的人不重复开详情；⑥修掉 `--plan --dry-run`
#   会真开详情/真写库的谎报 bug。
# 2026-09-16 晚 v1.11.0（老板拍板「取消搜索体检/采集计划这两个子步骤」）：
#   ① 「② 正式采集 / 🔁 再次采集」= **真跑**（一次点击就真跑；盘上没计划 → 小猎**一个回合内**自定计划
#      + 留档 + 直接跑，中间不停）；「📋 出采集计划」**另起一个按钮**（只出计划，测试期辅助工具，
#      **不挡在主流程前面**）；「🔎 搜索体检」按钮**取消**（`search_rounds.py` 留着按需调用）；
#   ② 体检的两块能力**并进采集执行器**：开工前**先报池子**（`search_page` 接 `on_step`）、
#      开搜前跑 `check_collect_spec` + `check_judge_card`（**有问题拒绝开跑**；缺判据卡=硬拒绝）；
#   ③ 顺手修一个真 bug：`step2_collected` 只认旧形态 `collected_*.json` → 现在也认
#      `collect_*.json` / `job.db`（否则 094907 采了 91 人、③按钮还是灰的）。
_EXEC_WIRED = True


# ═══════════════════════ 纯数据层 ═══════════════════════

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 运行台账（v1.8.7：断点/恢复的第一步）──────────────────────────────────
# 老板 2026-09-15 提的问题："要是在某个过程中网络卡了、电脑出问题了，在全自动的语境下，
# 小猎怎么记得他走到哪里了？"（他自己说"原来想起、一下子表达不清楚"）
# → 他文档里早有名字：重走复盘 §4.2 第五件「**把断点补上**」，原话：
#   "计划进度（走到第几步）——**'乱'的技术含义就是它；也是'放手'的前提**（它每轮冷启动，接得上 = 盘上写全了）"
# 关键认识：小猎的设计前提就是**每轮失忆**（不赌会话记忆，session_id 每次新建）
#   → 问题不是"它的记忆"，而是 **"盘上写全了没有"**：**恢复能力 = 落盘粒度**。
# 此前"这次 run 跑到哪"只在内存（LAST_RUN）→ 面板进程一死就蒸发；本台账把**开始/结束都落盘**。

def log_run(job_code: str, action: str, session_id: str, status: str, **extra) -> None:
    """追加一行运行台账（append-only）。status: running / done / error。

    ⚠️ 台账是**旁路**：任何写盘失败都**不许拖垮运行**（这里吞掉异常）。
    """
    try:
        RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": now_str(), "job_code": job_code, "action": action,
               "session": session_id, "status": status}
        rec.update({k: v for k, v in extra.items() if v not in (None, "")})
        with RUNS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def last_unfinished_run(job_code: str, within_hours: float = 24.0) -> dict | None:
    """本岗**最近一次没有正常收尾**的 run（写了 running、之后没有 done/error）→ 面板提示用。

    同一 session 后面的行覆盖前面的行（running → done/error）；只看 within_hours 内。
    """
    if not RUNS_LOG.exists():
        return None
    try:
        lines = RUNS_LOG.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    per_session: dict[str, dict] = {}
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("job_code") == job_code and r.get("session"):
            per_session[r["session"]] = r
    pend = [r for r in per_session.values() if r.get("status") == "running"]
    if not pend:
        return None
    newest = max(pend, key=lambda r: r.get("ts") or "")
    try:
        t = datetime.strptime(newest["ts"], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - t).total_seconds() > within_hours * 3600:
            return None
    except Exception:
        pass
    return newest


def job_dir(job_code: str) -> Path:
    return CHAT_DIR / job_code


def list_jobs() -> list[dict]:
    jobs = []
    if CHAT_DIR.exists():
        for d in sorted(CHAT_DIR.iterdir()):
            if not d.is_dir():
                continue
            meta = {}
            mp = d / "meta.json"
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            jobs.append({"job_code": meta.get("job_code", d.name),
                         "title": meta.get("title", ""),
                         "display_name": meta.get("display_name", ""),
                         "created_at": meta.get("created_at", ""),
                         "session_id": meta.get("session_id", f"m3chat-{d.name}"),
                         "dir": d})
    jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return jobs


def create_job(title: str = "", jd_text: str = "", jd_bytes: bytes | None = None) -> dict:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_code = f"J-CHAT-{ts}"
    d = job_dir(job_code)
    d.mkdir(parents=True, exist_ok=True)
    (d / "reports").mkdir(exist_ok=True)
    meta = {"job_code": job_code, "title": title or f"岗位 {job_code}",
            # 建岗时写的标题直接当短名（老板自己起的名字最好用）
            "display_name": title.strip(),
            "created_at": now_str(), "session_id": f"m3chat-{job_code}"}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if jd_bytes is not None:
        (d / "jd.txt").write_bytes(jd_bytes)
    else:
        (d / "jd.txt").write_text(jd_text or "", encoding="utf-8")
    (d / "transcript.json").write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    save_state(job_code, jd_provided=bool(jd_bytes is not None or jd_text.strip()),
               step1_analyzed=False, last_action="新建岗位", job_title=meta["title"])
    return meta


def load_transcript(job_code: str) -> list[dict]:
    p = job_dir(job_code) / "transcript.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def append_msg(job_code: str, role: str, content: str, artifacts: list[str] | None = None) -> None:
    p = job_dir(job_code) / "transcript.json"
    msgs = load_transcript(job_code)
    msgs.append({"role": role, "content": content, "ts": now_str(),
                 "artifacts": artifacts or []})
    p.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")


def list_artifacts(job_code: str) -> list[Path]:
    d = job_dir(job_code) / "reports"
    if not d.exists():
        return []
    files = [p for p in d.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _job_dir(job: dict) -> Path:
    d = job.get("dir")
    return Path(d) if d else job_dir(job["job_code"])


# ── 岗位"认人"（v1.8.0）：显示名 / 短名 / 记住最后在看的岗 ──────────────
# 背景（2026-09-14 老板提）：列表里只有 J-CHAT-20260914-xxxxx，人认不出是哪个岗，
# 结果"重跑岗位分析"点在了另一个岗上。而真名**早就在①分析报告里**（本地可读，0 花费）。
# 纪律：**目录名不动**——job_code 是全项目的对齐键（business.db / 产物路径 / state / 会话 id），
# 改名即全链断；记录不可改、展示可重算（§2.11）。
# 可用 M3CHAT_LAST_JOB 覆盖（同 M3CHAT_CHAT_DIR：自测 / 多实例隔离用）
LAST_JOB_FILE = (Path(os.environ["M3CHAT_LAST_JOB"]) if os.environ.get("M3CHAT_LAST_JOB")
                 else WORKSPACE / "data" / ".last_job")
JD_NOISE_LINES = {"禾蛙", "猎聘", "职位编号", "岗位职责", ""}


def _looks_like_job_title(s: str) -> bool:
    """jd.txt 是老板粘贴的整页文本，头几行常是「禾蛙 / 职位编号 / 职位职责：」这类噪音。
    挑第一行**像岗位名**的 —— 这样"还没做①分析"的新岗也能显示人话名。

    ⚠️ 自测现场（2026-09-14）：原来只按"长度≥6 + 不以噪音词开头"筛，结果把
    「职位职责：干活的」当成了岗位名 —— 所以这里再加两道：含冒号的不算、含职责/薪资类词的不算。
    """
    t = (s or "").split("\t")[0].strip()      # 粘贴页常见 "岗位名\t岗位职责： …" → 取 tab 前
    if not (4 <= len(t) <= 40):
        return False
    if any(t.startswith(n) for n in JD_NOISE_LINES if n):
        return False
    if "：" in t or ":" in t:
        return False
    return not any(w in t for w in ("岗位职责", "职位职责", "任职要求", "工作职责",
                                    "职位描述", "薪资", "薪酬", "福利"))


def load_last_job() -> str:
    """最后在看的岗位号（重启面板后恢复用；读不到返回空串）。"""
    try:
        return LAST_JOB_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def save_last_job(job_code: str) -> None:
    try:
        LAST_JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_JOB_FILE.write_text(job_code or "", encoding="utf-8")
    except Exception:
        pass


def save_meta(job_code: str, **updates) -> None:
    """只改 meta.json 的展示字段（短名等）；**绝不改目录名**。"""
    p = job_dir(job_code) / "meta.json"
    meta: dict = {}
    if p.exists():
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta.update(updates)
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def job_display_name(job: dict) -> str:
    """人看得懂的岗位名（纯本地推导，0 花费）。优先级：

      ① meta.display_name（老板自己起的短名）
      ② meta.title（老板建岗时写的标题，且不是占位串"岗位 J-…"）
      ③ ①岗前分析报告里的 jd_extracted.job_title（本地可读，0 花费）
      ④ jd.txt 里第一行像人话的文本（截断 40 字；剔掉"禾蛙/猎聘/职位编号"这类平台噪音）
      ⑤ 退回岗位号

    ⚠️ ② 排在 ③ 前面是故意的：**老板起的名字永远优先**。实测 J-AUTO-20260905-220105 的
    meta.title「AI应用开发工程师（NLP）·中国移动」比①分析提炼的名字更好用。
    """
    dn = (job.get("display_name") or "").strip()
    if dn:
        return dn
    t = (job.get("title") or "").strip()
    if t and not t.startswith("岗位 J-"):
        return t
    ana = latest_report(job, "analyze_", ".json")
    if ana is not None:
        try:
            jt = ((json.loads(ana.read_text(encoding="utf-8-sig")).get("jd_extracted") or {})
                  .get("job_title") or "").strip()
            if jt:
                return jt
        except Exception:
            pass
    jd_p = _job_dir(job) / "jd.txt"
    if jd_p.exists():
        try:
            for line in jd_p.read_text(encoding="utf-8", errors="replace").splitlines():
                if _looks_like_job_title(line):
                    t = line.split("\t")[0].strip()
                    return t[:40] + ("…" if len(t) > 40 else "")
        except Exception:
            pass
    return job.get("job_code") or ""


# ── 岗位状态卡 state.json（不赌 SDK 会话记忆；每次发令注入提示）──

def collect_output_exists(job_code: str) -> bool:
    """②到底采过没有 —— **认账口径（v1.11.0 修的真 bug）**。

    起因（2026-09-16）：`step2_collected` 只认**旧形态** `collected_*.json`，而现在执行器写的是
    `collect_*.json`（轨迹）+ `job.db`（人）→ 于是 094907 库里**采了 91 人、③按钮还是灰的**。
    现在改成"**任一**：有采集轨迹 **或** 本岗库里有候选人"。

    ⚠️ 必须排除 `collect_plan_*.json` —— 那只是**计划**、不是采集产物；认它 = 假成功。
    ⚠️ 用面板自己的 `job_dir()`（受 `M3CHAT_CHAT_DIR` 控制）而不是 job_db 的默认根，
       这样自测/多实例隔离下口径一致。
    """
    for p in list_artifacts(job_code):
        if p.name.startswith("collect_") and not p.name.startswith("collect_plan_"):
            return True
    db = job_dir(job_code) / "job.db"
    if not db.exists():
        return False
    try:
        import job_db
        con = job_db.open_db(job_code, path=db)
        try:
            n = con.execute("SELECT COUNT(*) FROM candidates WHERE job_code=?",
                            (job_code,)).fetchone()[0]
        finally:
            con.close()
        return bool(n)
    except Exception:  # noqa: BLE001
        return False


def load_state(job_code: str) -> dict:
    p = job_dir(job_code) / "state.json"
    st_def = {"job_code": job_code, "jd_provided": False, "step1_analyzed": False,
              "step2_collected": False, "step3_report": False, "last_action": None,
              "decision": None, "decision_note": None, "decision_ts": None,
              # v1.8.4 发布状态（占位，详见文件头）：⚠️ 默认 unknown 必须与 not_published 显式分开，
              # 否则分不清"没发"和"不知道"（决策 32 原话：默认 unknown，不知道就问、不许猜）
              "publish_status": "unknown", "liepin_posts": [],
              "updated_at": None}
    if p.exists():
        try:
            st_def.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    # 兼容旧岗位（无 state.json）：从文件反推
    jd_p = job_dir(job_code) / "jd.txt"
    if jd_p.exists() and jd_p.stat().st_size > 0:
        st_def["jd_provided"] = True
    # 兼容旧岗位（无 state.json）才从产物反推 —— 保持**只升级不降级**（已文档化的行为）。
    # ⚠️ 2026-09-14：我曾把这里改成"产物=权威口径、双向对齐"来治假成功，结果把"state 说已分析
    # 但产物缺失"的旧岗全降级了（v170 AppTest 立刻 7 条红）→ **撤回**。
    # 假成功改在源头治：render_main 跑完**先判本次有没有真产出文件**，再决定写不写 step1_analyzed。
    if any(p.name.startswith("analyze_") for p in list_artifacts(job_code)):
        st_def["step1_analyzed"] = True
    # 2026-09-22 补（治"分析完了、对话里却记不了拍板"）：分析完 + 无决策记录 ⇒ **等价于待拍板**。
    # 依据：① 设计口径本来就是"分析完 = 进入等你拍板"（见 DECISION_TEXT["pending"]）；
    #   ② 断口在写入口而不在读取口 —— `decision="pending"` 只在 action_kind=="analyze" 时写
    #      （render_main），而 09-21 实测那个岗的①分析是在**自由对话**里跑完的
    #      （runs.jsonl: action="chat"、产出 analyze_*.json）⇒ 那条写入分支根本没走到，
    #      于是 decision 永远 null，四个分类器（拍板/重判断/打招呼报告前置）的门全关着。
    # 为什么在**这里**修：全项目读 decision 只走 load_state（单源）⇒ 一处修、四处齐
    #   （分类器门 / 进度条 / 按钮锁 decision_ok / 状态卡）。
    # 为什么不假写历史：只推导读取口径，decision_note / decision_ts 仍为空——不伪造"老板拍过板"。
    # 连带修正（**故意**的）：无决策记录 ⇒ 按钮锁由"不锁（None 当旧岗兼容）"变成"锁"。
    #   这才是"没拍板就不许采"的本意（09-21 16:19 那次 70 分钟采集，就是在 null 下被放行的）。
    if st_def["step1_analyzed"] and not st_def.get("decision"):
        st_def["decision"] = "pending"
    # v1.11.0 修的真 bug：旧口径只认 `collected_*.json`，而新形态写的是 `collect_*.json` + `job.db`
    #   → 094907 采了 91 人、③按钮还是灰的。认账口径见 `collect_output_exists`。
    if collect_output_exists(job_code):
        st_def["step2_collected"] = True
    # v1.12.0：③池子评估已取消 → 这一步改成「💬 打招呼报告」（产物 = 打招呼报告_*.json）
    if any(p.name.startswith("打招呼报告_") for p in list_artifacts(job_code)):
        st_def["step3_report"] = True
    return st_def


def save_state(job_code: str, **updates) -> None:
    st_ = load_state(job_code)
    st_.update(updates)
    st_["updated_at"] = now_str()
    (job_dir(job_code) / "state.json").write_text(
        json.dumps(st_, ensure_ascii=False, indent=2), encoding="utf-8")


DECISION_TEXT = {
    None: "",
    "pending": "⚖️ ①岗前分析完成，正在等老板拍板（老板回复 做吧/不做/先核实 之一；此前可追问理由）",
    "accept": "✅ 老板已拍板：做这单",
    "decline": "⛔ 老板已拍板：不做这单（②采集/③评估/发岗已锁定；老板改主意会说「重新判断」重跑①）",
    "clarify": "📌 老板已拍板：先核实/暂缓再定（②③暂锁；核实完老板会说「做吧」或「不做」覆盖本决策）",
}


def decision_text(decision: str | None) -> str:
    return DECISION_TEXT.get(decision, "")


# ── 发布状态（v1.8.4 占位；目的 = 决策 32，2026-09-11 老板拍板）──────────────
# 「是否发岗」= **不阻塞的分岔**：发了 → 打招呼走「立即开聊」带岗位卡片（**需 hjobId**）；
# 没发 → 「不选择职位开聊」直发预设语（**不需 hjobId**）。该步**只记录**，
# **小猎不许以为它能替你发岗**（发岗动作永远是人工）。
# 猎聘侧事实：hjobId 是**8 位纯数字**，页面上**不显示明文**、只在链接地址里（/job/gethjobdetail?hjobId=…）。

PUBLISH_STATUS_TEXT = {
    "unknown": "❓ 发布状态未知",
    "published": "📤 已发布到猎聘",
    "not_published": "⭕ 未发布到猎聘",
}
PUBLISH_POST_KEYS = ("hjob_id", "title", "city", "published_at", "source", "note")


def publish_status_of(st: dict) -> str:
    """发布状态：**有发布记录 = 已发布**（记录是事实，胜过声明）；否则用声明值，缺省 unknown。"""
    if st.get("liepin_posts"):
        return "published"
    return st.get("publish_status") or "unknown"


def publish_status_text(st: dict) -> str:
    s = publish_status_of(st)
    n = len(st.get("liepin_posts") or [])
    return PUBLISH_STATUS_TEXT.get(s, s) + (f"（{n} 条记录）" if s == "published" else "")


def append_publish_post(job_code: str, rec: dict) -> dict:
    """追加一条发布记录（**字段固定** PUBLISH_POST_KEYS，不自造字段）+ 置 published。"""
    st_ = load_state(job_code)
    posts = list(st_.get("liepin_posts") or [])
    posts.append({k: str(rec.get(k) or "").strip() for k in PUBLISH_POST_KEYS})
    save_state(job_code, liepin_posts=posts, publish_status="published")
    return posts[-1]


def set_publish_status(job_code: str, status: str) -> None:
    """置发布状态（unknown/not_published）；**同时清空发布记录**——状态与事实不许打架（面板上已明示）。"""
    if status not in ("unknown", "not_published"):
        raise ValueError(f"只能用 unknown / not_published 覆盖（published 由发布记录决定）：{status!r}")
    save_state(job_code, publish_status=status, liepin_posts=[])


def state_block(job: dict) -> str:
    """状态卡文本：注入每条 prompt，让 agent 无论有没有会话记忆都掌握岗位现状。"""
    st_ = load_state(job["job_code"])
    jd_p = _job_dir(job) / "jd.txt"
    arts = list_artifacts(job["job_code"])
    jd_status = "已提供" if (st_.get("jd_provided") and jd_p.exists()) else "为空/未提供"
    dec_line = decision_text(st_.get("decision"))
    dec_extra = (f"（备注：{st_['decision_note'][:60]}）"
                 if st_.get("decision_note") else "")
    prof_p = job_profile_path(job)
    return (
        f"【岗位状态卡】{job.get('title','')}（{job['job_code']}）\n"
        f"- 岗位 JD 文件：{jd_p.as_posix()}（{jd_status}。已提供则开口前必须先读它）\n"
        f"- ① 岗前分析：{'已完成' if st_.get('step1_analyzed') else '未做'}"
        f"（最近一次动作：{st_.get('last_action') or '无'}）\n"
        f"- ⚖️ 老板决策：{dec_line or '尚未到判断点（①分析做完后老板会在对话里拍板 做/不做/先核实）'}{dec_extra}\n"
        f"- 📋 岗位资料（PM 口径/猎头关注，若已建则涉本岗口径先读它）：{prof_p.as_posix()}\n"
        f"- 现有产物 {len(arts)} 个（如需参考请读 reports 目录，最新的在前）\n"
        f"- 成长规则库：{RULES.as_posix()}（执行业务步骤前先读对应小节并遵守）\n"
    )


# ── 成长账（records.jsonl + rules.md）──────────────────────────────

def append_record(job: dict, step_no: int, note: str, tags: str = "") -> dict:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now_str(), "job_code": job["job_code"], "job_title": job.get("title", ""),
           "step": step_no, "step_name": STEP_NAME.get(step_no, str(step_no)),
           "note": note.strip(), "tags": [t.strip() for t in tags.split(",") if t.strip()],
           "status": "待消化"}
    with RECORDS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def list_records(job_code: str | None = None, pending_only: bool = False) -> list[dict]:
    if not RECORDS.exists():
        return []
    out = []
    for line in RECORDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if job_code and r.get("job_code") != job_code:
            continue
        if pending_only and r.get("status") != "待消化":
            continue
        out.append(r)
    return out


def mark_records_digested(job_code: str) -> int:
    if not RECORDS.exists():
        return 0
    lines = RECORDS.read_text(encoding="utf-8").splitlines()
    n = 0
    with RECORDS.open("w", encoding="utf-8") as f:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                f.write(line + "\n")
                continue
            if r.get("job_code") == job_code and r.get("status") == "待消化":
                r["status"] = "已消化"
                r["digested_at"] = now_str()
                n += 1
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return n


def ensure_rules() -> None:
    if RULES.exists():
        return
    PROMPTS.mkdir(parents=True, exist_ok=True)
    RULES.write_text(
        "# 成长规则库（小猎的方法论纠错沉淀）\n\n"
        "> 来源：老板与助理分步骤测试时的纠错 → 消化成规则。每条一句话：\n"
        "> 当〔情境〕时，应〔怎么做〕（来源：成长账 ts / 岗位）\n"
        "> 小猎执行涉及步骤前应阅读本文件对应小节并遵守。\n\n"
        "## ① 岗位分析\n（暂无）\n\n"
        "## ② 采集\n（暂无）\n\n"
        "## ③ 池子评估\n（暂无）\n\n"
        "## ④ 汇报 / HTML 过程文档\n（暂无）\n\n"
        "## 流程 / 工具\n（暂无）\n",
        encoding="utf-8",
    )


# ═══════════════════════ 任务构建（发令内容）══════════════════════

def job_profile_path(job: dict) -> Path:
    """岗位资料文件（v1.7.3，岗位目录 = 正式底座的附加信息载体）：
    {"job_code", "pm_notes": [...], "special_notes": [...], "events": [{"ts","who","note"}]}"""
    return _job_dir(job) / "job_profile.json"


def _recent_boss_text(job_code: str, limit: int = 4) -> str:
    """本会话老板最近 limit 条非任务原话（注入用；v1.7.2：agent 无跨 run 记忆，
    老板在对话里给的口径/教学原文不注入它真看不到）。"""
    msgs = load_transcript(job_code)
    boss_lines = []
    for m in msgs:
        c = (m.get("content") or "").strip()
        if m.get("role") != "user" or not c:
            continue
        if c.startswith("老板要你") or c.startswith("老板已确认"):
            continue  # 任务注入文本，非老板原话
        boss_lines.append(c)
    recent = boss_lines[-limit:]
    if not recent:
        return "〔本会话暂无可引用的老板原话〕"
    return "\n\n".join(f"〔老板消息 {i + 1}〕{c}" for i, c in enumerate(recent))


def build_free_task(job: dict, user_msg: str) -> str:
    """自由讨论/追问：注入状态卡 + 能力边界 + 完整路径，先读文件再开口（禁 bash、禁列盘、读不到不许编）。

    v1.7.1：检测"老板教规则"意图 → 追加成长沉淀操作指引（小猎自助写 rules.md，只追加不改删）。
    v1.7.3：检测"记到岗位资料/PM 口径"意图 → 追加岗位资料落盘指引（job_profile.json，只追加）。
    ⚠️ 2026-09-04 v1.6.2 修复：此前本函数写好却未接线，自由聊天把老板原始消息直接发给 agent，
    persona 承诺“路径每条消息都给”是假的 → agent 反复列盘找 jd.txt → “找不到岗位文件”。
    现由 render_main 对每条自由消息调用本函数，路径逐条写死。
    """
    jd_p = _job_dir(job) / "jd.txt"
    reports_dir = (_job_dir(job) / "reports").as_posix()
    latest = next((a for a in list_artifacts(job["job_code"])
                   if a.name.startswith("analyze_") and a.suffix == ".json"), None)
    analyze_hint = (latest.as_posix() if latest
                    else f"{reports_dir}（当前没有 analyze_*.json，就如实说岗前分析还没做，不用去找别的）")
    teach = any(w in user_msg for w in TEACH_WORDS)
    to_profile = any(w in user_msg for w in PROFILE_WORDS)
    inject = _recent_boss_text(job["job_code"])
    # —— v1.7.4 结构性修改硬边界（删/改已有记录、动代码/配置 → 拒绝并指向实施侧）——
    struct_mod = (any(w in user_msg for w in STRUCT_OBJ_WORDS)
                  and any(w in user_msg for w in STRUCT_ACT_WORDS))
    struct_hint = ""
    if struct_mod and not teach and not to_profile:
        struct_hint = (
            "\n【结构性修改·硬边界（务必遵守）】老板这条消息要求删除/取消/修改已有内容"
            "（岗位资料条目 / 成长库规则 / 代码 / 配置等）。这类**结构性修改不在你自由对话的能力内**"
            "（本通道只允许：读文件 + 受控追加——\"记到成长库 / 记到岗位资料\"）。\n"
            "请你如实回复老板：「结构性修改（删/改已有记录、动代码/配置）由老板或实施对话处理，"
            "我不在自由对话里执行这类操作」。并在回复里：①简述你理解的修改意图（确认没听错）；"
            "②说明建议路径（实施对话代改 / 老板人工处理，可简述改后效果）。\n"
            "**禁止**自己上手删改任何文件（含岗位资料/成长库/代码），禁止绕过此边界。\n"
        )
    # —— 成长沉淀分支（rules.md）——
    growth_hint = ""
    if teach:
        growth_hint = (
            f"\n【老板要你沉淀规则·背景（重要，先读）】你每次都是全新执行、没有跨轮记忆，"
            "老板教你的经验原文在**本会话对话记录**里——系统已把最近几条老板原话注入如下，"
            "**先从这里找老板教过你的规则/经验原文**（通常含\"教你/说明一下/记住/这个…\"等教学话术；"
            "跳过纯岗位问答）：\n"
            f"{inject}\n"
            f"\n【老板要你沉淀规则·操作步骤】用**文件工具**完成（禁 bash）：\n"
            f"  1) 先读成长规则库全文：{RULES.as_posix()}\n"
            "  2) 判断这条规则属于哪一节（## ① 岗位分析 / ## ② 采集 / ## ③ 池子评估 / "
            "## ④ 汇报 / HTML 过程文档 / ## 流程 / 工具）——不确定就放「流程 / 工具」；\n"
            "  3) 只在该节写入：若该节只有（暂无）占位，把占位替换成你的规则行；"
            "若已有规则，则在最后一条规则后、下一个 ## 小节标题前【追加】一行，格式：\n"
            f"     `- [来源 本岗 {job['job_code']} / {datetime.now().strftime('%Y-%m-%d')}] 当〔情境〕时，应〔怎么做〕`\n"
            "  4) 规则内容**只从上面注入的老板原话里提炼归纳**成一句，不许编造老板没说的；"
            "若注入内容里找不到可提炼的教学原文，如实告诉老板「我没找到您教的规则原文，请把原话发我」，"
            "**不许脑补、不许拿猜的内容写进成长库**；\n"
            "  5) 不许删改任何已有规则行，不许动其他文件；\n"
            "  6) 写完回读确认，回复里展示你新增的行与所在节。\n"
        )
    # —— 岗位资料落盘分支（job_profile.json）——
    profile_hint = ""
    if to_profile:
        profile_hint = (
            f"\n【老板要你记到岗位资料·背景（重要，先读）】老板给的口径/临时需求/PM 答复原文"
            "在**本会话对话记录**里——系统已把最近几条老板原话注入如下，先从中找要记的内容：\n"
            f"{inject}\n"
            f"\n【记到岗位资料·操作步骤】用**文件工具**完成（禁 bash）：\n"
            f"  1) 先读岗位资料文件（不存在就按下面结构新建）：{job_profile_path(job).as_posix()}\n"
            "     结构 = {\"job_code\": \"...\", \"pm_notes\": [\"PM/发单方口径、补充、岗位变动…\"], "
            "\"special_notes\": [\"猎头内部关注、客户特殊要求、潜规则…\"], "
            "\"events\": [{\"ts\": \"日期\", \"who\": \"PM/老板\", \"note\": \"变动或补充\"}]}\n"
            "  2) 判断内容属于哪类：PM/发单方说的口径与岗位变动 → pm_notes；"
            "老板自己的关注点/客户特殊要求（含\"不招女的\"这类内部记录）→ special_notes；"
            "带时间点的变动/补充 → 同时追加一条 events；\n"
            "  3) **一律追加新条目，绝不删改已有条目**（最新口径 = 数组最后一条）；文件不存在则新建骨架；\n"
            "  4) 内容只从注入的老板原话提炼，不编造；找不到可记内容就如实说；\n"
            "  5) ⚠️ 若记录含性别/年龄/婚育/户籍等歧视性要求：属【客户口径的内部事实记录】，"
            "只写进 special_notes，**绝不用于筛选条件/搜索关键字/任何对外文案**，并在回复里提示老板这条合规边界；\n"
            "  6) 写完回读确认，回复里展示你记了什么、进哪个字段。\n"
        )
    # —— v1.8.5 拍板硬边界（**只在"等你拍板"时注入** → 其它时候 0 成本）——
    # 治的是实测那句假事实："「做吧」我记为接单（accept）"——它没有这只手，却说了这句话。
    decision_hint = ""
    if load_state(job["job_code"]).get("decision") == "pending":
        decision_hint = (
            "\n【拍板·硬边界（本条务必遵守）】老板这句话**可能是在拍板**，但**「记录拍板」不是你的手**："
            "你**没有**写 state.json / decision 的能力与授权（结构性修改不在自由对话范围内）。"
            "若你判断他是在说做/不做/先核实，你**只能**回：「我听明白了，请回『做吧 / 不做 / 先核实』"
            "确认，我才好往下走」（面板也会自动帮他确认）。"
            "**严禁说「我记为 accept / 已记下决策 / 已经落盘」**——那是系统机制的活，"
            "说了就是假执行（纪律：判断错不罚、不诚实必罚）。\n"
        )
    return (
        f"{state_block(job)}\n{CAPABILITIES}\n"
        "【必须先读再答】你要读的文件完整绝对路径已在上方状态卡和下面 1) 2) 里**逐条写死**——"
        "**直接用文件工具读那个路径**，不要列目录、不要遍历磁盘、不要探测或猜测任何其他路径"
        "（Windows 下列盘根目录会因系统占用文件报错，属正常现象，不代表文件不存在）。\n"
        "回答任何关于本岗的问题前，用**文件工具**（禁止用 bash/命令行）读：\n"
        f"  1) {jd_p.as_posix()}（JD，非空则不许要求老板粘贴）\n"
        f"  2) {analyze_hint}\n"
        "读完再作答，并可以引用文件内容。文件工具真实报错时，把报错原文原样贴给老板并说明读不了哪一步；"
        "只要文件工具成功返回过内容，就不得声称“读不到/目录没挂载/被锁”。\n"
        f"{growth_hint}"
        f"{profile_hint}"
        f"{struct_hint}"
        f"{decision_hint}"
        f"【老板消息】{user_msg}\n"
        "请以「小猎」身份回复。若老板要求执行某一步骤并出过程文档，把工作过程写成中文 HTML "
        "保存到该岗 reports 目录（文件名自定，带上步骤与时间），回复里给出文件路径。"
        "（⚠️ ①岗前分析例外：那份过程网页由面板本地渲染，你只交 JSON 里的 process 短字段。）"
    )


def job_brief_block(job: dict) -> str:
    """【本岗现状卡】本地读盘生成（0 花费）：路径 + 现有产物清单 + 建档时间 + 当前进度。

    2026-09-14 加它的原因（实测一次①分析 8 轮 / 139,075 token）：
      其中 2 轮是它自己 glob 列目录、1 轮读 meta/state 去「找路」（≈25,478 token），
      根因是任务文本只给了三个文件路径，没告诉它「这个岗现在有什么、状态是什么」。
      → 把事实在任务里一次给全，它就不必去找；配合①的 bare 档（连 glob 本事都收走）双重封堵。
    """
    st_ = load_state(job["job_code"])
    d = _job_dir(job)
    arts = list_artifacts(job["job_code"])
    jd_p = d / "jd.txt"
    # ⚠️ 别用目录 mtime 当"建档时间"——那是"目录里最后有增删的时间"（实测本单会印成 11:04 而不是 09:49）。
    # 正解：meta.json 的 created_at，读不到才退回目录 mtime。
    created = "（未知）"
    meta_p = d / "meta.json"
    if meta_p.exists():
        try:
            created = str(json.loads(meta_p.read_text(encoding="utf-8")).get("created_at") or created)
        except Exception:
            pass
    if created == "（未知）":
        try:
            created = datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    if arts:
        art_lines = "\n".join(f"    - reports/{a.name}（{a.stat().st_size} 字节）" for a in arts[:20])
        art_block = (f"- 本岗 reports 目录现有产物 {len(arts)} 个（最新在前，**已替你列好，不必再列目录**）：\n"
                     f"{art_lines}")
    else:
        art_block = "- 本岗 reports 目录**当前为空**（还没有任何产物，不必去列目录确认）"
    progress = ("①岗前分析：已做过（本次是重跑，要覆盖旧结论，并在回复里点明改了什么）"
                if st_.get("step1_analyzed") else "①岗前分析：还没做过（本次是首次）")
    dec = {"accept": "老板已拍板：做", "decline": "老板已拍板：不做",
           "clarify": "老板已拍板：先核实", "pending": "分析完待老板拍板"}.get(
               st_.get("decision") or "", "尚未拍板")
    jd_stat = "为空" if not (jd_p.exists() and jd_p.stat().st_size) else f"非空 {jd_p.stat().st_size} 字节"
    return (
        "【本岗现状卡（本地读盘生成，0 花费；以此为准，不要再去别处找）】\n"
        f"- 岗位号 / 标题：{job['job_code']}｜{job.get('title') or ''}\n"
        f"- 岗位目录建档时间：{created}\n"
        f"- 岗位 JD 文件：{jd_p.as_posix()}（{jd_stat}）\n"
        f"{art_block}\n"
        f"- 当前进度：{progress}；{dec}\n"
        f"- 成长规则库：{RULES.as_posix()}\n"
        "- ⚠️ 你要读写的东西，路径在上面和下面都写全了。你**没有**列目录/搜索文件的工具，"
        "也不需要——不要试图列目录、搜索文件或遍历磁盘。"
    )


def build_step1_task(job: dict) -> str:
    """步骤① 岗前分析（判断 + 结论 JSON；过程网页本地渲染）。

    2026-09-14 改（省 token 第一刀，见 §4.4）：
      ① 路径 / 现有产物 / 当前进度**一次给全**（job_brief_block）→ 免掉它自己找路（实测约 25,478）；
      ② 明确「写完不要回读、不要列目录核对」→ 校验改由本地代码做（local_checks），结果贴进对话；
      ③ 工具面收窄（TOOL_PROFILE_BY_ACTION: analyze=bare），连 glob 都没给 → 机制上堵住列目录。
    2026-09-15 改（省 token 第二刀，见 §4.1-A）：
      ④ **过程网页不再由它手写**（原来 15% 的开销、且**没有长度上限**：盘上真网页 9.4K~24.1K 字节、
         一次重跑 +51%）→ 改成它只交 analyze JSON 里的 `process` 三个短字段（合计硬顶 600 字），
         页面由 render_analyze_html 本地渲染。**它写的不再是"两个大文件"，只有一个**——
         顺带根除 2026-09-14「一次写两个大文件撞输出上限、两个文件全丢」的事故形状。
      ⚠️ 判断内容（评分口径 / 态度 / 风险 / 请老板拍板的那段话）**一个字未改**。
    """
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_json = f"{reports_dir}/analyze_{ts}.json"
    method = (PROMPTS / "analyze_job.txt").as_posix()
    rules_hint = (f"先读成长规则库 {RULES.as_posix()}，遵守其中「① 岗位分析」及流程小节的相关规则。\n"
                  ) if RULES.exists() else ""
    return f"""老板要你执行【步骤① 岗前分析】。请全程用文件工具完成：
{job_brief_block(job)}

1. 【必须】先读岗位 JD 文件：{jd}
   —— 只要该文件非空，就不许向老板索要 JD 或要求他粘贴；JD 为空才提示老板提供。
2. 读你的岗前分析方法论手册（严格按它的 JSON 输出格式，不增不减字段）：{method}
3. 按手册完成岗前分析：提取岗位信息、判断进展、逐项评分（佣金/HC数量/新鲜度/上游靠谱度/匹配难度 各0-5）、
   算总分与等级、写清风险清单与建议、判定「接单/沟通/放弃」，并生成 4 组猎聘搜索关键字。
4. {rules_hint}
5. 把完整 JSON 结果写入：{report_json}（路径已定，直接写）
   ⚠️ **本次你只写这一个文件**。JSON 除上面 5 块外，再加第 6 块 `process`（**过程叙述**）——
   它只装"本地代码编不出来、只有你知道"的三件事，结构：
   {{"process": {{"keyword_reasoning": "≤250 字：4 组关键字怎么选出来的（哪组优先、词为什么这样拆、想过但没用的词）",
   "verify_list": ["≤5 条，每条 ≤50 字：动手前必须先跟 PM 核实的口径"], "next_step": "≤100 字：下一步建议"}}}}
   三块**合计不超过 600 字**（本地会量，超了会被截断并标注）。
6. ⚠️ **过程网页不用你写**（2026-09-15 起）：读了什么／关键判断／逐项评分依据／风险／结论，
   由老板侧的本地代码从你这份 JSON **自动渲染**成网页——你**一个字 HTML 都不要写**。
   原因（实测，请勿重犯）：原来要求"再单独一次写 HTML"，这份网页没有长度上限（一回重跑自己涨到
   13,065 字符、占掉整次分析约 15% 的开销），还曾因一次写两个大文件撞上单次输出上限导致
   **两个文件全丢**（2026-09-14 事故）。把省下来的力气全花在判断上。
   写完 JSON 后**不要再回读、不要列目录核对**——产物校验由老板侧的本地代码做（0 花费）。
7. 最后用「老板，我弄的咋样？」口吻给我一段**判断式**回复（≤10 句，**给人读的判断，不是报告摘要**——别罗列全部字段）：
   - 第 1 句给明确态度：从「这单我建议：接 / 先沟通再定 / 别做」三选一（与你报告的 recommendation 一致，
     不许含糊骑墙）；
   - 接着给最硬的 3~4 条理由（佣金/HC/新鲜度/上游/难度里哪几项拉分、哪几项拉胯，各一句话，可引用评分）；
   - 再点 1~2 条最该注意的风险或要先跟 PM 核实/澄清的口径；
   - 最后**请老板拍板**：「您定：做 / 不做 / 先核实——也可以再问我理由。」
   注意：老板拍板后岗位状态会记决策（accept/decline/clarify），他说「做吧」才会解锁②采集等下一步；
   判断错不罚、不诚实必罚。
8. 回复里给出上面那个 JSON 的路径（过程网页的路径由本地渲染时补上，你不用管）。
{CAPABILITIES}"""


# （v1.8.2 摘除）build_report_task()「导出 HTML 汇报」：出生即验收样板、11 天用 1 次、0 消费者、
# 定位与内容自相矛盾，且是最后一个"LLM 手写整页 HTML + 全量工具面"的按钮 → 已删（详见文件头 v1.8.2）。


# ── 判断拍板意图（v1.7.0 判断对话化：老板对①岗前分析结果拍板 做/不做/先核实）──

# 拍板词表（保守：宁可不命中落自由对话，也不误触记错决策；问句一律不触发）
ACCEPT_WORDS = ("做吧", "咱做", "可以做", "值得做", "就做", "决定做", "确定做", "做这单",
                "做做看", "接单", "接吧", "接单吧", "接了", "拿下", "干吧", "干这单",
                "可以，做", "好，做", "行，做")
DECLINE_WORDS = ("不做", "别做", "放弃", "不接", "别接", "算了", "不干", "拒了", "不值得",
                 "别做了", "不做吧", "放弃吧", "不做了", "钓鱼单", "坑单", "这单不行", "别搞")
CLARIFY_WORDS = ("先核实", "先问", "先沟通", "先确认", "先跟", "核实一下", "再想想", "考虑一下",
                 "先别定", "跟pm", "问pm", "看看再说", "先放着", "先不决定")
REJUDGE_WORDS = ("重新判断", "重新分析", "重跑分析", "再分析", "重新看看", "重看一遍", "再判断")


# ── 拍板·疑似识别与本地反问（v1.8.5：「闸门挪进门里」的第一步）────────────────
# 为什么加它（实测两次；§2.4 纪律②原话："词表漏一个词，就等于代码替你拍了板"）：
#   · 09-09「直接往下走吧，把这个岗位写入岗位」→ 未命中 ACCEPT_WORDS → 落自由对话 → 它**自行解读 accept**；
#   · 09-15「我们做这个岗位吧」→ 仍未命中 → 落自由对话 → 它**没敢动 state**（守住了边界），
#     但**嘴上说「我记为 accept」**（state 仍是 pending）→ 老板看到一句**假事实**。
# 自然语言穷举不完 → 正解不是继续扩词表，而是**没把握就当场问清**：
#   精确词命中 → 直接记（现状）｜**疑似命中 → 面板本地反问（0 花费、绝不替老板记）**｜都不命中 → 自由对话（现状）
ACCEPT_HINT_WORDS = ("做", "接", "干", "拿下", "推进", "往下走", "往前", "开工", "上这单")
DECLINE_HINT_WORDS = ("不做", "别做", "不接", "不干", "放弃", "算了", "不搞", "拒了", "不值得")
CLARIFY_HINT_WORDS = ("先核实", "先问", "先沟通", "先确认", "再想想", "考虑一下", "先别定")
DECISION_TARGET_WORDS = ("这个岗", "这岗", "这个单", "这单", "这活", "这活儿", "岗位", "它")
DECISION_CONFIRM_WORDS = ("对", "是", "嗯", "好", "可以", "行", "没错", "ok", "OK", "Ok")
ASK_MARK = "我听明白了，但不敢替你记"
CANCEL_REPLY = ("✅ 收到，**当没说**——决策仍是「待拍板」，②③/发岗继续锁着。\n"
                "（这条是面板本地处理的，**没花 token**；要继续就说「做吧 / 不做 / 先核实」，或直接聊别的。）")
# v1.9.1：②发令落到"执行链路未接线"时的**面板本地**回复（不调 agent、0 token）
EXEC_NOT_WIRED_REPLY = (
    "🔌 收到，但**②正式采集的执行链路还没接上**——这一步现在跑不了。\n\n"
    "本轮只做完了**按钮层**（改名「②正式采集」+ 排到「体检 → 正式采集 → ③评估」的顺序），"
    "真正的执行器（**翻页 + 本地粗筛打分 + 写进本岗库 `job.db` + 本地渲染采集报告**）"
    "是下一轮的事：做完那三件、你过目后才解锁按钮。\n\n"
    "为什么要先灰着：旧的采集只会抓**每个关键字首页 30 人**、不翻页、不进本岗库，"
    "跟刚过目的《②正式采集·形态计划》不是同一个形态——**宁可先灰着，也不给你跑出个旧形态还冒充新形态。**\n\n"
    "现在能用的：**🔎 搜索体检**（只读人数、不抓人）和 **③池子评估**；"
    "这条回复也是面板本地给的，**没花 token**。")


def _looks_like_question(m: str) -> bool:
    """讨论/反问句不触发任何拍板动作（与 detect_decision_intent 内联判据保持一致）。"""
    return ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
            or "？" in m or "?" in m or m.endswith("吗") or m.endswith("么"))


def detect_decision_hint(msg: str) -> str:
    """**疑似拍板**：只决定"要不要当场反问"，**绝不写状态**。返回 accept/decline/clarify/""。"""
    m = msg.strip()
    if not m or _looks_like_question(m) or "别放弃" in m or "别急着" in m:
        return ""
    if any(w in m for w in DECLINE_HINT_WORDS):
        return "decline"          # decline 先于 accept（"不值得做"应判 decline）
    has_target = any(w in m for w in DECISION_TARGET_WORDS)
    if has_target and any(w in m for w in ACCEPT_HINT_WORDS):
        return "accept"
    if has_target and any(w in m for w in CLARIFY_HINT_WORDS):
        return "clarify"
    return ""


def confirmed_intent(msg: str, awaiting: str) -> str:
    """老板对上一轮「拍板反问」的回答。返回 accept/decline/clarify（=记下）/ "cancel"（=当没说）/ ""。

    ⚠️ 这不是"小猎自行解读拍板"：面板**先把动作明确陈述出来问过**（"你是要拍板做这单吗？
    回「是」我就照这个记"），老板点头才算 —— 属于**人对一个已陈述动作的确认**，闸门在门里。
    """
    if not awaiting:
        return ""
    m = msg.strip()
    if not m or _looks_like_question(m):
        return ""
    if any(w in m for w in ("不是", "不对", "当我没说", "别记", "算了")):
        return "cancel"
    if any(w in m for w in DECLINE_HINT_WORDS):
        return "decline"
    if any(w in m for w in DECISION_CONFIRM_WORDS):
        return awaiting
    return ""


def last_pending_ask(job_code: str) -> str:
    """上一轮是不是面板刚发过「拍板反问」？是则返回当时问的意图，否则 ""。"""
    for m in reversed(load_transcript(job_code)):
        if m.get("role") == "user":
            return ""
        if m.get("role") == "assistant":
            c = m.get("content") or ""
            if ASK_MARK in c:
                for k in ("accept", "decline", "clarify"):
                    if f"decision={k}" in c:
                        return k
            return ""
    return ""


def build_decision_ask(hint: str, note: str = "") -> str:
    """本地反问确认（0 花费、不写状态）：疑似拍板但没命中精确词 → 先问清，**绝不替老板记录**。"""
    label, word = {"accept": ("做这单", "做吧"),
                   "decline": ("不做这单", "不做"),
                   "clarify": ("先核实再定", "先核实")}.get(hint, ("做这单", "做吧"))
    note_txt = f"（你的原话：{note.strip()[:60]}）" if note.strip() else ""
    return (f"🤔 **{ASK_MARK}**——{note_txt}\n"
            f"你是要拍板「**{label}**」吗？\n"
            f"· 回「**{word}**」= 我记下 `decision={hint}`（②采集 / 📤发岗助手 / ③评估立刻解锁）\n"
            "· 回「**是 / 对**」= 也照这个记（**这是你点头，不是我猜**）\n"
            "· 回「**不是**」= 当没说，决策仍是待拍板\n"
            "为什么不直接记：拍板只能由你说出口的话触发——09-09、09-15 各踩过一次"
            "（它嘴上说「我记为 accept」，其实系统里没记），所以现在**当场问你一句**。")


def claims_recorded_decision(reply: str) -> bool:
    """小猎的回复里有没有"我把决策记下了"这类**声称**（供面板事实核对用）。"""
    t = reply or ""
    return bool(re.search(r"(我记为|已记为|已经记|已记入|已记录|记下了|记入岗位决策|已落盘|已经落盘|我已记)", t)
                and re.search(r"(accept|decline|clarify|接单|不接|先核实|拍板|决策)", t))


def detect_decision_intent(msg: str) -> str:
    """识别老板对①岗前分析的拍板。返回 "accept"/"decline"/"clarify"/""（未命中=自由对话）。

    仅在 decision==pending 时由路由调用。保守规则：
    - 讨论/反问句（怎么/为什么/？/吗…）一律不触发 → 落自由对话（老板可追问理由）；
    - 「别放弃/别急着…」等反向表达不触发 decline；
    - 先查整句短词（"做"/"不做"/"可以"…），再查包含词；decline 先于 accept 查
      （"不值得做" 应判 decline 而非 accept）。
    """
    m = msg.strip()
    if not m:
        return ""
    if ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
            or "？" in m or "?" in m or m.endswith("吗") or m.endswith("么")):
        return ""
    if "别放弃" in m or "别急着" in m:
        return ""
    m_short = m.rstrip("。！!~ ")
    if m_short in ("做", "做吧", "可以", "可以做", "好", "行", "接", "干", "拿下"):
        return "accept"
    if m_short in ("不做", "别做", "算了", "放弃", "不接", "不干", "不做吧", "别做了"):
        return "decline"
    if any(w in m for w in DECLINE_WORDS):
        return "decline"
    if any(w in m for w in ACCEPT_WORDS):
        return "accept"
    if any(w in m for w in CLARIFY_WORDS):
        return "clarify"
    return ""


def detect_rejudge_intent(msg: str) -> bool:
    """老板想重跑①重新判断（decision 已非空时启用：decline 改主意 / 想再看一遍）。"""
    return any(w in msg for w in REJUDGE_WORDS)


def record_decision(job: dict, decision: str, note: str = "") -> None:
    """拍板落盘（本地动作，不调 agent）。note = 老板原话截断，留档可查。"""
    label = {"accept": "做", "decline": "不做", "clarify": "先核实"}.get(decision, decision)
    save_state(job["job_code"], decision=decision,
               decision_note=(note or "").strip()[:80] or None,
               decision_ts=now_str(), last_action=f"拍板：{label}")


def build_decision_reply(decision: str, note: str = "") -> str:
    """拍板确认消息（本地生成，留在对话里；理解错可纠正）。"""
    note_short = (note or "").strip()[:60]
    if decision == "accept":
        return ("✅ 收到：**这单咱做**。已记入岗位决策，②采集/③评估/发岗解锁。\n"
                "下一步你挑一个：说「去猎聘跑一轮」（先出采集计划请你确认）／点 📋 生成发岗文字"
                "／📥 入库当前岗。理解错了跟我说一声即可。")
    if decision == "decline":
        return ("✅ 收到：**这单不做**。已记入岗位决策，②③/发岗已锁定。\n"
                f"备注已留：{note_short or '（无）'}。想改主意或重新看一遍，说「重新判断」即可。")
    return ("📌 收到：**先核实再定**。②③/发岗暂锁，等你核实完回来说「做吧」或「不做」即可。\n"
            f"备注已留：{note_short or '（无）'}。")


# ── 步骤② 正式采集（v1.9.1 接线；原「探索采集」）──────────────────────────────
# 形态：**翻页 → 本地粗筛（0 token）→ 过线者 upsert 进本岗库 data/chat/<岗>/job.db → 本地渲染采集报告**
#   （计划见 工作文档\②正式采集·形态计划.md；老板过目后才接线，第一次真跑只翻 1 页）
# ⚠️ 现状（v1.9.1，本文件）：**只有按钮层接好了** —— 出计划/执行两个任务书都还在，
#   但 `_EXEC_WIRED=False`（闸门）→ 真跑那一段（翻页+粗筛+入库）**还没实现**，所以：
#   「去猎聘跑一轮」不许触发 collect_plan/collect_run；按钮灰着并如实写明"执行链路未接线"。
#   下一轮做完那三件 → `_EXEC_WIRED=True` 即开。

COLLECT_WORDS = ("猎聘", "采集", "搜候选人", "搜一轮", "跑一轮", "搜人", "捞人", "搜索",
                 "补采", "补跑", "重采", "再采", "去采")
COLLECT_CONFIRM_WORDS = ("按计划", "直接跑", "执行采集", "开始采集", "确认跑", "按这个跑",
                         "执行计划", "按此计划", "按这个计划")
# 动作意图词（配合已落盘计划 → 判定"确认执行"，如"按补跑计划执行"）
COLLECT_ACTION_WORDS = ("执行", "继续", "开始", "确认", "按", "补", "重新")


def latest_report(job: dict, prefix: str, suffix: str = ".json") -> Path | None:
    """reports 目录里最新一个 prefix 开头、suffix 结尾的文件（list_artifacts 已按 mtime 降序）。"""
    for a in list_artifacts(job["job_code"]):
        if a.name.startswith(prefix) and a.suffix == suffix:
            return a
    return None


def render_analyze_html(job: dict, analyze_json: Path) -> Path:
    """①分析的过程网页**本地渲染**（0 token；省 token 第二刀，2026-09-15）。

    输入 = 小猎写的 analyze_*.json（**资产**）；输出 = 同目录 analyze_<ts>_过程.html（**壳**，随时可重生）。
    纪律：只用它写的判断结论（评分/风险/建议）与 process 叙述，**本地绝不改判断**；
    process 有硬长度预算（`report_html.ANALYZE_BUDGET`，超了本地截断并标注）。
    """
    import report_html  # 本地渲染器（数据/展示分离）；导入失败由调用处兜住并如实报错
    analyze_json = Path(analyze_json)
    data = json.loads(analyze_json.read_text(encoding="utf-8-sig"))
    d = _job_dir(job)
    created = ""
    meta_p = d / "meta.json"
    if meta_p.exists():
        try:
            created = str(json.loads(meta_p.read_text(encoding="utf-8")).get("created_at") or "")
        except Exception:
            created = ""
    jd_p = d / "jd.txt"
    html = report_html.render_analyze(job_display_name(job), data, {
        "job_code": job["job_code"],
        "json_name": analyze_json.name,
        "created_at": created,
        # ⚠️ 此刻本次结果还没写进 state → step1_analyzed 反映的是"本次跑之前"，正好是首次/重跑的真实口径
        "first_time": not load_state(job["job_code"]).get("step1_analyzed"),
        "jd_bytes": jd_p.stat().st_size if jd_p.exists() else 0,
        "artifacts_count": len(list_artifacts(job["job_code"])),
        "rules_used": RULES.exists(),
    })
    out = analyze_json.with_name(analyze_json.stem + "_过程.html")
    out.write_text(html, encoding="utf-8")
    return out


def latest_collect_plan(job: dict) -> Path | None:
    return latest_report(job, "collect_plan_", ".json")


def latest_post_text(job: dict) -> Path | None:
    """本岗最近一次「发岗助手」生成的 HTML（有它 = 这个功能用过了 → 按钮显示「🔄 重新发」）。

    2026-09-15 老板要求：跟①分析按钮（`a1` → 「🔄 重跑岗位分析」）一样，用过的功能要看得出来，
    "重新发"也要顺手。口径：**展示层从产物推导**（决策 4：记录不可改、展示可重算）
    → 不新增 state 字段、不做迁移；老岗只要有旧产物，刷新后立刻就是"重新发"。
    """
    for a in list_artifacts(job["job_code"]):
        if a.name.startswith("发岗文字_") and a.suffix.lower() == ".html":
            return a
    return None


# ── ②搜索体检（v1.8.9）──────────────────────────────────────────────────────────
# 出处：2026-09-15 老板口径（"让小猎实际操作浏览器、按 JD 跑几轮搜索、每轮命中总人数是多少"）。
# 零件分工（各自不越权）：脑 = 小猎（轮次计划 + 结论小 JSON）；手 = search_rounds.py（开浏览器、读数）；
# 嘴 = report_html.render_search_rounds（本地渲染）。本处只负责**把三者接上**。
# ⚠️ 与②采集的区别：②采集真抓人、落 collected_*.json 喂③评估；体检**只读人数不抓人** → 另设按钮、不顶替②。

def latest_probe_plan(job: dict) -> Path | None:
    return latest_report(job, "search_probe_plan_", ".json")


def latest_probe_trace(job: dict) -> Path | None:
    return latest_report(job, "search_rounds_", ".json")


def latest_probe_concl(job: dict) -> Path | None:
    return latest_report(job, "search_probe_concl_", ".json")


def render_probe_html(job: dict, trace_json: Path, concl_json: Path | None = None) -> Path:
    """搜索体检的过程网页**本地渲染**（0 token）。

    输入 = `search_rounds.py` 落的轨迹 JSON（**资产**）+（可选）小猎写的结论小 JSON；
    输出 = 同目录 `search_rounds_<ts>_过程.html`（**壳**，随时可重生）。
    纪律：只用轨迹里的事实与小猎写的叙述，**本地不改判断**；命中人数/校验结果**一个数字不截**。
    """
    import report_html
    trace_json = Path(trace_json)
    trace = json.loads(trace_json.read_text(encoding="utf-8-sig"))
    if concl_json and Path(concl_json).exists():
        try:
            extra = json.loads(Path(concl_json).read_text(encoding="utf-8-sig"))
            if isinstance(extra, dict):
                for k in ("conclusion", "highlights"):
                    if extra.get(k):
                        trace[k] = extra[k]
        except Exception:
            pass  # 结论读不出来**不影响出报告**（页面上会显示"小猎没有给结论"）
    html = report_html.render_search_rounds(job_display_name(job), trace, {
        "job_code": job["job_code"],
        "json_name": trace_json.name,
        "plan_file": trace.get("plan_file") or "",
    })
    out = trace_json.with_name(trace_json.stem + "_过程.html")
    out.write_text(html, encoding="utf-8")
    return out


def build_step2_probe_task(job: dict) -> str:
    """②搜索体检的任务书：小猎自己定 2~5 轮 → 用 pwsh 跑 search_rounds.py → 写结论小 JSON。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    analyze = latest_report(job, "analyze_", ".json")
    analyze_hint = analyze.as_posix() if analyze else f"{reports_dir}（暂无 analyze_*.json——还没做①岗前分析）"
    py = sys.executable.replace("\\", "/")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan_file = f"{reports_dir}/search_probe_plan_{ts}.json"
    trace_file = f"{reports_dir}/search_rounds_{ts}.json"
    concl_file = f"{reports_dir}/search_probe_concl_{ts}.json"
    spec_brief = local_checks.recipe_options_brief() if local_checks is not None else ""
    return f"""老板要你执行【搜索体检】：**你自己定几轮搜索、亲手跑，然后给老板一份"每轮命中多少人"的报告**。
这一步不是去捞人，是**体检你自己**：会不会按 JD 正确设关键字/条件、会不会操作浏览器、看不看得懂池子厚薄。
⚠️ 本步**只读人数、不抓人**：不许 extract 候选人、不许开简历详情页（脚本已按这个规矩写好了，**别绕过它自己去点页面**）。

1. 读岗位 JD：{jd}
2. 读最新岗前分析报告：{analyze_hint}
   —— 里面 search_keywords 是 4 组关键字（精确/职能/竞品/技能），挑着用。
3. 自己定 **2~5 轮**搜索计划，**每轮只改一个变量**（否则报告里看不出是谁在砍人）：
   - 第 1 轮：JD 硬门槛那一套（城市 + 1 个最可能命中的关键字）
   - 之后每轮只改一样东西：换职能叫法 / 加或撤一个条件 / 试竞品公司名 / 试技能词
   - ⚠️ **一轮只放 1 个关键字**（多关键字就多写几轮）；关键字里**空格 = 全部命中（AND）**，最多 3 个词，别叠同义词
   - ⚠️ 条件值**只能从下面清单里选，不许自己编**（这是配方表实测过的事实）：
{spec_brief}
4. 把计划写成 JSON：{plan_file}
   格式：{{"job_code": "{job['job_code']}", "rounds": [
     {{"n": 1, "keyword": "关键字", "conds": ["city_current=南京", "education=本科"], "reason": "为什么这么设（≤80 字）"}},
     {{"n": 2, "keyword": "另一个关键字", "conds": ["..."], "changed": "这轮改了什么", "reason": "..."}}
   ]}}
5. 用 **pwsh 工具**（不是 bash；本机 pwsh 实为 Windows PowerShell 5.1，要串联就分次调用）在 bestagent 目录下**真跑**：
   {py} search_rounds.py --plan "{plan_file}" --out "{trace_file}"
   —— 脚本逐轮：导航 → 清空条件 → 按配方表设条件（**强制校验**：条件没生效就硬失败）→ 搜索 → **只读**页面上的「共N位人选」，
   并把每轮、每步的读数打印出来。轮间它自己限速 8~20 秒——**你别重试、别绕过脚本去点页面、别自己加轮数**。
6. 跑完**先看 stdout 总结**，再用文件工具读轨迹：{trace_file}
   ⚠️ **命中总数一律以脚本读到的为准**；某轮读不到就写"读不到"，**不许估、不许拿上一轮的数字顶替**。
   若脚本报「条件没生效（verify=False）」，就如实说这轮白跑了，并把它给的原话贴出来。
7. 再写一个**结论小 JSON**（这是你要交的判断，脚本不替你想）：{concl_file}
   格式：{{"conclusion": "≤300 字：哪套条件最厚 / 哪个条件砍人最狠 / 下一步建议怎么搜", "highlights": ["≤5 条要点，每条≤60 字"]}}
8. 用「老板，搜索体检跑完了」口吻回复 ≤8 句：几轮、每轮关键字与命中人数、哪个条件最狠、下一步建议。
   过程网页由**本地渲染**（0 token）——你**不许手写 HTML**。
{CAPABILITIES}"""


def looks_like_collect_cmd(msg: str) -> bool:
    """消息像不像「②采集发令」（**只看发令词，不掺执行链路是否接线**）。

    ⚠️ 为什么单独抽一个：`detect_collect_intent` 在未接线时**一律返回 ""**（闸门），
    所以用它当"老板是不是在喊采集"的判据会**自己把自己短路**（2026-09-16 实测踩到：
    「去猎聘跑一轮」照样落进了自由对话、还回了句假执行）→ 面板想在本地拦这句话，
    必须用**不含闸门**的判据：这里只问"他是不是在喊②"，接不接线由调用方另判。
    """
    m = (msg or "").strip()
    if not m:
        return False
    # 讨论/提问不算发令（与 detect_collect_intent 同一口径）：否则"采集这岗怎么做？"会被当成喊跑
    if ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
            or m.endswith("？") or m.endswith("?") or m.endswith("吗") or m.endswith("么")):
        return False
    return any(w in m for w in COLLECT_WORDS) or any(w in m for w in COLLECT_CONFIRM_WORDS)


def detect_collect_intent(msg: str, job: dict) -> str:
    """识别②采集发令。返回 "plan"（发令，先出计划）/ "run"（老板确认计划，执行）/ ""（普通对话）。

    保守规则：讨论/提问（含“怎么/为什么/？”）不触发；
    - run：盘上已有 collect_plan_*.json，且消息命中 ① 明确确认词（按计划/直接跑/…）
      或 ② 采集词（采集/补采/补跑…）+ 动作词（跑/执行/按/补…）——覆盖"按补跑计划执行"
      这类自然说法（2026-09-06 实测卡点：只说"按补跑计划执行"未命中旧词表 → 走普通聊天、
      没挂 pwsh 工具 → 小猎无法真跑）；
    - plan：有采集词但还没计划（或无法判定为执行）→ 先出计划请老板确认。
    """
    m = msg.strip()
    # ⚠️ 本函数**刻意不含接线闸门**（v1.9.1 修正）：它只回答"他是不是在喊②"。
    #    接不接线、要不要拦，由调用方（render_main 里的 `_EXEC_WIRED` 判断）决定。
    #    第一版把闸门塞进来 → 未接线时"按计划跑"永远返回 ""，面板自己把确认这条路砍断了。
    is_question = ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
                   or m.endswith("？") or m.endswith("?") or m.endswith("吗"))
    has_plan = latest_collect_plan(job) is not None
    has_collect_word = any(w in m for w in COLLECT_WORDS)
    has_confirm_word = any(w in m for w in COLLECT_CONFIRM_WORDS)
    has_action_word = any(w in m for w in COLLECT_ACTION_WORDS)
    if is_question:
        return ""
    if has_plan and (has_confirm_word or (has_collect_word and has_action_word)):
        return "run"
    if has_collect_word:
        return "plan"
    return ""


def build_step2_plan_task(job: dict) -> str:
    """② 正式采集·第一步（v1.9.1 接线；原「探索采集」）：读 JD + analyze → 拆关键字/条件 → 写计划文件 → 请老板确认（不真跑）。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    analyze = latest_report(job, "analyze_", ".json")
    analyze_hint = analyze.as_posix() if analyze else f"{reports_dir}（暂无 analyze_*.json——还没做①岗前分析）"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan_file = f"{reports_dir}/collect_plan_{ts}.json"
    method = (PROMPTS / "analyze_job.txt").as_posix()
    # v1.8.8：把**配方表的合法值一次给全**（单源 = local_checks.recipe_options_brief → page_recipes.json）。
    # 治的是实测病根：此前只给 JD+①分析+方法论、**没给可选值** → 它只能猜（把 JD 的"5-8年"写成
    # years=5-8年，而猎聘没这个档）→ "它年限迷糊"的真因是**我们没给事实**（§2.4 纪律②）。
    spec_brief = local_checks.recipe_options_brief() if local_checks is not None else ""
    return f"""老板要你执行【步骤② 正式采集·第一步：出计划】。请全程用文件工具完成，**这一步不真跑采集（只出计划给老板确认）**：
⚠️ v1.10.0 现状：**执行链路已全自动接通**（**自己设条件+搜索** → 本地粗筛打分 → 够格就开详情读全文 →
   写本岗库 job.db → **自动翻页** → 连续一批人不值得开就**换下一条关键字** → 本地渲染采集报告）。
   ✅ **不需要老板人工搜关键字、也不需要人工翻页**（每条关键字开跑前脚本自己搜；`click_paging` 已真页面实测）。
   —— 所以你出计划时只需把「关键字 / 条件 / 判据卡」想清楚，**不要**写"请老板先搜好""跑完一页等老板点下一页"这类前提。
   —— 🔴 **不设人为额度**（2026-09-16 死命令）：计划里**不要**写"先跑几条试试""省着点开详情"这类话。
1. 读岗位 JD：{jd}
2. 读最新岗前分析报告：{analyze_hint}
   —— 从报告的 search_keywords 里挑 2~4 个最可能命中目标候选人的关键字（参考其精确/职能/竞品/技能分组；
   若报告没有关键字，按方法论 {method} 的思路从 JD 拆）。
3. 按 JD 硬性条件给出猎聘筛选条件建议（配方组 group_id=value，可空）——
   ⚠️ **值只能从下面这份清单里选，不许自己编**（配方表实测过的事实）。
{spec_brief}
4. 把计划写成 JSON 文件：{plan_file}
   格式：{{"keywords": [关键字...], "conds": ["group_id=value"...], "reasons": "为何这样选（2~3 句）",
          "note": "口径提醒（如年限矛盾先核实）", "created_at": "...",
          "judge": {{"hard": ["city_current=南京"], "industry": ["叉车","AGV","穿梭车","提升机"],
                    "companies": ["杭叉","合力","极智嘉","新松"], "skills": ["非标","传动","丝杆","减速器","solidworks"],
                    "role": ["机械设计","结构设计","机械工程师"], "not_role": ["电气","电控","plc"],
                    "prefer": "industry", "notes": "为什么这么定（≤120字）"}}}}
   ⚠️ **`judge` 这一节是「判据卡」，本轮必须给**（采集脚本按它打分排序，**不再由代码写死某个岗的词**）：
      · `industry`：**行业对口词**（JD 里那个"必须对口"的行业，如输送线/叉车AGV/晶圆封测）；
      · `companies`：**同行公司名**（你从①分析的"竞品对标"里挑）；
      · `skills`：JD 明写的**硬技能/软件**（如 EPLAN / Solidworks / 受力分析）；
      · `role`：**本行职能词**（这个岗的人，职位/期望里一般会出现的词）；
      · `not_role`：**不是本行的职能词**（会被降噪，不会丢人——丢人是③的事）；
      · `prefer`：industry（行业优先）/ skill（技能优先）；
      · `hard`：硬条件（**只放 JD 写"必须"的**；口径打架的先不写，留到③逐人把关）。
      🔴 **硬条件里同一个组只能给一个值**：猎聘把并列值当"**同时满足**"——
        写 `["city_current=南京","city_current=苏州"]` = 要求"既在南京又在苏州" → **0 命中、整轮空跑**。
        双城/双学历这种情况要**分轮**（南京一轮、苏州一轮），不要并排写在同一轮里。
      ⚠️ 判据卡的权重是**写死的**（行业/技能/本行职能的加分），你**只能给词、不能改权重**；
        词表必须来自 JD 与①分析，**不许自己编**；给不出就留空数组，宁可少给也不要瞎给。
5. 用「老板，采集计划好了」口吻回复 ≤8 句：列出关键字与条件、为什么这样选、预估代价
   （每个关键字=1 次猎聘搜索，搜索次数不是瓶颈；⚠️ 猎聘搜索框是“包含全部关键词”——空格分隔的词**全部要命中**，
   关键字词内别叠同义词/多词，否则极易 0 命中；同义词宁可拆成多个关键字分路跑）、
   给一句**池子预期判断**（这个池子估摸着 厚/正常/薄——薄的话说明这单捞人费劲，老板心里有数再拍板）、
   以及**请老板拍板**（老板回复“按计划跑/直接跑”才执行；他想调关键字/条件，就说“重新出采集计划”按他的意思改）。
{CAPABILITIES}"""


def build_step2_run_task(job: dict, plan_file: Path | None = None) -> str:
    """② 正式采集·**真跑**（v1.10.0 全自动闭环；v1.11.0 起「无计划也能跑」）。

    v1.11.0（2026-09-16 老板拍板「取消搜索体检/采集计划这两个子步骤」）：
      · 「② 正式采集 / 🔁 再次采集」按钮 = **真跑这个动作本身**，不再要求老板先点一次「出计划」；
      · `plan_file=None`（盘上没计划）→ 小猎**一个回合内**自己定 关键字/条件/判据卡 →
        **仍写一份 `collect_plan_<ts>.json` 留档**（可重放）→ **立刻跑**，中间**不停**、不再请老板确认；
      · 首行仍用「老板已确认【步骤②」前缀 → `kind_of_task` 照旧判 `collect_run`（不必新增映射）。

    ⚠️ 口径（v1.10.0 老板重定方向后）：
      · **自己搜 + 换关键字**：每条关键字开跑前脚本走桥的 `execute_spec` 自己设条件并点「搜 索」
        （体检线 2026-09-15 已在真猎聘跑通）→ **"老板先人工搜一次"永久消失**，"换关键字"由此成立。
      · **开工前体检**（v1.11.0）：脚本开搜之前跑 `check_collect_spec` + `check_judge_card`，
        **有问题拒绝开跑**（缺判据卡 = 硬拒绝）——因为小猎是一回合内写完就跑，面板来不及拦。
      · **翻页自动**：`click_paging` 按分页结构点（按文字会点到年龄里的数字）。
      · **判断全在本地**（collect_rules.py）：谁值得开详情（**够格就开**）、什么时候该停、
        **连续一批人不值得开 → 换关键字**；**不调 LLM**。
      · **不设人为额度**（🔴 2026-09-16 死命令）：`--max-pages/--details/--total-details` 默认全 0=不限。
      · **详情全文只从 `page_text` 取**（不截断）。
    """
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    analyze = latest_report(job, "analyze_", ".json")
    analyze_hint = analyze.as_posix() if analyze else f"{reports_dir}（暂无 analyze_*.json——还没做①岗前分析）"
    method = (PROMPTS / "analyze_job.txt").as_posix()
    py = sys.executable.replace("\\", "/")  # 面板自身解释器（lzstudy），换机器自动跟随
    if plan_file is None:
        # ── 无计划分支（v1.11.0）：一回合内自定计划 → 留档 → 直接跑，中间不停 ──────────────
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        plan_abs = f"{reports_dir}/collect_plan_{ts}.json"
        spec_brief = local_checks.recipe_options_brief() if local_checks is not None else ""
        intro = ("老板已确认【步骤② 正式采集】。**盘上还没有采集计划 → 这一个回合里你自己把计划定下来，"
                 "然后直接开跑；中间不许停下来问老板、不许只出计划不跑**：\n")
        first_steps = f"""1. 先读岗位 JD：{jd}
   读最新岗前分析：{analyze_hint}
   —— 从报告的 search_keywords 里挑 2~4 个最可能命中目标候选人的关键字（若报告没有关键字，
   按方法论 {method} 的思路从 JD 拆）。
2. **自己**把三样定下来（口径与「出采集计划」完全一致，**不许问老板**）：
   · **关键字**：猎聘搜索框是"包含全部关键词"——空格分隔的词**全部要命中**，词内别叠同义词/多词，
     否则极易 0 命中；同义词宁可拆成多条关键字分路跑。
   · **条件**：**只放硬门槛**（JD 写"必须"的）；🔴 **同一个组只能给一个值**——并列值会被当成
     "**同时满足**"（如城市南京+苏州）→ 0 命中、整轮空跑，双城要**分轮**。
     值**只能从下面这份配方表清单里选，不许自己编**：
{spec_brief}
   · **判据卡 `judge`**（🔴 **必须给**，缺了执行器会**拒绝开跑**）：industry / companies / skills /
     role / not_role / prefer。词只能来自 JD 与①分析；⚠️ 权重是**写死的**，你**只能给词、不能改权重**。
3. 把计划**写下来留档**（这是可重放的那一份，别只留在脑子里）：{plan_abs}
   格式：{{"keywords": [关键字...], "conds": ["group_id=value"...], "reasons": "为何这样选（2~3 句）",
          "note": "口径提醒", "created_at": "...",
          "judge": {{"industry": [...], "companies": [...], "skills": [...], "role": [...],
                    "not_role": [...], "prefer": "industry", "notes": "..."}}}}
4. **立刻**用 **pwsh 工具**（不是 bash）在 bestagent 目录运行（**中间不停、不要老板再确认**）：
   {py} collect_exec.py --job-code {job['job_code']} --plan "{plan_abs}" --all-keywords
"""
    else:
        plan_abs = plan_file.as_posix()
        intro = "老板已确认【步骤② 正式采集】计划。请执行真实采集（**全自动：自己搜、自己换关键字、自己翻页**）：\n"
        first_steps = f"""1. 先用文件工具读计划文件：{plan_abs} —— 取 keywords 与 conds；读不到就如实说并请老板重新发令。
2. 用 **pwsh 工具**（不是 bash）在 bestagent 目录运行采集执行器：
   {py} collect_exec.py --job-code {job['job_code']} --plan "{plan_abs}" --all-keywords
"""
    return f"""{intro}{first_steps}   —— **`--plan` + `--all-keywords`**：脚本从计划里取 **judge 判据卡**（按岗打分）、**conds 硬条件**，
      并把计划里的关键字**一条条全跑完**：**每条关键字开跑前它自己设条件+点搜索**（走桥的
      `execute_spec`，体检线 2026-09-15 已在真猎聘跑通），然后逐页采到"该停"为止。
   —— ✅ **v1.10.0：不需要老板先去猎聘搜一次了。** 脚本自己搜（`navigate` → `清空筛选条件`
      → 设关键字/条件 → 点「搜 索」）。**"换关键字"由此成立**：每条关键字读到的页面都属于它自己。
   —— 🔴 **自己搜失败（verify=False 等）→ 脚本会"跳过这一条不采"**（绝不把别人的页当成自己的页采）。
      这种情况**如实报给老板**（哪条关键字、什么原因），不要当成"这个池子薄"。
   —— 🔴 **开工前体检（v1.11.0）**：脚本在**开搜之前**先跑本地体检（关键字形态 / 条件取值在不在配方表 /
      判据卡有没有坑）。**没过它会直接拒绝开跑并以非 0 退出**（一个字都不采）。
      计划是**你自己写的**，所以这种情况**是你写错了**：按它打印的原因**改计划**（尤其别缺 `judge`）
      **再跑一次**；仍不过就**如实报老板**，别绕过、别把兜底判据当正常结果。
   —— 计划里没有 `judge` 一节 → **现在会被拒绝开跑**（不再退回兜底判据）；如实告诉老板"计划缺判据卡"。
   —— **关键字/条件必须来自计划文件，一个字都不许改**。
   —— 🔴 **不设人为额度（2026-09-16 死命令）**：`--max-pages` / `--details` / `--total-details`
      **默认全是 0 = 不限**，让脚本自己按"值不值得"停。**不要**为了"省额度"手加任何上限。
   ⚠️ **你自己不许去点猎聘页面、不许自己设条件/清条件**（页面动作只走桥；模型不碰浏览器）。
   翻页由脚本走桥的 `click_paging` 完成（**按分页结构点，不按文字**——按文字会点到年龄里的数字）。
   若脚本报 `未知动作: click_paging` / `execute_spec` 相关错误 → **如实告诉老板**，别自己硬点页面。
3. 这个执行器会：**先报池子**（这条关键字+这串条件「共N位人选」，逐条件"砍掉多少人"也记进轨迹）
   → 逐页读卡片 → 本地规则打分 → **够格就开详情**（`page_text` 读**全文**，开完**自动关掉详情页并切回列表**）
   → 写进本岗库 `data/chat/{job['job_code']}/job.db` → 需要就翻页 → **连续一批人不值得开就换下一条关键字**
   → 落轨迹 + 本地渲染采集报告（0 token）。
   —— 开 1 个详情 = 1 次"查看简历"（平台计数，**这是真代价**）；但**不设配额**，
      由"够不够格"决定开谁；**本岗库里已有全文的人不会重复开**（重跑/换词都不浪费）。
   —— 停止由脚本按内容判：翻不动 / 连续 2 页行业命中为 0 / 连续一批人不值得开 / 整页无人可开。
4. 跑完读两份产物（路径在 stdout 最后两行）：
   `{reports_dir}/collect_*.json`（轨迹）与同名 `_过程.html`（本地渲染的报告）。
5. 如实汇报（≤8 句）：**每条关键字各搜到多少人（「共N位人选」）**、卡片几张、行业命中几个、
   开了几个详情（各读到多少字）、有没有"读不到/搜失败/开详情失败"的（**照实说，不许粉饰**）、
   本地判分最像的 3 个人、以及在哪个关键字上停的、为什么停。报错就贴原文。**不要自动重跑**。
{CAPABILITIES}"""


# ── 💬 打招呼报告（v1.12.0 **取代原「③ 池子评估」**）──────────────────────────
# 老板 2026-09-17 拍板：工作步骤 = 岗位分析 → 发岗助手 → 正式采集 → **打招呼报告** → 打招呼 → 查看回复。
# 关键定位：**这份报告是小猎自己的工作依据**（不只是给老板看的报告）：
#   ① 先看**态势**（池子多大 / 够格几个 / 打过几个 / 还剩几个 / 现在能不能打）—— 事实，不许猜；
#   ② **自己定口径**（够格少就放宽、打不完就收紧）→ 写一份 plan JSON 留痕（可重放）；
#   ③ 跑细筛（逐人调 LLM；评过的人命中缓存 0 花费）→ 出报告（本地渲染 0 token）→ 按时间窗排队打。
# 🔴 **规则不进代码**：阈值 / 名额 / 宽松度 / 时间窗**全在它写的 plan JSON 里**（老板要的"弹性"）。
GREET_REPORT_WORDS = ("打招呼报告", "打招呼的报告", "打招呼清单", "该打谁", "出一份报告", "生成一个报告",
                      "生成一份报告", "生成绩效报告")


def detect_greet_report_intent(msg: str, job: dict) -> bool:
    """识别「出打招呼报告」发令（老板原话：「我们先生成一个打招呼的报告吧，这次弄的稍微宽松吧」）。"""
    m = msg.strip()
    if not any(w in m for w in GREET_REPORT_WORDS):
        return False
    if ("怎么" in m or "为什么" in m or "是啥" in m or "是什么" in m
            or m.endswith("？") or m.endswith("?") or m.endswith("吗")):
        return False
    if any(w in m for w in COLLECT_CONFIRM_WORDS):
        return False
    return True


def build_greeting_report_task(job: dict) -> str:
    """💬 打招呼报告：**查态势 → 自己定口径（写 plan 留痕）→ 细筛 → 出报告 → 汇报**。"""
    jc = job["job_code"]
    reports_dir = (_job_dir(job) / "reports").as_posix()
    py = sys.executable.replace("\\", "/")   # 面板自身解释器（lzstudy），换机器自动跟随
    plan_f = latest_report(job, "greeting_plan_", ".json")
    plan_hint = (f"（盘上最新口径计划：{plan_f.as_posix()}——**可以参考，但沿不沿用由你定**）"
                 if plan_f else "（盘上还没有口径计划，这一份要你从头写）")
    plan_out = f"{reports_dir}/greeting_plan_{datetime.now():%Y%m%d-%H%M%S}.json"
    return f"""老板要你执行【打招呼报告】。**这份报告是你自己干活的依据**（不只是给老板看的），所以先看事实、再自己定口径：
1. **先看态势**（事实，**不许猜**）——用 **pwsh 工具**（不是 bash）在 bestagent 目录跑：
   {py} status_run.py --job-code {jc}
   —— 它会告诉你：池子多少人（多少有全文 / 只有卡片）、够格几个、已评几个、打过几个招呼、
      还剩几个够格没打、今天新采到几个、现在能不能打（时间窗）、最新报告新不新。
2. **自己定口径**（**这一步归你，不要问老板**）{plan_hint}：
   · 够格的人太少 → 放宽（strictness 写"宽松"、threshold 下调）；人太多打不完 → 收紧或调小 max_list；
   · 把口径写成 JSON **留档**（这是你的决策留痕：可重放、可追溯）：{plan_out}
   字段：{{"job_code": "{jc}", "created_at": "...", "boss_words": "老板原话（有就抄，没有留空）",
          "strictness": "严格/标准/宽松", "threshold": 70, "max_list": 15,
          "criteria": "一句话本次口径（会**动态拼进提示词**发给模型）",
          "follow_up_days": 3,
          "time_window": {{"days": [1,2,3,4,5], "slots": [["09:30","12:00"],["14:00","18:30"]]}},
          "notes": "你为什么这么定（≤2 句）"}}
   ⚠️ **规则不许写进代码**（你也不需要改任何 .py）：上面这些**全是数据**，改口径 = 改这份 JSON。
      老板说"这次宽松点"时，你要把它翻成具体值（如 strictness=宽松、threshold 70→60），**不是照抄一句话**。
3. **跑细筛**（逐人调 LLM 打分；对**过线**的人预生成话术。评过且口径没变的人**命中缓存、0 花费**）：
   {py} filter_run.py --job-code {jc} --plan "{plan_out}"
   —— 想先看账不花钱就加 `--dry-run`；想小样试水就加 `--limit 5`。
4. **出打招呼报告**（本地渲染，**0 token**）：
   {py} greeting_report.py --job-code {jc} --plan "{plan_out}"
   —— 产出 `打招呼报告_<ts>.json`（**你照它执行**）+ 同名 `_过程.html`（老板过目）。报告只列**够分的**；
      分数不够的不体现在报告上。
5. **汇报**（≤8 句，**别念系统日志**，像同事说话）：池子情况一句、**你定的口径与理由**、
   这次进了几个人、最该先打的 2-3 个（点名 + 一句理由）、有没有"仅卡片评估"的（如实说）、
   现在能不能打 / 要到哪个时段。
⚠️ 硬纪律：
   · 报告里的话术**一个字都不许改**（那是按口径预生成的）；数字与链接**不许编**；
   · **不许自己去点猎聘页面**；打招呼动作是**人工闸门**（还没接入）：你出报告 + 给话术 + 给链接，
     老板照着打，打完在台账里记一笔；
   · 吃不准就问老板（报告缺东西 / 口径拿不准 / 时间不对——都直说，**别硬干**）。
{CAPABILITIES}"""


def build_post_text_task(job: dict) -> str:
    """生成猎聘发岗文字：岗位名/亮点/职责/要求/薪酬地点 → 存 reports/发岗文字_<ts>.md 并在回复里全文给出。"""
    jd = (_job_dir(job) / "jd.txt").as_posix()
    reports_dir = (_job_dir(job) / "reports").as_posix()
    analyze = latest_report(job, "analyze_", ".json")
    analyze_hint = analyze.as_posix() if analyze else "（暂无，直接从 JD 提炼）"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = f"{reports_dir}/发岗文字_{ts}.md"
    return f"""老板要你生成【发岗文字】（用于把岗位发布到猎聘，老板会复制粘贴去发布，发布动作由老板人工完成）：
1. 读岗位 JD：{jd}
2. 读最新岗前分析：{analyze_hint}（它的 jd_extracted/评分理由/风险可用来提炼卖点与口径提醒）
3. 写一份可直接发布的猎聘职位文案，包含：
   - 职位名称（贴合 JD 叫法 + 搜索友好）
   - 一句话吸引点（卖点先行）
   - 岗位职责（4~6 条，来自 JD description）
   - 任职要求（硬性条件单列 + 加分项单列；若 JD 里有口径矛盾，如年限"博士2年 vs 10年+"，
     文案里按更宽松口径写并备注"面议/详询"，别写死自相矛盾）
   - 薪酬/地点/福利（按 JD；写"面议"的注明）
   - 结尾引导语（欢迎自荐/推荐）
4. 保存到：{out}
5. 回复里把整份文案**全文贴出**（老板直接复制），并给 ≤3 句提示（如"注意先核实年限口径再发布"）。
{CAPABILITIES}"""


# ═══════════════════════ 执行通道 ═══════════════════════

def _env_from_file(env_path: Path) -> dict:
    env: dict[str, str] = {}
    if env_path and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL") and v.strip():
                env[k] = v.strip().strip('"').strip("'")
    return env


def run_assistant(job: dict, prompt: str, env_path: Path, stub: bool = False,
                  max_tokens: int = 8192, action: str = "",
                  tool_profile: str | None = None,
                  ) -> tuple[str, list[Path], str]:
    """跑一次真 agent（阻塞式）。统一走 sdk profile（文件工具 + pwsh 工具都有）。

    每次运行用**新的 session id**（`<岗位会话>-<动作>-<时间戳>`）：新版 SDK 对跨进程复用同一 id 会
    直接报 `session "X" already exists`（§8.8 坑 B，rc1 复测一致）→ 与「不赌会话记忆」铁律一致，
    每轮靠状态卡 + 产物续上下文，零损失。
    `tool_profile`：工具面分档（framework_config.TOOL_PROFILES）——按动作给"手"，
    用不到的工具插件整行不挂载（省每轮固定租金，见 2026-09-14 实测：25 个 ≈ 6,481 token/轮）。
    返回 (回复, 新产物, 本次运行的 session id)。
    """
    LAST_RUN.clear()
    LAST_RUN.update({"action": action, "stub": bool(stub), "finish_reason": ""})
    if stub:
        time.sleep(0.2)
        return (f"（假执行·界面自测）收到指令：{prompt[:60]}…\n"
                "正式使用时请把执行模式切回「真执行」并配置 .env。"), [], "stub"
    if make_harness is None:
        raise RuntimeError("framework_config 导入失败（make_harness 不可用）：请查 bestagent/framework_config.py")

    env = _env_from_file(env_path)
    if "DEEPSEEK_API_KEY" not in env:
        raise RuntimeError("没有找到 DEEPSEEK_API_KEY：请检查侧栏「运行设置」里的 .env 路径")

    reports_dir = _job_dir(job) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in reports_dir.iterdir()}

    base_sid = job.get("session_id") or f"m3chat-{job.get('job_code', 'job')}"
    run_session_id = f"{base_sid}-{action or 'run'}-{int(time.time())}"

    # v1.8.7：**开始就落盘**（崩在这里之后，重启面板能看出"上次有个 run 没结束"）
    log_run(job["job_code"], action, run_session_id, "running", files_before=len(before))
    try:
        with make_harness(env, max_tokens=max_tokens, persona=PERSONA,
                          tool_profile=tool_profile) as harness:
            result = harness.run(prompt, session_id=run_session_id)
    except Exception as exc:  # 网络断/进程被杀/运行时崩 → 如实记 error 再往上抛（面板照旧报错）
        log_run(job["job_code"], action, run_session_id, "error", note=repr(exc)[:200])
        raise

    reply = (getattr(result, "final_response", "") or "").strip()
    after = {p.name for p in reports_dir.iterdir()}
    new_files = [reports_dir / n for n in sorted(after - before)]
    new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    _fr = getattr(result, "finish_reason", "") or ""
    LAST_RUN.update({"session": run_session_id, "finish_reason": _fr,
                     "new_files": [p.name for p in new_files]})
    log_run(job["job_code"], action, run_session_id, "done",
            finish_reason=_fr, new_files=[p.name for p in new_files])
    return reply, new_files, run_session_id


# ═══════════════════════ UI ═══════════════════════

def render_sidebar() -> dict:
    with st.sidebar:
        st.markdown("## 🎯 岗位会话")
        jobs = list_jobs()
        options = [j["job_code"] for j in jobs]
        # 显示名 = 人看得懂的岗位名（本地推导，0 花费）；岗位号放末尾保留（你我对话时用它精确指岗）
        labels = {j["job_code"]: f"{job_display_name(j)}　{j['job_code']}" for j in jobs}
        if not options:
            st.caption("还没有岗位会话，先在下面新建一个。")
        else:
            # 重启面板后回到"上次在看的岗"（原来默认选列表第一个=最新建的岗 → 实测点错过岗）
            _last = load_last_job()
            _idx = options.index(_last) if _last in options else 0
            pick = st.selectbox("当前岗位（=一条对话线程）", options, index=_idx,
                                format_func=lambda c: labels.get(c, str(c)), key="job_pick_chat")
            save_last_job(pick)
        with st.expander("➕ 新建岗位会话", expanded=not bool(options)):
            title = st.text_input("岗位标题（可空）", key="nj_title",
                                  placeholder="如：中国移动 NLP 应届博士岗")
            jd_up = st.file_uploader("上传 JD（.txt）", type=["txt"], key="nj_up")
            jd_paste = st.text_area("或直接粘贴 JD 原文（推荐贴完整页面快照）", key="nj_paste", height=160)
            if st.button("创建并进入该岗", key="nj_btn", use_container_width=True):
                if jd_up is not None:
                    new_job = create_job(title, jd_bytes=jd_up.getvalue())
                elif jd_paste.strip():
                    new_job = create_job(title, jd_text=jd_paste)
                else:
                    new_job = create_job(title)
                st.session_state["job_pick_chat"] = new_job["job_code"]
                st.success(f"已创建：{new_job['job_code']}")
                st.rerun()

        st.divider()
        with st.expander("⚙️ 运行设置"):
            stub = st.checkbox("假执行（界面自测，不调 API）",
                               value=os.environ.get("M3CHAT_STUB") == "1", key="stub_mode")
            env_path = st.text_input(".env 路径", value=str(DEFAULT_ENV), key="env_path")
            st.caption("真执行阻塞式：发令后耐心等待（页面右上角可 Stop）。")

        st.divider()
        with st.expander("📒 纠错成长账（原始账）"):
            st.caption(f"累计 {len(list_records())} 条 → data/growth/records.jsonl；"
                       "消化成规则写 data/prompts/rules.md，下次干活自动生效。")
            # 步骤下拉：默认按当前岗状态给建议（①分析已完成→默认①；否则自由讨论）
            cur_job_code = st.session_state.get("job_pick_chat") or (jobs[0]["job_code"] if jobs else None)
            default_no = 1
            if cur_job_code:
                stt = load_state(cur_job_code)
                default_no = 1 if stt.get("step1_analyzed") else 0
            rec_step = st.selectbox("这笔纠错属于哪一步？",
                                    [s["no"] for s in STEPS],
                                    format_func=lambda n: STEP_NAME[n],
                                    index=next(i for i, s in enumerate(STEPS) if s["no"] == default_no),
                                    key="rec_step")
            note = st.text_area("记一笔：助理哪里不对 / 应该怎样", key="rec_note", height=90)
            tags = st.text_input("主题标签（逗号分隔）", key="rec_tags",
                                 placeholder="如：评分口径,关键字选词,诚实边界")
            if st.button("✍️ 记录纠错（成长数据）", key="rec_btn", use_container_width=True):
                if not note.strip():
                    st.warning("批注为空，未记录。")
                else:
                    job = next((j for j in jobs if j["job_code"] == cur_job_code), None)
                    if job is None:
                        st.warning("请先选择岗位会话。")
                    else:
                        append_record(job, rec_step, note, tags)
                        st.success("已记入成长账（待消化）。")
                        st.rerun()
            recents = list_records()[-5:][::-1]
            if recents:
                st.markdown("**最近记录**")
                for r in recents:
                    st.caption(f"· [{r['step_name']}] {r['note'][:36]}{'…' if len(r['note']) > 36 else ''} ({r['ts'][5:16]})")

        st.divider()
        with st.expander("📖 怎么用（1 分钟）"):
            st.markdown(
                "- **建岗**：新建岗位时贴 JD（完整页面快照最稳）→ 选它进入对话\n"
                "- **判断在对话里**：🚀 岗前分析完，小猎给「接 / 先沟通 / 别做」态度 + 理由，"
                "你回复 做吧/不做/先核实 拍板，或直接追问「为什么」反驳；拍板后才解锁②采集/发岗\n"
                "- **按钮=执行显示层**：也可点按钮快捷发令（系统按岗位状态 + 你的拍板自动亮/灰）\n"
                "- **看过程**：每步执行自动落 HTML 过程文档，对话里点产物「打开 ↗」即看，不用盯屏\n"
                "- **教它规则（成长）**：对话里教完说「把这条记到成长库」——它会按格式追加进 rules.md"
                "（只追加不改删，写完展示新增内容，你随时可审）；要改设计/手册则找实施对话\n"
                "- **纠错**：侧栏记一笔 → 成长账；消化成规则后可让助理写进 rules.md\n"
                "- **发岗/入库**：第一行「📤 发岗助手」（①分析正后面，0 token 本地渲染 9 格表单，逐格复制去猎聘发布、"
                "发布动作人工）；任意时点「入库当前岗」把该岗产物幂等写入 business.db（台账/统计用）\n"
                "- **能力边界**：①②③已接入（分析/采集/评估），联系候选人=人工闸门（未接入）；自由聊天里也会如实说明")

    return {"jobs": jobs, "stub": stub, "env_path": Path(env_path)}


def render_progress_line(job: dict) -> None:
    """岗位自动进度（只读，不用手动维护）。v1.7.0：①分析完进入「等你拍板」判断点。"""
    stt = load_state(job["job_code"])
    jd_ok = stt.get("jd_provided")
    a1 = stt.get("step1_analyzed")
    c2 = stt.get("step2_collected")
    c3 = stt.get("step3_report")
    dec = stt.get("decision")
    jd_chip = "📥 JD 已收" if jd_ok else "📥 等 JD"
    if not a1:
        a1_chip = "⬜ ① 岗前分析未做"
    elif dec == "pending":
        a1_chip = "⚖️ ① 分析完 · 等你拍板"
    elif dec == "accept":
        a1_chip = "✅ ① 分析完 · 已拍板：做"
    elif dec == "decline":
        a1_chip = "⛔ ① 分析完 · 已拍板：不做"
    elif dec == "clarify":
        a1_chip = "📌 ① 分析完 · 已拍板：先核实"
    else:  # 旧岗无 decision 字段 → 兼容不锁
        a1_chip = "✅ ① 岗前分析完成（旧岗，未走拍板）"
    if c2:
        c2_chip = "✅ ② 已采集"
    elif not _EXEC_WIRED:
        c2_chip = "② 正式采集（🔌 执行链路未接线）"  # v1.9.1：改名 + 如实标未接线（别让它看起来能用）
    elif latest_collect_plan(job):
        c2_chip = "② 正式采集（计划已就绪，可点跑）"
    else:
        c2_chip = "② 正式采集（拍板做后解锁）"
    # v1.12.0：③池子评估取消 → 这一步 = 「💬 打招呼报告」（老板 2026-09-17 拍板的新工作步骤）
    c3_chip = "✅ 💬 打招呼报告已出" if c3 else "💬 打招呼报告（②采完才可点）"
    # v1.11.0：流程条里的「🔎 搜索体检」位**摘掉**（老板拍板取消这两个子步骤）——
    #   体检的两块能力已并进②正式采集（开工前报池子 + 开工前体检），脚本 search_rounds.py 仍留着按需调用。
    # v1.8.4：发布状态位（占位）——它**不是流程步骤**，是分岔（发了→打招呼带岗位卡片），故用 ｜ 隔开
    st.markdown(f"**流程进度**：{jd_chip}　→　{a1_chip}　→　{c2_chip}　→　{c3_chip}"
                f"　｜　{publish_status_text(stt)}")
    hint = []
    if not jd_ok:
        hint.append("先上传/粘贴 JD（新建岗位时），或直接在下方输入框把 JD 原文发来。")
    elif not a1:
        hint.append("点下方「🚀 开始岗位分析」——小猎会真分析并给「接/先沟通/别做」的态度和理由，等你拍板。")
    elif dec == "pending":
        hint.append("小猎的判断在上一条消息里：回复「做吧 / 不做 / 先核实」拍板，或直接追问「为什么」反驳。"
                    "（②正式采集要等你拍板做才解锁）")
    elif dec in ("decline", "clarify"):
        hint.append("②/打招呼报告/发岗已按你的拍板锁定。改主意/核实完了：说「做吧」「不做」，或「重新判断」重跑①。")
    elif dec is None:
        hint.append("旧岗兼容（未走拍板流程）：可继续按按钮走；想重新过一遍判断说「重新判断」。")
    elif not c2:
        hint.append("①已拍板做：②**搜索体检**可以点了（只读人数、不抓人）；②**正式采集**的执行链路还没接上"
                    "（按钮先灰着），接上后才解锁。")
    elif not c3:
        hint.append("②已采集：可点「③ 池子评估」给这批人评分（读方法论逐人打分，纯计算）。")
    else:
        hint.append("③评估已出：看 top 清单可追问/纠错/重跑；联系候选人=人工闸门（未接入）。")
    st.caption("　".join(hint))
    # v1.8.7 断点提示：上次有 run 没正常收尾（网络/进程中断）→ 先别急着重跑，先看盘上有什么
    _unf = last_unfinished_run(job["job_code"])
    if _unf:
        st.warning(f"⚠️ **上次「{_unf.get('action')}」没正常收尾**（{_unf.get('ts')}）——"
                   "可能是网络断了/进程被中断（不是「没做」，是「做到一半」）。\n"
                   "建议：先看对话里最后一条消息 + reports 里的新产物，再决定「重跑」还是接着跑；"
                   f"运行台账：`{RUNS_LOG.as_posix()}`")


def render_action_row(job: dict, cfg: dict | None = None) -> str | None:
    """动作按钮行：由岗位状态自动亮/灰；返回要发送的任务文本（无则 None）。

    v1.7.0 按钮 = 「执行显示层」：判断主通道在对话（小猎给态度+理由 → 老板拍板）。
    ①分析完先等拍板（decision=pending 锁②③/发岗）；accept 才解锁；decline/clarify 锁；
    旧岗无 decision 字段（None）不锁（兼容）。
    v1.6.8：📋 生成发岗文字按钮改为本地驱动 publish_run（agent 产字段 JSON →
    本地渲染 发岗文字_<ts>.html，逐格复制到猎聘），不再走聊天 agent 手写整篇 md。
    """
    stt = load_state(job["job_code"])
    jd_ok = stt.get("jd_provided") and (_job_dir(job) / "jd.txt").exists()
    # v1.8.2：`arts` 原先只服务于「导出 HTML 汇报」的 disabled → 按钮摘掉后这行变死代码，一并清掉
    stub = bool(cfg and cfg.get("stub"))
    env_path = (cfg or {}).get("env_path")
    a1 = stt.get("step1_analyzed")
    dec = stt.get("decision")

    # v1.8.3：第一行 = ①分析 → 📤发岗助手 → ②采集 → ③评估（业务顺序摆位）；v1.8.2 摘了「导出汇报」空出的位给了发岗助手
    c1, c2, c3, c4 = st.columns(4)
    task = None
    if not jd_ok:
        st.info("岗位 JD 还没就位：请先在左侧新建岗位时粘贴/上传 JD。")
        return None
    # v1.7.0：判断点提示——按钮是执行显示层，拍板在对话里
    if a1 and dec == "pending":
        st.info("⚖️ **判断点**：小猎已给态度和理由（见上一条消息）。请回复「做吧 / 不做 / 先核实」拍板，"
                "或先追问「为什么」——②采集/发岗要等你拍板做才解锁。")
    elif a1 and dec == "decline":
        st.info("⛔ 已拍板**不做**这单：②③/发岗已锁定。改主意或重看一遍，回复「重新判断」。")
    elif a1 and dec == "clarify":
        st.info("📌 已拍板**先核实再定**：②③/发岗暂锁。核实完回复「做吧」或「不做」。")
    decision_ok = dec in (None, "accept")  # None=旧岗兼容
    label1 = "🔄 重跑岗位分析（重新给判断）" if a1 else "🚀 开始岗位分析"
    if c1.button(label1, key="act_analyze", use_container_width=True,
                 help="读 JD+方法论+成长规则 → 评分/接单判断/4组关键字/process 叙述 → 只落 JSON；"
                      "过程网页由本地渲染（0 token、有长度预算）→ 对话里给「接/先沟通/别做」态度与理由，等你拍板"):
        task = build_step1_task(job)
    # v1.8.6：用过的功能要看得出来（与①分析的「🔄 重跑岗位分析」同一种口径）
    _pt = latest_post_text(job)
    _pt_label = "🔄 重新发岗助手" if _pt else "📤 发岗助手"
    _pt_help = ("v1.8.3 挪到①分析正后面（原「生成发岗文字」）：读 JD+①+发岗手册 → 发岗字段 JSON → "
                "**本地渲染** 9 格 HTML（0 token），逐格复制到猎聘发岗页；**发布动作仍是人工**")
    if _pt:
        _pt_help += (f"｜✅ 已用过：上次生成 {datetime.fromtimestamp(_pt.stat().st_mtime):%Y-%m-%d %H:%M}"
                     f"（{_pt.name}）——再点就是重新生成一份，旧的那份不会被删")
    if c2.button(_pt_label, key="act_post_text", use_container_width=True,
                 disabled=not (a1 and decision_ok), help=_pt_help):
        if stub:
            st.info("假执行模式：跳过 API（真执行会产发岗字段 JSON + 渲染 发岗文字_*.html）")
        elif not env_path:
            st.warning("未配置 .env 路径（侧栏「运行设置」）。")
        else:
            try:
                import publish_run
                with st.status("小猎整理发岗文字中（读发岗手册+JD → 字段 JSON → 本地渲染）…",
                               expanded=False) as status:
                    jf, hf = publish_run.publish_for_job(job["job_code"], env_path)
                    status.update(label="发岗助手完成", state="complete")
                files = [Path(p) for p in (jf, hf) if p and Path(p).exists()]
                if files:
                    # v1.6.9：产物以「可打开」消息留在对话里（HTML 打开即逐格复制，不再只给说明文字）
                    append_msg(job["job_code"], "assistant",
                               f"📤 发岗助手已生成（{now_str()}）——点下方「打开 ↗」用浏览器打开，"
                               "逐格复制到猎聘发岗页（发布动作人工）。",
                               artifacts=[p.name for p in files])
                    save_state(job["job_code"], last_action="发岗助手")
                    st.success("✅ 发岗助手已生成：见对话里最新一条消息（点「打开 ↗」直接看）。")
                    st.rerun()
                else:
                    st.warning("发岗助手未生成：看上方汇报定位问题（可重跑/纠错）。")
            except Exception as e:
                st.error(f"⚠️ 发岗助手生成失败：{e}")
    # ── 第二行（v1.11.0 按老板 2026-09-16 拍板重排）：📋出采集计划 → ②正式采集/🔁再次采集 → ③池子评估 ──
    # 🔴 老板口径（衔接报告 §4.1 改动任务书，老板已拍「按这个计划来」）：
    #   · 「② 正式采集 / 🔁 再次采集」= **真跑**（不再是"只出计划"）；执行器已接线（`_EXEC_WIRED=True`）；
    #   · 原来挂在 ② 上的"出计划"**另起一个按钮**（测试期辅助工具，但**不许挡在主流程前面**）；
    #   · 「🔎 搜索体检」按钮**取消**——它是测试期工具，两块能力已**并进采集**
    #     （① 开工前先报池子 = on_step 读数 ② 开工前体检 = check_collect_spec/check_judge_card）。
    #     脚本 `search_rounds.py` 仍留着（按需调用，**不占按钮**）。
    c5, c6, c7 = st.columns(3)
    _cp = latest_collect_plan(job)
    _cp_label = "🔄 重新出采集计划" if _cp else "📋 出采集计划"
    _cp_help = ("v1.11.0：**只出计划、不真跑**（测试期辅助工具）——小猎读 JD+①分析 → 定 关键字/条件/判据卡 → "
                "写一份 `collect_plan_*.json` 留档 → 请你过目。"
                "💡 **想直接跑就别点这个**：点右边「② 正式采集」，它一个回合内自己定计划、留档、**直接开跑**。")
    if _cp:
        _cp_help += (f"｜盘上最新计划：{_cp.name}（{datetime.fromtimestamp(_cp.stat().st_mtime):%Y-%m-%d %H:%M}）"
                     "——再点＝**重新出一份**（旧的不会被删；两份都留着，真跑默认用最新那份）")
    if c5.button(_cp_label, key="act_collect_plan", use_container_width=True,
                 disabled=not (a1 and decision_ok), help=_cp_help):
        task = build_step2_plan_task(job)

    _collected = bool(stt.get("step2_collected"))
    # v1.11.0：标签 = 「真跑」语义（老板原话："正式采集后还想再采集，可以改为 再次采集"）。
    # 盘上已有采集产物（job.db / collect_*.json）→ 说明采过了 → 显示「🔁 再次采集」。
    _c_label = ("② 正式采集（🔌 执行链路未接线）" if not _EXEC_WIRED
                else ("🔁 再次采集" if _collected else "② 正式采集"))
    _c_help = ("v1.11.0：**点它就是真跑**（全自动：小猎自己设条件+搜索 → **开工前先报池子** → 逐页本地粗筛打分（0 token）"
               "→ **够格就开详情**读全文 → 写进本岗库 job.db → **自动翻页** → 连续一批人不值得开就**换下一条关键字**"
               "→ 本地渲染采集报告）。🔴 **不设人为额度**（测试阶段死命令：不卡每日上限/每页配额/页数硬顶）。")
    if not _EXEC_WIRED:
        _c_help += ("｜⚠️ **当前未接线**：执行器（翻页/本地粗筛/写本岗库）还没做，所以这个按钮先灰着。")
    elif _cp:
        _c_help += (f"｜盘上已有计划 `{_cp.name}` → 直接按它跑；想改关键字/条件就先点左边的「🔄 重新出采集计划」。")
    else:
        _c_help += ("｜盘上**还没有计划** → 小猎会在**一个回合内**自己定 关键字/条件/判据卡、"
                    "**写一份计划留档**、然后**直接开跑**（中间不再请你确认）。"
                    "🔴 脚本开搜前有一道**开工前体检**（关键字形态/条件取值/判据卡），没过就**拒绝开跑**。")
    if c6.button(_c_label, key="act_collect", use_container_width=True,
                 disabled=(not _EXEC_WIRED) or not (a1 and decision_ok), help=_c_help):
        # ⚠️ v1.11.0：**一次点击就真跑**，不再有"先出计划再确认"两道门槛（老板拍板取消那两个子步骤）。
        #    有 plan 就按 plan；**没有 plan 也给任务书**（无计划分支：一回合内自定计划+留档+直接跑）。
        task = build_step2_run_task(job, _cp)

    # v1.12.0：③池子评估 → 💬 打招呼报告（老板拍板的新工作步骤：
    #   岗位分析 → 发岗助手 → 正式采集 → **打招呼报告** → 打招呼 → 查看回复）
    _gr = stt.get("step3_report")
    _gr_label = "🔄 重出打招呼报告" if _gr else "💬 打招呼报告"
    _gr_help = ("v1.12.0：小猎先看**态势**（池子多大 / 够格几个 / 打过几个 / 还剩多少 / 现在能不能打）→ "
                "**自己定口径**（够格少就放宽、打不完就收紧）→ 写口径计划留档 → 跑**细筛**（逐人调 LLM；"
                "评过的人命中缓存 **0 花费**）→ 出报告（**本地渲染 0 token**）。报告只列**够分的**，"
                "每人带 理由 / 匹配点 / 先核实 / 话术1·2 / 猎聘直达链接。")
    if _gr:
        _gr_help += "｜✅ 已有报告：再点＝按新口径重出一份（旧的不删）"
    if c7.button(_gr_label, key="act_greet_report", use_container_width=True,
                 disabled=not (stt.get("step2_collected") and decision_ok), help=_gr_help):
        task = build_greeting_report_task(job)

    # ── v1.12.1：④ 打招呼 / ⑤ 查看回复（老板 2026-09-20 拍板加）────────────────
    # 分工：**按钮不替小猎拍板**——面板只负责"把脚本的清单/结果端上来"；
    #   打招呼先 dry-run 列清单（一个人都不发），老板点「确认发送」才真发。
    jc = job["job_code"]
    _reps = _job_dir(job) / "reports"
    _plans = sorted(_reps.glob("greeting_plan_*.json"), key=lambda p: p.stat().st_mtime)
    _plan = str(_plans[-1]) if _plans else ""
    _greets = sorted(_reps.glob("打招呼报告_*.json"), key=lambda p: p.stat().st_mtime)
    _greet_json = _greets[-1] if _greets else None
    _greet_html = sorted(_reps.glob("打招呼报告_*_过程.html"), key=lambda p: p.stat().st_mtime)

    c8, c9 = st.columns(2)
    _g_help = ("v1.12.1：小猎读**最新打招呼报告**（谁、发什么都是报告写死的）→ 打开候选人详情页 → "
               "点【立即沟通】→ 点【不选择职位开聊】→ **紧接着发报告里的岗位介绍** → 关页面 → 记台账。"
               "｜🔴 先 dry-run **列清单、一个人都不发**；你点「确认发送」才真发（人工闸门）。"
               "｜前提：有报告 + 现在在时间窗内 + 桥在跑（双击 bridge-agent\\start_bridge.bat）。")
    _has_bridge = True
    if c8.button("💬 打招呼（先列清单）", key="act_greet_exec", use_container_width=True,
                 disabled=not (_greet_json and decision_ok), help=_g_help):
        ok_run, out = run_script("greet_exec.py", ["--job-code", jc], timeout=120)
        st.session_state["greet_preview"] = out
        st.session_state["greet_preview_ok"] = ok_run
    if st.session_state.get("greet_preview"):
        st.markdown("**📋 待打清单（dry-run，没发出去）**")
        st.code(st.session_state["greet_preview"], language="text")
        _n = st.number_input("本次最多打几个", min_value=1, max_value=50, value=3, step=1,
                             key="greet_confirm_n")
        if st.button(f"✅ 确认发送（最多 {int(_n)} 个，占 {int(_n)} 个额度）", key="act_greet_confirm",
                     type="primary"):
            ok2, out2 = run_script("greet_exec.py",
                                   ["--job-code", jc, "--yes", "--limit", str(int(_n))], timeout=900)
            st.session_state["greet_result"] = out2
            st.session_state["greet_preview"] = ""
    if st.session_state.get("greet_result"):
        st.markdown("**🤖 打招呼结果**")
        st.code(st.session_state["greet_result"], language="text")

    _r_help = ("v1.12.1：小猎开**职聊页**（h.liepin.com/im/showmsgnewpage）→ 读会话列表（谁、什么时候、"
               "最后一句、[已读]/[未读]）→ 落台账 → 重出报告（等回复→有回复）。**纯读，0 花费、0 风险**。")
    if c9.button("📨 查看回复（读回来记账）", key="act_reply_run", use_container_width=True,
                 disabled=not decision_ok, help=_r_help):
        ok3, out3 = run_script("reply_run.py", ["--job-code", jc], timeout=300)
        st.session_state["reply_result"] = out3
    if st.session_state.get("reply_result"):
        st.markdown("**📨 查看回复结果**")
        st.code(st.session_state["reply_result"], language="text")
    if _greet_html:
        st.caption("📄 打招呼报告（过程页）：")
        artifact_open_row(_greet_html[-1], key=f"greet_rep_{jc}_{_greet_html[-1].name}")

    # v1.12.0：第三行**先不放了**——老板口径「每个环节先做最基础的设计」，
    #   工作步骤 = 岗位分析 → 发岗助手 → 正式采集 → 打招呼报告 → 打招呼 → 查看回复（没有"入库"）。
    #   原「📥 入库当前岗」只读 collected_*.json + pool_report_*.json（都已不存在）→ 按下去只会写岗位行、
    #   候选人/评估都是 0 = **看起来成功、其实啥也没干**（犯本项目最重的那条纪律）→ **先摘掉**。
    #   `import_chat_job.py` 与 business.db 一个字节都没动：将来要收口（改成读 job.db）随时可加回来。
    return task


# ── 对话产物即点即开（v1.6.9：取代右侧报告栏；产物以可打开链接留在对话里）──

def run_script(script: str, args: list[str], *, timeout: int = 600) -> tuple[bool, str]:
    """跑一个本地脚本（**子进程**，不占面板线程），返回 (成功?, 输出尾部)。

    ⚠️ 只在面板按钮里用；脚本自己会做前置检查/校验，面板不替它判断成功。
    """
    import subprocess
    py = sys.executable
    cmd = [py, str(BASE / script)] + [str(a) for a in args]
    try:
        p = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode == 0, out
    except Exception as e:  # noqa: BLE001
        return False, f"跑 {script} 出错：{e}"


def greeting_plan_path(job_code: str) -> str:
    """本岗最新口径计划（greet_exec 要它；没有就给空串，脚本自己会拒绝）。"""
    reps = _job_dir({"job_code": job_code}) / "reports"
    got = sorted(reps.glob("greeting_plan_*.json"), key=lambda p: p.stat().st_mtime)
    return str(got[-1]) if got else ""


def artifact_open_row(path: Path, key: str) -> None:
    """一条产物的可打开行：文件名 + 「打开 ↗」按钮（os.startfile 本机打开，HTML=默认浏览器）。

    HTML 网页产物（发岗文字/打招呼清单/匹配报告/过程文档等）打开后可直接点页面里的链接操作，
    不用先看说明文字再手动去翻文件夹。
    """
    name = path.name
    if not path.exists():
        st.caption(f"📎 {name}")
        return
    is_html = path.suffix.lower() == ".html"
    c1, c2 = st.columns([7, 1], vertical_alignment="center")
    c1.markdown(f"📄 **{name}**")
    c1.caption("网页产物：打开后在浏览器里查看/点页面里的链接" if is_html
               else "点「打开 ↗」用本机默认程序查看")
    if c2.button("打开 ↗", key=key, use_container_width=True,
                 help="用本机默认程序打开（HTML=默认浏览器）"):
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as e:
            st.error(f"打开失败：{e}")


def render_artifacts(job: dict, msg_index: int, artifacts: list[str]) -> None:
    """助手消息下方的产物行：每个都是可点「打开 ↗」的链接。"""
    reports_dir = _job_dir(job) / "reports"
    for a in artifacts:
        artifact_open_row(reports_dir / a,
                          key=f"art_open_{job['job_code']}_{msg_index}_{a}")


def analyze_summary(job: dict) -> list[str]:
    """①分析摘要（本地从 analyze_*.json 渲染，0 花费）——给「岗位信息」弹窗用。"""
    ana = latest_report(job, "analyze_", ".json")
    if ana is None:
        return ["（这个岗还没做过 ① 岗前分析）"]
    try:
        d = json.loads(ana.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return [f"（①分析报告读不出来：{exc}）"]
    je, sc = d.get("jd_extracted") or {}, d.get("score") or {}
    out = [f"**{je.get('job_title') or '（未提取到岗位名）'}**"]
    for label, key in (("公司", "company"), ("城市", "city"), ("薪资", "salary")):
        if je.get(key):
            out.append(f"- {label}：{je[key]}")
    if sc.get("total") is not None:
        out.append(f"- 总分：{sc.get('total')}/25（{sc.get('level') or ''}）"
                   f"｜接单判断：{d.get('recommendation') or ''}")
    if sc.get("advice"):
        out.append(f"- 建议：{sc['advice']}")
    risks = sc.get("risks") or []
    if risks:
        out.append("- 风险（前 3 条）：")
        out += [f"  {i}. {str(r)}" for i, r in enumerate(risks[:3], 1)]
    out.append(f"- 报告文件：{ana.name}")
    return out


def job_profile_summary(job: dict) -> list[str]:
    """岗位资料摘要（本地从 job_profile.json 渲染，0 花费）——给「岗位信息」弹窗用。

    2026-09-15 加它的原因（老板当场提的）：正常流程是"我找 PM 沟通 → 拿到答复 → 让小猎记进岗位信息"，
    但记进去的 `job_profile.json` **面板上一直看不见**（只能开文件看）→ 记了也像没记，闭环缺一截。
    ⚠️ 纯只读展示：**面板不在这里改任何条目**（受控追加只走"发令给小猎"，见 CAPABILITIES 硬边界）；
    要删/改条目 = 结构性修改，由实施对话或老板人工处理。
    """
    p = job_profile_path(job)
    if not p.exists():
        return ["（这个岗还没有岗位资料 —— 在对话里说「记到岗位资料：<内容>」让小猎建档）"]
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return [f"（岗位资料读不出来：{exc}）"]
    if not isinstance(d, dict):
        return ["（岗位资料格式不对：顶层不是 JSON 对象）"]
    pm = [str(x) for x in (d.get("pm_notes") or []) if str(x).strip()]
    sp = [str(x) for x in (d.get("special_notes") or []) if str(x).strip()]
    ev = d.get("events") or []
    out: list[str] = [f"**PM / 发单方口径（{len(pm)} 条）** —— 生效口径以**数组最后一条**为准："]
    out += [f"{i}. {x}" for i, x in enumerate(pm, 1)] if pm else ["（空：还没有 PM 答回的口径）"]
    out.append(f"\n**猎头内部关注 / 客户特殊要求（{len(sp)} 条，不对候选人说）：**")
    out += [f"{i}. {x}" for i, x in enumerate(sp, 1)] if sp else ["（空）"]
    out.append(f"\n**变动时间线（共 {len(ev)} 条，显示最新 5 条）：**")
    if ev:
        for e in ev[-5:]:
            if isinstance(e, dict):
                out.append(f"- `{e.get('ts') or '—'}` **{e.get('who') or '—'}**：{e.get('note') or ''}")
            else:
                out.append(f"- {e}")
    else:
        out.append("（空）")
    return out


@st.dialog("📄 岗位信息", width="large")
def job_info_dialog(job: dict) -> None:
    """岗位信息弹窗（**纯本地读盘，0 花费**）：短名 / ①分析摘要 / 岗位资料 / 你粘贴的 JD 原文。"""
    code = job["job_code"]
    st.caption(f"岗位号（= 目录名，全项目的对齐键，**不要改**）：{code}")
    st.text_input("短名（你叫得顺口的名字；留空 = 用 ①分析里的岗位名）",
                  value=(job.get("display_name") or ""), key=f"dn_{code}")
    if st.button("💾 保存短名", key=f"dn_save_{code}"):
        save_meta(code, display_name=(st.session_state.get(f"dn_{code}") or "").strip())
        st.success("已保存（左侧列表与标题会立刻更新）")
        st.rerun()
    st.divider()
    st.markdown("**① 岗前分析摘要（本地渲染，0 花费）**")
    st.markdown("\n".join(analyze_summary(job)))
    st.divider()
    st.markdown("**📋 岗位资料（本地渲染，0 花费）**")
    st.caption("来源：job_profile.json｜**PM 答回后的正常动作**：在对话里说「记到岗位资料：…」，"
               "小猎受控追加（只增不改）；面板只读展示——改/删条目属结构性修改，由实施对话或你人工处理")
    st.markdown("\n".join(job_profile_summary(job)))
    st.divider()
    # ── v1.8.4 发布状态（占位：等走到打招呼流程再完善联动）──
    st.markdown("**📤 发布状态（占位，等走到打招呼流程再完善）**")
    _st = load_state(code)
    _posts = _st.get("liepin_posts") or []
    st.caption("用途（决策 32）：**发了 → 打招呼带岗位卡片（需 hjobId）；没发 → 不选职位直接开聊**。"
               "这里**只记录事实**——小猎不会替你发岗；默认「未知」≠「未发布」（不知道就问、不许猜）")
    st.markdown(f"当前：**{publish_status_text(_st)}**")
    if _posts:
        for _i, _p in enumerate(_posts, 1):
            st.markdown(f"{_i}. `{_p.get('hjob_id') or '—'}`｜{_p.get('title') or '（标题未填）'}｜"
                        f"{_p.get('city') or '—'}｜{_p.get('published_at') or '—'}"
                        f"｜来源：{_p.get('source') or '—'}")
    else:
        st.caption("（还没有发布记录）")
    with st.expander("➕ 记一条发布记录", expanded=not _posts):
        _hj = st.text_input("猎聘 hjobId（8 位数字；猎聘页面上不显示明文，在链接地址里）",
                            key=f"pub_hj_{code}")
        _ti = st.text_input("猎聘上你填的职位名称（原文）", key=f"pub_ti_{code}")
        _ci = st.text_input("城市（可空，双城发布就分两条记）", key=f"pub_ci_{code}")
        _pa = st.text_input("发布时间（可空，照猎聘上显示的抄）", key=f"pub_pa_{code}")
        if st.button("💾 记下这条发布", key=f"pub_save_{code}"):
            append_publish_post(code, {"hjob_id": _hj, "title": _ti, "city": _ci,
                                       "published_at": _pa, "source": "老板口述（面板录入）", "note": ""})
            st.success("已记下（发布状态 → 已发布）")
            st.rerun()
    _cb1, _cb2 = st.columns(2)
    _warn = f"⚠️ 会**一并清掉上面 {len(_posts)} 条发布记录**（要保留就别点）" if _posts else "（当前没有记录可清）"
    if _cb1.button("⭕ 标为「未发布到猎聘」", key=f"pub_no_{code}", help=_warn):
        set_publish_status(code, "not_published")
        st.rerun()
    if _cb2.button("❓ 清回「未知」", key=f"pub_unk_{code}", help=_warn):
        set_publish_status(code, "unknown")
        st.rerun()
    st.divider()
    st.markdown("**你原来粘贴的 JD 原文**（逐字未改）")
    jd_p = _job_dir(job) / "jd.txt"
    if jd_p.exists():
        st.text_area("JD 原文", value=jd_p.read_text(encoding="utf-8", errors="replace"),
                     height=300, disabled=True, key=f"jdv_{code}", label_visibility="collapsed")
    else:
        st.caption("（这个岗没有 jd.txt）")


def kind_of_task(t: str) -> str:
    """把任务书文本归类成动作名（v1.8.9 抽到模块级：渲染/台账/工具面都按它分档，抽出来才能单测）。"""
    if t.startswith("老板要你执行【步骤①"):
        return "analyze"
    if t.startswith("老板要你执行【搜索体检】"):
        return "probe"
    if t.startswith("老板要你执行【步骤②"):
        return "collect_plan"
    if t.startswith("老板已确认【步骤②"):
        return "collect_run"
    if t.startswith("老板要你执行【打招呼报告】"):
        return "greet_report"
    if t.startswith("老板要你生成【发岗文字】"):
        return "post_text"
    return "report"


def render_main(cfg: dict) -> None:
    jobs = cfg["jobs"]
    if not jobs:
        st.info("先在左侧「➕ 新建岗位会话」创建一个岗位（粘贴/上传 JD），再开始第一步测试。")
        return
    pick = st.session_state.get("job_pick_chat") or jobs[0]["job_code"]
    job = next((j for j in jobs if j["job_code"] == pick), jobs[0])

    _h1, _h2 = st.columns([8, 1], vertical_alignment="center")
    _h1.markdown(f"### 🗣 {job_display_name(job)}")
    _h1.caption(f"岗位 {job['job_code']} · 会话 {job['session_id']} · 创建于 {job['created_at']}")
    if _h2.button("📄 岗位信息", key=f"jobinfo_{job['job_code']}", use_container_width=True,
                  help="看这个岗的 JD 原文 / ①分析摘要 / 给它起个短名（纯本地，0 花费）"):
        job_info_dialog(job)
    render_progress_line(job)

    # v1.6.9 布局：对话流全宽；每步产物以「可打开」行留在对话里（右侧报告栏已去掉）
    for mi, m in enumerate(load_transcript(job["job_code"])):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            render_artifacts(job, mi, m.get("artifacts") or [])

    # 动作按钮行 + 自由输入
    task = render_action_row(job, cfg)
    prompt = st.chat_input("跟小猎说话：发指令 / 追问 / 讨论；也可以直接粘贴 JD 原文…")

    to_send = None
    agent_prompt = None
    action_kind = None
    if task:
        action_kind = kind_of_task(task)
        agent_prompt = task
        to_send = task
    elif prompt:
        # 若输入疑似整段 JD 且 jd.txt 为空 → 顺手存档为岗位 JD
        if not load_state(job["job_code"]).get("jd_provided") and len(prompt) > 200 and ("职位" in prompt or "岗位" in prompt):
            (_job_dir(job) / "jd.txt").write_text(prompt, encoding="utf-8")
            save_state(job["job_code"], jd_provided=True)
        to_send = prompt
        stt_now = load_state(job["job_code"])
        # v1.7.0 判断对话化：①分析完 & 等你拍板 → 先识别拍板（本地处理，不调 agent；可纠正）
        if stt_now.get("step1_analyzed") and stt_now.get("decision") == "pending":
            dec_action = detect_decision_intent(prompt)
            if dec_action:
                append_msg(job["job_code"], "user", to_send)
                record_decision(job, dec_action, prompt)
                append_msg(job["job_code"], "assistant", build_decision_reply(dec_action, prompt))
                st.rerun()
                return
            # v1.8.5：**疑似拍板 → 面板本地处理**（0 花费）。治两次实测漏拍板：
            # 「直接往下走吧，把这个岗位写入岗位」(09-09) / 「我们做这个岗位吧」(09-15) 都落进了自由对话，
            # 而自由对话里它**没有记决策的手** → 只能说"我记为 accept"（假事实）。
            _awaiting = last_pending_ask(job["job_code"])
            _conf = confirmed_intent(prompt, _awaiting)
            if _conf:
                append_msg(job["job_code"], "user", to_send)
                if _conf == "cancel":
                    append_msg(job["job_code"], "assistant", CANCEL_REPLY)
                else:
                    record_decision(job, _conf, prompt)
                    append_msg(job["job_code"], "assistant",
                               build_decision_reply(_conf, prompt)
                               + "\n（这次是**面板先问、你点头**才记的——不是它替你猜的。）")
                st.rerun()
                return
            _hint = detect_decision_hint(prompt)
            if _hint:
                append_msg(job["job_code"], "user", to_send)
                append_msg(job["job_code"], "assistant", build_decision_ask(_hint, prompt))
                st.rerun()
                return
        # 已拍板（decline/clarify）后想重跑①重新判断 → 走 analyze（decision 自动回 pending）
        if (stt_now.get("step1_analyzed") and stt_now.get("decision") in ("decline", "clarify")
                and detect_rejudge_intent(prompt)):
            action_kind, agent_prompt = "analyze", build_step1_task(job)
        else:
            # v1.6.3 修复：自由聊天必须走 build_free_task，注入状态卡+完整路径+能力边界+硬指令
            # （历史 bug：build_free_task 定义了没接线，agent 反复“找不到岗位文件”）
            # v1.12.0：先识别意图——💬打招呼报告（本地脚本，优先）→ ②采集（出计划/确认后执行）；讨论性问句不触发
            gr_rep, coll = False, ""
            # 先跑分类器（**不带闸门**）：②发令分三种——出计划 / 按计划跑 / 不是发令。
            # v1.9.1 修掉一个真 bug：此前把闸门塞进 `detect_collect_intent` 里，
            #   它未接线时对**一切**返回 ""，于是"按计划跑"（必须先有计划才算确认）也永远接不上——
            #   闸门自己把"先出计划 → 再说按计划跑"这条路砍断了。
            # 现在：分类器纯判"他是不是在喊②"；**接不接线由这里（闸门）决定**。
            _coll_kw = looks_like_collect_cmd(prompt)
            coll = detect_collect_intent(prompt, job)
            if not _EXEC_WIRED and (_coll_kw or coll):
                append_msg(job["job_code"], "user", to_send)
                append_msg(job["job_code"], "assistant", EXEC_NOT_WIRED_REPLY)
                st.rerun()
                return
            if stt_now.get("step1_analyzed"):
                # v1.12.0：先认「出打招呼报告」（老板原话：先生成一个打招呼的报告吧，这次宽松点）
                gr_rep = bool(stt_now.get("step2_collected")) and detect_greet_report_intent(prompt, job)
                if not gr_rep:
                    coll = coll or detect_collect_intent(prompt, job)
            if gr_rep:
                action_kind, agent_prompt = "greet_report", build_greeting_report_task(job)
            elif coll == "plan":
                action_kind, agent_prompt = "collect_plan", build_step2_plan_task(job)
            elif coll == "run":
                plan_f = latest_collect_plan(job)
                action_kind = "collect_run"
                agent_prompt = build_step2_run_task(job, plan_f) if plan_f else build_free_task(job, prompt)
            else:
                action_kind, agent_prompt = "chat", build_free_task(job, prompt)

    if to_send:
        decision_before = load_state(job["job_code"]).get("decision")  # v1.8.5 事实核对用（跑前口径）
        append_msg(job["job_code"], "user", to_send)
        run_sid = "-"
        try:
            with st.status("小猎工作中（阻塞式，长任务请耐心等待）…", expanded=False) as status:
                # ①分析要产两份大文件（结论 JSON + 过程网页）；8192 太紧、实测被截断 → 与 greet 同为 16384
                max_tok = 16384 if action_kind == "analyze" else 8192
                reply, new_files, run_sid = run_assistant(
                    job, agent_prompt, cfg["env_path"],
                    stub=cfg["stub"], max_tokens=max_tok, action=action_kind,
                    tool_profile=TOOL_PROFILE_BY_ACTION.get(action_kind))
                status.update(label=f"小猎完成（本次会话 {run_sid}）", state="complete")
        except Exception as e:
            reply = f"⚠️ 执行出错：{e}\n\n（若是 .env/API 问题请检查侧栏运行设置；界面自测请开「假执行」）"
            new_files = []
        append_msg(job["job_code"], "assistant", reply,
                   artifacts=[p.name for p in new_files])
        # ①分析：**先判真假成功，再决定状态**——不许假成功
        # （2026-09-14 实测事故：小猎没写出任何文件，面板却把状态标成"①完成/等你拍板"）
        analyze_ok = True
        if action_kind == "analyze" and not cfg["stub"]:
            rep = next((p for p in new_files
                        if p.name.startswith("analyze_") and p.suffix == ".json"), None)
            analyze_ok = rep is not None
            if analyze_ok:
                # ── 第二刀（2026-09-15）：过程网页**本地渲染**（0 花费、确定性、有长度预算）──
                # 原来这份 HTML 由小猎手写、没有上限（盘上真网页 9.4K~24.1K 字节；一回重跑 +51%），
                # 会把第一刀省下的 token 吃回去（实测 output 8,923→10,200）。
                # 判断结论仍全部来自它写的 analyze JSON，一个字不改——这里只搬运、排版、量长度。
                try:
                    hp = render_analyze_html(job, rep)
                    append_msg(job["job_code"], "assistant",
                               f"🧾 过程网页（本地渲染，0 花费）已生成：{hp.name}"
                               f"（{hp.stat().st_size} 字节）——点下方「打开 ↗」看",
                               artifacts=[hp.name])
                except Exception as e:
                    append_msg(job["job_code"], "assistant",
                               f"⚠️ 过程网页**本地渲染失败**（**不影响①结论**：JSON 是资产、网页只是壳）：{e}")
                if local_checks is not None:
                    append_msg(job["job_code"], "assistant",
                               "🔍 " + local_checks.check_analyze(rep)["summary"])
            else:
                fr = LAST_RUN.get("finish_reason") or "（未知）"
                append_msg(job["job_code"], "assistant",
                           f"⚠️ **①分析没有产出文件**——本次运行的结束原因：`{fr}`。"
                           "小猎话说了但报告没写下来，所以**状态没有被标成完成**"
                           "（纪律：不许假装执行，系统自己也一样）。"
                           "建议直接再点一次「🔄 重跑岗位分析」；若连续失败，把这条消息贴给实施对话。")
        # ②采集·出计划 → **本地判分**（v1.8.8，0 花费）：小猎把计划写出来后，当场核对
        # "条件组的取值在不在配方表的合法档里" —— 值不在 = 硬凑（如 years=5-8年），立刻贴给老板，
        # 而不是等真跑完发现"池子薄"再回头怀疑市场（这是"能力体检"最便宜的那半场：翻译考试）。
        if action_kind == "collect_plan" and not cfg["stub"] and local_checks is not None:
            pf = next((p for p in new_files
                       if p.name.startswith("collect_plan_") and p.suffix == ".json"), None)
            if pf is not None:
                append_msg(job["job_code"], "assistant",
                           "🔍 " + local_checks.check_collect_spec(pf)["summary"])
                # v1.9.2：**判据卡体检**（本地、0 花费）——抓"会让整轮空跑"的坑：
                #   同条件组给多值（如城市南京+苏州 = 要求同时满足 → 0 命中）、行业词写连写复合词。
                #   实测 2026-09-16：小猎第一份带判据卡的计划就踩了"双城并排"这一条。
                try:
                    _plan_d = json.loads(Path(pf).read_text(encoding="utf-8-sig"))
                    _probs, _warns = local_checks.check_judge_card(_plan_d)
                    _lines = ["🧪 **判据卡体检（本地，0 花费）**"]
                    if _probs:
                        _lines.append("**必须先改**（否则这一轮八成空跑）：")
                        _lines += [f"- {x}" for x in _probs]
                    if _warns:
                        _lines.append("提醒：")
                        _lines += [f"- {x}" for x in _warns]
                    if not _probs and not _warns:
                        _lines.append("✅ 没发现会空跑的坑（条件是一值一组、行业词没有连写复合词）")
                    append_msg(job["job_code"], "assistant", "\n".join(_lines))
                except Exception as _e:  # noqa: BLE001
                    append_msg(job["job_code"], "assistant", f"🧪 判据卡体检没跑成（不影响计划）：{_e}")
        # ②搜索体检（v1.8.9）：本地判分计划 + **本地渲染过程报告**（两件都 0 token）
        # 先判真假成功再说话：没有轨迹文件 = 没有报告（不许假装跑过；与①"没产出就不置完成"同一条纪律）。
        if action_kind == "probe" and not cfg["stub"]:
            _pf = next((p for p in new_files
                        if p.name.startswith("search_probe_plan_") and p.suffix == ".json"), None)
            _tf = next((p for p in new_files
                        if p.name.startswith("search_rounds_") and p.suffix == ".json"), None)
            _cf = next((p for p in new_files
                        if p.name.startswith("search_probe_concl_") and p.suffix == ".json"), None)
            if local_checks is not None and _pf is not None:
                try:
                    append_msg(job["job_code"], "assistant",
                               "🔍 " + local_checks.check_probe_plan(_pf)["summary"])
                except Exception as e:
                    append_msg(job["job_code"], "assistant",
                               f"⚠️ 体检计划的本地判分没跑起来（不影响体检本身）：{e}")
            if _tf is not None:
                try:
                    _hp = render_probe_html(job, _tf, _cf)
                    append_msg(job["job_code"], "assistant",
                               f"🧾 搜索体检过程网页（本地渲染，0 花费）已生成：{_hp.name}"
                               f"（{_hp.stat().st_size} 字节）——点下方「打开 ↗」看",
                               artifacts=[_hp.name])
                except Exception as e:
                    append_msg(job["job_code"], "assistant",
                               f"⚠️ 过程网页**本地渲染失败**（**不影响轨迹 JSON**：轨迹是资产、网页只是壳）：{e}")
            else:
                append_msg(job["job_code"], "assistant",
                           "⚠️ **本次没有产出轮次轨迹**（`search_rounds_*.json`）→ 所以没有过程报告。"
                           "常见原因：小猎没真跑脚本 / 脚本半路失败 / 猎聘那个标签页的扩展没挂上"
                           "（在猎聘页上按 F5 刷新一下再试）。具体看它上面贴的原话。")
        # 更新状态卡
        label_map = {"analyze": "岗位分析", "report": "未分类任务", "chat": "自由对话",
                     "collect_plan": "②采集·出计划", "collect_run": "②采集·执行", "probe": "②搜索体检",
                     "greet_report": "💬打招呼报告", "post_text": "发岗文字"}
        upd = {"last_action": label_map.get(action_kind, action_kind), "last_run_session": run_sid}
        if action_kind == "analyze":
            if analyze_ok:
                # v1.7.0：①分析完 → 进入「等你拍板」判断点（重跑清掉旧决策）
                upd["step1_analyzed"] = True
                upd["decision"] = "pending"
                upd["decision_note"] = None
                upd["decision_ts"] = None
            else:
                # 没产出 → 不置完成、不进判断点；状态按盘上真实产物算，并清掉可能误置的决策
                upd["step1_analyzed"] = bool(any(p.name.startswith("analyze_")
                                                 for p in list_artifacts(job["job_code"])))
                upd["decision"] = None
                upd["decision_note"] = None
                upd["decision_ts"] = None
                upd["last_action"] = "①分析失败（没产出文件）"
        if action_kind == "collect_run":
            # v1.11.0：认账口径同 load_state（collect_*.json / job.db 都算采过；collect_plan_* 不算）
            upd["step2_collected"] = collect_output_exists(job["job_code"])
        if action_kind == "greet_report":
            # v1.12.0：打招呼报告出没出，按盘上**真实产物**算（不许假成功）
            upd["step3_report"] = bool(any(p.name.startswith("打招呼报告_")
                                           for p in list_artifacts(job["job_code"])))
        save_state(job["job_code"], **upd)
        # ── v1.8.5 事实核对（治"它嘴上说已记、系统里没记"；与 §2.6「面板不许假成功」同一套机制）──
        # 实测 09-15 10:30：它说「我记为接单（accept）」，而 state.decision 仍是 pending。
        # 面板不能只把它的话转给老板——**必须在同一屏里给出系统里的事实**。
        if action_kind == "chat":
            _after_dec = load_state(job["job_code"]).get("decision")
            if _after_dec == decision_before and claims_recorded_decision(reply):
                append_msg(job["job_code"], "assistant",
                           "⚠️ **事实核对（面板本地核查，不是小猎发言）**：它上面说自己把你的拍板记下了，"
                           f"但**系统里没有发生**——`state.decision` 仍是 `{_after_dec}`。\n"
                           "原因：**拍板只能由你亲口说的精确词触发**（做吧 / 不做 / 先核实），"
                           "它手里没有「记决策」这只手（结构性修改不在自由对话授权内）。\n"
                           "→ 想落盘就回一句「**做吧**」（或 不做 / 先核实）；它刚才那段判断不用重跑。")
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="数字合伙人 · 对话汇报（v1.12.1）", page_icon="🗣", layout="wide")
    st.markdown("# 🗣 数字合伙人 · 对话式汇报")
    st.caption("v1.12.2：**「分析完却没有决策记录」⇒ 等价「待拍板」**（治 09-21 那个真岗：①分析在自由对话里跑完 ⇒ `decision` 永远 null ⇒ 对话里记不了拍板，而②按钮却亮着放行采集；现在推导 pending、②锁）｜ v1.12.1｜ ④打招呼（先列清单→确认发）/ ⑤查看回复（纯读）**已接入**｜ v1.12.0：③池子评估**已取消** → 换成 **💬打招呼报告**（小猎自己的工作依据：看态势 → 自己定口径 → 细筛 → 出报告，本地渲染 0 token）｜ ②正式采集 = **一键真跑**（**小猎自己设条件+搜索** → **开工前先报池子** → 本地粗筛判分 → "
               "**够格就开详情**读全文 → 写本岗库 job.db → **自动翻页** → 连续一批人不值得开就**换下一条关键字** "
               "→ 本地渲染采集报告）；盘上没计划时它**一回合内自定计划+留档+直接跑**（**中间不停**）｜ "
               "🔴 **开工前体检**（关键字形态/条件取值/判据卡）没过就**拒绝开跑**（缺判据卡=硬拒绝）｜ "
               "🔴 **不设人为额度**（测试阶段死命令：不卡每日上限/每页配额/页数硬顶）｜ "
               "「🔎 搜索体检」「出采集计划」两个测试期子步骤**不挡在主流程前面**（体检能力已并进采集）｜ "
               "⚠️ 开详情依赖桥的 `page_text`：**改过扩展后要在 chrome://extensions 重载一次**｜ "
               "拍板：精确词直接记；**疑似拍板 → 面板当场反问**（不替老板猜、也不听它嘴上说「已记」）｜ "
               "判断对话化（①分析完 → 小猎给态度+理由 → 你拍板 做/不做/先核实）｜ "
               "自由对话=读+受控追加（说「记到成长库/记到岗位资料」）；结构性修改（删改/动代码）走人工或实施对话｜ "
               "一岗一会话｜ 对话里产物即点即开（HTML 用浏览器打开）｜ "
               "①②③+发岗/打招呼清单/入库已接入｜ 纠错成长账：`data/growth/records.jsonl` + `data/prompts/rules.md`")
    ensure_rules()
    cfg = render_sidebar()
    render_main(cfg)


if __name__ == "__main__":
    main()
