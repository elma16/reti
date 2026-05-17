use serde_json::{json, Map, Value};
use std::fs;
use std::path::Path;

use crate::openings::OpeningCatalog;
use crate::source::{opening_bases, read_source_totals, total_games_for_opening};
use crate::{SiteError, SiteResult};

pub fn write_openings_js(
    opening_counts_json: &Path,
    source_totals_json: &Path,
    opening_catalog_csv: Option<&Path>,
    output_js: &Path,
) -> SiteResult<()> {
    let counts_text = fs::read_to_string(opening_counts_json).map_err(|e| {
        SiteError::new(format!(
            "failed to read {}: {e}",
            opening_counts_json.display()
        ))
    })?;
    let counts: Value = serde_json::from_str(&counts_text)?;
    let source_totals = read_source_totals(source_totals_json)?;
    let catalog = match opening_catalog_csv {
        Some(path) => OpeningCatalog::load_optional(path)?,
        None => OpeningCatalog::default(),
    };

    let thresholds = counts
        .get("thresholds")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_else(|| vec![Value::from(1), Value::from(2), Value::from(5)]);
    let threshold_keys = thresholds
        .iter()
        .filter_map(|value| value.as_u64().map(|n| n.to_string()))
        .collect::<Vec<_>>();

    let stem = output_js
        .file_stem()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("openings");
    let chunk_dir = output_js.with_file_name(stem);
    if chunk_dir.exists() {
        fs::remove_dir_all(&chunk_dir)?;
    }
    fs::create_dir_all(&chunk_dir)?;

    let mut options = Vec::new();
    let mut views = Map::new();
    for view in ["all", "otb", "online"] {
        views.insert(
            view.to_string(),
            json!({"key": view, "label": view_label(view)}),
        );
    }

    for eco_base in opening_bases(&source_totals) {
        if eco_base == "unknown" {
            continue;
        }
        let option = catalog.option_for_base(
            &eco_base,
            total_games_for_opening(&source_totals, "all", &eco_base),
        );
        let chunk_name = format!("{}.js", safe_path_part(&option.key));
        let chunk_src = format!("{stem}/{chunk_name}");
        let view_totals = json!({
            "all": total_games_for_opening(&source_totals, "all", &eco_base),
            "otb": total_games_for_opening(&source_totals, "otb", &eco_base),
            "online": total_games_for_opening(&source_totals, "online", &eco_base),
        });
        options.push(json!({
            "key": option.key,
            "ecoBase": option.eco_base,
            "ecoGroup": option.eco_group,
            "label": option.label,
            "aliases": option.aliases,
            "totalGames": option.total_games,
            "viewTotals": view_totals,
            "src": chunk_src,
        }));

        let mut chunk_views = Map::new();
        for view in ["all", "otb", "online"] {
            let total_games = total_games_for_opening(&source_totals, view, &eco_base);
            if total_games == 0 {
                continue;
            }
            let mut threshold_views = Map::new();
            for threshold in &threshold_keys {
                let raw = counts
                    .pointer(&format!(
                        "/views/{view}/thresholds/{threshold}/openings/{eco_base}"
                    ))
                    .cloned()
                    .unwrap_or_else(|| json!({"metrics":{"matchedRows":0},"rows":{}}));
                threshold_views.insert(threshold.clone(), decorate_threshold(raw, total_games));
            }
            let opening_payload = json!({
                "ecoBase": eco_base,
                "totalGames": total_games,
                "thresholds": threshold_views,
            });
            chunk_views.insert(view.to_string(), opening_payload);
        }
        let chunk_payload = json!({"views": chunk_views});
        let serialized_chunk = safe_json_for_script(&serde_json::to_string(&chunk_payload)?);
        let chunk_key = safe_json_for_script(&serde_json::to_string(&option.key)?);
        fs::write(
            chunk_dir.join(chunk_name),
            format!(
                "window.FCE_OPENING_CHUNKS=window.FCE_OPENING_CHUNKS||{{}};window.FCE_OPENING_CHUNKS[{chunk_key}]={serialized_chunk};\n"
            ),
        )?;
    }

    let payload = json!({
        "schemaVersion": 1,
        "kind": "fce-opening-ending-distribution",
        "exactness": "exact",
        "chunkMode": "eco-base-js",
        "semantics": "FCE ending incidence by ECO base code. Percentages use source-total ECO denominators; tablebase stats are intentionally omitted.",
        "thresholds": threshold_keys,
        "defaultOpening": options.first().and_then(|option| option.get("key")).cloned().unwrap_or(Value::String("".to_string())),
        "options": options,
        "views": views,
    });
    let serialized = safe_json_for_script(&serde_json::to_string(&payload)?);
    fs::write(output_js, format!("window.FCE_OPENINGS={serialized};\n"))?;
    Ok(())
}

