//! The `clean` subcommand and the underlying lexical rewriter.
//!
//! The rewriter is a literal port of the original `FastRewriter` in
//! `src/main.rs`, with one targeted change: it now writes to any
//! `std::io::Write` impl instead of accumulating into a `String`. This makes
//! it usable from `concat --clean` (chained writes into one output) and means
//! gigabyte PGNs no longer hold the full output in memory.
//!
//! The CLI surface for the legacy invocations is preserved exactly: the same
//! JSON stats are printed on stdout and the output file is byte-identical to
//! the previous implementation.

use std::fs::File;
use std::io::{self, BufWriter, IsTerminal, Read, Write};
use std::path::{Path, PathBuf};

use crate::progress::ProgressReporter;

/// Stats reported on stdout when `clean` (or the legacy form) finishes.
///
/// Field names and JSON shape are part of the public contract with the
/// Python wrapper at `src/reti/pgn_utils.py`. Don't rename.
#[derive(Debug, Default, Clone, Copy)]
pub struct CleanStats {
    pub removed_bom: bool,
    pub invalid_utf8_replaced: usize,
    pub control_characters_removed: usize,
    pub games_written: usize,
    pub comments_removed: usize,
    pub variations_removed: usize,
    pub line_comments_removed: usize,
}

impl CleanStats {
    pub fn to_json(&self) -> String {
        format!(
            concat!(
                "{{",
                "\"removed_bom\":{},",
                "\"invalid_utf8_replaced\":{},",
                "\"control_characters_removed\":{},",
                "\"games_written\":{},",
                "\"comments_removed\":{},",
                "\"variations_removed\":{},",
                "\"line_comments_removed\":{}",
                "}}"
            ),
            if self.removed_bom { "true" } else { "false" },
            self.invalid_utf8_replaced,
            self.control_characters_removed,
            self.games_written,
            self.comments_removed,
            self.variations_removed,
            self.line_comments_removed,
        )
    }
}

/// Streaming lexical PGN rewriter.
///
/// Identical character-by-character behaviour to the previous
/// `String`-buffered implementation. Tracked errors from the underlying
/// writer are deferred until [`FastRewriter::finish`] returns, so the call
/// sites stay simple (one `?` at the end).
pub struct FastRewriter<'w> {
    writer: &'w mut dyn Write,
    inspect_only: bool,
    write_err: Option<io::Error>,

    preserve_markup: bool,
    removed_bom: bool,
    invalid_utf8_replaced: usize,
    control_characters_removed: usize,
    games_written: usize,
    comments_removed: usize,
    variations_removed: usize,
    line_comments_removed: usize,

    at_file_start: bool,
    in_comment: bool,
    variation_depth: usize,
    skip_line_comment: bool,
    header_line: bool,
    line_start: bool,
    recovery_armed: bool,
    pending_space: bool,
    saw_nonwhitespace_output: bool,
    source_line_has_nonspace: bool,
    current_game_has_moves: bool,
    current_game_has_result: bool,

    leading_whitespace: String,
    line_output: String,
    token: String,
}

impl<'w> FastRewriter<'w> {
    pub fn new(writer: &'w mut dyn Write, preserve_markup: bool) -> Self {
        Self {
            writer,
            inspect_only: false,
            write_err: None,
            preserve_markup,
            removed_bom: false,
            invalid_utf8_replaced: 0,
            control_characters_removed: 0,
            games_written: 0,
            comments_removed: 0,
            variations_removed: 0,
            line_comments_removed: 0,
            at_file_start: true,
            in_comment: false,
            variation_depth: 0,
            skip_line_comment: false,
            header_line: false,
            line_start: true,
            recovery_armed: false,
            pending_space: false,
            saw_nonwhitespace_output: false,
            source_line_has_nonspace: false,
            current_game_has_moves: false,
            current_game_has_result: false,
            leading_whitespace: String::new(),
            line_output: String::new(),
            token: String::new(),
        }
    }

    pub fn set_inspect_only(&mut self, inspect_only: bool) {
        self.inspect_only = inspect_only;
    }

    pub fn feed_text(&mut self, text: &str) {
        let mut last_was_cr = false;
        for ch in text.chars() {
            if last_was_cr {
                last_was_cr = false;
                if ch == '\n' {
                    continue;
                }
            }
            if ch == '\r' {
                self.feed_char('\n');
                last_was_cr = true;
                continue;
            }
            self.feed_char(ch);
        }
    }

