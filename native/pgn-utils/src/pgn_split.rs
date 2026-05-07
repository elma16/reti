//! Streaming PGN game splitter.
//!
//! Reads from any `BufRead` and yields one [`Game`] per `[Event ` boundary.
//! Anything before the first `[Event` line (BOM, leading whitespace, garbage)
//! is treated as preamble and dropped — callers that care about preamble
//! (e.g. byte-exact concat) should not use the splitter.
//!
//! The splitter is byte-oriented so it works on PGNs that have already been
//! cleaned and on raw files alike. Each yielded `Game` includes the source
//! line number where it began so lint diagnostics can be precise.

use std::io::{self, BufRead};

/// One PGN game as raw bytes plus its location in the source.
#[derive(Debug, Clone)]
pub struct Game {
    pub bytes: Vec<u8>,
    /// 1-based line number of the `[Event ...]` line that opened this game.
    pub start_line: usize,
}

impl Game {
    /// Look up a header value (case-sensitive on the tag name, like real PGN).
    /// Returns the unquoted value, or None if the tag is absent.
    pub fn header(&self, key: &str) -> Option<String> {
        for line in split_lines(&self.bytes) {
            let trimmed = trim_ascii_start(line);
            if !trimmed.starts_with(b"[") {
                if !trimmed.is_empty() {
                    // Past the header section once we hit a non-tag, non-blank line.
                    return None;
                }
                continue;
            }
            let inner = &trimmed[1..];
            let space = inner.iter().position(|&b| b == b' ' || b == b'\t')?;
            let name = &inner[..space];
            if name != key.as_bytes() {
                continue;
            }
            let rest = &inner[space + 1..];
            // Header value is the first quoted string.
            let q1 = rest.iter().position(|&b| b == b'"')?;
            let after = &rest[q1 + 1..];
            let q2 = after.iter().position(|&b| b == b'"')?;
            return Some(String::from_utf8_lossy(&after[..q2]).into_owned());
        }
        None
    }

    /// Split this game into `(headers_bytes, movetext_bytes)`. The split point
    /// is the first non-tag, non-blank line after one or more tag lines.
    pub fn split_headers_movetext(&self) -> (&[u8], &[u8]) {
        let mut i = 0usize;
        let mut last_tag_end = 0usize;
        let bytes = &self.bytes;
        while i < bytes.len() {
            let line_start = i;
            // Find end of current line.
            while i < bytes.len() && bytes[i] != b'\n' {
                i += 1;
            }
            let line = &bytes[line_start..i];
            let trimmed = trim_ascii_start(line);
            if trimmed.starts_with(b"[") {
                last_tag_end = i + (i < bytes.len()) as usize; // include trailing \n
            } else if !trimmed.is_empty() {
                // Movetext line.
                return (&bytes[..last_tag_end], &bytes[line_start..]);
            }
            if i < bytes.len() {
                i += 1; // consume newline
            }
        }
        (bytes, &[])
    }

    pub fn movetext(&self) -> &[u8] {
        self.split_headers_movetext().1
    }

    /// Build a normalized form of the movetext suitable for hashing.
    /// Strips comments, variations, line comments, NAGs, move numbers, and
    /// whitespace; the resulting bytes are the canonical SAN sequence.
    pub fn normalized_movetext(&self) -> Vec<u8> {
        normalize_movetext(self.movetext())
    }
}

/// Iterator over games. See module docs.
pub struct GameSplitter<R: BufRead> {
    reader: R,
    line_no: usize,
    pending: Option<(Vec<u8>, usize)>, // (line bytes, line number)
    started: bool,
    eof: bool,
    cur_buf: Vec<u8>,
    cur_start_line: usize,
}

impl<R: BufRead> GameSplitter<R> {
    pub fn new(reader: R) -> Self {
        Self {
            reader,
            line_no: 0,
            pending: None,
            started: false,
            eof: false,
            cur_buf: Vec::new(),
            cur_start_line: 0,
        }
    }

