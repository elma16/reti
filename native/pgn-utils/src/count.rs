//! `count` subcommand: count games and break them down by header / derived
//! fields, printing an aligned text table.
//!
//!   pgn-utils count db.pgn                      # games per source file + total
//!   pgn-utils count --by year db.pgn            # games per year
//!   pgn-utils count --by Result .               # games per result
//!   pgn-utils count --by White --by year .      # cross-tab: white x year
//!   pgn-utils count --by eco-base --top 10 .    # 10 most common ECO families
//!
//! Inputs are files, directories (walked recursively for `*.pgn`), or a lone
//! `-` for stdin. A game is one `[Event ...]` boundary — the same definition
//! the other subcommands use, via the shared [`GameSplitter`].
//!
//! `--by FIELD` chooses a grouping dimension and may be repeated to build a
//! cross-tab (one table column per dimension, one row per distinct
//! combination). With no `--by` the games are grouped by source file, so the
//! bare command is a human-readable per-file tally. FIELD is one of the derived
//! keys `file`, `year`, `month`, `eco-base`, or any PGN tag name
//! (case-sensitive, e.g. `White`, `Event`, `Result`, `ECO`); a game that lacks
//! the field counts under `unknown`.
//!
//! Rows are sorted by count descending by default (`--sort key` for
//! alphabetical), with a trailing `TOTAL`. `--top N` keeps only the N largest
//! groups and prints how many were omitted (never a silent cap).

use std::collections::HashMap;
use std::ffi::OsString;
use std::io::{self, BufReader, Write};
use std::path::{Path, PathBuf};

use crate::pgn_split::{Game, GameSplitter};
use crate::progress::ProgressReporter;

// ---- grouping dimensions ------------------------------------------------- //

/// A single `--by` grouping dimension.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Dimension {
    File,
    Year,
    Month,
    EcoBase,
    /// Any literal PGN tag, matched case-sensitively like real PGN.
    Tag(String),
}

impl Dimension {
    /// Parse a `--by` value. The lowercase derived keys win; anything else is
    /// treated as a literal (case-sensitive) PGN tag name.
    fn parse(raw: &str) -> Dimension {
        match raw {
            "file" => Dimension::File,
            "year" => Dimension::Year,
            "month" => Dimension::Month,
            "eco-base" | "eco_base" | "ecobase" => Dimension::EcoBase,
            other => Dimension::Tag(other.to_string()),
        }
    }

    /// The column header shown for this dimension.
    fn label(&self) -> String {
        match self {
            Dimension::File => "FILE".to_string(),
            Dimension::Year => "YEAR".to_string(),
            Dimension::Month => "MONTH".to_string(),
            Dimension::EcoBase => "ECO".to_string(),
            Dimension::Tag(name) => name.to_uppercase(),
        }
    }

    /// This dimension's value for one game in a given file. Missing / invalid
    /// values bucket as `unknown`.
    fn value(&self, game: &Game, file_label: &str) -> String {
        let unknown = || "unknown".to_string();
        match self {
            Dimension::File => file_label.to_string(),
            Dimension::Year => game
                .header("Date")
                .and_then(|d| parse_year(&d))
                .unwrap_or_else(unknown),
            Dimension::Month => game
                .header("Date")
                .and_then(|d| parse_month(&d))
                .unwrap_or_else(unknown),
            Dimension::EcoBase => game
                .header("ECO")
                .and_then(|e| eco_base(&e))
                .unwrap_or_else(unknown),
            Dimension::Tag(name) => match game.header(name) {
                Some(v) if !v.is_empty() => v,
                _ => unknown(),
            },
        }
    }
}

/// Parse the 4-digit year from a PGN `Date` (`YYYY.MM.DD`); `None` when the
/// head isn't four digits (e.g. `????.??.??`).
fn parse_year(date: &str) -> Option<String> {
    let head: String = date.chars().take(4).collect();
    if head.len() == 4 && head.bytes().all(|b| b.is_ascii_digit()) {
        Some(head)
    } else {
        None
    }
}

