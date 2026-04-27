let configsData = [];
let defaultsData = {};
let _netMaxKB = 128;

// DOM Cache & State
const domCache = new Map();
function getEl(id) {
  if (!domCache.has(id)) {
    const el = document.getElementById(id);
    if (el) domCache.set(id, el);
    return el;
  }
  return domCache.get(id);
}

const uiState = {
  cpu: null,
  mem: null,
  upPct: null,
  downPct: null,
  memDetail: null,
  upSpeed: null,
  downSpeed: null,
  diskPct: null,
  diskDetail: null,
  uptime: null,
  lastPorts: []
};

function setTheme(theme) {
  document.documentElement.className = 'theme-' + theme;
  localStorage.setItem('theme', theme);
  const themeToggle = getEl('theme-toggle');
  if (themeToggle) themeToggle.checked = (theme === 'light');

  // If chart exists, re-init to pick up new colors
  if (trafficChart) {
    trafficChart.destroy();
    initChart();
  }
  // Re-draw gauges
  Object.keys(gaugeValues).forEach(k => {
    updateGauge(k + 'Gauge', gaugeValues[k], k);
  });
}

function setReducedMotion(enabled) {
  if (enabled) document.body.classList.add('reduced-motion');
  else document.body.classList.remove('reduced-motion');
  localStorage.setItem('reduced_motion', enabled ? '1' : '0');
}

function getThemeVars() {
  const isLight = document.documentElement.classList.contains('theme-light');
  return {
    gaugeInnerBg: isLight ? '#ffffff' : '#1e1e26',
    gaugeRingBorder: isLight ? '#e0e0e0' : '#2d2d3d',
    gaugeEmptyTick: isLight ? '#f0f0f0' : '#2d2d3d',
    gaugeText: isLight ? '#121212' : '#ffffff',
    gaugeUnitText: isLight ? '#757575' : '#9499b3',
    chartGrid: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)',
    chartText: isLight ? '#666' : '#9499b3'
  };
}

let _pollTimer = null;
function startPolling(interval) {
  stopPolling();
  _pollTimer = setInterval(pollStatus, interval);
}
function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

function genUuid(inputName) {
  const input = document.querySelector(`input[name="${inputName}"]`);
  if (input) {
    input.value = crypto.randomUUID();
  }
}

function switchCertTab(tab) {
  document.querySelectorAll('.cert-panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.cert-tab').forEach(b => b.classList.remove('cert-tab--active'));
  const panel = getEl('cert-panel-' + tab);
  if (panel) panel.style.display = '';
  const btn = document.querySelector('.cert-tab[data-tab="' + tab + '"]');
  if (btn) btn.classList.add('cert-tab--active');
}

function openEditModal(editId) {
  const form = getEl('configForm');
  let data = defaultsData;

  if (editId !== 'new') {
    const found = configsData.find(c => c.id === editId);
    if (found) { data = Object.assign({}, defaultsData, found); }
    const title = getEl('edit-modal-title');
    if (title) title.textContent = 'Edit Configuration';
  } else {
    const title = getEl('edit-modal-title');
    if (title) title.textContent = 'New Configuration';
  }

  form.elements['edit_id'].value = editId === 'new' ? '' : editId;
  form.elements['name'].value = data.name || '';
  form.elements['domain'].value = data.domain || '';
  form.elements['protocol'].value = data.protocol || 'vless';

  form.elements['network_security'].value = data.tls_enabled ? 'tls' : 'ws';

  form.elements['ws_host'].value = data.ws_host || data.domain || '';
  form.elements['ws_port'].value = data.ws_port || '';
  form.elements['ws_path'].value = data.ws_path || '';
  form.elements['ws_uuid'].value = data.ws_uuid || '';
  form.elements['ws_email'].value = data.ws_email || '';

  form.elements['tls_host'].value = data.tls_host || data.domain || '';
  form.elements['tls_port'].value = data.tls_port || '';
  form.elements['tls_path'].value = data.tls_path || '';
  form.elements['tls_uuid'].value = data.tls_uuid || '';
  form.elements['tls_email'].value = data.tls_email || '';
  form.elements['tls_cert'].value = data.tls_cert || '';
  form.elements['tls_key'].value = data.tls_key || '';
  form.elements['fingerprint'].value = data.fingerprint || 'randomized';
  form.elements['alpn'].value = data.alpn || 'h2,h3,http/1.1';
  form.elements['dns'].value = data.dns || '1.1.1.1';

  toggleTransport();
  const scrim = getEl('edit-modal-scrim');
  if (scrim) scrim.style.display = 'flex';
}

