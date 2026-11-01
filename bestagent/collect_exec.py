#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_exec.py — ②正式采集·执行器（**手**：动手；判断交给 collect_rules.py）

分工：
  - **小猎**：根据 JD 自主决定"这一轮怎么采"（关键字 / 条件）→ 写成计划小 JSON；
  - **本脚本**：确定性执行——**自己设条件+搜索 → 读页 → 本地判分 → 够格就开详情（读全文）
    → 写本岗库 → 自动翻页 → 换下一条关键字**；
  - **collect_rules**：判断（谁值得开详情 / 该不该停），**不调 LLM**。

🔴 **死命令（2026-09-16 老板拍板，测试阶段不设人为额度）**：
  `--max-pages / --details / --total-details` 默认全是 **0 = 不限**。本脚本不因"每日额度 /
  每页配额 / 页数硬顶 / 详情总数"而少采或停采；`quota` 只**记账当日志**，不拦。
  ⚠️ 保留的两条**不是额度**：① 真人节奏延迟（账号保护）② "翻不动 / 翻页没生效（没有新人）"（防死循环）。
  ⚠️ 平台侧的"查看简历数"是真实代价，所以**本岗库已有全文的人不重复开详情**（重跑/换词都不浪费）。

⚠️ 纪律（都是被实测逼出来的）：
  1. **自己搜**（v1.10.0）：`search_page` 走 `execute_spec`（体检线 2026-09-15 已在真猎聘跑通）
     → **"关键字必须老板先人工搜一次"永久消失**，也是"**换关键字**"成立的前提。
     搜失败就**跳过不采**（宁可这一条空着，绝不采错页）。
  2. **翻页自动**（v1.9.2）：`click_paging` 按分页结构点（按文字点会撞到年龄"46岁"里的 span）。
  3. **边采边落盘**：每人一落库（老板老代码的做法），崩了/点停都不丢已采的。
  4. **详情全文只从 `page_text` 取**（v1.9.0 新动作，不截断）：`snapshot` 的 3000 字实测会切掉
     项目经历/技能/自我评价（三份简历 3000/2999/1752 全卡上限）→ 那条路只能"预览"，不能当全文。
  5. **开工前体检**（v1.11.0）：`--plan` 路径在**开搜之前**跑 `preflight_plan`
     （= `check_collect_spec` + `check_judge_card`）→ 有问题**拒绝开跑**。体检这块能力
     原来是「🔎 搜索体检」那个子步骤的，现在**并进采集**（老板拍板取消那两个子步骤）。

用法（cwd = bestagent/）：
  # 真跑（推荐）：按小猎的计划——每条关键字**自己搜**、自动翻页、够格就开详情、写本岗库
  python collect_exec.py --job-code J-CHAT-20260909-094907 --plan <计划>.json --all-keywords
  # 只本地判分，不开详情、不写库（最安全的试跑；--plan 路径同样生效）
  python collect_exec.py --job-code ... --plan <计划>.json --dry-run
  # 老行为：用老板已经搜好的当前页（不搜、只跑这一页）
  python collect_exec.py --job-code ... --keyword "..." --page 1 --no-search
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from framework_config import BROWSER_AGENT, WORKSPACE  # noqa: E402
sys.path.insert(0, str(BROWSER_AGENT))

from agent.core import submit_task  # noqa: E402
from agent.recipe_exec import BRIDGE, COND_URL, execute_spec  # noqa: E402

import collect_rules as cr  # noqa: E402
import job_db  # noqa: E402
import local_checks  # noqa: E402
from collect_liepin import find_liepin_tab, stop_requested  # noqa: E402
from quota import Quota  # noqa: E402
# v1.11.0：把「搜索体检」的两块能力**并进采集**（老板 2026-09-16 拍板：取消那两个子步骤）：
#   ① `read_total` = 只读页面「共N位人选」（体检线 2026-09-15 真猎聘跑通）→ 开工前先报池子厚薄；
#   ② `AUTO_SEARCH_TYPES` = 哪些条件是"即点即搜"（读了才不是旧状态）。
from search_rounds import AUTO_SEARCH_TYPES, read_total  # noqa: E402

