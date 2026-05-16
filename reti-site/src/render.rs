use crate::aggregate::Snapshot;
use crate::SiteResult;
use serde_json::{Map, Value};
use std::fs;
use std::path::Path;

pub fn render_html(snapshot: &Snapshot) -> SiteResult<String> {
    render_html_value(&serde_json::to_value(snapshot)?)
}

pub fn render_snapshot_file(snapshot_json: &Path, output_html: &Path) -> SiteResult<()> {
    let text = fs::read_to_string(snapshot_json)?;
    let snapshot: Value = serde_json::from_str(&text)?;
    fs::write(output_html, render_html_value(&snapshot)?)?;
    Ok(())
}

pub fn write_samples_js(samples_json: &Path, output_js: &Path) -> SiteResult<()> {
    let text = fs::read_to_string(samples_json)?;
    let samples: Value = serde_json::from_str(&text)?;
    let Some(views) = samples.get("views").and_then(Value::as_object) else {
        let payload = safe_json_for_script(&serde_json::to_string(&samples)?);
        fs::write(
            output_js,
            format!("window.FCE_SAMPLED_EXAMPLES = {payload};\n"),
        )?;
        return Ok(());
    };

    let stem = output_js
        .file_stem()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("sampled_examples");
    let chunk_dir = output_js.with_file_name(stem);
    if chunk_dir.exists() {
        fs::remove_dir_all(&chunk_dir)?;
    }
    fs::create_dir_all(&chunk_dir)?;

    let mut manifest = Map::new();
    manifest.insert(
        "schemaVersion".to_string(),
        samples
            .get("schemaVersion")
            .cloned()
            .unwrap_or_else(|| Value::String("fce-sampled-examples-chunks-v1".to_string())),
    );
    manifest.insert(
        "sampleSize".to_string(),
        samples
            .get("sampleSize")
            .cloned()
            .unwrap_or(Value::from(60)),
    );
    manifest.insert(
        "chunkMode".to_string(),
        Value::String("view-threshold-stem-js".to_string()),
    );

    let mut manifest_views = Map::new();
    for (view_key, view_value) in views {
        let mut manifest_view = Map::new();
        let Some(thresholds) = view_value.get("thresholds").and_then(Value::as_object) else {
            continue;
        };
        let mut manifest_thresholds = Map::new();
        for (threshold_key, threshold_value) in thresholds {
            let mut manifest_threshold = Map::new();
            let Some(stems) = threshold_value.get("stems").and_then(Value::as_object) else {
                continue;
            };
            let mut manifest_stems = Map::new();
            for (stem_key, payload) in stems {
                let view_part = safe_path_part(view_key);
                let threshold_part = safe_path_part(threshold_key);
                let stem_part = safe_path_part(stem_key);
                let dir = chunk_dir.join(&view_part).join(&threshold_part);
                fs::create_dir_all(&dir)?;
                let chunk_path = dir.join(format!("{stem_part}.js"));
                let chunk_key = sample_chunk_key(view_key, threshold_key, stem_key);
                let chunk_payload = safe_json_for_script(&serde_json::to_string(payload)?);
                let chunk_key_json = safe_json_for_script(&serde_json::to_string(&chunk_key)?);
                fs::write(
                    &chunk_path,
                    format!(
                        "(function(){{window.FCE_SAMPLE_CHUNKS=window.FCE_SAMPLE_CHUNKS||{{}};window.FCE_SAMPLE_CHUNKS[{chunk_key_json}]={chunk_payload};}}());\n"
                    ),
                )?;
                manifest_stems.insert(
                    stem_key.clone(),
                    serde_json::json!({
                        "src": format!("{stem}/{view_part}/{threshold_part}/{stem_part}.js"),
                        "available": payload.get("available").cloned().unwrap_or(Value::from(0)),
                        "sampled": payload.get("sampled").cloned().unwrap_or(Value::from(0)),
                    }),
                );
            }
            manifest_threshold.insert("stems".to_string(), Value::Object(manifest_stems));
            manifest_thresholds.insert(threshold_key.clone(), Value::Object(manifest_threshold));
        }
        manifest_view.insert("thresholds".to_string(), Value::Object(manifest_thresholds));
        manifest_views.insert(view_key.clone(), Value::Object(manifest_view));
    }
    manifest.insert("views".to_string(), Value::Object(manifest_views));

    let manifest_payload = safe_json_for_script(&serde_json::to_string(&Value::Object(manifest))?);
    fs::write(
        output_js,
        format!(
            "window.FCE_SAMPLE_CHUNKS=window.FCE_SAMPLE_CHUNKS||{{}};\nwindow.FCE_SAMPLED_EXAMPLES_MANIFEST={manifest_payload};\n"
        ),
    )?;
    Ok(())
}

