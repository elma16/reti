//! `source-totals` subcommand: count source PGN games once.
//!
//! The combined FCE marker output only contains games that matched at least
//! one ending. To compute corpus percentages later, the dashboard also needs
//! exact per-source denominators, including games that matched no ending.
//! This command streams the original source PGNs once and writes a small,
//! deterministic JSON artifact keyed by source PGN filename.

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use crate::cli;
use crate::concat::expand_inputs;
use crate::progress::ProgressReporter;

const USAGE: &str = "\
usage: pgn-utils source-totals [options] INPUT_PGN_OR_DIR...

options:
  -o, --output PATH       write JSON to PATH; use '-' or omit for stdout
  --force                 replace an existing output file
  --no-progress           disable the stderr progress bar";

#[derive(Debug, Clone)]
pub struct SourceTotalsOptions {
    pub inputs: Vec<PathBuf>,
    pub output: Option<PathBuf>,
    pub force: bool,
    pub show_progress: bool,
}

#[derive(Debug, Clone, Eq, PartialEq)]
pub struct SourceFileTotal {
    pub source_pgn: String,
    pub source_group: String,
    pub path: String,
    pub size_bytes: u64,
    pub modified_unix_nanos: u128,
    pub games: usize,
    pub eco_base_counts: BTreeMap<String, usize>,
}

#[derive(Debug, Clone, Eq, PartialEq)]
pub struct SourceTotals {
    pub files_processed: usize,
    pub bytes_in: u64,
    pub total_games: usize,
    pub views: BTreeMap<String, usize>,
    pub opening_totals: BTreeMap<String, BTreeMap<String, usize>>,
    pub files: Vec<SourceFileTotal>,
}

impl SourceTotals {
    pub fn to_json(&self) -> String {
        let mut out = String::new();
        out.push('{');
        out.push_str("\"schemaVersion\":1,");
        out.push_str("\"kind\":\"reti-pgn-source-totals\",");
        out.push_str("\"countMethod\":\"event-tag-lines\",");
        out.push_str(&format!("\"filesProcessed\":{},", self.files_processed));
        out.push_str(&format!("\"bytesIn\":{},", self.bytes_in));
        out.push_str(&format!("\"totalGames\":{},", self.total_games));
        out.push_str("\"views\":{");
        for (index, (key, value)) in self.views.iter().enumerate() {
            if index > 0 {
                out.push(',');
            }
            out.push_str(&json_string(key));
            out.push(':');
            out.push_str(&value.to_string());
        }
        out.push_str("},\"openingTotals\":{");
        for (view_index, (view, totals)) in self.opening_totals.iter().enumerate() {
            if view_index > 0 {
                out.push(',');
            }
            out.push_str(&json_string(view));
            out.push_str(":{");
            for (eco_index, (eco, games)) in totals.iter().enumerate() {
                if eco_index > 0 {
                    out.push(',');
                }
                out.push_str(&json_string(eco));
                out.push(':');
                out.push_str(&games.to_string());
            }
            out.push('}');
        }
        out.push_str("},\"files\":[");
        for (index, file) in self.files.iter().enumerate() {
            if index > 0 {
                out.push(',');
            }
            out.push('{');
            out.push_str("\"sourcePgn\":");
            out.push_str(&json_string(&file.source_pgn));
            out.push_str(",\"sourceGroup\":");
            out.push_str(&json_string(&file.source_group));
            out.push_str(",\"path\":");
            out.push_str(&json_string(&file.path));
            out.push_str(&format!(
                ",\"sizeBytes\":{},\"mtimeNs\":{},\"games\":{}",
                file.size_bytes, file.modified_unix_nanos, file.games
            ));
            out.push_str(",\"ecoBaseCounts\":{");
            for (eco_index, (eco, games)) in file.eco_base_counts.iter().enumerate() {
                if eco_index > 0 {
                    out.push(',');
                }
                out.push_str(&json_string(eco));
                out.push(':');
                out.push_str(&games.to_string());
            }
            out.push('}');
            out.push('}');
        }
        out.push_str("]}");
        out
    }
}