    fn feed_char(&mut self, mut ch: char) {
        if self.at_file_start {
            self.at_file_start = false;
            if ch == '\u{feff}' {
                self.removed_bom = true;
                return;
            }
        }

        if ch == '\u{fffd}' {
            self.invalid_utf8_replaced += 1;
            ch = '?';
        }

        if (ch as u32) < 32 && ch != '\n' && ch != '\t' {
            self.control_characters_removed += 1;
            return;
        }

        if ch == '\n' {
            self.finish_line(true);
            return;
        }

        if ch != ' ' && ch != '\t' {
            self.source_line_has_nonspace = true;
        }

        if self.line_start {
            if ch == ' ' || ch == '\t' {
                self.leading_whitespace.push(ch);
                return;
            }

            if !self.preserve_markup && self.recovery_armed && ch == '[' {
                self.in_comment = false;
                self.variation_depth = 0;
                self.recovery_armed = false;
            }
        }

        if !self.preserve_markup && self.skip_line_comment {
            return;
        }

        if self.header_line {
            self.line_output.push(ch);
            return;
        }

        if !self.preserve_markup {
            if self.in_comment {
                if ch == '}' {
                    self.in_comment = false;
                    if self.variation_depth == 0 {
                        self.recovery_armed = false;
                    }
                }
                return;
            }

            if self.variation_depth > 0 {
                match ch {
                    '{' => {
                        self.finish_token();
                        self.comments_removed += 1;
                        self.in_comment = true;
                    }
                    '(' => {
                        self.finish_token();
                        self.variations_removed += 1;
                        self.variation_depth += 1;
                    }
                    ')' => {
                        self.variation_depth -= 1;
                        if self.variation_depth == 0 {
                            self.recovery_armed = false;
                        }
                    }
                    _ => {}
                }
                return;
            }
        }

        if self.line_start {
            if ch == '[' {
                self.header_line = true;
                self.line_output.push_str(&self.leading_whitespace);
                self.leading_whitespace.clear();
                self.line_output.push(ch);
                self.line_start = false;
                return;
            }

            if !self.preserve_markup && (ch == '%' || ch == ';') {
                self.line_comments_removed += 1;
                self.skip_line_comment = true;
                self.leading_whitespace.clear();
                self.line_start = false;
                return;
            }

            self.leading_whitespace.clear();
            self.line_start = false;
        }

        if !self.preserve_markup {
            match ch {
                '{' => {
                    self.finish_token();
                    self.comments_removed += 1;
                    self.in_comment = true;
                    return;
                }
                '(' => {
                    self.finish_token();
                    self.variations_removed += 1;
                    self.variation_depth = 1;
                    return;
                }
                ';' => {
                    self.finish_token();
                    self.line_comments_removed += 1;
                    self.skip_line_comment = true;
                    return;
                }
                _ => {}
            }
        }

        match ch {
            ' ' | '\t' => {
                if !self.line_output.is_empty() {
                    self.finish_token();
                    self.pending_space = true;
                }
            }
            _ => {
                if self.pending_space && !self.line_output.is_empty() {
                    self.line_output.push(' ');
                }
                self.pending_space = false;
                self.line_output.push(ch);
                self.token.push(ch);
                self.current_game_has_moves = true;
                self.saw_nonwhitespace_output = true;
            }
        }
    }

    fn finish_line(&mut self, had_newline: bool) {
        self.finish_token();
        if !self.header_line {
            while self.line_output.ends_with(' ') || self.line_output.ends_with('\t') {
                self.line_output.pop();
            }
        }

        let is_event_header = self.header_line
            && self
                .line_output
                .trim_start_matches(|c| c == ' ' || c == '\t')
                .starts_with("[Event ");
        if is_event_header {
            self.write_missing_result(true);
            self.games_written += 1;
            self.saw_nonwhitespace_output = true;
            self.current_game_has_moves = false;
            self.current_game_has_result = false;
        }

        if !self.inspect_only && self.write_err.is_none() {
            if !self.line_output.is_empty() {
                if let Err(e) = self.writer.write_all(self.line_output.as_bytes()) {
                    self.write_err = Some(e);
                }
            }
            if had_newline && self.write_err.is_none() {
                if let Err(e) = self.writer.write_all(b"\n") {
                    self.write_err = Some(e);
                }
            }
        }

        if (self.in_comment || self.variation_depth > 0) && !self.source_line_has_nonspace {
            self.recovery_armed = true;
        }

        self.skip_line_comment = false;
        self.header_line = false;
        self.line_start = true;
        self.pending_space = false;
        self.source_line_has_nonspace = false;
        self.leading_whitespace.clear();
        self.line_output.clear();
    }

