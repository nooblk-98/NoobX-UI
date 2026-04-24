const configsData = window.CONFIGS_DATA || [];
const defaultsData = window.DEFAULTS_DATA || {};
let pollIntervalId = null;

function getThemeVars() {
  const styles = getComputedStyle(document.documentElement);
  return {
    gaugeInnerBg: styles.getPropertyValue('--gauge-inner-bg').trim() || '#1a1a2e',
    gaugeEmptyTick: styles.getPropertyValue('--gauge-empty-tick').trim() || 'rgba(255,255,255,0.10)',
    gaugeRingBorder: styles.getPropertyValue('--gauge-ring-border').trim() || 'rgba(255,255,255,0.06)',
    gaugeText: styles.getPropertyValue('--gauge-text').trim() || '#ffffff',
    gaugeUnitText: styles.getPropertyValue('--gauge-unit-text').trim() || 'rgba(255,255,255,0.60)',
    chartGrid: styles.getPropertyValue('--chart-grid').trim() || 'rgba(255,255,255,0.1)',
    chartText: styles.getPropertyValue('--chart-text').trim() || 'rgba(255,255,255,0.7)'
  };
}

function openEditModal(editId) {
  const form = document.getElementById('configForm');
  let data = defaultsData;

  if (editId !== 'new') {
    const found = configsData.find(c => c.id === editId);
    if (found) { data = Object.assign({}, defaultsData, found); }
    document.getElementById('edit-modal-title').textContent = 'Edit Configuration';
  } else {
    document.getElementById('edit-modal-title').textContent = 'New Configuration';
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
  document.getElementById('edit-modal-scrim').style.display = 'flex';
}

let trafficChart;
const maxDataPoints = 30;
const trafficLabels = Array(maxDataPoints).fill('');
const upData = Array(maxDataPoints).fill(0);
const downData = Array(maxDataPoints).fill(0);
const gaugeValues = { cpu: 0, mem: 0, upload: 0, download: 0 };

function drawSegmentedGauge(canvasId, value, color, label) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  const cx = W / 2;
  const cy = H / 2;
  const themeVars = getThemeVars();

  ctx.clearRect(0, 0, W, H);

  const totalTicks = 60;
  const filledTicks = Math.round((value / 100) * totalTicks);
  const isNetwork = (canvasId === 'uploadGauge' || canvasId === 'downloadGauge');

  const ringInner = 62;
  const ringOuter = 84;
  const shortOuter = 79;

  for (let i = 0; i < totalTicks; i++) {
    const angle = (i / totalTicks) * Math.PI * 2 - Math.PI / 2;
    const filled = i < filledTicks;

    const innerR = ringInner;
    const outerR = filled ? ringOuter : shortOuter;
    const tickLen = outerR - innerR;
    const tickW = filled ? 3.5 : 2;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);

    if (filled) {
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 14;
      ctx.fillRect(innerR, -tickW / 2, tickLen, tickW);
    } else {
      ctx.shadowBlur = 0;
      ctx.shadowColor = 'transparent';
      ctx.fillStyle = themeVars.gaugeEmptyTick;
      ctx.fillRect(innerR, -tickW / 2, tickLen, tickW);
    }
    ctx.restore();
  }

  ctx.shadowColor = 'transparent';
  ctx.shadowBlur = 0;

  ctx.beginPath();
  ctx.arc(cx, cy, ringInner - 4, 0, Math.PI * 2);
  ctx.fillStyle = themeVars.gaugeInnerBg;
  ctx.fill();

  ctx.beginPath();
  ctx.arc(cx, cy, ringInner - 4, 0, Math.PI * 2);
  ctx.strokeStyle = themeVars.gaugeRingBorder;
  ctx.lineWidth = 1;
  ctx.stroke();

  const numStr = isNetwork ? value.toFixed(1) : Math.round(value).toString();
  const unitStr = isNetwork ? 'KB/s' : '%';

  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  ctx.font = 'bold 30px "Roboto", sans-serif';
  ctx.fillStyle = themeVars.gaugeText;
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;
  ctx.fillText(numStr, cx, cy - 8);

  ctx.font = '500 13px "Roboto", sans-serif';
  ctx.fillStyle = themeVars.gaugeUnitText;
  ctx.shadowBlur = 0;
  ctx.shadowColor = 'transparent';
  ctx.fillText(unitStr, cx, cy + 14);
}

function updateGauge(canvasId, value, type) {
  gaugeValues[type] = value;

  let color;
  switch (type) {
    case 'cpu': color = '#00ff88'; break;
    case 'mem': color = '#ff2d6f'; break;
    case 'upload': color = '#bb86fc'; break;
    case 'download': color = '#00cfff'; break;
    default: color = '#00cfff';
  }

  drawSegmentedGauge(canvasId, value, color, type);
}

