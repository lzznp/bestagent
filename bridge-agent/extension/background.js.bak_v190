/**
 * background.js — 小猎跑腿 执行器（原 browser-agent / 桥）
 *
 * 职责：
 *  1. 轮询桥接服务 /api/task/poll 领取任务
 *  2. 在"当前激活标签页"上注入执行（快照/点击/输入/滚动/猎聘提取）
 *  3. 结果回报 /api/task/result
 *
 * 工具函数全部自包含（executeScript 会把函数体序列化到页面上下文执行，
 * 不能引用外部作用域），因此每个工具内部内联全部逻辑。
 */

const BRIDGE_URL = 'http://127.0.0.1:8080';
const POLL_INTERVAL_MS = 1500;

// ============================================================
// 工具函数库（自包含，注入页面执行）
// ============================================================
// ⚠️ executeScript 注入时只序列化目标函数本身，函数体内的所有逻辑
// 必须自包含（不能引用本文件的其他函数/变量）。zSnapshot / zClick /
// zType 等每个工具内部均内联了完整实现，且共享同一套 DOM 遍历顺序，
// 保证快照编号与 click/type 取元素编号一致。

/** 快照：页面元信息 + 编号交互元素 + 正文预览（给 LLM 读的结构化文本）
 *  ⚠️ 自包含：executeScript 注入时只序列化本函数，因此 settle 等待与
 *  collectElements 的逻辑全部内联在此（与 zClick/zType 同一遍历顺序）。
 *  T2：快照前先等页面稳定（readyState complete + DOM 静默窗口），
 *  避免点击/导航后立刻拿到半成品页面导致 LLM 误判。 */