let trafficChart;
const maxDataPoints = 30;
const trafficLabels = Array(maxDataPoints).fill('');
const upData = Array(maxDataPoints).fill(0);
const downData = Array(maxDataPoints).fill(0);
const gaugeValues = { cpu: 0, mem: 0, upload: 0, download: 0 };
const gaugeRequestIds = {};

function drawSegmentedGauge(canvasId, value, color, label) {
  const canvas = getEl(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  const cx = W / 2;
  const cy = H / 2;
  const themeVars = getThemeVars();

  ctx.clearRect(0, 0, W, H);

  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, W, H);
  ctx.clip();

  const totalTicks = 60;
  const filledTicks = Math.round((value / 100) * totalTicks);
  const isNetwork = (canvasId === 'uploadGauge' || canvasId === 'downloadGauge');

  const scale = Math.min(W, H) / 180;
  const ringInner = Math.round(62 * scale);
  const ringOuter = Math.round(78 * scale);
  const shortOuter = Math.round(73 * scale);

  // Background ring
  ctx.beginPath();
  ctx.arc(cx, cy, (ringInner + ringOuter) / 2, 0, Math.PI * 2);
  ctx.strokeStyle = themeVars.gaugeEmptyTick;
  ctx.lineWidth = ringOuter - ringInner;
  ctx.stroke();

  // Progress ring with gradient
  if (filledTicks > 0) {
    const startAngle = -Math.PI / 2;
    const endAngle = startAngle + (value / 100) * Math.PI * 2;

    ctx.beginPath();
    ctx.arc(cx, cy, (ringInner + ringOuter) / 2, startAngle, endAngle);

    const gradient = ctx.createSweepGradient ? ctx.createSweepGradient(cx, cy) : null;
    if (gradient) {
        gradient.addColorStop(0, color);
        gradient.addColorStop(1, color);
        ctx.strokeStyle = gradient;
    } else {
        ctx.strokeStyle = color;
    }

    ctx.lineCap = 'round';
    ctx.lineWidth = ringOuter - ringInner;
    ctx.shadowColor = color;
    ctx.shadowBlur = 10 * scale;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // Segmented Ticks (Overlay)
  for (let i = 0; i < totalTicks; i++) {
    const angle = (i / totalTicks) * Math.PI * 2 - Math.PI / 2;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.fillStyle = themeVars.gaugeInnerBg;
    // Tick width of 2px for segmentation
    ctx.fillRect(ringInner - 2, -1, (ringOuter - ringInner) + 4, 2);
    ctx.restore();
  }

  ctx.restore();
  ctx.shadowColor = 'transparent';
  ctx.shadowBlur = 0;

  // Inner Circle
  ctx.beginPath();
  ctx.arc(cx, cy, ringInner - Math.round(4 * scale), 0, Math.PI * 2);
  ctx.fillStyle = themeVars.gaugeInnerBg;
  ctx.fill();

  ctx.beginPath();
  ctx.arc(cx, cy, ringInner - Math.round(4 * scale), 0, Math.PI * 2);
  ctx.strokeStyle = themeVars.gaugeRingBorder;
  ctx.lineWidth = 1;
  ctx.stroke();

  const numStr = isNetwork ? value.toFixed(1) : Math.round(value).toString();
  const unitStr = isNetwork ? 'KB/s' : '%';
  const fontSize = Math.round(30 * scale);
  const unitSize = Math.round(13 * scale);
  const numOffsetY = Math.round(8 * scale);
  const unitOffsetY = Math.round(14 * scale);

  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  ctx.font = `bold ${fontSize}px "Roboto", sans-serif`;
  ctx.fillStyle = themeVars.gaugeText;
  ctx.shadowColor = color;
  ctx.shadowBlur = 5 * scale;
  ctx.fillText(numStr, cx, cy - numOffsetY);

  ctx.font = `500 ${unitSize}px "Roboto", sans-serif`;
  ctx.fillStyle = themeVars.gaugeUnitText;
  ctx.shadowBlur = 0;
  ctx.shadowColor = 'transparent';
  ctx.fillText(unitStr, cx, cy + unitOffsetY);
}

function updateGauge(canvasId, value, type) {
  if (gaugeValues[type] === value) return;
  gaugeValues[type] = value;

  if (gaugeRequestIds[canvasId]) cancelAnimationFrame(gaugeRequestIds[canvasId]);

  gaugeRequestIds[canvasId] = requestAnimationFrame(() => {
    let color;
    switch (type) {
      case 'cpu': color = '#00ff88'; break;
      case 'mem': color = '#ff2d6f'; break;
      case 'upload': color = '#bb86fc'; break;
      case 'download': color = '#00cfff'; break;
      default: color = '#00cfff';
    }
    drawSegmentedGauge(canvasId, value, color, type);
    delete gaugeRequestIds[canvasId];
  });
}

function initChart() {
  const themeVars = getThemeVars();
  updateGauge('cpuGauge', 0, 'cpu');
  updateGauge('memGauge', 0, 'mem');
  updateGauge('uploadGauge', 0, 'upload');
  updateGauge('downloadGauge', 0, 'download');

  const chartEl = getEl('trafficChart');
  if (!chartEl) return;
  const ctx = chartEl.getContext('2d');

  const upGradient = ctx.createLinearGradient(0, 0, 0, 400);
  upGradient.addColorStop(0, 'rgba(187, 134, 252, 0.4)');
  upGradient.addColorStop(1, 'rgba(187, 134, 252, 0)');

  const downGradient = ctx.createLinearGradient(0, 0, 0, 400);
  downGradient.addColorStop(0, 'rgba(3, 218, 198, 0.4)');
  downGradient.addColorStop(1, 'rgba(3, 218, 198, 0)');

  trafficChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: trafficLabels,
      datasets: [
        {
          label: 'Upload (KB/s)',
          data: upData,
          borderColor: '#bb86fc',
          backgroundColor: upGradient,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.4,
          fill: true
        },
        {
          label: 'Download (KB/s)',
          data: downData,
          borderColor: '#03dac6',
          backgroundColor: downGradient,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.4,
          fill: true
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 0 },
      scales: {
        x: { display: false },
        y: {
          beginAtZero: true,
          grid: { color: themeVars.chartGrid, drawTicks: false },
          ticks: { color: themeVars.chartText, font: { size: 10 } }
        }
      },
      plugins: {
        legend: {
            position: 'top',
            align: 'end',
            labels: {
                color: themeVars.chartText,
                boxWidth: 8,
                boxHeight: 8,
                usePointStyle: true,
                font: { size: 11 }
            }
        }
      }
    }
  });
}

