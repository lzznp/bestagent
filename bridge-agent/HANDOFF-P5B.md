# 交接包：P5 设计转折 — B 计划（配方+校验+确定性执行）验证通过

> 生成时间：2026-08-23 ｜ 交接方式：本对话 → 新对话
> 新对话开场：先读本文件 → `HANDOFF-P5-3方联调.md`（P5 起点）→ `agent/page_recipes.json` + `agent/recipe_exec.py` → 再问环境

---

## 0. 一句话状态

**P5 三方圆联调暴露 LLM agent 决策不可靠（漏条件/点错/假完成）→ 设计转折：从"LLM 全权执行"改为"配方表（确定性）+ 校验 + LLM 只做决策"。配方执行器已在真实浏览器验证：歌尔条件 6/6 全设置成功+每步校验+提取正确候选人。视觉降级为侦察兵，未废弃。**

## 1. 设计转折（本对话核心结论）

- **旧路线（P1-P4）**：LLM 每步看快照猜编号 → 定位/流程/校验全交给 LLM → P5 实测失败（2/6 条件、点错成都、假完成、经验库污染）
- **新路线（B 计划）**：**配方表 = 精确操作知识（可执行）**；**执行器 = 确定性代码**（按配方执行+每步校验）；**LLM 只做决策**（JD→条件规格）；视觉=异常诊断侦察兵
- 本质：你原 Playwright 方案（脚本+人工兜底）的升级——把"人工兜底"换成"LLM 决策+程序校验"，脚本换成配方表
- 你的原话锚点："工作页面就这几个，不考虑改版，预先测试，以后 agent 少走弯路"——预测试铺路是正路

## 2. 实测关键发现（全部真值，配方表已固化）

| 发现 | 详情 | 对策 |
|---|---|---|
| **即点即搜** | 工作年限/教育经历/院校要求 chip = 点击选中+**自动触发搜索**（#session）；结果**等 8 秒才过滤生效**（2.5s 不够会误判"没过滤"） | 配方 chips 类型 + WAIT_RESULTS=8 |
| **下拉要 mousedown** | 统招/活跃度/性别/跳槽/求职状态是 Ant Design Select，监听 **mousedown**；`el.click()` 打不开 | 扩展 zClick/zClickByText 加 mousedown/mouseup 序列（已修） |
| **输入框零面积隐藏** | 关键词框等 Ant Select 搜索框未激活时 width<4 或与容器 IoU>0.8，被快照跳过 | 扩展 4 副本（zSnapshot/zClick/zType/som_shot）改"input/textarea/select 永远保留"（已修） |
| **拆节点** | "3-5年"= em"3-5" + label"年"，click_by_text 必须用"3-5" | 配方 click_text_map |
| **"不限" occ 映射** | document order：occ5 统招 / occ8 活跃度 / occ9 性别 / occ10 跳槽；"（不限）" occ2 跳槽 / occ3 求职状态 | 配方 locate.open_text/open_occ |
| **编号不稳定** | 干净页元素数 139/141 波动（快照修复后 155） | **一律文本定位，不按编号** |
| **城市面板** | 多选+必须点确认+确认后自动搜索+#session+面板背后页面 chip 混入编号 | 配方 city 流程 + 过滤结果按"输入框正下方 name=城市名 span"找 |
| **展开更多条件** | 内容已在 DOM 可见（元素有 rect），无需先点击 | 配方 confirmed |
| **下拉选项** | 统招：统招本科/硕士/博士/大专；活跃度：今天活跃/3天内/7天内/30天内/最近三月/半年/一年；求职状态：离职正在找工作/在职急寻/在职看看新机会/在职暂无跳槽打算 | 配方 options |

## 3. 代码改动清单（本对话）

