use crate::aggregate::Snapshot;
use crate::{SiteError, SiteResult};
use serde_json::{Map, Value};
use std::fs;
use std::path::{Path, PathBuf};

const STATIC_FILES: &[&str] = &[
    "index.html",
    "sankey.html",
    "fce.css",
    "fce-app.js",
    "fce-sankey.js",
];

pub fn render_html(_snapshot: &Snapshot) -> SiteResult<String> {
    static_asset("index.html")
}

pub fn render_html_value(_snapshot: &Value) -> SiteResult<String> {
    static_asset("index.html")
}

pub fn write_site(snapshot: &Snapshot, output_html: &Path) -> SiteResult<()> {
    write_site_value(&serde_json::to_value(snapshot)?, output_html)
}

pub fn render_snapshot_file(snapshot_json: &Path, output_html: &Path) -> SiteResult<()> {
    let text = fs::read_to_string(snapshot_json)?;
    let snapshot: Value = serde_json::from_str(&text)?;
    write_site_value(&snapshot, output_html)
}

pub fn write_site_value(snapshot: &Value, output_html: &Path) -> SiteResult<()> {
    let output_dir = output_html
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."));
    fs::create_dir_all(&output_dir)?;

    for file_name in STATIC_FILES {
        let target = if *file_name == "index.html" {
            output_html.to_path_buf()
        } else {
            output_dir.join(file_name)
        };
        fs::write(target, static_asset(file_name)?)?;
    }
    write_snapshot_js(snapshot, &output_dir.join("snapshot.js"))?;
    Ok(())
}