async function pollStatus() {
  try {
    const res = await fetch('/status');
    const data = await res.json();

    const si = data.sys_info || {};
    const cpuValue = parseFloat(si.cpu) || 0;
    const memValue = parseFloat(si.mem) || 0;

    _netMaxKB = Math.max(_netMaxKB * 0.95, data.up_raw, data.down_raw, 128);
    const upPct   = Math.min((data.up_raw   / _netMaxKB) * 100, 100);
    const downPct = Math.min((data.down_raw / _netMaxKB) * 100, 100);

    updateGauge('cpuGauge',       Math.min(cpuValue, 100), 'cpu');
    updateGauge('memGauge',       memValue,                'mem');
    updateGauge('uploadGauge',    upPct,                   'upload');
    updateGauge('downloadGauge',  downPct,                 'download');

    // Gauge sublabels with dirty checking
    const memDetailVal = `${si.mem_used_str} / ${si.mem_total_str}`;
    if (uiState.memDetail !== memDetailVal) {
      const el = getEl('mem-detail');
      if (el) el.textContent = memDetailVal;
      uiState.memDetail = memDetailVal;
    }

    if (uiState.upSpeed !== data.up_speed) {
      const el = getEl('up-speed-label');
      if (el) el.textContent = data.up_speed || '';
      const netUp = getEl('net-up');
      if (netUp) netUp.textContent = data.up_speed || '—';
      uiState.upSpeed = data.up_speed;
    }

    if (uiState.downSpeed !== data.down_speed) {
      const el = getEl('down-speed-label');
      if (el) el.textContent = data.down_speed || '';
      const netDown = getEl('net-down');
      if (netDown) netDown.textContent = data.down_speed || '—';
      uiState.downSpeed = data.down_speed;
    }

    // Disk
    if (si.disk_pct !== undefined && uiState.diskPct !== si.disk_pct) {
      const elPct = getEl('disk-pct');
      if (elPct) elPct.textContent = si.disk_pct + '%';
      const elBar = getEl('disk-bar');
      if (elBar) elBar.style.width = si.disk_pct + '%';
      uiState.diskPct = si.disk_pct;
    }

    const diskDetailVal = `${si.disk_used_str} / ${si.disk_total_str}`;
    if (si.disk_used_str && uiState.diskDetail !== diskDetailVal) {
      const el = getEl('disk-detail');
      if (el) el.textContent = diskDetailVal;
      uiState.diskDetail = diskDetailVal;
    }

    // Uptime
    if (si.uptime_str && uiState.uptime !== si.uptime_str) {
      const el = getEl('dash-uptime');
      if (el) el.textContent = si.uptime_str;
      uiState.uptime = si.uptime_str;
    }

    // Traffic chart
    if (trafficChart) {
      upData.shift(); upData.push(data.up_raw);
      downData.shift(); downData.push(data.down_raw);
      trafficChart.update('none'); // Update without animation
    }

    // Per-config traffic table
    if (data.xray_stats) {
      document.querySelectorAll('.dash-traffic-row').forEach(row => {
        const email = row.getAttribute('data-email');
        const port = parseInt(row.getAttribute('data-port'));
        const stats = data.xray_stats[email];
        const usageEl = row.querySelector('.dash-traffic-usage');
        const speedEl = row.querySelector('.dash-traffic-speed');
        const dotEl = row.querySelector('.dash-status-dot');
        const active = data.active_ports && data.active_ports.includes(port);

        if (dotEl) {
           const currentClass = dotEl.className;
           const targetClass = 'dash-status-dot ' + (active ? 'green' : 'grey');
           if (currentClass !== targetClass) dotEl.className = targetClass;
        }
        if (stats) {
          if (usageEl && usageEl.textContent !== stats.total_str) usageEl.textContent = stats.total_str;
          if (speedEl && speedEl.textContent !== stats.speed_str) speedEl.textContent = stats.speed_str;
        }
      });
    }

    // Update individual config cards
    document.querySelectorAll('.config-card').forEach(card => {
      const wsEmail = card.getAttribute('data-ws-email');
      const tlsEmail = card.getAttribute('data-tls-email');
      const wsPort = parseInt(card.getAttribute('data-ws-port'));
      const tlsPort = parseInt(card.getAttribute('data-tls-port'));

      const wsActive = data.active_ports && data.active_ports.includes(wsPort);
      const tlsActive = data.active_ports && data.active_ports.includes(tlsPort);
      const isActive = wsActive || tlsActive;

      const dot = card.querySelector('.status-dot');
      const txt = card.querySelector('.status-text');
      const usage = card.querySelector('.config-usage');

      if (dot) {
        const targetDotClass = 'status-dot ' + (isActive ? 'green' : 'grey');
        if (dot.className !== targetDotClass) dot.className = targetDotClass;
      }
      if (txt) {
        const targetTxt = isActive ? 'Active' : 'Idle';
        if (txt.textContent !== targetTxt) {
          txt.textContent = targetTxt;
          txt.className = 'status-text ' + (isActive ? 'text-success' : 'text-muted');
        }
      }

      let combinedUsage = '';
      if (data.xray_stats) {
        if (wsEmail && data.xray_stats[wsEmail]) combinedUsage += data.xray_stats[wsEmail].total_str;
        if (tlsEmail && data.xray_stats[tlsEmail]) {
          if (combinedUsage) combinedUsage += ' / ';
          combinedUsage += data.xray_stats[tlsEmail].total_str;
        }
      }
      if (usage && usage.textContent !== combinedUsage) usage.textContent = combinedUsage;
    });

  } catch (e) {
    console.error('Poll failed', e);
  }
}

