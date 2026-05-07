//! `dedup` subcommand: drop duplicate games by normalized movetext.
//!
//! Streams the input file game-by-game (no whole-file buffering), hashes the
//! normalized movetext (move numbers / comments / variations / NAGs / result
//! tokens stripped, whitespace collapsed) with xxh3-64, and emits each game
//! only on first occurrence. The hash table holds 8 bytes per unique game,
//! so even ten million games fit comfortably in memory.
//!
//! Collisions on xxh3-64 are vanishingly rare for ~10⁷ entries (birthday
//! probability ≈ 10⁻⁵). For workloads where any false positive is
//! unacceptable, run the user-facing flow twice with two different keys.

use std::collections::HashSet;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{self, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};

use xxhash_rust::xxh3::xxh3_64;

use crate::pgn_split::GameSplitter;
use crate::progress::ProgressReporter;

#[derive(Debug, Default, Clone, Copy)]
pub struct DedupStats {
    pub games_seen: usize,
    pub games_written: usize,
    pub duplicates_removed: usize,
}

impl DedupStats {
    pub fn to_json(&self) -> String {
        format!(
            "{{\"games_seen\":{},\"games_written\":{},\"duplicates_removed\":{}}}",
            self.games_seen, self.games_written, self.duplicates_removed
        )
    }
}

pub fn run_dedup(
    input_path: &Path,
    output_path: Option<&Path>,
    show_progress: bool,
) -> io::Result<DedupStats> {
    let total_bytes = fs::metadata(input_path)?.len();
    let progress = ProgressReporter::bytes(total_bytes, "dedup", show_progress);

    let file = File::open(input_path)?;
    let reader = BufReader::new(progress.wrap(file));

    let mut writer: Box<dyn Write> = match output_path {
        Some(p) => Box::new(BufWriter::new(File::create(p)?)),
        None => Box::new(BufWriter::new(io::stdout().lock())),
    };

    let stats = dedup_stream(reader, &mut writer)?;
    writer.flush()?;
    progress.finish("dedup done");
    Ok(stats)
}

/// Read games from `reader`, write unique games to `writer`. Pulled out of
/// `run_dedup` so the unit tests can exercise it without touching the
/// filesystem.
pub fn dedup_stream<R: io::BufRead, W: Write>(
    reader: R,
    writer: &mut W,
) -> io::Result<DedupStats> {
    let mut seen: HashSet<u64> = HashSet::new();
    let mut stats = DedupStats::default();

    for game in GameSplitter::new(reader) {
        let game = game?;
        stats.games_seen += 1;

        let normalized = game.normalized_movetext();
        let key = xxh3_64(&normalized);
        if !seen.insert(key) {
            stats.duplicates_removed += 1;
            continue;
        }

        let mut end = game.bytes.len();
        while end > 0 {
            let c = game.bytes[end - 1];
            if c == b'\n' || c == b'\r' || c == b' ' || c == b'\t' {
                end -= 1;
            } else {
                break;
            }
        }
        writer.write_all(&game.bytes[..end])?;
        writer.write_all(b"\n\n")?;
        stats.games_written += 1;
    }

    Ok(stats)
}

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    let parsed = crate::cli::parse(args, &[], &["output", "o"]).map_err(|e| e.to_string())?;
    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);
    if parsed.positionals.len() != 1 {
        return Err("dedup: expected exactly one input path".to_string());
    }
    let input = &parsed.positionals[0];
    let stats = run_dedup(input, output.as_deref(), !parsed.global.no_progress)
        .map_err(|e| format!("dedup failed: {e}"))?;
    println!("{}", stats.to_json());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn keeps_first_drops_subsequent_duplicates() {
        let pgn = b"[Event \"a\"]\n[White \"X\"]\n\n1. e4 e5 1-0\n\n[Event \"a\"]\n[White \"Y\"]\n\n1. e4 e5 1-0\n\n[Event \"b\"]\n\n1. d4 d5 1-0\n";
        let mut out = Vec::new();
        let stats = dedup_stream(Cursor::new(pgn), &mut out).unwrap();
        assert_eq!(stats.games_seen, 3);
        assert_eq!(stats.games_written, 2);
        assert_eq!(stats.duplicates_removed, 1);
        let s = String::from_utf8(out).unwrap();
        assert!(s.contains("[White \"X\"]"));
        assert!(!s.contains("[White \"Y\"]"));
        assert!(s.contains("[Event \"b\"]"));
    }

    #[test]
    fn dedup_ignores_header_differences_when_movetext_matches() {
        let pgn = b"[Event \"a\"]\n[White \"Alice\"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n\n[Event \"b\"]\n[White \"Bob\"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n";
        let mut out = Vec::new();
        let stats = dedup_stream(Cursor::new(pgn), &mut out).unwrap();
        assert_eq!(stats.games_written, 1);
        assert_eq!(stats.duplicates_removed, 1);
    }

    #[test]
    fn dedup_keeps_distinct_movetexts() {
        let pgn = b"[Event \"a\"]\n\n1. e4 e5 1-0\n\n[Event \"b\"]\n\n1. d4 d5 1-0\n";
        let mut out = Vec::new();
        let stats = dedup_stream(Cursor::new(pgn), &mut out).unwrap();
        assert_eq!(stats.games_written, 2);
        assert_eq!(stats.duplicates_removed, 0);
    }

    #[test]
    fn dedup_normalizes_comments_and_variations() {
        let pgn = b"[Event \"a\"]\n\n1. e4 {good} e5 1-0\n\n[Event \"b\"]\n\n1. e4 (1. d4) e5 1-0\n";
        let mut out = Vec::new();
        let stats = dedup_stream(Cursor::new(pgn), &mut out).unwrap();
        // Both reduce to "e4 e5" -> duplicates.
        assert_eq!(stats.games_written, 1);
        assert_eq!(stats.duplicates_removed, 1);
    }
}
