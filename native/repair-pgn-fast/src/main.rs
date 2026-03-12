use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;

struct FastRewriter {
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
    output: String,
}

impl FastRewriter {
    fn new(capacity: usize) -> Self {
        Self {
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
            output: String::with_capacity(capacity),
        }
    }

    fn feed_text(&mut self, text: &str) {
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

            if self.recovery_armed && ch == '[' {
                self.in_comment = false;
                self.variation_depth = 0;
                self.recovery_armed = false;
            }
        }

        if self.skip_line_comment {
            return;
        }

        if self.header_line {
            self.line_output.push(ch);
            return;
        }

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

        if self.line_start {
            if ch == '[' {
                self.header_line = true;
                self.line_output.push_str(&self.leading_whitespace);
                self.leading_whitespace.clear();
                self.line_output.push(ch);
                self.line_start = false;
                return;
            }

            if ch == '%' || ch == ';' {
                self.line_comments_removed += 1;
                self.skip_line_comment = true;
                self.leading_whitespace.clear();
                self.line_start = false;
                return;
            }

            self.leading_whitespace.clear();
            self.line_start = false;
        }

        match ch {
            '{' => {
                self.finish_token();
                self.comments_removed += 1;
                self.in_comment = true;
            }
            '(' => {
                self.finish_token();
                self.variations_removed += 1;
                self.variation_depth = 1;
            }
            ';' => {
                self.finish_token();
                self.line_comments_removed += 1;
                self.skip_line_comment = true;
            }
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

        if !self.line_output.is_empty() {
            self.output.push_str(&self.line_output);
        }
        if had_newline {
            self.output.push('\n');
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

    fn finish(mut self) -> Self {
        if !self.line_output.is_empty() || self.header_line {
            self.finish_line(false);
        }

        self.write_missing_result(false);
        if self.games_written == 0 && self.saw_nonwhitespace_output {
            self.games_written = 1;
        }

        self
    }

    fn json_stats(&self) -> String {
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
            self.line_comments_removed
        )
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

        if before_new_game {
            self.output.push_str("*\n\n");
        } else {
            self.output.push_str("*\n");
        }
        self.current_game_has_result = true;
        self.saw_nonwhitespace_output = true;
    }
}

fn run(input_path: PathBuf, output_path: PathBuf) -> Result<(), String> {
    let bytes = fs::read(&input_path).map_err(|err| format!("read failed: {err}"))?;
    let text = String::from_utf8_lossy(&bytes);
    let mut rewriter = FastRewriter::new(bytes.len());
    rewriter.feed_text(text.as_ref());
    let rewriter = rewriter.finish();
    fs::write(&output_path, rewriter.output.as_bytes())
        .map_err(|err| format!("write failed: {err}"))?;
    io::stdout()
        .write_all(rewriter.json_stats().as_bytes())
        .map_err(|err| format!("stdout failed: {err}"))?;
    Ok(())
}

fn main() {
    let mut args = env::args_os();
    let _program = args.next();
    let input_path = match args.next() {
        Some(value) => PathBuf::from(value),
        None => {
            eprintln!("usage: reti-fast-pgn-repair INPUT_PGN OUTPUT_PGN");
            std::process::exit(2);
        }
    };
    let output_path = match args.next() {
        Some(value) => PathBuf::from(value),
        None => {
            eprintln!("usage: reti-fast-pgn-repair INPUT_PGN OUTPUT_PGN");
            std::process::exit(2);
        }
    };

    if let Err(message) = run(input_path, output_path) {
        eprintln!("{message}");
        std::process::exit(1);
    }
}