/// Parse `YYYY-MM` from a PGN `Date` (`YYYY.MM.DD`); requires a 4-digit year,
/// a `.` separator, and a 2-digit month.
fn parse_month(date: &str) -> Option<String> {
    let year = parse_year(date)?;
    // After the 4 ASCII-digit year, byte index 4 is a valid char boundary.
    let mut rest = date.get(4..)?.chars();
    if rest.next() != Some('.') {
        return None;
    }
    let month: String = rest.take(2).collect();
    if month.len() == 2 && month.bytes().all(|b| b.is_ascii_digit()) {
        Some(format!("{year}-{month}"))
    } else {
        None
    }
}

/// Normalize an `ECO` tag value to its 3-character base (`B90a` -> `B90`), or
/// `None` if it isn't a valid `[A-E]dd` code. (Mirrors the same helper in
/// `source_totals`; the crate keeps such small helpers module-local on
/// purpose.)
fn eco_base(raw: &str) -> Option<String> {
    let raw = raw.trim();
    let mut chars = raw.chars();
    let family = chars.next()?.to_ascii_uppercase();
    let d1 = chars.next()?;
    let d2 = chars.next()?;
    if !matches!(family, 'A'..='E') || !d1.is_ascii_digit() || !d2.is_ascii_digit() {
        return None;
    }
    Some(format!("{family}{d1}{d2}"))
}

fn file_label(path: &Path) -> String {
    if crate::output::is_stdin_path(path) {
        "<stdin>".to_string()
    } else {
        path.display().to_string()
    }
}

// ---- counting ------------------------------------------------------------ //

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SortOrder {
    Count,
    Key,
}

#[derive(Debug, Clone)]
pub struct CountOptions {
    pub inputs: Vec<PathBuf>,
    by: Vec<Dimension>,
    sort: SortOrder,
    top: Option<usize>,
    show_progress: bool,
}

/// One output row: the key tuple (one entry per `--by` dimension) and its count.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CountRow {
    pub key: Vec<String>,
    pub games: usize,
}

/// The computed table, before formatting.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CountReport {
    /// Column headers, one per grouping dimension.
    pub headers: Vec<String>,
    /// Sorted rows, already truncated to `--top` if it was given.
    pub rows: Vec<CountRow>,
    /// Games scanned across all inputs (the true total, pre-truncation).
    pub total_games: usize,
    /// Distinct groups before truncation (so we can report what `--top` hid).
    pub total_groups: usize,
    pub files_scanned: usize,
}

pub fn run_count(opts: &CountOptions) -> io::Result<CountReport> {
    // No --by is sugar for grouping by source file.
    let dims: Vec<Dimension> = if opts.by.is_empty() {
        vec![Dimension::File]
    } else {
        opts.by.clone()
    };

    let files = crate::concat::expand_inputs(&opts.inputs)?;
    let has_stdin = files.iter().any(|p| crate::output::is_stdin_path(p));
    let corpus_bytes: u64 = files
        .iter()
        .filter(|p| !crate::output::is_stdin_path(p))
        .map(|p| std::fs::metadata(p).map(|m| m.len()).unwrap_or(0))
        .sum();
    let progress = ProgressReporter::maybe_bytes(
        if has_stdin { None } else { Some(corpus_bytes) },
        "count",
        opts.show_progress,
    );

    let mut counts: HashMap<Vec<String>, usize> = HashMap::new();
    let mut total_games = 0usize;
    let mut files_scanned = 0usize;

    for path in &files {
        let label = file_label(path);
        let (reader, _len) = crate::output::open_input(path)?;
        let reader = BufReader::new(progress.wrap(reader));
        files_scanned += 1;
        for game in GameSplitter::new(reader) {
            let game = game?;
            total_games += 1;
            let key: Vec<String> = dims.iter().map(|d| d.value(&game, &label)).collect();
            *counts.entry(key).or_insert(0) += 1;
        }
    }
    progress.finish("count done");

    let total_groups = counts.len();
    let mut rows: Vec<CountRow> = counts
        .into_iter()
        .map(|(key, games)| CountRow { key, games })
        .collect();

    match opts.sort {
        // Largest first; ties broken by key so output is deterministic.
        SortOrder::Count => {
            rows.sort_by(|a, b| b.games.cmp(&a.games).then_with(|| a.key.cmp(&b.key)))
        }
        SortOrder::Key => rows.sort_by(|a, b| a.key.cmp(&b.key)),
    }

    if let Some(top) = opts.top {
        rows.truncate(top);
    }

    Ok(CountReport {
        headers: dims.iter().map(|d| d.label()).collect(),
        rows,
        total_games,
        total_groups,
        files_scanned,
    })
}