fn decorate_threshold(raw: Value, total_games: u64) -> Value {
    let matched_rows = raw
        .pointer("/metrics/matchedRows")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let mut rows = Map::new();
    if let Some(raw_rows) = raw.get("rows").and_then(Value::as_object) {
        for (stem, row) in raw_rows {
            let quantity = row.get("quantity").and_then(Value::as_u64).unwrap_or(0);
            let actual = row.get("actualResult").cloned().unwrap_or_else(|| {
                json!({
                    "totalGames": quantity,
                    "sideWins": 0,
                    "sideDraws": 0,
                    "sideLosses": 0,
                    "symmetricDecisive": 0,
                    "unknownGames": quantity,
                })
            });
            rows.insert(
                stem.clone(),
                json!({
                    "quantity": quantity,
                    "percentage": pct(quantity, total_games),
                    "matchedShare": pct(quantity, matched_rows),
                    "actualResult": actual,
                }),
            );
        }
    }
    json!({
        "metrics": {
            "totalGames": total_games,
            "matchedRows": matched_rows,
        },
        "rows": rows,
    })
}

fn view_label(view: &str) -> &'static str {
    match view {
        "otb" => "OTB",
        "online" => "Online",
        _ => "All",
    }
}

fn pct(numerator: u64, denominator: u64) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64 * 100.0
    }
}

fn safe_json_for_script(value: &str) -> String {
    value
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('\u{2028}', "\\u2028")
        .replace('\u{2029}', "\\u2029")
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
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn decorate_threshold_computes_percentages() {
        let raw = json!({
            "metrics": {"matchedRows": 20},
            "rows": {
                "1-4BN": {
                    "quantity": 5,
                    "actualResult": {"totalGames": 5}
                }
            }
        });
        let decorated = decorate_threshold(raw, 100);
        assert_eq!(decorated["metrics"]["totalGames"], 100);
        assert_eq!(decorated["rows"]["1-4BN"]["percentage"], 5.0);
        assert_eq!(decorated["rows"]["1-4BN"]["matchedShare"], 25.0);
    }

    #[test]
    fn write_openings_js_emits_manifest_and_lazy_chunks() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!(
            "reti-site-openings-test-{}-{unique}",
            std::process::id()
        ));
        fs::create_dir_all(&dir).unwrap();

        let counts_path = dir.join("opening_counts.json");
        let totals_path = dir.join("source_totals.json");
        let output_js = dir.join("openings.js");
        fs::write(
            &counts_path,
            serde_json::to_string(&json!({
                "thresholds": [1],
                "views": {
                    "all": {"thresholds": {"1": {"openings": {
                        "A00": {
                            "metrics": {"matchedRows": 4},
                            "rows": {"1-4BN": {"quantity": 2, "actualResult": {"totalGames": 2, "sideWins": 1, "sideDraws": 1}}}
                        }
                    }}}},
                    "otb": {"thresholds": {"1": {"openings": {}}}},
                    "online": {"thresholds": {"1": {"openings": {}}}}
                }
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            &totals_path,
            serde_json::to_string(&json!({
                "totalGames": 5,
                "views": {"all": 5, "otb": 3, "online": 2},
                "openingTotals": {
                    "all": {"A00": 5},
                    "otb": {"A00": 3},
                    "online": {"A00": 2}
                },
                "files": []
            }))
            .unwrap(),
        )
        .unwrap();

        write_openings_js(&counts_path, &totals_path, None, &output_js).unwrap();

        let manifest = fs::read_to_string(&output_js).unwrap();
        assert!(manifest.contains("\"chunkMode\":\"eco-base-js\""));
        assert!(manifest.contains("\"src\":\"openings/eco_A00.js\""));
        let chunk = fs::read_to_string(dir.join("openings/eco_A00.js")).unwrap();
        assert!(chunk.contains("window.FCE_OPENING_CHUNKS"));
        assert!(chunk.contains("\"percentage\":40.0"));
        assert!(chunk.contains("\"matchedShare\":50.0"));

        fs::remove_dir_all(dir).unwrap();
    }
}