pub fn run_source_totals(opts: SourceTotalsOptions) -> io::Result<SourceTotals> {
    let files = expand_inputs(&opts.inputs)?;
    let total_bytes: u64 = files
        .iter()
        .map(|p| fs::metadata(p).map(|m| m.len()).unwrap_or(0))
        .sum();
    let progress = ProgressReporter::bytes(total_bytes, "source totals", opts.show_progress);

    let mut seen_names = BTreeSet::new();
    let mut file_totals = Vec::with_capacity(files.len());
    let mut views = BTreeMap::new();
    views.insert("all".to_string(), 0usize);
    views.insert("online".to_string(), 0usize);
    views.insert("otb".to_string(), 0usize);
    views.insert("unknown".to_string(), 0usize);
    let mut opening_totals: BTreeMap<String, BTreeMap<String, usize>> = BTreeMap::new();
    for view in ["all", "online", "otb", "unknown"] {
        opening_totals.insert(view.to_string(), BTreeMap::new());
    }

    for path in &files {
        let metadata = fs::metadata(path)?;
        let source_pgn = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "invalid PGN filename"))?
            .to_string();
        if !seen_names.insert(source_pgn.clone()) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("duplicate source PGN filename: {source_pgn}"),
            ));
        }

        let file = File::open(path)?;
        let reader = BufReader::new(progress.wrap(file));
        let file_counts = count_games_and_eco_bases(reader)?;
        let games = file_counts.games;
        let source_group = classify_source_group(&source_pgn).to_string();
        *views.entry("all".to_string()).or_insert(0) += games;
        *views.entry(source_group.clone()).or_insert(0) += games;
        add_opening_counts(&mut opening_totals, "all", &file_counts.eco_base_counts);
        add_opening_counts(
            &mut opening_totals,
            &source_group,
            &file_counts.eco_base_counts,
        );

        let modified_unix_nanos = metadata
            .modified()
            .ok()
            .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
            .map(|duration| duration.as_nanos())
            .unwrap_or(0);
        let path_string = fs::canonicalize(path)
            .unwrap_or_else(|_| path.clone())
            .to_string_lossy()
            .into_owned();
        file_totals.push(SourceFileTotal {
            source_pgn,
            source_group,
            path: path_string,
            size_bytes: metadata.len(),
            modified_unix_nanos,
            games,
            eco_base_counts: file_counts.eco_base_counts,
        });
    }

    progress.finish("source totals done");
    let total_games = views.get("all").copied().unwrap_or(0);
    Ok(SourceTotals {
        files_processed: file_totals.len(),
        bytes_in: total_bytes,
        total_games,
        views,
        opening_totals,
        files: file_totals,
    })
}

#[derive(Debug, Clone, Eq, PartialEq)]
struct FileCounts {
    games: usize,
    eco_base_counts: BTreeMap<String, usize>,
}

fn count_games_and_eco_bases<R: BufRead>(mut reader: R) -> io::Result<FileCounts> {
    let mut games = 0usize;
    let mut eco_base_counts = BTreeMap::new();
    let mut in_game = false;
    let mut current_eco_base: Option<String> = None;
    let mut line = Vec::new();
    loop {
        line.clear();
        let n = reader.read_until(b'\n', &mut line)?;
        if n == 0 {
            break;
        }
        let clean = strip_eol(&line);
        if is_event_line(clean) {
            if in_game {
                games += 1;
                let eco = current_eco_base
                    .take()
                    .unwrap_or_else(|| "unknown".to_string());
                *eco_base_counts.entry(eco).or_insert(0) += 1;
            }
            in_game = true;
        } else if in_game && current_eco_base.is_none() {
            if let Some(eco) = eco_base_from_tag_line(clean) {
                current_eco_base = Some(eco);
            }
        }
    }
    if in_game {
        games += 1;
        let eco = current_eco_base.unwrap_or_else(|| "unknown".to_string());
        *eco_base_counts.entry(eco).or_insert(0) += 1;
    }
    Ok(FileCounts {
        games,
        eco_base_counts,
    })
}

#[cfg(test)]
fn count_event_tags<R: BufRead>(reader: R) -> io::Result<usize> {
    Ok(count_games_and_eco_bases(reader)?.games)
}

fn add_opening_counts(
    opening_totals: &mut BTreeMap<String, BTreeMap<String, usize>>,
    view: &str,
    counts: &BTreeMap<String, usize>,
) {
    let view_totals = opening_totals.entry(view.to_string()).or_default();
    for (eco, games) in counts {
        *view_totals.entry(eco.clone()).or_insert(0) += *games;
    }
}

fn strip_eol(line: &[u8]) -> &[u8] {
    let mut end = line.len();
    if end > 0 && line[end - 1] == b'\n' {
        end -= 1;
    }
    if end > 0 && line[end - 1] == b'\r' {
        end -= 1;
    }
    &line[..end]
}

fn is_event_line(line: &[u8]) -> bool {
    let trimmed = trim_ascii_start(line);
    trimmed.starts_with(b"[Event ") || trimmed.starts_with(b"[Event\t")
}

fn eco_base_from_tag_line(line: &[u8]) -> Option<String> {
    let trimmed = trim_ascii_start(line);
    if !(trimmed.starts_with(b"[ECO ") || trimmed.starts_with(b"[ECO\t")) {
        return None;
    }
    let first_quote = trimmed.iter().position(|&b| b == b'"')?;
    let rest = &trimmed[first_quote + 1..];
    let second_quote = rest.iter().position(|&b| b == b'"')?;
    let raw = std::str::from_utf8(&rest[..second_quote]).ok()?.trim();
    normalize_eco_base(raw)
}

fn normalize_eco_base(raw: &str) -> Option<String> {
    let raw = raw.trim();
    if raw.len() < 3 {
        return None;
    }
    let mut chars = raw.chars();
    let family = chars.next()?.to_ascii_uppercase();
    let d1 = chars.next()?;
    let d2 = chars.next()?;
    if !matches!(family, 'A'..='E') || !d1.is_ascii_digit() || !d2.is_ascii_digit() {
        return None;
    }
    Some(format!("{family}{d1}{d2}"))
}