// ── Shared Helper Functions ───────────────────────────────────
function getUuidFromUrl(url) {
  const match = url.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  return match ? match[0] : null;
}

function formatUuid(uuid) {
  if (!uuid) return '';
  const hex = uuid.replace(/-/g, '');
  if (hex.length !== 32) return uuid;
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function copyUrl(button) {
  let input = null;
  const container = button.parentElement;
  if (container) {
    input = container.querySelector('input[type="text"]');
  }
  if (!input) {
    input = button.closest('.share-url-container').querySelector('input[type="text"]');
  }
  if (!input) {
    input = button.closest('.share-item').querySelector('input[type="text"]');
  }
  if (!input || !input.value) {
    console.error('Input field or value not found');
    return;
  }

  const urlText = input.value;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(urlText)
      .then(() => {
        showCopySuccess(button);
      })
      .catch(() => {
        fallbackCopy(input, button);
      });
  } else {
    fallbackCopy(input, button);
  }
}

function fallbackCopy(input, button) {
  try {
    input.select();
    input.setSelectionRange(0, 99999);
    document.execCommand('copy');
    showCopySuccess(button);
  } catch (err) {
    console.error('Fallback copy failed:', err);
    alert('Copy failed. Please try again.');
  }
}

function showCopySuccess(button) {
  const icon = button.querySelector('i');
  const origText = icon.textContent;
  icon.textContent = 'check';
  button.style.color = 'var(--mdc-theme-success)';

  setTimeout(() => {
    icon.textContent = origText;
    button.style.color = '';
  }, 2000);
}

