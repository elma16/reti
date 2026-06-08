//! `eco` subcommand: label games with their ECO opening classification.
//!
//! Each game is replayed with `shakmaty`; the resulting positions are matched
//! against an opening "book" built from `data/openings/lumbras_eco_codes.csv`
//! (embedded into the binary at compile time). Matching is position-based: the
//! deepest position the game reaches that is a known named opening wins, so
//! transpositions still classify. The game's `[ECO]` and `[Opening]` tags are
//! filled in; the movetext is emitted byte-for-byte unchanged, so `eco`
//! composes with `clean` (`pgn-utils clean in.pgn | pgn-utils eco - -o out.pgn`).
//!
//! By default only games that lack an `[ECO]` tag are classified; `--force`
//! recomputes and overwrites the `[ECO]`/`[Opening]` tags on every game.
//! Games with a non-standard start (`[FEN]`/`[SetUp "1"]`) are left untouched —
//! ECO is only defined from the standard initial position.

use std::collections::HashMap;
use std::ffi::OsString;
use std::fs;
use std::io::{self, BufReader, Write};
use std::path::PathBuf;

use shakmaty::{fen::Fen, san::SanPlus, Chess, EnPassantMode, Position};

use crate::pgn_split::{normalize_movetext, Game, GameSplitter};
use crate::progress::ProgressReporter;

/// The Lumbras ECO reference, bundled at compile time. Columns:
/// `row_number,eco,eco_base,eco_group,name,moves,source_url`.
const EMBEDDED_ECO_CSV: &str = include_str!("../../../data/openings/lumbras_eco_codes.csv");

/// What we attach to a game once classified.
#[derive(Debug, Clone)]
pub struct OpeningEntry {
    pub eco_base: String,
    pub name: String,
}

/// Position-keyed opening book: EPD (board, side, castling, en-passant) ->
/// the opening that names that position.
pub struct EcoBook {
    by_epd: HashMap<String, OpeningEntry>,
    /// Deepest reference line in plies; game replay stops here since no named
    /// position exists beyond it.
    max_ply: usize,
}

impl EcoBook {
    /// Build the book from the embedded Lumbras CSV.
    pub fn embedded() -> Self {
        Self::from_csv(EMBEDDED_ECO_CSV)
    }

    /// Build the book from CSV text in the Lumbras column layout. The first
    /// (header) line is skipped. Rows whose moves fail to replay are dropped.
    pub fn from_csv(csv: &str) -> Self {
        let mut by_epd: HashMap<String, OpeningEntry> = HashMap::new();
        let mut max_ply = 0usize;

        for line in csv.lines().skip(1) {
            if line.trim().is_empty() {
                continue;
            }
            let fields = parse_csv_line(line);
            // row_number, eco, eco_base, eco_group, name, moves, source_url
            if fields.len() < 6 {
                continue;
            }
            let eco_base = fields[2].trim();
            let name = fields[4].trim();
            let moves = fields[5].trim();
            if eco_base.is_empty() || moves.is_empty() {
                continue;
            }

            let normalized = normalize_movetext(moves.as_bytes());
            if let Some((epd, ply)) = replay_to_epd(&normalized) {
                max_ply = max_ply.max(ply);
                // Keep the first row (lowest row_number = main line) when two
                // lines transpose into the same position.
                by_epd.entry(epd).or_insert_with(|| OpeningEntry {
                    eco_base: eco_base.to_string(),
                    name: name.to_string(),
                });
            }
        }

        Self { by_epd, max_ply }
    }

    pub fn len(&self) -> usize {
        self.by_epd.len()
    }

    pub fn is_empty(&self) -> bool {
        self.by_epd.is_empty()
    }

