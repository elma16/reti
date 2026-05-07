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

use std::fs::{self, File};
use std::io::{self, BufWriter, Write};
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
/// returns `(rewritten_bytes, stats)`. Used by tests and by `concat --clean`.
pub fn rewrite_to_vec(text: &str, preserve_markup: bool) -> io::Result<(Vec<u8>, CleanStats)> {
    let mut buf: Vec<u8> = Vec::with_capacity(text.len());
    let stats = {
        let mut rw = FastRewriter::new(&mut buf, preserve_markup);
        rw.feed_text(text);
        rw.finish()?
    };
    Ok((buf, stats))
}

/// CLI entry for `clean` (and the legacy positional form).
///
/// `output_path == None` is the legacy `--inspect` mode: scan the input and
/// report stats without writing anything.
pub fn run_clean(
    input_path: &Path,
    output_path: Option<&Path>,
    preserve_markup: bool,
    show_progress: bool,
) -> io::Result<CleanStats> {
    let metadata = fs::metadata(input_path)?;
    let total_bytes = metadata.len();
    let progress = ProgressReporter::bytes(total_bytes, "clean", show_progress);

    let file = File::open(input_path)?;
    let mut wrapped = progress.wrap(file);
    let mut bytes = Vec::with_capacity(total_bytes as usize);
    io::copy(&mut wrapped, &mut bytes)?;
    let text = String::from_utf8_lossy(&bytes);

    let stats = match output_path {
        Some(path) => {
            let out_file = File::create(path)?;
            let mut writer = BufWriter::new(out_file);
            let mut rw = FastRewriter::new(&mut writer, preserve_markup);
            rw.feed_text(text.as_ref());
            let stats = rw.finish()?;
            writer.flush()?;
            stats
        }
        None => {
            let mut sink = io::sink();
            let mut rw = FastRewriter::new(&mut sink, preserve_markup);
            rw.set_inspect_only(true);
            rw.feed_text(text.as_ref());
            rw.finish()?
        }
    };

    progress.finish("clean done");
    Ok(stats)
}

/// Subcommand entry: parses subcommand-specific args off the supplied list.
///
/// Returns the path to write the output to (Some) or None if `--inspect`.
pub fn run_subcommand(
    args: &[std::ffi::OsString],
) -> Result<(), String> {
    let parsed = crate::cli::parse(
        args,
        &["preserve-markup", "inspect"],
        &["input", "output"],
    )
    .map_err(|e| e.to_string())?;

    let preserve = parsed.has_flag("preserve-markup");
    let inspect = parsed.has_flag("inspect");

    // Support both flag-form (`--input X --output Y`) and positional form
    // (`clean INPUT OUTPUT` or `clean --inspect INPUT`).
    let mut input: Option<PathBuf> = parsed.get_kv("input").map(PathBuf::from);
    let mut output: Option<PathBuf> = parsed.get_kv("output").map(PathBuf::from);

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

    let input = input.ok_or_else(|| "clean: missing input path".to_string())?;
    if inspect && output.is_some() {
        return Err("clean: --inspect cannot be combined with an output path".to_string());
    }
    if !inspect && output.is_none() {
        return Err("clean: missing output path (use --inspect to scan only)".to_string());
    }

    let stats = run_clean(
        &input,
        output.as_deref(),
        preserve,
        !parsed.global.no_progress,
    )
    .map_err(|e| format!("clean failed: {e}"))?;

    println!("{}", stats.to_json());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

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