CHAT = WORKSPACE / "data" / "chat"
DETAIL_URL = "https://h.liepin.com/resume/showresumedetail/?res_id_encode={rid}"
ANCHOR = "立即沟通"
# 猎聘详情页正文的锚点：**真简历都有**（2026-09-17 用它抓出 3 份"采错页"的假全文）
RESUME_MARK = "简历编号"
# 详情页折叠项：点开再抓，否则项目经历被折叠吃掉（老板老代码踩过这个坑）
TOGGLE_RE = r"(显示其他\s*\d+\s*段[^\n]{0,24}|查看更多[^\n]{0,16}|查看全部\s*\(?\d*\)?[^\n]{0,8})"
OPEN_WAIT = 7.0        # 详情页加载等待（老板老代码 6s；这里 7s 保守一点）
OPEN_GAP = (5.0, 12.0)  # 详情之间的随机间隔（真人节奏）
PAGE_GAP = (8.0, 20.0)  # 页/关键字之间的随机间隔
# 🔴 死命令（2026-09-16 老板拍板）：**测试阶段不设人为额度**。
#    → 下面是"不设限"的默认值：0 = 不限。只有显式传正数才按它停。
UNLIMITED = 0          # max_pages / details_per_page / total_details_cap 的"不限"取值
# 自己设条件+搜索（把「搜索体检」那条已实测的通路接进采集，见 search_page）
WAIT_NAV = 2.5         # navigate 到找简历页后等它渲染
WAIT_CLEAR = 2.0       # 点「清空筛选条件」后等它生效


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def submit_task_to(bridge: str, action: str, params: dict, source: str = "collect-exec",
                   timeout: float = 60.0) -> dict:
    """提交任务并等待结果，**超时自己定**（照抄 agent.core.submit_task，只把 60s 改成参数）。

    为什么要它：`agent.core.submit_task` 的 deadline 硬编码 60 秒。实测 2026-09-16：
    `snapshot` 在猎聘结果页（DOM 很大）会卡到 60 秒超时——而它只是"顺手读一下共N位人选"，
    用硬编码 60 秒会**每页白等一分钟**。这里给 snapshot 类"可选读数"用 6 秒，失败就算了。
    ⚠️ 超时后那条任务仍会把桥的 in-flight 占住（桥没有取消口子）→ 调用方要能接受"这次不读数"。
    """
    import time as _t
    import urllib.request
    req = urllib.request.Request(f"{bridge}/api/task", method="POST",
                                 data=json.dumps({"action": action, "params": params,
                                                  "source": source}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        task = (json.loads(r.read().decode("utf-8")) or {}).get("task") or {}
    tid = task.get("id")
    if not tid:
        return {"ok": False, "error": "桥没有返回 task id"}
    deadline = _t.time() + float(timeout)
    while _t.time() < deadline:
        _t.sleep(0.7)
        try:
            with urllib.request.urlopen(f"{bridge}/api/task/{tid}", timeout=8) as r:
                t = (json.loads(r.read().decode("utf-8")) or {}).get("task") or {}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"轮询失败：{e}"}
        if t.get("status") == "done":
            return {"ok": True, "result": t.get("result")}
        if t.get("status") in ("failed", "timeout"):
            return {"ok": False, "error": t.get("error") or "action-failed"}
    return {"ok": False, "error": f"等待执行结果超时（{timeout}s）"}


def search_page(tab: int, keyword: str, conds: list[str] | None = None,
                read_pool=read_total) -> dict:
    """**自己设条件 + 自己搜索**（v1.10.0：把「搜索体检」那条已实测的通路接进采集）。

    v1.11.0（2026-09-16 老板拍板「取消搜索体检这个子步骤」）：体检的第二块能力**并进这里**——
    给 `execute_spec` 传 `on_step`（体检线的做法），**每个条件执行完就地读一次「共N位人选」**
    = "这个条件砍掉多少人"；搜索定稿后再读一次 = **这条关键字+这串条件到底有多少人**。
    → 于是"先报池子、再开详情"：开详情前老板就能看出这条词厚不厚（**读数进轨迹，不花 token**）。

    ⚠️ `read_pool` 可注入（单测必须传假件：默认值会真调桥读页面，见 §7-1 那次"单测驱动真浏览器"事故）。

    ⚠️ 这条能力**本来就是现成的**：`bridge-agent/agent/recipe_exec.py` 的 `execute_spec`
    （逐格设条件 → 点「搜 索」→ 等结果刷新），2026-09-15 的搜索体检已经在真猎聘上跑通
    （每一格 verify=True，人数 3000+ → 142 → 121 逐级收窄）。此前**只装在体检线、没接进采集线**，
    于是采集被设计成"条件由老板人工设好，我只读当前页"（见 read_current_page 的旧注释）。

    序列照抄 `search_rounds.run_rounds`：
      1. navigate 到找简历页；
      2. 点「清空筛选条件」——把上一条关键字的条件清干净，**保证"这一页=这一条关键字"**；
      3. `execute_spec(spec, do_search=True)`：设条件 → 点「搜 索」→ 等刷新。

    🔴 两个后果（都是老板要的）：
      · "关键字必须老板先人工搜一次"**永久消失**；
      · "**换关键字**"成立——每条关键字开跑前重搜一次，页面上的人一定属于这条关键字。

    返回 {"ok", "error", "steps", "searches", "notes", "pool", "pool_by_step"}。
    **`ok=False` 时绝不往下采**（宁可报错，不采错页）。
    """
    conds = [str(c).strip() for c in (conds or []) if str(c).strip()]
    spec = cr.stage_plan(conds, keyword, 1)          # 纯拼装，不碰浏览器
    notes: list[str] = []
    readings: list[dict] = []

    def _hook(step):
        """每个条件执行完就地读一次人数（= 这个条件砍掉多少人）。体检线 2026-09-15 的范式。"""
        auto = step.get("type") in AUTO_SEARCH_TYPES
        rd = dict(read_pool(tab))
        if not auto:
            rd["stale"] = True      # input 类不触发搜索 → 这是上一次搜索的旧状态（如实标，不冒充它的效果）
        readings.append(dict(rd, group_id=step.get("group_id"), step_type=step.get("type")))
        return rd

    nav = submit_task(BRIDGE, "navigate", {"tab_id": tab, "url": COND_URL}, source="collect-exec")
    if not nav.get("ok"):
        # ⚠️ 实测 2026-09-16 17:07：`navigate` 报"等待执行结果超时"。
        #    根因在扩展：`zNavigate` 是 `location.href = url` —— **页面一卸载，执行脚本跟着死**，
        #    回执来不及送回桥 → 桥的 in-flight 被这条任务**永久占住**（症状：之后所有动作都超时）。
        #    但**页面其实已经跳过去了**（location.href 真的被设了）→ 所以这里**不当致命**：
        #    地面真相交给下一步 `execute_spec` 的逐格 `verify`（条件设不上它会硬失败）。
        notes.append(f"navigate 没回执（{nav.get('error')}）→ 不当致命：页面多半已跳过去，"
                     f"交给 execute_spec 的逐格 verify 判定")
        print(f"  ⚠️ {notes[-1]}")
    time.sleep(WAIT_NAV)
    submit_task(BRIDGE, "click_by_text",
                {"tab_id": tab, "text": "清空筛选条件", "occurrence": 1}, source="collect-exec")
    time.sleep(WAIT_CLEAR)
    res = execute_spec(spec, tab, do_search=True, do_extract=False, on_step=_hook)
    steps = res.get("steps") or []
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or "设条件/搜索失败",
                "verify_failed": res.get("verify_failed"), "steps": steps, "notes": notes,
                "pool": None, "pool_by_step": readings}
    # ── 开工前读数（体检能力①：**先报池子，再开详情**）──────────────────────────────
    # 体检线唯一的脆点就在这条正则（页面写法一变就失效）→ 读不到就如实标"读不到"，**绝不猜**。
    pool = dict(read_pool(tab))
    if pool.get("found"):
        notes.append(f"开工前读数：关键字「{keyword}」+ 条件 {len(conds)} 条 → {pool.get('total_raw')}")
        print(f"  👥 开工前读数：{pool.get('total_raw')}（关键字「{keyword}」+ 条件 {len(conds)} 条）")
    else:
        notes.append("开工前读数：读不到「共N位人选」——可能页面还没刷新完或文本被截断，"
                     "**按'读不到'记**（不影响继续采，但不许当成'池子薄'）")
        print(f"  ⚠️ {notes[-1]}")
    return {"ok": True, "error": None, "steps": steps, "notes": notes,
            "pool": pool, "pool_by_step": readings,
            "searches": 1 + len([s for s in steps if s.get("type") in AUTO_SEARCH_TYPES])}


def already_collected(job_code: str, root: Path | None = None) -> set[str]:
    """本岗库里**已经有全文**的人（source_id 集合）→ 重跑/换词时不重复开详情（省平台查看量）。"""
    try:
        con = job_db.open_db(job_code, root=root)
        rows = con.execute("SELECT source_id FROM candidates WHERE job_code=? "
                           "AND raw_content IS NOT NULL AND raw_content<>''", (job_code,)).fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:  # noqa: BLE001
        return set()


