//! Generic annotated-PGN extraction.
//!
//! This is the Rust/shakmaty replacement for the old Python `chess.pgn`
//! playthrough path. It streams PGNs with `pgn-reader`, replays only the
//! mainline with `shakmaty`, and writes one JSONL record per game containing
//! headers, UCI moves, parse errors, and positions marked by a chosen comment.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{self, BufWriter, Write};
use std::path::{Path, PathBuf};

use pgn_reader::{BufferedReader, Outcome, RawComment, RawTag, SanPlus, Skip, Visitor};
use shakmaty::fen::Fen;
use shakmaty::{CastlingMode, Chess, Color, EnPassantMode, Position};

use crate::cli;
use crate::concat::expand_inputs;
use crate::progress::ProgressReporter;

const USAGE: &str = "\
usage: pgn-utils annotated-pgn [options] INPUT_PGN_OR_DIR...

options:
  -o, --output PATH       write JSONL games to PATH (required)
  --marker TEXT           marker comment text to match exactly after trimming
                          (default: CQL)
  --limit-files N         process at most N input PGN files
  --limit-games N         process at most N games total
  --allow-parse-errors    exit 0 despite per-game replay errors
  --force                 replace an existing output file
  --no-progress           disable the stderr progress bar";

#[derive(Debug, Clone)]
pub struct AnnotatedOptions {
    pub inputs: Vec<PathBuf>,
    pub output: PathBuf,
    pub marker_text: String,
    pub limit_files: Option<usize>,
    pub limit_games: Option<usize>,
    pub allow_parse_errors: bool,
    pub force: bool,
    pub show_progress: bool,
}

#[derive(Debug, Default, Clone, Copy)]
pub struct AnnotatedStats {
    pub files_processed: usize,
    pub bytes_in: u64,
    pub games_read: usize,
    pub positions_written: usize,
    pub parse_errors: usize,
}

impl AnnotatedStats {
    fn to_json(self) -> String {
        format!(
            "{{\"mode\":\"annotated-pgn\",\"files_processed\":{},\"bytes_in\":{},\"games_read\":{},\"positions_written\":{},\"parse_errors\":{}}}",
            self.files_processed,
            self.bytes_in,
            self.games_read,
            self.positions_written,
            self.parse_errors,
        )
    }
}

#[derive(Debug, Clone)]
struct AnnotatedPosition {
    ply_index: u32,
    fullmove_number: u32,
    move_san: String,
    move_uci: String,
    fen: String,
    side_to_move: &'static str,
    piece_count: usize,
}

#[derive(Debug, Clone)]
struct GameExtraction {
    game_index: usize,
    headers: BTreeMap<String, String>,
    parse_error: Option<String>,
    uci_moves: Vec<String>,
    positions: Vec<AnnotatedPosition>,
}

struct AnnotatedVisitor {
    marker_text: Vec<u8>,
    game_index: usize,
    pos: Chess,
    headers: BTreeMap<String, String>,
    outcome: Option<String>,
    ply_index: u32,
    last_move_san: String,
    last_move_uci: String,
    uci_moves: Vec<String>,
    positions: Vec<AnnotatedPosition>,
    parse_error: Option<String>,
}

impl AnnotatedVisitor {
    fn new(marker_text: &str) -> Self {
        Self {
            marker_text: marker_text.as_bytes().to_vec(),
            game_index: 0,
            pos: Chess::default(),
            headers: BTreeMap::new(),
            outcome: None,
            ply_index: 0,
            last_move_san: String::new(),
            last_move_uci: String::new(),
            uci_moves: Vec::new(),
            positions: Vec::new(),
            parse_error: None,
        }
    }

    fn record_error(&mut self, message: String) {
        if self.parse_error.is_none() {
            self.parse_error = Some(message);
        }
    }

    fn capture_marker(&mut self) {
        let fen = Fen::from_position(&self.pos, EnPassantMode::Legal).to_string();
        self.positions.push(AnnotatedPosition {
            ply_index: self.ply_index,
            fullmove_number: self.pos.fullmoves().get(),
            move_san: self.last_move_san.clone(),
            move_uci: self.last_move_uci.clone(),
            fen,
            side_to_move: color_name(self.pos.turn()),
            piece_count: self.pos.board().occupied().count(),
        });
    }
}

impl Visitor for AnnotatedVisitor {
    type Result = GameExtraction;

    fn begin_game(&mut self) {
        self.game_index += 1;
        self.pos = Chess::default();
        self.headers.clear();
        self.outcome = None;
        self.ply_index = 0;
        self.last_move_san.clear();
        self.last_move_uci.clear();
        self.uci_moves.clear();
        self.positions.clear();
        self.parse_error = None;
    }

