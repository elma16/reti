//! `lint` subcommand: report (don't fix) issues in a PGN file.
//!
//! Checks fall into three buckets:
//!   structural   – missing STR tags, malformed Date, unbalanced { } / ( ),
//!                  empty or unterminated games
//!   consistency  – Result header vs trailing result token; PlyCount vs
//!                  actual ply count
//!   legality     – SAN moves replay successfully against `shakmaty` from
//!                  the start position (or the position in [FEN] if present)
//!
//! `lint` is read-only by design; use `clean` to fix.

use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use shakmaty::{
    fen::Fen, san::SanPlus, CastlingMode, Chess, EnPassantMode, Position,
};

use crate::pgn_split::{normalize_movetext, Game, GameSplitter};
use crate::progress::ProgressReporter;

#[derive(Debug, Clone)]
pub struct LintIssue {
    pub game_index: usize,
    pub start_line: usize,
    pub code: &'static str,
    pub message: String,
}

#[derive(Debug, Default, Clone)]
pub struct LintReport {
    pub games_checked: usize,
    pub issues: Vec<LintIssue>,
}

impl LintReport {
    pub fn to_json(&self) -> String {
        let mut s = String::with_capacity(64 + self.issues.len() * 96);
        s.push('{');
        s.push_str(&format!("\"games_checked\":{},", self.games_checked));
        s.push_str(&format!("\"issues_found\":{},", self.issues.len()));
        s.push_str("\"issues\":[");
        for (i, issue) in self.issues.iter().enumerate() {
            if i > 0 {
                s.push(',');
            }
            s.push('{');
            s.push_str(&format!("\"game_index\":{},", issue.game_index));
            s.push_str(&format!("\"line\":{},", issue.start_line));
            s.push_str(&format!("\"code\":\"{}\",", issue.code));
            s.push_str(&format!(
                "\"message\":\"{}\"",
                escape_json_string(&issue.message)
            ));
            s.push('}');
        }
        s.push_str("]}");
        s
    }

    pub fn write_human<W: Write>(&self, file_label: &str, mut out: W) -> io::Result<()> {
        for issue in &self.issues {
            writeln!(
                out,
                "{}:{}: [{}] (game #{}) {}",
                file_label, issue.start_line, issue.code, issue.game_index, issue.message
            )?;
        }
        writeln!(
            out,
            "summary: checked {} game(s), found {} issue(s)",
            self.games_checked,
            self.issues.len()
        )?;
        Ok(())
    }
}

fn escape_json_string(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 4);
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

pub fn run_lint(
    input_path: &Path,
    json: bool,
    show_progress: bool,
) -> io::Result<LintReport> {
    let total_bytes = fs::metadata(input_path)?.len();
    let progress = ProgressReporter::bytes(total_bytes, "lint", show_progress);

    let file = File::open(input_path)?;
    let reader = BufReader::new(progress.wrap(file));

    let report = lint_stream(reader)?;

    let label = input_path.display().to_string();
    if json {
        println!("{}", report.to_json());
    } else {
        report.write_human(&label, io::stdout().lock())?;
    }
    progress.finish("lint done");
    Ok(report)
}

pub fn lint_stream<R: BufRead>(reader: R) -> io::Result<LintReport> {
    let mut report = LintReport::default();
    for (idx, game) in GameSplitter::new(reader).enumerate() {
        let game = game?;
        report.games_checked += 1;
        check_game(idx + 1, &game, &mut report.issues);
    }
    Ok(report)
}

const STR_TAGS: [&str; 7] = ["Event", "Site", "Date", "Round", "White", "Black", "Result"];