function closeModal(event) {
  if (event.target.classList.contains("mdc-dialog-scrim") && event.target.id === "edit-modal-scrim") {
    getEl("edit-modal-scrim").style.display = "none";
  } else if (event.target.classList.contains("mdc-dialog-scrim") && event.target.id !== "qr-modal-scrim") {
    getEl("edit-modal-scrim").style.display = "none";
  }
}

function closeModalDirect() {
  getEl("edit-modal-scrim").style.display = "none";
}

function openQrModal(src) {
  getEl("qr-modal-img").src = src;
  getEl("qr-modal-scrim").style.display = "flex";
}

function closeQrModal(event) {
  if (event.target.id === "qr-modal-scrim") {
    getEl("qr-modal-scrim").style.display = "none";
  }
}

function closeQrModalDirect() {
  getEl("qr-modal-scrim").style.display = "none";
}

function toggleTransport() {
  const select = document.querySelector('select[name="network_security"]');
  const wsSection = getEl('ws_section');
  const tlsSection = getEl('tls_section');
  if (select && wsSection && tlsSection) {
    if (select.value === 'ws') {
      wsSection.style.display = 'block';
      tlsSection.style.display = 'none';
    } else {
      wsSection.style.display = 'none';
      tlsSection.style.display = 'block';
    }
  }
}

const themeToggle = getEl('theme-toggle');
const motionToggle = getEl('motion-toggle');
const refreshToggle = getEl('refresh-toggle');
const refreshInterval = getEl('refresh-interval');

const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
const storedTheme = localStorage.getItem('theme');
const initialTheme = storedTheme || (prefersLight ? 'light' : 'dark');
setTheme(initialTheme);
if (themeToggle) {
  themeToggle.checked = initialTheme === 'light';
  themeToggle.addEventListener('change', (e) => {
    setTheme(e.target.checked ? 'light' : 'dark');
  });
}

const storedMotion = localStorage.getItem('reduced_motion') === '1';
setReducedMotion(storedMotion);
if (motionToggle) {
  motionToggle.checked = storedMotion;
  motionToggle.addEventListener('change', (e) => {
    setReducedMotion(e.target.checked);
  });
}

const storedRefreshEnabled = localStorage.getItem('refresh_enabled');
const refreshEnabled = storedRefreshEnabled !== '0';
const storedInterval = parseInt(localStorage.getItem('refresh_interval') || '3000', 10);
if (refreshToggle) {
  refreshToggle.checked = refreshEnabled;
  refreshToggle.addEventListener('change', (e) => {
    const enabled = e.target.checked;
    localStorage.setItem('refresh_enabled', enabled ? '1' : '0');
    if (enabled) {
      startPolling(parseInt(refreshInterval.value, 10));
      pollStatus();
    } else {
      stopPolling();
    }
  });
}
if (refreshInterval) {
  refreshInterval.value = String(storedInterval);
  refreshInterval.addEventListener('change', (e) => {
    const intervalMs = parseInt(e.target.value, 10);
    localStorage.setItem('refresh_interval', String(intervalMs));
    if (refreshToggle && refreshToggle.checked) {
      startPolling(intervalMs);
    }
  });
}

if (refreshEnabled && getEl('trafficChart')) {
  startPolling(storedInterval);
  pollStatus();
}

// ── Log Viewer ────────────────────────────────────────────────
let _logEs = null;
let _currentLogType = 'access';

