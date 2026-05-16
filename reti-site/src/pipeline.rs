use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::aggregate::{build_snapshot, ensure_indexes};
use crate::catalog;
use crate::cli::BuildConfig;
use crate::csv_export;
use crate::manifest::{base_manifest, fingerprint, manifest_matches};
use crate::render;
use crate::source::{load_source_totals, load_summary};
use crate::sqlite::Db;
use crate::{SiteError, SiteResult};

#[derive(Debug, Clone)]
pub struct BuildResult {
    pub output_dir: PathBuf,
    pub snapshot_json: PathBuf,
    pub sqlite_db: PathBuf,
    pub index_html: PathBuf,
    pub up_to_date: bool,
}

pub fn build_fce_tablebase(config: BuildConfig) -> SiteResult<BuildResult> {
    log_phase("Validating combined run and source totals");
    let annotated_run_dir = absolutize(&config.annotated_run_dir)?;
    let source_totals_json = absolutize(&config.source_totals_json)?;
    let output_dir = absolutize(&config.output_dir)?;
    let work_parent = match &config.work_dir {
        Some(path) => absolutize(path)?,
        None => output_dir
            .parent()
            .ok_or_else(|| SiteError::new("output dir has no parent"))?
            .to_path_buf(),
    };
    let pgn_utils_bin = absolutize(&config.pgn_utils_bin)?;
    let syzygy_dirs: Vec<PathBuf> = config
        .syzygy_dirs
        .iter()
        .map(|path| absolutize(path))
        .collect::<SiteResult<_>>()?;

    let summary_rows = load_summary(&annotated_run_dir)?;
    let source_totals = load_source_totals(&source_totals_json, &summary_rows)?;
    let expected_matched_games: u64 = summary_rows.iter().map(|row| row.matched_games).sum();
    let manifest = base_manifest(
        &config.title,
        &annotated_run_dir,
        &source_totals_json,
        &syzygy_dirs,
        &pgn_utils_bin,
        &config.thresholds,
        config.tablebase_threshold,
    )?;

    log_phase("Checking output manifest");
    if output_dir.exists() && !config.force {
        if manifest_matches(&output_dir.join("manifest.json"), &manifest)
            && output_dir.join("snapshot.json").is_file()
            && output_dir.join("evaluations.sqlite3").is_file()
            && output_dir.join("index.html").is_file()
        {
            return Ok(result(output_dir, true));
        }
        return Err(SiteError::new(format!(
            "{} already exists with a different manifest; use --force or choose a new output dir",
            output_dir.display()
        )));
    }

    log_phase("Preparing temporary output directory");
    fs::create_dir_all(&work_parent)?;
    fs::create_dir_all(
        output_dir
            .parent()
            .ok_or_else(|| SiteError::new("output dir has no parent"))?,
    )?;
    let temp_dir = work_parent.join(format!(
        ".{}.tmp-{}",
        output_dir
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("reti-site"),
        std::process::id()
    ));
    if temp_dir.exists() {
        fs::remove_dir_all(&temp_dir)?;
    }
    fs::create_dir_all(&temp_dir)?;

    let committed = (|| -> SiteResult<()> {
        let db_path = temp_dir.join("evaluations.sqlite3");
        log_phase("Streaming combined marker PGNs into SQLite with Rust");
        let ingest_stats = run_marker_ingest(
            &pgn_utils_bin,
            &annotated_run_dir,
            &db_path,
            &catalog::known_stems()
                .into_iter()
                .collect::<Vec<_>>()
                .join(","),
            &fingerprint(&manifest)?[..16],
            config.tablebase_threshold,
            !config.no_progress,
        )?;
        validate_marker_ingest_stats(
            &ingest_stats,
            summary_rows.len() as u64,
            expected_matched_games,
        )?;
        log_phase("Creating SQLite indexes");
        let db = Db::open(&db_path, false)?;
        ensure_indexes(&db)?;
        drop(db);
        log_phase("Evaluating unique first-marker <=5-man FENs with Rust Syzygy");
        run_syzygy_eval(
            &pgn_utils_bin,
            &db_path,
            &syzygy_dirs,
            config.tablebase_threshold,
            config.workers,
            !config.no_progress,
        )?;
        log_phase("Aggregating corpus views and threshold tables");
        let db = Db::open(&db_path, false)?;
        let snapshot_id = format!(
            "fce-combined-rust-{}",
            manifest["fingerprint"]
                .as_str()
                .unwrap_or("unknown")
                .get(0..12)
                .unwrap_or("unknown")
        );
        let snapshot = build_snapshot(
            &db,
            &config.title,
            snapshot_id,
            generated_at(),
            &source_totals,
            &config.thresholds,
        )?;
        log_phase("Writing snapshot JSON, CSV exports, and HTML");
        write_json(
            &temp_dir.join("snapshot.json"),
            &serde_json::to_value(&snapshot)?,
        )?;
        write_json(&temp_dir.join("manifest.json"), &manifest)?;
        csv_export::write_summary_by_ending(&snapshot, &temp_dir.join("summary_by_ending.csv"))?;
        csv_export::write_tablebase_wdl(
            &snapshot,
            &temp_dir.join("tablebase_wdl_by_view_threshold.csv"),
        )?;
        fs::write(temp_dir.join("index.html"), render::render_html(&snapshot)?)?;
        Ok(())
    })();

    match committed {
        Ok(()) => {
            log_phase("Installing completed snapshot atomically");
            install_dir(&temp_dir, &output_dir, config.force)?;
            Ok(result(output_dir, false))
        }
        Err(err) => {
            let _ = fs::remove_dir_all(&temp_dir);
            Err(err)
        }
    }
}