pub fn render_html_value(snapshot: &Value) -> SiteResult<String> {
    let data = safe_json_for_script(&serde_json::to_string(snapshot)?);
    let raw_title = snapshot
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or("FCE endings");
    let title = display_title(raw_title);
    let comparison_note = reference_note_html(snapshot);
    Ok(format!(
        r##"<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{}</title>
  <script>
    try {{
      const theme = localStorage.getItem("fce-theme");
      if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    }} catch (error) {{}}
  </script>
  <style>
    :root {{ color-scheme: light; --bg:#f7f7f4; --fg:#1d1f21; --muted:#666; --line:#d8d8d0; --panel:#fff; --panel-soft:#fbfbf8; --accent:#2f6f9f; --accent-soft:#e7f0f6; --win:#7fb069; --draw:#b9b9b9; --loss:#d66b5f; --board-light:#f0d9b5; --board-dark:#b58863; --example-bg:#fff; --shadow:0 1px 2px rgba(0,0,0,0.05),0 8px 28px rgba(0,0,0,0.04); }}
    :root[data-theme="dark"] {{ color-scheme: dark; --bg:#161715; --fg:#eeeeea; --muted:#aaa69d; --line:#383a35; --panel:#20221f; --panel-soft:#1b1d1a; --accent:#79afd4; --accent-soft:#1d3342; --example-bg:#151d23; --shadow:0 1px 2px rgba(0,0,0,0.3),0 10px 28px rgba(0,0,0,0.18); }}
    @media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark; --bg:#161715; --fg:#eeeeea; --muted:#aaa69d; --line:#383a35; --panel:#20221f; --panel-soft:#1b1d1a; --accent:#79afd4; --accent-soft:#1d3342; --example-bg:#151d23; --shadow:0 1px 2px rgba(0,0,0,0.3),0 10px 28px rgba(0,0,0,0.18); }} }}
    * {{ box-sizing:border-box; }}
    html {{ -webkit-text-size-adjust:100%; }}
    body {{ min-width:320px; margin:0; font:14px/1.4 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg); }}
    main {{ width:100%; max-width:1440px; margin:0 auto; padding:22px; }}
    .page-head {{ border-bottom:1px solid var(--line); padding:8px 0 18px; margin-bottom:18px; }}
    .header-main {{ display:flex; align-items:flex-start; justify-content:space-between; gap:14px; }}
    .theme-toggle {{ flex:0 0 auto; width:38px; height:38px; display:grid; place-items:center; padding:0; border:1px solid var(--line); border-radius:8px; background:var(--panel); color:var(--fg); cursor:pointer; }}
    .theme-toggle:hover {{ border-color:var(--accent); }}
    .theme-icon {{ display:block; width:19px; height:19px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }}
    .theme-icon-sun {{ display:none; }}
    .theme-toggle[data-active-theme="dark"] .theme-icon-moon {{ display:none; }}
    .theme-toggle[data-active-theme="dark"] .theme-icon-sun {{ display:block; }}
    .eyebrow {{ color:var(--accent); font-size:12px; font-weight:700; letter-spacing:0; text-transform:uppercase; margin:0 0 6px; }}
    h1 {{ font-size:34px; line-height:1.08; margin:0 0 10px; max-width:920px; }}
    .lede {{ color:var(--muted); font-size:16px; max-width:940px; margin:0; }}
    .badges {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
    .badge {{ border:1px solid var(--line); border-radius:999px; background:var(--panel); padding:5px 8px; font-size:12px; }}
    .explanation {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:18px; margin:18px 0; }}
    .explanation h2 {{ margin:0 0 10px; }}
    .method-body {{ max-width:980px; }}
    .method-body p {{ margin:0 0 10px; color:var(--muted); }}
    .method-body p:last-child {{ margin-bottom:0; }}
    .method-body strong {{ color:var(--fg); }}
    .source-links {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; padding-top:14px; border-top:1px solid var(--line); }}
    .source-links a {{ display:inline-flex; align-items:center; min-height:34px; border:1px solid var(--line); border-radius:999px; background:var(--panel-soft); color:var(--fg); padding:7px 10px; text-decoration:none; }}
    .source-links a:hover {{ border-color:var(--accent); color:var(--accent); }}
    .citation-note {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:14px 18px; margin:18px 0; }}
    .citation-note h2 {{ margin:0 0 8px; }}
    .citation-note p {{ margin:0 0 10px; color:var(--muted); max-width:980px; }}
    .citation-note p:last-child {{ margin-bottom:0; }}
    .citation-note strong {{ color:var(--fg); }}
    .citation-note a {{ color:var(--accent); }}
    .controls {{ display:flex; flex-wrap:wrap; align-items:flex-end; gap:12px 18px; margin:18px 0; }}
    .control-group {{ flex:0 1 auto; min-width:0; }}
    .controls strong {{ display:block; margin-bottom:6px; }}
    .seg {{ display:inline-flex; width:max-content; max-width:100%; overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:var(--panel); -webkit-overflow-scrolling:touch; }}
    button {{ flex:0 0 auto; min-height:36px; border:0; border-right:1px solid var(--line); background:transparent; color:inherit; padding:8px 12px; cursor:pointer; white-space:nowrap; }}
    button:last-child {{ border-right:0; }}
    button.active {{ background:var(--accent); color:white; }}
    button:focus-visible {{ outline:3px solid var(--accent); outline-offset:-3px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,160px),1fr)); gap:10px; margin:14px 0; }}
    .metric {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:10px; }}
    .metric strong {{ display:block; font-size:20px; }}
    .metric span {{ color:var(--muted); }}
    h2 {{ font-size:18px; margin:22px 0 8px; }}
    .table-wrap {{ max-width:100%; overflow:auto; border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); background:var(--panel); -webkit-overflow-scrolling:touch; scrollbar-gutter:stable; }}
    table {{ width:100%; min-width:920px; border-collapse:collapse; background:var(--panel); }}
    th, td {{ border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:middle; }}
    th.num, td.num {{ text-align:right; }}
    th {{ position:sticky; top:0; background:var(--panel); z-index:1; }}
    th[data-sort] {{ cursor:pointer; user-select:none; white-space:nowrap; }}
    th[data-sort]::after {{ content:""; display:inline-block; width:1em; color:var(--muted); }}
    th.sorted-asc::after {{ content:"▲"; }}
    th.sorted-desc::after {{ content:"▼"; }}
    .aux td:first-child {{ color:var(--muted); }}
    .aux-label {{ color:var(--muted); font-size:12px; margin-left:6px; white-space:nowrap; }}
    .bar-shell {{ position:relative; display:block; min-width:140px; }}
    .bar-shell:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; border-radius:5px; }}
    .bar-shell::after {{ content:attr(data-tip); position:absolute; left:50%; bottom:calc(100% + 7px); transform:translate(-50%,4px); z-index:20; opacity:0; pointer-events:none; white-space:nowrap; border:1px solid var(--line); border-radius:6px; box-shadow:var(--shadow); background:var(--fg); color:var(--bg); padding:4px 7px; font-size:12px; line-height:1.2; transition:opacity .12s ease, transform .12s ease; }}
    .bar-shell:hover::after, .bar-shell:focus-visible::after {{ opacity:1; transform:translate(-50%,0); }}
    .bar {{ display:flex; width:100%; height:20px; min-width:inherit; overflow:hidden; border-radius:3px; background:#ddd; }}
    .bar span {{ display:block; min-width:0; overflow:hidden; text-align:center; font-size:12px; line-height:20px; color:#111; white-space:nowrap; }}
    .win {{ background:var(--win); }} .draw {{ background:var(--draw); }} .loss {{ background:var(--loss); }}
    tr[data-stem] {{ cursor:pointer; }}
    tr[data-stem]:hover {{ background:var(--panel-soft); }}
    .detail-row > td {{ padding:0; background:var(--panel-soft); }}
    .detail-inner {{ padding:14px; border-bottom:1px solid var(--line); }}
    .detail-head {{ display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:8px 12px; margin-bottom:10px; }}
    .detail-head h3 {{ margin:0; font-size:16px; }}
    .detail-head span {{ color:var(--muted); white-space:nowrap; }}
    .detail-note {{ color:var(--muted); margin:0 0 10px; }}
    .detail-panels {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr)); gap:12px; margin:12px 0; }}
    .detail-panel {{ min-width:0; overflow:hidden; border:1px solid var(--line); border-radius:6px; background:var(--panel); padding:10px; }}
    .detail-panel.matrix-panel {{ grid-column:span 2; }}
    .detail-panel h4 {{ margin:0 0 8px; font-size:13px; }}
    .detail-panel p {{ margin:0; color:var(--muted); }}
    .detail-subtitle {{ color:var(--muted); font-size:12px; margin:0 0 8px; }}
    .detail-stat-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px; }}
    .detail-stat {{ border:1px solid var(--line); border-radius:4px; background:var(--panel-soft); padding:7px; }}
    .detail-stat span {{ display:block; color:var(--muted); font-size:11px; }}
    .detail-stat strong {{ display:block; font-size:16px; }}
    .matrix-wrap {{ max-width:100%; overflow-x:auto; }}
    .matrix {{ min-width:380px; width:100%; border-collapse:collapse; font-size:12px; }}
    .matrix th, .matrix td {{ padding:5px; }}
    .examples-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr)); gap:12px; max-height:620px; overflow:auto; padding:2px; -webkit-overflow-scrolling:touch; }}
    .example-card {{ min-width:0; overflow:hidden; border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); background:var(--example-bg); }}
    .board-link {{ position:relative; display:block; width:100%; aspect-ratio:1; overflow:hidden; border-bottom:1px solid var(--line); }}
    .board-link:focus-visible {{ outline:3px solid var(--accent); outline-offset:-3px; }}
    .board-svg {{ display:block; width:100%; height:100%; }}
    .board-square.light {{ fill:var(--board-light); }}
    .board-square.dark {{ fill:var(--board-dark); }}
    .board-piece {{ pointer-events:none; filter:drop-shadow(0 0.015625rem 0.015625rem rgba(0,0,0,0.35)); }}
    .example-meta {{ padding:8px 9px 9px; }}
    .example-title {{ display:block; font-size:11px; line-height:1.25; overflow-wrap:anywhere; }}
    .example-subtitle {{ display:block; color:var(--muted); font-size:11px; line-height:1.25; margin-top:3px; overflow-wrap:anywhere; }}
    .example-meta dl {{ display:grid; grid-template-columns:auto minmax(0,1fr); gap:2px 7px; margin:7px 0 0; font-size:11px; }}
    .example-meta dt {{ color:var(--muted); white-space:nowrap; }}
    .example-meta dd {{ margin:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    @media (max-width:980px) {{ main {{ padding:18px; }} .detail-panel.matrix-panel {{ grid-column:auto; }} }}
    @media (max-width:760px) {{ main {{ padding:12px; }} h1 {{ font-size:28px; }} .lede {{ font-size:14px; }} table {{ min-width:860px; font-size:12px; }} th, td {{ padding:7px; }} .bar-shell {{ min-width:110px; }} .detail-inner {{ position:sticky; left:0; width:calc(100vw - 24px); max-width:calc(100vw - 24px); padding:12px; }} .detail-panels {{ grid-template-columns:1fr; }} .matrix {{ min-width:380px; }} .examples-grid {{ grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr)); gap:10px; max-height:none; }} .header-main {{ align-items:flex-start; }} }}
    @media (max-width:520px) {{ h1 {{ font-size:24px; }} .page-head {{ padding-top:4px; }} .header-main {{ gap:10px; }} .theme-toggle {{ width:36px; height:36px; }} .badges {{ gap:6px; }} .badge {{ font-size:11px; }} .explanation {{ padding:12px; }} .source-links a {{ width:100%; justify-content:center; }} .metrics {{ grid-template-columns:1fr 1fr; gap:8px; }} .metric {{ padding:8px; }} .metric strong {{ font-size:18px; }} .examples-grid {{ grid-template-columns:1fr; }} .example-meta {{ padding:8px; }} }}
    @media (hover:none) {{ button {{ min-height:40px; }} tr[data-stem] {{ -webkit-tap-highlight-color:var(--accent-soft); }} }}
    @media print {{ :root {{ --bg:#fff; --fg:#111; --muted:#555; --line:#ccc; --panel:#fff; --panel-soft:#fff; }} body {{ background:#fff; }} main {{ max-width:none; padding:0; }} .theme-toggle, .controls {{ display:none; }} .table-wrap, .examples-grid, .matrix-wrap {{ overflow:visible; }} table {{ min-width:0; }} th {{ position:static; }} }}
  </style>
</head>
<body>
<main>
  <header class="page-head">
    <div class="header-main">
      <div>
        <p class="eyebrow">Fundamental Chess Endings snapshot</p>
        <h1>{}</h1>
      </div>
      <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle light and dark mode">
        <svg class="theme-icon theme-icon-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8z"></path></svg>
        <svg class="theme-icon theme-icon-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>
      </button>
    </div>
    <p class="lede">A reusable, tablebase-aware view of FCE ending incidence across Lumbra's Gigabase. The expensive PGN scan and Syzygy evaluation have already been precomputed; this page only switches between stored aggregate views.</p>
    <div class="badges"><span class="badge">Exact incidence counts</span><span class="badge">All / OTB / Online</span><span class="badge">First run per game-ending</span><span class="badge">Syzygy WDL for <=5-piece first markers</span></div>
  </header>
  <section class="explanation" aria-labelledby="methodology-title">
    <h2 id="methodology-title">Methodology</h2>
    <div class="method-body">
      <p><strong>Reference point.</strong> This project is inspired by the frequency table in Karsten Muller and Frank Lamprecht's <em>Fundamental Chess Endings</em>. The published values are not reproduced here; the closest public summary is the chess endgame frequency table on Wikipedia.</p>
      <p><strong>Corpus.</strong> The source games are from Lumbra's Gigabase, split into All, OTB, and Online views. The denominators for Corpus % are the original source-game totals for the selected corpus, not just the games that matched an ending.</p>
      <p><strong>Extraction pipeline.</strong> Reti builds combined CQL marker files, scans the annotated PGNs once, and stores reusable snapshot artifacts. Each game can count once for each FCE ending stem, while different endings in the same game can both count.</p>
      <p><strong>Thresholds.</strong> The marker extractor finds consecutive runs of the same ending. The first run for a game-ending pair is kept, and the half-move buttons filter by that first run length. The Games column is therefore a count of qualifying game-ending incidences, not a count of mutually exclusive games.</p>
      <p><strong>Tablebase positions.</strong> For a qualifying game-ending incidence, if the first marker position has five pieces or fewer, that occurrence is stored in the tablebase-position table. The TB positions column counts those occurrence rows under the active corpus and threshold. It is not a games column, and it is not generally a distinct-FEN column: identical FENs in different games can contribute more than once. If a row shows 92 TB positions, read that as 92 qualifying first-marker occurrences for the current filters; the number of distinct FENs may be the same or lower.</p>
      <p><strong>Syzygy evaluation.</strong> Identical tablebase FENs are deduplicated before probing, so the same position is evaluated only once internally. The displayed TB WDL percentages and tablebase-to-final-result matrix are then weighted by the occurrence rows, because the question here is how often those evaluated positions arise in the corpus.</p>
      <p><strong>Results and perspective.</strong> Actual result means the final PGN result for every qualifying game-ending incidence. W/D/L categories use the named material side, not colour; symmetric rows have no named side, so decisive outcomes are counted separately from draws.</p>
      <p><strong>Reading the table.</strong> Corpus % is row games divided by all games in the selected corpus. Matched share is row games divided by all counted ending incidences for the active corpus and threshold. Click a row for tablebase-to-final-result details and sampled boards; click a column header to sort.</p>
    </div>
    <nav class="source-links" aria-label="Source links">
      <a href="https://en.wikipedia.org/wiki/Chess_endgame#Frequency_table" target="_blank" rel="noopener noreferrer">Wikipedia frequency table</a>
      <a href="https://books.google.com/books?vid=ISBN1901983536" target="_blank" rel="noopener noreferrer">Fundamental Chess Endings</a>
      <a href="https://github.com/elma16/reti" target="_blank" rel="noopener noreferrer">Reti GitHub</a>
      <a href="https://lumbrasgigabase.com/en/download-in-pgn-format-en/" target="_blank" rel="noopener noreferrer">Lumbra's Gigabase</a>
    </nav>
  </section>
  {}
  <div class="controls">
    <div class="control-group"><strong>Corpus</strong> <span class="seg" id="view-controls"></span></div>
    <div class="control-group"><strong>Minimum half-moves</strong> <span class="seg" id="threshold-controls"></span></div>
  </div>
  <div class="metrics" id="metrics"></div>
  <div class="table-wrap">
    <table id="ending-table">
      <thead></thead>
      <tbody></tbody>
    </table>
  </div>
</main>
<script id="snapshot-data" type="application/json">{}</script>
<script src="sampled_examples.js"></script>
<script>
const snapshot = JSON.parse(document.getElementById('snapshot-data').textContent);
const sampleManifest = window.FCE_SAMPLED_EXAMPLES_MANIFEST || null;
window.FCE_SAMPLE_CHUNKS = window.FCE_SAMPLE_CHUNKS || {{}};
const sampleLoadPromises = new Map();
const sampleLoadErrors = new Map();
if (snapshot.sourceBuckets) console.debug('FCE source buckets', snapshot.sourceBuckets);
let activeView = snapshot.datasetViews.default || 'all';
let activeThreshold = '1';
let sortKey = 'sortIndex';
let sortDir = 1;
let expandedStem = null;
const fmtInt = n => Number(n || 0).toLocaleString();
function fmtPct(n) {{
  const value = Number(n || 0);
  if (!Number.isFinite(value) || value === 0) return '0%';
  const abs = Math.abs(value);
  if (abs >= 0.001) return `${{value.toFixed(3)}}%`;
  const decimals = Math.min(10, Math.max(4, Math.ceil(-Math.log10(abs)) + 2));
  return `${{value.toFixed(decimals).replace(/0+$/, '').replace(/\\.$/, '')}}%`;
}}
function pct(a,b) {{ return b ? Math.round((a/b)*1000)/10 : 0; }}
function esc(value) {{ return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch])); }}
function viewOrder() {{ return ['all','otb','online'].filter(k => snapshot.datasetViews.views[k]); }}
function activeTheme() {{ return document.documentElement.dataset.theme || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); }}
function updateThemeToggle() {{
  const button = document.getElementById('theme-toggle');
  if (!button) return;
  const theme = activeTheme();
  button.dataset.activeTheme = theme;
  button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
}}
document.getElementById('theme-toggle')?.addEventListener('click', () => {{
  const next = activeTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try {{ localStorage.setItem('fce-theme', next); }} catch (error) {{}}
  updateThemeToggle();
}});
updateThemeToggle();
function outcomeBar(payload, totalKey='totalPositions') {{
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
  const label = `W ${{ap}}% | D ${{bp}}% | L ${{cp}}%`;
  const text = p => p >= 10 ? `${{p}}%` : '';
  return `<span class="bar-shell" tabindex="0" data-tip="${{esc(label)}}" aria-label="${{esc(label)}}"><span class="bar"><span class="win" style="width:${{ap}}%">${{text(ap)}}</span><span class="draw" style="width:${{bp}}%">${{text(bp)}}</span><span class="loss" style="width:${{cp}}%">${{text(cp)}}</span></span></span>`;
}}
function controls() {{
  const vc = document.getElementById('view-controls');
  vc.innerHTML = '';
  viewOrder().map(k => snapshot.datasetViews.views[k]).forEach(v => {{
    const b = document.createElement('button'); b.textContent = v.label; b.className = v.key === activeView ? 'active' : '';
    b.onclick = () => {{ activeView = v.key; render(); }}; vc.appendChild(b);
  }});
  const tc = document.getElementById('threshold-controls');
  const thresholds = Object.keys(snapshot.datasetViews.views[activeView].thresholdViews);
  tc.innerHTML = '';
  thresholds.forEach(t => {{
    const b = document.createElement('button'); b.textContent = t; b.className = t === activeThreshold ? 'active' : '';
    b.onclick = () => {{ activeThreshold = t; render(); }}; tc.appendChild(b);
  }});
}}
function tableHeadHtml() {{
  return `<tr><th data-sort="sortIndex">ID</th><th data-sort="label">Ending</th><th class="num" data-sort="quantity" title="Qualifying game-ending incidences: each game can count once for each ending stem.">Games</th><th class="num" data-sort="percentage" title="Row games divided by all games in the selected corpus.">Corpus %</th><th class="num" data-sort="matchedShare" title="Row games divided by all counted ending incidences in the active view.">Matched share</th><th class="num" data-sort="tablebasePositions" title="<=5-piece first-marker occurrence rows, not unique FENs and not total games.">TB positions</th><th data-sort="tbWinPct" title="Syzygy WDL over TB position occurrence rows. Repeated FENs are probed once but counted per occurrence.">TB WDL</th><th data-sort="actualWinPct" title="Final PGN result from the named-material side perspective.">Actual result</th></tr>`;
}}
function tableColspan() {{
  return 8;
}}
function rowHtml(row, stats) {{
  const w = stats?.tablebaseWdl || {{}};
  const actual = stats?.actualResult || {{}};
  const label = rowDisplayLabel(row);
  return `<tr class="${{row.isAux ? 'aux' : ''}}" data-stem="${{esc(row.stem)}}" tabindex="0"><td>${{esc(row.rowId || '')}}</td><td>${{row.isAux ? '↳ ' : ''}}${{esc(label)}}</td><td class="num">${{fmtInt(stats?.quantity)}}</td><td class="num">${{fmtPct(stats?.percentage)}}</td><td class="num">${{fmtPct(stats?.matchedShare)}}</td><td class="num">${{fmtInt(w.totalPositions)}}</td><td>${{outcomeBar(w,'totalPositions')}}</td><td>${{outcomeBar(actual,'totalGames')}}</td></tr>`;
}}
function rowDisplayLabel(row) {{
  if (!row.isAux) return row.label;
  const child = String(row.label || '').trim();
  const parent = String(row.parentLabel || '').trim();
  if (!parent) return child;
  if (/^without pawns$/i.test(child)) return `${{parent}} without pawns`;
  if (/^connected pawns$/i.test(child)) return `${{parent}} with connected pawns`;
  return `${{parent}}: ${{child}}`;
}}
function rowSortValue(row, tv) {{
  const stats = tv.rows[row.stem] || {{}};
  const w = stats.tablebaseWdl || {{}};
  if (sortKey === 'label') return row.label;
  if (sortKey === 'quantity') return Number(stats.quantity || 0);
  if (sortKey === 'percentage') return Number(stats.percentage || 0);
  if (sortKey === 'matchedShare') return Number(stats.matchedShare || 0);
  if (sortKey === 'tablebasePositions') return Number(w.totalPositions || 0);
  if (sortKey === 'tbWinPct') return pct(Number(w.sideWins || w.symmetricDecisive || 0), Number(w.totalPositions || 0));
  if (sortKey === 'actualWinPct') {{
    const actual = stats.actualResult || {{}};
    return pct(Number(actual.sideWins || actual.symmetricDecisive || 0), Number(actual.totalGames || 0));
  }}
  return Number(row.sortIndex || 0);
}}
function flatRows() {{
  const out = [];
  snapshot.rows.forEach(row => {{
    out.push({{...row, isAux:false}});
    (row.auxiliaryRows || []).forEach((aux, idx) => out.push({{...aux, rowId: auxId(row, idx), isAux:true, parentLabel:row.label, parentStem:row.stem}}));
  }});
  return out;
}}
function auxId(parent, index) {{
  const letter = String.fromCharCode(97 + index);
  if (parent.rowId) return `${{parent.rowId}}${{letter}}`;
  if (parent.stem === '10-7-1Qbrr') return `10.7${{letter}}`;
  return letter;
}}
function sortedRows(tv) {{
  const rows = flatRows();
  rows.sort((a,b) => {{
    const av = rowSortValue(a, tv);
    const bv = rowSortValue(b, tv);
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * sortDir;
    return (av - bv) * sortDir || (Number(a.sortIndex || 0) - Number(b.sortIndex || 0));
  }});
  return rows;
}}
function bindSorting() {{
  document.querySelectorAll('#ending-table th[data-sort]').forEach(th => {{
    th.onclick = () => {{
      const next = th.dataset.sort;
      if (sortKey === next) sortDir *= -1; else {{ sortKey = next; sortDir = next === 'sortIndex' ? 1 : -1; }}
      render();
    }};
    th.setAttribute('aria-sort', th.dataset.sort === sortKey ? (sortDir > 0 ? 'ascending' : 'descending') : 'none');
    th.classList.toggle('sorted-asc', th.dataset.sort === sortKey && sortDir > 0);
    th.classList.toggle('sorted-desc', th.dataset.sort === sortKey && sortDir < 0);
  }});
}}
const pieceSvgs = {{
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
}};
function lichessUrl(fen) {{ return fen ? `https://lichess.org/analysis/standard/${{encodeURI(fen.replaceAll(' ', '_'))}}` : 'https://lichess.org/analysis'; }}
function boardHtml(fen, label) {{
  const board = String(fen || '').split(' ')[0];
  const ranks = board.split('/');
  let squares = '';
  for (let rankIndex = 0; rankIndex < 8; rankIndex++) {{
    for (let fileIndex = 0; fileIndex < 8; fileIndex++) {{
      const tone = (rankIndex + fileIndex) % 2 === 0 ? 'light' : 'dark';
      squares += `<rect class="board-square ${{tone}}" x="${{fileIndex}}" y="${{rankIndex}}" width="1" height="1"></rect>`;
    }}
  }}
  let pieces = '';
  if (ranks.length === 8) {{
    ranks.forEach((rank, rankIndex) => {{
      let fileIndex = 0;
      [...rank].forEach(token => {{
        if (/\d/.test(token)) {{ fileIndex += Number(token); return; }}
        const piece = pieceSvgs[token];
        if (piece && fileIndex < 8) pieces += `<g class="board-piece" data-piece="${{esc(token)}}" data-square="${{String.fromCharCode(97 + fileIndex)}}${{8 - rankIndex}}" transform="translate(${{fileIndex}} ${{rankIndex}}) scale(${{1 / 45}})">${{piece}}</g>`;
        fileIndex += 1;
      }});
    }});
  }}
  const turn = String(fen || '').split(' ')[1] === 'b' ? 'black' : 'white';
  return `<a class="board-link" href="${{esc(lichessUrl(fen))}}" data-fen="${{esc(fen)}}" data-turn="${{turn}}" target="_blank" rel="noopener noreferrer" aria-label="${{esc(label)}}"><svg class="board-svg" viewBox="0 0 8 8" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${{squares}}${{pieces}}</svg></a>`;
}}
function sampleChunkKey(view, threshold, stem) {{ return `${{view}}|${{threshold}}|${{stem}}`; }}
function fullSamplePayload(stem) {{
  const full = window.FCE_SAMPLED_EXAMPLES || snapshot.sampledExamples || null;
  return full?.views?.[activeView]?.thresholds?.[activeThreshold]?.stems?.[stem] || null;
}}
function sampleManifestEntry(stem) {{
  return sampleManifest?.views?.[activeView]?.thresholds?.[activeThreshold]?.stems?.[stem] || null;
}}
function samplePayload(stem) {{
  const full = fullSamplePayload(stem);
  if (full) return full;
  return window.FCE_SAMPLE_CHUNKS[sampleChunkKey(activeView, activeThreshold, stem)] || null;
}}
function sampleLimit() {{
  const full = window.FCE_SAMPLED_EXAMPLES || snapshot.sampledExamples || null;
  return Number(sampleManifest?.sampleSize || full?.sampleSize || 60);
}}
function requestSampleLoad(stem) {{
  if (samplePayload(stem)) return;
  const entry = sampleManifestEntry(stem);
  const key = sampleChunkKey(activeView, activeThreshold, stem);
  if (!entry?.src || sampleLoadPromises.has(key) || sampleLoadErrors.has(key)) return;
  const promise = new Promise((resolve, reject) => {{
    const script = document.createElement('script');
    script.async = true;
    script.src = entry.src;
    script.onload = () => resolve(samplePayload(stem));
    script.onerror = () => reject(new Error(`Failed to load ${{entry.src}}`));
    document.head.appendChild(script);
  }});
  sampleLoadPromises.set(key, promise);
  promise.then(() => {{
    if (expandedStem === stem) render();
  }}).catch(error => {{
    sampleLoadErrors.set(key, error);
    if (expandedStem === stem) render();
  }});
}}
function outcomeCounts(payload, totalKey) {{
  return [
    ['Side wins', payload?.sideWins || 0],
    ['Draws', payload?.sideDraws || 0],
    ['Side losses', payload?.sideLosses || 0],
    ['Decisive', payload?.symmetricDecisive || 0],
    ['Unknown', payload?.unknownGames || payload?.unknownPositions || 0],
    ['Total', payload?.[totalKey] || 0]
  ];
}}
function statsPanel(title, payload, totalKey, note) {{
  const counts = outcomeCounts(payload || {{}}, totalKey);
  return `<section class="detail-panel"><h4>${{esc(title)}}</h4><div class="detail-stat-grid">${{counts.map(([k,v]) => `<div class="detail-stat"><span>${{esc(k)}}</span><strong>${{fmtInt(v)}}</strong></div>`).join('')}}</div><p class="detail-note">${{esc(note)}}</p></section>`;
}}
function tbResultMatrix(w) {{
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
  const label = key => ({{win:'TB win', draw:'TB draw', loss:'TB loss', decisive:'TB decisive', unknown:'TB unknown'}}[key] || key);
  const header = columns.map(([, title]) => `<th class="num">${{esc(title)}}</th>`).join('');
  const body = rows.map(row => `<tr><th>${{esc(label(row.tbOutcome))}}</th>${{columns.map(([key]) => `<td class="num">${{fmtInt(row[key])}}</td>`).join('')}}<td class="num">${{fmtInt(row.total)}}</td></tr>`).join('');
  return `<section class="detail-panel matrix-panel"><h4>Tablebase vs Final Result</h4><p class="detail-subtitle">${{esc(subtitle)}}</p><div class="matrix-wrap"><table class="matrix"><thead><tr><th>Tablebase</th>${{header}}<th class="num">Total</th></tr></thead><tbody>${{body}}</tbody></table></div></section>`;
}}
function detailStats(row, stats) {{
  const actual = stats?.actualResult || {{}};
  const w = stats?.tablebaseWdl || {{}};
  const hasTablebase = Number(w?.totalPositions || 0) > 0;
  return `<div class="detail-panels">${{
    statsPanel('Actual result', actual, 'totalGames', 'Final PGN result for every qualifying game-ending incidence.')
  }}${{
    hasTablebase ? statsPanel('Tablebase WDL', w, 'totalPositions', 'Syzygy WDL over <=5-piece first-marker occurrence rows. Repeated FENs are probed once internally but counted per game-ending occurrence here.') : ''
  }}${{hasTablebase ? tbResultMatrix(w) : ''}}</div>`;
}}
function exampleCard(example) {{
  const rating = value => {{
    const text = String(value ?? '').trim();
    return text && text !== '?' && text !== '-' ? text : '';
  }};
  const player = (name, elo) => {{
    const cleanName = String(name || '').trim();
    const cleanElo = rating(elo);
    if (!cleanName && !cleanElo) return '';
    return cleanElo ? `${{cleanName || 'Unknown'}} (${{cleanElo}})` : cleanName;
  }};
  const white = player(example.white, example.whiteElo || example.whiteRating);
  const black = player(example.black, example.blackElo || example.blackRating);
  const title = [white, black].filter(Boolean).join(' vs ') || 'Sampled game';
  const clean = value => {{
    const text = String(value ?? '').trim();
    return text && text !== '?' && text !== '-' ? text : '';
  }};
  const tournament = clean(example.event);
  const location = clean(example.site);
  const subtitle = [tournament, location].filter(Boolean).join(' | ');
  const meta = [
    ['Result', example.result],
    ['Date', example.date],
    ['Side to move', example.sideToMove === 'black' ? 'Black' : 'White']
  ].filter(([, value]) => value !== undefined && value !== null && String(value) !== '');
  return `<article class="example-card">${{boardHtml(example.fen, 'Open sampled position on Lichess analysis board')}}<div class="example-meta"><strong class="example-title">${{esc(title)}}</strong><span class="example-subtitle">${{esc(subtitle)}}</span><dl>${{meta.map(([k,v]) => `<dt>${{esc(k)}}</dt><dd>${{esc(v)}}</dd>`).join('')}}</dl></div></article>`;
}}
function detailHtml(row) {{
  const payload = samplePayload(row.stem);
  const entry = sampleManifestEntry(row.stem);
  const key = sampleChunkKey(activeView, activeThreshold, row.stem);
  const view = snapshot.datasetViews.views[activeView];
  const tv = view.thresholdViews[activeThreshold] || view.thresholdViews[Object.keys(view.thresholdViews)[0]];
  const stats = tv.rows[row.stem] || {{}};
  const detailTitle = rowDisplayLabel(row);
  const colspan = tableColspan();
  if (!payload) {{
    requestSampleLoad(row.stem);
    const error = sampleLoadErrors.get(key);
    const message = error
      ? `Sample boards could not be loaded from ${{entry?.src || 'sample sidecar'}}.`
      : entry
        ? `Loading sample boards from ${{entry.src}}...`
        : 'No sampled examples are available for this ending in the selected corpus and threshold.';
    return `<tr class="detail-row"><td colspan="${{colspan}}"><div class="detail-inner"><div class="detail-head"><h3>${{esc(row.rowId ? row.rowId + ' ' : '')}}${{esc(detailTitle)}} Details</h3><span>${{esc(activeView.toUpperCase())}} | ≥${{esc(activeThreshold)}} half-move(s)</span></div>${{detailStats(row, stats)}}<p class="detail-note">${{esc(message)}}</p></div></td></tr>`;
  }}
  const examples = Array.isArray(payload.examples) ? payload.examples : [];
  console.debug('FCE sampled example metadata', {{ view: activeView, threshold: activeThreshold, stem: row.stem, row, payload, examples }});
  const note = `${{fmtInt(payload.sampled)}} board(s) shown from ${{fmtInt(payload.available)}} qualifying game-ending incidence(s). At most ${{fmtInt(sampleLimit())}} games are sampled for each selected corpus, threshold, and ending; if fewer qualify, all available games are shown.`;
  return `<tr class="detail-row"><td colspan="${{colspan}}"><div class="detail-inner"><div class="detail-head"><h3>${{esc(row.rowId ? row.rowId + ' ' : '')}}${{esc(detailTitle)}} Details</h3><span>${{esc(activeView.toUpperCase())}} | ≥${{esc(activeThreshold)}} half-move(s)</span></div>${{detailStats(row, stats)}}<p class="detail-note">${{note}}</p><div class="examples-grid">${{examples.map(exampleCard).join('')}}</div></div></td></tr>`;
}}
function bindRowExpansion() {{
  document.querySelectorAll('#ending-table tbody tr[data-stem]').forEach(row => {{
    row.onclick = () => {{ expandedStem = expandedStem === row.dataset.stem ? null : row.dataset.stem; render(); }};
    row.onkeydown = event => {{ if (event.key === 'Enter' || event.key === ' ') {{ event.preventDefault(); row.click(); }} }};
  }});
}}
function render() {{
  controls();
  const view = snapshot.datasetViews.views[activeView];
  if (!view.thresholdViews[activeThreshold]) activeThreshold = Object.keys(view.thresholdViews)[0];
  const tv = view.thresholdViews[activeThreshold];
  const table = document.getElementById('ending-table');
  table.querySelector('thead').innerHTML = tableHeadHtml();
  document.getElementById('metrics').innerHTML = `
    <div class="metric" title="Original source games in the selected corpus."><span>Total games</span><strong>${{fmtInt(tv.metrics.totalGames)}}</strong></div>
    <div class="metric" title="Source games with at least one qualifying FCE ending."><span>Matched games</span><strong>${{fmtInt(tv.metrics.matchedGames)}}</strong></div>
    <div class="metric" title="Qualifying game-ending incidences. Different endings in the same game can both count."><span>Ending incidences</span><strong>${{fmtInt(tv.metrics.matchedRows)}}</strong></div>
    <div class="metric" title="<=5-piece first-marker occurrence rows. FENs are deduplicated for Syzygy probing, but this displayed count is occurrence-weighted."><span>TB positions</span><strong>${{fmtInt(tv.metrics.tablebasePositions)}}</strong></div>`;
  const body = table.querySelector('tbody');
  body.innerHTML = sortedRows(tv).map(row => {{
    let html = rowHtml(row, tv.rows[row.stem]);
    if (row.stem === expandedStem) html += detailHtml(row);
    return html;
  }}).join('');
  bindSorting();
  bindRowExpansion();
}}
render();
</script>
</body>
</html>"##,
        html_escape(&title),
        html_escape(&title),
        comparison_note,
        data
    ))
}

