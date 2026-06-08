(function () {
  "use strict";

  const data = window.CQL_SITE_DATA;
  if (!data) return;
  const samples = window.CQL_SAMPLED_EXAMPLES || null;

  const state = {
    view: "all",
    search: "",
    hideGenericPairs: true,
    expandedStem: null,
  };

  const fmt = new Intl.NumberFormat("en");
  const pct = (value) => Number.isFinite(value) ? `${value.toFixed(value < 10 ? 2 : 1)}%` : "";
  const byId = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function setupTheme() {
    const button = byId("theme-toggle");
    if (!button) return;
    const current = () => document.documentElement.dataset.theme ||
      (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const sync = () => button.dataset.activeTheme = current();
    sync();
    button.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("cql-site-theme", next); } catch (error) {}
      sync();
    });
  }

  function sourceViews() {
    const sources = data.sources || [];
    const groups = Array.from(new Set(sources.map((source) => source.group || "unknown"))).sort();
    const views = [["all", "All", sources]];
    for (const group of groups) {
      views.push([group, group, sources.filter((source) => source.group === group)]);
    }
    return views;
  }

  function selectedSources() {
    const view = sourceViews().find((candidate) => candidate[0] === state.view);
    return view ? view[2] : data.sources || [];
  }

  function emptyPatternMap() {
    return new Map((data.patterns || []).map((pattern) => [pattern.stem, {
      stem: pattern.stem,
      label: pattern.label || pattern.stem,
      group: pattern.group || "",
      description: pattern.description || "",
      color: pattern.color || "",
      games: 0,
      instances: 0,
      exclusiveGames: 0,
      overlapGames: 0,
      summaryCount: pattern.summaryCount || 0,
    }]));
  }

  function aggregate() {
    const sources = selectedSources();
    const patterns = emptyPatternMap();
    const pairs = new Map();
    const eco = new Map();
    const ratings = new Map();
    const results = new Map();
    let annotatedGames = 0;
    let denominatorGames = 0;
    let gamesWithAnyMarker = 0;
    let patternGameIncidences = 0;
    let patternInstances = 0;
    let multiPatternGames = 0;
    let maxPatternsInGame = 0;

    for (const source of sources) {
      annotatedGames += source.annotatedGames || 0;
      denominatorGames += source.denominatorGames || source.annotatedGames || 0;
      gamesWithAnyMarker += source.gamesWithAnyMarker || 0;
      patternGameIncidences += source.patternGameIncidences || 0;
      patternInstances += source.patternInstances || 0;
      multiPatternGames += source.multiPatternGames || 0;
      maxPatternsInGame = Math.max(maxPatternsInGame, source.maxPatternsInGame || 0);
      for (const [stem, stats] of Object.entries(source.patterns || {})) {
        if (!patterns.has(stem)) patterns.set(stem, { stem, label: stem, games: 0, instances: 0, exclusiveGames: 0, overlapGames: 0, summaryCount: 0 });
        const row = patterns.get(stem);
        row.games += stats.games || 0;
        row.instances += stats.instances || 0;
        row.exclusiveGames += stats.exclusiveGames || 0;
        row.overlapGames += stats.overlapGames || 0;
      }
      for (const pair of source.pairs || []) {
        const key = `${pair[0]}\t${pair[1]}`;
        pairs.set(key, (pairs.get(key) || 0) + pair[2]);
      }
      mergeCounts(eco, source.ecoBases || {});
      mergeCounts(ratings, source.ratingBands || {});
      mergeCounts(results, source.results || {});
    }
    return { sources, patterns, pairs, eco, ratings, results, annotatedGames, denominatorGames, gamesWithAnyMarker, patternGameIncidences, patternInstances, multiPatternGames, maxPatternsInGame };
  }

  function mergeCounts(target, values) {
    for (const [key, count] of Object.entries(values)) {
      target.set(key, (target.get(key) || 0) + count);
    }
  }

  function patternMeta(stem) {
    return (data.patterns || []).find((pattern) => pattern.stem === stem) || { stem, label: stem };
  }

  function samplePayload(stem) {
    return samples?.views?.[state.view]?.stems?.[stem] || null;
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
  function lichessUrl(fen) { return fen ? `https://lichess.org/analysis/standard/${encodeURI(String(fen).replaceAll(' ', '_'))}` : 'https://lichess.org/analysis'; }
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
          if (piece && fileIndex < 8) pieces += `<g class="board-piece" data-piece="${escapeHtml(token)}" data-square="${String.fromCharCode(97 + fileIndex)}${8 - rankIndex}" transform="translate(${fileIndex} ${rankIndex}) scale(${1 / 45})">${piece}</g>`;
          fileIndex += 1;
        });
      });
    }
    const turn = String(fen || '').split(' ')[1] === 'b' ? 'black' : 'white';
    return `<a class="board-link" href="${escapeHtml(lichessUrl(fen))}" data-fen="${escapeHtml(fen)}" data-turn="${turn}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHtml(label)}"><svg class="board-svg" viewBox="0 0 8 8" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${squares}${pieces}</svg></a>`;
  }

  function exampleCard(example) {
    const clean = (value) => {
      const text = String(value ?? "").trim();
      return text && text !== "?" && text !== "-" ? text : "";
    };
    const player = (name, elo) => {
      const cleanName = clean(name);
      const cleanElo = clean(elo);
      if (!cleanName && !cleanElo) return "";
      return cleanElo ? `${cleanName || "Unknown"} (${cleanElo})` : cleanName;
    };
    const white = player(example.white, example.whiteElo);
    const black = player(example.black, example.blackElo);
    const title = [white, black].filter(Boolean).join(" vs ") || "Sampled game";
    const subtitle = [clean(example.event), clean(example.site)].filter(Boolean).join(" | ");
    const meta = [
      ["Result", example.result],
      ["Date", example.date],
      ["Move", example.moveSan ? `${example.fullmoveNumber || ""}${example.sideToMove === "white" ? "..." : "."} ${example.moveSan}` : ""],
      ["ECO", example.ecoBase],
      ["Source", example.sourceGroup || example.sourcePgn],
    ].filter(([, value]) => clean(value));
    return `<article class="example-card">${boardHtml(example.fen, "Open sampled position on Lichess analysis board")}<div class="example-meta"><strong class="example-title">${escapeHtml(title)}</strong><span class="example-subtitle">${escapeHtml(subtitle)}</span><dl>${meta.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl></div></article>`;
  }

  function detailHtml(row) {
    const payload = samplePayload(row.stem);
    const label = row.label || row.stem;
    if (!payload) {
      return `<tr class="detail-row"><td colspan="9"><div class="detail-inner"><div class="detail-head"><h3>${escapeHtml(label)} Examples</h3></div><p class="detail-note">No sampled examples are available for this marker in the selected corpus.</p></div></td></tr>`;
    }
    const examples = Array.isArray(payload.examples) ? payload.examples : [];
    const boardWord = Number(payload.sampled || 0) === 1 ? "board" : "boards";
    const note = `${fmt.format(payload.sampled || 0)} ${boardWord} shown from ${fmt.format(payload.available || 0)} marker game(s).`;
    return `<tr class="detail-row"><td colspan="9"><div class="detail-inner"><div class="detail-head"><h3>${escapeHtml(label)} Examples</h3><span>${escapeHtml(state.view)}</span></div><p class="detail-note">${escapeHtml(note)}</p><div class="examples-grid">${examples.map(exampleCard).join("")}</div></div></td></tr>`;
  }

  function genericStem() {
    const explicit = (data.genericStem || "").trim();
    if (explicit) return explicit;
    if ((data.patterns || []).some((pattern) => pattern.stem === "ismate")) return "ismate";
    return "";
  }

  function renderControls() {
    const controls = byId("view-controls");
    controls.innerHTML = "";
    for (const [value, label] of sourceViews()) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.className = value === state.view ? "active" : "";
      button.addEventListener("click", () => {
        state.view = value;
        state.expandedStem = null;
        render();
      });
      controls.appendChild(button);
    }

    const search = byId("pattern-search");
    search.value = state.search;
    search.oninput = () => {
      state.search = search.value.trim().toLowerCase();
      state.expandedStem = null;
      render();
    };

    const hideGeneric = byId("hide-generic-pairs");
    const generic = genericStem();
    hideGeneric.disabled = !generic;
    hideGeneric.checked = state.hideGenericPairs && Boolean(generic);
    hideGeneric.onchange = () => {
      state.hideGenericPairs = hideGeneric.checked;
      render();
    };
  }

  function renderMetrics(agg) {
    const denominatorLabel = data.hasSourceTotals ? "source games" : "annotated games";
    const metrics = [
      [fmt.format(agg.annotatedGames), "annotated games scanned"],
      [fmt.format(agg.denominatorGames), denominatorLabel],
      [fmt.format(agg.gamesWithAnyMarker), "games with marker"],
      [fmt.format(agg.patternGameIncidences), "marker-game incidences"],
      [fmt.format(agg.patternInstances), "marker instances"],
      [pct(agg.annotatedGames ? agg.multiPatternGames / agg.annotatedGames * 100 : 0), "multi-marker games"],
      [fmt.format(agg.maxPatternsInGame), "max markers in one game"],
    ];
    byId("metrics").innerHTML = metrics.map(([value, label]) =>
      `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`
    ).join("");
  }

  function renderPatternTable(agg) {
    const maxGames = Math.max(...Array.from(agg.patterns.values()).map((row) => row.games), 1);
    const rows = Array.from(agg.patterns.values())
      .filter((row) => row.games || row.summaryCount)
      .filter((row) => {
        if (!state.search) return true;
        return `${row.stem} ${row.label} ${row.group}`.toLowerCase().includes(state.search);
      })
      .sort((a, b) => b.games - a.games || a.label.localeCompare(b.label));
    byId("markers-note").textContent = `${fmt.format(rows.length)} markers shown. Counts are unique games unless marked as instances.`;
    byId("pattern-table").tHead.innerHTML = "<tr><th>Marker</th><th class=\"num\">Games</th><th class=\"num\">Instances</th><th class=\"num\">Corpus %</th><th class=\"num\">Annotated %</th><th>Scale</th><th class=\"num\">Exclusive</th><th class=\"num\">Co-occurs</th><th class=\"num\">Summary delta</th></tr>";
    byId("pattern-table").tBodies[0].innerHTML = rows.map((row) => {
      const delta = row.games - (row.summaryCount || 0);
      const expandable = Boolean(samples);
      const expanded = state.expandedStem === row.stem;
      const rowHtml = `
        <tr data-stem="${escapeHtml(row.stem)}" class="${expandable ? "expandable" : ""} ${expanded ? "expanded" : ""}" ${expandable ? "tabindex=\"0\"" : ""}>
          <td><strong>${escapeHtml(row.label)}</strong><br><span class="stem">${escapeHtml(row.stem)}${row.group ? ` | ${escapeHtml(row.group)}` : ""}</span></td>
          <td class="num">${fmt.format(row.games)}</td>
          <td class="num">${fmt.format(row.instances)}</td>
          <td class="num">${pct(agg.denominatorGames ? row.games / agg.denominatorGames * 100 : 0)}</td>
          <td class="num">${pct(agg.annotatedGames ? row.games / agg.annotatedGames * 100 : 0)}</td>
          <td class="bar-cell"><div class="bar-track"><div class="bar-fill" style="width:${Math.max(1, row.games / maxGames * 100)}%"></div></div></td>
          <td class="num">${fmt.format(row.exclusiveGames || 0)}</td>
          <td class="num">${fmt.format(row.overlapGames || 0)}</td>
          <td class="num ${delta === 0 ? "delta-ok" : "delta-warn"}">${fmt.format(delta)}</td>
        </tr>
      `;
      return expanded ? rowHtml + detailHtml(row) : rowHtml;
    }).join("");
    bindPatternExpansion();
  }

  function bindPatternExpansion() {
    if (!samples) return;
    document.querySelectorAll("#pattern-table tbody tr[data-stem]").forEach((row) => {
      row.onclick = () => {
        state.expandedStem = state.expandedStem === row.dataset.stem ? null : row.dataset.stem;
        render();
      };
      row.onkeydown = (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          row.click();
        }
      };
    });
  }

  function renderCountTable(id, noteId, label, counts, total, limit) {
    const rows = Array.from(counts.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, limit);
    byId(noteId).textContent = `${fmt.format(rows.length)} ${label} shown.`;
    byId(id).tHead.innerHTML = "<tr><th>Bucket</th><th class=\"num\">Games</th><th class=\"num\">Share</th></tr>";
    byId(id).tBodies[0].innerHTML = rows.map(([bucket, count]) => `
      <tr><td>${escapeHtml(bucket)}</td><td class="num">${fmt.format(count)}</td><td class="num">${pct(total ? count / total * 100 : 0)}</td></tr>
    `).join("");
  }

  function renderSourceTable(agg) {
    const rows = agg.sources.slice().sort((a, b) => (b.patternGameIncidences || 0) - (a.patternGameIncidences || 0) || a.label.localeCompare(b.label));
    byId("sources-note").textContent = `${fmt.format(rows.length)} sources.`;
    byId("source-table").tHead.innerHTML = "<tr><th>Source</th><th>Group</th><th class=\"num\">Annotated</th><th class=\"num\">Denominator</th><th class=\"num\">With marker</th><th class=\"num\">Incidences</th><th>Top marker</th></tr>";
    byId("source-table").tBodies[0].innerHTML = rows.map((source) => {
      const top = Object.entries(source.patterns || {}).sort((a, b) => (b[1].games || 0) - (a[1].games || 0))[0];
      const topMeta = top ? patternMeta(top[0]) : null;
      return `
        <tr>
          <td><strong>${escapeHtml(source.label)}</strong><br><span class="stem">${escapeHtml(source.outputPgn || source.path)}</span></td>
          <td>${escapeHtml(source.group || "unknown")}</td>
          <td class="num">${fmt.format(source.annotatedGames || 0)}</td>
          <td class="num">${fmt.format(source.denominatorGames || source.annotatedGames || 0)}</td>
          <td class="num">${fmt.format(source.gamesWithAnyMarker || 0)}</td>
          <td class="num">${fmt.format(source.patternGameIncidences || 0)}</td>
          <td>${topMeta ? `${escapeHtml(topMeta.label)} <span class="muted">${fmt.format(top[1].games || 0)}</span>` : ""}</td>
        </tr>
      `;
    }).join("");
  }

  function renderPairTable(agg) {
    const generic = genericStem();
    let rows = Array.from(agg.pairs.entries()).map(([key, count]) => {
      const [a, b] = key.split("\t");
      return { a, b, count };
    });
    if (generic && state.hideGenericPairs) {
      rows = rows.filter((row) => row.a !== generic && row.b !== generic);
    }
    rows.sort((a, b) => b.count - a.count || a.a.localeCompare(b.a) || a.b.localeCompare(b.b));
    rows = rows.slice(0, 40);
    byId("pairs-note").textContent = `${fmt.format(rows.length)} strongest pairs shown.`;
    byId("pair-table").tHead.innerHTML = "<tr><th>Marker A</th><th>Marker B</th><th class=\"num\">Games</th><th class=\"num\">Annotated %</th></tr>";
    byId("pair-table").tBodies[0].innerHTML = rows.map((row) => `
      <tr>
        <td>${escapeHtml(patternMeta(row.a).label)}<br><span class="stem">${escapeHtml(row.a)}</span></td>
        <td>${escapeHtml(patternMeta(row.b).label)}<br><span class="stem">${escapeHtml(row.b)}</span></td>
        <td class="num">${fmt.format(row.count)}</td>
        <td class="num">${pct(agg.annotatedGames ? row.count / agg.annotatedGames * 100 : 0)}</td>
      </tr>
    `).join("");
  }

  function render() {
    byId("page-title").textContent = data.title || "CQL Incidence Dashboard";
    byId("run-meta").textContent = `${data.inputLabel || ""} | ${fmt.format((data.sources || []).length)} sources | ${fmt.format((data.patterns || []).length)} markers`;
    renderControls();
    const agg = aggregate();
    renderMetrics(agg);
    renderPatternTable(agg);
    renderCountTable("eco-table", "eco-note", "ECO bases", agg.eco, agg.annotatedGames, 30);
    renderCountTable("rating-table", "rating-note", "rating bands", agg.ratings, agg.annotatedGames, 20);
    renderSourceTable(agg);
    renderPairTable(agg);
  }

  setupTheme();
  render();
})();
