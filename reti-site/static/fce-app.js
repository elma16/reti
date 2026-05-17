const snapshot = window.FCE_SNAPSHOT;
if (!snapshot) { throw new Error('FCE snapshot data was not loaded.'); }
const sampleManifest = window.FCE_SAMPLED_EXAMPLES_MANIFEST || null;
window.FCE_SAMPLE_CHUNKS = window.FCE_SAMPLE_CHUNKS || {};
const sampleLoadPromises = new Map();
const sampleLoadErrors = new Map();
if (snapshot.sourceBuckets) console.debug('FCE source buckets', snapshot.sourceBuckets);
let activeView = snapshot.datasetViews.default || 'all';
let activeThreshold = '1';
let sortKey = 'sortIndex';
let sortDir = 1;
let expandedStem = null;
const symmetricStems = new Set(['2-0Pp','3-2NN','4-2scBB','4-3ocBB','6-2-0Rr','6-3RRrr','8-3RAra','9-2Qq']);
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
function viewOrder() { return ['all','otb','online'].filter(k => snapshot.datasetViews.views[k]); }
function currentDatasetView() {
  return snapshot.datasetViews.views[activeView];
}
function currentThresholdView() {
  const view = currentDatasetView();
  if (!view.thresholdViews[activeThreshold]) activeThreshold = Object.keys(view.thresholdViews)[0];
  return view.thresholdViews[activeThreshold];
}
function activeTheme() { return document.documentElement.dataset.theme || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); }
function updateThemeToggle() {
  const button = document.getElementById('theme-toggle');
  if (!button) return;
  const theme = activeTheme();
  button.dataset.activeTheme = theme;
  button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
}
const themeButton = document.getElementById('theme-toggle');
if (themeButton && themeButton.dataset.fceThemeBound !== '1') {
  themeButton.dataset.fceThemeBound = '1';
  themeButton.addEventListener('click', () => {
    const next = activeTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('fce-theme', next); } catch (error) {}
    updateThemeToggle();
  });
}
updateThemeToggle();
function outcomeBar(payload, totalKey='totalPositions') {
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
  const vc = document.getElementById('view-controls');
  vc.innerHTML = '';
  viewOrder().map(k => snapshot.datasetViews.views[k]).forEach(v => {
    const b = document.createElement('button'); b.textContent = v.label; b.className = v.key === activeView ? 'active' : '';
    b.onclick = () => { activeView = v.key; render(); }; vc.appendChild(b);
  });
  const tc = document.getElementById('threshold-controls');
  const thresholds = Object.keys(snapshot.datasetViews.views[activeView].thresholdViews);
  tc.innerHTML = '';
  thresholds.forEach(t => {
    const b = document.createElement('button'); b.textContent = t; b.className = t === activeThreshold ? 'active' : '';
    b.onclick = () => { activeThreshold = t; render(); }; tc.appendChild(b);
  });
}
function tableHeadHtml() {
  return `<tr><th data-sort="sortIndex">ID</th><th data-sort="label">Ending</th><th class="num" data-sort="quantity" title="Qualifying game-ending incidences: each game can count once for each ending stem.">Games</th><th class="num" data-sort="percentage" title="Row games divided by all games in the selected corpus.">Corpus %</th><th class="num" data-sort="matchedShare" title="Row games divided by all counted ending incidences in the active view.">Matched share %</th><th class="num" data-sort="tablebasePositions" title="<=5-piece first-marker occurrence rows, not unique FENs and not total games.">TB positions</th><th data-sort="tbWinPct" title="Syzygy WDL over TB position occurrence rows. Repeated FENs are probed once but counted per occurrence.">TB WDL</th><th data-sort="actualWinPct" title="Final PGN result from the named-material side perspective.">Actual result</th></tr>`;
}
function tableColspan() {
  return 8;
}
function rowHtml(row, stats) {
  const w = stats?.tablebaseWdl || {};
  const actual = stats?.actualResult || {};
  const label = rowDisplayLabel(row);
  return `<tr class="${row.isAux ? 'aux' : ''}" data-stem="${esc(row.stem)}" tabindex="0"><td>${esc(row.rowId || '')}</td><td>${row.isAux ? '↳ ' : ''}${esc(label)}</td><td class="num">${fmtInt(stats?.quantity)}</td><td class="num">${fmtPct(stats?.percentage)}</td><td class="num">${fmtPct(stats?.matchedShare)}</td><td class="num">${fmtInt(w.totalPositions)}</td><td>${outcomeBar(w,'totalPositions')}</td><td>${outcomeBar(actual,'totalGames')}</td></tr>`;
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
function rowSortValue(row, tv) {
  const stats = tv.rows[row.stem] || {};
  const w = stats.tablebaseWdl || {};
  if (sortKey === 'label') return row.label;
  if (sortKey === 'quantity') return Number(stats.quantity || 0);
  if (sortKey === 'percentage') return Number(stats.percentage || 0);
  if (sortKey === 'matchedShare') return Number(stats.matchedShare || 0);
  if (sortKey === 'tablebasePositions') return Number(w.totalPositions || 0);
  if (sortKey === 'tbWinPct') return pct(Number(w.sideWins || w.symmetricDecisive || 0), Number(w.totalPositions || 0));
  if (sortKey === 'actualWinPct') {
    const actual = stats.actualResult || {};
    return pct(Number(actual.sideWins || actual.symmetricDecisive || 0), Number(actual.totalGames || 0));
  }
  return Number(row.sortIndex || 0);
}
function flatRows() {
  const out = [];
  snapshot.rows.forEach(row => {
    out.push({...row, isAux:false});
    (row.auxiliaryRows || []).forEach((aux, idx) => out.push({...aux, rowId: auxId(row, idx), isAux:true, parentLabel:row.label, parentStem:row.stem}));
  });
  return out;
}
function auxId(parent, index) {
  const letter = String.fromCharCode(97 + index);
  if (parent.rowId) return `${parent.rowId}${letter}`;
  if (parent.stem === '10-7-1Qbrr') return `10.7${letter}`;
  return letter;
}
function sortedRows(tv) {
  const rows = flatRows();
  rows.sort((a,b) => {
    const av = rowSortValue(a, tv);
    const bv = rowSortValue(b, tv);
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * sortDir;
    return (av - bv) * sortDir || (Number(a.sortIndex || 0) - Number(b.sortIndex || 0));
  });
  return rows;
}
function bindSorting() {
  document.querySelectorAll('#ending-table th[data-sort]').forEach(th => {
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
const pieceSvgs = {
  K: `<g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path stroke-linejoin="miter" d="M22.5 11.63V6M20 8h5"/><path fill="#fff" stroke-linecap="butt" stroke-linejoin="miter" d="M22.5 25s4.5-7.5 3-10.5c0 0-1-2.5-3-2.5s-3 2.5-3 2.5c-1.5 3 3 10.5 3 10.5"/><path fill="#fff" d="M11.5 37c5.5 3.5 15.5 3.5 21 0v-7s9-4.5 6-10.5c-4-6.5-13.5-3.5-16 4V27v-3.5c-3.5-7.5-13-10.5-16-4-3 6 5 10 5 10z"/><path d="M11.5 30c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0"/></g>`,
  Q: `<g fill="#fff" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path d="M8 12a2 2 0 1 1-4 0 2 2 0 1 1 4 0m16.5-4.5a2 2 0 1 1-4 0 2 2 0 1 1 4 0M41 12a2 2 0 1 1-4 0 2 2 0 1 1 4 0M16 8.5a2 2 0 1 1-4 0 2 2 0 1 1 4 0M33 9a2 2 0 1 1-4 0 2 2 0 1 1 4 0"/><path stroke-linecap="butt" d="M9 26c8.5-1.5 21-1.5 27 0l2-12-7 11V11l-5.5 13.5-3-15-3 15-5.5-14V25L7 14z"/><path stroke-linecap="butt" d="M9 26c0 2 1.5 2 2.5 4 1 1.5 1 1 .5 3.5-1.5 1-1.5 2.5-1.5 2.5-1.5 1.5.5 2.5.5 2.5 6.5 1 16.5 1 23 0 0 0 1.5-1 0-2.5 0 0 .5-1.5-1-2.5-.5-2.5-.5-2 .5-3.5 1-2 2.5-2 2.5-4-8.5-1.5-18.5-1.5-27 0z"/><path fill="none" d="M11.5 30c3.5-1 18.5-1 22 0M12 33.5c6-1 15-1 21 0"/></g>`,
  R: `<g fill="#fff" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path stroke-linecap="butt" d="M9 39h27v-3H9zm3-3v-4h21v4zm-1-22V9h4v2h5V9h5v2h5V9h4v5"/><path d="m34 14-3 3H14l-3-3"/><path stroke-linecap="butt" stroke-linejoin="miter" d="M31 17v12.5H14V17"/><path d="m31 29.5 1.5 2.5h-20l1.5-2.5"/><path fill="none" stroke-linejoin="miter" d="M11 14h23"/></g>`,
  B: `<g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><g fill="#fff" stroke-linecap="butt"><path d="M9 36c3.39-.97 10.11.43 13.5-2 3.39 2.43 10.11 1.03 13.5 2 0 0 1.65.54 3 2-.68.97-1.65.99-3 .5-3.39-.97-10.11.46-13.5-1-3.39 1.46-10.11.03-13.5 1-1.35.49-2.32.47-3-.5 1.35-1.94 3-2 3-2z"/><path d="M15 32c2.5 2.5 12.5 2.5 15 0 .5-1.5 0-2 0-2 0-2.5-2.5-4-2.5-4 5.5-1.5 6-11.5-5-15.5-11 4-10.5 14-5 15.5 0 0-2.5 1.5-2.5 4 0 0-.5.5 0 2z"/><path d="M25 8a2.5 2.5 0 1 1-5 0 2.5 2.5 0 1 1 5 0z"/></g><path stroke-linejoin="miter" d="M17.5 26h10M15 30h15m-7.5-14.5v5M20 18h5"/></g>`,
  N: `<g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path fill="#fff" d="M22 10c10.5 1 16.5 8 16 29H15c0-9 10-6.5 8-21"/><path fill="#fff" d="M24 18c.38 2.91-5.55 7.37-8 9-3 2-2.82 4.34-5 4-1.042-.94 1.41-3.04 0-3-1 0 .19 1.23-1 2-1 0-4.003 1-4-4 0-2 6-12 6-12s1.89-1.9 2-3.5c-.73-.994-.5-2-.5-3 1-1 3 2.5 3 2.5h2s.78-1.992 2.5-3c1 0 1 3 1 3"/><path fill="#000" d="M9.5 25.5a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0m5.433-9.75a.5 1.5 30 1 1-.866-.5.5 1.5 30 1 1 .866.5"/></g>`,
  P: `<path fill="#fff" stroke="#000" stroke-linecap="round" stroke-width="1.5" d="M22.5 9c-2.21 0-4 1.79-4 4 0 .89.29 1.71.78 2.38C17.33 16.5 16 18.59 16 21c0 2.03.94 3.84 2.41 5.03-3 1.06-7.41 5.55-7.41 13.47h23c0-7.92-4.41-12.41-7.41-13.47 1.47-1.19 2.41-3 2.41-5.03 0-2.41-1.33-4.5-3.28-5.62.49-.67.78-1.49.78-2.38 0-2.21-1.79-4-4-4z"/>`,
  k: `<g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path stroke-linejoin="miter" d="M22.5 11.6V6"/><path fill="#000" stroke-linecap="butt" stroke-linejoin="miter" d="M22.5 25s4.5-7.5 3-10.5c0 0-1-2.5-3-2.5s-3 2.5-3 2.5c-1.5 3 3 10.5 3 10.5"/><path fill="#000" d="M11.5 37a22.3 22.3 0 0 0 21 0v-7s9-4.5 6-10.5c-4-6.5-13.5-3.5-16 4V27v-3.5c-3.5-7.5-13-10.5-16-4-3 6 5 10 5 10z"/><path stroke-linejoin="miter" d="M20 8h5"/><path stroke="#ececec" d="M32 29.5s8.5-4 6-9.7C34.1 14 25 18 22.5 24.6v2.1-2.1C20 18 9.9 14 7 19.9c-2.5 5.6 4.8 9 4.8 9"/><path stroke="#ececec" d="M11.5 30c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0m-21 3.5c5.5-3 15.5-3 21 0"/></g>`,
  q: `<g fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><g stroke="none"><circle cx="6" cy="12" r="2.75"/><circle cx="14" cy="9" r="2.75"/><circle cx="22.5" cy="8" r="2.75"/><circle cx="31" cy="9" r="2.75"/><circle cx="39" cy="12" r="2.75"/></g><path stroke-linecap="butt" d="M9 26c8.5-1.5 21-1.5 27 0l2.5-12.5L31 25l-.3-14.1-5.2 13.6-3-14.5-3 14.5-5.2-13.6L14 25 6.5 13.5z"/><path stroke-linecap="butt" d="M9 26c0 2 1.5 2 2.5 4 1 1.5 1 1 .5 3.5-1.5 1-1.5 2.5-1.5 2.5-1.5 1.5.5 2.5.5 2.5 6.5 1 16.5 1 23 0 0 0 1.5-1 0-2.5 0 0 .5-1.5-1-2.5-.5-2.5-.5-2 .5-3.5 1-2 2.5-2 2.5-4-8.5-1.5-18.5-1.5-27 0z"/><path fill="none" stroke-linecap="butt" d="M11 38.5a35 35 1 0 0 23 0"/><path fill="none" stroke="#ececec" d="M11 29a35 35 1 0 1 23 0m-21.5 2.5h20m-21 3a35 35 1 0 0 22 0m-23 3a35 35 1 0 0 24 0"/></g>`,
  r: `<g fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path stroke-linecap="butt" d="M9 39h27v-3H9zm3.5-7 1.5-2.5h17l1.5 2.5zm-.5 4v-4h21v4z"/><path stroke-linecap="butt" stroke-linejoin="miter" d="M14 29.5v-13h17v13z"/><path stroke-linecap="butt" d="M14 16.5 11 14h23l-3 2.5zM11 14V9h4v2h5V9h5v2h5V9h4v5z"/><path fill="none" stroke="#ececec" stroke-linejoin="miter" stroke-width="1" d="M12 35.5h21m-20-4h19m-18-2h17m-17-13h17M11 14h23"/></g>`,
  b: `<g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><g fill="#000" stroke-linecap="butt"><path d="M9 36c3.4-1 10.1.4 13.5-2 3.4 2.4 10.1 1 13.5 2 0 0 1.6.5 3 2-.7 1-1.6 1-3 .5-3.4-1-10.1.5-13.5-1-3.4 1.5-10.1 0-13.5 1-1.4.5-2.3.5-3-.5 1.4-2 3-2 3-2z"/><path d="M15 32c2.5 2.5 12.5 2.5 15 0 .5-1.5 0-2 0-2 0-2.5-2.5-4-2.5-4 5.5-1.5 6-11.5-5-15.5-11 4-10.5 14-5 15.5 0 0-2.5 1.5-2.5 4 0 0-.5.5 0 2z"/><path d="M25 8a2.5 2.5 0 1 1-5 0 2.5 2.5 0 1 1 5 0z"/></g><path stroke="#ececec" stroke-linejoin="miter" d="M17.5 26h10M15 30h15m-7.5-14.5v5M20 18h5"/></g>`,
  n: `<g fill="none" fill-rule="evenodd" stroke="#000" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path fill="#000" d="M22 10c10.5 1 16.5 8 16 29H15c0-9 10-6.5 8-21"/><path fill="#000" d="M24 18c.38 2.91-5.55 7.37-8 9-3 2-2.82 4.34-5 4-1.04-.94 1.41-3.04 0-3-1 0 .19 1.23-1 2-1 0-4 1-4-4 0-2 6-12 6-12s1.89-1.9 2-3.5c-.73-1-.5-2-.5-3 1-1 3 2.5 3 2.5h2s.78-2 2.5-3c1 0 1 3 1 3"/><path fill="#ececec" stroke="#ececec" d="M9.5 25.5a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0m5.43-9.75a.5 1.5 30 1 1-.86-.5.5 1.5 30 1 1 .86.5"/><path fill="#ececec" stroke="none" d="m24.55 10.4-.45 1.45.5.15c3.15 1 5.65 2.49 7.9 6.75S35.75 29.06 35.25 39l-.05.5h2.25l.05-.5c.5-10.06-.88-16.85-3.25-21.34s-5.79-6.64-9.19-7.16z"/></g>`,
  p: `<path stroke="#000" stroke-linecap="round" stroke-width="1.5" d="M22.5 9a4 4 0 0 0-3.22 6.38 6.48 6.48 0 0 0-.87 10.65c-3 1.06-7.41 5.55-7.41 13.47h23c0-7.92-4.41-12.41-7.41-13.47a6.46 6.46 0 0 0-.87-10.65A4.01 4.01 0 0 0 22.5 9z"/>`
};
function lichessUrl(fen) { return fen ? `https://lichess.org/analysis/standard/${encodeURI(fen.replaceAll(' ', '_'))}` : 'https://lichess.org/analysis'; }
function boardHtml(fen, label) {
  const board = String(fen || '').split(' ')[0];
  const ranks = board.split('/');
  let squares = '';
  for (let rankIndex = 0; rankIndex < 8; rankIndex++) {
    for (let fileIndex = 0; fileIndex < 8; fileIndex++) {
      const tone = (rankIndex + fileIndex) % 2 === 0 ? 'light' : 'dark';
      squares += `<rect class="board-square ${tone}" x="${fileIndex}" y="${rankIndex}" width="1" height="1"></rect>`;
    }
  }
  let pieces = '';
  if (ranks.length === 8) {
    ranks.forEach((rank, rankIndex) => {
      let fileIndex = 0;
      [...rank].forEach(token => {
        if (/\d/.test(token)) { fileIndex += Number(token); return; }
        const piece = pieceSvgs[token];
        if (piece && fileIndex < 8) pieces += `<g class="board-piece" data-piece="${esc(token)}" data-square="${String.fromCharCode(97 + fileIndex)}${8 - rankIndex}" transform="translate(${fileIndex} ${rankIndex}) scale(${1 / 45})">${piece}</g>`;
        fileIndex += 1;
      });
    });
  }
  const turn = String(fen || '').split(' ')[1] === 'b' ? 'black' : 'white';
  return `<a class="board-link" href="${esc(lichessUrl(fen))}" data-fen="${esc(fen)}" data-turn="${turn}" target="_blank" rel="noopener noreferrer" aria-label="${esc(label)}"><svg class="board-svg" viewBox="0 0 8 8" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${squares}${pieces}</svg></a>`;
}
function sampleChunkKey(view, threshold, stem) { return `${view}|${threshold}|${stem}`; }
function fullSamplePayload(stem) {
  const full = window.FCE_SAMPLED_EXAMPLES || snapshot.sampledExamples || null;
  return full?.views?.[activeView]?.thresholds?.[activeThreshold]?.stems?.[stem] || null;
}
function sampleManifestEntry(stem) {
  return sampleManifest?.views?.[activeView]?.thresholds?.[activeThreshold]?.stems?.[stem] || null;
}
function samplePayload(stem) {
  const full = fullSamplePayload(stem);
  if (full) return full;
  return window.FCE_SAMPLE_CHUNKS[sampleChunkKey(activeView, activeThreshold, stem)] || null;
}
function sampleLimit() {
  const full = window.FCE_SAMPLED_EXAMPLES || snapshot.sampledExamples || null;
  return Number(sampleManifest?.sampleSize || full?.sampleSize || 32);
}
function requestSampleLoad(stem) {
  if (samplePayload(stem)) return;
  const entry = sampleManifestEntry(stem);
  const key = sampleChunkKey(activeView, activeThreshold, stem);
  if (!entry?.src || sampleLoadPromises.has(key) || sampleLoadErrors.has(key)) return;
  const promise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.async = true;
    script.src = entry.src;
    script.onload = () => resolve(samplePayload(stem));
    script.onerror = () => reject(new Error(`Failed to load ${entry.src}`));
    document.head.appendChild(script);
  });
  sampleLoadPromises.set(key, promise);
  promise.then(() => {
    if (expandedStem === stem) render();
  }).catch(error => {
    sampleLoadErrors.set(key, error);
    if (expandedStem === stem) render();
  });
}
function outcomeCounts(payload, totalKey, row) {
  const unknown = payload?.unknownGames || payload?.unknownPositions || 0;
  const sideWins = Number(payload?.sideWins || 0);
  const draws = Number(payload?.sideDraws || 0);
  const sideLosses = Number(payload?.sideLosses || 0);
  const decisive = Number(payload?.symmetricDecisive || 0);
  const isSymmetric = symmetricStems.has(row?.stem) || (decisive > 0 && sideWins === 0 && sideLosses === 0);
  const rows = isSymmetric
    ? [['Draws', draws]]
    : [['Side wins', sideWins], ['Draws', draws], ['Side losses', sideLosses]];
  if (decisive > 0) rows.push(['Decisive', decisive]);
  if (unknown > 0) rows.push(['Unknown', unknown]);
  rows.push(['Total', payload?.[totalKey] || 0]);
  return rows;
}
function statsPanel(title, payload, totalKey, note, row) {
  const counts = outcomeCounts(payload || {}, totalKey, row);
  return `<section class="detail-panel"><h4>${esc(title)}</h4><div class="detail-stat-grid">${counts.map(([k,v]) => `<div class="detail-stat"><span>${esc(k)}</span><strong>${fmtInt(v)}</strong></div>`).join('')}</div><p class="detail-note">${esc(note)}</p></section>`;
}
function tbResultMatrix(w) {
  const rows = w?.resultCrosstab?.rows || [];
  const hasDecisive = rows.some(row => Number(row.decisive || 0) > 0);
  const hasUnknown = rows.some(row => Number(row.unknown || 0) > 0);
  const columns = hasDecisive
    ? [['draw','Draw'], ['decisive','Decisive']]
    : [['win','Win'], ['draw','Draw'], ['loss','Loss']];
  if (hasUnknown) columns.push(['unknown', 'Unknown']);
  const subtitle = hasDecisive
    ? 'Rows show the Syzygy result; columns show the final game result, counted over tablebase-position occurrence rows. This symmetric ending has no named material side, so decisive means either side won.'
    : 'Rows show the Syzygy result; columns show the final game result from the named-material side perspective, counted over tablebase-position occurrence rows.';
  if (!rows.length) return '';
  const label = key => ({win:'TB win', draw:'TB draw', loss:'TB loss', decisive:'TB decisive', unknown:'TB unknown'}[key] || key);
  const header = columns.map(([, title]) => `<th class="num">${esc(title)}</th>`).join('');
  const body = rows.map(row => `<tr><th>${esc(label(row.tbOutcome))}</th>${columns.map(([key]) => `<td class="num">${fmtInt(row[key])}</td>`).join('')}<td class="num">${fmtInt(row.total)}</td></tr>`).join('');
  return `<section class="detail-panel matrix-panel"><h4>Tablebase vs Final Result</h4><p class="detail-subtitle">${esc(subtitle)}</p><div class="matrix-wrap"><table class="matrix"><thead><tr><th>Tablebase</th>${header}<th class="num">Total</th></tr></thead><tbody>${body}</tbody></table></div></section>`;
}
function detailStats(row, stats) {
  const actual = stats?.actualResult || {};
  const w = stats?.tablebaseWdl || {};
  const hasTablebase = Number(w?.totalPositions || 0) > 0;
  return `<div class="detail-panels">${
    statsPanel('Actual result', actual, 'totalGames', 'Final PGN result for every qualifying game-ending incidence.', row)
  }${
    hasTablebase ? statsPanel('Tablebase WDL', w, 'totalPositions', 'Syzygy WDL over <=5-piece first-marker occurrence rows. Repeated FENs are probed once internally but counted per game-ending occurrence here.', row) : ''
  }${hasTablebase ? tbResultMatrix(w) : ''}</div>`;
}
function exampleCard(example) {
  const rating = value => {
    const text = String(value ?? '').trim();
    return text && text !== '?' && text !== '-' ? text : '';
  };
  const player = (name, elo) => {
    const cleanName = String(name || '').trim();
    const cleanElo = rating(elo);
    if (!cleanName && !cleanElo) return '';
    return cleanElo ? `${cleanName || 'Unknown'} (${cleanElo})` : cleanName;
  };
  const white = player(example.white, example.whiteElo || example.whiteRating);
  const black = player(example.black, example.blackElo || example.blackRating);
  const title = [white, black].filter(Boolean).join(' vs ') || 'Sampled game';
  const clean = value => {
    const text = String(value ?? '').trim();
    return text && text !== '?' && text !== '-' ? text : '';
  };
  const tournament = clean(example.event);
  const location = clean(example.site);
  const subtitle = [tournament, location].filter(Boolean).join(' | ');
  const meta = [
    ['Result', example.result],
    ['Date', example.date],
    ['Side to move', example.sideToMove === 'black' ? 'Black' : 'White']
  ].filter(([, value]) => value !== undefined && value !== null && String(value) !== '');
  return `<article class="example-card">${boardHtml(example.fen, 'Open sampled position on Lichess analysis board')}<div class="example-meta"><strong class="example-title">${esc(title)}</strong><span class="example-subtitle">${esc(subtitle)}</span><dl>${meta.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl></div></article>`;
}
function detailHtml(row) {
  const payload = samplePayload(row.stem);
  const entry = sampleManifestEntry(row.stem);
  const key = sampleChunkKey(activeView, activeThreshold, row.stem);
  const view = currentDatasetView();
  const tv = currentThresholdView();
  const stats = tv.rows[row.stem] || {};
  const detailTitle = rowDisplayLabel(row);
  const colspan = tableColspan();
  if (!payload) {
    requestSampleLoad(row.stem);
    const error = sampleLoadErrors.get(key);
    const message = error
      ? `Sample boards could not be loaded from ${entry?.src || 'sample sidecar'}.`
      : entry
        ? `Loading sample boards from ${entry.src}...`
        : 'No sampled examples are available for this ending in the selected corpus and threshold.';
    return `<tr class="detail-row"><td colspan="${colspan}"><div class="detail-inner"><div class="detail-head"><h3>${esc(row.rowId ? row.rowId + ' ' : '')}${esc(detailTitle)} Details</h3><span>${esc(activeView.toUpperCase())} | ≥${esc(activeThreshold)} half-move(s)</span></div>${detailStats(row, stats)}<p class="detail-note">${esc(message)}</p></div></td></tr>`;
  }
  const examples = Array.isArray(payload.examples) ? payload.examples : [];
  console.debug('FCE sampled example metadata', { view: activeView, threshold: activeThreshold, stem: row.stem, row, payload, examples });
  const boardWord = Number(payload.sampled || 0) === 1 ? 'board' : 'boards';
  const note = `${fmtInt(payload.sampled)} ${boardWord} shown from ${fmtInt(payload.available)} qualifying game-ending incidence(s).`;
  return `<tr class="detail-row"><td colspan="${colspan}"><div class="detail-inner"><div class="detail-head"><h3>${esc(row.rowId ? row.rowId + ' ' : '')}${esc(detailTitle)} Details</h3><span>${esc(activeView.toUpperCase())} | ≥${esc(activeThreshold)} half-move(s)</span></div>${detailStats(row, stats)}<p class="detail-note">${note}</p><div class="examples-grid">${examples.map(exampleCard).join('')}</div></div></td></tr>`;
}
function bindRowExpansion() {
  document.querySelectorAll('#ending-table tbody tr[data-stem]').forEach(row => {
    row.onclick = () => { expandedStem = expandedStem === row.dataset.stem ? null : row.dataset.stem; render(); };
    row.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); row.click(); } };
  });
}
function render() {
  controls();
  const view = currentDatasetView();
  const tv = currentThresholdView();
  const table = document.getElementById('ending-table');
  table.querySelector('thead').innerHTML = tableHeadHtml();
  document.getElementById('metrics').innerHTML = `
    <div class="metric" title="Original source games in the selected corpus."><span>Total games</span><strong>${fmtInt(tv.metrics.totalGames)}</strong></div>
    <div class="metric" title="Source games with at least one qualifying FCE ending."><span>Matched games</span><strong>${fmtInt(tv.metrics.matchedGames)}</strong></div>
    <div class="metric" title="Qualifying game-ending incidences. Different endings in the same game can both count."><span>Ending incidences</span><strong>${fmtInt(tv.metrics.matchedRows)}</strong></div>
    <div class="metric" title="<=5-piece first-marker occurrence rows. FENs are deduplicated for Syzygy probing, but this displayed count is occurrence-weighted."><span>TB positions</span><strong>${fmtInt(tv.metrics.tablebasePositions)}</strong></div>`;
  const body = table.querySelector('tbody');
  body.innerHTML = sortedRows(tv).map(row => {
    let html = rowHtml(row, tv.rows[row.stem]);
    if (row.stem === expandedStem) html += detailHtml(row);
    return html;
  }).join('');
  bindSorting();
  bindRowExpansion();
}
render();
