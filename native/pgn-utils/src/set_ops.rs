//! `set` subcommand: set operations over two PGN sources.
//!
//!   pgn-utils set <intersect|union|diff> A B [-o OUT]
//!
//! `A` and `B` may each be a file, a directory (walked recursively for
//! `*.pgn`), or `-` for stdin. Two games are considered equal when their bytes
//! are identical (after trimming trailing whitespace / the inter-game blank
//! line), so re-formatted or re-annotated copies count as different — pick the
//! `clean` step first if you want format-insensitive comparison.
//!
//!   intersect  games present in both A and B (A's copy is emitted)
//!   union      every distinct game from A and B
//!   diff       games in A that are not in B (A − B)
//!
//! Output is deduplicated (a set), pipe-friendly (`-o`/stdout with the
//! terminal-flood guard), and the JSON stats line goes to stderr when the
//! result streams to stdout.

use std::collections::HashSet;
use std::ffi::OsString;
use std::io::{self, BufReader, Write};
use std::path::PathBuf;

use xxhash_rust::xxh3::xxh3_64;

use crate::pgn_split::GameSplitter;
use crate::progress::ProgressReporter;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Op {
    Intersect,
    Union,
    Diff,
}

impl Op {
    fn parse(s: &str) -> Option<Op> {
        match s {
            "intersect" | "intersection" | "and" => Some(Op::Intersect),
            "union" | "or" => Some(Op::Union),
            "diff" | "difference" | "minus" => Some(Op::Diff),
            _ => None,
        }
    }

    fn label(self) -> &'static str {
        match self {
            Op::Intersect => "intersect",
            Op::Union => "union",
            Op::Diff => "diff",
        }
    }
}

#[derive(Debug, Default, Clone, Copy)]
pub struct SetStats {
    pub a_games: usize,
    pub b_games: usize,
    pub result_games: usize,
}

impl SetStats {
    pub fn to_json(&self, op: Op) -> String {
        format!(
            "{{\"op\":\"{}\",\"a_games\":{},\"b_games\":{},\"result_games\":{}}}",
            op.label(),
            self.a_games,
            self.b_games,
            self.result_games,
        )
    }
}

/// Identity key: xxh3 of the game's bytes with trailing whitespace stripped, so
/// the inter-game separator never affects equality but the content is exact.
fn game_key(bytes: &[u8]) -> u64 {
    xxh3_64(trim_end(bytes))
}

fn trim_end(bytes: &[u8]) -> &[u8] {
    let mut end = bytes.len();
    while end > 0 {
        match bytes[end - 1] {
            b'\n' | b'\r' | b' ' | b'\t' => end -= 1,
            _ => break,
        }
    }
    &bytes[..end]
}

/// Emit a game with a normalized trailing `\n\n` separator.
fn emit_game<W: Write>(bytes: &[u8], out: &mut W) -> io::Result<()> {
    out.write_all(trim_end(bytes))?;
    out.write_all(b"\n\n")?;
    Ok(())
}

/// Call `f` once per game across all of `paths` (files / `-` stdin), advancing
/// the shared progress bar as bytes are read.
fn for_each_game<F>(paths: &[PathBuf], progress: &ProgressReporter, mut f: F) -> io::Result<()>
where
    F: FnMut(&[u8]) -> io::Result<()>,
{
    for path in paths {
        let (reader, _len) = crate::output::open_input(path)?;
        let reader = BufReader::new(progress.wrap(reader));
        for game in GameSplitter::new(reader) {
            let game = game?;
            f(&game.bytes)?;
        }
    }
    Ok(())
}

