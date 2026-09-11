#!/usr/bin/env python3
"""report_html.py — 本地 HTML 报告渲染器（数据/展示分离：LLM 只产结构化 JSON，页面由本地模板渲染）

背景（2026-09-05 老板拍板方向）：
- 产物是资产、UI 是壳。结构化 JSON（pool_report / collected / 将来的打招呼数据）= 资产；
  HTML 只是随时可由本地代码重新生成的展示层——换壳（弃 Streamlit / 上桌面）不废。
- 参考老实现：岗位招聘单机版 services/report_generator.py（Python f-string）、
  wails internal/report/report.go（Go html/template）。
- 避免让 LLM 手写整份 HTML（大输出 → 截断风险、费 token、不可控）；HTML 渲染零 token、确定性、永不断流。

用法：
  python report_html.py --report data/chat/<job>/reports/pool_report_*.json \
      --collect data/chat/<job>/reports/collected_*.json \
      --out data/chat/<job>/reports/候选人匹配_<ts>.html \
      [--title "岗位名"] [--group none|verdict|city]

输入数据格式（与 m2_eval_run / 面板③ 输出一致）：
  pool_report = {"pool_quality": {"pool_quality": "中", "match_distribution": {...}, "main_gaps": [...],
                 "strengths": [...], "recommendation": "...", "data_valid": ..., "data_valid_message": "..."},
                 "candidates": [{"candidate_id": 1, "score": 0-100, "verdict": "推荐/待定/不推荐",
                                 "match_points": [...], "concerns": [...], "summary": "..."}]}
  collected  = {"rows": [{"fields": {"res_id_encode": "..."}, "text": "..."}]}（rows 数组顺序 = candidate_id 1..N）

将来扩展：若候选人 dict 带 话术1/话术2/先核实/概况（④ 打招呼数据），卡片自动加话术区；无需改渲染逻辑。
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DETAIL_URL = "https://h.liepin.com/resume/showresumedetail/?res_id_encode={rid}"

VERDICT_META = {
    "推荐": {"cls": "rec", "label": "✅ 推荐"},
    "待定": {"cls": "hold", "label": "🟡 待定"},
    "不推荐": {"cls": "no", "label": "🔴 不推荐"},
}


def esc(x) -> str:
    return html.escape(str(x or ""), quote=True)


def parse_collected(path: Path) -> list[dict]:
    """读 collected JSON，返回与 candidate_id 对齐的行列表（rows 顺序 1..N）。"""
    if not path or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return (data.get("rows") or []) if isinstance(data, dict) else []


def best_name(row: dict) -> str:
    """尽力从 raw text 里抠姓名（掩码如 张**）；抠不到就返回空。"""
    text = (row.get("text") or "") if isinstance(row, dict) else ""
    for line in text.split("\n"):
        s = line.strip()
        if "**" in s and len(s) <= 12 and not s.startswith(("工作", "硕士", "本科", "博士")):
            return s
    return ""


def detail_link(row: dict) -> str:
    fields = (row.get("fields") or {}) if isinstance(row, dict) else {}
    rid = fields.get("res_id_encode") or row.get("res_id_encode") or row.get("source_id")
    return DETAIL_URL.format(rid=rid) if rid else None


def text_snippet(row: dict, limit: int = 300) -> str:
    t = ((row.get("text") or "") if isinstance(row, dict) else "").strip()
    if not t:
        return ""
    return t if len(t) <= limit else t[:limit] + "…"


# ── 发岗助手渲染（v1.6.8：📋 生成发岗文字 → 逐格复制到猎聘发岗表单）─────────
# 输入与 data/prompts/publish_manual.txt 的 JSON 契约一致：
#   {company_name, job_title_original, job_title_normalized, city, salary_original,
#    salary_benefits, work_years, education, headcount,
#    responsibilities[], requirements[], priority_notes[], compliance_issues[]}
#   可选 salary_converted（本地换算，如 "50-120万/18薪" → "42-100K·18薪"）
# 展示按猎聘发岗表单的格子排：每格一个可编辑输入框 + 「复制此格」按钮；职位描述本地拼。

PUB_FIELD_DEFS = [
    ("company_name", "1️⃣ 招聘企业", False),
    ("job_title_normalized", "2️⃣ 职位名称", True),   # 显示原始名对照
    ("city", "3️⃣ 工作城市", False),
    ("salary_display", "4️⃣ 职位薪资", False),         # 显示换算后 + 原始
    ("salary_benefits", "5️⃣ 薪资福利", False),
    ("work_years", "6️⃣ 工作年限", False),
    ("education", "7️⃣ 学历要求", False),
    ("headcount", "8️⃣ 招聘人数", False),
    ("job_description", "9️⃣ 职位描述（岗位职责/任职要求/优先考虑）", False),
]


def _pub_field_value(pub: dict, key: str) -> str:
    """渲染值：本地换算/拼装优先，LLM 原始字段兜底。"""
    if key == "salary_display":
        conv = (pub.get("salary_converted") or {}).get("converted") if isinstance(pub.get("salary_converted"), dict) else None
        return conv or (pub.get("salary_original") or "")
    if key == "job_description":
        parts = []
        resp = pub.get("responsibilities") or []
        if resp:
            parts.append("【岗位职责】")
            parts.append("\n".join(f"{i}. {x}" for i, x in enumerate(resp, 1)))
        req = pub.get("requirements") or []
        if req:
            parts.append("【任职要求】")
            parts.append("\n".join(f"• {x}" for x in req))
        pri = pub.get("priority_notes") or []
        if pri:
            parts.append("【优先考虑】")
            parts.append("\n".join(f"• {x}" for x in pri))
        return "\n\n".join(parts)
    v = pub.get(key)
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    return str(v or "")


def _pub_orig(pub: dict, key: str) -> str:
    """原始值对照（职位名称/薪资 显示 LLM 提取的原文，供老板核对）。"""
    if key == "job_title_normalized":
        o = pub.get("job_title_original")
        n = pub.get("job_title_normalized")
        return f"📌 原始：{o}" if o and o != n else ""
    if key == "salary_display":
        s = pub.get("salary_original")
        conv = pub.get("salary_converted") if isinstance(pub.get("salary_converted"), dict) else None
        if s and conv and conv.get("converted"):
            return f"📌 换算：{s} / {conv.get('months', 12)}薪 → {conv.get('converted')}"
        return f"📌 原始：{s}" if s else ""
    return ""


def render_publish(job_title: str, pub: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    comp = (pub.get("compliance_issues") or [])
    warn = ""
    if comp:
        items = "".join(f"<li>{esc(x)}</li>" for x in comp)
        warn = (f'<div class="pub-warn"><b>⚠️ 已自动过滤以下不合规内容（发岗前请知悉）</b>'
                f'<ul>{items}</ul></div>')

    rows = []
    for key, label, _show_orig in PUB_FIELD_DEFS:
        val = _pub_field_value(pub, key)
        orig = _pub_orig(pub, key)
        rows.append(f"""<div class="pub-row" data-key="{esc(key)}">
      <div class="pub-head"><span class="pub-label">{esc(label)}</span>
        <span class="pub-btns"><button class="pub-copy" data-key="{esc(key)}">📋 复制此格</button></span></div>
      <textarea class="pub-input" data-key="{esc(key)}" rows="{6 if key == 'job_description' else 2}" ondblclick="this.select()">{esc(val)}</textarea>
      {f'<div class="pub-orig">{esc(orig)}</div>' if orig else ''}
    </div>""")
    rows_html = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(job_title)} · 发岗助手</title>
<style>
  body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f2f4f8;margin:0;padding:20px;color:#1f2937;}}
  .wrap{{max-width:760px;margin:0 auto;}}
  h1{{font-size:20px;margin:0 0 2px;}}
  .meta{{color:#6b7280;font-size:12px;margin-bottom:14px;}}
  .tip{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:8px 12px;font-size:13px;margin-bottom:12px;}}
  .pub-warn{{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:8px 12px;font-size:13px;margin-bottom:12px;}}
  .pub-warn ul{{margin:4px 0 0 20px;padding:0;}} .pub-warn li{{color:#92400e;}}
  .pub-row{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px 14px;margin-bottom:10px;}}
  .pub-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;}}
  .pub-label{{font-weight:600;font-size:14px;}}
  .pub-copy{{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:4px 12px;cursor:pointer;font-size:12px;}}
  .pub-copy:hover{{background:#1d4ed8;}}
  .pub-input{{width:100%;box-sizing:border-box;border:1px solid #d1d5db;border-radius:8px;padding:6px 10px;font-size:14px;font-family:inherit;resize:vertical;}}
  .pub-input:focus{{outline:2px solid #bfdbfe;border-color:#3b82f6;}}
  .pub-orig{{color:#9ca3af;font-size:12px;margin-top:4px;}}
  .bar{{display:flex;gap:10px;margin-bottom:16px;}}
  .bar button{{flex:1;padding:8px 0;border-radius:8px;font-size:13px;cursor:pointer;border:0;}}
  .btn-copy-all{{background:#10b981;color:#fff;}}
  .btn-copy-all:hover{{background:#059669;}}
  .footer{{text-align:center;margin-top:16px;color:#9ca3af;font-size:12px;}}
</style>
</head>
<body>
<div class="wrap">
  <h1>📤 {esc(job_title)} · 发岗助手</h1>
  <div class="meta">本地渲染（LLM 只产字段 JSON，本页可随时重生）· 生成 {esc(now)}</div>
  <div class="tip">💡 打开猎聘「发布职位」页与此页并排：逐格点「复制此格」→ 粘贴到对应输入框；职位描述整段复制到正文框。若某格复制失败，双击输入框可全选，再按 Ctrl+C。</div>
  {warn}
  <div class="bar">
    <button class="btn-copy-all" id="copyAll">📋 一键复制全部字段（带标签）</button>
  </div>
  {rows_html}
  <div class="footer">小猎工作台产物 · 数据资产在 reports/publish_*.json，本页可随时重新生成</div>
</div>
<script>
  function g(k){{ var el = document.querySelector('textarea[data-key="'+k+'"]'); return el ? el.value : ''; }}
  async function copy(t, msg) {{
    var ok = false;
    try {{ await navigator.clipboard.writeText(t); ok = true; }} catch(e) {{
      var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta);
      ta.select(); try {{ ok = document.execCommand('copy'); }} catch(_) {{ ok = false; }}
      document.body.removeChild(ta);
    }}
    var tip = document.createElement('div');
    tip.textContent = ok ? '✅ 已复制' : '❌ 复制失败：请双击输入框全选 → Ctrl+C';
    tip.style.cssText = 'position:fixed;top:16px;right:16px;background:' + (ok ? '#10b981' : '#dc2626') +
      ';color:#fff;padding:6px 14px;border-radius:8px;z-index:99;max-width:70vw;';
    document.body.appendChild(tip); setTimeout(function(){{ tip.remove(); }}, ok ? 1200 : 4000);
  }}
  document.querySelectorAll('.pub-copy').forEach(function(btn){{
    btn.addEventListener('click', function(){{ var k = btn.getAttribute('data-key'); copy(g(k), btn); }});
  }});
  document.getElementById('copyAll').addEventListener('click', function(){{
    var keys = {json.dumps([d[0] for d in PUB_FIELD_DEFS], ensure_ascii=False)};
    var labels = {json.dumps({d[0]: d[1] for d in PUB_FIELD_DEFS}, ensure_ascii=False)};
    var parts = [];
    keys.forEach(function(k){{ var v = g(k); parts.push(labels[k] + '：' + (v || '未提供')); }});
    copy(parts.join('\\n'), this);
  }});
</script>
</body>
</html>"""