// ---- rendering ----------------------------------------------------------- //

fn pad_right(s: &str, width: usize) -> String {
    let pad = width.saturating_sub(s.chars().count());
    let mut out = String::with_capacity(s.len() + pad);
    out.push_str(s);
    out.extend(std::iter::repeat_n(' ', pad));
    out
}

fn pad_left(s: &str, width: usize) -> String {
    let pad = width.saturating_sub(s.chars().count());
    let mut out = String::with_capacity(s.len() + pad);
    out.extend(std::iter::repeat_n(' ', pad));
    out.push_str(s);
    out
}

/// Render the report as an aligned table: key columns left-justified, the
/// `GAMES` column right-justified, a separator rule, and a `TOTAL` row.
pub fn render_table(report: &CountReport) -> String {
    const GAMES: &str = "GAMES";
    const TOTAL: &str = "TOTAL";
    let ncols = report.headers.len();

    // Key-column widths: header vs. every cell. The TOTAL label lives in col 0.
    let mut widths: Vec<usize> = report.headers.iter().map(|h| h.chars().count()).collect();
    for row in &report.rows {
        for (i, cell) in row.key.iter().enumerate() {
            widths[i] = widths[i].max(cell.chars().count());
        }
    }
    if let Some(first) = widths.first_mut() {
        *first = (*first).max(TOTAL.len());
    }

    // GAMES column: header vs. every count vs. the grand total.
    let mut games_width = GAMES.len();
    for row in &report.rows {
        games_width = games_width.max(row.games.to_string().len());
    }
    games_width = games_width.max(report.total_games.to_string().len());

    let rule_width: usize = widths.iter().sum::<usize>() + 2 * ncols + games_width;
    let mut out = String::new();

    let push_key_cols = |out: &mut String, cells: &[String]| {
        for (i, cell) in cells.iter().enumerate() {
            if i > 0 {
                out.push_str("  ");
            }
            out.push_str(&pad_right(cell, widths[i]));
        }
    };

    // Header.
    push_key_cols(&mut out, &report.headers);
    out.push_str("  ");
    out.push_str(&pad_left(GAMES, games_width));
    out.push('\n');
    out.push_str(&"-".repeat(rule_width));
    out.push('\n');

    // Data rows.
    for row in &report.rows {
        push_key_cols(&mut out, &row.key);
        out.push_str("  ");
        out.push_str(&pad_left(&row.games.to_string(), games_width));
        out.push('\n');
    }

    // Total: label in col 0, blanks for the remaining key columns.
    out.push_str(&"-".repeat(rule_width));
    out.push('\n');
    let mut total_cells: Vec<String> = vec![TOTAL.to_string()];
    total_cells.extend(std::iter::repeat_n(String::new(), ncols.saturating_sub(1)));
    push_key_cols(&mut out, &total_cells);
    out.push_str("  ");
    out.push_str(&pad_left(&report.total_games.to_string(), games_width));
    out.push('\n');

    out
}

// ---- CLI ----------------------------------------------------------------- //

const USAGE: &str = "\
usage: pgn-utils count [--by FIELD]... [--sort count|key] [--top N] INPUT...

Count games (one [Event ...] boundary = one game) across files, directories
(walked for *.pgn), or - for stdin, and print an aligned table.

