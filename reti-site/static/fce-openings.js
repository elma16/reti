const snapshot = window.FCE_SNAPSHOT;
const openings = window.FCE_OPENINGS;
if (!snapshot) { throw new Error('FCE snapshot data was not loaded.'); }
if (!openings) { throw new Error('FCE opening distribution data was not loaded.'); }

let activeOpening = openings.defaultOpening || openings.options?.[0]?.key || '';
let activeView = 'all';
let activeThreshold = openings.thresholds?.[0] || '1';
let activeMode = 'table';
let activeLimit = 20;
let sortKey = 'quantity';
let sortDir = -1;

const fmtInt = n => Number(n || 0).toLocaleString();
function fmtPct(n) {
  const value = Number(n || 0);
  if (!Number.isFinite(value) || value === 0) return '0%';
  const abs = Math.abs(value);
  if (abs >= 0.001) return `${value.toFixed(3)}%`;
  const decimals = Math.min(10, Math.max(4, Math.ceil(-Math.log10(abs)) + 2));
  return `${value.toFixed(decimals).replace(/0+$/, '').replace(/\.$/, '')}%`;
}
function pct(a,b) { return b ? Math.round((a/b)*1000)/10 : 0; }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }

const optionByKey = new Map((openings.options || []).map(option => [option.key, option]));
const valueToKey = new Map();
const chunkState = new Map();
window.FCE_OPENING_CHUNKS = window.FCE_OPENING_CHUNKS || {};
for (const option of openings.options || []) {
  const label = optionLabel(option);
  valueToKey.set(label.toLowerCase(), option.key);
  valueToKey.set(String(option.ecoBase || '').toLowerCase(), option.key);
  valueToKey.set(String(option.label || '').toLowerCase(), option.key);
  for (const alias of option.aliases || []) valueToKey.set(String(alias).toLowerCase(), option.key);
}

function activeTheme() { return document.documentElement.dataset.theme || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); }
function updateThemeToggle() {
  const button = document.getElementById('theme-toggle');
  if (!button) return;
  const theme = activeTheme();
  button.dataset.activeTheme = theme;
  button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
}
document.getElementById('theme-toggle')?.addEventListener('click', () => {
  const next = activeTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('fce-theme', next); } catch (error) {}
  updateThemeToggle();
});
updateThemeToggle();

function optionLabel(option) {
  if (!option) return '';
  return `${option.ecoBase} · ${option.label || option.ecoBase}`;
}

function currentOption() {
  return optionByKey.get(activeOpening) || openings.options?.[0] || null;
}

function currentOpeningView() {
  return openings.views?.[activeView]?.openings?.[activeOpening] || window.FCE_OPENING_CHUNKS?.[activeOpening]?.views?.[activeView] || null;
}

function openingChunkLoaded(key) {
  return Boolean(
    openings.views?.[activeView]?.openings?.[key] ||
    window.FCE_OPENING_CHUNKS?.[key]
  );
}

function ensureOpeningLoaded(key) {
  if (openingChunkLoaded(key)) return true;
  const option = optionByKey.get(key);
  if (!option?.src) return true;
  if (chunkState.get(key) === 'loading' || chunkState.get(key) === 'error') return false;
  chunkState.set(key, 'loading');
  const script = document.createElement('script');
  script.src = option.src;
  script.async = true;
  script.onload = () => {
    chunkState.set(key, 'loaded');
    render();
  };
  script.onerror = () => {
    chunkState.set(key, 'error');
    render();
  };
  document.head.appendChild(script);
  return false;
}

function currentThresholdPayload() {
  const view = currentOpeningView();
  if (!view) {
    const totalGames = Number(currentOption()?.viewTotals?.[activeView] || 0);
    return {metrics:{totalGames, matchedRows:0}, rows:{}};
  }
  if (!view?.thresholds?.[activeThreshold]) activeThreshold = openings.thresholds?.[0] || '1';
  return view?.thresholds?.[activeThreshold] || {metrics:{totalGames:0, matchedRows:0}, rows:{}};
}

function flatRows() {
  const out = [];
  snapshot.rows.forEach(row => {
    out.push({...row, isAux:false});
    (row.auxiliaryRows || []).forEach(aux => out.push({...aux, isAux:true, parentLabel:row.label, parentStem:row.stem}));
  });
  return out;
}

function rowDisplayLabel(row) {
  if (!row.isAux) return row.label;
  const child = String(row.label || '').trim();
  const parent = String(row.parentLabel || '').trim();
  if (!parent) return child;
  if (/^without pawns$/i.test(child)) return `${parent} without pawns`;
  if (/^connected pawns$/i.test(child)) return `${parent} with connected pawns`;
  return `${parent}: ${child}`;
}