    fn write_str(&mut self, s: &str) {
        if self.inspect_only || self.write_err.is_some() {
            return;
        }
        if let Err(e) = self.writer.write_all(s.as_bytes()) {
            self.write_err = Some(e);
        }
    }

    fn finish_token(&mut self) {
        if self.token.is_empty() {
            return;
        }
        if self.token == "1-0"
            || self.token == "0-1"
            || self.token == "1/2-1/2"
            || self.token == "*"
        {
            self.current_game_has_result = true;
        }
        self.token.clear();
    }

    fn write_missing_result(&mut self, before_new_game: bool) {
        if !self.current_game_has_moves || self.current_game_has_result {
            return;
        }

        if !self.inspect_only {
            if before_new_game {
                self.write_str("*\n\n");
            } else {
                self.write_str("*\n");
            }
        }
        self.current_game_has_result = true;
        self.saw_nonwhitespace_output = true;
    }

    /// Flush trailing state, return the accumulated stats. Any deferred
    /// write error is surfaced here.
    pub fn finish(mut self) -> io::Result<CleanStats> {
        if !self.line_output.is_empty() || self.header_line {
            self.finish_line(false);
        }

        self.write_missing_result(false);
        if !self.inspect_only && self.games_written == 0 && self.saw_nonwhitespace_output {
            self.games_written = 1;
        }

        if let Some(err) = self.write_err {
            return Err(err);
        }

        Ok(CleanStats {
            removed_bom: self.removed_bom,
            invalid_utf8_replaced: self.invalid_utf8_replaced,
            control_characters_removed: self.control_characters_removed,
            games_written: self.games_written,
            comments_removed: self.comments_removed,
            variations_removed: self.variations_removed,
            line_comments_removed: self.line_comments_removed,
        })
    }
}

/// Convenience helper that runs the rewriter against an in-memory string and
/// returns `(rewritten_bytes, stats)`. Used by `clean`, the legacy form, and
/// `concat --clean`.
///
/// In strip mode (`preserve_markup == false`) the rewriter's output is run
/// through [`reflow_pgn`] so the movetext is re-wrapped into standard export
/// formatting instead of inheriting the source's (now comment-less) line
/// breaks. With `preserve_markup` the bytes are returned untouched so callers
/// that depend on the exact lexical layout — notably the `{CQL}`-marker
/// preflight path — see no change.
pub fn rewrite_to_vec(text: &str, preserve_markup: bool) -> io::Result<(Vec<u8>, CleanStats)> {
    let mut buf: Vec<u8> = Vec::with_capacity(text.len());
    let stats = {
        let mut rw = FastRewriter::new(&mut buf, preserve_markup);
        rw.feed_text(text);
        rw.finish()?
    };
    let out = if preserve_markup {
        buf
    } else {
        reflow_pgn(&buf)
    };
    Ok((out, stats))
}

/// Standard PGN export movetext wrap width: a movetext line never exceeds this
/// many columns, and breaks fall only between whole tokens.
const MOVETEXT_WIDTH: usize = 80;