    /// Classify a normalized SAN sequence, returning the deepest opening the
    /// game passes through. Replay stops at the first unparseable/illegal token
    /// (keeping the best match found so far) and at the book's max depth.
    pub fn classify(&self, normalized: &[u8]) -> Option<&OpeningEntry> {
        let s = std::str::from_utf8(normalized).ok()?;
        let mut pos = Chess::default();
        let mut best: Option<&OpeningEntry> = None;
        let mut ply = 0usize;

        for token in s.split_whitespace() {
            if ply >= self.max_ply {
                break;
            }
            let san_text = strip_leading_move_number(token);
            if san_text.is_empty() {
                continue;
            }
            let san = match SanPlus::from_ascii(san_text.as_bytes()) {
                Ok(s) => s,
                Err(_) => break,
            };
            let mv = match san.san.to_move(&pos) {
                Ok(m) => m,
                Err(_) => break,
            };
            pos = match pos.play(mv) {
                Ok(p) => p,
                Err(_) => break,
            };
            ply += 1;
            if let Some(entry) = self.by_epd.get(&epd_key(&pos)) {
                best = Some(entry);
            }
        }
        best
    }
}

/// Replay a normalized SAN sequence from the start position; return the
/// terminal EPD key and ply count, or None if any move is illegal/unparseable.
fn replay_to_epd(normalized: &[u8]) -> Option<(String, usize)> {
    let s = std::str::from_utf8(normalized).ok()?;
    let mut pos = Chess::default();
    let mut ply = 0usize;
    for token in s.split_whitespace() {
        let san_text = strip_leading_move_number(token);
        if san_text.is_empty() {
            continue;
        }
        let san = SanPlus::from_ascii(san_text.as_bytes()).ok()?;
        let mv = san.san.to_move(&pos).ok()?;
        pos = pos.play(mv).ok()?;
        ply += 1;
    }
    if ply == 0 {
        return None;
    }
    Some((epd_key(&pos), ply))
}

/// Strip a leading move-number prefix (`12.`, `12...`) from a movetext token.
/// The Lumbras reference and Lumbras-style PGNs glue the number to White's
/// move (`1.c4`); no real SAN token starts with a digit, so this is safe.
fn strip_leading_move_number(token: &str) -> &str {
    let bytes = token.as_bytes();
    let mut i = 0;
    while i < bytes.len() && bytes[i].is_ascii_digit() {
        i += 1;
    }
    if i == 0 {
        return token; // no leading digits -> already bare SAN
    }
    let digits_end = i;
    while i < bytes.len() && bytes[i] == b'.' {
        i += 1;
    }
    if i == digits_end {
        return token; // digits but no dot -> not a move number, leave untouched
    }
    &token[i..]
}

/// Position key for transposition matching: the first four FEN fields (board,
/// side to move, castling rights, en-passant square), dropping the move
/// counters. `EnPassantMode::Legal` only records an en-passant square when a
/// capture is actually available, which is the conventional opening-book key.
fn epd_key(pos: &Chess) -> String {
    let fen = Fen::from_position(pos, EnPassantMode::Legal).to_string();
    let mut fields = fen.split(' ');
    let board = fields.next().unwrap_or("");
    let turn = fields.next().unwrap_or("");
    let castling = fields.next().unwrap_or("");
    let ep = fields.next().unwrap_or("");
    format!("{board} {turn} {castling} {ep}")
}

/// Parse one CSV record (RFC 4180-ish: double-quoted fields may contain commas
/// and `""`-escaped quotes). Embedded newlines are not expected in this data.
fn parse_csv_line(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut cur = String::new();
    let mut in_quotes = false;
    let mut chars = line.chars().peekable();

    while let Some(c) = chars.next() {
        if in_quotes {
            if c == '"' {
                if chars.peek() == Some(&'"') {
                    cur.push('"');
                    chars.next();
                } else {
                    in_quotes = false;
                }
            } else {
                cur.push(c);
            }
        } else {
            match c {
                '"' => in_quotes = true,
                ',' => fields.push(std::mem::take(&mut cur)),
                _ => cur.push(c),
            }
        }
    }
    fields.push(cur);
    fields
}