fn check_game(idx: usize, game: &Game, issues: &mut Vec<LintIssue>) {
    let mut push = |code: &'static str, message: String| {
        issues.push(LintIssue {
            game_index: idx,
            start_line: game.start_line,
            code,
            message,
        });
    };

    // 1. Seven Tag Roster presence.
    for tag in STR_TAGS {
        if game.header(tag).is_none() {
            push("missing-tag", format!("missing required header [{tag} ...]"));
        }
    }

    // 2. Date format (YYYY.MM.DD with `?` permitted).
    if let Some(date) = game.header("Date") {
        if !is_valid_pgn_date(&date) {
            push(
                "bad-date",
                format!("Date \"{date}\" is not in YYYY.MM.DD form"),
            );
        }
    }

    // 3. Result header value.
    let header_result = game.header("Result");
    if let Some(ref r) = header_result {
        if !is_valid_result(r) {
            push(
                "bad-result",
                format!("Result \"{r}\" is not one of 1-0, 0-1, 1/2-1/2, *"),
            );
        }
    }

    let movetext = game.movetext();

    // 4. Result-header / movetext-result mismatch.
    let trailing_result = trailing_result_token(movetext);
    if let (Some(ref h), Some(ref t)) = (&header_result, &trailing_result) {
        if h != t {
            push(
                "result-mismatch",
                format!("Result header \"{h}\" does not match movetext result \"{t}\""),
            );
        }
    }

    // 5. Bracket balance in movetext.
    let (brace_diff, paren_diff) = bracket_balance(movetext);
    if brace_diff != 0 {
        push(
            "unbalanced-brace",
            format!("unbalanced brace comments (diff = {brace_diff})"),
        );
    }
    if paren_diff != 0 {
        push(
            "unbalanced-paren",
            format!("unbalanced parenthesised variations (diff = {paren_diff})"),
        );
    }

    // 6. Empty game.
    let normalized = normalize_movetext(movetext);
    if normalized.is_empty() {
        push("empty-movetext", "game has no SAN moves".to_string());
    }

    // 7. No result token in movetext.
    if !normalized.is_empty() && trailing_result.is_none() {
        push(
            "no-result-token",
            "movetext does not end with 1-0, 0-1, 1/2-1/2, or *".to_string(),
        );
    }

    // 8. Move legality: replay all SAN moves through shakmaty.
    if !normalized.is_empty() {
        if let Some(err) = check_move_legality(game, &normalized) {
            push("illegal-move", err);
        }
    }

    // 9. PlyCount consistency.
    if let Some(pc) = game.header("PlyCount") {
        if let Ok(declared) = pc.trim().parse::<usize>() {
            let actual = san_token_count(&normalized);
            if declared != actual {
                push(
                    "plycount-mismatch",
                    format!("PlyCount header is {declared} but movetext has {actual} ply"),
                );
            }
        } else {
            push(
                "bad-plycount",
                format!("PlyCount \"{pc}\" is not an integer"),
            );
        }
    }
}

fn is_valid_pgn_date(date: &str) -> bool {
    let parts: Vec<&str> = date.split('.').collect();
    if parts.len() != 3 {
        return false;
    }
    let widths = [4, 2, 2];
    for (i, p) in parts.iter().enumerate() {
        if p.len() != widths[i] {
            return false;
        }
        if !p.chars().all(|c| c.is_ascii_digit() || c == '?') {
            return false;
        }
    }
    true
}

fn is_valid_result(r: &str) -> bool {
    matches!(r, "1-0" | "0-1" | "1/2-1/2" | "*")
}

/// Walk the movetext picking out the *last* token that looks like a result.
fn trailing_result_token(movetext: &[u8]) -> Option<String> {
    // Strip comments / variations / line comments, then look at the last
    // whitespace-separated token.
    let normalized = strip_markup(movetext);
    let s = std::str::from_utf8(&normalized).ok()?;
    let last = s.split_whitespace().last()?;
    if is_valid_result(last) {
        Some(last.to_string())
    } else {
        None
    }
}

fn strip_markup(movetext: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(movetext.len());
    let mut depth = 0usize;
    let mut in_brace = false;
    let mut skip_eol = false;
    let mut i = 0usize;
    while i < movetext.len() {
        let c = movetext[i];
        if skip_eol {
            if c == b'\n' {
                skip_eol = false;
            }
            i += 1;
            continue;
        }
        if in_brace {
            if c == b'}' {
                in_brace = false;
            }
            i += 1;
            continue;
        }
        if depth > 0 {
            match c {
                b'(' => depth += 1,
                b')' => depth -= 1,
                b'{' => in_brace = true,
                _ => {}
            }
            i += 1;
            continue;
        }
        match c {
            b'{' => in_brace = true,
            b'(' => depth = 1,
            b';' => skip_eol = true,
            b'%' if i == 0 || movetext[i - 1] == b'\n' => skip_eol = true,
            _ => out.push(c),
        }
        i += 1;
    }
    out
}

fn bracket_balance(movetext: &[u8]) -> (i64, i64) {
    let mut br: i64 = 0;
    let mut pr: i64 = 0;
    let mut skip_eol = false;
    let mut i = 0usize;
    while i < movetext.len() {
        let c = movetext[i];
        if skip_eol {
            if c == b'\n' {
                skip_eol = false;
            }
            i += 1;
            continue;
        }
        match c {
            b'{' => br += 1,
            b'}' => br -= 1,
            b'(' => pr += 1,
            b')' => pr -= 1,
            b';' => skip_eol = true,
            b'%' if i == 0 || movetext[i - 1] == b'\n' => skip_eol = true,
            _ => {}
        }
        i += 1;
    }
    (br, pr)
}

fn san_token_count(normalized: &[u8]) -> usize {
    if normalized.is_empty() {
        return 0;
    }
    normalized.iter().filter(|&&b| b == b' ').count() + 1
}