pub fn run_set(
    op: Op,
    a: &PathBuf,
    b: &PathBuf,
    output: Option<&std::path::Path>,
    show_progress: bool,
) -> io::Result<(SetStats, bool)> {
    let a_files = crate::concat::expand_inputs(std::slice::from_ref(a))?;
    let b_files = crate::concat::expand_inputs(std::slice::from_ref(b))?;

    // Resolve the destination first so the terminal-flood guard fires before we
    // start reading either side.
    let sink = crate::output::open_output(output, "set")?;
    let stats_to_stderr = sink.stats_to_stderr;
    let mut writer = sink.writer;

    let has_stdin = a_files
        .iter()
        .chain(b_files.iter())
        .any(|p| crate::output::is_stdin_path(p));
    let total_bytes: u64 = a_files
        .iter()
        .chain(b_files.iter())
        .filter(|p| !crate::output::is_stdin_path(p))
        .map(|p| std::fs::metadata(p).map(|m| m.len()).unwrap_or(0))
        .sum();
    let progress = ProgressReporter::maybe_bytes(
        if has_stdin { None } else { Some(total_bytes) },
        "set",
        show_progress,
    );

    let mut stats = SetStats::default();

    match op {
        Op::Union => {
            let mut seen: HashSet<u64> = HashSet::new();
            for_each_game(&a_files, &progress, |bytes| {
                stats.a_games += 1;
                if seen.insert(game_key(bytes)) {
                    stats.result_games += 1;
                    emit_game(bytes, &mut writer)?;
                }
                Ok(())
            })?;
            for_each_game(&b_files, &progress, |bytes| {
                stats.b_games += 1;
                if seen.insert(game_key(bytes)) {
                    stats.result_games += 1;
                    emit_game(bytes, &mut writer)?;
                }
                Ok(())
            })?;
        }
        Op::Intersect | Op::Diff => {
            // Load B's keys, then stream A and emit per the operation. Output is
            // deduplicated so each distinct game appears at most once.
            let mut b_keys: HashSet<u64> = HashSet::new();
            for_each_game(&b_files, &progress, |bytes| {
                stats.b_games += 1;
                b_keys.insert(game_key(bytes));
                Ok(())
            })?;

            let mut emitted: HashSet<u64> = HashSet::new();
            for_each_game(&a_files, &progress, |bytes| {
                stats.a_games += 1;
                let key = game_key(bytes);
                let in_b = b_keys.contains(&key);
                let keep = match op {
                    Op::Intersect => in_b,
                    Op::Diff => !in_b,
                    Op::Union => unreachable!(),
                };
                if keep && emitted.insert(key) {
                    stats.result_games += 1;
                    emit_game(bytes, &mut writer)?;
                }
                Ok(())
            })?;
        }
    }

    writer.flush()?;
    progress.finish("set done");
    Ok((stats, stats_to_stderr))
}