function switchLog(type, btn) {
  document.querySelectorAll('.log-tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  _currentLogType = type;
  const viewer = getEl('log-viewer');
  if (viewer) viewer.innerHTML = '';
  if (getEl('log-live-toggle')?.checked) {
    startLogStream(type);
  }
}

function startLogStream(type) {
  if (_logEs) { _logEs.close(); _logEs = null; }
  const viewer = getEl('log-viewer');
  if (!viewer) return;

  _logEs = new EventSource(`/logs/stream/${type}`);
  _logEs.onmessage = function (e) {
    if (!e.data || e.data === 'ping') return;
    const line = document.createElement('div');
    line.className = 'log-line';
    const lower = e.data.toLowerCase();
    if (lower.includes('error') || lower.includes('fail')) line.classList.add('log-line--error');
    else if (lower.includes('warn')) line.classList.add('log-line--warn');
    line.textContent = e.data;
    viewer.appendChild(line);
    viewer.scrollTop = viewer.scrollHeight;
  };
}

function clearLogView() {
  const viewer = getEl('log-viewer');
  if (viewer) viewer.innerHTML = '';
}

const logLiveToggle = getEl('log-live-toggle');
if (logLiveToggle) {
  if (logLiveToggle.checked) startLogStream(_currentLogType);
  logLiveToggle.addEventListener('change', e => {
    if (e.target.checked) {
      startLogStream(_currentLogType);
    } else {
      if (_logEs) { _logEs.close(); _logEs = null; }
    }
  });
}

// ── Config Validate ───────────────────────────────────────────
async function validateConfig() {
  const btn = document.querySelector('[onclick="validateConfig()"]');
  const result = getEl('validate-result');
  if (!result) return;
  if (btn) btn.disabled = true;
  result.style.display = 'block';
  result.style.background = 'var(--mdc-theme-surface-2)';
  result.style.color = 'var(--mdc-theme-text-secondary-on-background)';
  result.textContent = 'Validating...';
  try {
    const res = await fetch('/config/validate', { method: 'POST' });
    const data = await res.json();
    result.textContent = data.msg;
    result.style.background = data.ok
      ? 'rgba(76,175,80,0.12)'
      : 'rgba(207,102,121,0.12)';
    result.style.color = data.ok
      ? 'var(--mdc-theme-success)'
      : 'var(--mdc-theme-error)';
  } catch {
    result.textContent = 'Request failed.';
    result.style.color = 'var(--mdc-theme-error)';
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Xray version switch with download progress
const switchForm = document.querySelector('form[action="/xray/switch"]');
if (switchForm) {
  switchForm.addEventListener('submit', function (e) {
    const select = switchForm.querySelector('select[name="xray_version"]');
    if (!select) return;
    const selectedOption = select.options[select.selectedIndex];
    const needsDownload = selectedOption && selectedOption.text.includes('(will download)');
    if (!needsDownload) return;

    e.preventDefault();
    const versionKey = select.value;
    openDownloadModal(versionKey);
  });
}

function openDownloadModal(versionKey) {
  const scrim = getEl('dl-modal-scrim');
  const title = getEl('dl-modal-title');
  const statusEl = getEl('dl-modal-status');
  const bar = getEl('dl-progress-bar');
  const pctEl = getEl('dl-progress-pct');

  title.textContent = `Installing Xray ${versionKey}`;
  statusEl.textContent = 'Connecting...';
  bar.style.width = '0%';
  pctEl.textContent = '';
  scrim.style.display = 'flex';

  const es = new EventSource(`/xray/install-stream/${encodeURIComponent(versionKey)}`);

  es.onmessage = function (event) {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    if (data.type === 'progress' || data.type === 'status') {
      statusEl.textContent = data.msg || '';
      if (typeof data.pct === 'number') {
        bar.style.width = data.pct + '%';
        pctEl.textContent = data.pct + '%';
      }
    } else if (data.type === 'done') {
      bar.style.width = '100%';
      pctEl.textContent = '100%';
      statusEl.textContent = data.msg || 'Done!';
      es.close();
      setTimeout(() => {
        scrim.style.display = 'none';
        window.location.href = '/settings?message=' + encodeURIComponent(data.msg || 'Switched successfully.');
      }, 800);
    } else if (data.type === 'error') {
      statusEl.textContent = '⚠ ' + (data.msg || 'Download failed.');
      bar.style.background = 'var(--mdc-theme-error, #cf6679)';
      es.close();
      setTimeout(() => {
        scrim.style.display = 'none';
        bar.style.background = '';
        window.location.href = '/settings?error=' + encodeURIComponent(data.msg || 'Failed.');
      }, 2000);
    }
  };

  es.onerror = function () {
    statusEl.textContent = 'Connection lost. Please try again.';
    es.close();
  };
}
