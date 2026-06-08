(function () {
  "use strict";

  const data = window.MATE_PATTERN_DATA;
  if (!data) return;

  const state = {
    view: "all",
    search: "",
    hideGenericPairs: true,
  };

  const fmt = new Intl.NumberFormat("en");
  const pct = (value) => Number.isFinite(value) ? `${value.toFixed(value < 10 ? 2 : 1)}%` : "";
  const byId = (id) => document.getElementById(id);

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
      try { localStorage.setItem("mates-theme", next); } catch (error) {}
      sync();
    });
  }

  function classifySources() {
    const sources = data.sources || [];
    return {
      all: sources,
      otb: sources.filter((source) => source.group === "OTB"),
      online: sources.filter((source) => source.group === "Online"),
    };
  }

  function sourceSet() {
    return classifySources()[state.view] || [];
  }

  function aggregate() {
    const sources = sourceSet();
    const patternCounts = new Map();
    const pairCounts = new Map();
    let games = 0;
    let incidences = 0;
    let multiPatternGames = 0;
    let maxPatternsInGame = 0;

    for (const source of sources) {
      games += source.games || 0;
      incidences += source.incidences || 0;
      multiPatternGames += source.multiPatternGames || 0;
      maxPatternsInGame = Math.max(maxPatternsInGame, source.maxPatternsInGame || 0);
      for (const [stem, count] of Object.entries(source.patterns || {})) {
        patternCounts.set(stem, (patternCounts.get(stem) || 0) + count);
      }
      for (const pair of source.pairs || []) {
        const key = `${pair[0]}\t${pair[1]}`;
        pairCounts.set(key, (pairCounts.get(key) || 0) + pair[2]);
      }
    }

    return { sources, patternCounts, pairCounts, games, incidences, multiPatternGames, maxPatternsInGame };
  }

  function patternMeta(stem) {
    return data.patterns.find((pattern) => pattern.stem === stem) || { stem, label: stem };
  }

  function renderControls() {
    const controls = byId("view-controls");
    controls.innerHTML = "";
    for (const [value, label] of [["all", "All"], ["otb", "OTB"], ["online", "Online"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.className = value === state.view ? "active" : "";
      button.addEventListener("click", () => {
        state.view = value;
        render();
      });
      controls.appendChild(button);
    }

    const search = byId("pattern-search");
    search.value = state.search;
    search.addEventListener("input", () => {
      state.search = search.value.trim().toLowerCase();
      render();
    }, { once: true });

    const hideGeneric = byId("hide-ismate-pairs");
    hideGeneric.checked = state.hideGenericPairs;
    hideGeneric.addEventListener("change", () => {
      state.hideGenericPairs = hideGeneric.checked;
      render();
    }, { once: true });
  }

  function renderMetrics(agg) {
    const metrics = [
      [fmt.format(agg.games), "annotated games"],
      [fmt.format(agg.incidences), "pattern incidences"],
      [pct(agg.games ? agg.multiPatternGames / agg.games * 100 : 0), "multi-pattern games"],
      [fmt.format(agg.patternCounts.size), "patterns observed"],
      [fmt.format(agg.sources.length), "source buckets"],
      [fmt.format(agg.maxPatternsInGame), "max patterns in one game"],
    ];
    byId("metrics").innerHTML = metrics.map(([value, label]) =>
      `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`
    ).join("");
  }

  function renderPatternTable(agg) {
    const maxCount = Math.max(...Array.from(agg.patternCounts.values()), 1);
    const rows = Array.from(agg.patternCounts.entries())
      .map(([stem, count]) => {
        const meta = patternMeta(stem);
        const q = `${stem} ${meta.label}`.toLowerCase();
        const summary = meta.summaryCount || 0;
        return {
          stem,
          label: meta.label,
          count,
          summary,
          delta: count - summary,
          share: agg.games ? count / agg.games * 100 : 0,
          incidenceShare: agg.incidences ? count / agg.incidences * 100 : 0,
          exclusive: meta.exclusiveGames || 0,
          overlap: meta.overlapGames || 0,
          include: !state.search || q.includes(state.search),
        };
      })
      .filter((row) => row.include)
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));

    byId("patterns-note").textContent = `${fmt.format(rows.length)} shown, sorted by observed games.`;
    byId("pattern-table").tHead.innerHTML = "<tr><th>Pattern</th><th class=\"num\">Games</th><th class=\"num\">Game %</th><th>Scale</th><th class=\"num\">Incidence %</th><th class=\"num\">Exclusive</th><th class=\"num\">Co-occurs</th><th class=\"num\">Summary delta</th></tr>";
    byId("pattern-table").tBodies[0].innerHTML = rows.map((row) => `
      <tr>
        <td><strong>${escapeHtml(row.label)}</strong><br><span class="stem">${escapeHtml(row.stem)}</span></td>
        <td class="num">${fmt.format(row.count)}</td>
        <td class="num">${pct(row.share)}</td>
        <td class="bar-cell"><div class="bar-track"><div class="bar-fill" style="width:${Math.max(1, row.count / maxCount * 100)}%"></div></div></td>
        <td class="num">${pct(row.incidenceShare)}</td>
        <td class="num">${fmt.format(row.exclusive)}</td>
        <td class="num">${fmt.format(row.overlap)}</td>
        <td class="num ${row.delta === 0 ? "delta-ok" : "delta-warn"}">${row.delta === 0 ? "0" : fmt.format(row.delta)}</td>
      </tr>
    `).join("");
  }

  function renderSourceTable(agg) {
    const rows = agg.sources.slice().sort((a, b) => b.games - a.games || a.label.localeCompare(b.label));
    byId("sources-note").textContent = `${fmt.format(rows.length)} source bucket${rows.length === 1 ? "" : "s"}.`;
    byId("source-table").tHead.innerHTML = "<tr><th>Source</th><th>Group</th><th class=\"num\">Games</th><th class=\"num\">Incidences</th><th class=\"num\">Multi %</th><th>Top pattern</th></tr>";
    byId("source-table").tBodies[0].innerHTML = rows.map((source) => {
      const top = Object.entries(source.patterns || {}).sort((a, b) => b[1] - a[1])[0];
      const topMeta = top ? patternMeta(top[0]) : null;
      return `
        <tr>
          <td><strong>${escapeHtml(source.label)}</strong><br><span class="stem">${escapeHtml(source.outputPgn)}</span></td>
          <td>${escapeHtml(source.group)}</td>
          <td class="num">${fmt.format(source.games || 0)}</td>
          <td class="num">${fmt.format(source.incidences || 0)}</td>
          <td class="num">${pct(source.games ? (source.multiPatternGames || 0) / source.games * 100 : 0)}</td>
          <td>${topMeta ? `${escapeHtml(topMeta.label)} <span class="muted">${fmt.format(top[1])}</span>` : ""}</td>
        </tr>
      `;
    }).join("");
  }

  function renderPairTable(agg) {
    let rows = Array.from(agg.pairCounts.entries()).map(([key, count]) => {
      const [a, b] = key.split("\t");
      return { a, b, count };
    });
    if (state.hideGenericPairs) {
      rows = rows.filter((row) => row.a !== "ismate" && row.b !== "ismate");
    }
    rows.sort((a, b) => b.count - a.count || a.a.localeCompare(b.a) || a.b.localeCompare(b.b));
    rows = rows.slice(0, 40);
    byId("pairs-note").textContent = `${fmt.format(rows.length)} strongest pairs shown.`;
    byId("pair-table").tHead.innerHTML = "<tr><th>Pattern A</th><th>Pattern B</th><th class=\"num\">Games</th><th class=\"num\">Game %</th></tr>";
    byId("pair-table").tBodies[0].innerHTML = rows.map((row) => `
      <tr>
        <td>${escapeHtml(patternMeta(row.a).label)}<br><span class="stem">${escapeHtml(row.a)}</span></td>
        <td>${escapeHtml(patternMeta(row.b).label)}<br><span class="stem">${escapeHtml(row.b)}</span></td>
        <td class="num">${fmt.format(row.count)}</td>
        <td class="num">${pct(agg.games ? row.count / agg.games * 100 : 0)}</td>
      </tr>
    `).join("");
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function render() {
    byId("page-title").textContent = data.title || "Checkmate Pattern Incidence";
    byId("run-meta").textContent = `${data.runDir || ""} | ${fmt.format(data.totals.sourceCount)} sources | ${fmt.format(data.totals.patternCount)} CQL patterns`;
    renderControls();
    const agg = aggregate();
    renderMetrics(agg);
    renderPatternTable(agg);
    renderSourceTable(agg);
    renderPairTable(agg);
  }

  setupTheme();
  render();
})();