fn trim_ascii_start(line: &[u8]) -> &[u8] {
    let mut index = 0usize;
    while index < line.len() && (line[index] == b' ' || line[index] == b'\t') {
        index += 1;
    }
    &line[index..]
}

fn classify_source_group(source_pgn: &str) -> &'static str {
    if source_pgn.starts_with("LumbrasGigaBase_OTB_") {
        "otb"
    } else if source_pgn.starts_with("LumbrasGigaBase_Online_") {
        "online"
    } else {
        "unknown"
    }
}

fn json_string(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('"');
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            ch if ch < ' ' => out.push_str(&format!("\\u{:04x}", ch as u32)),
            ch => out.push(ch),
        }
    }
    out.push('"');
    out
}

fn write_output(path: Option<&Path>, json: &str, force: bool) -> io::Result<()> {
    match path {
        None => {
            println!("{json}");
            Ok(())
        }
        Some(path) if path == Path::new("-") => {
            println!("{json}");
            Ok(())
        }
        Some(path) => {
            if path.exists() && !force {
                return Err(io::Error::new(
                    io::ErrorKind::AlreadyExists,
                    format!("output already exists: {}", path.display()),
                ));
            }
            if let Some(parent) = path.parent() {
                if !parent.as_os_str().is_empty() {
                    fs::create_dir_all(parent)?;
                }
            }
            let tmp_path = path.with_extension(format!(
                "{}.tmp-{}",
                path.extension()
                    .and_then(|ext| ext.to_str())
                    .unwrap_or("json"),
                std::process::id()
            ));
            {
                let mut writer = BufWriter::new(File::create(&tmp_path)?);
                writer.write_all(json.as_bytes())?;
                writer.write_all(b"\n")?;
                writer.flush()?;
            }
            match fs::rename(&tmp_path, path) {
                Ok(()) => {}
                Err(err) if force && path.exists() => {
                    fs::remove_file(path)?;
                    fs::rename(tmp_path, path).map_err(|rename_err| {
                        io::Error::new(
                            rename_err.kind(),
                            format!(
                                "rename after replacing {} failed: {rename_err}; original error: {err}",
                                path.display()
                            ),
                        )
                    })?;
                }
                Err(err) => return Err(err),
            }
            Ok(())
        }
    }
}

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    if args.iter().any(|arg| {
        let text = arg.to_string_lossy();
        text == "--help" || text == "-h" || text == "help"
    }) {
        println!("{USAGE}");
        return Ok(());
    }
    let parsed = cli::parse(args, &["force"], &["output", "o"]).map_err(|e| e.to_string())?;
    if parsed.positionals.is_empty() {
        return Err(format!("source-totals: no input files supplied\n{USAGE}"));
    }
    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);
    let opts = SourceTotalsOptions {
        inputs: parsed.positionals.clone(),
        output: output.clone(),
        force: parsed.has_flag("force"),
        show_progress: !parsed.global.no_progress,
    };
    let totals = run_source_totals(opts).map_err(|e| format!("source-totals failed: {e}"))?;
    write_output(
        output.as_deref(),
        &totals.to_json(),
        parsed.has_flag("force"),
    )
    .map_err(|e| format!("source-totals failed: {e}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn counts_event_tag_lines() {
        let input = b" [Event \"a\"]\n[Site \"?\"]\n\n1. e4 *\n\t[Event \"b\"]\n\n1. d4 *\n";
        assert_eq!(count_event_tags(Cursor::new(input)).unwrap(), 2);
    }

    #[test]
    fn counts_eco_bases_per_game() {
        let input = b"[Event \"a\"]\n[ECO \"A00q\"]\n\n1. b4 *\n[Event \"b\"]\n[Site \"?\"]\n\n1. d4 *\n[Event \"c\"]\n[ECO \"e99\"]\n\n1. d4 *\n";
        let counts = count_games_and_eco_bases(Cursor::new(input)).unwrap();
        assert_eq!(counts.games, 3);
        assert_eq!(counts.eco_base_counts.get("A00"), Some(&1));
        assert_eq!(counts.eco_base_counts.get("E99"), Some(&1));
        assert_eq!(counts.eco_base_counts.get("unknown"), Some(&1));
    }

    #[test]
    fn normalizes_eco_base_from_extended_code() {
        assert_eq!(normalize_eco_base("A00q").as_deref(), Some("A00"));
        assert_eq!(normalize_eco_base("e99").as_deref(), Some("E99"));
        assert_eq!(normalize_eco_base("X99"), None);
    }

    #[test]
    fn classifies_lumbras_source_groups() {
        assert_eq!(classify_source_group("LumbrasGigaBase_OTB_2025.pgn"), "otb");
        assert_eq!(
            classify_source_group("LumbrasGigaBase_Online_2025.pgn"),
            "online"
        );
        assert_eq!(classify_source_group("other.pgn"), "unknown");
    }

    #[test]
    fn json_escapes_strings() {
        assert_eq!(json_string("a\"b\\c\n"), "\"a\\\"b\\\\c\\n\"");
    }
}