def read_current_page(tab: int, total_timeout: float = 6.0) -> dict:
    """读**当前这一页**的卡片（不翻页、不设条件——**设条件+搜索由 `search_page` 负责**）。

    卡片走 `extract`（不截断、实测 30 行秒回）；"共N位人选"走 `snapshot` 的 body_preview，
    **超时就如实标"读不到"、绝不拖死整轮**（2026-09-16 实测：结果页 snapshot 会卡 60 秒）。
    """
    r = submit_task(BRIDGE, "extract", {"tab_id": tab, "anchor_text": ANCHOR}, source="collect-exec")
    if not r.get("ok"):
        return {"ok": False, "error": f"extract 失败：{r.get('error')}", "rows": []}
    rows = (r.get("result") or {}).get("rows") or []
    total_raw, note = "", ""
    sn = submit_task_to(BRIDGE, "snapshot", {"tab_id": tab}, "collect-exec", timeout=total_timeout)
    if sn.get("ok"):
        body = (sn.get("result") or {}).get("body_preview") or ""
        import re
        m = re.search(r"共\s*([\d,]+)\s*(\+?)\s*位人选", body)
        total_raw = m.group(0) if m else ""
    else:
        note = f"没读到「共N位人选」（snapshot {sn.get('error')}）——如实标注，不猜"
    return {"ok": True, "rows": rows, "total_raw": total_raw,
            "note": note or ("" if total_raw else "页面上没读到「共N位人选」（如实标注，不猜）")}


def turn_page(tab: int, direction: str = "next", wait_ms: int = 15000) -> dict:
    """翻一页（走扩展的 `click_paging`：**按分页结构点，不按文字**）。

    实测过为什么不能按文字：`click_by_text("下一页")` 找不到可点祖先（分页 `li` 没有
    role/tabindex/onclick/class，文字在子节点里）；`click_by_text("4")` 会点到年龄"46岁"里的 span。
    → 扩展新增 `click_paging`，优先点箭头、否则点"当前页+1"那个页码。
    返回 {ok, clicked, page_after, reason, error}；`ok=false` 就是"到头了/翻不动"，上层据此停。

    ⚠️ 2026-09-16 真跑实测修：`submit_task` 返回的是**外层信封** `{ok, result:{...}}`，
    而扩展真正的读数（`clicked/page_before/page_after/reason`）在 `result` 里。
    以前直接把信封返回 → 调用方读 `t.get("clicked")` 全是 None、
    更糟的是 `t.get("ok")` 只代表"桥这一趟通没通"（**翻不动时它也是 True**）
    → **"翻不动就停"这条最硬的停止规则实际失效**（日志里那行 `翻页：None None→None 成功`）。
    所以这里**脱一层壳**，并把 `ok` 归到扩展的真实结论上。
    """
    r = submit_task(BRIDGE, "click_paging",
                    {"tab_id": tab, "direction": direction, "wait_ms": wait_ms},
                    source="collect-exec")
    inner = r.get("result") or {}
    if not r.get("ok"):
        return {"ok": False, "clicked": None, "page_before": None, "page_after": None,
                "reason": r.get("error"), "error": r.get("error")}
    return {"ok": bool(inner.get("ok")), "clicked": inner.get("clicked"),
            "page_before": inner.get("page_before"), "page_after": inner.get("page_after"),
            "reason": inner.get("reason"), "error": inner.get("error")}


def _tab_id_of(resp: dict) -> int:
    """从 `new_tab` 的返回里取**真正的**标签页 id。

    🔴 2026-09-17 修的真 bug（老板实测：浏览器里堆了一排标签页 + 3 份"全文"是别的页面）：
      扩展 `new_tab` 给的是 `{ok:true, tab:{tab_id:N}}`（`background.js:610`），
      `bridge/server.py:129` 把扩展的返回**原样**存进 `result`，
      而老代码读的是 `result["tab_id"]`（少一层 `tab`）→ **永远取到 0**；
      扩展又把 `tab_id=0` 当"**没指定**"（`background.js:1132` 的三元判断）→ **回退读"当前激活标签页"**。
      两个后果：① 读到老板当时正在看的页面（那 3 份假"全文"就是这么来的）
                ② `finally` 里 `if new_id:` 也不成立 → **详情页从来没被关掉**（标签页越堆越多）。
    """
    r = (resp or {}).get("result") or {}
    for cand in ((r.get("tab") or {}).get("tab_id"), r.get("tab_id"), (resp or {}).get("tab_id")):
        try:
            if cand:
                return int(cand)
        except (TypeError, ValueError):
            continue
    return 0


def open_detail(tab: int, res_id: str, wait: float | None = None,
                reread_wait: float = 2.5) -> dict:
    """开一个人的详情页 → 读**整页全文**（page_text）→ **关掉这个详情页** → 切回列表页。

    返回 {ok, chars, truncated, text, url, error, wrong_page}。
    ⚠️ 开一次 = 一次"查看简历"（平台计数，**这是真代价**）。

    🔴 三条硬纪律（2026-09-17 按老板要求 + 真跑事故加的）：
      1. **必须钉住"刚开的那一个"标签页**（`new_tab` 回的 tab_id）。取不到就**失败退出**，
         绝不当成 0 往下走 —— 0 会被扩展当成"没指定"→ 读到**当前激活页**（老板当时在看的面板）。
      2. **读完就关**（`close_tab`）再切回列表 —— 老板明确要求"看一个关一个"，不许堆标签页。
      3. **读到的必须像简历**（含「简历编号」）才算成功；不像 → 如实 `ok=False` + 同一标签页再读一次，
         **绝不把别的页面的文本当简历写库**（宁可漏这一份全文，也不许污染池子）。
    另外：详情页地址还要和这个人的 `res_id` 对得上（对不上 = 钉住的页停在别处 → 同样判失败）。
    """
    url = DETAIL_URL.format(rid=res_id)
    w = OPEN_WAIT if wait is None else wait
    new_id = 0
    try:
        nt = submit_task(BRIDGE, "new_tab", {"url": url}, source="collect-exec")
        if not nt.get("ok"):
            return {"ok": False, "error": f"new_tab 失败：{nt.get('error')}", "wrong_page": False}
        new_id = _tab_id_of(nt)
        if not new_id:
            # 这一次"查看简历"其实已经花掉了 —— 但**宁可漏这份全文，也不读错页**（人按"只有卡片"入库）。
            return {"ok": False, "wrong_page": False, "url": url,
                    "error": "new_tab 没回可用的 tab_id → **不猜**（tab_id=0 会被当成'没指定'、可能读到"
                             "别的页面）：本次这份全文放弃"}
        time.sleep(w)
        sn = submit_task(BRIDGE, "snapshot", {"tab_id": new_id}, source="collect-exec")
        url_actual = (sn.get("result") or {}).get("url") or ""
        if url_actual and res_id and res_id not in url_actual:
            time.sleep(reread_wait)      # 可能还没跳完 → 再看一眼（不额外花"查看简历"）
            sn = submit_task(BRIDGE, "snapshot", {"tab_id": new_id}, source="collect-exec")
            url_actual = (sn.get("result") or {}).get("url") or ""
            if res_id not in url_actual:
                return {"ok": False, "wrong_page": True, "url": url_actual,
                        "error": f"钉住的详情页停在**别的页面**（{(url_actual or '?')[:80]}）"
                                 f"→ 判失败、不写库"}
        text, chars, truncated = "", 0, False
        for _try in range(2):             # 同一标签页最多读两次（不额外花"查看简历"）
            pt = submit_task(BRIDGE, "page_text", {"tab_id": new_id}, source="collect-exec")
            if not pt.get("ok"):
                # 桥还没重载（未知动作）→ **如实报错，不拿 3000 字冒充全文**（纪律：不假装成功）
                return {"ok": False, "wrong_page": False, "url": url_actual,
                        "error": f"page_text 不可用：{pt.get('error')}（需要重载扩展）"}
            res = pt.get("result") or {}
            text = res.get("text") or ""
            chars, truncated = res.get("chars") or len(text), bool(res.get("truncated"))
            if RESUME_MARK in text:
                break
            if _try == 0:
                time.sleep(reread_wait)   # 可能还没渲染完 → 等一会儿再读一次
        if RESUME_MARK not in text:
            return {"ok": False, "wrong_page": True, "chars": chars, "url": url_actual,
                    "error": f"读到的文本**不像简历**（没有「{RESUME_MARK}」，{chars} 字）"
                             f"→ 判失败、不写库（人仍按'只有卡片'留着）"}
        toggles = [m.group(1).strip() for m in re.finditer(TOGGLE_RE, text)][:6]
        for t in toggles:
            submit_task(BRIDGE, "click_by_text", {"tab_id": new_id, "text": t, "occurrence": 1},
                        source="collect-exec")
        if toggles:
            time.sleep(2.2)
            pt2 = submit_task(BRIDGE, "page_text", {"tab_id": new_id}, source="collect-exec")
            if pt2.get("ok"):
                t2 = (pt2.get("result") or {}).get("text") or ""
                if len(t2) > len(text):
                    text, chars = t2, len(t2)
        return {"ok": True, "chars": chars, "truncated": truncated, "text": text,
                "url": url_actual or url, "wrong_page": False}
    finally:
        # 老板口径（2026-09-17）：**看一个就关一个**（以前因 new_id=0 从没关过 → 标签页堆一排）
        if new_id:
            submit_task(BRIDGE, "close_tab", {"tab_id": new_id}, source="collect-exec")
        if tab:
            submit_task(BRIDGE, "switch_tab", {"tab_id": tab}, source="collect-exec")