function outcomeBar(payload, totalKey='totalGames') {
  const win = Number(payload?.sideWins || 0);
  const draw = Number(payload?.sideDraws || 0);
  const loss = Number(payload?.sideLosses || 0);
  const decisive = Number(payload?.symmetricDecisive || 0);
  const total = Number(payload?.[totalKey] || 0) || win + draw + loss + decisive;
  if (!total) return '';
  const a = decisive || win;
  const b = draw;
  const c = loss;
  const ap = pct(a,total);
  const bp = pct(b,total);
  const cp = pct(c,total);
  const label = `W ${ap}% | D ${bp}% | L ${cp}%`;
  const text = p => p >= 10 ? `${p}%` : '';
  return `<span class="bar-shell" tabindex="0" data-tip="${esc(label)}" aria-label="${esc(label)}"><span class="bar"><span class="win" style="width:${ap}%">${text(ap)}</span><span class="draw" style="width:${bp}%">${text(bp)}</span><span class="loss" style="width:${cp}%">${text(cp)}</span></span></span>`;
}

function controls() {
  const datalist = document.getElementById('opening-options');
  datalist.innerHTML = (openings.options || []).map(option => `<option value="${esc(optionLabel(option))}"></option>`).join('');
  const input = document.getElementById('opening-search');
  const option = currentOption();
  if (document.activeElement !== input) input.value = optionLabel(option);
  input.onchange = () => {
    const key = openingKeyFromInput(input.value);
    if (key) {
      activeOpening = key;
      render();
    }
  };
  input.onkeydown = event => {
    if (event.key === 'Enter') {
      const key = openingKeyFromInput(input.value);
      if (key) {
        activeOpening = key;
        input.blur();
        render();
      }
    }
  };

  const vc = document.getElementById('opening-view-controls');
  vc.innerHTML = '';
  ['all','otb','online'].forEach(view => {
    if (!openings.views?.[view]) return;
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = openings.views[view].label || view.toUpperCase();
    b.className = view === activeView ? 'active' : '';
    b.onclick = () => { activeView = view; render(); };
    vc.appendChild(b);
  });

  const tc = document.getElementById('opening-threshold-controls');
  tc.innerHTML = '';
  (openings.thresholds || ['1']).forEach(threshold => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = threshold;
    b.className = threshold === activeThreshold ? 'active' : '';
    b.onclick = () => { activeThreshold = threshold; render(); };
    tc.appendChild(b);
  });

  const mc = document.getElementById('opening-mode-controls');
  mc.innerHTML = '';
  [['table','Table'], ['bars','Bars']].forEach(([mode, label]) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    b.className = mode === activeMode ? 'active' : '';
    b.onclick = () => { activeMode = mode; render(); };
    mc.appendChild(b);
  });

  const lc = document.getElementById('opening-limit-controls');
  lc.innerHTML = '';
  [10, 20, 35, 'all'].forEach(limit => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = limit === 'all' ? 'All' : String(limit);
    b.className = limit === activeLimit ? 'active' : '';
    b.onclick = () => { activeLimit = limit; render(); };
    lc.appendChild(b);
  });
}

function openingKeyFromInput(raw) {
  const value = String(raw || '').trim().toLowerCase();
  if (valueToKey.has(value)) return valueToKey.get(value);
  const eco = value.match(/[a-e][0-9]{2}/i)?.[0]?.toUpperCase();
  if (eco && optionByKey.has(`eco:${eco}`)) return `eco:${eco}`;
  const found = (openings.options || []).find(option => optionLabel(option).toLowerCase().includes(value) || (option.aliases || []).some(alias => String(alias).toLowerCase().includes(value)));
  return found?.key || null;
}

function rowsWithStats() {
  const tv = currentThresholdPayload();
  return flatRows().map(row => {
    const stats = tv.rows?.[row.stem] || {quantity:0, percentage:0, matchedShare:0, actualResult:{totalGames:0}};
    return {row, stats};
  });
}

function sortValue(item) {
  const {row, stats} = item;
  if (sortKey === 'label') return rowDisplayLabel(row);
  if (sortKey === 'percentage') return Number(stats.percentage || 0);
  if (sortKey === 'matchedShare') return Number(stats.matchedShare || 0);
  if (sortKey === 'actualWinPct') return pct(Number(stats.actualResult?.sideWins || stats.actualResult?.symmetricDecisive || 0), Number(stats.actualResult?.totalGames || 0));
  if (sortKey === 'sortIndex') return Number(row.sortIndex || 0);
  return Number(stats.quantity || 0);
}

function sortedRows() {
  const rows = rowsWithStats();
  rows.sort((a,b) => {
    const av = sortValue(a);
    const bv = sortValue(b);
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * sortDir;
    return (av - bv) * sortDir || (Number(a.row.sortIndex || 0) - Number(b.row.sortIndex || 0));
  });
  return rows;
}