    fn tag(&mut self, name: &[u8], value: RawTag<'_>) {
        let key = String::from_utf8_lossy(name).into_owned();
        let decoded = value.decode_utf8_lossy().into_owned();
        self.headers.insert(key, decoded);

        if name == b"FEN" {
            match Fen::from_ascii(value.as_bytes()) {
                Ok(fen) => match fen.into_position(CastlingMode::Standard) {
                    Ok(pos) => self.pos = pos,
                    Err(err) => self.record_error(format!("illegal FEN tag: {err}")),
                },
                Err(err) => self.record_error(format!("invalid FEN tag: {err}")),
            }
        }
    }

    fn begin_variation(&mut self) -> Skip {
        Skip(true)
    }

    fn san(&mut self, san_plus: SanPlus) {
        if self.parse_error.is_some() {
            return;
        }

        let san_text = san_plus.to_string();
        let move_result = san_plus.san.to_move(&self.pos);
        let Ok(chess_move) = move_result else {
            self.record_error(format!(
                "illegal SAN at ply {}: {}",
                self.ply_index + 1,
                san_text
            ));
            return;
        };

        let uci = chess_move.to_uci(self.pos.castles().mode()).to_string();
        self.pos.play_unchecked(chess_move);
        self.ply_index += 1;
        self.last_move_san = san_text;
        self.last_move_uci = uci.clone();
        self.uci_moves.push(uci);
    }

    fn comment(&mut self, comment: RawComment<'_>) {
        if self.parse_error.is_some() {
            return;
        }
        if trim_ascii(comment.as_bytes()) != self.marker_text.as_slice() {
            return;
        }
        self.capture_marker();
    }

    fn outcome(&mut self, outcome: Option<Outcome>) {
        self.outcome = outcome.map(|o| o.to_string());
    }

    fn end_game(&mut self) -> Self::Result {
        let parse_error = self.parse_error.take();
        let positions = if parse_error.is_none() {
            std::mem::take(&mut self.positions)
        } else {
            self.positions.clear();
            Vec::new()
        };
        let mut headers = std::mem::take(&mut self.headers);
        if !headers.contains_key("Result") {
            if let Some(outcome) = self.outcome.take() {
                headers.insert("Result".to_string(), outcome);
            }
        }

        GameExtraction {
            game_index: self.game_index,
            headers,
            parse_error,
            uci_moves: std::mem::take(&mut self.uci_moves),
            positions,
        }
    }
}

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    if args.iter().any(|arg| {
        let text = arg.to_string_lossy();
        text == "--help" || text == "-h" || text == "help"
    }) {
        println!("{USAGE}");
        return Ok(());
    }

    let parsed = cli::parse(
        args,
        &["allow-parse-errors", "force"],
        &["output", "o", "marker", "limit-files", "limit-games"],
    )
    .map_err(|e| format!("{e}\n{USAGE}"))?;

    if parsed.positionals.is_empty() {
        return Err(USAGE.to_string());
    }

    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from)
        .ok_or_else(|| format!("annotated-pgn: --output is required\n{USAGE}"))?;
    let marker_text = parsed
        .get_kv("marker")
        .map(|v| v.to_string_lossy().into_owned())
        .unwrap_or_else(|| "CQL".to_string());
    let limit_files = parse_optional_usize(&parsed, "limit-files")?;
    let limit_games = parse_optional_usize(&parsed, "limit-games")?;
    let allow_parse_errors = parsed.has_flag("allow-parse-errors");
    let force = parsed.has_flag("force");
    let show_progress = !parsed.global.no_progress;

    let opts = AnnotatedOptions {
        inputs: parsed.positionals,
        output,
        marker_text,
        limit_files,
        limit_games,
        allow_parse_errors,
        force,
        show_progress,
    };

    let stats = run_annotated_pgn(&opts)?;
    println!("{}", stats.to_json());
    Ok(())
}

pub fn run_annotated_pgn(opts: &AnnotatedOptions) -> Result<AnnotatedStats, String> {
    let mut files =
        expand_inputs(&opts.inputs).map_err(|e| format!("input discovery failed: {e}"))?;
    if let Some(limit) = opts.limit_files {
        files.truncate(limit);
    }

    if opts.output.exists() && !opts.force {
        return Err(format!(
            "output already exists: {} (pass --force to replace it)",
            opts.output.display()
        ));
    }
    if let Some(parent) = opts.output.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
    }

    let temp_path = temp_output_path(&opts.output);
    let result = (|| -> Result<AnnotatedStats, String> {
        let file = File::create(&temp_path)
            .map_err(|e| format!("failed to create {}: {e}", temp_path.display()))?;
        let mut writer = BufWriter::new(file);
        let stats = process_files(opts, &files, &mut writer)?;
        writer
            .flush()
            .map_err(|e| format!("flush {} failed: {e}", temp_path.display()))?;
        finish_or_error(opts, stats)
    })();

    match result {
        Ok(stats) => {
            fs::rename(&temp_path, &opts.output).map_err(|e| {
                format!(
                    "failed to rename {} to {}: {e}",
                    temp_path.display(),
                    opts.output.display()
                )
            })?;
            Ok(stats)
        }
        Err(err) => {
            let _ = fs::remove_file(&temp_path);
            Err(err)
        }
    }
}