const USAGE: &str = "\
usage: pgn-utils set <intersect|union|diff> A B [-o OUT]
  A and B may be files, directories, or - for stdin.
  intersect  games in both A and B        union  every distinct game
  diff       games in A but not in B (A - B)";

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    let parsed = crate::cli::parse(args, &[], &["output", "o"]).map_err(|e| e.to_string())?;
    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);

    if parsed.positionals.len() != 3 {
        return Err(format!("set: expected OP A B\n{USAGE}"));
    }
    let op_str = parsed.positionals[0].to_string_lossy().into_owned();
    let op =
        Op::parse(&op_str).ok_or_else(|| format!("set: unknown operation {op_str:?}\n{USAGE}"))?;
    let a = parsed.positionals[1].clone();
    let b = parsed.positionals[2].clone();

    let (stats, stats_to_stderr) =
        run_set(op, &a, &b, output.as_deref(), !parsed.global.no_progress)
            .map_err(|e| format!("set failed: {e}"))?;
    crate::output::print_stats(&stats.to_json(op), stats_to_stderr);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn keys_present(out: &str) -> Vec<String> {
        // Collect the Event values present in the output, in order.
        out.lines()
            .filter(|l| l.starts_with("[Event "))
            .map(|l| l.to_string())
            .collect()
    }

    fn run_inline(op: Op, a: &[u8], b: &[u8]) -> (String, SetStats) {
        // Exercise the core logic without the filesystem by hashing inline.
        let mut stats = SetStats::default();
        let mut out = Vec::new();
        match op {
            Op::Union => {
                let mut seen = HashSet::new();
                for g in GameSplitter::new(Cursor::new(a)) {
                    let g = g.unwrap();
                    stats.a_games += 1;
                    if seen.insert(game_key(&g.bytes)) {
                        stats.result_games += 1;
                        emit_game(&g.bytes, &mut out).unwrap();
                    }
                }
                for g in GameSplitter::new(Cursor::new(b)) {
                    let g = g.unwrap();
                    stats.b_games += 1;
                    if seen.insert(game_key(&g.bytes)) {
                        stats.result_games += 1;
                        emit_game(&g.bytes, &mut out).unwrap();
                    }
                }
            }
            Op::Intersect | Op::Diff => {
                let mut b_keys = HashSet::new();
                for g in GameSplitter::new(Cursor::new(b)) {
                    let g = g.unwrap();
                    stats.b_games += 1;
                    b_keys.insert(game_key(&g.bytes));
                }
                let mut emitted = HashSet::new();
                for g in GameSplitter::new(Cursor::new(a)) {
                    let g = g.unwrap();
                    stats.a_games += 1;
                    let key = game_key(&g.bytes);
                    let in_b = b_keys.contains(&key);
                    let keep = if op == Op::Intersect { in_b } else { !in_b };
                    if keep && emitted.insert(key) {
                        stats.result_games += 1;
                        emit_game(&g.bytes, &mut out).unwrap();
                    }
                }
            }
        }
        (String::from_utf8(out).unwrap(), stats)
    }

    const A: &[u8] = b"[Event \"a1\"]\n\n1. e4 e5 1-0\n\n[Event \"a2\"]\n\n1. d4 d5 0-1\n";
    const B: &[u8] = b"[Event \"a2\"]\n\n1. d4 d5 0-1\n\n[Event \"b1\"]\n\n1. c4 c5 1/2-1/2\n";

    #[test]
    fn intersect_keeps_only_shared_games() {
        let (out, stats) = run_inline(Op::Intersect, A, B);
        let events = keys_present(&out);
        assert_eq!(events, vec!["[Event \"a2\"]"], "out: {out}");
        assert_eq!(stats.result_games, 1);
    }

    #[test]
    fn diff_is_a_minus_b() {
        let (out, stats) = run_inline(Op::Diff, A, B);
        let events = keys_present(&out);
        assert_eq!(events, vec!["[Event \"a1\"]"], "out: {out}");
        assert_eq!(stats.result_games, 1);
    }

    #[test]
    fn union_is_distinct_games_from_both() {
        let (out, stats) = run_inline(Op::Union, A, B);
        let events = keys_present(&out);
        assert_eq!(
            events,
            vec!["[Event \"a1\"]", "[Event \"a2\"]", "[Event \"b1\"]"],
            "out: {out}"
        );
        assert_eq!(stats.result_games, 3);
    }

    #[test]
    fn exact_bytes_identity_distinguishes_reformatted_games() {
        // Same moves, different comment -> different bytes -> not shared.
        let a = b"[Event \"x\"]\n\n1. e4 {hi} e5 1-0\n";
        let b = b"[Event \"x\"]\n\n1. e4 e5 1-0\n";
        let (out, stats) = run_inline(Op::Intersect, a, b);
        assert_eq!(stats.result_games, 0, "should not match: {out}");
    }

    #[test]
    fn output_is_deduplicated() {
        let a = b"[Event \"d\"]\n\n1. e4 e5 1-0\n\n[Event \"d\"]\n\n1. e4 e5 1-0\n";
        let (out, stats) = run_inline(Op::Union, a, b"");
        assert_eq!(stats.a_games, 2);
        assert_eq!(stats.result_games, 1, "duplicates should collapse: {out}");
    }
}