fn display_title(title: &str) -> String {
    if let Some(rest) = title.strip_prefix("FCE endings in ") {
        format!("Fundamental Chess Endings in {rest}")
    } else {
        title.to_string()
    }
}

const FCE_REFERENCE_PERCENTAGES: &[(&str, f64)] = &[
    ("1-4BN", 0.02),
    ("2-0Pp", 2.87),
    ("2-1P", 0.23),
    ("3-1Np", 0.92),
    ("3-2NN", 1.56),
    ("4-1Bp", 1.01),
    ("4-2scBB", 1.65),
    ("4-3ocBB", 1.11),
    ("5-0BN", 3.29),
    ("6-1-0RP", 0.75),
    ("6-2-0Rr", 8.45),
    ("6-2-1RPr", 0.67),
    ("6-2-2RPPr", 0.56),
    ("6-3RRrr", 3.45),
    ("7-1RN", 0.97),
    ("7-2RB", 1.51),
    ("8-1RNr", 1.42),
    ("8-2RBr", 1.77),
    ("8-3RAra", 15.13),
    ("9-1Qp", 0.42),
    ("9-2Qq", 1.83),
    ("9-3QPq", 0.09),
    ("10-1Qa", 0.17),
    ("10-2Qr", 0.40),
    ("10-3Qaa", 0.08),
    ("10-4Qra", 0.69),
    ("10-5Qrr", 0.31),
    ("10-6Qaaa", 0.01),
    ("10-7QAq", 0.90),
    ("10-7-1Qbrr", 0.00006),
];

