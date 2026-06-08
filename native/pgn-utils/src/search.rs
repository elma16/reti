//! `grep` subcommand: find games whose header fields match a query, and emit
//! the whole matching games as PGN.
//!
//!   pgn-utils grep --player "Carlsen, Magnus" DIR... [-o OUT]
//!   pgn-utils grep --white Kasparov --year-min 1990 --year-max 1995 db.pgn
//!   pgn-utils grep --event "World Championship" --tag ECO=B90 .
//!
//! Inputs are files, directories (walked for `*.pgn`), or `-` for stdin.
//! Matching is token-based with case and accent folding: every whitespace word
//! of the query must appear (as a substring) in the field, in any order — so
//! `"Magnus Carlsen"` and `"Carlsen, Magnus"` both match `[White "Carlsen,
//! Magnus"]`, and `muller` matches `Müller`. `--player` matches White OR Black;
//! every other supplied filter must also match (AND).
//!
//! Speed: when `ripgrep` (`rg`) is on PATH and the query has a selective word,
//! it is used to skip files that cannot contain a match (using an
//! accent-permissive pattern that never drops a real match); the precise
//! matching is always done natively. `--no-prefilter` forces a plain native
//! scan. Without `rg`, it falls back to scanning every file natively.

use std::ffi::OsString;
use std::io::{self, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};

use crate::pgn_split::{Game, GameSplitter};
use crate::progress::ProgressReporter;

// ---- accent / case folding ---------------------------------------------- //

/// Map a single lowercase char to its ASCII fold (e.g. `ü` -> `u`, `ß` -> `ss`),
/// or `None` if it has no special fold and should pass through unchanged.
fn fold_accent(c: char) -> Option<&'static str> {
    Some(match c {
        'à' | 'á' | 'â' | 'ã' | 'ä' | 'å' | 'ā' | 'ă' | 'ą' => "a",
        'æ' => "ae",
        'ç' | 'ć' | 'č' | 'ċ' | 'ĉ' => "c",
        'ð' | 'ď' | 'đ' => "d",
        'è' | 'é' | 'ê' | 'ë' | 'ē' | 'ĕ' | 'ė' | 'ę' | 'ě' => "e",
        'ĝ' | 'ğ' | 'ġ' | 'ģ' => "g",
        'ĥ' | 'ħ' => "h",
        'ì' | 'í' | 'î' | 'ï' | 'ī' | 'ĭ' | 'į' | 'ı' => "i",
        'ĵ' => "j",
        'ķ' => "k",
        'ł' | 'ľ' | 'ĺ' | 'ļ' | 'ŀ' => "l",
        'ñ' | 'ń' | 'ň' | 'ņ' | 'ŋ' => "n",
        'ò' | 'ó' | 'ô' | 'õ' | 'ö' | 'ø' | 'ō' | 'ŏ' | 'ő' => "o",
        'œ' => "oe",
        'ŕ' | 'ř' | 'ŗ' => "r",
        'ś' | 'š' | 'ş' | 'ș' | 'ŝ' => "s",
        'ß' => "ss",
        'ť' | 'ţ' | 'ț' | 'ŧ' => "t",
        'ù' | 'ú' | 'û' | 'ü' | 'ū' | 'ŭ' | 'ů' | 'ű' | 'ų' => "u",
        'ŵ' => "w",
        'ý' | 'ÿ' | 'ŷ' => "y",
        'ź' | 'ž' | 'ż' => "z",
        _ => return None,
    })
}

/// Lowercase + strip diacritics so comparison is case- and accent-insensitive.
/// Combining marks (U+0300..U+036F) are dropped so decomposed input folds too.
pub fn fold(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        for lc in c.to_lowercase() {
            if ('\u{300}'..='\u{36f}').contains(&lc) {
                continue;
            }
            match fold_accent(lc) {
                Some(rep) => out.push_str(rep),
                None => out.push(lc),
            }
        }
    }
    out
}

