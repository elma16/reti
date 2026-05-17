(() => {
const sankeyData = window.FCE_SANKEY;
if (!sankeyData) {
  console.warn('FCE Sankey data was not loaded.');
  return;
}

let activeView = sankeyData.controls.defaultView || 'all';
let activeThreshold = sankeyData.controls.defaultThreshold || '1';
let activeLimit = 50;

const nodeByStem = new Map((sankeyData.nodes || []).map(node => [node.stem, node]));
const fmtInt = n => Number(n || 0).toLocaleString();
function pct(a, b) { return b ? Math.round((a / b) * 1000) / 10 : 0; }
function pctText(a, b) { return `${pct(a, b)}%`; }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function cssId(value) { return window.CSS?.escape ? CSS.escape(String(value)) : String(value).replace(/["\\]/g, '\\$&'); }
function labelFor(stem) { return nodeByStem.get(stem)?.label || stem; }
function idFor(stem) { return nodeByStem.get(stem)?.rowId || ''; }
function colorFor(stem) { return nodeByStem.get(stem)?.color || '#777'; }

function activeTheme() {
  return document.documentElement.dataset.theme || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}
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

function currentThresholdPayload() {
  const view = sankeyData.views[activeView] || sankeyData.views.all || Object.values(sankeyData.views)[0];
  if (!view.thresholds[activeThreshold]) activeThreshold = Object.keys(view.thresholds)[0];
  return view.thresholds[activeThreshold];
}

function currentLinks() {
  const payload = currentThresholdPayload();
  const links = [...(payload.links || [])].sort((a, b) => b.count - a.count || labelFor(a.source).localeCompare(labelFor(b.source)) || labelFor(a.target).localeCompare(labelFor(b.target)));
  return activeLimit === 'all' ? links : links.slice(0, activeLimit);
}

function controls() {
  const vc = document.getElementById('sankey-view-controls');
  vc.innerHTML = '';
  (sankeyData.controls.views || []).forEach(view => {
    if (!sankeyData.views[view.key]) return;
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = view.label;
    b.className = view.key === activeView ? 'active' : '';
    b.onclick = () => { activeView = view.key; render(); };
    vc.appendChild(b);
  });

  const tc = document.getElementById('sankey-threshold-controls');
  tc.innerHTML = '';
  const thresholds = Object.keys((sankeyData.views[activeView] || {}).thresholds || {});
  thresholds.forEach(threshold => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = threshold;
    b.className = threshold === activeThreshold ? 'active' : '';
    b.onclick = () => { activeThreshold = threshold; render(); };
    tc.appendChild(b);
  });

  const lc = document.getElementById('sankey-limit-controls');
  lc.innerHTML = '';
  [25, 50, 100, 'all'].forEach(limit => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = limit === 'all' ? 'All' : String(limit);
    b.className = limit === activeLimit ? 'active' : '';
    b.onclick = () => { activeLimit = limit; render(); };
    lc.appendChild(b);
  });
}

function metrics() {
  const payload = currentThresholdPayload();
  const m = payload.metrics || {};
  document.getElementById('sankey-metrics').innerHTML = [
    ['Game-ending incidences', m.gameEndingIncidences],
    ['Games with transitions', m.gamesWithTransitions],
    ['Distinct transitions', m.distinctTransitions],
    ['Transition incidences', m.transitionIncidences],
  ].map(([label, value]) => `<div class="metric"><span>${esc(label)}</span><strong>${fmtInt(value)}</strong></div>`).join('');
}

function layoutSide(totals, x, side, height) {
  const entries = [...totals.entries()].sort((a, b) => b[1] - a[1] || labelFor(a[0]).localeCompare(labelFor(b[0])));
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  const top = 24;
  const gap = 8;
  const available = Math.max(120, height - top * 2 - Math.max(0, entries.length - 1) * gap);
  const scale = total ? available / total : 1;
  const out = new Map();
  let y = top;
  entries.forEach(([stem, value]) => {
    const h = Math.max(3, value * scale);
    out.set(stem, { stem, value, x, y, h, offset: 0, side });
    y += h + gap;
  });
  return { nodes: out, scale };
}

function pathD(x0, y0, x1, y1) {
  const dx = Math.max(120, (x1 - x0) * 0.5);
  return `M${x0},${y0} C${x0 + dx},${y0} ${x1 - dx},${y1} ${x1},${y1}`;
}

function drawSankey() {
  const svg = document.getElementById('sankey-svg');
  const links = currentLinks();
  const payload = currentThresholdPayload();
  const activeCount = links.length;
  document.getElementById('sankey-subtitle').textContent = `${fmtInt(activeCount)} of ${fmtInt(payload.metrics?.distinctTransitions || 0)} distinct transitions shown for ${activeView.toUpperCase()} at threshold ${activeThreshold}.`;

  const leftTotals = new Map();
  const rightTotals = new Map();
  links.forEach(link => {
    leftTotals.set(link.source, (leftTotals.get(link.source) || 0) + Number(link.count || 0));
    rightTotals.set(link.target, (rightTotals.get(link.target) || 0) + Number(link.count || 0));
  });

  const width = 1480;
  const nodeWidth = 14;
  const labelGutter = 390;
  const labelGap = 10;
  const height = Math.max(460, Math.max(leftTotals.size, rightTotals.size) * 34 + 80);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  svg.innerHTML = '';

  if (!links.length) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" class="sankey-empty">No consecutive transitions for this selection.</text>`;
    return;
  }

  const left = layoutSide(leftTotals, labelGutter, 'left', height);
  const right = layoutSide(rightTotals, width - labelGutter, 'right', height);
  const scale = Math.min(left.scale, right.scale);
  const totalTransitions = Number(payload.metrics?.transitionIncidences || 0);

  const linkGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  linkGroup.setAttribute('class', 'sankey-links');
  svg.appendChild(linkGroup);

  links.slice().reverse().forEach(link => {
    const source = left.nodes.get(link.source);
    const target = right.nodes.get(link.target);
    if (!source || !target) return;
    const strokeWidth = Math.max(1, Number(link.count || 0) * scale);
    const y0 = source.y + source.offset + strokeWidth / 2;
    const y1 = target.y + target.offset + strokeWidth / 2;
    source.offset += strokeWidth;
    target.offset += strokeWidth;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', 'sankey-link');
    path.dataset.source = link.source;
    path.dataset.target = link.target;
    path.setAttribute('d', pathD(source.x + nodeWidth, y0, target.x, y1));
    path.setAttribute('stroke', colorFor(link.source));
    path.setAttribute('stroke-width', strokeWidth);
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = `${labelFor(link.source)} -> ${labelFor(link.target)}: ${fmtInt(link.count)} game-link incidence${Number(link.count) === 1 ? '' : 's'} (${pctText(Number(link.count || 0), totalTransitions)} of all transition incidences)`;
    path.appendChild(title);
    linkGroup.appendChild(path);
  });

  drawNodes(svg, left.nodes, nodeWidth, 'left', labelGap);
  drawNodes(svg, right.nodes, nodeWidth, 'right', labelGap);
  wireSankeyHover(svg);
}

function drawNodes(svg, nodes, nodeWidth, side, labelGap) {
  const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  group.setAttribute('class', `sankey-nodes sankey-nodes-${side}`);
  svg.appendChild(group);
  [...nodes.values()].forEach(node => {
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('class', 'sankey-node');
    rect.dataset.stem = node.stem;
    rect.setAttribute('x', node.x);
    rect.setAttribute('y', node.y);
    rect.setAttribute('width', nodeWidth);
    rect.setAttribute('height', node.h);
    rect.setAttribute('fill', colorFor(node.stem));
    group.appendChild(rect);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('class', 'sankey-label');
    text.dataset.stem = node.stem;
    text.setAttribute('x', side === 'left' ? node.x - labelGap : node.x + nodeWidth + labelGap);
    text.setAttribute('y', node.y + Math.max(11, node.h / 2));
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('text-anchor', side === 'left' ? 'end' : 'start');
    text.textContent = `${idFor(node.stem) ? `${idFor(node.stem)} ` : ''}${labelFor(node.stem)}`;
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = `${labelFor(node.stem)}: ${fmtInt(node.value)} shown link incidence${Number(node.value) === 1 ? '' : 's'} on the ${side}`;
    text.appendChild(title);
    group.appendChild(text);
  });
}

function wireSankeyHover(svg) {
  const links = [...svg.querySelectorAll('.sankey-link')];
  const components = [...svg.querySelectorAll('.sankey-link,.sankey-node,.sankey-label')];
  const clear = () => {
    svg.classList.remove('is-focused');
    components.forEach(el => el.classList.remove('is-highlighted'));
  };
  const highlightLink = link => {
    const source = link.dataset.source;
    const target = link.dataset.target;
    svg.classList.add('is-focused');
    components.forEach(el => el.classList.remove('is-highlighted'));
    link.classList.add('is-highlighted');
    svg.querySelectorAll(`[data-stem="${cssId(source)}"],[data-stem="${cssId(target)}"]`).forEach(el => el.classList.add('is-highlighted'));
  };
  const highlightNode = stem => {
    svg.classList.add('is-focused');
    components.forEach(el => el.classList.remove('is-highlighted'));
    svg.querySelectorAll(`[data-stem="${cssId(stem)}"]`).forEach(el => el.classList.add('is-highlighted'));
    links.forEach(link => {
      if (link.dataset.source === stem || link.dataset.target === stem) {
        link.classList.add('is-highlighted');
        svg.querySelectorAll(`[data-stem="${cssId(link.dataset.source)}"],[data-stem="${cssId(link.dataset.target)}"]`).forEach(el => el.classList.add('is-highlighted'));
      }
    });
  };
  links.forEach(link => {
    link.addEventListener('mouseenter', () => highlightLink(link));
    link.addEventListener('focus', () => highlightLink(link));
    link.addEventListener('mouseleave', clear);
    link.addEventListener('blur', clear);
    link.setAttribute('tabindex', '0');
  });
  svg.querySelectorAll('.sankey-node,.sankey-label').forEach(node => {
    node.addEventListener('mouseenter', () => highlightNode(node.dataset.stem));
    node.addEventListener('focus', () => highlightNode(node.dataset.stem));
    node.addEventListener('mouseleave', clear);
    node.addEventListener('blur', clear);
    node.setAttribute('tabindex', '0');
  });
}

function render() {
  controls();
  metrics();
  drawSankey();
}

render();
window.addEventListener('resize', () => {
  window.clearTimeout(window.__fceSankeyResize);
  window.__fceSankeyResize = window.setTimeout(drawSankey, 120);
});
})();