#[derive(Debug)]
struct ReferenceDeviation {
    label: String,
    gigabase_pct: f64,
    reference_pct: f64,
    delta: f64,
}

fn reference_note_html(snapshot: &Value) -> String {
    let deviations = reference_deviations(snapshot);
    let comparison = if deviations.is_empty() {
        "The public reference percentages are linked here for context; this snapshot does not embed a full copy of the original table.".to_string()
    } else {
        let top = deviations
            .iter()
            .take(5)
            .map(|d| {
                format!(
                    "{} ({:+.3} percentage points: {} here vs {} reference)",
                    html_escape(&d.label),
                    d.delta,
                    format_percent_note(d.gigabase_pct),
                    format_percent_note(d.reference_pct)
                )
            })
            .collect::<Vec<_>>()
            .join("; ");
        format!(
            "Using the default All corpus and minimum 1 half-move view, the largest absolute deviations from the public reference percentages are: {top}."
        )
    };
    r#"<section class="citation-note" aria-labelledby="citation-note-title">
    <h2 id="citation-note-title">Sources and Comparison Notes</h2>
    <p><strong>Citations.</strong> The categories are based on Karsten Muller and Frank Lamprecht's <a href="https://books.google.com/books?vid=ISBN1901983536" target="_blank" rel="noopener noreferrer"><cite>Fundamental Chess Endings</cite></a>, with the public comparison percentages taken from <a href="https://en.wikipedia.org/wiki/Chess_endgame#Frequency_table" target="_blank" rel="noopener noreferrer">Wikipedia's chess endgame frequency table</a>. The corpus is the <a href="https://lumbrasgigabase.com/en/download-in-pgn-format-en/" target="_blank" rel="noopener noreferrer">Lumbra's Gigabase PGN release</a>. Marker extraction uses <a href="https://cql64.com/faqs.html" target="_blank" rel="noopener noreferrer">CQLi</a> / <a href="https://www.gadycosteff.com/cql-6-1/" target="_blank" rel="noopener noreferrer">Chess Query Language</a>; WDL evaluation uses <a href="https://help.chessbase.com/CBase/14/Fra/tablebases_syzygy.htm" target="_blank" rel="noopener noreferrer">Syzygy tablebases</a>; board presentation follows the open-source <a href="https://lichess.org/source" target="_blank" rel="noopener noreferrer">Lichess/lila</a> visual style.</p>
    <p><strong>Largest differences.</strong> "#
        .to_string()
        + &comparison
        + r#"</p>
    <p><strong>Interpretive note.</strong> The most surprising outliers are the rook-plus-minor rows, especially Rook + Bishop vs Rook and Rook + Knight vs Rook, because they are several percentage points higher than the older reference. I would treat those as the first rows to audit if the goal is historical comparability: they are sensitive to corpus composition, pawn allowances, and the first-run threshold semantics used here.</p>
  </section>"#
}