pub fn write_snapshot_js(snapshot: &Value, output_js: &Path) -> SiteResult<()> {
    let payload = safe_json_for_script(&serde_json::to_string(snapshot)?);
    fs::write(output_js, format!("window.FCE_SNAPSHOT={payload};\n"))?;
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
            .unwrap_or(Value::from(32)),
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

fn static_asset(file_name: &str) -> SiteResult<String> {
    let path = static_asset_path(file_name);
    fs::read_to_string(&path)
        .map_err(|e| SiteError::new(format!("failed to read {}: {e}", path.display())))
}

fn static_asset_path(file_name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("static")
        .join(file_name)
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

#[cfg(test)]
mod tests {
    use super::*;

    fn asset(name: &str) -> String {
        static_asset(name).unwrap()
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
    fn static_index_imports_editable_assets_and_data_sidecars() {
        let html = render_html_value(&serde_json::json!({"title":"FCE endings"})).unwrap();
        assert!(html.contains("<link rel=\"stylesheet\" href=\"fce.css\">"));
        assert!(html.contains("<script src=\"snapshot.js\"></script>"));
        assert!(html.contains("<script src=\"sampled_examples.js\"></script>"));
        assert!(html.contains("<script src=\"fce-app.js\"></script>"));
        assert!(!html.contains("id=\"snapshot-data\""));
        assert!(!html.contains("<style>"));
        assert!(!html.contains("window.FCE_SNAPSHOT="));
    }

    #[test]
    fn write_site_emits_snapshot_js_and_static_assets() {
        let base = std::env::temp_dir().join(format!("reti-site-static-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();
        let output_html = base.join("custom.html");
        let snapshot = serde_json::json!({"title":"A </script> B", "datasetViews":{"default":"all","views":{}}});

        write_site_value(&snapshot, &output_html).unwrap();

        assert!(output_html.is_file());
        assert!(base.join("sankey.html").is_file());
        assert!(base.join("fce.css").is_file());
        assert!(base.join("fce-app.js").is_file());
        assert!(base.join("fce-sankey.js").is_file());
        assert!(!base.join("openings.html").exists());
        assert!(!base.join("fce-openings.js").exists());
        let snapshot_js = fs::read_to_string(base.join("snapshot.js")).unwrap();
        assert!(snapshot_js.starts_with("window.FCE_SNAPSHOT="));
        assert!(!snapshot_js.contains("</script>"));
        assert!(snapshot_js.contains("\\u003c/script\\u003e"));

        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn app_uses_global_snapshot_and_lazy_sample_chunks() {
        let app = asset("fce-app.js");
        assert!(app.contains("const snapshot = window.FCE_SNAPSHOT;"));
        assert!(app.contains("const sampleManifest = window.FCE_SAMPLED_EXAMPLES_MANIFEST"));
        assert!(app.contains("function requestSampleLoad(stem)"));
        assert!(app.contains("document.createElement('script')"));
        assert!(!app.contains("document.getElementById('snapshot-data')"));
        assert!(!app.contains("const sampledExamples = window.FCE_SAMPLED_EXAMPLES"));
    }

    #[test]
    fn app_renders_boards_with_inline_svg_white_pov_coordinates() {
        let app = asset("fce-app.js");
        assert!(app.contains("const pieceSvgs = {"));
        assert!(app.contains("if (/\\d/.test(token))"));
        assert!(!app.contains("if (/\\\\d/.test(token))"));
        assert!(app.contains("transform=\"translate(${fileIndex} ${rankIndex}) scale(${1 / 45})\""));
        assert!(
            app.contains("data-square=\"${String.fromCharCode(97 + fileIndex)}${8 - rankIndex}\"")
        );
        assert!(!app.contains("turn-dot-svg"));
        assert!(!app.contains("cx=\"7.68\" cy=\"0.32\""));
        assert!(!app.contains("<image class=\"board-piece\""));
        assert!(!app.contains(".board-piece { position:absolute;"));
    }

    #[test]
    fn app_keeps_tablebase_details_compact() {
        let app = asset("fce-app.js");
        assert!(app.contains("const hasTablebase = Number(w?.totalPositions || 0) > 0;"));
        assert!(app.contains("if (!rows.length) return '';"));
        assert!(app.contains("hasTablebase ? statsPanel('Tablebase WDL'"));
        assert!(app.contains("${hasTablebase ? tbResultMatrix(w) : ''}"));
        assert!(app.contains("const columns = hasDecisive"));
        assert!(app.contains("? [['draw','Draw'], ['decisive','Decisive']]"));
        assert!(app.contains(": [['win','Win'], ['draw','Draw'], ['loss','Loss']]"));
        assert!(app.contains("const symmetricStems = new Set("));
        assert!(app.contains("const isSymmetric = symmetricStems.has(row?.stem) || (decisive > 0 && sideWins === 0 && sideLosses === 0);"));
        assert!(app.contains("if (decisive > 0) rows.push(['Decisive', decisive]);"));
        assert!(app.contains("if (unknown > 0) rows.push(['Unknown', unknown]);"));
        assert!(!app.contains("No tablebase/result matrix is available"));
    }

    #[test]
    fn app_bars_use_compact_hover_tooltips() {
        let css = asset("fce.css");
        let app = asset("fce-app.js");
        assert!(css.contains(".bar-shell::after"));
        assert!(css.contains("content:attr(data-tip)"));
        assert!(app.contains("const label = `W ${ap}% | D ${bp}% | L ${cp}%`;"));
        assert!(app.contains("const text = p => p >= 10 ? `${p}%` : '';"));
        assert!(app.contains("tabindex=\"0\" data-tip=\"${esc(label)}\""));
        assert!(!app.contains("W/D/L:"));
    }

    #[test]
    fn static_table_page_keeps_opening_page_unpublished_and_pluralizes_board_note() {
        let html = asset("index.html");
        let app = asset("fce-app.js");
        assert!(!html.contains("id=\"opening-filter\""));
        assert!(!app.contains("activeOpening"));
        assert!(!html.contains("openings.html"));
        assert!(html.contains("not part of this published dashboard"));
        assert!(app.contains("Matched share %"));
        assert!(!html.contains("Total Corpus %"));
        assert!(!app.contains("Matched share total"));
        assert!(app.contains(
            "const boardWord = Number(payload.sampled || 0) === 1 ? 'board' : 'boards';"
        ));
        assert!(html.contains("At most 32 games are sampled for each selected corpus, threshold, and ending; if fewer qualify, all available games are shown."));
        assert!(!app.contains("board(s)"));
    }

    #[test]
    fn sankey_keeps_labels_inside_and_uses_percentage_tooltips() {
        let html = asset("sankey.html");
        let css = asset("fce.css");
        let app = asset("fce-sankey.js");
        assert!(app.contains("const width = 1480;"));
        assert!(app.contains("const labelGutter = 390;"));
        assert!(app.contains("pctText(Number(link.count || 0), totalTransitions)"));
        assert!(app.contains("text.textContent = `${idFor(node.stem) ? `${idFor(node.stem)} ` : ''}${labelFor(node.stem)}`;"));
        assert!(!app.contains("(${fmtInt(node.value)})"));
        assert!(!html.contains("Transition Counts"));
        assert!(!html.contains("Share of all transitions"));
        assert!(html.contains("Exact counts and percentages are shown in link hover text"));
        assert!(css.contains(".sankey-svg { display:block; min-width:1180px;"));
    }

    #[test]
    fn static_theme_icon_button_is_centered() {
        let css = asset("fce.css");
        assert!(css.contains(".theme-toggle { flex:0 0 auto; width:34px; height:34px; display:grid; place-items:center; padding:0;"));
        assert!(css.contains(".theme-icon { display:block; width:17px; height:17px;"));
    }

    #[test]
    fn static_page_has_article_intro_and_numbered_references() {
        let html = asset("index.html");
        assert!(html.contains(
            "Reproducing the <cite>Fundamental Chess Endings</cite> Statistics Table using FOSS"
        ));
        assert!(html.contains("Date: 2026-05-16 | Author: Elliott Macneil"));
        assert!(!html.contains("Fundamental Chess Endings snapshot"));
        assert!(html.contains("Methodology and Scope"));
        assert!(html.contains("current build does not run Stockfish evaluations"));
        assert!(html.contains("<section class=\"references-section\""));
        assert!(html.contains("<h2 id=\"references-title\">References</h2>"));
        assert!(html.find("<div class=\"table-wrap\">") < html.find("<section class=\"references-section\""));
        assert!(html.contains("id=\"ref-fce\""));
        assert!(html.contains("id=\"ref-reti\""));
        assert!(
            html.contains("https://books.google.co.uk/books/about/Fundamental_Chess_Endings.html")
        );
        assert!(html.contains("https://en.wikipedia.org/wiki/Chess_endgame#Frequency_table"));
        assert!(!html.contains("Sources and Comparison Notes"));
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
                "sampleSize": 32,
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