/// Re-flow stripped PGN (the output of [`FastRewriter`] with
/// `preserve_markup == false`) into conventional export formatting:
///
///   * header tag lines (`[Tag "..."]`) are emitted verbatim, one per line;
///   * exactly one blank line separates a game's headers from its movetext;
///   * movetext tokens (move numbers, SAN, NAGs, the result) flow continuously
///     and wrap at [`MOVETEXT_WIDTH`] columns, breaking only between tokens;
///   * exactly one blank line separates consecutive games.
///
/// The lexer leaves one token per line when each move trailed a long comment in
/// the source, and a stray blank line wherever a comment-only line was
/// stripped; this pass collapses that ragged output into the standard layout.
/// It works on raw bytes so it never has to assume valid UTF-8 (player names,
/// etc. are passed through unchanged).
pub fn reflow_pgn(bytes: &[u8]) -> Vec<u8> {
    #[derive(PartialEq)]
    enum State {
        Start,
        Headers,
        Movetext,
    }

    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut state = State::Start;
    let mut col = 0usize;
    // Whether the current game has already emitted a movetext token. A black
    // move-number indicator (`12...`) is only required as the very first
    // movetext token of a game (black to move from the start position);
    // anywhere else it stood in for stripped commentary and is now redundant.
    let mut seen_move_token = false;

    for raw_line in bytes.split(|&b| b == b'\n') {
        // Drop a trailing CR so CRLF-terminated input reflows cleanly.
        let line = match raw_line.last() {
            Some(b'\r') => &raw_line[..raw_line.len() - 1],
            _ => raw_line,
        };
        let trimmed = trim_ascii_ws(line);
        if trimmed.is_empty() {
            // Blank lines carry no information here; spacing is reconstructed.
            continue;
        }

        if trimmed[0] == b'[' {
            // A header tag line. `[Event ` marks the start of a new game.
            let is_event = trimmed.starts_with(b"[Event ") || trimmed.starts_with(b"[Event\t");
            match state {
                // New game after the previous game's movetext: end the line and
                // leave one blank separator. This transition (movetext -> header)
                // is the *only* way a fresh game can begin carrying a stale
                // `seen_move_token`, so re-arm here rather than keying off
                // `[Event ` — games whose header block doesn't lead with `[Event `
                // would otherwise lose a load-bearing leading `1...`.
                State::Movetext => {
                    out.extend_from_slice(b"\n\n");
                    seen_move_token = false;
                }
                // A new game right after a headers-only game: one blank line so
                // the two header blocks don't run together. (A headers-only game
                // emits no movetext, so `seen_move_token` is already false here;
                // resetting is just belt-and-braces.)
                State::Headers if is_event => {
                    out.push(b'\n');
                    seen_move_token = false;
                }
                _ => {}
            }
            out.extend_from_slice(trimmed);
            out.push(b'\n');
            state = State::Headers;
            col = 0;
        } else {
            // A movetext line: flow its tokens into the wrapped output.
            if state == State::Headers {
                // One blank line between the header block and the movetext.
                out.push(b'\n');
                col = 0;
            }
            for token in trimmed.split(|&b| b == b' ' || b == b'\t') {
                if token.is_empty() {
                    continue;
                }
                match black_move_number_suffix(token) {
                    // A redundant black move-number indicator (commentary that
                    // forced it has been stripped). Drop the `12...` prefix; if a
                    // SAN was glued onto it (`12...Nf6`), keep just the SAN.
                    Some(san) if seen_move_token => {
                        if !san.is_empty() {
                            emit_movetext_token(&mut out, &mut col, san);
                        }
                    }
                    // Either an ordinary token, or a leading black indicator that
                    // is genuinely needed (first move, black to play) — keep as-is.
                    _ => {
                        emit_movetext_token(&mut out, &mut col, token);
                        // A NAG (`$N`) annotates the *previous* move, so it never
                        // stands in for one; don't let a leading NAG consume the
                        // first-token slot and strip a load-bearing `1...`.
                        if token.first() != Some(&b'$') {
                            seen_move_token = true;
                        }
                    }
                }
            }
            state = State::Movetext;
        }
    }

    if state == State::Movetext {
        // Terminate the final movetext line and leave one trailing blank line,
        // matching the per-game separator the rest of the toolset emits.
        out.extend_from_slice(b"\n\n");
    }

    out
}

/// Append `token` to the wrapped movetext in `out`, inserting a space or a line
/// break as needed and tracking the current column in `col`.
fn emit_movetext_token(out: &mut Vec<u8>, col: &mut usize, token: &[u8]) {
    if *col == 0 {
        out.extend_from_slice(token);
        *col = token.len();
    } else if *col + 1 + token.len() <= MOVETEXT_WIDTH {
        out.push(b' ');
        out.extend_from_slice(token);
        *col += 1 + token.len();
    } else {
        out.push(b'\n');
        out.extend_from_slice(token);
        *col = token.len();
    }
}

