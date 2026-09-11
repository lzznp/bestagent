// popup.js — P2 产品化：连接状态 + 运行状态 + 暂停/继续 + 紧急停止（人工介入）
const BRIDGE_URL = 'http://127.0.0.1:8080';
const statusEl = document.getElementById('status');
const runInfoEl = document.getElementById('run-info');
const resultEl = document.getElementById('result');
const stopBtn = document.getElementById('btn-stop');
const pauseBtn = document.getElementById('btn-pause');
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

async function refreshRunInfo() {
  try {
    const res = await fetch(`${BRIDGE_URL}/api/agent/runs`);
    const data = await res.json();
    const running = (data.runs || []).filter(r => r.status === 'running');
    if (running.length > 0) {
      const r = running[0];
      const task = (r.task || '').slice(0, 26);
      if (r.paused) {
        runInfoEl.className = 'running';
        runInfoEl.textContent = `⏸ 已暂停：${task}`;
        pauseBtn.disabled = false;
        pauseBtn.textContent = '▶ 继续';
      } else {
        runInfoEl.className = 'running';
        runInfoEl.textContent = `⏳ 运行中：${task}`;
        pauseBtn.disabled = false;
        pauseBtn.textContent = '⏸ 暂停';
      }
      stopBtn.disabled = false;
    } else {
      runInfoEl.className = '';
      runInfoEl.textContent = '当前无运行中的 Agent 任务';
      pauseBtn.disabled = true;
      pauseBtn.textContent = '⏸ 暂停';
      stopBtn.disabled = true;
    }
  } catch (e) {
    runInfoEl.className = '';
    runInfoEl.textContent = '无法获取运行状态';
  }
}

async function sendControl(action, successText) {
  resultEl.textContent = '正在发送指令…';
  try {
    const res = await fetch(`${BRIDGE_URL}/api/agent/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (data.ok) resultEl.textContent = successText;
    else resultEl.textContent = `❌ ${data.error || '未知错误'}`;
  } catch (e) {
    resultEl.textContent = '❌ 桥接服务未连接，无法操作';
  }
  refreshRunInfo();
}

pauseBtn.addEventListener('click', () => {
  const paused = pauseBtn.textContent.includes('继续');
  sendControl(paused ? 'resume' : 'pause',
    paused ? '▶ 已发送继续指令，任务将恢复运行' : '⏸ 已发送暂停指令，将在当前步骤结束后暂停');
});

stopBtn.addEventListener('click', async () => {
  if (!stopArmed) {
    stopArmed = true;
    stopBtn.textContent = '⚠️ 再次点击确认停止';
    resultEl.textContent = '将停止当前 Agent 任务（当前步骤结束后生效）';
    setTimeout(() => {
      stopArmed = false;
      stopBtn.textContent = '⛔ 紧急停止';
    }, 3000);
    return;
  }
  stopArmed = false;
  stopBtn.textContent = '⛔ 紧急停止';
  resultEl.textContent = '正在发送停止指令…';
  try {
    const res = await fetch(`${BRIDGE_URL}/api/agent/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (data.ok) {
      resultEl.textContent = `⛔ 停止指令已发送（run ${data.run_id}），将在当前步骤结束后停止`;
    } else {
      resultEl.textContent = `❌ 停止失败：${data.error || '未知错误'}`;
    }
  } catch (e) {
    resultEl.textContent = '❌ 桥接服务未连接，无法停止';
  }
  refreshRunInfo();
});

checkHealth();
refreshRunInfo();
setInterval(checkHealth, 5000);
setInterval(refreshRunInfo, 3000);