def load_plan(plan_path) -> dict:
    """读小猎写的采集计划（`collect_plan_*.json`）——**它的判断就是这轮的判据来源**。"""
    p = Path(plan_path)
    if not p.exists():
        raise SystemExit(f"❌ 计划文件不存在：{p}（先让老板点「②正式采集」出计划）")
    return json.loads(p.read_text(encoding="utf-8-sig"))


def preflight_plan(plan_path, plan: dict | None = None) -> dict:
    """🔴 开工前体检（v1.11.0，本地、0 花费、0 浏览器）：**有问题就拒绝开跑**。

    为什么放进执行器（而不是留在面板）：小猎现在**一个回合内**自己写完计划就直接开跑
    （「② 正式采集」按钮），面板来不及在中间拦一道 → **最后一道闸门必须在真正开跑的那一步**。
    能力本身不是新写的（老板 2026-09-16：「取消搜索体检这个子步骤」= 把它的两块能力并进采集）：
      ① `local_checks.check_collect_spec`：关键字形态 + 条件组存不存在 + 取值在不在配方表合法档里；
      ② `local_checks.check_judge_card`：会让整轮空跑的坑（同组多值 = "同时满足" → 0 命中 /
         连写复合词 / **计划里没有 judge 判据卡** → 会退回兜底判据）。

    ⚠️ **缺判据卡 = 硬拒绝**（老板 2026-09-16 拍板）：兜底卡装的是**别的岗的行业词**，
       用它采出来的池子**不可信**（§2.9：那 28 行数据就是这么来的）——宁可跑不起来，
       也不许把一批贴错岗标签的人写进本岗库。
    ⚠️ `problems`（机械问题）拒绝开跑；`warnings`（提醒）只打印、不拦。

    返回 {"ok", "problems", "warnings", "summary", "spec", "judge"}。
    """
    p = Path(plan_path)
    spec = local_checks.check_collect_spec(p)
    judge_problems, judge_warnings = local_checks.check_judge_card(plan if plan is not None else {})
    problems = list(spec.get("problems") or []) + list(judge_problems)
    warnings = list(spec.get("warnings") or []) + list(judge_warnings)
    ok = not problems
    head = "✅ 开工前体检通过" if ok else f"❌ 开工前体检**拒绝开跑**：{len(problems)} 处问题"
    summary = f"{head}（{p.name}）"
    if problems:
        summary += "｜" + "；".join(problems)
    if warnings:
        summary += f"｜另 {len(warnings)} 处提醒"
    return {"ok": ok, "problems": problems, "warnings": warnings, "summary": summary,
            "spec": spec, "judge": {"problems": judge_problems, "warnings": judge_warnings}}


def profile_of(plan: dict, plan_path=None) -> "cr.JudgeProfile":
    """从计划里取**判据卡**。缺卡不静默：used_default=True 会一路带到 reasons/轨迹/报告里。"""
    return cr.profile_from_plan(plan or {}, source=str(plan_path or ""))


def _apply_profile(trace: dict, prof) -> None:
    """把判据卡写进轨迹（报告要能看出"这轮按哪份判据采的"）。"""
    trace["judge"] = prof.to_dict()
    if prof.used_default:
        trace["notes"].append("⚠️ **本轮用的是兜底判据**（计划里没给 judge 词表）——"
                              "排序可能不贴本岗，请让小猎在计划里补 industry/skills/role。")