/// Classify `token` as a black move-number indicator and return the SAN, if
/// any, glued directly onto it.
///
///   * `"12..."`    -> `Some(b"")`     (bare indicator)
///   * `"12...Nf6"` -> `Some(b"Nf6")`  (indicator with the move attached)
///   * anything else (white number `"12."`, result `"1/2-1/2"`, SAN, NAG) ->
///     `None`
///
/// A match requires one or more leading ASCII digits followed by exactly three
/// dots. Two dots (`"12.."`) or four (`"12...."`) are malformed move numbers, so
/// they're left untouched rather than guessed at.
fn black_move_number_suffix(token: &[u8]) -> Option<&[u8]> {
    let mut digits = 0;
    while digits < token.len() && token[digits].is_ascii_digit() {
        digits += 1;
    }
    if digits == 0 || token.len() < digits + 3 || &token[digits..digits + 3] != b"..." {
        return None;
    }
    let rest = &token[digits + 3..];
    // A fourth dot means this isn't a `N...` indicator; don't touch it.
    if rest.first() == Some(&b'.') {
        return None;
    }
    Some(rest)
}

/// Trim leading/trailing ASCII spaces and tabs from a byte slice.
fn trim_ascii_ws(s: &[u8]) -> &[u8] {
    let mut start = 0;
    while start < s.len() && (s[start] == b' ' || s[start] == b'\t') {
        start += 1;
    }
    let mut end = s.len();
    while end > start && (s[end - 1] == b' ' || s[end - 1] == b'\t') {
        end -= 1;
    }
    &s[start..end]
}

/// Where a `clean` run sends its rewritten bytes.
enum CleanOutput<'a> {
    /// Write the rewritten PGN to this sink.
    Write(&'a mut dyn Write),
    /// Scan only and report stats (the legacy `--inspect` mode); produce no
    /// output.
    Inspect,
}

/// Core of `clean`: read everything from `reader`, run the rewriter, and send
/// the result to `output`. `total` is the input length when known (a file) so
/// the progress bar can show a percentage; `None` (stdin) falls back to a
/// byte-counting spinner.
fn clean_core(
    reader: Box<dyn Read>,
    total: Option<u64>,
    output: CleanOutput<'_>,
    preserve_markup: bool,
    label: &str,
    show_progress: bool,
) -> io::Result<CleanStats> {
    let progress = ProgressReporter::maybe_bytes(total, label, show_progress);
    let mut wrapped = progress.wrap(reader);
    let mut bytes = Vec::new();
    io::copy(&mut wrapped, &mut bytes)?;
    let text = String::from_utf8_lossy(&bytes);

    let stats = match output {
        CleanOutput::Write(writer) => {
            // Buffer + reflow so the movetext is re-wrapped (strip mode); the
            // output is always smaller than the already-buffered input.
            let (out_bytes, stats) = rewrite_to_vec(text.as_ref(), preserve_markup)?;
            writer.write_all(&out_bytes)?;
            stats
        }
        CleanOutput::Inspect => {
            let mut sink = io::sink();
            let mut rw = FastRewriter::new(&mut sink, preserve_markup);
            rw.set_inspect_only(true);
            rw.feed_text(text.as_ref());
            rw.finish()?
        }
    };

    progress.finish(&format!("{label} done"));
    Ok(stats)
}

/// CLI entry for `clean` (and the legacy positional form).
///
/// `output_path == None` is the legacy `--inspect` mode: scan the input and
/// report stats without writing anything. `input_path` may be `-` for stdin.
pub fn run_clean(
    input_path: &Path,
    output_path: Option<&Path>,
    preserve_markup: bool,
    show_progress: bool,
) -> io::Result<CleanStats> {
    let (reader, len) = crate::output::open_input(input_path)?;
    match output_path {
        Some(path) => {
            let out_file = File::create(path)?;
            let mut writer = BufWriter::new(out_file);
            let stats = clean_core(
                reader,
                len,
                CleanOutput::Write(&mut writer),
                preserve_markup,
                "clean",
                show_progress,
            )?;
            writer.flush()?;
            Ok(stats)
        }
        None => clean_core(
            reader,
            len,
            CleanOutput::Inspect,
            preserve_markup,
            "clean",
            show_progress,
        ),
    }
}