/// Split a query into folded alphanumeric tokens (punctuation dropped), so
/// `"Carlsen, Magnus"` -> `["carlsen", "magnus"]`.
fn query_tokens(query: &str) -> Vec<String> {
    fold(query)
        .split(|c: char| !c.is_alphanumeric())
        .filter(|t| !t.is_empty())
        .map(|t| t.to_string())
        .collect()
}

/// True when every token appears as a substring of the folded field value.
fn field_matches(field: &str, tokens: &[String]) -> bool {
    if tokens.is_empty() {
        return false;
    }
    let folded = fold(field);
    tokens.iter().all(|t| folded.contains(t.as_str()))
}

// ---- filters ------------------------------------------------------------- //

#[derive(Debug, Default)]
pub struct Filters {
    player: Option<Vec<String>>,
    white: Option<Vec<String>>,
    black: Option<Vec<String>>,
    event: Option<Vec<String>>,
    site: Option<Vec<String>>,
    year_min: Option<i32>,
    year_max: Option<i32>,
    tags: Vec<(String, Vec<String>)>,
}

impl Filters {
    fn is_empty(&self) -> bool {
        self.player.is_none()
            && self.white.is_none()
            && self.black.is_none()
            && self.event.is_none()
            && self.site.is_none()
            && self.year_min.is_none()
            && self.year_max.is_none()
            && self.tags.is_empty()
    }

    pub fn matches(&self, game: &Game) -> bool {
        if let Some(tokens) = &self.player {
            let white_ok = game
                .header("White")
                .is_some_and(|v| field_matches(&v, tokens));
            let black_ok = game
                .header("Black")
                .is_some_and(|v| field_matches(&v, tokens));
            if !(white_ok || black_ok) {
                return false;
            }
        }
        for (key, tokens) in [
            ("White", &self.white),
            ("Black", &self.black),
            ("Event", &self.event),
            ("Site", &self.site),
        ] {
            if let Some(tokens) = tokens {
                if !game.header(key).is_some_and(|v| field_matches(&v, tokens)) {
                    return false;
                }
            }
        }
        if self.year_min.is_some() || self.year_max.is_some() {
            match game.header("Date").and_then(|d| parse_year(&d)) {
                Some(year) => {
                    if self.year_min.is_some_and(|m| year < m)
                        || self.year_max.is_some_and(|m| year > m)
                    {
                        return false;
                    }
                }
                None => return false,
            }
        }
        for (tag, tokens) in &self.tags {
            if !game.header(tag).is_some_and(|v| field_matches(&v, tokens)) {
                return false;
            }
        }
        true
    }

    /// The longest query token across the string filters (used to build the rg
    /// prefilter pattern). `None` when nothing selective enough exists.
    fn selective_token(&self) -> Option<&str> {
        [
            &self.player,
            &self.white,
            &self.black,
            &self.event,
            &self.site,
        ]
        .into_iter()
        .flatten()
        .flatten()
        .chain(self.tags.iter().flat_map(|(_, t)| t.iter()))
        .map(|s| s.as_str())
        .filter(|s| s.chars().count() >= 3)
        .max_by_key(|s| s.chars().count())
    }
}

/// Parse a 4-digit year from a PGN `Date` value (`YYYY.MM.DD`, `????` allowed).
fn parse_year(date: &str) -> Option<i32> {
    let head: String = date.chars().take(4).collect();
    head.parse::<i32>().ok()
}

// ---- rg prefilter -------------------------------------------------------- //