fn run_marker_ingest(
    pgn_utils_bin: &Path,
    annotated_run_dir: &Path,
    db_path: &Path,
    known_stems: &str,
    profile_id: &str,
    tablebase_threshold: u32,
    show_progress: bool,
) -> SiteResult<Value> {
    let mut cmd = Command::new(pgn_utils_bin);
    cmd.arg("fce-combined-markers")
        .arg("--relative-to")
        .arg(annotated_run_dir)
        .arg("--known-stems")
        .arg(known_stems)
        .arg("--max-pieces")
        .arg(tablebase_threshold.to_string())
        .arg("--sqlite-db")
        .arg(db_path)
        .arg("--profile-id")
        .arg(profile_id)
        .arg("--sqlite-batch-rows")
        .arg("1000000");
    if !show_progress {
        cmd.arg("--no-progress");
    }
    cmd.arg(annotated_run_dir);
    run_command_json(cmd, "combined marker ingest")
}

fn run_syzygy_eval(
    pgn_utils_bin: &Path,
    db_path: &Path,
    syzygy_dirs: &[PathBuf],
    tablebase_threshold: u32,
    workers: usize,
    show_progress: bool,
) -> SiteResult<()> {
    let mut cmd = Command::new(pgn_utils_bin);
    cmd.arg("fce-syzygy-eval")
        .arg("--db")
        .arg(db_path)
        .arg("--max-pieces")
        .arg(tablebase_threshold.to_string())
        .arg("--batch-rows")
        .arg("20000")
        .arg("--workers")
        .arg(workers.to_string());
    for dir in syzygy_dirs {
        cmd.arg("--syzygy-dir").arg(dir);
    }
    if !show_progress {
        cmd.arg("--no-progress");
    }
    let _stats = run_command_json(cmd, "Syzygy evaluation")?;
    Ok(())
}