fn reference_deviations(snapshot: &Value) -> Vec<ReferenceDeviation> {
    let Some(rows) = snapshot
        .pointer("/datasetViews/views/all/thresholdViews/1/rows")
        .and_then(Value::as_object)
    else {
        return Vec::new();
    };
    let mut deviations = Vec::new();
    for (stem, reference_pct) in FCE_REFERENCE_PERCENTAGES {
        let Some(gigabase_pct) = rows
            .get(*stem)
            .and_then(|row| row.get("percentage"))
            .and_then(Value::as_f64)
        else {
            continue;
        };
        deviations.push(ReferenceDeviation {
            label: snapshot_row_label(snapshot, stem),
            gigabase_pct,
            reference_pct: *reference_pct,
            delta: gigabase_pct - reference_pct,
        });
    }
    deviations.sort_by(|a, b| {
        b.delta
            .abs()
            .partial_cmp(&a.delta.abs())
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    deviations
}

fn snapshot_row_label(snapshot: &Value, stem: &str) -> String {
    let Some(rows) = snapshot.get("rows").and_then(Value::as_array) else {
        return stem.to_string();
    };
    for row in rows {
        if row.get("stem").and_then(Value::as_str) != Some(stem) {
            continue;
        }
        let row_id = row
            .get("rowId")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim();
        let label = row
            .get("label")
            .and_then(Value::as_str)
            .unwrap_or(stem)
            .trim();
        return if row_id.is_empty() {
            label.to_string()
        } else {
            format!("{row_id} {label}")
        };
    }
    stem.to_string()
}

fn format_percent_note(value: f64) -> String {
    let mut text = if value.abs() < 0.001 && value != 0.0 {
        format!("{value:.5}")
    } else {
        format!("{value:.3}")
    };
    while text.contains('.') && text.ends_with('0') {
        text.pop();
    }
    if text.ends_with('.') {
        text.pop();
    }
    text.push('%');
    text
}

fn safe_json_for_script(value: &str) -> String {
    value
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('\u{2028}', "\\u2028")
        .replace('\u{2029}', "\\u2029")
}

fn sample_chunk_key(view: &str, threshold: &str, stem: &str) -> String {
    format!("{view}|{threshold}|{stem}")
}

fn safe_path_part(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_') {
            out.push(ch);
        } else {
            out.push('_');
        }
    }
    if out.is_empty() {
        "_".to_string()
    } else {
        out
    }
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escapes_html() {
        assert_eq!(html_escape("<x>"), "&lt;x&gt;");
    }

    #[test]
    fn script_json_keeps_quotes_but_escapes_end_tags() {
        let raw = r#"{"title":"A </script> B"}"#;
        let safe = safe_json_for_script(raw);
        assert!(safe.contains("\"title\""));
        assert!(!safe.contains("&quot;"));
        assert!(!safe.contains("</script>"));
        serde_json::from_str::<serde_json::Value>(&safe).unwrap();
    }

    #[test]
    fn expands_fce_title() {
        assert_eq!(
            display_title("FCE endings in Lumbra's Gigabase"),
            "Fundamental Chess Endings in Lumbra's Gigabase"
        );
    }

    #[test]
    fn board_renderer_uses_inline_svg_white_pov_coordinates() {
        let html = render_html_value(&serde_json::json!({"title":"FCE endings"})).unwrap();
        assert!(html.contains(".board-link { position:relative; display:block;"));
        assert!(html.contains("<svg class=\"board-svg\" viewBox=\"0 0 8 8\""));
        assert!(html.contains("const pieceSvgs = {"));
        assert!(html.contains("if (/\\d/.test(token))"));
        assert!(!html.contains("if (/\\\\d/.test(token))"));
        assert!(
            html.contains("transform=\"translate(${fileIndex} ${rankIndex}) scale(${1 / 45})\"")
        );
        assert!(
            html.contains("data-square=\"${String.fromCharCode(97 + fileIndex)}${8 - rankIndex}\"")
        );
        assert!(!html.contains("turn-dot-svg"));
        assert!(!html.contains("cx=\"7.68\" cy=\"0.32\""));
        assert!(!html.contains("<image class=\"board-piece\""));
        assert!(!html.contains(".board-piece { position:absolute;"));
        assert!(!html.contains("grid-column:var(--file)"));
        assert!(!html.contains("grid-row:var(--rank)"));
    }

    #[test]
    fn rendered_html_uses_lazy_sample_chunks() {
        let html = render_html_value(&serde_json::json!({"title":"FCE endings"})).unwrap();
        assert!(html.contains("<script src=\"sampled_examples.js\"></script>"));
        assert!(html.contains("const sampleManifest = window.FCE_SAMPLED_EXAMPLES_MANIFEST"));
        assert!(html.contains("function requestSampleLoad(stem)"));
        assert!(html.contains("document.createElement('script')"));
        assert!(!html.contains("const sampledExamples = window.FCE_SAMPLED_EXAMPLES"));
    }

    #[test]
    fn rendered_matrix_columns_are_compact() {
        let html = render_html_value(&serde_json::json!({"title":"FCE endings"})).unwrap();
        assert!(html.contains("const columns = hasDecisive"));
        assert!(html.contains("? [['draw','Draw'], ['decisive','Decisive']]"));
        assert!(html.contains(": [['win','Win'], ['draw','Draw'], ['loss','Loss']]"));
        assert!(!html.contains("<th class=\"num\">Win</th><th class=\"num\">Draw</th><th class=\"num\">Loss</th><th class=\"num\">Decisive</th>"));
    }

    #[test]
    fn rendered_detail_hides_empty_tablebase_widgets() {
        let html = render_html_value(&serde_json::json!({"title":"FCE endings"})).unwrap();
        assert!(html.contains("const hasTablebase = Number(w?.totalPositions || 0) > 0;"));
        assert!(html.contains("if (!rows.length) return '';"));
        assert!(html.contains("hasTablebase ? statsPanel('Tablebase WDL'"));
        assert!(html.contains("${hasTablebase ? tbResultMatrix(w) : ''}"));
        assert!(!html.contains("No tablebase/result matrix is available"));
    }

    #[test]
    fn rendered_bars_use_compact_hover_tooltips() {
        let html = render_html_value(&serde_json::json!({"title":"FCE endings"})).unwrap();
        assert!(html.contains(".bar-shell::after"));
        assert!(html.contains("content:attr(data-tip)"));
        assert!(html.contains("const label = `W ${ap}% | D ${bp}% | L ${cp}%`;"));
        assert!(html.contains("const text = p => p >= 10 ? `${p}%` : '';"));
        assert!(html.contains("tabindex=\"0\" data-tip=\"${esc(label)}\""));
        assert!(!html.contains("W/D/L:"));
    }

    #[test]
    fn rendered_theme_icon_button_is_centered() {
        let html = render_html_value(&serde_json::json!({"title":"FCE endings"})).unwrap();
        assert!(html.contains(".theme-toggle { flex:0 0 auto; width:38px; height:38px; display:grid; place-items:center; padding:0;"));
        assert!(html.contains(".theme-icon { display:block; width:19px; height:19px;"));
    }

    #[test]
    fn rendered_page_has_citation_and_comparison_note() {
        let snapshot = serde_json::json!({
            "title": "FCE endings",
            "rows": [
                {"stem": "8-2RBr", "rowId": "8.2", "label": "Rook + Bishop vs Rook"},
                {"stem": "8-1RNr", "rowId": "8.1", "label": "Rook + Knight vs Rook"}
            ],
            "datasetViews": {
                "views": {
                    "all": {
                        "thresholdViews": {
                            "1": {
                                "rows": {
                                    "8-2RBr": {"percentage": 6.222891978948557},
                                    "8-1RNr": {"percentage": 4.433643249356359}
                                }
                            }
                        }
                    }
                }
            }
        });
        let html = render_html_value(&snapshot).unwrap();
        assert!(html.contains("Sources and Comparison Notes"));
        assert!(html.contains("https://books.google.com/books?vid=ISBN1901983536"));
        assert!(html.contains("https://en.wikipedia.org/wiki/Chess_endgame#Frequency_table"));
        assert!(html.contains("Largest differences"));
        assert!(html.contains("8.2 Rook + Bishop vs Rook"));
        assert!(html.contains("+4.453 percentage points"));
    }

    #[test]
    fn write_samples_js_splits_examples_into_chunks() {
        let base = std::env::temp_dir().join(format!("reti-site-samples-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();
        let input = base.join("sampled_examples.json");
        let output = base.join("sampled_examples.js");
        fs::write(
            &input,
            serde_json::json!({
                "schemaVersion": "test",
                "sampleSize": 60,
                "views": {
                    "all": {
                        "thresholds": {
                            "1": {
                                "stems": {
                                    "1-4BN": {
                                        "available": 1,
                                        "sampled": 1,
                                        "examples": [{"fen": "8/8/8/8/8/8/8/8 w - - 0 1"}]
                                    }
                                }
                            }
                        }
                    }
                }
            })
            .to_string(),
        )
        .unwrap();

        write_samples_js(&input, &output).unwrap();
        let manifest = fs::read_to_string(&output).unwrap();
        let chunk = fs::read_to_string(base.join("sampled_examples/all/1/1-4BN.js")).unwrap();
        assert!(manifest.contains("window.FCE_SAMPLED_EXAMPLES_MANIFEST="));
        assert!(manifest.contains("\"chunkMode\":\"view-threshold-stem-js\""));
        assert!(manifest.contains("\"src\":\"sampled_examples/all/1/1-4BN.js\""));
        assert!(!manifest.contains("\"examples\""));
        assert!(chunk.contains("window.FCE_SAMPLE_CHUNKS"));
        assert!(chunk.contains("\"all|1|1-4BN\""));
        assert!(chunk.contains("\"fen\":\"8/8/8/8/8/8/8/8 w - - 0 1\""));

        let _ = fs::remove_dir_all(&base);
    }
}