fn process_files<W: Write>(
    opts: &AnnotatedOptions,
    files: &[PathBuf],
    writer: &mut W,
) -> Result<AnnotatedStats, String> {
    let total_bytes: u64 = files
        .iter()
        .map(|path| fs::metadata(path).map(|m| m.len()).unwrap_or(0))
        .sum();
    let progress = ProgressReporter::bytes(total_bytes, "annotated pgn", opts.show_progress);
    let mut stats = AnnotatedStats::default();
    let mut remaining_games = opts.limit_games;

    'files: for path in files {
        if matches!(remaining_games, Some(0)) {
            break;
        }
        let metadata =
            fs::metadata(path).map_err(|e| format!("failed to stat {}: {e}", path.display()))?;
        stats.files_processed += 1;
        stats.bytes_in += metadata.len();

        let file =
            File::open(path).map_err(|e| format!("failed to open {}: {e}", path.display()))?;
        let reader = progress.wrap(file);
        let mut pgn_reader = BufferedReader::new(reader);
        let mut visitor = AnnotatedVisitor::new(&opts.marker_text);

        loop {
            if matches!(remaining_games, Some(0)) {
                break 'files;
            }
            let game = pgn_reader
                .read_game(&mut visitor)
                .map_err(|e| format!("failed to parse {}: {e}", path.display()))?;
            let Some(game) = game else {
                break;
            };

            stats.games_read += 1;
            if let Some(remaining) = remaining_games.as_mut() {
                *remaining = remaining.saturating_sub(1);
            }
            if let Some(err) = &game.parse_error {
                stats.parse_errors += 1;
                eprintln!(
                    "parse error in {} game {}: {}",
                    path.display(),
                    game.game_index,
                    err
                );
            }
            stats.positions_written += game.positions.len();
            write_game(writer, &game).map_err(|e| format!("failed to write JSONL row: {e}"))?;
        }
    }

    progress.finish("annotated pgn done");
    Ok(stats)
}

fn finish_or_error(
    opts: &AnnotatedOptions,
    stats: AnnotatedStats,
) -> Result<AnnotatedStats, String> {
    if stats.parse_errors > 0 && !opts.allow_parse_errors {
        return Err(format!(
            "{} PGN game(s) had replay errors; no output was committed. Pass --allow-parse-errors to keep game records.",
            stats.parse_errors
        ));
    }
    Ok(stats)
}

fn write_game<W: Write>(out: &mut W, game: &GameExtraction) -> io::Result<()> {
    write!(out, "{{\"schema_version\":1")?;
    write_num_field(out, "game_index", game.game_index)?;

    write!(out, ",\"headers\":{{")?;
    for (idx, (key, value)) in game.headers.iter().enumerate() {
        if idx > 0 {
            write!(out, ",")?;
        }
        write_json_string(out, key)?;
        write!(out, ":")?;
        write_json_string(out, value)?;
    }
    write!(out, "}}")?;

    write!(out, ",\"parse_errors\":[")?;
    if let Some(error) = &game.parse_error {
        write_json_string(out, error)?;
    }
    write!(out, "]")?;

    write!(out, ",\"move_uci_sequence\":[")?;
    for (idx, mv) in game.uci_moves.iter().enumerate() {
        if idx > 0 {
            write!(out, ",")?;
        }
        write_json_string(out, mv)?;
    }
    write!(out, "]")?;

    write!(out, ",\"positions\":[")?;
    for (idx, position) in game.positions.iter().enumerate() {
        if idx > 0 {
            write!(out, ",")?;
        }
        write_position(out, position)?;
    }
    writeln!(out, "]}}")?;
    Ok(())
}

fn write_position<W: Write>(out: &mut W, position: &AnnotatedPosition) -> io::Result<()> {
    write!(out, "{{")?;
    write!(out, "\"ply_index\":{}", position.ply_index)?;
    write_num_field(out, "fullmove_number", position.fullmove_number)?;
    write_str_field(out, "move_san", &position.move_san)?;
    write_str_field(out, "move_uci", &position.move_uci)?;
    write_str_field(out, "fen", &position.fen)?;
    write_str_field(out, "side_to_move", position.side_to_move)?;
    write_num_field(out, "piece_count", position.piece_count)?;
    write!(out, "}}")
}

fn write_str_field<W: Write>(out: &mut W, key: &str, value: &str) -> io::Result<()> {
    write!(out, ",\"{key}\":")?;
    write_json_string(out, value)
}