    fn read_line(&mut self) -> io::Result<Option<(Vec<u8>, usize)>> {
        if let Some(p) = self.pending.take() {
            return Ok(Some(p));
        }
        if self.eof {
            return Ok(None);
        }
        let mut buf = Vec::new();
        let n = self.reader.read_until(b'\n', &mut buf)?;
        if n == 0 {
            self.eof = true;
            return Ok(None);
        }
        self.line_no += 1;
        Ok(Some((buf, self.line_no)))
    }
}

fn is_event_header(line: &[u8]) -> bool {
    let t = trim_ascii_start(line);
    t.starts_with(b"[Event ") || t.starts_with(b"[Event\t")
}

impl<R: BufRead> Iterator for GameSplitter<R> {
    type Item = io::Result<Game>;

    fn next(&mut self) -> Option<Self::Item> {
        loop {
            let (line, lineno) = match self.read_line() {
                Ok(Some(x)) => x,
                Ok(None) => {
                    if self.started && !self.cur_buf.is_empty() {
                        let bytes = std::mem::take(&mut self.cur_buf);
                        let start = self.cur_start_line;
                        self.started = false;
                        return Some(Ok(Game {
                            bytes,
                            start_line: start,
                        }));
                    }
                    return None;
                }
                Err(e) => return Some(Err(e)),
            };

            if is_event_header(&line) {
                if self.started && !self.cur_buf.is_empty() {
                    // Stash this header line as the start of the *next* game.
                    self.pending = Some((line, lineno));
                    let bytes = std::mem::take(&mut self.cur_buf);
                    let start = self.cur_start_line;
                    return Some(Ok(Game {
                        bytes,
                        start_line: start,
                    }));
                } else {
                    self.started = true;
                    self.cur_start_line = lineno;
                    self.cur_buf.extend_from_slice(&line);
                }
            } else if self.started {
                self.cur_buf.extend_from_slice(&line);
            }
            // else: pre-Event preamble, drop on the floor.
        }
    }
}

fn trim_ascii_start(s: &[u8]) -> &[u8] {
    let mut i = 0;
    while i < s.len() && (s[i] == b' ' || s[i] == b'\t') {
        i += 1;
    }
    &s[i..]
}

fn split_lines(bytes: &[u8]) -> impl Iterator<Item = &[u8]> {
    bytes.split(|&b| b == b'\n').map(|line| {
        if let Some(stripped) = line.strip_suffix(b"\r") {
            stripped
        } else {
            line
        }
    })
}