#[derive(Debug, Default, Clone, Copy)]
pub struct EcoStats {
    pub games: usize,
    /// Games we wrote an `[ECO]`/`[Opening]` to.
    pub eco_assigned: usize,
    /// Games left alone because they already had an `[ECO]` (no `--force`).
    pub already_tagged: usize,
    /// Games we tried to classify but no opening matched.
    pub unmatched: usize,
    /// Games skipped because of a non-standard start position.
    pub custom_start: usize,
}

impl EcoStats {
    pub fn to_json(&self) -> String {
        format!(
            "{{\"games\":{},\"eco_assigned\":{},\"already_tagged\":{},\"unmatched\":{},\"custom_start\":{}}}",
            self.games, self.eco_assigned, self.already_tagged, self.unmatched, self.custom_start,
        )
    }
}

/// Run the classifier over every game from `reader`, writing tagged games to
/// `writer`. `force` recomputes/overwrites existing tags.
pub fn run_eco<R: io::BufRead, W: Write>(
    book: &EcoBook,
    reader: R,
    writer: &mut W,
    force: bool,
) -> io::Result<EcoStats> {
    let mut stats = EcoStats::default();

    for game in GameSplitter::new(reader) {
        let game = game?;
        stats.games += 1;

        let has_eco = game.header("ECO").is_some();
        let custom_start =
            game.header("FEN").is_some() || game.header("SetUp").map(|v| v == "1").unwrap_or(false);

        let should_classify = force || !has_eco;

        let mut tags: Option<OpeningEntry> = None;
        if !should_classify {
            stats.already_tagged += 1;
        } else if custom_start {
            stats.custom_start += 1;
        } else {
            match book.classify(&game.normalized_movetext()) {
                Some(entry) => {
                    tags = Some(entry.clone());
                    stats.eco_assigned += 1;
                }
                None => stats.unmatched += 1,
            }
        }

        emit_game(&game, tags.as_ref(), writer)?;
    }

    Ok(stats)
}

/// Emit one game, inserting `[ECO]`/`[Opening]` when `tags` is `Some`. Existing
/// `[ECO]`/`[Opening]` lines are dropped first (so re-tagging never duplicates),
/// and the new tags go right after `[Result ...]`, else at the end of the
/// header block. The movetext is preserved byte-for-byte.
fn emit_game<W: Write>(game: &Game, tags: Option<&OpeningEntry>, out: &mut W) -> io::Result<()> {
    let Some(entry) = tags else {
        // Nothing to change: pass the game through verbatim.
        out.write_all(&game.bytes)?;
        return Ok(());
    };

    let new_tags = format!(
        "[ECO \"{}\"]\n[Opening \"{}\"]\n",
        escape_tag_value(&entry.eco_base),
        escape_tag_value(&entry.name),
    );

    let bytes = &game.bytes;
    let mut i = 0usize;
    let mut in_headers = true;
    let mut inserted = false;

    while i < bytes.len() {
        let line_start = i;
        while i < bytes.len() && bytes[i] != b'\n' {
            i += 1;
        }
        let has_nl = i < bytes.len();
        let line_end = if has_nl { i + 1 } else { i }; // include the newline
        let line = &bytes[line_start..line_end];
        let content = trim_ascii_start(strip_eol(line));

        if in_headers {
            if content.first() == Some(&b'[') {
                let name = tag_name(content);
                if name == Some(b"ECO".as_ref()) || name == Some(b"Opening".as_ref()) {
                    // Drop the old tag; the fresh one is re-emitted below.
                } else {
                    out.write_all(line)?;
                    if name == Some(b"Result".as_ref()) && !inserted {
                        out.write_all(new_tags.as_bytes())?;
                        inserted = true;
                    }
                }
            } else {
                // First blank or movetext line ends the header block.
                if !inserted {
                    out.write_all(new_tags.as_bytes())?;
                    inserted = true;
                }
                in_headers = false;
                out.write_all(line)?;
            }
        } else {
            out.write_all(line)?;
        }

        i = line_end;
    }

    if !inserted {
        // Header-only game with no trailing blank/movetext line.
        out.write_all(new_tags.as_bytes())?;
    }

    Ok(())
}