def run_page(job_code: str, keyword: str, conds: list[str], page: int = 1,
             details_per_page: int = cr.DETAILS_PER_PAGE, dry_run: bool = False,
             tab: int | None = None, no_quota: bool = False,
             read_page=read_current_page, open_detail=open_detail,
             db_root: Path | None = None, open_gap: tuple = OPEN_GAP,
             profile=None) -> dict:
    """跑**一页**（可注入 read_page/open_detail，便于单测）。

    返回轨迹 dict（可直接喂 report_html.render_collect）。
    """
    started = time.time()
    trace = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "job_code": job_code,
             "keyword": keyword, "conds": conds, "details_per_page": details_per_page,
             "page": page, "dry_run": dry_run, "rounds": [], "notes": [], "tab_id": tab}
    q = None if no_quota else Quota()
    if q:
        trace["quota_before"] = q.stats()

    rec = {"n": page, "keyword": keyword, "conds": conds, "total_raw": "", "stats": {},
           "cards": [], "stop_reason": ""}
    rd = read_page(tab)
    if not rd.get("ok"):
        rec["error"] = rd.get("error")
        trace["rounds"].append(rec)
        trace["notes"].append(f"读页失败：{rd.get('error')}")
        return trace
    if rd.get("note"):
        trace["notes"].append(rd["note"])
    rec["total_raw"] = rd.get("total_raw") or ""
    rows = rd.get("rows") or []

    if profile is not None:
        _apply_profile(trace, profile)
    judged = []
    for row in rows:
        j = cr.local_judge(row.get("text") or "", job_keywords=keyword.split(), profile=profile)
        j["res_id"] = (row.get("fields") or {}).get("res_id_encode") or ""
        j["text"] = row.get("text") or ""
        judged.append(j)
    plan = cr.page_plan(judged, details_per_page=details_per_page)
    rec["stats"] = plan["stats"]
    rec["cards"] = plan["items"]

    # ── 开详情（配额内；边采边落库）──
    if not dry_run:
        con = job_db.open_db(job_code, root=db_root)
        job_db.set_job_meta(con, job_code, title=trace.get("job_title") or "")
        opened = 0
        for j in plan["items"]:
            j["action"] = j.get("action") or "skip"
            if j["action"] != "open":
                continue
            if stop_requested(started):
                trace["notes"].append(f"⛔ 人工停止：已开 {opened} 个详情，剩下 {rec['stats']['open'] - opened} 个没开")
                break
            if q and not q.check("detail"):
                trace["notes"].append("⚠ 今日查看简历额度用完 → 停止开详情")
                break
            sid = j.get("res_id") or ""
            if not sid:
                j["detail"] = {"ok": False, "error": "没有 res_id_encode，跳过"}
                continue
            d = open_detail(tab, sid)
            if d.get("ok"):
                j["detail"] = {"ok": True, "chars": d.get("chars"), "truncated": d.get("truncated"),
                               "excerpt": (d.get("text") or "")[:800]}
                _upsert(con, job_code, j, d.get("text") or "", keyword=keyword, page=page)
                opened += 1
                if q:
                    q.record("detail")
                print(f"  ✅ 开详情 {opened}/{rec['stats']['open']}：{j['card'].get('name')} "
                      f"{d.get('chars')} 字{'（截断）' if d.get('truncated') else ''}")
            else:
                j["detail"] = {"ok": False, "error": d.get("error"),
                               "wrong_page": bool(d.get("wrong_page")), "url": d.get("url")}
                # ⚠️ "读到别的页面"和"开详情失败"是两种事，分开记（前者是**错的文本**，绝不能写库）
                _tag = "🔴 读到别的页面（判失败、没写库）" if d.get("wrong_page") else "开详情失败"
                trace["notes"].append(f"{j['card'].get('name')} {_tag}：{d.get('error')}")
                print(f"  ⚠️ {_tag}：{d.get('error')}")
            time.sleep(_gap(open_gap))
        # **留卡入库**：所有没成功抓到详情的人也要进库（老板口径：采集=拿到一个池子，
        # 只是不必每个人都开详情）——本地分/命中词都落上，③匹配和老板点开都看得到。
        # ⚠️ 2026-09-16 修：第一版只落了"开详情失败"的，把"按配额自愿跳过"的漏了（单测抓到）。
        for j in plan["items"]:
            if j["action"] == "open" and (j.get("detail") or {}).get("ok"):
                continue
            _upsert(con, job_code, j, "", keyword=keyword, page=page)
        trace["db_path"] = str(job_db.db_path(job_code, root=db_root))
        trace["_con"] = con          # 自动翻页要多页共用同一个连接（见 run_auto）
    else:
        trace["notes"].append("dry-run：只做本地判分，未开详情、未写库")

    rec["elapsed_sec"] = round(time.time() - started, 1)
    trace["rounds"].append(rec)
    trace["elapsed_sec"] = round(time.time() - started, 1)
    if q:
        trace["quota_after"] = q.stats()
    return trace