/// Returns Some(error_message) on first illegal move; None if all legal.
fn check_move_legality(game: &Game, normalized: &[u8]) -> Option<String> {
    let mut pos: Chess = match game.header("FEN") {
        Some(fen_str) => match Fen::from_ascii(fen_str.as_bytes()) {
            Ok(fen) => match fen.into_position(CastlingMode::Standard) {
                Ok(p) => p,
                Err(e) => return Some(format!("could not load [FEN]: {e}")),
            },
            Err(e) => return Some(format!("could not parse [FEN \"{fen_str}\"]: {e}")),
        },
        None => Chess::default(),
    };

    let s = std::str::from_utf8(normalized).ok()?;
    for (i, tok) in s.split_whitespace().enumerate() {
        let san = match SanPlus::from_ascii(tok.as_bytes()) {
            Ok(s) => s,
            Err(e) => {
                return Some(format!(
                    "ply {} (\"{tok}\"): could not parse as SAN: {e}",
                    i + 1
                ))
            }
        };
        let mv = match san.san.to_move(&pos) {
            Ok(m) => m,
            Err(_) => {
                return Some(format!(
                    "ply {} (\"{tok}\"): not a legal move in position {}",
                    i + 1,
                    Fen(pos.into_setup(EnPassantMode::Legal))
                ))
            }
        };
        pos = match pos.play(&mv) {
            Ok(p) => p,
            Err(_) => {
                return Some(format!(
                    "ply {} (\"{tok}\"): play() rejected the move",
                    i + 1
                ))
            }
        };
    }
    None
}

/// Returns the desired process exit code: 0 if no issues, 2 if issues found.
pub fn run_subcommand(args: &[OsString]) -> Result<i32, String> {
    let parsed = crate::cli::parse(args, &[], &[]).map_err(|e| e.to_string())?;
    if parsed.positionals.len() != 1 {
        return Err("lint: expected exactly one input path".to_string());
    }
    let input: PathBuf = parsed.positionals[0].clone();
    let report = run_lint(&input, parsed.global.json, !parsed.global.no_progress)
        .map_err(|e| format!("lint failed: {e}"))?;
    Ok(if report.issues.is_empty() { 0 } else { 2 })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn lint(pgn: &[u8]) -> LintReport {
        lint_stream(Cursor::new(pgn)).unwrap()
    }

    #[test]
    fn flags_missing_seven_tag_roster_entries() {
        let pgn = b"[Event \"x\"]\n\n1. e4 e5 1-0\n";
        let report = lint(pgn);
        let codes: Vec<&str> = report.issues.iter().map(|i| i.code).collect();
        assert!(codes.contains(&"missing-tag"));
        let missing: Vec<_> = report
            .issues
            .iter()
            .filter(|i| i.code == "missing-tag")
            .map(|i| i.message.clone())
            .collect();
        assert!(missing.iter().any(|m| m.contains("[Site")));
        assert!(missing.iter().any(|m| m.contains("[White")));
    }

    #[test]
    fn flags_result_mismatch() {
        let pgn = b"[Event \"x\"]\n[Site \"x\"]\n[Date \"2024.01.01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"1-0\"]\n\n1. e4 e5 0-1\n";
        let report = lint(pgn);
        assert!(report.issues.iter().any(|i| i.code == "result-mismatch"));
    }

    #[test]
    fn passes_a_clean_game() {
        let pgn = b"[Event \"x\"]\n[Site \"x\"]\n[Date \"2024.01.01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"1-0\"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n";
        let report = lint(pgn);
        assert!(report.issues.is_empty(), "unexpected issues: {:?}", report.issues);
    }

    #[test]
    fn flags_illegal_san_move() {
        // 1. e9 isn't legal.
        let pgn = b"[Event \"x\"]\n[Site \"x\"]\n[Date \"2024.01.01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"*\"]\n\n1. e9 *\n";
        let report = lint(pgn);
        assert!(
            report.issues.iter().any(|i| i.code == "illegal-move"),
            "expected illegal-move issue, got {:?}",
            report.issues
        );
    }

    #[test]
    fn flags_unbalanced_brace() {
        let pgn = b"[Event \"x\"]\n[Site \"x\"]\n[Date \"2024.01.01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"1-0\"]\n\n1. e4 {oops e5 1-0\n";
        let report = lint(pgn);
        assert!(report.issues.iter().any(|i| i.code == "unbalanced-brace"));
    }

    #[test]
    fn flags_bad_date() {
        let pgn = b"[Event \"x\"]\n[Site \"x\"]\n[Date \"24-01-01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"1-0\"]\n\n1. e4 1-0\n";
        let report = lint(pgn);
        assert!(report.issues.iter().any(|i| i.code == "bad-date"));
    }

    #[test]
    fn allows_question_marks_in_date() {
        assert!(is_valid_pgn_date("2024.01.01"));
        assert!(is_valid_pgn_date("????.??.??"));
        assert!(is_valid_pgn_date("1992.??.??"));
        assert!(!is_valid_pgn_date("1992-01-01"));
        assert!(!is_valid_pgn_date("92.01.01"));
    }

    #[test]
    fn json_serialization_round_trips_basic_shape() {
        let pgn = b"[Event \"x\"]\n\n1. e4 1-0\n";
        let report = lint(pgn);
        let s = report.to_json();
        assert!(s.starts_with('{'));
        assert!(s.contains("\"games_checked\":1"));
        assert!(s.contains("\"issues\":["));
    }
}
