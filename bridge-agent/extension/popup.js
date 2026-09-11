// popup.js — 小猎跑腿 popup：连接状态 + 任务执行状态 + ⛔ 停止
//
// 2026-09-11 A+B 改版（老板拍板）：
//  · 去掉「⏸ 暂停/继续」—— 那是桥自带 LLM 循环（控制台「▶ 运行 Agent」）时代的东西；
//    小猎现在走的是 /api/task 单动作队列（submit_task），暂停/继续对它没有意义（确定性脚本失败重跑即可）。
//  · 「⛔ 停小猎跑腿」接桥的人工总闸 /api/control/stop：清空待执行队列 + 正在跑的采集脚本
//    在下一个动作前自查收尾。使能条件 = 有任务在执行或排队（不再只看 agent run）。
const BRIDGE_URL = 'http://127.0.0.1:8080';
const statusEl = document.getElementById('status');
const runInfoEl = document.getElementById('run-info');
const resultEl = document.getElementById('result');
const stopBtn = document.getElementById('btn-stop');
let stopArmed = false; // 二次点击确认，避免 popup 里 confirm() 弹窗导致 popup 失焦关闭

async function checkHealth() {
  try {
    const res = await fetch(`${BRIDGE_URL}/api/health`);
    const data = await res.json();
    if (data.ok) {
      statusEl.className = 'ok';
      statusEl.textContent = `🟢 桥接服务已连接 (${BRIDGE_URL})`;
      return true;
    }
    statusEl.className = 'bad';
    statusEl.textContent = '🔴 桥接服务异常';
    return false;
  } catch (e) {
    statusEl.className = 'bad';
    statusEl.textContent = '🔴 桥接服务未启动 — 请运行: python bridge/server.py';
    return false;
  }
}

// 任务执行状态（/api/control/state）：inflight=正在执行的动作，pending=排队中
async function refreshControl() {
  try {
    const res = await fetch(`${BRIDGE_URL}/api/control/state`);
    const data = await res.json();
    const inflight = data.inflight;
    const pending = data.pending || 0;
    if (inflight) {
      runInfoEl.className = 'running';
      runInfoEl.textContent = `⏳ 正在执行：${inflight.action}` +
        (inflight.source ? `（${inflight.source}）` : '');
      stopBtn.disabled = false;
    } else if (pending > 0) {
      runInfoEl.className = 'running';
      runInfoEl.textContent = `⏳ 待执行 ${pending} 个任务`;
      stopBtn.disabled = false;
    } else {
      runInfoEl.className = '';
      runInfoEl.textContent = '空闲（无待执行 / 执行中的任务）';
      stopBtn.disabled = true;
    }
  } catch (e) {
    runInfoEl.className = '';
    runInfoEl.textContent = '无法获取运行状态';
    stopBtn.disabled = true;
  }
}

stopBtn.addEventListener('click', async () => {
  if (!stopArmed) {
    stopArmed = true;
    stopBtn.textContent = '⚠️ 再次点击确认停止';
    resultEl.textContent = '将清空待执行任务，并让正在跑的采集在下一个动作前收尾';
    setTimeout(() => {
      stopArmed = false;
      stopBtn.textContent = '⛔ 停小猎跑腿';
    }, 3000);
    return;
  }
  stopArmed = false;
  stopBtn.textContent = '⛔ 停小猎跑腿';
  resultEl.textContent = '正在发送停止指令…';
  try {
    const res = await fetch(`${BRIDGE_URL}/api/control/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (data.ok) {
      const who = data.inflight ? `正在跑的「${data.inflight.action}」结束后收尾` : '当前无动作在执行';
      resultEl.textContent = `⛔ 已停：清空待执行 ${data.cleared} 个；${who}`;
    } else {
      resultEl.textContent = `❌ 停止失败：${data.error || '未知错误'}`;
    }
  } catch (e) {
    resultEl.textContent = '❌ 桥接服务未连接，无法停止';
  }
  refreshControl();
});

checkHealth();
refreshControl();
setInterval(checkHealth, 5000);
setInterval(refreshControl, 3000);