async function zSnapshot() {
  const result = { ok: true, title: '', url: '', elements: [], body_preview: '', error: null, settled: null };
  try {
    // ---- T2 settle：等待页面加载稳定 ----
    const settle = async () => {
      const t0 = performance.now();
      // 1) 等待 document readyState === complete（最多 8s）
      if (document.readyState !== 'complete') {
        await new Promise((resolve) => {
          let done = false;
          const finish = () => { if (!done) { done = true; document.removeEventListener('readystatechange', finish); resolve(); } };
          document.addEventListener('readystatechange', finish);
          setTimeout(finish, 8000);
        });
      }
      // 2) DOM 静默窗口：readyState complete 后，观察 200ms 无 DOM 变更
      //    （最多等 2.5s，持续动画页面不能无限阻塞）
      const readyAt = performance.now();
      let lastMutation = readyAt;
      let observer = null;
      const settledOk = await new Promise((resolve) => {
        let finished = false;
        let timer = null;
        const finish = (v) => {
          if (finished) return;
          finished = true;
          if (timer) clearTimeout(timer);
          if (observer) observer.disconnect();
          resolve(v);
        };
        const check = () => {
          timer = null;
          const now = performance.now();
          if ((now - readyAt >= 100 && now - lastMutation >= 200) || now - readyAt >= 2500) {
            finish(true);
            return;
          }
          timer = setTimeout(check, 50);
        };
        if (document.documentElement) {
          observer = new MutationObserver(() => { lastMutation = performance.now(); });
          observer.observe(document.documentElement, {
            subtree: true, childList: true, attributes: true, characterData: true,
          });
        }
        check();
      });
      return { waited_ms: Math.round(performance.now() - t0), settled: settledOk };
    };
    result.settled = await settle();
    // ---- 页面元信息 ----
    result.title = document.title || '';
    result.url = location.href;
    // ---- 内联 collectElements（与 elementByIndex 相同遍历顺序）----
    const els = [];
    const seen = new WeakSet();
    // T1（G1）：可点元素检测增强——把"看得见字、点不了"的选项类 span/li 纳入
    // ① class 含 option|select|dropdown（猎聘条件选项）② cursor:pointer 且有自有文本
    // ⚠️ 与 zClick/zType/zClickByText 内的副本保持同一逻辑（编号一致性）
    const isInteractive = (el) => {
      const tag = el.tagName.toLowerCase();
      if (['a', 'button', 'input', 'textarea', 'select'].includes(tag)) return true;
      const role = (el.getAttribute('role') || '').toLowerCase();
      if (['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'menuitem', 'tab', 'searchbox'].includes(role)) return true;
      if (el.getAttribute('tabindex') !== null) return true;
      if (el.hasAttribute('onclick')) return true;
      const cls = typeof el.className === 'string' ? el.className : '';
      if (/(^|[\s_-])(option|select|dropdown)([\s_-]|$)/i.test(cls)) return true;
      if (['span', 'li', 'em', 'i', 'label'].includes(tag)) {
        // 自有文本（直接文本节点，非子元素里的）→ 典型选项小元素；样式为 pointer
        const ownText = Array.from(el.childNodes).some(n => n.nodeType === 3 && (n.textContent || '').trim());
        if (ownText) {
          try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
        }
      }
      return false;
    };
    const getLabel = (el) => {
      const aria = el.getAttribute('aria-label');
      if (aria && aria.trim()) return aria.trim().slice(0, 80);
      const title = el.getAttribute('title');
      if (title && title.trim()) return title.trim().slice(0, 80);
      const ph = el.getAttribute('placeholder');
      if (ph && ph.trim()) return ph.trim().slice(0, 80);
      const name = el.getAttribute('name');
      if (name && name.trim()) return name.trim().slice(0, 80);
      if (el.children.length === 0) {
        const t = (el.textContent || '').trim();
        return t.slice(0, 80);
      }
      const direct = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3)
        .map(n => n.textContent.trim()).join(' ').trim();
      return direct ? direct.slice(0, 80) : '';
    };
    const walk = (node) => {
      if (!node || node.nodeType !== 1) return;
      if (seen.has(node)) return;
      seen.add(node);
      const tag = node.tagName.toLowerCase();
      if (['script', 'style', 'noscript', 'svg', 'path'].includes(tag)) return;
      if (isInteractive(node) && node.offsetParent !== null) {
        els.push(node);
      }
      for (const child of node.children) walk(child);
    };
    walk(document.body);
    // P4-SOM：视觉顺序编号——按元素屏幕位置（top→left）排序（文档序作稳定兜底），
    // 使编号顺序与"看图选编号"的视觉感知一致（DOM 文档序与视觉序有偏移，
    // 如行内右侧元素"清空筛选条件"）；编号 = 截图徽标上的编号（zClick/zType 同序）。
    // P4-SOM 去重叠：IoU>0.8 的近重合 rect（隐藏下拉堆叠/容器与子元素同点）只保留第一个，
    // 避免徽标重叠成团（与 zClick/zType/徽标注入同规则，保证编号一致）。
    const rectOf = (el) => {
      try { const r = el.getBoundingClientRect(); return { top: r.top, left: r.left, width: r.width, height: r.height }; }
      catch (e) { return { top: 0, left: 0, width: 0, height: 0 }; }
    };
    const iou = (a, b) => {
      const ix = Math.max(a.left, b.left), iy = Math.max(a.top, b.top);
      const iw = Math.max(0, Math.min(a.left + a.width, b.left + b.width) - ix);
      const ih = Math.max(0, Math.min(a.top + a.height, b.top + b.height) - iy);
      const inter = iw * ih;
      if (inter <= 0) return 0;
      const union = a.width * a.height + b.width * b.height - inter;
      return union > 0 ? inter / union : 0;
    };
    const withRect = els.map((el, i) => ({ el, i, rect: rectOf(el) }));
    withRect.sort((a, b) => (a.rect.top - b.rect.top) || (a.rect.left - b.rect.left) || (a.i - b.i));
    const kept = [];
    for (const x of withRect) {
      // P5-2：表单输入元素（input/textarea/select）永远保留——零面积隐藏的搜索框
      // （如 Ant Design Select 未激活时的输入框）仍需可定位可输入；非表单元素才做零面积/去重过滤
      const isFormEl = ['input', 'textarea', 'select'].includes((x.el.tagName || '').toLowerCase());
      if (!isFormEl && (x.rect.width < 4 || x.rect.height < 4)) continue;
      let dup = false;
      for (const k of kept) {
        if (iou(x.rect, k.rect) > 0.8) { dup = true; break; }
      }
      if (!dup || isFormEl) kept.push(x);
    }
    result.elements = kept.map((x, idx) => {
      const el = x.el;
      const tag = el.tagName.toLowerCase();
      const value = el.value !== undefined && el.value !== null ? String(el.value).slice(0, 60) : '';
      return {
        index: idx,
        tag,
        role: (el.getAttribute('role') || tag).toLowerCase(),
        name: getLabel(el),
        value,
        href: el.href ? el.href.slice(0, 120) : '',
        rect: x.rect,
      };
    });
    result.order = 'visual';
    // ---- 正文预览 ----
    const bodyText = (document.body && document.body.innerText || '').trim();
    result.body_preview = bodyText.slice(0, 3000);
  } catch (e) {
    result.ok = false;
    result.error = String(e);
  }
  return result;
}

/** 按编号点击
 *  ⚠️ 自包含：elementByIndex 的遍历逻辑内联在此（与 zSnapshot 相同的遍历顺序）。 */
function zClick(index) {
  const result = { ok: false, error: null };
  try {
    // ---- 内联 elementByIndex ----
    const out = [];
    const seen = new WeakSet();
    // T1（G1）：与 zSnapshot 相同的可点增强（选项类 span/li + cursor:pointer）
    const isInteractive = (el) => {
      const tag = el.tagName.toLowerCase();
      if (['a', 'button', 'input', 'textarea', 'select'].includes(tag)) return true;
      const role = (el.getAttribute('role') || '').toLowerCase();
      if (['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'menuitem', 'tab', 'searchbox'].includes(role)) return true;
      if (el.getAttribute('tabindex') !== null) return true;
      if (el.hasAttribute('onclick')) return true;
      const cls = typeof el.className === 'string' ? el.className : '';
      if (/(^|[\s_-])(option|select|dropdown)([\s_-]|$)/i.test(cls)) return true;
      if (['span', 'li', 'em', 'i', 'label'].includes(tag)) {
        const ownText = Array.from(el.childNodes).some(n => n.nodeType === 3 && (n.textContent || '').trim());
        if (ownText) {
          try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
        }
      }
      return false;
    };
    const walk = (node) => {
      if (!node || node.nodeType !== 1 || seen.has(node)) return;
      seen.add(node);
      const tag = node.tagName.toLowerCase();
      if (['script', 'style', 'noscript', 'svg', 'path'].includes(tag)) return;
      if (isInteractive(node) && node.offsetParent !== null) out.push(node);
      for (const child of node.children) walk(child);
    };
    walk(document.body);
    // P4-SOM：与 zSnapshot 相同的视觉顺序（top→left）+ IoU>0.8 去重叠，保证编号一致
    const _iou = (a, b) => {
      const ix = Math.max(a.left, b.left), iy = Math.max(a.top, b.top);
      const iw = Math.max(0, Math.min(a.left + a.width, b.left + b.width) - ix);
      const ih = Math.max(0, Math.min(a.top + a.height, b.top + b.height) - iy);
      const inter = iw * ih;
      if (inter <= 0) return 0;
      const union = a.width * a.height + b.width * b.height - inter;
      return union > 0 ? inter / union : 0;
    };
    const _rects = out.map((el) => {
      try { const r = el.getBoundingClientRect(); return { top: r.top, left: r.left, width: r.width, height: r.height }; }
      catch (e) { return { top: 0, left: 0, width: 0, height: 0 }; }
    });
    const _idx = out.map((_, i) => i);
    _idx.sort((a, b) => (_rects[a].top - _rects[b].top) || (_rects[a].left - _rects[b].left) || (a - b));
    const _kept = [];
    for (const i of _idx) {
      // P5-2：表单输入元素永远保留（零面积隐藏搜索框仍需可点可输入）
      const _isFormEl = ['input', 'textarea', 'select'].includes((out[i].tagName || '').toLowerCase());
      if (!_isFormEl && (_rects[i].width < 4 || _rects[i].height < 4)) continue;  // 零面积隐藏项跳过
      let dup = false;
      for (const k of _kept) {
        if (_iou(_rects[i], _rects[k]) > 0.8) { dup = true; break; }
      }
      if (!dup || _isFormEl) _kept.push(i);
    }
    const target = _kept.map(i => out[i])[Number(index)];
    // ---- 点击 ----
    if (!target) { result.error = `编号 ${index} 不存在，请重新快照`; return result; }
    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    // P5-2：真实事件序列——Ant Design Select 等控件监听 mousedown，仅 el.click() 打不开下拉。
    // 先派发 mousedown/mouseup 再 click（自包含内联，executeScript 只序列化本函数）
    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    target.click();
    result.ok = true;
    result.clicked = { index, tag: target.tagName.toLowerCase() };
  } catch (e) {
    result.error = String(e);
  }
  return result;
}

/** 按编号输入文本（兼容 React：原生 setter + input/change 事件）
 *  ⚠️ 自包含：elementByIndex 的遍历逻辑内联在此（与 zSnapshot 相同的遍历顺序）。 */
function zType(index, text) {
  const result = { ok: false, error: null };
  try {
    // ---- 内联 elementByIndex ----
    const out = [];
    const seen = new WeakSet();
    // T1（G1）：与 zSnapshot 相同的可点增强（选项类 span/li + cursor:pointer）
    const isInteractive = (el) => {
      const tag = el.tagName.toLowerCase();
      if (['a', 'button', 'input', 'textarea', 'select'].includes(tag)) return true;
      const role = (el.getAttribute('role') || '').toLowerCase();
      if (['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'menuitem', 'tab', 'searchbox'].includes(role)) return true;
      if (el.getAttribute('tabindex') !== null) return true;
      if (el.hasAttribute('onclick')) return true;
      const cls = typeof el.className === 'string' ? el.className : '';
      if (/(^|[\s_-])(option|select|dropdown)([\s_-]|$)/i.test(cls)) return true;
      if (['span', 'li', 'em', 'i', 'label'].includes(tag)) {
        const ownText = Array.from(el.childNodes).some(n => n.nodeType === 3 && (n.textContent || '').trim());
        if (ownText) {
          try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
        }
      }
      return false;
    };
    const walk = (node) => {
      if (!node || node.nodeType !== 1 || seen.has(node)) return;
      seen.add(node);
      const tag = node.tagName.toLowerCase();
      if (['script', 'style', 'noscript', 'svg', 'path'].includes(tag)) return;
      if (isInteractive(node) && node.offsetParent !== null) out.push(node);
      for (const child of node.children) walk(child);
    };
    walk(document.body);
    // P4-SOM：与 zSnapshot 相同的视觉顺序（top→left）+ IoU>0.8 去重叠，保证编号一致
    const _iou = (a, b) => {
      const ix = Math.max(a.left, b.left), iy = Math.max(a.top, b.top);
      const iw = Math.max(0, Math.min(a.left + a.width, b.left + b.width) - ix);
      const ih = Math.max(0, Math.min(a.top + a.height, b.top + b.height) - iy);
      const inter = iw * ih;
      if (inter <= 0) return 0;
      const union = a.width * a.height + b.width * b.height - inter;
      return union > 0 ? inter / union : 0;
    };
    const _rects = out.map((el) => {
      try { const r = el.getBoundingClientRect(); return { top: r.top, left: r.left, width: r.width, height: r.height }; }
      catch (e) { return { top: 0, left: 0, width: 0, height: 0 }; }
    });
    const _idx = out.map((_, i) => i);
    _idx.sort((a, b) => (_rects[a].top - _rects[b].top) || (_rects[a].left - _rects[b].left) || (a - b));
    const _kept = [];
    for (const i of _idx) {
      // P5-2：表单输入元素永远保留（零面积隐藏搜索框仍需可点可输入）
      const _isFormEl = ['input', 'textarea', 'select'].includes((out[i].tagName || '').toLowerCase());
      if (!_isFormEl && (_rects[i].width < 4 || _rects[i].height < 4)) continue;  // 零面积隐藏项跳过
      let dup = false;
      for (const k of _kept) {
        if (_iou(_rects[i], _rects[k]) > 0.8) { dup = true; break; }
      }
      if (!dup || _isFormEl) _kept.push(i);
    }
    const target = _kept.map(i => out[i])[Number(index)];
    // ---- 输入 ----
    if (!target) { result.error = `编号 ${index} 不存在，请重新快照`; return result; }
    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    target.focus();
    target.click();
    const proto = target.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
      : target.tagName === 'INPUT' ? HTMLInputElement.prototype : null;
    if (proto) {
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(target, String(text));
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.dispatchEvent(new Event('change', { bubbles: true }));
    } else if (target.isContentEditable) {
      target.textContent = String(text);
      target.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      result.error = '目标不是可输入元素';
      return result;
    }
    result.ok = true;
    result.typed = { index, text: String(text).slice(0, 50) };
  } catch (e) {
    result.error = String(e);
  }
  return result;
}

/** 按文本点击（T1/G1：解决"看得见字、点不了"的选项类元素）
 *  参数 text：目标文本（快照正文预览/选项里可见的任意子串）；
 *  参数 occurrence（可选）：第几个匹配（默认 1，页面有多个同文本元素时指定）。
 *  逻辑：TreeWalker 找文本节点包含 text 的元素 → 向上找**最小可点祖先**
 *  （自身或最近祖先命中可点检测，见内联 isInteractive）→ 点击。
 *  返回命中总数 total 与匹配文本，方便验证点到的是哪个。
 *  ⚠️ 自包含：executeScript 只序列化本函数，全部逻辑内联（isInteractive 与 zSnapshot 同款增强）。 */
function zClickByText(text, occurrence) {
  const result = { ok: false, error: null };
  try {
    const t = String(text || '').trim();
    if (!t) { result.error = '缺少 text 参数（目标文本）'; return result; }
    const want = Math.max(1, Number(occurrence) || 1);
    // ---- 内联 isInteractive（与 zSnapshot/zClick/zType 同款增强）----
    const isInteractive = (el) => {
      const tag = el.tagName.toLowerCase();
      if (['a', 'button', 'input', 'textarea', 'select'].includes(tag)) return true;
      const role = (el.getAttribute('role') || '').toLowerCase();
      if (['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'menuitem', 'tab', 'searchbox'].includes(role)) return true;
      if (el.getAttribute('tabindex') !== null) return true;
      if (el.hasAttribute('onclick')) return true;
      const cls = typeof el.className === 'string' ? el.className : '';
      if (/(^|[\s_-])(option|select|dropdown)([\s_-]|$)/i.test(cls)) return true;
      if (['span', 'li', 'em', 'i', 'label'].includes(tag)) {
        const ownText = Array.from(el.childNodes).some(n => n.nodeType === 3 && (n.textContent || '').trim());
        if (ownText) {
          try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
        }
      }
      return false;
    };
    // ---- 匹配：文本节点包含 t → 向上找最小可点祖先 ----
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const matches = []; // [{el, text}]，按文档序
    const seenEls = new WeakSet();
    let n = null;
    while ((n = walker.nextNode())) {
      const nt = (n.textContent || '').trim();
      if (!nt || !nt.includes(t)) continue;
      let cur = n.parentElement;
      let target = null;
      while (cur && cur !== document.body) {
        if (isInteractive(cur) && cur.offsetParent !== null) { target = cur; break; }
        cur = cur.parentElement;
      }
      if (target && !seenEls.has(target)) {
        seenEls.add(target);
        matches.push({ el: target, text: nt.slice(0, 80) });
      }
    }
    if (matches.length === 0) {
      result.error = `未找到包含 "${t}" 的可点元素`;
      return result;
    }
    if (matches.length < want) {
      result.error = `包含 "${t}" 的可点元素共 ${matches.length} 个，少于要求的第 ${want} 个`;
      return result;
    }
    const target = matches[want - 1].el;
    target.scrollIntoView({ block: 'center', behavior: 'instant' });
    // P5-2：真实事件序列（同 zClick）——mousedown 监听控件（Ant Design Select）必须派发
    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    target.click();
    result.ok = true;
    result.clicked = {
      text: t,
      occurrence: want,
      total: matches.length,
      tag: target.tagName.toLowerCase(),
      matched_text: matches[want - 1].text,
    };
  } catch (e) {
    result.error = String(e);
  }
  return result;
}

/** 滚动 */
function zScroll(direction, amount) {
  const result = { ok: false, error: null };
  try {
    const d = String(direction || 'down').toLowerCase();
    const a = Number(amount) || 600;
    const y = d === 'up' ? -a : d === 'top' ? -window.scrollY : d === 'bottom' ? document.body.scrollHeight - window.innerHeight - window.scrollY : a;
    window.scrollBy({ top: y, behavior: 'instant' });
    result.ok = true;
    result.scrolled = { direction: d, y: window.scrollY };
  } catch (e) {
    result.error = String(e);
  }
  return result;
}

/** 跳转 */
function zNavigate(url) {
  const result = { ok: false, error: null };
  try {
    location.href = String(url);
    result.ok = true;
  } catch (e) {
    result.error = String(e);
  }
  return result;
}

/** 通用提取：文本锚点定位卡片行，返回行内文本 + 行内命名 input 的 value
 *  P2-1（去猎聘化）：替代 zExtractLiepin。参数 anchor_text = 卡片内任一稳定子串
 *  （如"立即沟通"），锚点命中所有卡片 → 向上找行容器（tr/li/class 含 item|card）→
 *  去重 → 每行 {text: 行 innerText, fields: {name: value}}（行内所有带 name 的 input，
 *  如诚猎通的 res_id_encode 会自动入列；本工具不认识任何站点字段）。
 *  ⚠️ 自包含：executeScript 只序列化本函数，全部逻辑内联。 */
function zExtract(anchorText) {
  const result = { ok: true, url: location.href, rows: [], count: 0, error: null };
  try {
    const anchor = String(anchorText || '').trim();
    if (!anchor) {
      result.ok = false;
      result.error = '缺少 anchor_text 参数（卡片内任一稳定子串，如"立即沟通"）';
      return result;
    }
    // 1) 文本节点命中锚点 → 取其父元素（最小命中元素，避免父容器整段命中）
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const t = (node.textContent || '').trim();
        return t && t.includes(anchor) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    const hits = new Set();
    let n = null;
    while ((n = walker.nextNode())) {
      if (n.parentElement) hits.add(n.parentElement);
    }
    // 2) 从命中元素向上找行容器：优先 tr/li（语义行，页面数据卡片通常就是它）；
    //    无 tr/li 时取最近的 class 含 item|card 的祖先兜底（避免"立即沟通"按钮外层
    //    的 op-item 之类小容器被误当整卡——继续向上爬到 tr 即纠正）
    const rows = new Set();
    for (const el of hits) {
      let cur = el;
      let best = null;
      while (cur && cur !== document.body) {
        const tag = cur.tagName.toLowerCase();
        if (tag === 'tr' || tag === 'li') { best = cur; break; }
        const cls = cur.className;
        if (typeof cls === 'string' && /item|card/i.test(cls)) best = cur;
        cur = cur.parentElement;
      }
      if (best) rows.add(best);
    }
    // 3) 每行：text = innerText；fields = 行内所有带 name 的 input 的 value（同名取第一个）
    for (const row of rows) {
      const fields = {};
      for (const inp of row.querySelectorAll('input[name]')) {
        const nm = inp.getAttribute('name');
        if (nm && !(nm in fields)) fields[nm] = (inp.value !== undefined && inp.value !== null) ? String(inp.value) : '';
      }
      result.rows.push({ text: (row.innerText || '').trim(), fields });
    }
    result.count = result.rows.length;
  } catch (e) {
    result.ok = false;
    result.error = String(e);
  }
  return result;
}

/** 站点结构基线检测（P2-4 知识库改版检测用，内部动作，不暴露给 LLM）
 *  参数 checks: [{type: "text_anchor"|"input_name"|"text"|"selector", value: "..."}]
 *  - text_anchor: 文本节点包含 value（锚点文本，如"立即沟通"）
 *  - input_name:  存在 input[name=value]（隐藏字段，如 res_id_encode）
 *  - text:        body.innerText 包含 value
 *  - selector:    querySelector(value) 命中
 *  任一不命中 → result.ok=false + missing 列出缺失项（= 网站可能改版）。
 *  ⚠️ 自包含：executeScript 只序列化本函数，全部逻辑内联。 */
function zVerifySite(checks) {
  const result = { ok: true, url: location.href, checks: [], missing: [], verified: true, error: null };
  try {
    const list = Array.isArray(checks) ? checks : [];
    for (const c of list) {
      const item = { type: c && c.type, value: c && c.value, pass: false };
      try {
        const v = String(c && c.value || '');
        if (c && c.type === 'text_anchor') {
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          let n = null;
          while ((n = walker.nextNode())) {
            if ((n.textContent || '').includes(v)) { item.pass = true; break; }
          }
        } else if (c && c.type === 'input_name') {
          item.pass = !!document.querySelector('input[name="' + v.replace(/"/g, '\\"') + '"]');
        } else if (c && c.type === 'text') {
          item.pass = (document.body && document.body.innerText || '').includes(v);
        } else if (c && c.type === 'selector') {
          item.pass = !!document.querySelector(v);
        }
      } catch (e) {
        item.error = String(e);
      }
      result.checks.push(item);
      if (!item.pass) result.missing.push(item.value || item.type);
    }
    // ⚠️ 语义：ok 恒为 true（探测动作"执行成功"）；校验结果在 verified 字段——
    // verified=false 是有效的探测结果（站点可能改版），不是动作失败，
    // 否则 bridge 会按失败任务处理，agent 侧拿不到校验结论。
    result.verified = result.missing.length === 0;
  } catch (e) {
    result.ok = false;
    result.error = String(e);
  }
  return result;
}

// ============================================================
// 多标签页工具（P2-3：后台型动作，不经页面注入，直接 chrome.tabs API）
// 人工场景：找简历 → 开详情页 → 切回复页对话
// ============================================================

/** 列出当前窗口所有标签页（tab_id/url/title/active） */
async function zListTabs() {
  try {
    const tabs = await chrome.tabs.query({ currentWindow: true });
    return {
      ok: true,
      tabs: tabs.map(t => ({ tab_id: t.id, url: t.url || '', title: t.title || '', active: t.active })),
    };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}

/** 打开新标签页并激活 */
async function zNewTab(url) {
  try {
    const tab = await chrome.tabs.create({ url: String(url || 'about:blank'), active: true });
    return { ok: true, tab: { tab_id: tab.id, url: tab.url || '', title: tab.title || '', active: true } };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}

/** 切换到指定标签页（激活；后续注入型动作作用于新激活页） */
async function zSwitchTab(tabId) {
  try {
    const n = Number(tabId);
    if (!n) return { ok: false, error: '缺少有效的 tab_id' };
    const tab = await chrome.tabs.update(n, { active: true });
    return { ok: true, tab: { tab_id: tab.id, url: tab.url || '', title: tab.title || '', active: true } };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}

/** 关闭指定标签页（新标签用完后关闭；关闭激活标签后浏览器自动激活相邻标签） */
async function zCloseTab(tabId) {
  try {
    const n = Number(tabId);
    if (!n) return { ok: false, error: '缺少有效的 tab_id' };
    await chrome.tabs.remove(n);
    return { ok: true, closed: n };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}

/** 截图（P4-V-T1：视觉辅助基础能力——SOM 看图选编号/改版检测都依赖它）
 *  后台型动作：不注入页面，直接 chrome.tabs API（captureVisibleTab 需要目标标签可见）。
 *  优先 chrome.tabs.captureTab(tabId)（Chrome 126+：可直接截指定标签，含后台标签）；
 *  不可用时回退 captureVisibleTab（只能截窗口内激活标签——目标标签非激活时
 *  临时激活→截图→恢复原激活标签，避免打扰用户当前正在看的页面）。
 *  返回 {ok, data_url: PNG base64, tab_id}；由 bridge 落盘 logs/screenshots/ 并换成文件路径。
 *  ⚠️ 只读动作：截图不改变页面状态。 */
async function zScreenshot(tabId) {
  const result = { ok: false, error: null, data_url: null, method: null };
  try {
    const n = Number(tabId);
    if (!n) return { ok: false, error: '缺少有效的 tab_id（截图需要指定目标标签页）' };
    let dataUrl = null;
    // 1) captureTab（Chrome 126+）：仅目标标签**已激活**时可用（后台标签会拿陈旧帧/直接抛错）
    if (typeof chrome.tabs.captureTab === 'function') {
      try {
        const tabNow = await chrome.tabs.get(n);
        if (tabNow.active) {
          dataUrl = await chrome.tabs.captureTab(n, { format: 'png' });
          if (dataUrl) result.method = 'captureTab';
        }
      } catch (e) {
        result.capturetab_error = String(e && e.message || e);
        dataUrl = null;
      }
    }
    // 2) 回退 captureVisibleTab：目标非激活时**先激活并等待画面真实刷新**再截。
    //    ⚠️ 后台标签可能被浏览器休眠/冻结（如 Edge Memory Saver），激活后立即截会拿到
    //    陈旧帧——先等 400ms + 预热截图一帧（丢弃），再截正式图，保证画面是当前状态。
    if (!dataUrl) {
      const tab = await chrome.tabs.get(n);
      let prevActive = null;
      try {
        const winTabs = await chrome.tabs.query({ windowId: tab.windowId, active: true });
        prevActive = winTabs && winTabs[0] ? winTabs[0].id : null;
        if (!tab.active && prevActive !== n) {
          await chrome.tabs.update(n, { active: true });
          await new Promise(r => setTimeout(r, 400)); // 等唤醒/重绘
          try { await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' }); } catch (e) {} // 预热一帧
          await new Promise(r => setTimeout(r, 200));
        }
        dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
        if (dataUrl) result.method = 'captureVisibleTab';
      } finally {
        if (prevActive && prevActive !== n) {
          try { await chrome.tabs.update(prevActive, { active: true }); } catch (e) {}
        }
      }
    }
    if (!dataUrl) return { ok: false, error: '截图失败：captureTab/captureVisibleTab 均未返回图像（需 <all_urls> 或 activeTab 权限）' };
    result.ok = true;
    result.data_url = dataUrl;
    result.tab_id = n;
  } catch (e) {
    result.error = String(e && e.message || e);
    result.ok = false;
  }
  return result;
}

/** SOM 徽标注入（executeScript 注入页面，自包含）：
 *  与 zSnapshot 相同的 isInteractive + 视觉顺序（top→left）编号，
 *  给每个可点元素叠加红色编号徽标（按 getBoundingClientRect 定位）。
 *  返回 [{index, tag, name, rect}]（编号 = 快照/点击同序，上限 400 防徽标重叠）。 */
function __somInjectBadges() {
  const out = [];
  const seen = new WeakSet();
  const isInteractive = (el) => {
    const tag = el.tagName.toLowerCase();
    if (['a', 'button', 'input', 'textarea', 'select'].includes(tag)) return true;
    const role = (el.getAttribute('role') || '').toLowerCase();
    if (['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'menuitem', 'tab', 'searchbox'].includes(role)) return true;
    if (el.getAttribute('tabindex') !== null) return true;
    if (el.hasAttribute('onclick')) return true;
    const cls = typeof el.className === 'string' ? el.className : '';
    if (/(^|[\s_-])(option|select|dropdown)([\s_-]|$)/i.test(cls)) return true;
    if (['span', 'li', 'em', 'i', 'label'].includes(tag)) {
      const ownText = Array.from(el.childNodes).some(n => n.nodeType === 3 && (n.textContent || '').trim());
      if (ownText) {
        try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
      }
    }
    return false;
  };
  const getLabel = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim().slice(0, 80);
    const title = el.getAttribute('title');
    if (title && title.trim()) return title.trim().slice(0, 80);
    const ph = el.getAttribute('placeholder');
    if (ph && ph.trim()) return ph.trim().slice(0, 80);
    const name = el.getAttribute('name');
    if (name && name.trim()) return name.trim().slice(0, 80);
    if (el.children.length === 0) {
      const t = (el.textContent || '').trim();
      return t.slice(0, 80);
    }
    const direct = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3)
      .map(n => n.textContent.trim()).join(' ').trim();
    return direct ? direct.slice(0, 80) : '';
  };
  const walk = (node) => {
    if (!node || node.nodeType !== 1 || seen.has(node)) return;
    seen.add(node);
    const tag = node.tagName.toLowerCase();
    if (['script', 'style', 'noscript', 'svg', 'path'].includes(tag)) return;
    if (isInteractive(node) && node.offsetParent !== null) out.push(node);
    for (const child of node.children) walk(child);
  };
  walk(document.body);
  out.sort((a, b) => {
    const ra = (() => { try { const r = a.getBoundingClientRect(); return { top: r.top, left: r.left }; } catch (e) { return { top: 0, left: 0 }; } })();
    const rb = (() => { try { const r = b.getBoundingClientRect(); return { top: r.top, left: r.left }; } catch (e) { return { top: 0, left: 0 }; } })();
    return (ra.top - rb.top) || (ra.left - rb.left);
  });
  // 与 zSnapshot 相同的 IoU>0.8 去重叠（隐藏下拉堆叠/容器同点元素只留第一个）
  const _iou = (a, b) => {
    const ix = Math.max(a.left, b.left), iy = Math.max(a.top, b.top);
    const iw = Math.max(0, Math.min(a.left + a.width, b.left + b.width) - ix);
    const ih = Math.max(0, Math.min(a.top + a.height, b.top + b.height) - iy);
    const inter = iw * ih;
    if (inter <= 0) return 0;
    const union = a.width * a.height + b.width * b.height - inter;
    return union > 0 ? inter / union : 0;
  };
  const _rects = out.map((el) => {
    try { const r = el.getBoundingClientRect(); return { top: r.top, left: r.left, width: r.width, height: r.height }; }
    catch (e) { return { top: 0, left: 0, width: 0, height: 0 }; }
  });
  const _kept = [];
  out.forEach((_, i) => {
    // P5-2：表单输入元素永远保留（零面积隐藏搜索框仍需可点可输入）
    const _isFormEl = ['input', 'textarea', 'select'].includes((out[i].tagName || '').toLowerCase());
    if (!_isFormEl && (_rects[i].width < 4 || _rects[i].height < 4)) return;  // 零面积隐藏项不徽标
    let dup = false;
    for (const k of _kept) {
      if (_iou(_rects[i], _rects[k]) > 0.8) { dup = true; break; }
    }
    if (!dup || _isFormEl) _kept.push(i);
  });
  const keptEls = _kept.map(i => out[i]);
  const keptRects = _kept.map(i => _rects[i]);
  const MAX = 400; // 与快照元素上限一致，防徽标重叠成团
  const list = keptEls.slice(0, MAX).map((el, idx) => {
    const r = keptRects[idx];
    return { index: idx, tag: el.tagName.toLowerCase(), name: getLabel(el), rect: r };
  });
  // 防御性清理：注入前移除可能残留的旧徽标层（防累计重叠）
  document.querySelectorAll('#__som_badges__').forEach(l => l.remove());
  const layer = document.createElement('div');
  layer.id = '__som_badges__';
  layer.style.cssText = 'position:fixed;top:0;left:0;z-index:2147483647;pointer-events:none;';
  keptEls.slice(0, MAX).forEach((el, idx) => {
    const r = keptRects[idx];
    if (!r) return;
    const b = document.createElement('div');
    b.textContent = String(idx);
    b.setAttribute('data-som-index', String(idx));
    // 徽标嵌入元素左上角（+2px 内缩，不悬浮在元素上方），大字号+白边增强可读性
    b.style.cssText = `position:absolute;left:${r.left + 2}px;top:${r.top + 2}px;` +
      'background:#ff3b30;color:#fff;font:bold 15px/1.3 Consolas,monospace;padding:0 6px;border-radius:4px;' +
      'border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.7);z-index:2147483647;white-space:nowrap;';
    layer.appendChild(b);
  });
  (document.documentElement || document.body).appendChild(layer);
  return { ok: true, count: list.length, elements: list, order: 'visual' };
}

/** SOM 徽标清理（executeScript 注入页面，自包含）：移除全部徽标层（防残留累计） */
function __somRemoveBadges() {
  document.querySelectorAll('#__som_badges__').forEach(l => l.remove());
  return { ok: true };
}

/** SOM 标注截图（P4-SOM：看图选编号）——后台型动作。
 *  流程：注入红色编号徽标（视觉顺序，与快照/点击同序）→ 截图 → 清除徽标。
 *  返回 {ok, data_url, elements:[{index,tag,name,rect}], method}；
 *  data_url 由 bridge 落盘 logs/screenshots/ 并换成文件路径。
 *  用途：视觉模型看图读编号（"编号 N 是什么"）→ 坐标由标注层（rect）负责，模型只选号。 */
async function zSomShot(tabId) {
  const result = { ok: false, error: null, data_url: null, elements: [], method: null };
  try {
    const n = Number(tabId);
    if (!n) return { ok: false, error: '缺少有效的 tab_id（som_shot 需要指定目标标签页）' };
    const tab = await chrome.tabs.get(n);
    let prevActive = null;
    let injected = null;
    try {
      // 0) 先激活目标标签并等画面真实刷新（后台标签可能被休眠冻结——Edge Memory Saver；
      //    激活后立即截会拿到陈旧帧，且徽标注入需与最终截图同状态）
      const winTabs = await chrome.tabs.query({ windowId: tab.windowId, active: true });
      prevActive = winTabs && winTabs[0] ? winTabs[0].id : null;
      if (!tab.active && prevActive !== n) {
        await chrome.tabs.update(n, { active: true });
        await new Promise(r2 => setTimeout(r2, 400)); // 等唤醒/重绘
        try { await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' }); } catch (e) {} // 预热一帧
        await new Promise(r2 => setTimeout(r2, 200));
      }
      // 1) 注入徽标（测量当前可见状态）
      try {
        const r = await chrome.scripting.executeScript({ target: { tabId: n }, func: __somInjectBadges });
        injected = r && r[0] && r[0].result;
      } catch (e) {
        return { ok: false, error: `徽标注入失败: ${e && e.message || e}` };
      }
      // 2) 等徽标渲染后截图
      await new Promise(r2 => setTimeout(r2, 150));
      result.data_url = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
      result.method = 'captureVisibleTab';
    } finally {
      // 3) 清除徽标（无论成败）+ 恢复原激活标签
      try { await chrome.scripting.executeScript({ target: { tabId: n }, func: __somRemoveBadges }); } catch (e) {}
      if (prevActive && prevActive !== n) {
        try { await chrome.tabs.update(prevActive, { active: true }); } catch (e) {}
      }
    }
    if (!result.data_url) return { ok: false, error: 'som_shot 截图失败（captureVisibleTab 无返回）' };
    result.ok = true;
    result.elements = (injected && injected.elements) || [];
    result.order = 'visual';
    result.tab_id = n;
  } catch (e) {
    result.error = String(e && e.message || e);
    result.ok = false;
  }
  return result;
}

// ============================================================
// 任务分发：action -> 工具函数
// ============================================================

const TOOL_FUNCS = {
  snapshot: zSnapshot,
  click: zClick,
  click_by_text: zClickByText,
  type: zType,
  scroll: zScroll,
  navigate: zNavigate,
  extract: zExtract,
  verify_site: zVerifySite,
  list_tabs: zListTabs,
  new_tab: zNewTab,
  switch_tab: zSwitchTab,
  close_tab: zCloseTab,
  screenshot: zScreenshot,
  som_shot: zSomShot,
};

// 后台型动作：不注入页面，在 background 直接执行（不需要目标标签页）
const BACKGROUND_ACTIONS = new Set(['list_tabs', 'new_tab', 'switch_tab', 'close_tab', 'screenshot', 'som_shot']);

// ============================================================
// 桥接服务轮询
// ============================================================

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  return res.json();
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs && tabs.length > 0 ? tabs[0] : null;
}

async function executeOnTab(tab, action, params) {
  const fn = TOOL_FUNCS[action];
  if (!fn) return { ok: false, error: `未知动作: ${action}` };
  // P2-3：后台型动作（多标签）直接在 background 执行，不需要注入目标
  if (BACKGROUND_ACTIONS.has(action)) {
    try {
      if (action === 'new_tab') return await fn(params && params.url);
      if (action === 'switch_tab' || action === 'close_tab' || action === 'screenshot' || action === 'som_shot') return await fn(params && params.tab_id);
      return await fn();
    } catch (e) {
      return { ok: false, error: String(e && e.message || e) };
    }
  }
  // 注入型动作
  const args = [];
  const p = params || {};
  if (action === 'click') args.push(p.index !== undefined ? Number(p.index) : -1);
  if (action === 'click_by_text') args.push(p.text ? String(p.text) : '', p.occurrence ? Number(p.occurrence) : 1);
  if (action === 'type') { args.push(p.index !== undefined ? Number(p.index) : -1, p.text !== undefined ? String(p.text) : ''); }
  if (action === 'scroll') args.push(p.direction ? String(p.direction) : 'down', p.amount !== undefined ? Number(p.amount) : 600);
  if (action === 'navigate') args.push(p.url ? String(p.url) : '');
  if (action === 'extract') args.push(p.anchor_text ? String(p.anchor_text) : '');
  if (action === 'verify_site') args.push(Array.isArray(p.checks) ? p.checks : []);
  if (action === 'snapshot') { /* 无参 */ }
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fn,
      args,
    });
    const r = results && results[0] && results[0].result;
    return r || { ok: false, error: '注入无返回' };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e), code: 'injection-failed' };
  }
}

async function pollOnce() {
  try {
    const data = await fetchJson(`${BRIDGE_URL}/api/task/poll`);
    const task = data && data.task;
    if (!task) return;
    console.log('[browser-agent] 领取任务', task.id, task.action);

    // P2-3：后台型动作（多标签）不需要目标标签页
    if (BACKGROUND_ACTIONS.has(task.action)) {
      const result = await executeOnTab(null, task.action, task.params);
      if (result && result.ok) {
        await report(task.id, true, result, null);
      } else {
        await report(task.id, false, result, (result && result.error) || 'action-failed');
      }
      return;
    }
    // 注入型动作：优先按 params.tab_id 指定目标标签（P2-3），否则用激活标签页
    let tab = null;
    const pinnedTabId = task.params && task.params.tab_id ? Number(task.params.tab_id) : null;
    if (pinnedTabId) {
      try { tab = await chrome.tabs.get(pinnedTabId); } catch (e) { tab = null; }
    }
    if (pinnedTabId && !tab) {
      // T4（G4）：指定标签页已关闭/不存在 → 明确报 tab-lost，绝不静默回退激活页
      // （静默回退会在用户不知情时操作错页面，是可归因性错误，必须显式上报）
      await report(task.id, false, null,
        `tab-lost: 指定的标签页 ${pinnedTabId} 不存在或已关闭（可能被用户手动关闭），请用 list_tabs 重新确认目标标签`);
      return;
    }
    if (!tab) tab = await getActiveTab();
    if (!tab || !tab.id) {
      await report(task.id, false, null, 'no-active-tab');
      return;
    }
    const result = await executeOnTab(tab, task.action, task.params);
    if (result && result.ok) {
      await report(task.id, true, result, null);
    } else {
      await report(task.id, false, result, (result && result.error) || 'action-failed');
    }
  } catch (e) {
    // 桥接服务未启动：静默重试
    console.warn('[browser-agent] 轮询失败', e && e.message || e);
  }
}

async function report(taskId, ok, result, error) {
  try {
    await fetchJson(`${BRIDGE_URL}/api/task/result`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, ok, result, error }),
    });
    console.log('[browser-agent] 任务回报', taskId, ok ? 'done' : 'failed');
  } catch (e) {
    console.warn('[browser-agent] 回报失败', e && e.message || e);
  }
}

// ------------------------------------------------------------
// 轮询保活（MV3 关键修复）
// ------------------------------------------------------------
// MV3 service worker 空闲约 30 秒后会被 Chrome 终止，顶层的 setInterval
// 会随 SW 一起停止，导致轮询静默失效（任务一直 pending）。
// 解决：用 chrome.alarms 周期性唤醒 SW（alarm 触发即事件活动，SW 不会休眠），
// 每次唤醒后立即轮询一次，并重启 setInterval 作为唤醒窗口内的高频轮询。
const ALARM_NAME = 'browser-agent-poll';
let pollTimer = null;

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
  pollOnce(); // 唤醒后立即轮询，不等待第一个 interval
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) startPolling();
});

// 注册保活闹钟：25 秒一次（小于 Chrome 30 秒空闲回收阈值）。
// 注意：Chrome <120 的 alarms 最小周期是 1 分钟，创建失败则降级为 1 分钟。
try {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: 25 / 60 });
} catch (e) {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: 1 });
}

chrome.runtime.onInstalled.addListener(startPolling);
chrome.runtime.onStartup.addListener(startPolling);
startPolling();
console.log(`[browser-agent] 轮询已启动: ${BRIDGE_URL} 每 ${POLL_INTERVAL_MS}ms（alarms 保活）`);
