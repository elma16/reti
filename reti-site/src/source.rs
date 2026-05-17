use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::{SiteError, SiteResult};

#[derive(Debug, Clone)]
pub struct SummaryRow {
    pub source_pgn: String,
    pub source_group: String,
    pub output_pgn: PathBuf,
    pub matched_games: u64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SourceTotals {
    #[serde(rename = "totalGames")]
    pub total_games: u64,
    pub views: BTreeMap<String, u64>,
    #[serde(rename = "openingTotals", default)]
    pub opening_totals: BTreeMap<String, BTreeMap<String, u64>>,
    pub files: Vec<SourceTotalFile>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SourceTotalFile {
    #[serde(rename = "sourcePgn")]
    pub source_pgn: String,
    #[serde(rename = "sourceGroup")]
    pub source_group: String,
    #[serde(rename = "sizeBytes")]
    pub size_bytes: Option<u64>,
    #[serde(rename = "mtimeNs")]
    pub mtime_ns: Option<u64>,
    pub games: u64,
    #[serde(rename = "ecoBaseCounts", default)]
    pub eco_base_counts: BTreeMap<String, u64>,
}

pub fn load_summary(run_dir: &Path) -> SiteResult<Vec<SummaryRow>> {
    let summary = run_dir.join("summary.csv");
    let text = fs::read_to_string(&summary)
        .map_err(|e| SiteError::new(format!("failed to read {}: {e}", summary.display())))?;
    parse_summary_csv(&text, run_dir)
}

pub fn parse_summary_csv(text: &str, run_dir: &Path) -> SiteResult<Vec<SummaryRow>> {
    let mut lines = text.lines();
    let header = lines
        .next()
        .ok_or_else(|| SiteError::new("summary.csv is empty"))?;
    let fields: Vec<&str> = header.split(',').collect();
    let idx = |name: &str| {
        fields
            .iter()
            .position(|field| *field == name)
            .ok_or_else(|| SiteError::new(format!("summary.csv missing {name:?} column")))
    };
    let pgn_idx = idx("pgn")?;
    let cql_idx = idx("cql")?;
    let output_idx = idx("output_pgn")?;
    let status_idx = idx("status")?;
    let count_idx = idx("match_count")?;

    let mut rows = Vec::new();
    let mut seen = BTreeSet::new();
    for (line_no, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let cells: Vec<&str> = line.split(',').collect();
        if cells.len() < fields.len() {
            return Err(SiteError::new(format!(
                "summary.csv row {} has too few columns",
                line_no + 2
            )));
        }
        let source_pgn = cells[pgn_idx].trim().to_string();
        if cells[cql_idx].trim() != "fce-table-markers.cql" {
            return Err(SiteError::new(format!(
                "summary.csv row {} has unexpected CQL script {:?}",
                line_no + 2,
                cells[cql_idx]
            )));
        }
        if cells[status_idx].trim() != "ok" {
            return Err(SiteError::new(format!(
                "summary.csv row {} is not ok: {}",
                line_no + 2,
                cells[status_idx]
            )));
        }
        if !seen.insert(source_pgn.clone()) {
            return Err(SiteError::new(format!(
                "summary.csv has duplicate source row {source_pgn}"
            )));
        }
        let matched_games = cells[count_idx].trim().parse::<u64>().map_err(|e| {
            SiteError::new(format!(
                "summary.csv row {} has invalid match_count: {e}",
                line_no + 2
            ))
        })?;
        let output_pgn = run_dir.join(cells[output_idx].trim());
        if !output_pgn.is_file() {
            return Err(SiteError::new(format!(
                "annotated output PGN is missing: {}",
                output_pgn.display()
            )));
        }
        let source_group = classify_source_group(&source_pgn)?;
        rows.push(SummaryRow {
            source_pgn,
            source_group,
            output_pgn,
            matched_games,
        });
    }
    rows.sort_by(|a, b| source_sort_key(&a.source_pgn).cmp(&source_sort_key(&b.source_pgn)));
    Ok(rows)
}

pub fn load_source_totals(path: &Path, summary_rows: &[SummaryRow]) -> SiteResult<SourceTotals> {
    let totals = read_source_totals(path)?;
    validate_source_totals(&totals, summary_rows)?;
    Ok(totals)
}

pub fn read_source_totals(path: &Path) -> SiteResult<SourceTotals> {
    let text = fs::read_to_string(path)
        .map_err(|e| SiteError::new(format!("failed to read {}: {e}", path.display())))?;
    Ok(serde_json::from_str(&text)?)
}

fn validate_source_totals(totals: &SourceTotals, summary_rows: &[SummaryRow]) -> SiteResult<()> {
    let by_source: BTreeMap<&str, &SourceTotalFile> = totals
        .files
        .iter()
        .map(|file| (file.source_pgn.as_str(), file))
        .collect();
    let summary_sources: BTreeSet<&str> = summary_rows
        .iter()
        .map(|row| row.source_pgn.as_str())
        .collect();
    if by_source.len() != summary_sources.len() {
        return Err(SiteError::new(format!(
            "source totals list {} files but summary.csv lists {} files",
            by_source.len(),
            summary_sources.len()
        )));
    }
    for row in summary_rows {
        let source = by_source
            .get(row.source_pgn.as_str())
            .ok_or_else(|| SiteError::new(format!("source totals missing {}", row.source_pgn)))?;
        if source.source_group != row.source_group {
            return Err(SiteError::new(format!(
                "source totals classify {} as {}, expected {}",
                row.source_pgn, source.source_group, row.source_group
            )));
        }
        if source.games < row.matched_games {
            return Err(SiteError::new(format!(
                "source totals for {} has fewer games than matched output",
                row.source_pgn
            )));
        }
    }
    for source in &totals.files {
        if !summary_sources.contains(source.source_pgn.as_str()) {
            return Err(SiteError::new(format!(
                "source totals has extra file not present in summary.csv: {}",
                source.source_pgn
            )));
        }
        let classified = classify_source_group(&source.source_pgn)?;
        if classified != source.source_group {
            return Err(SiteError::new(format!(
                "source totals classify {} as {}, expected {}",
                source.source_pgn, source.source_group, classified
            )));
        }
    }
    let all_games: u64 = totals.files.iter().map(|file| file.games).sum();
    let otb_games: u64 = totals
        .files
        .iter()
        .filter(|file| file.source_group == "otb")
        .map(|file| file.games)
        .sum();
    let online_games: u64 = totals
        .files
        .iter()
        .filter(|file| file.source_group == "online")
        .map(|file| file.games)
        .sum();
    if totals.total_games != all_games {
        return Err(SiteError::new(format!(
            "source totals totalGames={} but file sum is {all_games}",
            totals.total_games
        )));
    }
    validate_view_total(totals, "all", all_games)?;
    validate_view_total(totals, "otb", otb_games)?;
    validate_view_total(totals, "online", online_games)?;
    validate_opening_totals(totals)?;
    Ok(())
}

fn validate_view_total(totals: &SourceTotals, view: &str, expected: u64) -> SiteResult<()> {
    let actual = totals
        .views
        .get(view)
        .copied()
        .ok_or_else(|| SiteError::new(format!("source totals missing {view:?} view")))?;
    if actual != expected {
        return Err(SiteError::new(format!(
            "source totals view {view}={actual} but expected {expected}"
        )));
    }
    Ok(())
}

fn validate_opening_totals(totals: &SourceTotals) -> SiteResult<()> {
    if totals.opening_totals.is_empty() {
        return Ok(());
    }
    for view in ["all", "otb", "online"] {
        let Some(openings) = totals.opening_totals.get(view) else {
            return Err(SiteError::new(format!(
                "source totals openingTotals missing {view:?} view"
            )));
        };
        let opening_sum: u64 = openings.values().sum();
        let view_total = total_games_for_view(totals, view);
        if opening_sum != view_total {
            return Err(SiteError::new(format!(
                "source totals openingTotals {view} sum {opening_sum} but view total is {view_total}"
            )));
        }
    }
    Ok(())
}

pub fn total_games_for_view(totals: &SourceTotals, view: &str) -> u64 {
    totals.views.get(view).copied().unwrap_or(0)
}

pub fn total_games_for_opening(totals: &SourceTotals, view: &str, eco_base: &str) -> u64 {
    totals
        .opening_totals
        .get(view)
        .and_then(|values| values.get(eco_base))
        .copied()
        .unwrap_or(0)
}

pub fn opening_bases(totals: &SourceTotals) -> Vec<String> {
    totals
        .opening_totals
        .get("all")
        .map(|values| {
            values
                .keys()
                .filter(|key| key.as_str() != "unknown")
                .cloned()
                .collect()
        })
        .unwrap_or_default()
}

pub fn source_games(totals: &SourceTotals, source_pgn: &str) -> u64 {
    totals
        .files
        .iter()
        .find(|file| file.source_pgn == source_pgn)
        .map(|file| file.games)
        .unwrap_or(0)
}

pub fn classify_source_group(source_pgn: &str) -> SiteResult<String> {
    if source_pgn.starts_with("LumbrasGigaBase_OTB_") {
        Ok("otb".to_string())
    } else if source_pgn.starts_with("LumbrasGigaBase_Online_") {
        Ok("online".to_string())
    } else {
        Err(SiteError::new(format!(
            "unknown source group for {source_pgn}; expected LumbrasGigaBase_OTB_* or LumbrasGigaBase_Online_*"
        )))
    }
}

pub fn source_bucket_label(source_pgn: &str) -> String {
    source_pgn
        .trim_end_matches(".pgn")
        .trim_start_matches("LumbrasGigaBase_")
        .replace("_partial_release", " partial")
        .replace('_', " ")
}

fn source_sort_key(source_pgn: &str) -> (u32, String) {
    let stem = source_pgn.trim_end_matches(".pgn");
    if stem.ends_with("_noDate") {
        return (999_999, stem.to_string());
    }
    for token in stem.replace('-', "_").split('_') {
        if token.len() >= 4 && token[..4].chars().all(|ch| ch.is_ascii_digit()) {
            return (
                token[..4].parse::<u32>().unwrap_or(999_998),
                stem.to_string(),
            );
        }
        if token.chars().all(|ch| ch.is_ascii_digit()) {
            return (token.parse::<u32>().unwrap_or(999_998), stem.to_string());
        }
    }
    (999_998, stem.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_sources() {
        assert_eq!(
            classify_source_group("LumbrasGigaBase_OTB_2025.pgn").unwrap(),
            "otb"
        );
        assert_eq!(
            classify_source_group("LumbrasGigaBase_Online_2025.pgn").unwrap(),
            "online"
        );
        assert!(classify_source_group("other.pgn").is_err());
    }

    #[test]
    fn source_totals_must_match_summary_exactly() {
        let rows = vec![SummaryRow {
            source_pgn: "LumbrasGigaBase_OTB_2025.pgn".to_string(),
            source_group: "otb".to_string(),
            output_pgn: PathBuf::from("x.pgn"),
            matched_games: 1,
        }];
        let totals = SourceTotals {
            total_games: 2,
            views: BTreeMap::from([
                ("all".to_string(), 2),
                ("otb".to_string(), 1),
                ("online".to_string(), 1),
            ]),
            opening_totals: BTreeMap::new(),
            files: vec![
                SourceTotalFile {
                    source_pgn: "LumbrasGigaBase_OTB_2025.pgn".to_string(),
                    source_group: "otb".to_string(),
                    size_bytes: None,
                    mtime_ns: None,
                    games: 1,
                    eco_base_counts: BTreeMap::new(),
                },
                SourceTotalFile {
                    source_pgn: "LumbrasGigaBase_Online_2025.pgn".to_string(),
                    source_group: "online".to_string(),
                    size_bytes: None,
                    mtime_ns: None,
                    games: 1,
                    eco_base_counts: BTreeMap::new(),
                },
            ],
        };
        assert!(validate_source_totals(&totals, &rows).is_err());
    }
}