def run_auto(job_code: str, keyword: str, conds: list[str], max_pages: int = UNLIMITED,
             details_per_page: int = cr.DETAILS_PER_PAGE, tab: int | None = None,
             no_quota: bool = False, read_page=read_current_page, open_detail=open_detail,
             turn_page_fn=turn_page, db_root: Path | None = None,
             total_details_cap: int = UNLIMITED, open_gap: tuple = OPEN_GAP,
             page_gap: tuple = PAGE_GAP, profile=None, dry_run: bool = False,
             already: set | None = None) -> dict:
    """**自动翻页**跑一轮关键字：逐页 读页→判分→开详情(够格就开)→写库 → 翻下一页 → 直到该停。

    停止判据（**本地规则，不调 LLM**；与老板对齐）：
      1. 翻不动 / 已到最后一页（`click_paging` 返回 no-next / not-changed）——**最硬的一条**
      2. **连续 N 个人"不值得开详情"**（`cr.tired_streak`，老板口径：往后的人都不太相关了 → 换关键字）
      3. 连续 2 页「行业命中=0」（`collect_rules.should_stop`）
      4. 翻够 `max_pages` 硬顶（🔴 死命令后默认 **0 = 不限**）；或累计开详情到 `total_details_cap`（默认 0 = 不限）
    另外：**同一页反复出现同一批人**（res_id 全见过）→ 说明翻页没生效，立即停（防死循环，**不是额度**）。

    🔴 死命令（2026-09-16）：**不设人为额度** → `max_pages/details_per_page/total_details_cap`
       默认全是 0（不限）。`details_per_page=0` 时开详情的口径变成"**够格就开**"（`cr.is_worth_opening`）。

    `already`：本岗库**已有全文**的 source_id 集合 → 这些人不重复开详情（省一次平台查看量）。
    `dry_run`：只本地判分，**不开详情、不写库**（标志在轨迹里如实记）。
    轨迹里 `rounds` = 每一页的 stats + 卡片。
    """
    started = time.time()
    already = set() if already is None else already
    trace = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "job_code": job_code,
             "keyword": keyword, "conds": conds, "mode": "auto", "max_pages": max_pages,
             "details_per_page": details_per_page, "total_details_cap": total_details_cap,
             "dry_run": bool(dry_run), "rounds": [], "notes": [], "tab_id": tab,
             "start_page": 1}
    if profile is not None:
        _apply_profile(trace, profile)
    q = None if no_quota else Quota()
    con = None
    seen: set[str] = set()
    blank_streak = 0
    total_open = 0
    page = 1
    while True:
        hard_pages = int(max_pages or 0)
        if hard_pages > 0 and page > hard_pages:
            trace["notes"].append(f"翻够硬顶 {hard_pages} 页 → 收工")
            break
        # ⛔ 人工刹车（2026-09-16 真跑实测修：**这条以前只接在 run_page 里，`--auto`/`--plan`
        #    根本不查它** → 老板点「停小猎跑腿」对这个路径完全无效，只能硬杀进程）。
        if stop_requested(started):
            trace["notes"].append(f"⛔ 人工停止：已开 {total_open} 个详情，本页不再继续")
            print(f"⛔ 人工停止（已开 {total_open} 个详情）→ 收尾")
            break
        rd = read_page(tab)
        if not rd.get("ok"):
            trace["notes"].append(f"第 {page} 页读失败：{rd.get('error')}")
            break
        if rd.get("note"):
            trace["notes"].append(f"第 {page} 页：{rd['note']}")
        rows = rd.get("rows") or []
        judged = []
        fresh = 0
        for row in rows:
            sid = (row.get("fields") or {}).get("res_id_encode") or ""
            j = cr.local_judge(row.get("text") or "", job_keywords=keyword.split(), profile=profile)
            j["res_id"], j["text"] = sid, row.get("text") or ""
            if sid and sid not in seen:
                fresh += 1
            if sid:
                seen.add(sid)
            judged.append(j)
        plan = cr.page_plan(judged, details_per_page=details_per_page)
        rec = {"n": page, "keyword": keyword, "conds": conds, "total_raw": rd.get("total_raw") or "",
               "stats": plan["stats"], "cards": plan["items"], "stop_reason": "",
               "fresh": fresh, "elapsed_sec": None}
        st = plan["stats"]
        blank_streak = blank_streak + 1 if st.get("industry", 0) == 0 else 0
        # 🔴 老板口径：连续遇到"不值得开详情"的人 → 以后的人都不太相关了 → 换关键字
        tired, tired_run = cr.tired_streak(judged, need=cr.TIRED_STREAK)
        print(f"▶ 第 {page} 页：卡片 {st['n']}｜行业 {st['industry']}｜够格 {st.get('worthy')}"
              f"｜开详情 {st['open']}（累计 {total_open}）｜新人 {fresh}")

        # 开详情 + 写库（开成功的带全文，其余留卡）
        if dry_run:
            trace["notes"].append("dry-run：只做本地判分，未开详情、未写库")
        else:
            if con is None:
                con = job_db.open_db(job_code, root=db_root)
            opened = 0
            for j in plan["items"]:
                if j.get("action") != "open":
                    continue
                cap = int(total_details_cap or 0)
                if cap > 0 and total_open >= cap:
                    trace["notes"].append(f"累计开详情到上限 {cap} → 不再开")
                    break
                # ⛔ 人工刹车：**每个详情之间**查一次 → 老板点停后最多再开完当前这一个
                if stop_requested(started):
                    trace["notes"].append(f"⛔ 人工停止：已开 {total_open} 个详情，本页剩下的没开")
                    print(f"⛔ 人工停止（已开 {total_open} 个）→ 本页剩下的没开")
                    break
                if q and not q.check("detail"):
                    trace["notes"].append("⚠ 今日查看简历额度用完 → 停止开详情")
                    break
                sid = j.get("res_id") or ""
                if not sid:
                    continue
                if sid in already:
                    j["detail"] = {"ok": False, "skip_reason": "already-collected",
                                   "error": "本岗库里已有本人全文 → 不重复开（省一次查看量）"}
                    trace["notes"].append(f"{j['card'].get('name')} 已有全文 → 跳过开详情")
                    continue
                d = open_detail(tab, sid)
                if d.get("ok"):
                    j["detail"] = {"ok": True, "chars": d.get("chars"), "truncated": d.get("truncated"),
                                   "excerpt": (d.get("text") or "")[:800]}
                    _upsert(con, job_code, j, d.get("text") or "", keyword=keyword, page=page)
                    already.add(sid)          # 同一次跑里也别重复开
                    opened += 1
                    total_open += 1
                    if q:
                        q.record("detail")
                    print(f"  ✅ 开详情 {j['card'].get('name')} {d.get('chars')} 字（累计 {total_open}）")
                else:
                    j["detail"] = {"ok": False, "error": d.get("error")}
                    trace["notes"].append(f"{j['card'].get('name')} 开详情失败：{d.get('error')}")
                time.sleep(_gap(open_gap))
            for j in plan["items"]:
                if j.get("action") == "open" and (j.get("detail") or {}).get("ok"):
                    continue
                _upsert(con, job_code, j, "", keyword=keyword, page=page)
        trace["rounds"].append(rec)

        # 该停了吗？
        stop, why = cr.should_stop(st, blank_streak, max_pages=max_pages, pages_done=page)
        if tired and not stop:
            stop, why = True, f"连续 {tired_run} 个不值得开详情（这词往后没对口的人了）→ 换关键字"
        if not stop and st.get("n", 0) > 0 and fresh == 0:
            stop, why = True, "这一页没有新人（翻页可能没生效，防死循环）"
        if stop:
            rec["stop_reason"] = why
            print(f"⏹ 停：{why}")
            break

        t = turn_page_fn(tab)
        trace["notes"].append(f"翻页 → {t.get('clicked') or '?'} "
                              f"page {t.get('page_before')}→{t.get('page_after')} "
                              f"{'ok' if t.get('ok') else '失败:' + str(t.get('reason') or t.get('error'))}")
        print(f"  ➡ 翻页：{t.get('clicked')} {t.get('page_before')}→{t.get('page_after')} "
              f"{'成功' if t.get('ok') else '失败（' + str(t.get('reason') or t.get('error')) + '）'}")
        if not t.get("ok"):
            rec["stop_reason"] = f"翻不动了（{t.get('reason') or t.get('error')}）→ 这一轮到此"
            break
        page += 1
        time.sleep(_gap(page_gap))

    trace["pages_done"] = page if trace["rounds"] and trace["rounds"][-1].get("stop_reason") else max(0, page - 1)
    trace["total_opened"] = total_open
    if con is not None:
        trace["db_path"] = str(job_db.db_path(job_code, root=db_root))
    trace["elapsed_sec"] = round(time.time() - started, 1)
    if q:
        trace["quota_after"] = q.stats()
    return trace