fn run_command_json(mut cmd: Command, label: &str) -> SiteResult<Value> {
    let output = cmd
        .stderr(Stdio::inherit())
        .output()
        .map_err(|e| SiteError::new(format!("failed to start {label}: {e}")))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    eprint!("{stdout}");
    if !output.status.success() {
        return Err(SiteError::new(format!(
            "{label} failed with status {}",
            output.status
        )));
    }
    let json_line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{'))
        .ok_or_else(|| SiteError::new(format!("{label} did not print JSON stats")))?;
    serde_json::from_str(json_line)
        .map_err(|e| SiteError::new(format!("failed to parse {label} JSON stats: {e}")))
}

fn validate_marker_ingest_stats(
    stats: &Value,
    expected_files: u64,
    expected_games: u64,
) -> SiteResult<()> {
    let files = stats
        .get("files_processed")
        .and_then(Value::as_u64)
        .ok_or_else(|| SiteError::new("marker ingest stats missing files_processed"))?;
    let games = stats
        .get("games_read")
        .and_then(Value::as_u64)
        .ok_or_else(|| SiteError::new("marker ingest stats missing games_read"))?;
    let parse_errors = stats
        .get("parse_errors")
        .and_then(Value::as_u64)
        .ok_or_else(|| SiteError::new("marker ingest stats missing parse_errors"))?;
    if files != expected_files {
        return Err(SiteError::new(format!(
            "marker ingest processed {files} files, expected {expected_files} from summary.csv"
        )));
    }
    if games != expected_games {
        return Err(SiteError::new(format!(
            "marker ingest read {games} games, expected {expected_games} from summary.csv match_count"
        )));
    }
    if parse_errors != 0 {
        return Err(SiteError::new(format!(
            "marker ingest reported {parse_errors} parse errors"
        )));
    }
    Ok(())
}

fn write_json(path: &Path, value: &Value) -> SiteResult<()> {
    fs::write(path, serde_json::to_string_pretty(value)? + "\n")?;
    Ok(())
}

fn install_dir(temp_dir: &Path, output_dir: &Path, force: bool) -> SiteResult<()> {
    if output_dir.exists() {
        if force {
            fs::remove_dir_all(output_dir)?;
        } else {
            return Err(SiteError::new(format!(
                "output exists: {}",
                output_dir.display()
            )));
        }
    }
    match fs::rename(temp_dir, output_dir) {
        Ok(()) => Ok(()),
        Err(_) => {
            let parent = output_dir
                .parent()
                .ok_or_else(|| SiteError::new("output dir has no parent"))?;
            let staging = parent.join(format!(
                ".{}.install-{}",
                output_dir
                    .file_name()
                    .and_then(|name| name.to_str())
                    .unwrap_or("reti-site"),
                std::process::id()
            ));
            if staging.exists() {
                fs::remove_dir_all(&staging)?;
            }
            copy_dir(temp_dir, &staging)?;
            fs::rename(&staging, output_dir)?;
            fs::remove_dir_all(temp_dir)?;
            Ok(())
        }
    }
}

fn copy_dir(from: &Path, to: &Path) -> SiteResult<()> {
    fs::create_dir_all(to)?;
    for entry in fs::read_dir(from)? {
        let entry = entry?;
        let target = to.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir(&entry.path(), &target)?;
        } else {
            fs::copy(entry.path(), target)?;
        }
    }
    Ok(())
}

fn result(output_dir: PathBuf, up_to_date: bool) -> BuildResult {
    BuildResult {
        snapshot_json: output_dir.join("snapshot.json"),
        sqlite_db: output_dir.join("evaluations.sqlite3"),
        index_html: output_dir.join("index.html"),
        output_dir,
        up_to_date,
    }
}

fn absolutize(path: &Path) -> SiteResult<PathBuf> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        Ok(std::env::current_dir()?.join(path))
    }
}

fn log_phase(message: &str) {
    eprintln!("[reti-site] {message}");
}

fn generated_at() -> String {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(duration) => format_unix_utc(duration.as_secs() as i64),
        Err(_) => "1970-01-01T00:00:00Z".to_string(),
    }
}

fn format_unix_utc(seconds: i64) -> String {
    let days = seconds.div_euclid(86_400);
    let seconds_of_day = seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    let hour = seconds_of_day / 3_600;
    let minute = (seconds_of_day % 3_600) / 60;
    let second = seconds_of_day % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

fn civil_from_days(days_since_unix_epoch: i64) -> (i64, i64, i64) {
    let z = days_since_unix_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    let year = y + if month <= 2 { 1 } else { 0 };
    (year, month, day)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generated_time_is_stable_shape() {
        let timestamp = generated_at();
        assert!(timestamp.ends_with('Z'));
        assert!(timestamp.contains('T'));
    }

    #[test]
    fn unix_time_formats_as_utc_iso8601() {
        assert_eq!(format_unix_utc(0), "1970-01-01T00:00:00Z");
        assert_eq!(format_unix_utc(86_400), "1970-01-02T00:00:00Z");
        assert_eq!(format_unix_utc(1_704_067_199), "2023-12-31T23:59:59Z");
    }

    #[test]
    fn marker_ingest_stats_must_match_summary() {
        let stats = serde_json::json!({
            "files_processed": 2,
            "games_read": 10,
            "parse_errors": 0
        });
        assert!(validate_marker_ingest_stats(&stats, 2, 10).is_ok());
        assert!(validate_marker_ingest_stats(&stats, 3, 10).is_err());
        assert!(validate_marker_ingest_stats(&stats, 2, 11).is_err());
    }
}
