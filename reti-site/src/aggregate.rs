use serde::Serialize;
use std::collections::BTreeMap;

use crate::catalog;
use crate::openings::{OpeningCatalog, OpeningOption};
use crate::source::{
    opening_bases, source_bucket_label, source_games, total_games_for_opening,
    total_games_for_view, SourceTotals,
};
use crate::sqlite::{Db, SQLITE_ROW};
use crate::{SiteError, SiteResult};

#[derive(Debug, Clone, Serialize)]
pub struct Snapshot {
    #[serde(rename = "schemaVersion")]
    pub schema_version: u32,
    #[serde(rename = "snapshotId")]
    pub snapshot_id: String,
    #[serde(rename = "generatedAt")]
    pub generated_at: String,
    pub title: String,
    pub corpus: serde_json::Value,
    pub methodology: serde_json::Value,
    pub catalog: serde_json::Value,
    pub totals: Totals,
    #[serde(rename = "sourceBuckets")]
    pub source_buckets: Vec<SourceBucket>,
    #[serde(rename = "datasetViews")]
    pub dataset_views: DatasetViews,
    #[serde(rename = "openingFilters", skip_serializing_if = "Option::is_none")]
    pub opening_filters: Option<OpeningFilters>,
    pub rows: Vec<DisplayRow>,
    #[serde(rename = "tablebaseMode")]
    pub tablebase_mode: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Totals {
    #[serde(rename = "sourceBuckets")]
    pub source_buckets: usize,
    #[serde(rename = "endingRows")]
    pub ending_rows: usize,
    #[serde(rename = "matchedGames")]
    pub matched_games: u64,
    #[serde(rename = "matchedRows")]
    pub matched_rows: u64,
    pub exactness: &'static str,
}

#[derive(Debug, Clone, Serialize)]
pub struct SourceBucket {
    #[serde(rename = "sourcePgn")]
    pub source_pgn: String,
    #[serde(rename = "sourceGroup")]
    pub source_group: String,
    #[serde(rename = "displayLabel")]
    pub display_label: String,
    #[serde(rename = "originalGameCount")]
    pub original_game_count: u64,
    #[serde(rename = "matchedGames")]
    pub matched_games: u64,
    #[serde(rename = "matchTotal")]
    pub match_total: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct DatasetViews {
    pub default: &'static str,
    pub views: BTreeMap<String, View>,
}

#[derive(Debug, Clone, Serialize)]
pub struct View {
    pub key: String,
    pub label: String,
    #[serde(rename = "totalGames")]
    pub total_games: u64,
    #[serde(rename = "thresholdViews")]
    pub threshold_views: BTreeMap<String, ThresholdView>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ThresholdView {
    pub metrics: ViewMetrics,
    pub rows: BTreeMap<String, RowStats>,
    #[serde(rename = "sourceBuckets")]
    pub source_buckets: BTreeMap<String, SourceThresholdStats>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OpeningFilters {
    pub default: &'static str,
    pub exactness: &'static str,
    pub semantics: &'static str,
    pub options: Vec<OpeningOption>,
    pub views: BTreeMap<String, OpeningDatasetViews>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OpeningDatasetViews {
    pub views: BTreeMap<String, View>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ViewMetrics {
    #[serde(rename = "totalGames")]
    pub total_games: u64,
    #[serde(rename = "matchedGames")]
    pub matched_games: u64,
    #[serde(rename = "matchedRows")]
    pub matched_rows: u64,
    #[serde(rename = "tablebasePositions")]
    pub tablebase_positions: u64,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct RowStats {
    pub quantity: u64,
    pub percentage: f64,
    #[serde(rename = "matchedShare")]
    pub matched_share: f64,
    #[serde(rename = "actualResult")]
    pub actual_result: ActualStats,
    #[serde(rename = "tablebaseWdl")]
    pub tablebase_wdl: WdlStats,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct SourceThresholdStats {
    #[serde(rename = "matchedGames")]
    pub matched_games: u64,
    #[serde(rename = "matchTotal")]
    pub match_total: u64,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct WdlStats {
    #[serde(rename = "totalPositions")]
    pub total_positions: u64,
    #[serde(rename = "sideWins")]
    pub side_wins: u64,
    #[serde(rename = "sideDraws")]
    pub side_draws: u64,
    #[serde(rename = "sideLosses")]
    pub side_losses: u64,
    #[serde(rename = "symmetricDecisive")]
    pub symmetric_decisive: u64,
    #[serde(rename = "actualSideWins")]
    pub actual_side_wins: u64,
    #[serde(rename = "actualSideDraws")]
    pub actual_side_draws: u64,
    #[serde(rename = "actualSideLosses")]
    pub actual_side_losses: u64,
    #[serde(rename = "actualSymmetricDecisive")]
    pub actual_symmetric_decisive: u64,
    #[serde(rename = "unknownPositions")]
    pub unknown_positions: u64,
    #[serde(rename = "resultCrosstab")]
    pub result_crosstab: ResultCrosstab,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ActualStats {
    #[serde(rename = "totalGames")]
    pub total_games: u64,
    #[serde(rename = "sideWins")]
    pub side_wins: u64,
    #[serde(rename = "sideDraws")]
    pub side_draws: u64,
    #[serde(rename = "sideLosses")]
    pub side_losses: u64,
    #[serde(rename = "symmetricDecisive")]
    pub symmetric_decisive: u64,
    #[serde(rename = "unknownGames")]
    pub unknown_games: u64,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ResultCrosstab {
    pub rows: Vec<ResultCrosstabRow>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ResultCrosstabRow {
    #[serde(rename = "tbOutcome")]
    pub tb_outcome: String,
    pub win: u64,
    pub draw: u64,
    pub loss: u64,
    pub decisive: u64,
    pub unknown: u64,
    pub total: u64,
}

#[derive(Debug, Clone, Default)]
struct OutcomeCounts {
    win: u64,
    draw: u64,
    loss: u64,
    decisive: u64,
    unknown: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct DisplayRow {
    pub stem: String,
    #[serde(rename = "rowId")]
    pub row_id: String,
    pub label: String,
    pub chapter: String,
    pub color: String,
    #[serde(rename = "sortIndex")]
    pub sort_index: f64,
    #[serde(rename = "auxiliaryRows", skip_serializing_if = "Vec::is_empty")]
    pub auxiliary_rows: Vec<DisplayRow>,
}

pub fn ensure_indexes(db: &Db) -> SiteResult<()> {
    db.exec(
        "
        CREATE INDEX IF NOT EXISTS idx_game_stems_view_threshold
            ON game_stems(source_group, max_run_length, stem);
        CREATE INDEX IF NOT EXISTS idx_game_stems_opening_threshold
            ON game_stems(eco_base, source_group, max_run_length, stem);
        CREATE INDEX IF NOT EXISTS idx_game_stems_game
            ON game_stems(source_group, source_pgn, game_key);
        CREATE INDEX IF NOT EXISTS idx_game_stems_sankey
            ON game_stems(source_group, source_pgn, game_key, ply_index, stem, max_run_length);
        CREATE INDEX IF NOT EXISTS idx_positions_view_threshold
            ON positions(source_group, run_length, stem);
        CREATE INDEX IF NOT EXISTS idx_positions_opening_threshold
            ON positions(eco_base, source_group, run_length, stem);
        CREATE INDEX IF NOT EXISTS idx_positions_eval_key
            ON positions(eval_key);
        CREATE INDEX IF NOT EXISTS idx_evaluations_status
            ON evaluations(eval_status);
        ",
    )
}

pub fn build_snapshot(
    db: &Db,
    title: &str,
    snapshot_id: String,
    generated_at: String,
    source_totals: &SourceTotals,
    opening_catalog: &OpeningCatalog,
    thresholds: &[u32],
) -> SiteResult<Snapshot> {
    let mut views = BTreeMap::new();
    for (key, label) in [("all", "All"), ("otb", "OTB"), ("online", "Online")] {
        views.insert(
            key.to_string(),
            View {
                key: key.to_string(),
                label: label.to_string(),
                total_games: total_games_for_view(source_totals, key),
                threshold_views: build_threshold_views(db, source_totals, key, None, thresholds)?,
            },
        );
    }
    let all_t1 = views
        .get("all")
        .and_then(|view| view.threshold_views.get("1"))
        .ok_or_else(|| SiteError::new("missing all/1 threshold view"))?;
    let source_buckets = source_buckets(db, source_totals)?;
    Ok(Snapshot {
        schema_version: 2,
        snapshot_id,
        generated_at,
        title: title.to_string(),
        corpus: serde_json::json!({
            "name": "Lumbra/Lumbras Gigabase",
            "totalGames": total_games_for_view(source_totals, "all"),
            "sourceGroups": ["otb", "online"],
            "exactness": "exact"
        }),
        methodology: serde_json::json!({
            "countingSemantics": "first run per game and FCE ending stem",
            "tablebasePositionFiltering": "first <=5-piece marker position per game and FCE stem",
            "thresholdSemantics": "the active threshold filters by first-run half-move length",
            "actualResultSemantics": "final PGN result from the material-side perspective for every qualifying game-ending incidence",
            "symmetricSemantics": "symmetric endings have no named material side; decisive results are counted separately from draws",
            "tablebaseResultCrosstab": "Syzygy WDL crossed with final PGN result for tablebase-eligible first markers only",
            "evaluation": "Syzygy WDL in Rust; no Stockfish",
            "combinedComments": true,
            "runLengthThresholds": true
        }),
        catalog: serde_json::json!({
            "name": "fce",
            "chapters": catalog::CHAPTERS,
            "rows": catalog::ENDINGS
        }),
        totals: Totals {
            source_buckets: source_totals.files.len(),
            ending_rows: catalog::ENDINGS.len(),
            matched_games: all_t1.metrics.matched_games,
            matched_rows: all_t1.metrics.matched_rows,
            exactness: "exact",
        },
        source_buckets,
        dataset_views: DatasetViews {
            default: "all",
            views,
        },
        opening_filters: build_opening_filters(db, source_totals, opening_catalog, thresholds)?,
        rows: display_rows(),
        tablebase_mode: "combined-first-marker-rust-v2".to_string(),
    })
}

fn build_threshold_views(
    db: &Db,
    source_totals: &SourceTotals,
    view: &str,
    eco_base: Option<&str>,
    thresholds: &[u32],
) -> SiteResult<BTreeMap<String, ThresholdView>> {
    let total_games = eco_base
        .map(|eco| total_games_for_opening(source_totals, view, eco))
        .unwrap_or_else(|| total_games_for_view(source_totals, view));
    let mut out = BTreeMap::new();
    for threshold in thresholds {
        let where_clause = threshold_where(*threshold, view, eco_base, "");
        let matched_rows = scalar_count(
            db,
            &format!("SELECT COUNT(*) FROM game_stems WHERE {where_clause}"),
        )?;
        let matched_games = scalar_count(
            db,
            &format!(
                "SELECT COUNT(*) FROM (SELECT source_pgn, game_key FROM game_stems WHERE {where_clause} GROUP BY source_pgn, game_key)"
            ),
        )?;
        let mut rows = incidence_rows(db, view, eco_base, *threshold, total_games, matched_rows)?;
        let actual = actual_result_rows(db, view, eco_base, *threshold)?;
        for (stem, stats) in actual {
            rows.entry(stem).or_default().actual_result = stats;
        }
        let wdl = wdl_rows(db, view, eco_base, *threshold)?;
        for (stem, stats) in wdl {
            rows.entry(stem).or_default().tablebase_wdl = stats;
        }
        let tablebase_positions = rows
            .values()
            .map(|row| row.tablebase_wdl.total_positions)
            .sum();
        out.insert(
            threshold.to_string(),
            ThresholdView {
                metrics: ViewMetrics {
                    total_games,
                    matched_games,
                    matched_rows,
                    tablebase_positions,
                },
                rows,
                source_buckets: if eco_base.is_none() {
                    source_thresholds(db, view, *threshold)?
                } else {
                    BTreeMap::new()
                },
            },
        );
    }
    Ok(out)
}

fn incidence_rows(
    db: &Db,
    view: &str,
    eco_base: Option<&str>,
    threshold: u32,
    total_games: u64,
    matched_rows: u64,
) -> SiteResult<BTreeMap<String, RowStats>> {
    let mut rows: BTreeMap<String, RowStats> = if eco_base.is_none() {
        catalog::known_stems()
            .into_iter()
            .map(|stem| (stem, RowStats::default()))
            .collect()
    } else {
        BTreeMap::new()
    };
    let sql = format!(
        "SELECT stem, COUNT(*) FROM game_stems WHERE {} GROUP BY stem",
        threshold_where(threshold, view, eco_base, "")
    );
    let mut stmt = db.prepare(&sql)?;
    while stmt.step()? == SQLITE_ROW {
        let stem = stmt.column_text(0);
        let quantity = stmt.column_i64(1).max(0) as u64;
        let row = rows.entry(stem).or_default();
        row.quantity = quantity;
        row.percentage = pct(quantity, total_games);
        row.matched_share = pct(quantity, matched_rows);
    }
    Ok(rows)
}

fn actual_result_rows(
    db: &Db,
    view: &str,
    eco_base: Option<&str>,
    threshold: u32,
) -> SiteResult<BTreeMap<String, ActualStats>> {
    let sql = format!(
        "
        WITH classified AS (
            SELECT
                stem,
                CASE
                    WHEN result = '1/2-1/2' THEN 'draw'
                    WHEN material_side = 'symmetric' AND result IN ('1-0', '0-1') THEN 'decisive'
                    WHEN material_side = 'white' AND result = '1-0' THEN 'win'
                    WHEN material_side = 'white' AND result = '0-1' THEN 'loss'
                    WHEN material_side = 'black' AND result = '0-1' THEN 'win'
                    WHEN material_side = 'black' AND result = '1-0' THEN 'loss'
                    ELSE 'unknown'
                END AS result_outcome
            FROM game_stems
            WHERE {}
        )
        SELECT stem,
               COUNT(*),
               SUM(CASE WHEN result_outcome = 'win' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'draw' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'loss' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'decisive' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'unknown' THEN 1 ELSE 0 END)
        FROM classified GROUP BY stem
        ",
        threshold_where(threshold, view, eco_base, "")
    );
    let mut out = BTreeMap::new();
    let mut stmt = db.prepare(&sql)?;
    while stmt.step()? == SQLITE_ROW {
        out.insert(
            stmt.column_text(0),
            ActualStats {
                total_games: as_u64(stmt.column_i64(1)),
                side_wins: as_u64(stmt.column_i64(2)),
                side_draws: as_u64(stmt.column_i64(3)),
                side_losses: as_u64(stmt.column_i64(4)),
                symmetric_decisive: as_u64(stmt.column_i64(5)),
                unknown_games: as_u64(stmt.column_i64(6)),
            },
        );
    }
    Ok(out)
}

fn wdl_rows(
    db: &Db,
    view: &str,
    eco_base: Option<&str>,
    threshold: u32,
) -> SiteResult<BTreeMap<String, WdlStats>> {
    let mut crosstabs = result_crosstab_rows(db, view, eco_base, threshold)?;
    let sql = format!(
        "
        WITH classified AS (
            SELECT
                p.stem,
                p.material_side,
                p.result,
                e.eval_status,
                e.winning_side,
                CASE
                    WHEN e.eval_status != 'ok' OR e.winning_side = 'unknown' OR p.material_side = 'unknown' THEN 'unknown'
                    WHEN p.material_side = 'symmetric' AND e.winning_side IN ('white', 'black') THEN 'decisive'
                    WHEN p.material_side = 'symmetric' AND e.winning_side = 'draw' THEN 'draw'
                    WHEN p.material_side IN ('white', 'black') AND e.winning_side = p.material_side THEN 'win'
                    WHEN p.material_side IN ('white', 'black') AND e.winning_side = 'draw' THEN 'draw'
                    WHEN p.material_side = 'white' AND e.winning_side = 'black' THEN 'loss'
                    WHEN p.material_side = 'black' AND e.winning_side = 'white' THEN 'loss'
                    ELSE 'unknown'
                END AS tb_outcome,
                CASE
                    WHEN p.result = '1/2-1/2' THEN 'draw'
                    WHEN p.material_side = 'symmetric' AND p.result IN ('1-0', '0-1') THEN 'decisive'
                    WHEN p.material_side = 'white' AND p.result = '1-0' THEN 'win'
                    WHEN p.material_side = 'white' AND p.result = '0-1' THEN 'loss'
                    WHEN p.material_side = 'black' AND p.result = '0-1' THEN 'win'
                    WHEN p.material_side = 'black' AND p.result = '1-0' THEN 'loss'
                    ELSE 'unknown'
                END AS result_outcome
            FROM positions p JOIN evaluations e ON e.eval_key = p.eval_key
            WHERE {}
        )
        SELECT stem,
               COUNT(*),
               SUM(CASE WHEN tb_outcome = 'win' THEN 1 ELSE 0 END),
               SUM(CASE WHEN tb_outcome = 'draw' THEN 1 ELSE 0 END),
               SUM(CASE WHEN tb_outcome = 'loss' THEN 1 ELSE 0 END),
               SUM(CASE WHEN tb_outcome = 'decisive' THEN 1 ELSE 0 END),
               SUM(CASE WHEN tb_outcome = 'unknown' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'win' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'draw' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'loss' THEN 1 ELSE 0 END),
               SUM(CASE WHEN result_outcome = 'decisive' THEN 1 ELSE 0 END)
        FROM classified GROUP BY stem
        ",
        threshold_where(threshold, view, eco_base, "p.")
    );
    let mut out = BTreeMap::new();
    let mut stmt = db.prepare(&sql)?;
    while stmt.step()? == SQLITE_ROW {
        out.insert(
            stmt.column_text(0),
            WdlStats {
                total_positions: as_u64(stmt.column_i64(1)),
                side_wins: as_u64(stmt.column_i64(2)),
                side_draws: as_u64(stmt.column_i64(3)),
                side_losses: as_u64(stmt.column_i64(4)),
                symmetric_decisive: as_u64(stmt.column_i64(5)),
                unknown_positions: as_u64(stmt.column_i64(6)),
                actual_side_wins: as_u64(stmt.column_i64(7)),
                actual_side_draws: as_u64(stmt.column_i64(8)),
                actual_side_losses: as_u64(stmt.column_i64(9)),
                actual_symmetric_decisive: as_u64(stmt.column_i64(10)),
                result_crosstab: crosstabs.remove(&stmt.column_text(0)).unwrap_or_default(),
            },
        );
    }
    Ok(out)
}

fn result_crosstab_rows(
    db: &Db,
    view: &str,
    eco_base: Option<&str>,
    threshold: u32,
) -> SiteResult<BTreeMap<String, ResultCrosstab>> {
    let sql = format!(
        "
        WITH classified AS (
            SELECT
                p.stem,
                CASE
                    WHEN e.eval_status != 'ok' OR e.winning_side = 'unknown' OR p.material_side = 'unknown' THEN 'unknown'
                    WHEN p.material_side = 'symmetric' AND e.winning_side IN ('white', 'black') THEN 'decisive'
                    WHEN p.material_side = 'symmetric' AND e.winning_side = 'draw' THEN 'draw'
                    WHEN p.material_side IN ('white', 'black') AND e.winning_side = p.material_side THEN 'win'
                    WHEN p.material_side IN ('white', 'black') AND e.winning_side = 'draw' THEN 'draw'
                    WHEN p.material_side = 'white' AND e.winning_side = 'black' THEN 'loss'
                    WHEN p.material_side = 'black' AND e.winning_side = 'white' THEN 'loss'
                    ELSE 'unknown'
                END AS tb_outcome,
                CASE
                    WHEN p.result = '1/2-1/2' THEN 'draw'
                    WHEN p.material_side = 'symmetric' AND p.result IN ('1-0', '0-1') THEN 'decisive'
                    WHEN p.material_side = 'white' AND p.result = '1-0' THEN 'win'
                    WHEN p.material_side = 'white' AND p.result = '0-1' THEN 'loss'
                    WHEN p.material_side = 'black' AND p.result = '0-1' THEN 'win'
                    WHEN p.material_side = 'black' AND p.result = '1-0' THEN 'loss'
                    ELSE 'unknown'
                END AS result_outcome
            FROM positions p JOIN evaluations e ON e.eval_key = p.eval_key
            WHERE {}
        )
        SELECT stem, tb_outcome, result_outcome, COUNT(*)
        FROM classified
        GROUP BY stem, tb_outcome, result_outcome
        ",
        threshold_where(threshold, view, eco_base, "p.")
    );
    let mut counts: BTreeMap<String, BTreeMap<String, OutcomeCounts>> = BTreeMap::new();
    let mut stmt = db.prepare(&sql)?;
    while stmt.step()? == SQLITE_ROW {
        let stem = stmt.column_text(0);
        let tb = stmt.column_text(1);
        let result = stmt.column_text(2);
        let n = as_u64(stmt.column_i64(3));
        let row = counts.entry(stem).or_default().entry(tb).or_default();
        match result.as_str() {
            "win" => row.win += n,
            "draw" => row.draw += n,
            "loss" => row.loss += n,
            "decisive" => row.decisive += n,
            _ => row.unknown += n,
        }
    }
    let mut out = BTreeMap::new();
    for (stem, by_tb) in counts {
        let mut rows = Vec::new();
        for outcome in ["win", "draw", "loss", "decisive", "unknown"] {
            if let Some(counts) = by_tb.get(outcome) {
                let total =
                    counts.win + counts.draw + counts.loss + counts.decisive + counts.unknown;
                if total > 0 {
                    rows.push(ResultCrosstabRow {
                        tb_outcome: outcome.to_string(),
                        win: counts.win,
                        draw: counts.draw,
                        loss: counts.loss,
                        decisive: counts.decisive,
                        unknown: counts.unknown,
                        total,
                    });
                }
            }
        }
        out.insert(stem, ResultCrosstab { rows });
    }
    Ok(out)
}

fn build_opening_filters(
    db: &Db,
    source_totals: &SourceTotals,
    opening_catalog: &OpeningCatalog,
    thresholds: &[u32],
) -> SiteResult<Option<OpeningFilters>> {
    let bases = opening_bases(source_totals);
    if bases.is_empty() {
        return Ok(None);
    }
    let mut options = Vec::new();
    let mut views_by_opening = BTreeMap::new();
    let total_bases = bases.len();
    for (index, eco_base) in bases.into_iter().enumerate() {
        if index == 0 || (index + 1) % 25 == 0 || index + 1 == total_bases {
            eprintln!(
                "[reti-site] Aggregating opening filters: {}/{} {}",
                index + 1,
                total_bases,
                eco_base
            );
        }
        let total_games = total_games_for_opening(source_totals, "all", &eco_base);
        if total_games == 0 {
            continue;
        }
        let option = opening_catalog.option_for_base(&eco_base, total_games);
        let mut views = BTreeMap::new();
        for (key, label) in [("all", "All"), ("otb", "OTB"), ("online", "Online")] {
            views.insert(
                key.to_string(),
                View {
                    key: key.to_string(),
                    label: label.to_string(),
                    total_games: total_games_for_opening(source_totals, key, &eco_base),
                    threshold_views: build_threshold_views(
                        db,
                        source_totals,
                        key,
                        Some(&eco_base),
                        thresholds,
                    )?,
                },
            );
        }
        views_by_opening.insert(option.key.clone(), OpeningDatasetViews { views });
        options.push(option);
    }
    options.sort_by(|a, b| a.eco_base.cmp(&b.eco_base).then(a.label.cmp(&b.label)));
    Ok(Some(OpeningFilters {
        default: "all",
        exactness: "exact",
        semantics: "opening filters use standard ECO base codes A00-E99; extended Lumbra ECO tags are normalized to their first three characters",
        options,
        views: views_by_opening,
    }))
}

fn source_thresholds(
    db: &Db,
    view: &str,
    threshold: u32,
) -> SiteResult<BTreeMap<String, SourceThresholdStats>> {
    let sql = format!(
        "SELECT source_pgn, COUNT(*), COUNT(DISTINCT game_key) FROM game_stems WHERE max_run_length >= {}{} GROUP BY source_pgn",
        threshold,
        view_where(view, "")
    );
    let mut out = BTreeMap::new();
    let mut stmt = db.prepare(&sql)?;
    while stmt.step()? == SQLITE_ROW {
        out.insert(
            stmt.column_text(0),
            SourceThresholdStats {
                match_total: as_u64(stmt.column_i64(1)),
                matched_games: as_u64(stmt.column_i64(2)),
            },
        );
    }
    Ok(out)
}

fn source_buckets(db: &Db, totals: &SourceTotals) -> SiteResult<Vec<SourceBucket>> {
    let mut buckets = Vec::new();
    for file in &totals.files {
        let match_total = scalar_count(
            db,
            &format!(
                "SELECT COUNT(*) FROM game_stems WHERE source_pgn = '{}'",
                escape_sql(&file.source_pgn)
            ),
        )?;
        let matched_games = scalar_count(
            db,
            &format!(
                "SELECT COUNT(*) FROM (SELECT game_key FROM game_stems WHERE source_pgn = '{}' GROUP BY game_key)",
                escape_sql(&file.source_pgn)
            ),
        )?;
        buckets.push(SourceBucket {
            source_pgn: file.source_pgn.clone(),
            source_group: file.source_group.clone(),
            display_label: source_bucket_label(&file.source_pgn),
            original_game_count: source_games(totals, &file.source_pgn),
            matched_games,
            match_total,
        });
    }
    Ok(buckets)
}

fn display_rows() -> Vec<DisplayRow> {
    catalog::ENDINGS
        .iter()
        .enumerate()
        .map(|(idx, ending)| {
            let mut auxiliary_rows = Vec::new();
            for (stem, parent, label) in catalog::AUXILIARY.iter() {
                if *parent == ending.stem {
                    let offset = auxiliary_rows.len();
                    auxiliary_rows.push(DisplayRow {
                        stem: (*stem).to_string(),
                        row_id: auxiliary_row_id(ending.row_id, ending.stem, offset),
                        label: (*label).to_string(),
                        chapter: ending.chapter_label.to_string(),
                        color: ending.color.to_string(),
                        sort_index: idx as f64 + (offset as f64 + 1.0) / 10.0,
                        auxiliary_rows: Vec::new(),
                    });
                }
            }
            DisplayRow {
                stem: ending.stem.to_string(),
                row_id: ending.row_id.to_string(),
                label: ending.label.to_string(),
                chapter: ending.chapter_label.to_string(),
                color: ending.color.to_string(),
                sort_index: idx as f64,
                auxiliary_rows,
            }
        })
        .collect()
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

pub fn scalar_count(db: &Db, sql: &str) -> SiteResult<u64> {
    let mut stmt = db.prepare(sql)?;
    if stmt.step()? != SQLITE_ROW {
        return Err(SiteError::new("scalar query returned no rows"));
    }
    Ok(as_u64(stmt.column_i64(0)))
}

fn view_where(view: &str, alias: &str) -> String {
    match view {
        "all" => String::new(),
        "otb" | "online" => format!(" AND {alias}source_group = '{view}'"),
        _ => unreachable!("unknown view"),
    }
}

fn threshold_where(threshold: u32, view: &str, eco_base: Option<&str>, alias: &str) -> String {
    let run_column = if alias == "p." {
        "run_length"
    } else {
        "max_run_length"
    };
    let mut clauses = vec![format!("{alias}{run_column} >= {threshold}")];
    match view {
        "all" => {}
        "otb" | "online" => clauses.push(format!("{alias}source_group = '{view}'")),
        _ => unreachable!("unknown view"),
    }
    if let Some(eco_base) = eco_base {
        clauses.push(format!("{alias}eco_base = '{}'", escape_sql(eco_base)));
    }
    clauses.join(" AND ")
}

fn pct(numerator: u64, denominator: u64) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64 * 100.0
    }
}

fn as_u64(value: i64) -> u64 {
    value.max(0) as u64
}

fn escape_sql(value: &str) -> String {
    value.replace('\'', "''")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn percentage_handles_zero_denominator() {
        assert_eq!(pct(5, 0), 0.0);
        assert_eq!(pct(1, 4), 25.0);
    }

    #[test]
    fn auxiliary_rows_get_sub_ids() {
        assert_eq!(auxiliary_row_id("6.2 A2", "6-2-2RPPr", 0), "6.2 A2a");
        assert_eq!(auxiliary_row_id("", "10-7-1Qbrr", 0), "10.7a");
    }

    #[test]
    fn auxiliary_row_offsets_are_per_parent() {
        let rows = display_rows();
        let rn = rows.iter().find(|row| row.stem == "8-1RNr").unwrap();
        let rb = rows.iter().find(|row| row.stem == "8-2RBr").unwrap();
        assert_eq!(rn.auxiliary_rows[0].row_id, "8.1a");
        assert_eq!(rb.auxiliary_rows[0].row_id, "8.2a");
    }
}