/// The tag name of a header line, i.e. `ECO` for `[ECO "B90"]`. Assumes `line`
/// has already been left-trimmed and starts with `[`.
fn tag_name(line: &[u8]) -> Option<&[u8]> {
    let inner = &line[1..];
    let end = inner
        .iter()
        .position(|&b| b == b' ' || b == b'\t' || b == b']')?;
    Some(&inner[..end])
}

fn escape_tag_value(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
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

fn trim_ascii_start(s: &[u8]) -> &[u8] {
    let mut i = 0;
    while i < s.len() && (s[i] == b' ' || s[i] == b'\t') {
        i += 1;
    }
    &s[i..]
}

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    let parsed = crate::cli::parse(args, &["force"], &["output", "o", "eco-csv"])
        .map_err(|e| e.to_string())?;

    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);
    let force = parsed.has_flag("force");
    let show_progress = !parsed.global.no_progress;

    if parsed.positionals.len() != 1 {
        return Err("eco: expected exactly one input path (a file or - for stdin)".to_string());
    }
    let input = &parsed.positionals[0];

    // Build the opening book (embedded CSV by default; --eco-csv overrides).
    let book = match parsed.get_kv("eco-csv") {
        Some(path) => {
            let csv = fs::read_to_string(path)
                .map_err(|e| format!("eco: failed to read --eco-csv {path:?}: {e}"))?;
            EcoBook::from_csv(&csv)
        }
        None => EcoBook::embedded(),
    };
    if book.is_empty() {
        return Err("eco: opening reference is empty (no usable rows)".to_string());
    }

    // Resolve destination first so the terminal-flood guard fires before we
    // consume the (possibly stdin) input.
    let sink = crate::output::open_output(output.as_deref(), "eco").map_err(|e| e.to_string())?;
    let stats_to_stderr = sink.stats_to_stderr;
    let mut writer = sink.writer;

    let (raw_reader, len) = crate::output::open_input(input).map_err(|e| format!("eco: {e}"))?;
    let progress = ProgressReporter::maybe_bytes(len, "eco", show_progress);
    let reader = BufReader::new(progress.wrap(raw_reader));

    let stats =
        run_eco(&book, reader, &mut writer, force).map_err(|e| format!("eco failed: {e}"))?;
    writer.flush().map_err(|e| format!("eco failed: {e}"))?;
    progress.finish("eco done");

    crate::output::print_stats(&stats.to_json(), stats_to_stderr);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn test_book() -> EcoBook {
        EcoBook::embedded()
    }

    fn classify(book: &EcoBook, moves: &str) -> Option<OpeningEntry> {
        let normalized = normalize_movetext(moves.as_bytes());
        book.classify(&normalized).cloned()
    }

    #[test]
    fn parses_quoted_csv_field_with_comma() {
        let fields = parse_csv_line(
            "501,A17,A17,A,\"English: Anglo-Indian, 2.Nc3 e6 3.g3\",1.c4 Nf6 2.Nc3 e6 3.g3,url",
        );
        assert_eq!(fields[2], "A17");
        assert_eq!(fields[4], "English: Anglo-Indian, 2.Nc3 e6 3.g3");
        assert_eq!(fields[5], "1.c4 Nf6 2.Nc3 e6 3.g3");
    }

    #[test]
    fn embedded_book_is_populated() {
        let book = test_book();
        assert!(book.len() > 1000, "book unexpectedly small: {}", book.len());
        assert!(book.max_ply >= 6, "max_ply too small: {}", book.max_ply);
    }

    #[test]
    fn classifies_well_known_openings() {
        let book = test_book();
        assert_eq!(classify(&book, "1. e4 c5").unwrap().eco_base, "B20");
        assert_eq!(
            classify(&book, "1. e4 e5 2. Nf3 Nc6 3. Bb5")
                .unwrap()
                .eco_base,
            "C60"
        );
        assert_eq!(
            classify(&book, "1. e4 e5 2. Nf3 Nc6 3. Bc4")
                .unwrap()
                .eco_base,
            "C50"
        );
    }

    #[test]
    fn classification_is_transposition_aware() {
        let book = test_book();
        // 1.d4 Nf6 2.c4 e6 and 1.c4 Nf6 2.d4 e6 reach the same position.
        let a = classify(&book, "1. d4 Nf6 2. c4 e6").map(|e| e.eco_base);
        let b = classify(&book, "1. c4 Nf6 2. d4 e6").map(|e| e.eco_base);
        assert!(a.is_some());
        assert_eq!(a, b, "transposed move orders should share an ECO");
    }

    #[test]
    fn deepest_match_wins() {
        let book = test_book();
        // Plain Sicilian -> B20; the Najdorf continuation must classify deeper.
        let najdorf = classify(&book, "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6")
            .unwrap()
            .eco_base;
        assert!(najdorf.starts_with('B'));
        assert_ne!(najdorf, "B20", "should match deeper than the bare Sicilian");
    }

    #[test]
    fn run_eco_adds_tags_when_missing() {
        let book = test_book();
        let pgn = b"[Event \"x\"]\n[Result \"1-0\"]\n\n1. e4 c5 1-0\n";
        let mut out = Vec::new();
        let stats = run_eco(&book, Cursor::new(pgn), &mut out, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("[ECO \"B20\"]"), "missing ECO: {s}");
        assert!(s.contains("[Opening \""), "missing Opening: {s}");
        // Inserted right after Result, movetext preserved.
        assert!(
            s.contains("[Result \"1-0\"]\n[ECO \"B20\"]"),
            "placement: {s}"
        );
        assert!(s.contains("1. e4 c5 1-0"));
        assert_eq!(stats.eco_assigned, 1);
        assert_eq!(stats.games, 1);
    }

    #[test]
    fn run_eco_skips_already_tagged_without_force() {
        let book = test_book();
        let pgn = b"[Event \"x\"]\n[Result \"1-0\"]\n[ECO \"Z99\"]\n\n1. e4 c5 1-0\n";
        let mut out = Vec::new();
        let stats = run_eco(&book, Cursor::new(pgn), &mut out, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            s.contains("[ECO \"Z99\"]"),
            "existing tag should survive: {s}"
        );
        assert!(!s.contains("B20"));
        assert_eq!(stats.already_tagged, 1);
        assert_eq!(stats.eco_assigned, 0);
    }

    #[test]
    fn run_eco_force_overwrites_without_duplicating() {
        let book = test_book();
        let pgn = b"[Event \"x\"]\n[Result \"1-0\"]\n[ECO \"Z99\"]\n\n1. e4 c5 1-0\n";
        let mut out = Vec::new();
        let stats = run_eco(&book, Cursor::new(pgn), &mut out, true).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("[ECO \"B20\"]"), "force should overwrite: {s}");
        assert!(!s.contains("Z99"), "old tag should be gone: {s}");
        assert_eq!(s.matches("[ECO ").count(), 1, "no duplicate ECO: {s}");
        assert_eq!(stats.eco_assigned, 1);
    }

    #[test]
    fn run_eco_skips_custom_start_position() {
        let book = test_book();
        let pgn =
            b"[Event \"x\"]\n[Result \"*\"]\n[FEN \"8/8/8/8/8/8/8/K6k w - - 0 1\"]\n\n1. Kb2 *\n";
        let mut out = Vec::new();
        let stats = run_eco(&book, Cursor::new(pgn), &mut out, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            !s.contains("[ECO "),
            "custom-start game should be skipped: {s}"
        );
        assert_eq!(stats.custom_start, 1);
    }
}