function initChart() {
  const themeVars = getThemeVars();
  updateGauge('cpuGauge', 0, 'cpu');
  updateGauge('memGauge', 0, 'mem');
  updateGauge('uploadGauge', 0, 'upload');
  updateGauge('downloadGauge', 0, 'download');

  const ctx = document.getElementById('trafficChart').getContext('2d');
  trafficChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: trafficLabels,
      datasets: [
        {
          label: 'Upload (KB/s)',
          data: upData,
          borderColor: 'rgba(187, 134, 252, 1)',
          backgroundColor: 'rgba(187, 134, 252, 0.2)',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.4,
          fill: true
        },
        {
          label: 'Download (KB/s)',
          data: downData,
          borderColor: 'rgba(3, 218, 198, 1)',
          backgroundColor: 'rgba(3, 218, 198, 0.2)',
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
          grid: { color: themeVars.chartGrid },
          ticks: { color: themeVars.chartText }
        }
      },
      plugins: {
        legend: { labels: { color: themeVars.chartText } }
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

    updateGauge('cpuGauge', Math.min(cpuValue, 100), 'cpu');
    updateGauge('memGauge', memValue, 'mem');
    updateGauge('uploadGauge', Math.min((data.up_raw / 100), 100), 'upload');
    updateGauge('downloadGauge', Math.min((data.down_raw / 100), 100), 'download');

    // Gauge sublabels
    const memDetail = document.getElementById('mem-detail');
    if (memDetail && si.mem_used_str) memDetail.textContent = `${si.mem_used_str} / ${si.mem_total_str}`;
    const upLabel = document.getElementById('up-speed-label');
    if (upLabel) upLabel.textContent = data.up_speed || '';
    const downLabel = document.getElementById('down-speed-label');
    if (downLabel) downLabel.textContent = data.down_speed || '';

    // Disk
    const diskPct = document.getElementById('disk-pct');
    const diskBar = document.getElementById('disk-bar');
    const diskDetail = document.getElementById('disk-detail');
    if (si.disk_pct !== undefined) {
      if (diskPct) diskPct.textContent = si.disk_pct + '%';
      if (diskBar) diskBar.style.width = si.disk_pct + '%';
      if (diskDetail) diskDetail.textContent = `${si.disk_used_str} / ${si.disk_total_str}`;
    }

    // Network cards
    const netUp = document.getElementById('net-up');
    const netDown = document.getElementById('net-down');
    if (netUp) netUp.textContent = data.up_speed || '—';
    if (netDown) netDown.textContent = data.down_speed || '—';

    // Uptime
    const uptimeEl = document.getElementById('dash-uptime');
    if (uptimeEl && si.uptime_str) uptimeEl.textContent = si.uptime_str;

    // Traffic chart
    if (trafficChart) {
      upData.shift(); upData.push(data.up_raw);
      downData.shift(); downData.push(data.down_raw);
      trafficChart.update();
    }

    // Per-config traffic table
    if (data.xray_stats) {
      document.querySelectorAll('.dash-traffic-row').forEach(row => {
        const email = row.getAttribute('data-email');
        const port = parseInt(row.getAttribute('data-port'));
        const type = row.getAttribute('data-type');
        const stats = data.xray_stats[email];
        const usageEl = row.querySelector('.dash-traffic-usage');
        const speedEl = row.querySelector('.dash-traffic-speed');
        const dotEl = row.querySelector('.dash-status-dot');
        const active = data.active_ports && data.active_ports.includes(port);
        if (dotEl) { dotEl.className = 'dash-status-dot ' + (active ? 'green' : 'grey'); }
        if (stats) {
          if (usageEl) usageEl.textContent = stats.total_str;
          if (speedEl) speedEl.textContent = stats.speed_str;
        }
      });
    }

    // Config cards live status (configurations page)
    if (data.active_ports) {
      document.querySelectorAll('.config-card').forEach(card => {
        const wsPortStr = card.getAttribute('data-ws-port');
        const tlsPortStr = card.getAttribute('data-tls-port');
        const enableWs = card.getAttribute('data-ws-en') === 'True';
        const enableTls = card.getAttribute('data-tls-en') === 'True';
        let isActive = false;
        if (enableWs && wsPortStr && data.active_ports.includes(parseInt(wsPortStr))) isActive = true;
        if (enableTls && tlsPortStr && data.active_ports.includes(parseInt(tlsPortStr))) isActive = true;
        const statusDot = card.querySelector('.config-live-status');
        if (statusDot) {
          statusDot.innerHTML = isActive
            ? '<span class="status-dot green"></span><span class="status-text success-text">Active Link</span>'
            : '<span class="status-dot grey"></span><span class="status-text text-muted">Idle</span>';
        }
        const wsEmailStr = card.getAttribute('data-ws-email');
        const tlsEmailStr = card.getAttribute('data-tls-email');
        const usageSpan = card.querySelector('.config-usage');
        if (usageSpan && data.xray_stats) {
          let usageText = '';
          if (enableWs && wsEmailStr && data.xray_stats[wsEmailStr])
            usageText += `WS: ${data.xray_stats[wsEmailStr].total_str} `;
          if (enableTls && tlsEmailStr && data.xray_stats[tlsEmailStr])
            usageText += `TLS: ${data.xray_stats[tlsEmailStr].total_str}`;
          usageSpan.textContent = usageText.trim();
        }
      });
    }
  } catch (err) {
    console.error('Failed to update status', err);
  }
}