def run_plan(plan: dict, keywords: list[str] | None = None, conds: list[str] | None = None,
             max_pages: int = UNLIMITED, details_per_page: int = cr.DETAILS_PER_PAGE,
             total_details_cap: int = UNLIMITED, tab: int | None = None, no_quota: bool = False,
             db_root: Path | None = None, plan_path=None, read_page=read_current_page,
             open_detail=open_detail, turn_page_fn=turn_page, dry_run: bool = False,
             do_search: bool = True, search_fn=search_page, page_gap: tuple = PAGE_GAP,
             job_code: str | None = None) -> dict:
    """按**小猎的计划**把关键字一条条跑完——**每条关键字自己搜、自己翻页、采到该停**。

    🔴 v1.10.0（2026-09-16 老板重定方向）：**"关键字必须老板先人工搜一次"永久消失**。
      每条关键字开跑前，脚本自己 `search_page`（navigate → 清空筛选 → 设条件 → 点搜索），
      然后才进"逐页判分 → 够格就开详情 → 入库 → 翻页"的循环 →
      **"换关键字"由此成立**：页面上的人一定属于这一条关键字。

    `do_search=False`：退化成老行为（用老板已经搜好的那一页），只跑第一条关键字一遍，
      给"手工搜一次、只想采这一页"的场合用。
    `dry_run=True`：只本地判分，不开详情、不写库（标志如实记进轨迹）。
    每条关键字之间保持 8-20 秒真人节奏，并做**同一条关键字不重复跑**的去重。
    """
    # ⚠️ 2026-09-16 真跑实测修（**数据写错岗**）：以前这里用 `plan.get("job_code")`，
    #   而小猎写的计划**常常没有 job_code 字段** → 变成空串 → `data/chat//job.db` =
    #   **`data/chat/job.db`**：61 份全文全写进了一个没有岗位的野库，而 `--job-code` 只被用来打印。
    #   现在：**job_code 必须显式给**（main 已经把 `--job-code` 解析好传进来），
    #   缺了就**直接报错**——宁可跑不起来，也不许把数据写到不知道哪个岗里去。
    jc = str(job_code or plan.get("job_code") or "").strip()
    if not jc:
        raise ValueError("run_plan: 缺 job_code（计划里没有、调用方也没给）——"
                         "缺它会把采集结果写进 data/chat/job.db 这种没有岗位的野库，宁可报错")
    started = time.time()
    prof = profile_of(plan, plan_path)
    kws = [str(k).strip() for k in (keywords or plan.get("keywords") or []) if str(k).strip()]
    cs = [str(c).strip() for c in (conds if conds is not None else (plan.get("conds") or [])) if str(c).strip()]
    trace = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "job_code": jc, "mode": ("plan" if do_search else "plan-manual-search"),
             "plan_file": str(plan_path or ""), "keywords": kws, "conds": cs,
             "max_pages": max_pages, "details_per_page": details_per_page,
             "total_details_cap": total_details_cap, "dry_run": bool(dry_run),
             "do_search": bool(do_search), "rounds": [], "notes": [], "tab_id": tab,
             "keyword_runs": [], "searches": []}
    _apply_profile(trace, prof)
    if not kws:
        trace["notes"].append("计划里没有关键字 → 没得跑")
        return trace
    # 本岗库里已有全文的人 → 重跑/换词时不重复开详情
    already = set() if dry_run else already_collected(jc, root=db_root)
    if already:
        trace["notes"].append(f"本岗库已有全文 {len(already)} 人 → 不重复开详情（省查看量）")
    seen_kw: set[str] = set()
    for kw in kws:
        if stop_requested(started):
            trace["notes"].append("⛔ 人工停止（老板点了「停小猎跑腿」）→ 不再开新关键字")
            print("⛔ 人工停止 → 不再开新关键字")
            break
        if kw in seen_kw:
            trace["notes"].append(f"关键字「{kw}」重复，跳过")
            continue
        seen_kw.add(kw)
        print(f"\n===== 关键字「{kw}」 =====")
        if do_search:
            print(f"  🔎 自己设条件并搜索：关键字「{kw}」｜条件 {cs or '（无）'}")
            sr = search_fn(tab, kw, cs)
            trace["searches"].append({"keyword": kw, "conds": cs, "ok": bool(sr.get("ok")),
                                      "error": sr.get("error"),
                                      "verify_failed": sr.get("verify_failed"),
                                      "notes": sr.get("notes") or [],
                                      "steps": sr.get("steps") or [],
                                      # v1.11.0：开工前读数（池子厚薄 + 每个条件砍掉多少人）——体检能力并进采集
                                      "pool": sr.get("pool"),
                                      "pool_by_step": sr.get("pool_by_step") or [],
                                      "searches": sr.get("searches") or 0})
            trace["notes"].extend([f"[{kw}] {x}" for x in (sr.get("notes") or [])])
            if not sr.get("ok"):
                # **绝不采错页**：没搜成就不读不采（宁可这一条空着，也不把别人的页当自己的）
                trace["notes"].append(f"关键字「{kw}」自己搜失败 → **跳过不采**（不采错页）：{sr.get('error')}")
                print(f"  ❌ 搜失败 → 跳过（不采错页）：{sr.get('error')}")
                trace["keyword_runs"].append({"keyword": kw, "pages": 0, "opened": 0,
                                              "elapsed_sec": 0, "search_failed": True,
                                              "error": sr.get("error")})
                continue
            time.sleep(_gap(page_gap))
        sub = run_auto(jc, kw, cs, max_pages=max_pages,
                       details_per_page=details_per_page, tab=tab, no_quota=no_quota,
                       read_page=read_page, open_detail=open_detail, turn_page_fn=turn_page_fn,
                       db_root=db_root, total_details_cap=total_details_cap, profile=prof,
                       dry_run=dry_run, already=already, page_gap=page_gap)
        trace["rounds"].extend(sub.get("rounds") or [])
        trace["notes"].extend([f"[{kw}] {x}" for x in (sub.get("notes") or [])])
        trace["keyword_runs"].append({"keyword": kw, "pages": len(sub.get("rounds") or []),
                                      "opened": sub.get("total_opened", 0),
                                      "elapsed_sec": sub.get("elapsed_sec")})
        if sub.get("db_path"):
            trace["db_path"] = sub["db_path"]
        trace["job_code"] = jc
        trace["total_opened"] = trace.get("total_opened", 0) + sub.get("total_opened", 0)
        time.sleep(_gap(page_gap))
    trace["elapsed_sec"] = round(sum((r.get("elapsed_sec") or 0) for r in (trace.get("rounds") or [])), 1)
    return trace


def _gap(rng: tuple[float, float]) -> float:
    import random
    return random.uniform(*rng)


def _upsert(con, job_code: str, j: dict, raw_text: str, keyword: str = "", page: int = 1) -> dict:
    """把一个人写进本岗库（**边采边落盘**；同一人第二次采到 = updated）。"""
    c = j.get("card") or {}
    hits = list(j.get("industry_hits") or []) + list(j.get("skill_hits") or [])
    cur_job = (c.get("jobs") or [{}])[0]
    return job_db.upsert_candidate(con, job_code, {
        "source_id": j.get("res_id") or "",
        "source_url": job_db_detail_url(j.get("res_id") or ""),
        "raw_content": raw_text or "",
        "summary_text": j.get("text") or "",
        "display_name": c.get("name") or "",
        "display_company": cur_job.get("org") or "",
        "display_position": cur_job.get("role") or "",
        "active_badge": c.get("activity") or "",
        "structured": {"city": c.get("city"), "education": c.get("education"),
                       "edu_tongzhao": c.get("edu_tongzhao"), "years": c.get("years"),
                       "age": c.get("age"), "expect_city": c.get("expect_city"),
                       "expect_position": c.get("expect_position"),
                       "jobs": c.get("jobs"), "schools": c.get("schools"),
                       "skills": c.get("skills"), "resume_flags": j.get("resume_flags")},
        "local_score": j.get("score"),
        "local_hits": hits,
        "round_tag": f"{keyword}#p{page}",
        "status": ("opened" if (j.get("detail") or {}).get("ok") else
                   ("dropped" if j.get("decision") == "drop" else "kept")),
    })


