//! `concat` subcommand: combine multiple PGN sources into one output.
//!
//! Inputs may be files or directories; directories are walked recursively
//! for `*.pgn` (case-insensitive) and visited in deterministic, sorted order
//! so output is reproducible. Output goes to `--output PATH` or stdout.
//!
//! Optional flags:
//!   --clean   pipe each input through the same lexical rewriter as `clean`
//!   --dedup   skip games whose normalized movetext was already emitted
//!
//! All four combinations work; `--clean --dedup` materializes the cleaned
//! bytes per-file (necessary so the splitter can scan them). For multi-GB
//! inputs prefer a two-step pipeline (`clean` then `concat --dedup`).

use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, BufWriter, Cursor, Read, Write};
use std::path::{Path, PathBuf};

use xxhash_rust::xxh3::xxh3_64;

use crate::clean::rewrite_to_vec;
use crate::pgn_split::GameSplitter;
use crate::progress::ProgressReporter;

#[derive(Debug, Default, Clone, Copy)]
pub struct ConcatStats {
    pub files_processed: usize,
    pub bytes_in: u64,
    pub games_written: usize,
    pub duplicates_removed: usize,
}

impl ConcatStats {
    pub fn to_json(&self) -> String {
        format!(
            "{{\"files_processed\":{},\"bytes_in\":{},\"games_written\":{},\"duplicates_removed\":{}}}",
            self.files_processed, self.bytes_in, self.games_written, self.duplicates_removed,
        )
    }
}

#[derive(Debug, Default, Clone)]
pub struct ConcatOptions {
    pub inputs: Vec<PathBuf>,
    pub output: Option<PathBuf>,
    pub clean: bool,
    pub dedup: bool,
    pub show_progress: bool,
}

/// Expand the user-supplied paths: directories are walked recursively for
/// `.pgn` files, and the result is sorted for stability.
pub fn expand_inputs(inputs: &[PathBuf]) -> io::Result<Vec<PathBuf>> {
    let mut out: Vec<PathBuf> = Vec::new();
    for path in inputs {
        let meta = fs::metadata(path)?;
        if meta.is_dir() {
            walk_pgn_dir(path, &mut out)?;
        } else {
            out.push(path.clone());
        }
    }
    out.sort();
    Ok(out)
}

fn walk_pgn_dir(dir: &Path, out: &mut Vec<PathBuf>) -> io::Result<()> {
    let mut entries: Vec<PathBuf> = fs::read_dir(dir)?
        .map(|e| e.map(|e| e.path()))
        .collect::<io::Result<Vec<_>>>()?;
    entries.sort();
    for entry in entries {
        if entry.is_dir() {
            walk_pgn_dir(&entry, out)?;
        } else if has_pgn_ext(&entry) {
            out.push(entry);
        }
    }
    Ok(())
}

fn has_pgn_ext(path: &Path) -> bool {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|e| e.eq_ignore_ascii_case("pgn"))
        .unwrap_or(false)
}

pub fn run_concat(opts: ConcatOptions) -> io::Result<ConcatStats> {
    let files = expand_inputs(&opts.inputs)?;
    let total_bytes: u64 = files
        .iter()
        .map(|p| fs::metadata(p).map(|m| m.len()).unwrap_or(0))
        .sum();

    let progress = ProgressReporter::bytes(total_bytes, "concat", opts.show_progress);

    let mut writer: Box<dyn Write> = match opts.output.as_deref() {
        Some(p) => Box::new(BufWriter::new(File::create(p)?)),
        None => Box::new(BufWriter::new(io::stdout().lock())),
    };

    let mut stats = ConcatStats {
        files_processed: 0,
        bytes_in: 0,
        games_written: 0,
        duplicates_removed: 0,
    };
    let mut seen_hashes: Option<std::collections::HashSet<u64>> =
        if opts.dedup { Some(Default::default()) } else { None };

    for path in &files {
        let file_size = fs::metadata(path)?.len();
        stats.bytes_in += file_size;
        stats.files_processed += 1;

        if opts.clean {
            // Read the whole file, run FastRewriter into a buffer, then either
            // stream that buffer into the output (no dedup) or split it into
            // games for dedup.
            let f = File::open(path)?;
            let mut reader = progress.wrap(f);
            let mut bytes = Vec::with_capacity(file_size as usize);
            reader.read_to_end(&mut bytes)?;
            let text = String::from_utf8_lossy(&bytes);
            let (cleaned, _clean_stats) = rewrite_to_vec(text.as_ref(), false)?;
            if let Some(seen) = seen_hashes.as_mut() {
                emit_games_with_dedup(&cleaned, seen, &mut writer, &mut stats)?;
            } else {
                emit_raw_normalized(&cleaned, &mut writer)?;
                stats.games_written += count_games(&cleaned);
            }
        } else if let Some(seen) = seen_hashes.as_mut() {
            // Dedup but no clean: stream split directly from the file.
            let f = File::open(path)?;
            let reader = BufReader::new(progress.wrap(f));
            let mut splitter_buf: Vec<u8> = Vec::new();
            // We need the full bytes for emit_games_with_dedup so we can preserve
            // each game's exact text. Read into a Vec then split.
            let mut r = reader;
            r.read_to_end(&mut splitter_buf)?;
            emit_games_with_dedup(&splitter_buf, seen, &mut writer, &mut stats)?;
        } else {
            // Raw streaming pass-through with normalized blank-line separator.
            let f = File::open(path)?;
            let reader = BufReader::new(progress.wrap(f));
            let games_in_file = stream_normalized(reader, &mut writer)?;
            stats.games_written += games_in_file;
        }
    }

    writer.flush()?;
    progress.finish("concat done");
    Ok(stats)
}

