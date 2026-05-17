#!/usr/bin/env python3
"""Build a local exploratory overlay plot for FCE endings by ECO code.

This is intentionally separate from the production static site.  It uses the
already-computed opening_counts.json and source totals, then emits a single
self-contained HTML file for judging whether the visualization is informative.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_SNAPSHOT = (
    "/Volumes/2025archive/FCE-table/eval-snapshots/"
    "fce-lumbras-all-tablebase-knbpawns-20260516-223833/snapshot.json"
)
DEFAULT_OPENING_COUNTS = (
    "/Volumes/2025archive/FCE-table/eval-snapshots/"
    "fce-lumbras-all-tablebase-knbpawns-20260516-223833/opening_counts.json"
)
DEFAULT_SOURCE_TOTALS = (
    "/Volumes/2025archive/FCE-table/source-totals/"
    "lumbras-source-totals-2026-05-15.json"
)
DEFAULT_ECO_CSV = "data/openings/lumbras_eco_codes.csv"
DEFAULT_OUTPUT = "/private/tmp/fce-opening-distribution-overlay.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a local FCE ending-distribution overlay by ECO code."
    )
    parser.add_argument("--snapshot-json", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--opening-counts-json", default=DEFAULT_OPENING_COUNTS)
    parser.add_argument("--source-totals-json", default=DEFAULT_SOURCE_TOTALS)
    parser.add_argument("--eco-catalog-csv", default=DEFAULT_ECO_CSV)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def opening_catalog(path: str | Path) -> dict[str, str]:
    names_by_base: dict[str, list[str]] = defaultdict(list)
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                base = (row.get("eco_base") or row.get("eco") or "").strip().upper()
                name = (row.get("name") or "").strip()
                if not base or not name or name.lower() == "start position":
                    continue
                if name not in names_by_base[base]:
                    names_by_base[base].append(name)
    except FileNotFoundError:
        return {}

    catalog: dict[str, str] = {}
    for base, names in names_by_base.items():
        shown = names[:4]
        suffix = " / ".join(shown)
        if len(names) > len(shown):
            suffix += f" / +{len(names) - len(shown)} more"
        catalog[base] = suffix
    return catalog


def flatten_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in snapshot["rows"]:
        rows.append(
            {
                "stem": row["stem"],
                "rowId": row.get("rowId", ""),
                "label": row["label"],
                "chapter": row.get("chapter", ""),
            }
        )
        for aux in row.get("auxiliaryRows", []):
            label = aux["label"]
            lowered = label.lower()
            if lowered == "without pawns":
                label = f"{row['label']} without pawns"
            elif lowered == "connected pawns":
                label = f"{row['label']} with connected pawns"
            rows.append(
                {
                    "stem": aux["stem"],
                    "rowId": aux.get("rowId", ""),
                    "label": label,
                    "chapter": aux.get("chapter", row.get("chapter", "")),
                }
            )
    return rows


def build_payload(
    snapshot: dict[str, Any],
    opening_counts: dict[str, Any],
    source_totals: dict[str, Any],
    eco_names: dict[str, str],
) -> dict[str, Any]:
    rows = flatten_rows(snapshot)
    stems = [row["stem"] for row in rows]
    views = ["all", "otb", "online"]
    thresholds = [int(t) for t in opening_counts["thresholds"]]

    eco_set: set[str] = set()
    for view in views:
        eco_set.update(source_totals.get("openingTotals", {}).get(view, {}).keys())
    eco_set.discard("unknown")

    openings: list[dict[str, Any]] = []
    for eco in sorted(eco_set):
        totals = {
            view: int(source_totals.get("openingTotals", {}).get(view, {}).get(eco, 0))
            for view in views
        }
        if not any(totals.values()):
            continue
        entry: dict[str, Any] = {
            "eco": eco,
            "name": eco_names.get(eco, ""),
            "label": f"{eco}: {eco_names.get(eco, '').strip()}" if eco_names.get(eco) else eco,
            "totals": totals,
            "views": {},
        }
        for view in views:
            view_counts = opening_counts["views"].get(view, {}).get("thresholds", {})
            entry["views"][view] = {}
            for threshold in thresholds:
                opening = (
                    view_counts.get(str(threshold), {})
                    .get("openings", {})
                    .get(eco, {})
                )
                row_counts = opening.get("rows", {})
                matched_rows = int(opening.get("metrics", {}).get("matchedRows", 0))
                total_games = totals[view]
                quantities = [
                    int(row_counts.get(stem, {}).get("quantity", 0)) for stem in stems
                ]
                corpus_pct = [
                    (quantity / total_games * 100.0) if total_games else 0.0
                    for quantity in quantities
                ]
                matched_share = [
                    (quantity / matched_rows * 100.0) if matched_rows else 0.0
                    for quantity in quantities
                ]
                entry["views"][view][str(threshold)] = {
                    "matchedRows": matched_rows,
                    "quantity": quantities,
                    "corpusPct": corpus_pct,
                    "matchedShare": matched_share,
                }
        openings.append(entry)

    return {
        "title": "FCE ending distribution by ECO code",
        "generatedFrom": {
            "snapshot": str(Path(DEFAULT_SNAPSHOT).name),
            "openingCounts": str(Path(DEFAULT_OPENING_COUNTS).name),
        },
        "thresholds": thresholds,
        "views": views,
        "rows": rows,
        "openings": openings,
    }


def render_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, separators=(",", ":"))
    title = html.escape(payload["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f7f7f4;
  --panel: #fffefa;
  --ink: #202124;
  --muted: #62645f;
  --line: #d8d3c8;
  --blue: #2b6f9f;
  --red: #c14f43;
  --green: #5f9c5b;
  --grid: rgba(32,33,36,.12);
  --eco-line: rgba(43,111,159,.105);
}}
body {{
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--ink);
}}
main {{
  max-width: 1480px;
  margin: 0 auto;
  padding: 28px 24px 48px;
}}
h1 {{
  margin: 0 0 8px;
  font-size: clamp(28px, 4vw, 46px);
  letter-spacing: 0;
}}
p {{
  margin: 0;
  max-width: 940px;
  color: var(--muted);
  line-height: 1.5;
}}
.panel {{
  margin-top: 22px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0,0,0,.05);
}}
.controls {{
  display: grid;
  grid-template-columns: repeat(5, minmax(160px, 1fr));
  gap: 12px;
  padding: 14px;
  align-items: end;
}}
label {{
  display: grid;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
}}
select, input {{
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
  color: var(--ink);
  padding: 9px 10px;
  font: inherit;
}}
.summary {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 14px 14px;
  color: var(--muted);
  font-size: 13px;
}}
.pill {{
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 10px;
  background: #fff;
}}
.plot-wrap {{
  position: relative;
  overflow-x: auto;
  border-top: 1px solid var(--line);
  padding: 12px;
}}
svg {{
  display: block;
  min-width: 1180px;
  width: 100%;
  height: 640px;
}}
.axis text {{
  fill: var(--muted);
  font-size: 11px;
}}
.axis line, .axis path {{
  stroke: var(--line);
}}
.grid-line {{
  stroke: var(--grid);
  stroke-width: 1;
}}
.eco-line {{
  fill: none;
  stroke: var(--eco-line);
  stroke-width: 1.1;
}}
.eco-line.highlight {{
  stroke: var(--blue);
  stroke-width: 3;
  opacity: 1;
}}
.mean-line {{
  fill: none;
  stroke: #1d1f20;
  stroke-width: 2.3;
  opacity: .9;
}}
.focus-dot {{
  fill: var(--red);
  stroke: #fff;
  stroke-width: 1.5;
}}
.hover-target {{
  fill: transparent;
  cursor: crosshair;
}}
.tooltip {{
  position: fixed;
  pointer-events: none;
  z-index: 4;
  max-width: 320px;
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: rgba(255,254,250,.98);
  color: var(--ink);
  box-shadow: 0 8px 28px rgba(0,0,0,.12);
  font-size: 13px;
  line-height: 1.35;
  opacity: 0;
  transform: translate(10px, 10px);
}}
.tables {{
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(280px, 1fr);
  gap: 16px;
  margin-top: 16px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}}
caption {{
  text-align: left;
  font-weight: 800;
  margin-bottom: 8px;
}}
th, td {{
  border-bottom: 1px solid var(--line);
  padding: 7px 8px;
  text-align: right;
  vertical-align: top;
}}
th:first-child, td:first-child,
th:nth-child(2), td:nth-child(2) {{
  text-align: left;
}}
.note {{
  margin-top: 12px;
  color: var(--muted);
  font-size: 13px;
}}
@media (max-width: 900px) {{
  main {{ padding: 18px 12px 32px; }}
  .controls {{ grid-template-columns: 1fr 1fr; }}
  .tables {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <p>This exploratory page overlays one ECO curve per opening bucket.  The default metric is the percentage of games from that opening which reach each ending, using the already-computed FCE opening aggregate; no PGNs, CQL, Syzygy files, or SQLite queries are run here.</p>

  <section class="panel">
    <div class="controls">
      <label>Corpus
        <select id="view">
          <option value="all">All</option>
          <option value="otb">OTB</option>
          <option value="online">Online</option>
        </select>
      </label>
      <label>Minimum half-moves
        <select id="threshold"></select>
      </label>
      <label>Metric
        <select id="metric">
          <option value="corpusPct">Opening corpus %</option>
          <option value="matchedShare">Opening matched share %</option>
        </select>
      </label>
      <label>Minimum games per ECO
        <input id="minGames" type="number" min="0" step="1000" value="10000">
      </label>
      <label>Highlighted opening
        <input id="openingInput" list="openingOptions" value="B90">
        <datalist id="openingOptions"></datalist>
      </label>
    </div>
    <div class="summary" id="summary"></div>
    <div class="plot-wrap">
      <svg id="plot" role="img" aria-label="Opening ending-distribution overlay"></svg>
      <div id="tooltip" class="tooltip"></div>
    </div>
  </section>

  <section class="tables">
    <div class="panel" style="padding:14px">
      <table id="deviationTable">
        <caption>Most unusual openings by curve distance</caption>
        <thead><tr><th>ECO</th><th>Name</th><th>Games</th><th>RMS pp</th></tr></thead>
        <tbody></tbody>
      </table>
      <p class="note">RMS pp is the root-mean-square percentage-point distance from the all-opening mean curve for the selected corpus, threshold, metric, and minimum-game filter.</p>
    </div>
    <div class="panel" style="padding:14px">
      <table id="selectedTable">
        <caption>Largest deviations for highlighted opening</caption>
        <thead><tr><th>ID</th><th>Ending</th><th>Opening %</th><th>Mean %</th><th>Diff pp</th></tr></thead>
        <tbody></tbody>
      </table>
      <p class="note">This table is usually more readable than the full overlay for answering which endings an opening changes most.</p>
    </div>
  </section>
</main>
<script>
const DATA = {data_json};

const state = {{
  view: "all",
  threshold: String(DATA.thresholds[0]),
  metric: "corpusPct",
  minGames: 10000,
  opening: "B90",
}};

const els = {{
  view: document.getElementById("view"),
  threshold: document.getElementById("threshold"),
  metric: document.getElementById("metric"),
  minGames: document.getElementById("minGames"),
  openingInput: document.getElementById("openingInput"),
  openingOptions: document.getElementById("openingOptions"),
  summary: document.getElementById("summary"),
  svg: document.getElementById("plot"),
  tooltip: document.getElementById("tooltip"),
  deviationBody: document.querySelector("#deviationTable tbody"),
  selectedBody: document.querySelector("#selectedTable tbody"),
}};

function fmt(n, digits = 2) {{
  if (!Number.isFinite(n)) return "0";
  return n.toLocaleString(undefined, {{ maximumFractionDigits: digits, minimumFractionDigits: digits }});
}}
function fmtInt(n) {{
  return Math.round(n || 0).toLocaleString();
}}
function esc(s) {{
  return String(s ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
}}
function linePath(values, x, y) {{
  return values.map((v, i) => `${{i === 0 ? "M" : "L"}}${{x(i).toFixed(2)}},${{y(v).toFixed(2)}}`).join(" ");
}}
function currentOpenings() {{
  return DATA.openings.filter(o => (o.totals[state.view] || 0) >= state.minGames);
}}
function openingValues(opening) {{
  return opening.views[state.view][state.threshold][state.metric];
}}
function meanCurve(openings) {{
  const n = DATA.rows.length;
  const out = Array(n).fill(0);
  if (!openings.length) return out;
  for (const opening of openings) {{
    const values = openingValues(opening);
    for (let i = 0; i < n; i++) out[i] += values[i] || 0;
  }}
  return out.map(v => v / openings.length);
}}
function rmsDistance(values, mean) {{
  let sum = 0;
  for (let i = 0; i < values.length; i++) {{
    const diff = (values[i] || 0) - (mean[i] || 0);
    sum += diff * diff;
  }}
  return Math.sqrt(sum / values.length);
}}
function selectedOpening(openings = DATA.openings) {{
  const raw = state.opening.trim().toUpperCase();
  const eco = (raw.match(/[A-E][0-9]{{2}}/) || [raw])[0];
  return openings.find(o => o.eco === eco) || DATA.openings.find(o => o.eco === eco) || openings[0] || DATA.openings[0];
}}
function yMaxFor(openings, mean, selected) {{
  const vals = [];
  for (const opening of openings) vals.push(...openingValues(opening));
  vals.push(...mean);
  if (selected) vals.push(...openingValues(selected));
  vals.sort((a, b) => a - b);
  const p99 = vals[Math.max(0, Math.floor(vals.length * 0.99) - 1)] || 1;
  const max = Math.max(p99 * 1.25, ...mean, ...(selected ? openingValues(selected) : []), 0.05);
  return max;
}}
function render() {{
  state.view = els.view.value;
  state.threshold = els.threshold.value;
  state.metric = els.metric.value;
  state.minGames = Math.max(0, Number(els.minGames.value) || 0);
  state.opening = els.openingInput.value || state.opening;

  const openings = currentOpenings();
  const mean = meanCurve(openings);
  const selected = selectedOpening(openings);
  if (selected && els.openingInput.value.toUpperCase() !== selected.eco) {{
    // Keep free typing intact unless a redraw was caused by a different control.
  }}

  const width = Math.max(1180, els.svg.clientWidth || 1180);
  const height = 640;
  const margin = {{ top: 22, right: 28, bottom: 150, left: 64 }};
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const n = DATA.rows.length;
  const x = i => margin.left + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
  const yMax = yMaxFor(openings, mean, selected);
  const y = v => margin.top + plotH - (Math.min(v, yMax) / yMax) * plotH;
  const ticks = 5;

  const parts = [];
  parts.push(`<rect width="${{width}}" height="${{height}}" fill="transparent"></rect>`);
  for (let t = 0; t <= ticks; t++) {{
    const value = yMax * t / ticks;
    const yy = y(value);
    parts.push(`<line class="grid-line" x1="${{margin.left}}" y1="${{yy}}" x2="${{width - margin.right}}" y2="${{yy}}"></line>`);
    parts.push(`<text x="${{margin.left - 10}}" y="${{yy + 4}}" text-anchor="end" fill="var(--muted)" font-size="11">${{fmt(value, 1)}}%</text>`);
  }}
  for (let i = 0; i < n; i++) {{
    const xx = x(i);
    parts.push(`<line x1="${{xx}}" y1="${{margin.top}}" x2="${{xx}}" y2="${{margin.top + plotH}}" stroke="rgba(0,0,0,.045)"></line>`);
    const row = DATA.rows[i];
    const label = esc(row.rowId || row.label);
    parts.push(`<text x="${{xx}}" y="${{height - 118}}" transform="rotate(55 ${{xx}} ${{height - 118}})" text-anchor="start" fill="var(--muted)" font-size="11">${{label}}</text>`);
  }}
  for (const opening of openings) {{
    const cls = selected && opening.eco === selected.eco ? "eco-line highlight" : "eco-line";
    const values = openingValues(opening);
    parts.push(`<path class="${{cls}}" d="${{linePath(values, x, y)}}"><title>${{esc(opening.label)}}; ${{fmtInt(opening.totals[state.view])}} games</title></path>`);
  }}
  parts.push(`<path class="mean-line" d="${{linePath(mean, x, y)}}"><title>Mean across filtered ECO buckets</title></path>`);
  if (selected) {{
    const values = openingValues(selected);
    for (let i = 0; i < n; i++) {{
      parts.push(`<circle class="focus-dot" cx="${{x(i)}}" cy="${{y(values[i])}}" r="2.6"></circle>`);
    }}
  }}
  for (let i = 0; i < n; i++) {{
    const left = i === 0 ? margin.left - 12 : (x(i - 1) + x(i)) / 2;
    const right = i === n - 1 ? width - margin.right + 12 : (x(i) + x(i + 1)) / 2;
    parts.push(`<rect class="hover-target" data-i="${{i}}" x="${{left}}" y="${{margin.top}}" width="${{Math.max(1, right-left)}}" height="${{plotH}}"></rect>`);
  }}
  els.svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
  els.svg.innerHTML = parts.join("");

  els.summary.innerHTML = [
    `<span class="pill">${{fmtInt(openings.length)}} ECO buckets shown</span>`,
    `<span class="pill">${{selected ? esc(selected.eco) + ": " + esc(selected.name || selected.eco) : "No highlighted ECO"}}</span>`,
    `<span class="pill">${{selected ? fmtInt(selected.totals[state.view]) : "0"}} games in highlighted ECO</span>`,
    `<span class="pill">Y-axis: ${{state.metric === "corpusPct" ? "games from this opening reaching the ending" : "share of matched ending incidences within this opening"}}</span>`,
  ].join("");

  renderTables(openings, mean, selected);
  wireHover(mean, selected);
}}
function renderTables(openings, mean, selected) {{
  const ranked = openings.map(opening => {{
    const values = openingValues(opening);
    return {{ opening, rms: rmsDistance(values, mean) }};
  }}).sort((a, b) => b.rms - a.rms).slice(0, 14);
  els.deviationBody.innerHTML = ranked.map(({{opening, rms}}) => `
    <tr><td>${{esc(opening.eco)}}</td><td>${{esc(opening.name || "")}}</td><td>${{fmtInt(opening.totals[state.view])}}</td><td>${{fmt(rms, 3)}}</td></tr>
  `).join("");

  if (!selected) {{
    els.selectedBody.innerHTML = "";
    return;
  }}
  const values = openingValues(selected);
  const diffs = DATA.rows.map((row, i) => ({{
    row,
    value: values[i] || 0,
    mean: mean[i] || 0,
    diff: (values[i] || 0) - (mean[i] || 0),
  }})).sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff)).slice(0, 14);
  els.selectedBody.innerHTML = diffs.map(d => `
    <tr><td>${{esc(d.row.rowId || "")}}</td><td>${{esc(d.row.label)}}</td><td>${{fmt(d.value, 3)}}%</td><td>${{fmt(d.mean, 3)}}%</td><td>${{d.diff >= 0 ? "+" : ""}}${{fmt(d.diff, 3)}}</td></tr>
  `).join("");
}}
function wireHover(mean, selected) {{
  const selectedValues = selected ? openingValues(selected) : [];
  els.svg.querySelectorAll(".hover-target").forEach(rect => {{
    rect.addEventListener("mousemove", event => {{
      const i = Number(rect.dataset.i);
      const row = DATA.rows[i];
      const selectedValue = selectedValues[i] || 0;
      const meanValue = mean[i] || 0;
      els.tooltip.innerHTML = `
        <strong>${{esc(row.rowId ? row.rowId + " " : "")}}${{esc(row.label)}}</strong><br>
        ${{selected ? esc(selected.eco) + ": " + fmt(selectedValue, 3) + "%" : ""}}<br>
        Mean: ${{fmt(meanValue, 3)}}%<br>
        Difference: ${{selectedValue - meanValue >= 0 ? "+" : ""}}${{fmt(selectedValue - meanValue, 3)}} pp
      `;
      els.tooltip.style.left = event.clientX + "px";
      els.tooltip.style.top = event.clientY + "px";
      els.tooltip.style.opacity = "1";
    }});
    rect.addEventListener("mouseleave", () => {{
      els.tooltip.style.opacity = "0";
    }});
  }});
}}

function init() {{
  els.threshold.innerHTML = DATA.thresholds.map(t => `<option value="${{t}}">${{t}}</option>`).join("");
  els.openingOptions.innerHTML = DATA.openings.map(o => `<option value="${{esc(o.eco)}}">${{esc(o.label)}}</option>`).join("");
  for (const el of [els.view, els.threshold, els.metric, els.minGames]) {{
    el.addEventListener("input", render);
  }}
  els.openingInput.addEventListener("change", render);
  els.openingInput.addEventListener("input", () => {{
    const raw = els.openingInput.value.trim().toUpperCase();
    if (/^[A-E][0-9]{{2}}$/.test(raw)) render();
  }});
  window.addEventListener("resize", render);
  render();
}}
init();
</script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    snapshot = read_json(args.snapshot_json)
    opening_counts = read_json(args.opening_counts_json)
    source_totals = read_json(args.source_totals_json)
    eco_names = opening_catalog(args.eco_catalog_csv)
    payload = build_payload(snapshot, opening_counts, source_totals, eco_names)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(payload), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Openings: {len(payload['openings'])}")
    print(f"Endings: {len(payload['rows'])}")


if __name__ == "__main__":
    main()