function applyThemeToChart() {
  if (!trafficChart) return;
  const themeVars = getThemeVars();
  trafficChart.options.scales.y.grid.color = themeVars.chartGrid;
  trafficChart.options.scales.y.ticks.color = themeVars.chartText;
  trafficChart.options.plugins.legend.labels.color = themeVars.chartText;
  trafficChart.update();
}

function refreshGaugeTheme() {
  updateGauge('cpuGauge', gaugeValues.cpu, 'cpu');
  updateGauge('memGauge', gaugeValues.mem, 'mem');
  updateGauge('uploadGauge', gaugeValues.upload, 'upload');
  updateGauge('downloadGauge', gaugeValues.download, 'download');
}

function setTheme(mode) {
  const root = document.documentElement;
  const isLight = mode === 'light';
  root.classList.toggle('theme-light', isLight);
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
  applyThemeToChart();
  refreshGaugeTheme();
}

function setReducedMotion(enabled) {
  const root = document.documentElement;
  root.classList.toggle('reduced-motion', enabled);
  localStorage.setItem('reduced_motion', enabled ? '1' : '0');
}

function startPolling(intervalMs) {
  if (pollIntervalId) {
    clearInterval(pollIntervalId);
  }
  pollIntervalId = setInterval(pollStatus, intervalMs);
}

function stopPolling() {
  if (pollIntervalId) {
    clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
}

if (document.getElementById('trafficChart')) {
  initChart();
}

const navItems = document.querySelectorAll('.mdc-list-item');
const sections = document.querySelectorAll('.content-section');
const pageTitle = document.getElementById('page-title');

// Set page title based on active section
function updatePageTitle() {
  sections.forEach(sec => {
    if (sec.classList.contains('active')) {
      const navItem = [...navItems].find(item => 
        item.classList.contains('mdc-list-item--activated')
      );
      if (navItem) {
        pageTitle.textContent = navItem.querySelector('.mdc-list-item__text').textContent;
      }
    }
  });
}

updatePageTitle();

setTimeout(() => {
  const snackbars = document.querySelectorAll('.mdc-snackbar');
  snackbars.forEach(s => s.style.opacity = '0');
  setTimeout(() => snackbars.forEach(s => s.remove()), 300);
}, 3000);

function genUuid(field) {
  const input = document.querySelector(`input[name="${field}"]`);
  if (!input) return;
  if (window.crypto?.randomUUID) {
    input.value = window.crypto.randomUUID();
    return;
  }
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  input.value = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
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
    document.getElementById("edit-modal-scrim").style.display = "none";
  } else if (event.target.classList.contains("mdc-dialog-scrim") && event.target.id !== "qr-modal-scrim") {
    document.getElementById("edit-modal-scrim").style.display = "none";
  }
}

function closeModalDirect() {
  document.getElementById("edit-modal-scrim").style.display = "none";
}

function openQrModal(src) {
  document.getElementById("qr-modal-img").src = src;
  document.getElementById("qr-modal-scrim").style.display = "flex";
}

function closeQrModal(event) {
  if (event.target.id === "qr-modal-scrim") {
    document.getElementById("qr-modal-scrim").style.display = "none";
  }
}

function closeQrModalDirect() {
  document.getElementById("qr-modal-scrim").style.display = "none";
}

function toggleTransport() {
  const select = document.querySelector('select[name="network_security"]');
  const wsSection = document.getElementById('ws_section');
  const tlsSection = document.getElementById('tls_section');
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

const themeToggle = document.getElementById('theme-toggle');
const motionToggle = document.getElementById('motion-toggle');
const refreshToggle = document.getElementById('refresh-toggle');
const refreshInterval = document.getElementById('refresh-interval');

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

if (refreshEnabled && document.getElementById('trafficChart')) {
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
  const viewer = document.getElementById('log-viewer');
  if (viewer) viewer.innerHTML = '';
  if (document.getElementById('log-live-toggle')?.checked) {
    startLogStream(type);
  }
}

function startLogStream(type) {
  if (_logEs) { _logEs.close(); _logEs = null; }
  const viewer = document.getElementById('log-viewer');
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
  const viewer = document.getElementById('log-viewer');
  if (viewer) viewer.innerHTML = '';
}

const logLiveToggle = document.getElementById('log-live-toggle');
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
  const result = document.getElementById('validate-result');
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
  const scrim = document.getElementById('dl-modal-scrim');
  const title = document.getElementById('dl-modal-title');
  const statusEl = document.getElementById('dl-modal-status');
  const bar = document.getElementById('dl-progress-bar');
  const pctEl = document.getElementById('dl-progress-pct');

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