/// Normalize movetext for dedup/hashing. Strips comments, variations, NAGs,
/// move numbers, and result tokens; collapses whitespace; preserves SAN.
pub fn normalize_movetext(movetext: &[u8]) -> Vec<u8> {
    let mut out: Vec<u8> = Vec::with_capacity(movetext.len() / 2);
    let mut i = 0usize;
    let mut depth: usize = 0; // (...) variation depth
    let mut in_brace = false; // {...} comment
    let mut skip_eol = false; // ; or % comment

    let mut token: Vec<u8> = Vec::with_capacity(8);

    let flush_token = |token: &mut Vec<u8>, out: &mut Vec<u8>| {
        if token.is_empty() {
            return;
        }
        let t = token.as_slice();

        // Drop result tokens.
        if t == b"1-0" || t == b"0-1" || t == b"1/2-1/2" || t == b"*" {
            token.clear();
            return;
        }
        // Drop NAGs ($N).
        if t.first() == Some(&b'$') {
            token.clear();
            return;
        }
        // Drop move numbers (e.g. "1.", "1...", "12.", "12...").
        if t.iter().all(|&b| b.is_ascii_digit() || b == b'.') {
            token.clear();
            return;
        }

        if !out.is_empty() {
            out.push(b' ');
        }
        out.extend_from_slice(t);
        token.clear();
    };

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
            b'{' => {
                flush_token(&mut token, &mut out);
                in_brace = true;
            }
            b'(' => {
                flush_token(&mut token, &mut out);
                depth = 1;
            }
            b';' => {
                flush_token(&mut token, &mut out);
                skip_eol = true;
            }
            b'%' if i == 0 || movetext[i - 1] == b'\n' => {
                flush_token(&mut token, &mut out);
                skip_eol = true;
            }
            b' ' | b'\t' | b'\r' | b'\n' => {
                flush_token(&mut token, &mut out);
            }
            _ => {
                token.push(c);
            }
        }
        i += 1;
    }
    flush_token(&mut token, &mut out);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn split_all(input: &[u8]) -> Vec<Game> {
        GameSplitter::new(Cursor::new(input))
            .collect::<io::Result<Vec<_>>>()
            .unwrap()
    }

    #[test]
    fn splits_two_games_at_event_boundary() {
        let pgn = b"[Event \"a\"]\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n\n[Event \"b\"]\n[Result \"0-1\"]\n\n1. d4 d5 0-1\n";
        let games = split_all(pgn);
        assert_eq!(games.len(), 2);
        assert_eq!(games[0].header("Event").as_deref(), Some("a"));
        assert_eq!(games[1].header("Event").as_deref(), Some("b"));
    }

    #[test]
    fn skips_preamble_before_first_event() {
        let pgn = b"; some comment\n\n[Event \"a\"]\n\n1. e4 1-0\n";
        let games = split_all(pgn);
        assert_eq!(games.len(), 1);
        assert_eq!(games[0].header("Event").as_deref(), Some("a"));
    }

    #[test]
    fn header_extraction() {
        let pgn = b"[Event \"x\"]\n[White \"Alice\"]\n[Black \"Bob\"]\n[Result \"1-0\"]\n\n1. e4 1-0\n";
        let games = split_all(pgn);
        assert_eq!(games[0].header("White").as_deref(), Some("Alice"));
        assert_eq!(games[0].header("Black").as_deref(), Some("Bob"));
        assert_eq!(games[0].header("Result").as_deref(), Some("1-0"));
        assert_eq!(games[0].header("Missing"), None);
    }

    #[test]
    fn split_headers_movetext_works() {
        let pgn = b"[Event \"x\"]\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n";
        let games = split_all(pgn);
        let (h, m) = games[0].split_headers_movetext();
        assert!(std::str::from_utf8(h).unwrap().contains("[Event"));
        assert!(std::str::from_utf8(m).unwrap().contains("1. e4"));
    }

    #[test]
    fn normalize_strips_comments_variations_numbers_results() {
        let mv = b"1. e4 {good} (1. d4 d5) e5 2. Nf3 Nc6 1-0";
        let n = normalize_movetext(mv);
        assert_eq!(std::str::from_utf8(&n).unwrap(), "e4 e5 Nf3 Nc6");
    }

    #[test]
    fn normalize_drops_nags_and_line_comments() {
        let mv = b"1. e4 $1 e5 ; trailing comment\n2. Nf3 *";
        let n = normalize_movetext(mv);
        assert_eq!(std::str::from_utf8(&n).unwrap(), "e4 e5 Nf3");
    }

    #[test]
    fn normalize_handles_nested_variations() {
        let mv = b"1. e4 (1. d4 (1. c4 c5) d5) e5 1-0";
        let n = normalize_movetext(mv);
        assert_eq!(std::str::from_utf8(&n).unwrap(), "e4 e5");
    }

    #[test]
    fn line_numbers_are_tracked() {
        let pgn = b"\n\n[Event \"a\"]\n\n1. e4 1-0\n\n[Event \"b\"]\n\n1. d4 1-0\n";
        let games = split_all(pgn);
        assert_eq!(games[0].start_line, 3);
        assert_eq!(games[1].start_line, 7);
    }
}