| 文件 | 改动 |
|---|---|
| `extension/background.js` | ① zClick/zClickByText 加 mousedown/mouseup 真实事件序列（Ant Design Select 才能展开）② zSnapshot/zClick/zType/som_shot 4 副本：input/textarea/select 豁免零面积跳过+IoU 去重（隐藏搜索框可定位） |
| `agent/core.py` | params 白名单加 **occurrence**（P3 T1 就埋下的静默 bug：LLM 发 occurrence=2 被丢弃→扩展收 1；期望城市"其他"永远点不到） |
| `agent/page_recipes.json`（新） | 找简历页 **29 组条件配方表**：24 confirmed / 5 pending；每组含 type/options/action/verify/pits/locate（结构化：input_contains 或 pos、other_occ、click_text_map、open_text/open_occ）；behaviors（即点即搜/下拉展开方式/occ 映射/城市面板/结果页结构/页面记忆/编号不稳定） |
| `agent/recipe_exec.py`（新） | 配方执行器：`execute_spec(spec, tab_id)` 按 TYPE_ORDER（input→dropdown→city→chips）排序执行，每步程序化校验（value/#session/已选标签窗口），收尾点"搜 索"+extract+去重；失败返回 {failed, error} 供归因 |
| `p5_run.py` / `p5_probe.py` / `p5_probe_conds*.py` / `p5_cond_probe*.py` | LLM run 驱动 + 页面/控件探针脚本（测试基建，可复用） |

## 4. 验证结果（真实浏览器）

- **配方执行器**：歌尔条件（嵌入式/双城青岛/3-5年/985/今天活跃）**6/6 全设置+校验通过** → 搜 索 → 提取 2 位候选人
- **候选人判定**：城市/年限/院校条件精确生效（985 院校、3-5 年、青岛 ✓）；关键词"嵌入式"是全文宽泛匹配（业务层可换更精准关键词）
- **回归**：6 套测试全过（test_experience 43/0 等），mousedown/输入框修复无回归
- **对比旧路线**：LLM agent 2/6 条件+点错+假完成 vs 配方执行器 6/6+每步校验

## 5. 环境备忘（当前状态）

- **浏览器**：猎聘 tab 1890028341（找简历页，当前停在歌尔条件的结果页 2 候选人）；激活标签=dsh GUI
- **扩展**：background.js 已含两处修复，**已重载**（用户操作）；再改需用户重载
- **bridge**：单实例 8080；core.py 改动对新进程立即生效（跑 `python -m agent.recipe_exec` 或 pipeline 前无需重启）
- **配方表**：`agent/page_recipes.json`（热加载无缓存，直接读）
- **JD 素材**：歌尔 MCU 固件 JD 在对话里（p5 讨论区），可另存

## 6. 下一步建议（按序）

1. **LLM 决策层接执行器**（本对话已在做）：`jd_to_spec(jd)` → LLM 输出条件规格 JSON（只从配方 options 里选）→ `execute_spec` → **JD→候选人闭环**
2. **pending 控件**（低优先）：当前行业/职位（input placeholder 型，交互特殊）、简历语言、跳槽频率选项文字
3. **经验沉淀重设计**：自动沉淀需"业务正确性校验通过"才允许（v6 污染教训：ok=True 但业务全错也沉淀了）
4. **职聊页配方表**：定位零障碍，难点是不可逆动作（发送/索要）= 人工确认闸门（P3 机制已有）
5. **视觉接入异常诊断**：执行器校验失败 → 截图+视觉"页面变成什么样了" → 修正方向（改版/弹层/时序）

## 7. 关键教训（下个对话别重踩）

1. **occurrence 白名单 bug 存在 4 个阶段无人发现**（P3 T1 埋下，P5 才暴露）——确定性动作参数要有单测
2. **置信度闸门不查业务正确性**——"任务 ok"≠"业务对"，自动沉淀会污染
3. **按编号操作必踩坑**（139/141 波动）——文本定位是唯一可靠方式
4. **先测试后固化是正路**：页面预测试→配方→执行→修正，而不是让执行时现踩
5. **下拉打不开先查事件类型**（click vs mousedown），输入框找不到先查零面积/去重
