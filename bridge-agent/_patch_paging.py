import sys
from pathlib import Path

p = Path(r"D:\study\bestagent\bridge-agent\extension\background.js")
src = p.read_text(encoding="utf-8")

NEWFUNC = '''/** 翻页（v1.9.2 新增，2026-09-16）——**按分页结构点，不按文字**
 *
 *  为什么必须新加它（实测）：老板的结果页页码是 `li.ant-pagination-item`，
 *  ① `click_by_text("下一页")` 找不到可点祖先（`li` 没有 role/tabindex/onclick/class，
 *     而文字在子节点里 → 我们的"可点判定"漏了它）；
 *  ② `click_by_text("4")` 会点到年龄"46岁"里的那个 span（每次 72 个候选匹配）——
 *     页码是**短数字**，拿文字定位必然撞车。
 *  所以这里直接读分页容器：优先点"下一页"，没有箭头就点"当前页 + 1"那个页码。
 *
 *  direction: 'next' | 'prev'
 *  返回 {ok, clicked, page_before, page_after, waited_ms}：
 *    · clicked='next-arrow' / 'page-item' / 'text-fallback'
 *    · page_after 为 null 表示"读不到当前页码"（不是失败）
 *    · 翻不动（下一页是 disabled，或页码没变）→ ok=false + reason='no-next' / 'not-changed'
 *      —— **这套语义正好当"尾部到头了/翻页失败"的判据**，上层不用猜。
 *  ⚠️ 自包含：executeScript 只序列化本函数，全部逻辑内联。 */
function zClickPaging(direction, waitMs) {
  const result = { ok: false, error: null, clicked: null, page_before: null, page_after: null,
                   waited_ms: 0, url: location.href };
  const t0 = performance.now();
  try {
    const dir = String(direction || 'next').toLowerCase() === 'prev' ? 'prev' : 'next';
    const cap = Number(waitMs) > 0 ? Number(waitMs) : 15000;
    const activeSel = '.ant-pagination-item-active, li.active, .active[class*="pagination"], [class*="pagination"] .active';
    const activeEl = () => document.querySelector(activeSel);
    const pageOf = (el) => {
      if (!el) return null;
      const t = (el.textContent || el.innerText || '').trim();
      const m = t.match(/\\d+/);
      return m ? parseInt(m[0], 10) : null;
    };
    result.page_before = pageOf(activeEl());

    const arrow = document.querySelector('.ant-pagination-' + dir);
    let target = null;
    if (arrow && !/disabled/.test(String(arrow.className))) {
      target = arrow;
      result.clicked = dir + '-arrow';
    } else {
      const a = activeEl();
      if (a) {
        const items = Array.from(document.querySelectorAll('.ant-pagination-item'));
        const i = items.indexOf(a);
        const cand = i >= 0 ? items[i + (dir === 'next' ? 1 : -1)] : null;
        if (cand) {
          target = cand;
          result.clicked = 'page-item';
        }
      }
      if (!target) {
        // 兜底：非 antd 分页——找含"下一页/next"的可点元素
        const words = dir === 'next' ? ['下一页', '下页', 'next', '›', '»'] : ['上一页', '上页', 'prev', '‹', '«'];
        const all = document.querySelectorAll('a,button,li,span,div');
        for (const el of all) {
          const txt = ((el.textContent || '').trim()).slice(0, 6).toLowerCase();
          if (txt && words.some((w) => txt === w || txt.includes(w))) {
            if (el.offsetParent !== null) { target = el; result.clicked = 'text-fallback'; break; }
          }
        }
      }
    }
    if (!target || target.offsetParent === null) {
      result.error = '没找到可点的翻页控件（可能已是最后一页 / 分页结构变了）';
      result.reason = 'no-next';
      result.waited_ms = Math.round(performance.now() - t0);
      return result;
    }
    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    target.click();

    // 等"页码真的变了"（或等到发现页码读不到就不再干等）
    const seenBefore = result.page_before;
    const deadline = t0 + cap;
    let sawReadable = seenBefore !== null;
    while (performance.now() < deadline) {
      const cur = pageOf(activeEl());
      if (cur !== null) {
        sawReadable = true;
        if (cur !== seenBefore) break;
      } else if (sawReadable && performance.now() - t0 > 1200) {
        break;   // 原来读得到、现在读不到了 → 视为已变（页面在重渲染）
      }
    }
    result.page_after = pageOf(activeEl());
    result.waited_ms = Math.round(performance.now() - t0);
    if (sawReadable && seenBefore !== null && result.page_after === seenBefore) {
      result.ok = false;
      result.reason = 'not-changed';
      result.error = `点了${result.clicked}但页码还是第 ${seenBefore} 页（可能已是最后一页）`;
      return result;
    }
    result.ok = true;
  } catch (e) {
    result.error = String(e);
  }
  return result;
}

'''

ANCHOR = "// ============================================================\n// 任务分发：action -> 工具函数"
if src.count(ANCHOR) != 1:
    raise SystemExit(f"锚点匹配 {src.count(ANCHOR)} 次")
src = src.replace(ANCHOR, NEWFUNC + ANCHOR, 1)

OLD2 = "  extract: zExtract,\n  page_text: zPageText,"
NEW2 = "  extract: zExtract,\n  page_text: zPageText,\n  click_paging: zClickPaging,"
if src.count(OLD2) != 1:
    raise SystemExit("TOOL_FUNCS 锚点不唯一")
src = src.replace(OLD2, NEW2, 1)

OLD3 = "  if (action === 'page_text') args.push(p.max_chars !== undefined ? Number(p.max_chars) : 0);"
NEW3 = (OLD3 + "\n  if (action === 'click_paging') args.push(p.direction ? String(p.direction) : 'next', "
        "p.wait_ms !== undefined ? Number(p.wait_ms) : 15000);")
if src.count(OLD3) != 1:
    raise SystemExit("参数装配锚点不唯一")
src = src.replace(OLD3, NEW3, 1)

p.write_text(src, encoding="utf-8")
print("OK: click_paging 已加，字符数 =", len(src))