/// Subcommand entry: parses subcommand-specific args off the supplied list.
///
/// Returns the path to write the output to (Some) or None if `--inspect`.
pub fn run_subcommand(args: &[std::ffi::OsString]) -> Result<(), String> {
    let parsed = crate::cli::parse(
        args,
        &["preserve-markup", "inspect"],
        &["input", "output", "o"],
    )
    .map_err(|e| e.to_string())?;

    let preserve = parsed.has_flag("preserve-markup");
    let inspect = parsed.has_flag("inspect");
    let show_progress = !parsed.global.no_progress;

    // Support both flag-form (`--input X --output Y`/`-o Y`) and positional form
    // (`clean INPUT OUTPUT` or `clean --inspect INPUT`).
    let mut input: Option<PathBuf> = parsed.get_kv("input").map(PathBuf::from);
    let mut output: Option<PathBuf> = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);

    let mut iter = parsed.positionals.iter();
    if input.is_none() {
        input = iter.next().cloned();
    }
    if output.is_none() && !inspect {
        output = iter.next().cloned();
    }
    if iter.next().is_some() {
        return Err("clean: too many positional arguments".to_string());
    }

    // No explicit input + piped stdin => read stdin, so `concat . | clean` works.
    let input = match input {
        Some(p) => p,
        None => {
            if io::stdin().is_terminal() {
                return Err(
                    "clean: missing input path (pass a file, - for stdin, or pipe into clean)"
                        .to_string(),
                );
            }
            PathBuf::from("-")
        }
    };

    if inspect && output.is_some() {
        return Err("clean: --inspect cannot be combined with an output path".to_string());
    }

    if inspect {
        let stats = run_clean(&input, None, preserve, show_progress)
            .map_err(|e| format!("clean failed: {e}"))?;
        // --inspect produces no data stream, so the stats are the result and
        // belong on stdout.
        crate::output::print_stats(&stats.to_json(), false);
        return Ok(());
    }

    // Resolve the destination (file, forced `-`, piped stdout, or the
    // terminal-flood guard) before consuming the (possibly stdin) input.
    let sink = crate::output::open_output(output.as_deref(), "clean")
        .map_err(|e| format!("clean failed: {e}"))?;
    let stats_to_stderr = sink.stats_to_stderr;
    let mut writer = sink.writer;

    let (reader, len) =
        crate::output::open_input(&input).map_err(|e| format!("clean failed: {e}"))?;
    let stats = clean_core(
        reader,
        len,
        CleanOutput::Write(&mut *writer),
        preserve,
        "clean",
        show_progress,
    )
    .map_err(|e| format!("clean failed: {e}"))?;
    writer.flush().map_err(|e| format!("clean failed: {e}"))?;

    crate::output::print_stats(&stats.to_json(), stats_to_stderr);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reflow_rewraps_ragged_movetext_and_collapses_blanks() {
        // The TCEC shape: a stripped leading comment (-> blank line) plus a
        // long comment after every move, so the lexer leaves one move per line.
        let pgn = "[Event \"x\"]\n[Result \"1/2-1/2\"]\n\n{ huge engine options }\n\
                   1. e4 {c} b6 {c}\n2. Nc3 {c}\nBb7 {c}\n3. d4 {c}\ne6 {c} 1/2-1/2\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(!s.contains('{'), "comment leaked: {s:?}");
        // Movetext flows onto one line (well under 80 cols), result included.
        assert!(
            s.contains("1. e4 b6 2. Nc3 Bb7 3. d4 e6 1/2-1/2"),
            "movetext not reflowed: {s:?}"
        );
        // Exactly one blank line between headers and movetext, and no stray
        // blank from the stripped leading comment.
        assert!(
            s.contains("[Result \"1/2-1/2\"]\n\n1. e4"),
            "header/movetext spacing wrong: {s:?}"
        );
        assert!(!s.contains("\n\n\n"), "triple newline present: {s:?}");
    }

    #[test]
    fn reflow_wraps_long_movetext_at_column_limit() {
        let mut pgn = String::from("[Event \"x\"]\n\n");
        for i in 1..=60 {
            pgn.push_str(&format!("{i}. Nf3 Nc6 "));
        }
        pgn.push_str("1-0\n");
        let (out, _stats) = rewrite_to_vec(&pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        for line in s.lines() {
            assert!(
                line.len() <= MOVETEXT_WIDTH,
                "line over {MOVETEXT_WIDTH}: {line:?}"
            );
        }
        let movetext_lines = s
            .lines()
            .filter(|l| l.starts_with(|c: char| c.is_ascii_digit()))
            .count();
        assert!(
            movetext_lines >= 2,
            "expected wrapping into multiple lines: {s:?}"
        );
    }

    #[test]
    fn reflow_separates_headers_only_games() {
        // A game with no movetext must still be separated from the next game's
        // headers by one blank line (no merging, no triple newline).
        let pgn = "[Event \"a\"]\n[Site \"s\"]\n\n[Event \"b\"]\n\n1. e4 e5 1-0\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            s.contains("[Site \"s\"]\n\n[Event \"b\"]"),
            "headers merged: {s:?}"
        );
        assert!(!s.contains("\n\n\n"), "triple newline present: {s:?}");
    }

    #[test]
    fn reflow_separates_games_with_one_blank_line() {
        let pgn = "[Event \"a\"]\n\n1. e4 {x}\ne5 1-0\n\n[Event \"b\"]\n\n1. d4 d5 0-1\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            s.contains("1. e4 e5 1-0\n\n[Event \"b\"]"),
            "game separator wrong: {s:?}"
        );
        assert!(!s.contains("\n\n\n"), "triple newline present: {s:?}");
    }

    #[test]
    fn drops_redundant_black_move_numbers_after_stripping_comments() {
        // The lichess-broadcast shape: every move trails an [%eval]/[%clk]
        // comment, so the source spells out a black move-number indicator before
        // each black move. Once the comments are gone those indicators are
        // redundant and must not survive.
        let pgn = "[Event \"x\"]\n\n\
                   1. d4 { [%eval 0.2] } 1... Nf6 { [%eval 0.2] } 2. c4 \
                   { [%eval 0.2] } 2... e6 { [%eval 0.2] } 1/2-1/2\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            s.contains("1. d4 Nf6 2. c4 e6 1/2-1/2"),
            "redundant black move numbers not dropped: {s:?}"
        );
        assert!(!s.contains("..."), "ellipsis leaked: {s:?}");
    }

    #[test]
    fn keeps_leading_black_move_number_when_black_starts() {
        // A game that begins with black to move (e.g. set up from a FEN) genuinely
        // needs its leading `1...`; it is the one indicator that is load-bearing.
        let pgn = "[Event \"x\"]\n[FEN \"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b\"]\n\n\
                   1... e5 { c } 2. Nf3 { c } 2... Nc6 1/2-1/2\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            s.contains("1... e5 2. Nf3 Nc6 1/2-1/2"),
            "leading black indicator wrongly dropped or trailing one kept: {s:?}"
        );
    }

    #[test]
    fn resets_black_move_number_state_per_game() {
        // The first-token exception must re-arm for every game: game two also
        // starts with black to move and must keep its own `1...`.
        let pgn = "[Event \"a\"]\n\n1. e4 {c} 1... e5 1-0\n\n\
                   [Event \"b\"]\n\n1... c5 {c} 2. Nf3 {c} 2... d6 0-1\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("1. e4 e5 1-0"), "game a not normalized: {s:?}");
        assert!(
            s.contains("1... c5 2. Nf3 d6 0-1"),
            "game b leading indicator wrongly dropped: {s:?}"
        );
    }

    #[test]
    fn rearms_leading_indicator_for_event_less_game() {
        // A second game whose header block does not lead with `[Event ` must
        // still re-arm the leading-indicator exception: the reset keys off the
        // movetext->header boundary, not the `[Event ` tag.
        let pgn = "[Event \"a\"]\n\n1. e4 {c} 1... e5 1-0\n\n\
                   [White \"x\"]\n[FEN \"8/8/8/8/8/8/8/8 b - - 0 1\"]\n\n1... c5 {c} 2. Nf3 0-1\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("1. e4 e5 1-0"), "game a not normalized: {s:?}");
        assert!(
            s.contains("1... c5 2. Nf3 0-1"),
            "event-less game lost its load-bearing leading 1...: {s:?}"
        );
    }

    #[test]
    fn keeps_leading_indicator_preceded_by_nag() {
        // A NAG before the first move must not consume the first-token slot and
        // cause the genuinely-leading black indicator to be dropped.
        let pgn = "[Event \"x\"]\n[FEN \"8/8/8/8/8/8/8/8 b - - 0 1\"]\n\n\
                   $10 { white is better } 1... e5 { c } 2. Nf3 { c } 2... Nc6 1-0\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            s.contains("$10 1... e5 2. Nf3 Nc6 1-0"),
            "leading indicator dropped after a NAG: {s:?}"
        );
    }

    #[test]
    fn drops_redundant_black_number_glued_to_san() {
        // Some producers write the indicator without a trailing space
        // (`5...Bxc5`). The redundant prefix is stripped but the move is kept.
        let pgn = "[Event \"x\"]\n\n1. e4 {c} 1...e5 {c} 2. Nf3 {c} 2...Nc6 1-0\n";
        let (out, _stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(
            s.contains("1. e4 e5 2. Nf3 Nc6 1-0"),
            "glued black indicator not handled: {s:?}"
        );
        assert!(!s.contains("..."), "ellipsis leaked: {s:?}");
    }

    #[test]
    fn black_move_number_suffix_classifies_tokens() {
        assert_eq!(black_move_number_suffix(b"1..."), Some(&b""[..]));
        assert_eq!(black_move_number_suffix(b"35..."), Some(&b""[..]));
        assert_eq!(black_move_number_suffix(b"35...Be8"), Some(&b"Be8"[..]));
        // White move numbers, results, SAN, NAGs, and malformed dot-runs: no match.
        assert_eq!(black_move_number_suffix(b"35."), None);
        assert_eq!(black_move_number_suffix(b"1-0"), None);
        assert_eq!(black_move_number_suffix(b"1/2-1/2"), None);
        assert_eq!(black_move_number_suffix(b"Nf6"), None);
        assert_eq!(black_move_number_suffix(b"$1"), None);
        assert_eq!(black_move_number_suffix(b"..."), None);
        assert_eq!(black_move_number_suffix(b"12.."), None);
        assert_eq!(black_move_number_suffix(b"12...."), None);
    }

    #[test]
    fn strips_block_comments_and_variations() {
        let pgn = "[Event \"x\"]\n[Result \"1-0\"]\n\n1. e4 {good} (1. d4) e5 1-0\n";
        let (out, stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(!s.contains('{'), "comment not stripped: {s:?}");
        assert!(!s.contains('('), "variation not stripped: {s:?}");
        assert_eq!(stats.comments_removed, 1);
        assert_eq!(stats.variations_removed, 1);
        assert_eq!(stats.games_written, 1);
    }

    #[test]
    fn preserve_markup_keeps_braces_and_parens() {
        let pgn = "[Event \"x\"]\n[Result \"1-0\"]\n\n1. e4 {good} (1. d4) e5 1-0\n";
        let (out, _stats) = rewrite_to_vec(pgn, true).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("{good}"));
        assert!(s.contains("(1. d4)"));
    }

    #[test]
    fn inserts_missing_result_token() {
        let pgn = "[Event \"x\"]\n\n1. e4 e5\n";
        let (out, stats) = rewrite_to_vec(pgn, false).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(s.trim_end().ends_with('*'), "expected trailing *: {s:?}");
        assert_eq!(stats.games_written, 1);
    }

    #[test]
    fn drops_utf8_bom() {
        let pgn = "\u{feff}[Event \"x\"]\n\n1. e4 1-0\n";
        let (out, stats) = rewrite_to_vec(pgn, false).unwrap();
        assert!(stats.removed_bom);
        assert!(!String::from_utf8(out).unwrap().starts_with('\u{feff}'));
    }

    #[test]
    fn replaces_replacement_character_with_question_mark() {
        let pgn = "[Event \"x\u{fffd}\"]\n\n1. e4 1-0\n";
        let (out, stats) = rewrite_to_vec(pgn, false).unwrap();
        assert_eq!(stats.invalid_utf8_replaced, 1);
        assert!(String::from_utf8(out).unwrap().contains("x?"));
    }

    #[test]
    fn json_stats_shape_is_stable() {
        // The Python wrapper parses this JSON; field order matters for
        // simple consumers but the shape definitely does.
        let stats = CleanStats {
            removed_bom: true,
            invalid_utf8_replaced: 1,
            control_characters_removed: 2,
            games_written: 3,
            comments_removed: 4,
            variations_removed: 5,
            line_comments_removed: 6,
        };
        let json = stats.to_json();
        assert!(json.contains("\"removed_bom\":true"));
        assert!(json.contains("\"invalid_utf8_replaced\":1"));
        assert!(json.contains("\"games_written\":3"));
        assert!(json.contains("\"line_comments_removed\":6"));
    }
}