function renderMetrics() {
  const option = currentOption();
  const tv = currentThresholdPayload();
  const nonzero = rowsWithStats().filter(item => Number(item.stats.quantity || 0) > 0);
  const top = nonzero.slice().sort((a,b) => Number(b.stats.quantity || 0) - Number(a.stats.quantity || 0))[0];
  document.getElementById('opening-metrics').innerHTML = [
    ['Opening', option?.ecoBase || ''],
    ['Source games', fmtInt(tv.metrics?.totalGames)],
    ['Ending incidences', fmtInt(tv.metrics?.matchedRows)],
    ['Top ending', top ? rowDisplayLabel(top.row) : 'None'],
  ].map(([label, value]) => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
}

function renderTable() {
  const tableWrap = document.getElementById('opening-table-wrap');
  tableWrap.hidden = activeMode !== 'table';
  const head = document.querySelector('#opening-table thead');
  const body = document.querySelector('#opening-table tbody');
  head.innerHTML = `<tr><th data-sort="sortIndex">ID</th><th data-sort="label">Ending</th><th class="num" data-sort="quantity">Games</th><th class="num" data-sort="percentage">Opening corpus %</th><th class="num" data-sort="matchedShare">Opening matched share %</th><th data-sort="actualWinPct">Actual result</th></tr>`;
  body.innerHTML = sortedRows().map(({row, stats}) => `<tr class="${row.isAux ? 'aux' : ''}"><td>${esc(row.rowId || '')}</td><td>${row.isAux ? '↳ ' : ''}${esc(rowDisplayLabel(row))}</td><td class="num">${fmtInt(stats.quantity)}</td><td class="num">${fmtPct(stats.percentage)}</td><td class="num">${fmtPct(stats.matchedShare)}</td><td>${outcomeBar(stats.actualResult,'totalGames')}</td></tr>`).join('');
  bindSorting();
}

function bindSorting() {
  document.querySelectorAll('#opening-table th[data-sort]').forEach(th => {
    th.onclick = () => {
      const next = th.dataset.sort;
      if (sortKey === next) sortDir *= -1; else { sortKey = next; sortDir = next === 'sortIndex' ? 1 : -1; }
      render();
    };
    th.setAttribute('aria-sort', th.dataset.sort === sortKey ? (sortDir > 0 ? 'ascending' : 'descending') : 'none');
    th.classList.toggle('sorted-asc', th.dataset.sort === sortKey && sortDir > 0);
    th.classList.toggle('sorted-desc', th.dataset.sort === sortKey && sortDir < 0);
  });
}

function renderBars() {
  const panel = document.getElementById('opening-chart-panel');
  panel.hidden = activeMode !== 'bars';
  const container = document.getElementById('opening-bars');
  if (activeMode !== 'bars') {
    container.innerHTML = '';
    return;
  }
  let rows = rowsWithStats().filter(item => Number(item.stats.quantity || 0) > 0);
  rows.sort((a,b) => Number(b.stats.quantity || 0) - Number(a.stats.quantity || 0));
  if (activeLimit !== 'all') rows = rows.slice(0, Number(activeLimit));
  const max = Math.max(1, ...rows.map(item => Number(item.stats.quantity || 0)));
  container.innerHTML = rows.map(({row, stats}) => {
    const width = Math.max(1, Number(stats.quantity || 0) / max * 100);
    return `<div class="opening-bar-row"><div class="opening-bar-label"><strong>${esc(row.rowId || '')}</strong><span>${esc(rowDisplayLabel(row))}</span></div><div class="opening-bar-track"><div class="opening-bar-fill" style="width:${width}%"></div></div><div class="opening-bar-value">${fmtInt(stats.quantity)} <span>${fmtPct(stats.percentage)}</span></div></div>`;
  }).join('') || '<p class="detail-note">No FCE ending incidences for this opening and threshold.</p>';
}

function renderLoading() {
  const option = currentOption();
  const status = chunkState.get(activeOpening);
  const message = status === 'error'
    ? `Could not load opening data for ${option?.ecoBase || activeOpening}.`
    : `Loading opening data for ${option?.ecoBase || activeOpening}...`;
  document.getElementById('opening-metrics').innerHTML = [
    ['Opening', option?.ecoBase || ''],
    ['Status', message],
  ].map(([label, value]) => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');

  const tableWrap = document.getElementById('opening-table-wrap');
  tableWrap.hidden = activeMode !== 'table';
  document.querySelector('#opening-table thead').innerHTML = '<tr><th>Opening data</th></tr>';
  document.querySelector('#opening-table tbody').innerHTML = `<tr><td>${esc(message)}</td></tr>`;

  const panel = document.getElementById('opening-chart-panel');
  const container = document.getElementById('opening-bars');
  panel.hidden = activeMode !== 'bars';
  container.innerHTML = activeMode === 'bars' ? `<p class="detail-note">${esc(message)}</p>` : '';
}

function render() {
  controls();
  if (!ensureOpeningLoaded(activeOpening)) {
    renderLoading();
    return;
  }
  renderMetrics();
  renderTable();
  renderBars();
}

render();