fn rg_available() -> bool {
    Command::new("rg")
        .arg("--version")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Accented codepoints that fold to a given ASCII letter (the inverse of
/// `fold_accent`); kept in sync with it by `fold_table_round_trips`.
fn accented_variants(c: char) -> &'static str {
    match c {
        'a' => "àáâãäåāăą",
        'c' => "çćčċĉ",
        'd' => "ðďđ",
        'e' => "èéêëēĕėęě",
        'g' => "ĝğġģ",
        'h' => "ĥħ",
        'i' => "ìíîïīĭįı",
        'j' => "ĵ",
        'k' => "ķ",
        'l' => "łľĺļŀ",
        'n' => "ñńňņŋ",
        'o' => "òóôõöøōŏő",
        'r' => "ŕřŗ",
        's' => "śšşșŝ",
        't' => "ťţțŧ",
        'u' => "ùúûüūŭůűų",
        'w' => "ŵ",
        'y' => "ýÿŷ",
        'z' => "źžż",
        _ => "",
    }
}

/// One regex char class for an ASCII letter `c`: the letter and its accented
/// variants, followed by optional combining marks (so decomposed input matches
/// too).
fn cls(c: char) -> String {
    format!("[{c}{}][\\x{{300}}-\\x{{36f}}]*", accented_variants(c))
}

/// Build an accent-permissive, case-insensitive regex that matches any text
/// whose accent fold contains `token`. Guaranteed to be a *superset* of the
/// native matcher, so an rg prefilter using it never drops a real match.
fn build_accent_pattern(token: &str) -> String {
    let bytes = token.as_bytes();
    let mut pat = String::new();
    let mut i = 0;
    while i < bytes.len() {
        let two = if i + 2 <= bytes.len() {
            &token[i..i + 2]
        } else {
            ""
        };
        match two {
            "ss" => {
                pat.push_str(&format!(
                    "(?:{}{}|ß[\\x{{300}}-\\x{{36f}}]*)",
                    cls('s'),
                    cls('s')
                ));
                i += 2;
            }
            "ae" => {
                pat.push_str(&format!(
                    "(?:{}{}|æ[\\x{{300}}-\\x{{36f}}]*)",
                    cls('a'),
                    cls('e')
                ));
                i += 2;
            }
            "oe" => {
                pat.push_str(&format!(
                    "(?:{}{}|œ[\\x{{300}}-\\x{{36f}}]*)",
                    cls('o'),
                    cls('e')
                ));
                i += 2;
            }
            _ => {
                let c = token[i..].chars().next().unwrap();
                if c.is_ascii_alphabetic() {
                    pat.push_str(&cls(c));
                } else {
                    // digit or other: literal
                    pat.push(c);
                }
                i += c.len_utf8();
            }
        }
    }
    pat
}

/// Run rg to keep only files that may contain `token`. Files for which rg
/// errors are kept (fail safe). Stdin markers are handled by the caller.
fn rg_prefilter(files: &[PathBuf], token: &str) -> io::Result<Vec<PathBuf>> {
    let pattern = build_accent_pattern(token);
    let mut keep: Vec<PathBuf> = Vec::new();
    for chunk in files.chunks(4000) {
        let mut cmd = Command::new("rg");
        cmd.arg("-l")
            .arg("-i")
            .arg("--no-config")
            .arg("-e")
            .arg(&pattern)
            .arg("--");
        for f in chunk {
            cmd.arg(f);
        }
        cmd.stdin(Stdio::null()).stderr(Stdio::null());
        let output = cmd.output()?;
        match output.status.code() {
            Some(0) => {
                for line in output.stdout.split(|&b| b == b'\n') {
                    if !line.is_empty() {
                        keep.push(PathBuf::from(String::from_utf8_lossy(line).into_owned()));
                    }
                }
            }
            Some(1) => {}                       // no matches in this chunk -> drop all
            _ => keep.extend_from_slice(chunk), // rg error -> keep (fail safe)
        }
    }
    Ok(keep)
}

// ---- driver -------------------------------------------------------------- //

#[derive(Debug, Default, Clone, Copy)]
pub struct SearchStats {
    pub files_scanned: usize,
    pub games_scanned: usize,
    pub matched: usize,
}

impl SearchStats {
    pub fn to_json(&self) -> String {
        format!(
            "{{\"files_scanned\":{},\"games_scanned\":{},\"matched\":{}}}",
            self.files_scanned, self.games_scanned, self.matched
        )
    }
}

fn emit_game<W: Write>(bytes: &[u8], out: &mut W) -> io::Result<()> {
    let mut end = bytes.len();
    while end > 0 {
        match bytes[end - 1] {
            b'\n' | b'\r' | b' ' | b'\t' => end -= 1,
            _ => break,
        }
    }
    out.write_all(&bytes[..end])?;
    out.write_all(b"\n\n")?;
    Ok(())
}

pub fn run_search(
    inputs: &[PathBuf],
    filters: &Filters,
    output: Option<&std::path::Path>,
    show_progress: bool,
    use_prefilter: bool,
) -> io::Result<(SearchStats, bool)> {
    // Resolve the destination first so the terminal-flood guard fires before
    // we walk directories or run the (potentially long) prefilter.
    let sink = crate::output::open_output(output, "grep")?;
    let stats_to_stderr = sink.stats_to_stderr;
    let mut writer = sink.writer;

    let all_files = crate::concat::expand_inputs(inputs)?;

    // The bar spans the whole input corpus so it is meaningful regardless of how
    // selective the query is. It is created before the prefilter and ticks on a
    // timer so it stays alive while ripgrep scans; files the prefilter rules out
    // are credited as soon as they are known.
    let has_stdin = all_files.iter().any(|p| crate::output::is_stdin_path(p));
    let file_size = |p: &PathBuf| std::fs::metadata(p).map(|m| m.len()).unwrap_or(0);
    let corpus_bytes: u64 = all_files
        .iter()
        .filter(|p| !crate::output::is_stdin_path(p))
        .map(file_size)
        .sum();
    let progress = ProgressReporter::maybe_bytes(
        if has_stdin { None } else { Some(corpus_bytes) },
        "grep",
        show_progress,
    );
    progress.enable_steady_tick();

    // Opt-in rg prefilter. The default is a plain native single-pass: it reads
    // each byte exactly once and advances the bar smoothly, which on a large
    // (disk-bound) corpus is both faster and far better feedback than scanning
    // everything with rg first. We keep `all_files`' (sorted) order so output
    // is deterministic; stdin markers always pass through (can't be pre-scanned).
    let files = if use_prefilter && filters.selective_token().is_some() && rg_available() {
        let token = filters.selective_token().unwrap();
        let real: Vec<PathBuf> = all_files
            .iter()
            .filter(|p| !crate::output::is_stdin_path(p))
            .cloned()
            .collect();
        let candidates: std::collections::HashSet<PathBuf> =
            rg_prefilter(&real, token)?.into_iter().collect();
        // Credit the bar for files the prefilter excludes (rg already read them).
        let skipped: u64 = real
            .iter()
            .filter(|p| !candidates.contains(*p))
            .map(file_size)
            .sum();
        progress.inc(skipped);
        all_files
            .into_iter()
            .filter(|p| crate::output::is_stdin_path(p) || candidates.contains(p))
            .collect()
    } else {
        all_files
    };

    let mut stats = SearchStats::default();
    for path in &files {
        let (reader, _len) = crate::output::open_input(path)?;
        let reader = BufReader::new(progress.wrap(reader));
        stats.files_scanned += 1;
        for game in GameSplitter::new(reader) {
            let game = game?;
            stats.games_scanned += 1;
            if filters.matches(&game) {
                stats.matched += 1;
                emit_game(&game.bytes, &mut writer)?;
            }
        }
    }

    writer.flush()?;
    progress.finish("grep done");
    Ok((stats, stats_to_stderr))
}

const USAGE: &str = "\
usage: pgn-utils grep [FILTERS] INPUT... [-o OUT]
filters (all AND together; values are token + accent/case folded):
  --player Q     White OR Black contains Q
  --white Q / --black Q / --event Q / --site Q
  --year YYYY    exact year (from Date); or --year-min / --year-max for a range
  --tag NAME=Q   any header tag (repeatable)
  --prefilter    use ripgrep to skip files that can't match before the native
                 scan (default: native single-pass; rg only helps a sparse
                 query over a warm, cached corpus)
INPUT may be files, directories, or - for stdin.";

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    let parsed = crate::cli::parse(
        args,
        &["prefilter"],
        &[
            "output", "o", "player", "white", "black", "event", "site", "year", "year-min",
            "year-max", "tag",
        ],
    )
    .map_err(|e| e.to_string())?;

    let kv_tokens = |name: &str| -> Option<Vec<String>> {
        parsed
            .get_kv(name)
            .map(|v| query_tokens(&v.to_string_lossy()))
    };
    let parse_year_arg = |name: &str| -> Result<Option<i32>, String> {
        match parsed.get_kv(name) {
            Some(v) => {
                let s = v.to_string_lossy();
                s.parse::<i32>()
                    .map(Some)
                    .map_err(|_| format!("grep: --{name} must be a year, got {s:?}"))
            }
            None => Ok(None),
        }
    };

    let mut year_min = parse_year_arg("year-min")?;
    let mut year_max = parse_year_arg("year-max")?;
    if let Some(y) = parse_year_arg("year")? {
        year_min = Some(y);
        year_max = Some(y);
    }

    // Collect every --tag NAME=VALUE (repeatable).
    let mut tags: Vec<(String, Vec<String>)> = Vec::new();
    for (key, value) in &parsed.kv_flags {
        if key == "tag" {
            let raw = value.to_string_lossy();
            let (name, query) = raw
                .split_once('=')
                .ok_or_else(|| format!("grep: --tag expects NAME=VALUE, got {raw:?}"))?;
            tags.push((name.to_string(), query_tokens(query)));
        }
    }

    let filters = Filters {
        player: kv_tokens("player"),
        white: kv_tokens("white"),
        black: kv_tokens("black"),
        event: kv_tokens("event"),
        site: kv_tokens("site"),
        year_min,
        year_max,
        tags,
    };

    if filters.is_empty() {
        return Err(format!("grep: no filters supplied\n{USAGE}"));
    }
    if parsed.positionals.is_empty() {
        return Err(format!("grep: no input paths supplied\n{USAGE}"));
    }

    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);

    let (stats, stats_to_stderr) = run_search(
        &parsed.positionals,
        &filters,
        output.as_deref(),
        !parsed.global.no_progress,
        parsed.has_flag("prefilter"),
    )
    .map_err(|e| format!("grep failed: {e}"))?;

    crate::output::print_stats(&stats.to_json(), stats_to_stderr);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn game(headers: &str) -> Game {
        // GameSplitter starts a game at the `[Event ` line, so ensure one leads.
        let body = if headers.trim_start().starts_with("[Event ") {
            format!("{headers}\n\n1. e4 e5 1-0\n")
        } else {
            format!("[Event \"Test\"]\n{headers}\n\n1. e4 e5 1-0\n")
        };
        GameSplitter::new(Cursor::new(body.into_bytes()))
            .next()
            .unwrap()
            .unwrap()
    }

    fn filters_player(q: &str) -> Filters {
        Filters {
            player: Some(query_tokens(q)),
            ..Default::default()
        }
    }

    #[test]
    fn fold_lowercases_and_strips_accents() {
        assert_eq!(fold("Müller"), "muller");
        assert_eq!(fold("Étienne"), "etienne");
        assert_eq!(fold("Straße"), "strasse");
        assert_eq!(fold("Łukasz"), "lukasz");
        assert_eq!(fold("Réti"), "reti");
    }

    #[test]
    fn name_order_independent_and_accent_insensitive() {
        let g = game("[White \"Carlsen, Magnus\"]\n[Black \"Müller, Hans\"]");
        assert!(filters_player("Magnus Carlsen").matches(&g));
        assert!(filters_player("Carlsen, Magnus").matches(&g));
        assert!(filters_player("muller").matches(&g)); // accent-folded, Black side
        assert!(!filters_player("Kasparov").matches(&g));
    }

    #[test]
    fn white_and_black_filters_are_specific() {
        let g = game("[White \"Carlsen, Magnus\"]\n[Black \"Nepomniachtchi, Ian\"]");
        let white_only = Filters {
            white: Some(query_tokens("carlsen")),
            ..Default::default()
        };
        assert!(white_only.matches(&g));
        let black_carlsen = Filters {
            black: Some(query_tokens("carlsen")),
            ..Default::default()
        };
        assert!(!black_carlsen.matches(&g));
    }

    #[test]
    fn year_range_filter() {
        let g = game("[Date \"1995.06.12\"]");
        let in_range = Filters {
            year_min: Some(1990),
            year_max: Some(2000),
            ..Default::default()
        };
        assert!(in_range.matches(&g));
        let after = Filters {
            year_min: Some(2000),
            ..Default::default()
        };
        assert!(!after.matches(&g));
    }

    #[test]
    fn tag_filter_and_combination_is_and() {
        let g = game("[Event \"Tata Steel\"]\n[White \"Carlsen, Magnus\"]\n[ECO \"B90\"]");
        let f = Filters {
            player: Some(query_tokens("carlsen")),
            event: Some(query_tokens("tata")),
            tags: vec![("ECO".to_string(), query_tokens("B90"))],
            ..Default::default()
        };
        assert!(f.matches(&g));
        let f_bad = Filters {
            player: Some(query_tokens("carlsen")),
            tags: vec![("ECO".to_string(), query_tokens("C99"))],
            ..Default::default()
        };
        assert!(!f_bad.matches(&g));
    }

    #[test]
    fn run_search_emits_matching_games_only() {
        let pgn = b"[Event \"x\"]\n[White \"Carlsen, Magnus\"]\n\n1. e4 e5 1-0\n\n[Event \"y\"]\n[White \"Kasparov, Garry\"]\n\n1. d4 d5 0-1\n";
        let dir = std::env::temp_dir().join(format!("pgn-grep-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join("g.pgn");
        std::fs::write(&file, pgn).unwrap();
        let out_path = dir.join("out.pgn");
        let f = filters_player("carlsen");
        let (stats, _) = run_search(
            std::slice::from_ref(&file),
            &f,
            Some(out_path.as_path()),
            false,
            false, // native single-pass (no rg prefilter)
        )
        .unwrap();
        assert_eq!(stats.games_scanned, 2);
        assert_eq!(stats.matched, 1);
        let written = std::fs::read_to_string(&out_path).unwrap();
        assert!(written.contains("Carlsen, Magnus"));
        assert!(!written.contains("Kasparov"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn fold_table_round_trips() {
        // Every accented char in `accented_variants` must fold to its letter,
        // keeping the native matcher and the rg pattern in sync (soundness).
        for letter in "acdeghijklnorstuwyz".chars() {
            for accented in accented_variants(letter).chars() {
                assert_eq!(
                    fold(&accented.to_string()),
                    letter.to_string(),
                    "{accented} should fold to {letter}"
                );
            }
        }
        // The multi-char folds.
        assert_eq!(fold("æ"), "ae");
        assert_eq!(fold("œ"), "oe");
        assert_eq!(fold("ß"), "ss");
    }

    #[test]
    fn accent_pattern_is_built_for_selective_token() {
        let f = filters_player("Carlsen");
        assert_eq!(f.selective_token(), Some("carlsen"));
        let pat = build_accent_pattern("muller");
        // Contains the accent class for 'u'.
        assert!(pat.contains('ü'), "pattern should allow ü: {pat}");
    }
}