fn write_num_field<W: Write, T: std::fmt::Display>(
    out: &mut W,
    key: &str,
    value: T,
) -> io::Result<()> {
    write!(out, ",\"{key}\":{value}")
}

fn write_json_string<W: Write>(out: &mut W, value: &str) -> io::Result<()> {
    out.write_all(b"\"")?;
    for ch in value.chars() {
        match ch {
            '"' => out.write_all(br#"\""#)?,
            '\\' => out.write_all(br#"\\"#)?,
            '\n' => out.write_all(br#"\n"#)?,
            '\r' => out.write_all(br#"\r"#)?,
            '\t' => out.write_all(br#"\t"#)?,
            c if c.is_control() => write!(out, "\\u{:04x}", c as u32)?,
            c => write!(out, "{c}")?,
        }
    }
    out.write_all(b"\"")
}

fn color_name(color: Color) -> &'static str {
    match color {
        Color::White => "white",
        Color::Black => "black",
    }
}

fn trim_ascii(bytes: &[u8]) -> &[u8] {
    let mut start = 0usize;
    let mut end = bytes.len();
    while start < end && bytes[start].is_ascii_whitespace() {
        start += 1;
    }
    while end > start && bytes[end - 1].is_ascii_whitespace() {
        end -= 1;
    }
    &bytes[start..end]
}

fn parse_optional_usize(parsed: &cli::ParsedArgs, name: &str) -> Result<Option<usize>, String> {
    parsed
        .get_kv(name)
        .map(|value| {
            value
                .to_string_lossy()
                .parse::<usize>()
                .map_err(|e| format!("invalid --{name}: {e}"))
        })
        .transpose()
}

fn temp_output_path(output_path: &Path) -> PathBuf {
    let file_name = output_path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("annotated-pgn.jsonl");
    output_path.with_file_name(format!(".{file_name}.tmp-{}", std::process::id()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_temp_dir() -> PathBuf {
        // A bare nanosecond timestamp can repeat when two tests start within the
        // same clock tick, so two parallel tests would share (and clobber) one
        // dir. Mix in a per-process atomic counter to guarantee uniqueness.
        use std::sync::atomic::{AtomicUsize, Ordering};
        static COUNTER: AtomicUsize = AtomicUsize::new(0);
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let seq = COUNTER.fetch_add(1, Ordering::Relaxed);
        let dir = std::env::temp_dir().join(format!(
            "reti-annotated-test-{}-{suffix}-{seq}",
            std::process::id()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn exports_marked_positions_with_fen_and_uci() {
        let dir = unique_temp_dir();
        let pgn = dir.join("input.pgn");
        let out = dir.join("out.jsonl");
        fs::write(
            &pgn,
            "[Event \"T\"]\n[Result \"*\"]\n\n1. e4 {CQL} e5 { other } 2. Nf3 { CQL } *\n",
        )
        .unwrap();

        let opts = AnnotatedOptions {
            inputs: vec![pgn],
            output: out.clone(),
            marker_text: "CQL".to_string(),
            limit_files: None,
            limit_games: None,
            allow_parse_errors: false,
            force: true,
            show_progress: false,
        };
        let stats = run_annotated_pgn(&opts).unwrap();
        assert_eq!(stats.games_read, 1);
        assert_eq!(stats.positions_written, 2);

        let mut text = String::new();
        File::open(&out).unwrap().read_to_string(&mut text).unwrap();
        assert!(text.contains("\"move_uci\":\"e2e4\""));
        assert!(text.contains("\"move_san\":\"Nf3\""));
        assert!(text.contains("\"side_to_move\":\"black\""));
        assert!(text.contains("\"piece_count\":32"));
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn records_replay_errors_without_positions_when_allowed() {
        let dir = unique_temp_dir();
        let pgn = dir.join("bad.pgn");
        let out = dir.join("out.jsonl");
        fs::write(&pgn, "[Event \"Bad\"]\n[Result \"*\"]\n\n1. Ke2 {CQL} *\n").unwrap();

        let opts = AnnotatedOptions {
            inputs: vec![pgn],
            output: out.clone(),
            marker_text: "CQL".to_string(),
            limit_files: None,
            limit_games: None,
            allow_parse_errors: true,
            force: true,
            show_progress: false,
        };
        let stats = run_annotated_pgn(&opts).unwrap();
        assert_eq!(stats.parse_errors, 1);

        let mut text = String::new();
        File::open(&out).unwrap().read_to_string(&mut text).unwrap();
        assert!(text.contains("\"parse_errors\":[\"illegal SAN at ply 1: Ke2\"]"));
        assert!(text.contains("\"positions\":[]"));
        fs::remove_dir_all(dir).unwrap();
    }
}