options:
  --by FIELD     grouping dimension; repeat for a cross-tab. With no --by,
                 games are grouped by source file. FIELD is a derived key:
                 file, year, month, eco-base; or any PGN tag name
                 (case-sensitive), e.g. White, Black, Event, Result, ECO.
                 A game missing the field counts under \"unknown\".
  --sort ORDER   count (default; largest first) or key (alphabetical)
  --top N        show only the N largest groups; note how many were omitted
  --no-progress  disable the stderr progress bar";

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    if args.iter().any(|a| {
        let t = a.to_string_lossy();
        t == "--help" || t == "-h" || t == "help"
    }) {
        println!("{USAGE}");
        return Ok(());
    }

    let parsed = crate::cli::parse(args, &[], &["by", "sort", "top"]).map_err(|e| e.to_string())?;

    if parsed.global.json {
        return Err("count: --json is not supported; count prints a text table".to_string());
    }
    if parsed.positionals.is_empty() {
        return Err(format!("count: no input paths supplied\n{USAGE}"));
    }

    // Collect every --by (repeatable), preserving left-to-right order.
    let by: Vec<Dimension> = parsed
        .kv_flags
        .iter()
        .filter(|(k, _)| k == "by")
        .map(|(_, v)| Dimension::parse(&v.to_string_lossy()))
        .collect();

    let sort = match parsed
        .get_kv("sort")
        .map(|v| v.to_string_lossy().into_owned())
    {
        None => SortOrder::Count,
        Some(s) if s == "count" => SortOrder::Count,
        Some(s) if s == "key" => SortOrder::Key,
        Some(s) => {
            return Err(format!(
                "count: --sort must be 'count' or 'key', got {s:?}\n{USAGE}"
            ))
        }
    };

    let top = match parsed.get_kv("top") {
        None => None,
        Some(v) => {
            let s = v.to_string_lossy();
            let n: usize = s
                .parse()
                .map_err(|_| format!("count: --top must be a non-negative integer, got {s:?}"))?;
            Some(n)
        }
    };

    let opts = CountOptions {
        inputs: parsed.positionals.clone(),
        by,
        sort,
        top,
        show_progress: !parsed.global.no_progress,
    };

    let report = run_count(&opts).map_err(|e| format!("count failed: {e}"))?;

    let render = |out: &mut dyn Write| -> io::Result<()> {
        out.write_all(render_table(&report).as_bytes())?;
        if let Some(top) = opts.top {
            if report.total_groups > top {
                let hidden = report.total_groups - top;
                let plural = if hidden == 1 { "" } else { "s" };
                writeln!(
                    out,
                    "... {hidden} more group{plural} not shown (of {} total; --top {top})",
                    report.total_groups
                )?;
            }
        }
        out.flush()
    };
    let mut out = io::stdout().lock();
    render(&mut out).map_err(|e| format!("count failed: {e}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn games(pgn: &[u8]) -> Vec<Game> {
        GameSplitter::new(Cursor::new(pgn.to_vec()))
            .collect::<io::Result<Vec<_>>>()
            .unwrap()
    }

    #[test]
    fn parses_derived_and_tag_dimensions() {
        assert_eq!(Dimension::parse("file"), Dimension::File);
        assert_eq!(Dimension::parse("year"), Dimension::Year);
        assert_eq!(Dimension::parse("eco-base"), Dimension::EcoBase);
        assert_eq!(
            Dimension::parse("White"),
            Dimension::Tag("White".to_string())
        );
    }

    #[test]
    fn year_and_month_parsing() {
        assert_eq!(parse_year("2021.12.10").as_deref(), Some("2021"));
        assert_eq!(parse_year("????.??.??"), None);
        assert_eq!(parse_year("21.1.1"), None);
        assert_eq!(parse_month("2021.12.10").as_deref(), Some("2021-12"));
        assert_eq!(parse_month("2021.??.??"), None);
    }

    #[test]
    fn eco_base_normalizes() {
        assert_eq!(eco_base("B90a").as_deref(), Some("B90"));
        assert_eq!(eco_base("c42").as_deref(), Some("C42"));
        assert_eq!(eco_base("Z99"), None);
        assert_eq!(eco_base("?"), None);
    }

    #[test]
    fn dimension_value_buckets_missing_as_unknown() {
        let g = &games(b"[Event \"x\"]\n[White \"Carlsen, Magnus\"]\n\n1. e4 1-0\n")[0];
        assert_eq!(
            Dimension::Tag("White".into()).value(g, "f"),
            "Carlsen, Magnus"
        );
        assert_eq!(Dimension::Tag("Black".into()).value(g, "f"), "unknown");
        assert_eq!(Dimension::Year.value(g, "f"), "unknown");
        assert_eq!(Dimension::File.value(g, "f.pgn"), "f.pgn");
    }

    fn count(pgn: &[u8], by: Vec<Dimension>, sort: SortOrder, top: Option<usize>) -> CountReport {
        // Drive the counting core directly over a single in-memory file by
        // faking the per-file loop the way run_count does.
        let dims = if by.is_empty() {
            vec![Dimension::File]
        } else {
            by
        };
        let mut counts: HashMap<Vec<String>, usize> = HashMap::new();
        let mut total = 0usize;
        for game in games(pgn) {
            total += 1;
            let key: Vec<String> = dims.iter().map(|d| d.value(&game, "mem.pgn")).collect();
            *counts.entry(key).or_insert(0) += 1;
        }
        let total_groups = counts.len();
        let mut rows: Vec<CountRow> = counts
            .into_iter()
            .map(|(key, games)| CountRow { key, games })
            .collect();
        match sort {
            SortOrder::Count => {
                rows.sort_by(|a, b| b.games.cmp(&a.games).then_with(|| a.key.cmp(&b.key)))
            }
            SortOrder::Key => rows.sort_by(|a, b| a.key.cmp(&b.key)),
        }
        if let Some(t) = top {
            rows.truncate(t);
        }
        CountReport {
            headers: dims.iter().map(|d| d.label()).collect(),
            rows,
            total_games: total,
            total_groups,
            files_scanned: 1,
        }
    }

    const SAMPLE: &[u8] =
        b"[Event \"a\"]\n[Result \"1-0\"]\n[Date \"2021.01.02\"]\n\n1. e4 1-0\n\n\
[Event \"b\"]\n[Result \"0-1\"]\n[Date \"2021.05.06\"]\n\n1. d4 0-1\n\n\
[Event \"c\"]\n[Result \"1-0\"]\n[Date \"2020.07.08\"]\n\n1. c4 1-0\n";

    #[test]
    fn groups_by_result_sorted_by_count() {
        let r = count(
            SAMPLE,
            vec![Dimension::Tag("Result".into())],
            SortOrder::Count,
            None,
        );
        assert_eq!(r.total_games, 3);
        assert_eq!(r.headers, vec!["RESULT"]);
        // 1-0 (2) before 0-1 (1).
        assert_eq!(
            r.rows[0],
            CountRow {
                key: vec!["1-0".into()],
                games: 2
            }
        );
        assert_eq!(
            r.rows[1],
            CountRow {
                key: vec!["0-1".into()],
                games: 1
            }
        );
    }

    #[test]
    fn groups_by_year_sorted_by_key() {
        let r = count(SAMPLE, vec![Dimension::Year], SortOrder::Key, None);
        assert_eq!(
            r.rows,
            vec![
                CountRow {
                    key: vec!["2020".into()],
                    games: 1
                },
                CountRow {
                    key: vec!["2021".into()],
                    games: 2
                },
            ]
        );
    }

    #[test]
    fn cross_tab_uses_one_column_per_dimension() {
        let r = count(
            SAMPLE,
            vec![Dimension::Year, Dimension::Tag("Result".into())],
            SortOrder::Key,
            None,
        );
        assert_eq!(r.headers, vec!["YEAR", "RESULT"]);
        // Three distinct (year, result) combinations.
        assert_eq!(r.rows.len(), 3);
        assert!(r.rows.contains(&CountRow {
            key: vec!["2021".into(), "1-0".into()],
            games: 1
        }));
        assert!(r.rows.contains(&CountRow {
            key: vec!["2020".into(), "1-0".into()],
            games: 1
        }));
    }

    #[test]
    fn top_truncates_but_total_stays_whole() {
        let r = count(
            SAMPLE,
            vec![Dimension::Tag("Event".into())],
            SortOrder::Count,
            Some(1),
        );
        assert_eq!(r.rows.len(), 1);
        assert_eq!(r.total_groups, 3);
        assert_eq!(r.total_games, 3);
    }

    #[test]
    fn render_table_aligns_and_totals() {
        let report = CountReport {
            headers: vec!["RESULT".into()],
            rows: vec![
                CountRow {
                    key: vec!["1-0".into()],
                    games: 2,
                },
                CountRow {
                    key: vec!["0-1".into()],
                    games: 1,
                },
            ],
            total_games: 3,
            total_groups: 2,
            files_scanned: 1,
        };
        let table = render_table(&report);
        let lines: Vec<&str> = table.lines().collect();
        assert_eq!(lines[0], "RESULT  GAMES");
        assert_eq!(lines[2], "1-0         2");
        assert_eq!(lines[3], "0-1         1");
        assert_eq!(*lines.last().unwrap(), "TOTAL       3");
    }
}