/// Stream a reader into `out`, replacing trailing whitespace with a single
/// `\n\n` separator so games from successive files don't run together.
/// Returns an estimate of games (number of `[Event ` lines seen).
fn stream_normalized<R: BufRead, W: Write>(mut reader: R, out: &mut W) -> io::Result<usize> {
    let mut games = 0usize;
    let mut trailing_newlines = 0usize;
    let mut had_any_content = false;
    let mut line_buf: Vec<u8> = Vec::new();

    loop {
        line_buf.clear();
        let n = reader.read_until(b'\n', &mut line_buf)?;
        if n == 0 {
            break;
        }
        let line = strip_eol(&line_buf);
        if line.is_empty() {
            if had_any_content {
                trailing_newlines += 1;
            }
            continue;
        }

        // Flush pending blank lines (collapsed to one) before the next line.
        if had_any_content && trailing_newlines > 0 {
            out.write_all(b"\n\n")?;
            trailing_newlines = 0;
        } else if had_any_content {
            out.write_all(b"\n")?;
        }

        out.write_all(line)?;
        had_any_content = true;

        if is_event_line(line) {
            games += 1;
        }
    }
    if had_any_content {
        out.write_all(b"\n\n")?;
    }
    Ok(games)
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
    let t = trim_ascii_start(line);
    t.starts_with(b"[Event ") || t.starts_with(b"[Event\t")
}

fn trim_ascii_start(s: &[u8]) -> &[u8] {
    let mut i = 0;
    while i < s.len() && (s[i] == b' ' || s[i] == b'\t') {
        i += 1;
    }
    &s[i..]
}

fn emit_raw_normalized<W: Write>(bytes: &[u8], out: &mut W) -> io::Result<()> {
    stream_normalized(Cursor::new(bytes), out).map(|_| ())
}

fn count_games(bytes: &[u8]) -> usize {
    let mut count = 0usize;
    let mut at_line_start = true;
    let mut i = 0usize;
    while i < bytes.len() {
        if at_line_start {
            // Skip leading whitespace.
            let mut j = i;
            while j < bytes.len() && (bytes[j] == b' ' || bytes[j] == b'\t') {
                j += 1;
            }
            if bytes[j..].starts_with(b"[Event ") || bytes[j..].starts_with(b"[Event\t") {
                count += 1;
            }
        }
        at_line_start = bytes[i] == b'\n';
        i += 1;
    }
    count
}

fn emit_games_with_dedup<W: Write>(
    bytes: &[u8],
    seen: &mut std::collections::HashSet<u64>,
    out: &mut W,
    stats: &mut ConcatStats,
) -> io::Result<()> {
    let splitter = GameSplitter::new(Cursor::new(bytes));
    for game in splitter {
        let game = game?;
        let normalized = game.normalized_movetext();
        let key = xxh3_64(&normalized);
        if !seen.insert(key) {
            stats.duplicates_removed += 1;
            continue;
        }
        write_game_normalized(&game.bytes, out)?;
        stats.games_written += 1;
    }
    Ok(())
}

fn write_game_normalized<W: Write>(bytes: &[u8], out: &mut W) -> io::Result<()> {
    // Trim trailing whitespace and emit `\n\n` separator for consistency.
    let mut end = bytes.len();
    while end > 0 {
        let c = bytes[end - 1];
        if c == b'\n' || c == b'\r' || c == b' ' || c == b'\t' {
            end -= 1;
        } else {
            break;
        }
    }
    out.write_all(&bytes[..end])?;
    out.write_all(b"\n\n")?;
    Ok(())
}

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    let parsed =
        crate::cli::parse(args, &["clean", "dedup"], &["output", "o"]).map_err(|e| e.to_string())?;
    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);
    if parsed.positionals.is_empty() {
        return Err("concat: no input files supplied".to_string());
    }
    let opts = ConcatOptions {
        inputs: parsed.positionals.clone(),
        output,
        clean: parsed.has_flag("clean"),
        dedup: parsed.has_flag("dedup"),
        show_progress: !parsed.global.no_progress,
    };
    let stats = run_concat(opts).map_err(|e| format!("concat failed: {e}"))?;
    println!("{}", stats.to_json());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn stream_normalized_collapses_blank_lines() {
        let input = b"[Event \"a\"]\n[Result \"1-0\"]\n\n\n\n1. e4 1-0\n";
        let mut out = Vec::new();
        let games = stream_normalized(Cursor::new(input), &mut out).unwrap();
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("[Event \"a\"]\n[Result \"1-0\"]\n\n1. e4 1-0\n\n"));
        assert!(!s.contains("\n\n\n"));
        assert_eq!(games, 1);
    }

    #[test]
    fn count_games_counts_event_lines() {
        let bytes = b"[Event \"a\"]\n\n1. e4 1-0\n\n[Event \"b\"]\n\n1. d4 1-0\n";
        assert_eq!(count_games(bytes), 2);
    }

    #[test]
    fn emit_games_with_dedup_skips_duplicates() {
        let bytes = b"[Event \"a\"]\n\n1. e4 e5 1-0\n\n[Event \"a-dup\"]\n\n1. e4 e5 1-0\n\n[Event \"b\"]\n\n1. d4 d5 1-0\n";
        let mut seen = std::collections::HashSet::new();
        let mut out = Vec::new();
        let mut stats = ConcatStats::default();
        emit_games_with_dedup(bytes, &mut seen, &mut out, &mut stats).unwrap();
        assert_eq!(stats.games_written, 2);
        assert_eq!(stats.duplicates_removed, 1);
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("[Event \"a\"]"));
        assert!(s.contains("[Event \"b\"]"));
        assert!(!s.contains("[Event \"a-dup\"]"));
    }
}
