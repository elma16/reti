use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use crate::catalog;
use crate::sqlite::{Db, SQLITE_ROW};
use crate::{SiteError, SiteResult};

#[derive(Debug, Clone, Serialize)]
pub struct SankeyData {
    #[serde(rename = "schemaVersion")]
    pub schema_version: u32,
    pub semantics: SankeySemantics,
    pub controls: SankeyControls,
    pub nodes: Vec<SankeyNode>,
    pub views: BTreeMap<String, SankeyView>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SankeySemantics {
    #[serde(rename = "edgeMeaning")]
    pub edge_meaning: &'static str,
    #[serde(rename = "stageMeaning")]
    pub stage_meaning: &'static str,
    #[serde(rename = "samePlyHandling")]
    pub same_ply_handling: &'static str,
    #[serde(rename = "auxiliaryHandling")]
    pub auxiliary_handling: &'static str,
}

#[derive(Debug, Clone, Serialize)]
pub struct SankeyControls {
    pub views: Vec<SankeyControlOption>,
    pub thresholds: Vec<String>,
    #[serde(rename = "defaultView")]
    pub default_view: &'static str,
    #[serde(rename = "defaultThreshold")]
    pub default_threshold: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SankeyControlOption {
    pub key: String,
    pub label: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SankeyNode {
    pub stem: String,
    #[serde(rename = "rowId")]
    pub row_id: String,
    pub label: String,
    #[serde(rename = "shortLabel")]
    pub short_label: String,
    pub chapter: String,
    pub color: String,
    #[serde(rename = "sortIndex")]
    pub sort_index: f64,
    #[serde(rename = "isAux")]
    pub is_aux: bool,
    #[serde(rename = "parentStem", skip_serializing_if = "Option::is_none")]
    pub parent_stem: Option<String>,
    #[serde(rename = "parentLabel", skip_serializing_if = "Option::is_none")]
    pub parent_label: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SankeyView {
    pub key: String,
    pub label: String,
    pub thresholds: BTreeMap<String, SankeyThreshold>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct SankeyThreshold {
    pub metrics: SankeyMetrics,
    pub links: Vec<SankeyLink>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct SankeyMetrics {
    #[serde(rename = "gameEndingIncidences")]
    pub game_ending_incidences: u64,
    #[serde(rename = "gamesWithTransitions")]
    pub games_with_transitions: u64,
    #[serde(rename = "distinctTransitions")]
    pub distinct_transitions: u64,
    #[serde(rename = "transitionIncidences")]
    pub transition_incidences: u64,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct SankeyLink {
    pub source: String,
    pub target: String,
    pub count: u64,
}

#[derive(Debug, Clone)]
struct StemRun {
    stem: String,
    max_run_length: u32,
    ply: i64,
}

#[derive(Debug, Clone)]
struct Stage {
    ply: i64,
    stems: Vec<String>,
}

#[derive(Debug, Clone, Default)]
struct GameStages {
    source_pgn: String,
    game_key: String,
    source_group: String,
    runs: Vec<StemRun>,
}

#[derive(Debug, Clone, Default)]
struct ThresholdAccumulator {
    metrics: SankeyMetrics,
    links: BTreeMap<(String, String), u64>,
}

pub fn write_sankey_js(db: &Db, output_js: &Path, thresholds: &[u32]) -> SiteResult<()> {
    ensure_sankey_index(db)?;
    let data = build_sankey_data(db, thresholds)?;
    let payload = safe_json_for_script(&serde_json::to_string(&data)?);
    fs::write(output_js, format!("window.FCE_SANKEY={payload};\n"))?;
    Ok(())
}

pub fn build_sankey_data(db: &Db, thresholds: &[u32]) -> SiteResult<SankeyData> {
    let nodes = sankey_nodes();
    let known_stems = nodes
        .iter()
        .map(|node| node.stem.clone())
        .collect::<BTreeSet<_>>();
    let mut accumulators = scan_sankey_accumulators(db, thresholds, &known_stems)?;
    let mut views = BTreeMap::new();
    for (key, label) in [("all", "All"), ("otb", "OTB"), ("online", "Online")] {
        let mut threshold_views = BTreeMap::new();
        for threshold in thresholds {
            let accumulator = accumulators
                .remove(&(key.to_string(), *threshold))
                .unwrap_or_default();
            threshold_views.insert(
                threshold.to_string(),
                threshold_from_accumulator(accumulator),
            );
        }
        views.insert(
            key.to_string(),
            SankeyView {
                key: key.to_string(),
                label: label.to_string(),
                thresholds: threshold_views,
            },
        );
    }

    Ok(SankeyData {
        schema_version: 1,
        semantics: SankeySemantics {
            edge_meaning: "A link counts a game-level consecutive transition from one FCE ending stem to the next distinct first-marker stage in the same game.",
            stage_meaning: "Each game/stem contributes at most once, positioned by the first marker ply for that stem after applying the half-move threshold.",
            same_ply_handling: "Different stems first seen on the same ply are treated as one co-present stage; no artificial ordering is created within that ply.",
            auxiliary_handling: "Auxiliary pawnless/connected-pawn rows are separate nodes, matching the table.",
        },
        controls: SankeyControls {
            views: vec![
                SankeyControlOption {
                    key: "all".to_string(),
                    label: "All".to_string(),
                },
                SankeyControlOption {
                    key: "otb".to_string(),
                    label: "OTB".to_string(),
                },
                SankeyControlOption {
                    key: "online".to_string(),
                    label: "Online".to_string(),
                },
            ],
            thresholds: thresholds.iter().map(u32::to_string).collect(),
            default_view: "all",
            default_threshold: thresholds
                .first()
                .copied()
                .unwrap_or(1)
                .to_string(),
        },
        nodes,
        views,
    })
}

fn ensure_sankey_index(db: &Db) -> SiteResult<()> {
    eprintln!("[reti-site] Ensuring Sankey covering index");
    db.exec(
        "
        CREATE INDEX IF NOT EXISTS idx_game_stems_sankey
            ON game_stems(source_group, source_pgn, game_key, ply_index, stem, max_run_length);
        ",
    )?;
    eprintln!("[reti-site] Sankey covering index is ready");
    Ok(())
}

fn scan_sankey_accumulators(
    db: &Db,
    thresholds: &[u32],
    known_stems: &BTreeSet<String>,
) -> SiteResult<BTreeMap<(String, u32), ThresholdAccumulator>> {
    let sql = "
        SELECT source_pgn, game_key, source_group, stem, max_run_length, ply_index
        FROM game_stems
        ORDER BY source_group, source_pgn, game_key
        ";
    let mut accumulators = BTreeMap::new();
    for view in ["all", "otb", "online"] {
        for threshold in thresholds {
            accumulators.insert(
                (view.to_string(), *threshold),
                ThresholdAccumulator::default(),
            );
        }
    }

    let mut stmt = db.prepare(&sql)?;
    let mut current = GameStages::default();
    let mut has_current = false;
    let mut rows_seen = 0u64;
    let mut games_seen = 0u64;

    while stmt.step()? == SQLITE_ROW {
        rows_seen += 1;
        if rows_seen % 1_000_000 == 0 {
            eprintln!(
                "[reti-site] Sankey scan: {} game-ending rows, {} games",
                rows_seen, games_seen
            );
        }
        let source_pgn = stmt.column_text(0);
        let game_key = stmt.column_text(1);
        let source_group = stmt.column_text(2);
        let stem = stmt.column_text(3);
        let max_run_length = stmt.column_i64(4).max(0) as u32;
        let ply = stmt.column_i64(5);
        if !known_stems.contains(&stem) {
            continue;
        }
        if has_current
            && (current.source_group != source_group
                || current.source_pgn != source_pgn
                || current.game_key != game_key)
        {
            games_seen += 1;
            process_game_runs(&current, thresholds, &mut accumulators);
            current = GameStages::default();
            has_current = false;
        }
        if !has_current {
            current.source_pgn = source_pgn;
            current.game_key = game_key;
            current.source_group = source_group;
            has_current = true;
        }
        current.runs.push(StemRun {
            stem,
            max_run_length,
            ply,
        });
    }
    if has_current {
        games_seen += 1;
        process_game_runs(&current, thresholds, &mut accumulators);
    }
    if rows_seen >= 1_000_000 {
        eprintln!(
            "[reti-site] Sankey scan complete: {} game-ending rows, {} games",
            rows_seen, games_seen
        );
    }

    Ok(accumulators)
}

fn threshold_from_accumulator(accumulator: ThresholdAccumulator) -> SankeyThreshold {
    let mut out_links = accumulator
        .links
        .into_iter()
        .map(|((source, target), count)| SankeyLink {
            source,
            target,
            count,
        })
        .collect::<Vec<_>>();
    out_links.sort_by(|a, b| {
        b.count
            .cmp(&a.count)
            .then(a.source.cmp(&b.source))
            .then(a.target.cmp(&b.target))
    });
    let mut metrics = accumulator.metrics;
    metrics.distinct_transitions = out_links.len() as u64;
    metrics.transition_incidences = out_links.iter().map(|link| link.count).sum();

    SankeyThreshold {
        metrics,
        links: out_links,
    }
}

fn process_game_runs(
    game: &GameStages,
    thresholds: &[u32],
    accumulators: &mut BTreeMap<(String, u32), ThresholdAccumulator>,
) {
    let views = ["all", game.source_group.as_str()];
    let mut runs = game.runs.clone();
    runs.sort_by(|a, b| a.ply.cmp(&b.ply).then(a.stem.cmp(&b.stem)));
    for threshold in thresholds {
        let mut stages = Vec::new();
        let mut incidence_count = 0u64;
        for run in &runs {
            if run.max_run_length < *threshold {
                continue;
            }
            incidence_count += 1;
            push_stage_stem(&mut stages, run.ply, run.stem.clone());
        }
        if incidence_count == 0 {
            continue;
        }
        for view in views {
            if let Some(accumulator) = accumulators.get_mut(&(view.to_string(), *threshold)) {
                accumulator.metrics.game_ending_incidences += incidence_count;
                process_game(&stages, &mut accumulator.links, &mut accumulator.metrics);
            }
        }
    }
}

fn push_stage_stem(stages: &mut Vec<Stage>, ply: i64, stem: String) {
    if let Some(stage) = stages.last_mut() {
        if stage.ply == ply {
            if !stage.stems.iter().any(|existing| existing == &stem) {
                stage.stems.push(stem);
            }
            return;
        }
    }
    stages.push(Stage {
        ply,
        stems: vec![stem],
    });
}

fn process_game(
    stages: &[Stage],
    links: &mut BTreeMap<(String, String), u64>,
    metrics: &mut SankeyMetrics,
) {
    if stages.len() < 2 {
        return;
    }
    metrics.games_with_transitions += 1;
    for pair in stages.windows(2) {
        let source_stage = &pair[0];
        let target_stage = &pair[1];
        for source in &source_stage.stems {
            for target in &target_stage.stems {
                if source == target {
                    continue;
                }
                *links.entry((source.clone(), target.clone())).or_default() += 1;
            }
        }
    }
}

fn sankey_nodes() -> Vec<SankeyNode> {
    let mut nodes = Vec::new();
    for (idx, ending) in catalog::ENDINGS.iter().enumerate() {
        nodes.push(SankeyNode {
            stem: ending.stem.to_string(),
            row_id: ending.row_id.to_string(),
            label: ending.label.to_string(),
            short_label: ending.label.to_string(),
            chapter: ending.chapter_label.to_string(),
            color: ending.color.to_string(),
            sort_index: idx as f64,
            is_aux: false,
            parent_stem: None,
            parent_label: None,
        });
        let mut offset = 0usize;
        for (stem, parent, label) in catalog::AUXILIARY {
            if *parent != ending.stem {
                continue;
            }
            nodes.push(SankeyNode {
                stem: (*stem).to_string(),
                row_id: auxiliary_row_id(ending.row_id, ending.stem, offset),
                label: auxiliary_full_label(ending.label, label),
                short_label: (*label).to_string(),
                chapter: ending.chapter_label.to_string(),
                color: ending.color.to_string(),
                sort_index: idx as f64 + (offset as f64 + 1.0) / 10.0,
                is_aux: true,
                parent_stem: Some(ending.stem.to_string()),
                parent_label: Some(ending.label.to_string()),
            });
            offset += 1;
        }
    }
    nodes
}

fn auxiliary_full_label(parent: &str, child: &str) -> String {
    if child.eq_ignore_ascii_case("without pawns") {
        format!("{parent} without pawns")
    } else if child.eq_ignore_ascii_case("connected pawns") {
        format!("{parent} with connected pawns")
    } else {
        format!("{parent}: {child}")
    }
}

fn auxiliary_row_id(parent_row_id: &str, parent_stem: &str, offset: usize) -> String {
    let letter = char::from(b'a' + offset as u8);
    if !parent_row_id.is_empty() {
        format!("{parent_row_id}{letter}")
    } else if parent_stem == "10-7-1Qbrr" {
        format!("10.7{letter}")
    } else {
        letter.to_string()
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

pub fn write_sankey_js_from_path(
    sqlite_db: &Path,
    output_js: &Path,
    thresholds: &[u32],
) -> SiteResult<()> {
    if thresholds.is_empty() {
        return Err(SiteError::new("--thresholds must not be empty"));
    }
    let db = Db::open(sqlite_db, false)?;
    write_sankey_js(&db, output_js, thresholds)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_db(name: &str) -> (std::path::PathBuf, Db) {
        let path = std::env::temp_dir().join(format!("{name}-{}.sqlite3", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let db = Db::open(&path, true).unwrap();
        db.exec(
            "
            CREATE TABLE game_stems (
                source_pgn TEXT NOT NULL,
                source_group TEXT NOT NULL,
                game_key TEXT NOT NULL,
                stem TEXT NOT NULL,
                max_run_length INTEGER NOT NULL,
                ply_index INTEGER NOT NULL
            );
            ",
        )
        .unwrap();
        (path, db)
    }

    fn insert(db: &Db, source: &str, group: &str, game: &str, stem: &str, run: u32, ply: u32) {
        db.exec(&format!(
            "INSERT INTO game_stems VALUES ('{}','{}','{}','{}',{},{})",
            source, group, game, stem, run, ply
        ))
        .unwrap();
    }

    #[test]
    fn consecutive_links_ignore_same_ply_ordering() {
        let (_path, db) = temp_db("reti-sankey-links");
        insert(&db, "otb.pgn", "otb", "g1", "2-0Pp", 2, 10);
        insert(&db, "otb.pgn", "otb", "g1", "6-2-0Rr", 2, 12);
        insert(&db, "otb.pgn", "otb", "g1", "6-2-1RPr", 2, 12);
        insert(&db, "otb.pgn", "otb", "g1", "7-1RN", 2, 20);

        let data = build_sankey_data(&db, &[1]).unwrap();
        let links = &data.views["all"].thresholds["1"].links;
        assert!(links
            .iter()
            .any(|link| link.source == "2-0Pp" && link.target == "6-2-0Rr"));
        assert!(links
            .iter()
            .any(|link| link.source == "2-0Pp" && link.target == "6-2-1RPr"));
        assert!(!links
            .iter()
            .any(|link| link.source == "6-2-0Rr" && link.target == "6-2-1RPr"));
        assert!(links
            .iter()
            .any(|link| link.source == "6-2-0Rr" && link.target == "7-1RN"));
        assert!(links
            .iter()
            .any(|link| link.source == "6-2-1RPr" && link.target == "7-1RN"));
    }

    #[test]
    fn view_and_threshold_filters_are_applied() {
        let (_path, db) = temp_db("reti-sankey-filters");
        insert(&db, "otb.pgn", "otb", "g1", "2-0Pp", 1, 10);
        insert(&db, "otb.pgn", "otb", "g1", "6-2-0Rr", 1, 12);
        insert(&db, "online.pgn", "online", "g2", "3-2NN", 5, 3);
        insert(&db, "online.pgn", "online", "g2", "5-0BN", 5, 9);

        let data = build_sankey_data(&db, &[1, 5]).unwrap();
        assert_eq!(
            data.views["all"].thresholds["1"]
                .metrics
                .games_with_transitions,
            2
        );
        assert_eq!(
            data.views["otb"].thresholds["1"]
                .metrics
                .games_with_transitions,
            1
        );
        assert_eq!(
            data.views["otb"].thresholds["5"]
                .metrics
                .games_with_transitions,
            0
        );
        assert_eq!(
            data.views["online"].thresholds["5"]
                .metrics
                .games_with_transitions,
            1
        );
    }
}