def job_db_detail_url(res_id: str) -> str:
    return DETAIL_URL.format(rid=res_id) if res_id else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-code", required=True)
    ap.add_argument("--keyword", default=None, help="单个关键字（不给 --plan 时必填）")
    ap.add_argument("--plan", default=None,
                    help="小猎写的 collect_plan_*.json：从中取 判据卡 + 条件 + 全部关键字（推荐）")
    ap.add_argument("--all-keywords", action="store_true",
                    help="配合 --plan：把计划里的关键字**一条条全跑完**（否则只跑 --keyword 那条）")
    ap.add_argument("--conds", action="append", default=None, help="group_id=value，可多次")
    ap.add_argument("--page", type=int, default=1, help="当前是第几页（**只为标注**；翻页自动）")
    ap.add_argument("--details", type=int, default=cr.DETAILS_PER_PAGE,
                    help="一页最多开几个详情；**默认 0 = 不限（够格就开）**（🔴 死命令：测试期不设人为额度）")
    ap.add_argument("--tab-id", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="只本地判分，**不开详情、不写库**（--plan / --auto 路径同样生效）")
    ap.add_argument("--no-search", action="store_true",
                    help="**不做「自己搜」**：直接用老板已经搜好的当前页（老行为；配合 --plan 只跑第一条）")
    ap.add_argument("--no-quota", action="store_true")
    ap.add_argument("--auto", action="store_true",
                    help="自动翻页（走扩展 click_paging）：逐页采到「该停」为止（默认关=只跑当前这一页）")
    ap.add_argument("--max-pages", type=int, default=UNLIMITED,
                    help="翻页硬顶；**默认 0 = 不限**（🔴 死命令：它只是防失控，不是额度）")
    ap.add_argument("--total-details", type=int, default=UNLIMITED,
                    help="一轮累计开详情的保险丝；**默认 0 = 不限**（🔴 死命令）")
    ap.add_argument("--out", default=None, help="轨迹 JSON 输出（默认落本岗 reports）")
    args = ap.parse_args()

    if not args.plan and not args.keyword:
        raise SystemExit("❌ 要么给 --plan（推荐，按小猎的计划跑），要么给 --keyword")
    tab = args.tab_id or find_liepin_tab()
    if args.plan:
        plan = load_plan(args.plan)
        jc = args.job_code or plan.get("job_code") or ""
        if not jc:
            raise SystemExit("❌ 计划里没有 job_code，命令行也没给 --job-code")
        kws = ([args.keyword] if (args.keyword and not args.all_keywords)
               else [str(k) for k in (plan.get("keywords") or []) if str(k).strip()])
        print(f"▶ 按计划跑：{args.plan}")
        print(f"  岗位 {jc}｜关键字 {len(kws)} 条：{kws}")
        print(f"  条件 {plan.get('conds') or '（无）'}｜翻页硬顶 {args.max_pages or '不限'}"
              f"｜每页详情 {args.details or '不限（够格就开）'}｜累计详情 {args.total_details or '不限'}"
              f"｜{'自己搜' if not args.no_search else '用当前页(不搜)'}"
              f"｜{'dry-run' if args.dry_run else '真跑'}")
        # ── 🔴 开工前体检（v1.11.0）：有问题**拒绝开跑**，绝不"先跑起来再说" ──────────────
        # 起因：老板拍板取消「搜索体检/采集计划」两个子步骤后，小猎是**一个回合内**自己写完
        # 计划就直接开跑 → 面板来不及在中间拦一道，所以闸门必须在**真正开跑这一步**。
        pf = preflight_plan(args.plan, plan)
        print(("✅ " if pf["ok"] else "❌ ") + pf["summary"])
        for _x in pf["problems"]:
            print(f"  ❌ {_x}")
        for _x in pf["warnings"]:
            print(f"  ⚠️ {_x}")
        if not pf["ok"]:
            print("\n❌ 开工前体检没过 → **拒绝开跑**（一个字都没采、一个人都没开）。")
            print("   把上面每条问题改掉再跑（改计划文件或让老板点「🔄 重新出采集计划」）。")
            raise SystemExit(2)
        trace = run_plan(plan, keywords=kws, conds=plan.get("conds") or [],
                         max_pages=args.max_pages, details_per_page=args.details,
                         total_details_cap=args.total_details, tab=tab,
                         no_quota=args.no_quota, plan_path=args.plan,
                         dry_run=args.dry_run, do_search=not args.no_search,
                         job_code=jc)   # ⚠️ 必须传：计划里可能没有 job_code（实测踩到）
        args.job_code = jc
    else:
        mode = "自动翻页" if args.auto else "只跑当前页"
        print(f"▶ 岗位 {args.job_code}｜关键字「{args.keyword}」｜条件 {args.conds or '（无）'}"
              f"｜{mode}｜每页详情 {args.details or '不限（够格就开）'}"
              f"｜{'dry-run' if args.dry_run else '真跑'}")
        if args.auto:
            trace = run_auto(args.job_code, args.keyword, args.conds or [], max_pages=args.max_pages,
                             details_per_page=args.details, tab=tab, no_quota=args.no_quota,
                             total_details_cap=args.total_details, dry_run=args.dry_run)
        else:
            trace = run_page(args.job_code, args.keyword, args.conds or [], page=args.page,
                             details_per_page=args.details, dry_run=args.dry_run, tab=tab,
                             no_quota=args.no_quota)
    trace.pop("_con", None)   # 连接对象不能进 JSON

    reports = CHAT / args.job_code / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else reports / f"collect_{now_ts()}.json"
    trace["out_file"] = out.as_posix()
    out.write_text(json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 轨迹：{out.as_posix()}")

    # ── 本地渲染过程报告（0 token）──
    try:
        import report_html
        st = (trace.get("rounds") or [{}])[0].get("stats") or {}
        html = report_html.render_collect(args.job_code, trace,
                                         {"job_code": args.job_code, "json_name": out.name})
        hp = out.with_name(out.stem + "_过程.html")
        hp.write_text(html, encoding="utf-8")
        print(f"✅ 采集报告：{hp.as_posix()}")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 本地渲染失败（不影响数据）：{e}")

    st = (trace.get("rounds") or [{}])[0].get("stats") or {}
    print(f"\n本页：卡片 {st.get('n')}｜行业命中 {st.get('industry')}｜够格 {st.get('worthy')}"
          f"｜开详情 {st.get('open')}｜留卡 {st.get('skip')}｜平均分 {st.get('avg_score')}"
          + ("（dry-run，未写库）" if args.dry_run else f"｜库：{trace.get('db_path')}"))


if __name__ == "__main__":
    main()