def render(job_title: str, pool: dict, candidates: list[dict],
           collected_rows: list[dict], group: str = "none") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(candidates)
    n_rec = sum(1 for c in candidates if c.get("verdict") == "推荐")
    n_hold = sum(1 for c in candidates if c.get("verdict") == "待定")
    n_no = sum(1 for c in candidates if c.get("verdict") == "不推荐")

    # 池评区（pool_quality 可能是 dict，也可能是旧格式字符串）
    pq = pool.get("pool_quality") if isinstance(pool, dict) else pool
    pq_html = ""
    if isinstance(pq, dict):
        chips = []
        for k in ("pool_quality", "recommendation"):
            if pq.get(k):
                chips.append(f'<span class="chip">{esc(pq[k])}</span>')
        dist = pq.get("match_distribution") or {}
        dist_txt = " / ".join(f"{k} {v}" for k, v in dist.items() if k in ("high", "medium", "low", "total"))
        if dist_txt:
            chips.append(f'<span class="chip">分布 {esc(dist_txt)}</span>')
        dv = pq.get("data_valid")
        if dv is not None:
            dv_cls = "ok" if dv else "warn"
            dv_txt = "data_valid ✅通过" if dv else "data_valid ⚠️异常"
            chips.append(f'<span class="chip {dv_cls}">{esc(dv_txt)}</span>')
        lists = ""
        if pq.get("main_gaps"):
            lists += '<div class="kv"><b>主要缺口：</b><ul class="red">' + "".join(f"<li>{esc(x)}</li>" for x in pq["main_gaps"]) + "</ul></div>"
        if pq.get("strengths"):
            lists += '<div class="kv"><b>优势：</b><ul class="green">' + "".join(f"<li>{esc(x)}</li>" for x in pq["strengths"]) + "</ul></div>"
        if pq.get("data_valid_message"):
            lists += f'<div class="kv"><b>数据校验：</b>{esc(pq["data_valid_message"])}</div>'
        pq_html = f'<div class="poolbox"><div class="poolchips">{"".join(chips)}</div>{lists}</div>'
    elif pq:
        pq_html = f'<div class="poolbox"><span class="chip">{esc(pq)}</span></div>'

    # 候选人卡片
    cards = []
    for idx, c in enumerate(sorted(candidates, key=lambda x: -int(x.get("score") or 0)), 1):
        cid = c.get("candidate_id")
        row = collected_rows[cid - 1] if collected_rows and 0 < cid <= len(collected_rows) else {}
        verdict = c.get("verdict") or ""
        meta = VERDICT_META.get(verdict, {"cls": "no", "label": esc(verdict)})
        score = c.get("score")
        try:
            sc = int(score)
            sc_cls = "high" if sc >= 80 else ("mid" if sc >= 60 else "low")
        except (TypeError, ValueError):
            sc, sc_cls = score, "low"
        name = best_name(row) or f"候选人 #{cid}"
        link = detail_link(row)
        link_html = f'<a class="btn" href="{esc(link)}" target="_blank" rel="noopener">🔗 猎聘直达（新标签）</a>' if link else ""
        points = "".join(f"<li>{esc(p)}</li>" for p in (c.get("match_points") or [])) if c.get("match_points") else ""
        concerns = "".join(f"<li>{esc(x)}</li>" for x in (c.get("concerns") or [])) if c.get("concerns") else ""
        greet = ""
        if c.get("概况") or c.get("话术1") or c.get("话术2") or c.get("先核实"):
            g1 = f'<div class="g-item"><span class="g-label">话术1 · 岗位亮点</span>{esc(c.get("话术1"))}</div>' if c.get("话术1") else ""
            g2 = f'<div class="g-item"><span class="g-label">话术2 · 匹配理由</span>{esc(c.get("话术2"))}</div>' if c.get("话术2") else ""
            gv = f'<div class="g-item"><span class="g-label">概况</span>{esc(c.get("概况"))}</div>' if c.get("概况") else ""
            gc = f'<div class="g-item"><span class="g-label">先核实</span>{esc(c.get("先核实"))}</div>' if c.get("先核实") else ""
            greet = f'<div class="greeting">{gv}{gc}{g1}{g2}</div>'
        snippet = text_snippet(row)
        det = f"<details class='snippet'><summary>列表摘要（展开）</summary><pre>{esc(snippet)}</pre></details>" if snippet else ""
        cards.append(f"""
    <div class="candidate v-{meta['cls']}" data-v="{esc(verdict)}">
      <div class="chead">
        <span class="score {sc_cls}">{esc(sc)}</span>
        <span class="vtag {meta['cls']}">{meta['label']}</span>
        <span class="cname">{esc(name)}</span>
        <span class="cid">#{esc(cid)}</span>
        {link_html}
      </div>
      <div class="summ">{esc(c.get('summary'))}</div>
      {('<div class="points"><b>✅ 匹配点</b><ul>' + points + '</ul></div>') if points else ''}
      {('<div class="concerns"><b>⚠️ 疑虑点</b><ul>' + concerns + '</ul></div>') if concerns else ''}
      {greet}
      {det}
    </div>""")
    cards_html = "".join(cards)

    body_g = ""
    if group == "verdict":
        body_g = ('<div class="filters"><button class="f active" data-f="all">全部</button>'
                  '<button class="f" data-f="推荐">推荐</button>'
                  '<button class="f" data-f="待定">待定</button>'
                  '<button class="f" data-f="不推荐">不推荐</button></div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(job_title)} · 匹配报告</title>
<style>
  body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f2f4f8;margin:0;padding:20px;color:#1f2937;}}
  .wrap{{max-width:1000px;margin:0 auto;}}
  h1{{font-size:20px;margin:0 0 2px;}}
  .meta{{color:#6b7280;font-size:12px;margin-bottom:14px;}}
  .poolbox{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px;margin-bottom:14px;}}
  .poolchips .chip{{display:inline-block;background:#eef2ff;border:1px solid #c7d2fe;border-radius:999px;padding:2px 10px;font-size:12px;margin:2px 4px 2px 0;}}
  .chip.ok{{background:#ecfdf5;border-color:#a7f3d0;}}
  .chip.warn{{background:#fffbeb;border-color:#fde68a;}}
  .kv{{font-size:13px;margin:6px 0;}}
  .kv ul{{margin:2px 0;padding-left:20px;}}
  ul.red li{{color:#b91c1c;}} ul.green li{{color:#047857;}}
  .filters{{margin:10px 0;}}
  .f{{border:1px solid #d1d5db;background:#fff;border-radius:8px;padding:4px 12px;margin-right:6px;cursor:pointer;font-size:13px;}}
  .f.active{{background:#2563eb;border-color:#2563eb;color:#fff;}}
  .candidate{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin-bottom:12px;}}
  .chead{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px;}}
  .score{{font-weight:700;padding:2px 10px;border-radius:999px;color:#fff;font-size:13px;}}
  .score.high{{background:#10b981;}} .score.mid{{background:#f59e0b;}} .score.low{{background:#ef4444;}}
  .vtag{{font-size:12px;padding:1px 8px;border-radius:999px;}}
  .vtag.rec{{background:#d1fae5;color:#065f46;}} .vtag.hold{{background:#fef3c7;color:#92400e;}} .vtag.no{{background:#fee2e2;color:#991b1b;}}
  .cname{{font-weight:600;font-size:15px;}} .cid{{color:#9ca3af;font-size:12px;}}
  .btn{{margin-left:auto;background:#2563eb;color:#fff;text-decoration:none;font-size:12px;padding:5px 12px;border-radius:8px;}}
  .btn:hover{{background:#1d4ed8;}}
  .summ{{font-size:13px;color:#374151;margin-bottom:6px;}}
  .points,.concerns{{font-size:13px;margin:4px 0;}}
  .points ul,.concerns ul{{margin:2px 0;padding-left:20px;}}
  .points li{{color:#047857;}} .concerns li{{color:#b91c1c;}}
  .greeting{{background:#fff7ed;border-left:3px solid #fb923c;padding:8px 12px;border-radius:4px;margin-top:8px;font-size:13px;}}
  .g-item{{margin-top:4px;}} .g-label{{display:inline-block;background:#fef3c7;color:#92400e;font-size:11px;padding:1px 8px;border-radius:999px;margin-right:6px;font-weight:600;}}
  details.snippet{{margin-top:8px;}} details.snippet summary{{cursor:pointer;color:#6b7280;font-size:12px;}}
  details.snippet pre{{background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:8px;font-size:12px;white-space:pre-wrap;font-family:inherit;}}
  .footer{{text-align:center;margin-top:18px;color:#9ca3af;font-size:12px;}}
</style>
</head>
<body>
<div class="wrap">
  <h1>📊 {esc(job_title)} · 候选人匹配报告</h1>
  <div class="meta">本地渲染（数据来源：结构化 JSON，非 LLM 手写）· 生成 {esc(now)} · 共 {esc(total)} 人
    （推荐 {n_rec} / 待定 {n_hold} / 不推荐 {n_no}）</div>
  {pq_html}
  {body_g}
  {cards_html}
  <div class="footer">小猎工作台产物 · 数据资产在 reports/*.json，本页可随时重新生成</div>
</div>
<script>
  document.querySelectorAll('.f').forEach(function(btn){{
    btn.addEventListener('click', function(){{
      document.querySelectorAll('.f').forEach(function(b){{b.classList.remove('active');}});
      btn.classList.add('active');
      var f = btn.getAttribute('data-f');
      document.querySelectorAll('.candidate').forEach(function(c){{
        c.style.display = (f === 'all' || c.getAttribute('data-v') === f) ? '' : 'none';
      }});
    }});
  }});
</script>
</body>
</html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="本地渲染候选人匹配/打招呼 HTML 报告")
    ap.add_argument("--report", required=True, type=Path, help="pool_report JSON（含 pool_quality + candidates）")
    ap.add_argument("--collect", type=Path, default=None, help="collected JSON（可选，取姓名/直达链接/摘要）")
    ap.add_argument("--out", type=Path, default=None, help="输出 HTML 路径（默认 stdout 同级文件名）")
    ap.add_argument("--title", default="", help="报告标题（岗位名）")
    ap.add_argument("--group", choices=["none", "verdict"], default="none", help="分组方式（none=按分排序；verdict=按判定）")
    args = ap.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"❌ 报告文件不存在: {report_path}")
        sys.exit(1)
    data = json.loads(report_path.read_text(encoding="utf-8-sig"))
    candidates = data.get("candidates") or []
    rows = parse_collected(args.collect) if args.collect else []
    title = args.title or f"岗位 {report_path.parent.name}"
    out_html = render(title, data, candidates, rows, group=args.group)
    out = args.out or (report_path.with_name(report_path.stem + ".html"))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_html, encoding="utf-8")
    print(f"✅ 已渲染 {len(candidates)} 人 → {out}（{out.stat().st_size} 字节）")


if __name__ == "__main__":
    main()
