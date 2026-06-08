//! Export CQL marker positions from FCE output PGNs.
//!
//! The FCE CQL run writes one annotated PGN per `(source bucket, ending)`.
//! This subcommand streams those files, replays only the mainline, and emits
//! JSONL rows for marker positions. The default mode is the pilot dataset:
//! the first `{CQL}` marker per output game, which is one position for each
//! per-ending incidence row.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{self, BufWriter, Write};
use std::path::{Path, PathBuf};

use pgn_reader::{BufferedReader, Outcome, RawComment, RawTag, SanPlus, Skip, Visitor};
use shakmaty::fen::Fen;
use shakmaty::{CastlingMode, Chess, Color, EnPassantMode, Position};
use xxhash_rust::xxh3::xxh3_64;

use crate::cli;
use crate::concat::expand_inputs;
use crate::progress::ProgressReporter;

const USAGE: &str = "\
usage: pgn-utils fce-markers [options] INPUT_PGN_OR_DIR...

options:
  -o, --output PATH       write JSONL to PATH; use '-' or omit for stdout
  --relative-to DIR       store output_pgn paths relative to DIR
  --marker TEXT           marker comment text to match exactly after trimming
                          (default: CQL)
  --mode MODE             first-per-ending-game or all
                          (default: first-per-ending-game)
  --limit-files N         process at most N input PGN files
  --limit-games N         process at most N games total
  --allow-parse-errors    write rows from clean games and exit 0 despite errors
  --force                 replace an existing output file
  --no-progress           disable the stderr progress bar";

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub(crate) enum MarkerMode {
    FirstPerEndingGame,
    All,
}

impl MarkerMode {
    fn parse(raw: &str) -> Result<Self, String> {
        match raw {
            "first-per-ending-game" | "first" => Ok(Self::FirstPerEndingGame),
            "all" => Ok(Self::All),
            _ => Err(format!(
                "unknown --mode {raw:?}; expected first-per-ending-game or all"
            )),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::FirstPerEndingGame => "first-per-ending-game",
            Self::All => "all",
        }
    }
}

#[derive(Debug, Clone)]
pub struct FceMarkerOptions {
    pub inputs: Vec<PathBuf>,
    pub output: Option<PathBuf>,
    pub relative_to: Option<PathBuf>,
    marker_text: String,
    mode: MarkerMode,
    pub limit_files: Option<usize>,
    pub limit_games: Option<usize>,
    pub allow_parse_errors: bool,
    pub force: bool,
    pub show_progress: bool,
}

#[derive(Debug, Default, Clone, Copy)]
pub struct FceMarkerStats {
    pub files_processed: usize,
    pub bytes_in: u64,
    pub games_read: usize,
    pub marker_positions_written: usize,
    pub parse_errors: usize,
}

impl FceMarkerStats {
    fn to_json(self, mode: MarkerMode) -> String {
        format!(
            "{{\"mode\":\"{}\",\"files_processed\":{},\"bytes_in\":{},\"games_read\":{},\"positions_written\":{},\"parse_errors\":{}}}",
            mode.as_str(),
            self.files_processed,
            self.bytes_in,
            self.games_read,
            self.marker_positions_written,
            self.parse_errors,
        )
    }
}

#[derive(Debug, Clone)]
struct FileContext {
    source_pgn: String,
    source_bucket: String,
    output_pgn: String,
    ending: String,
}

#[derive(Debug, Clone)]
struct PartialMarker {
    marker_index: usize,
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
    game_key: String,
    rows: Vec<PartialMarker>,
    parse_error: Option<String>,
}

struct MarkerVisitor {
    marker_text: Vec<u8>,
    mode: MarkerMode,
    game_index: usize,
    pos: Chess,
    headers: BTreeMap<String, String>,
    outcome: Option<String>,
    ply_index: u32,
    marker_comments_seen: usize,
    row_already_captured: bool,
    last_move_san: String,
    last_move_uci: String,
    uci_moves: Vec<String>,
    rows: Vec<PartialMarker>,
    parse_error: Option<String>,
}

impl MarkerVisitor {
    fn new(marker_text: &str, mode: MarkerMode) -> Self {
        Self {
            marker_text: marker_text.as_bytes().to_vec(),
            mode,
            game_index: 0,
            pos: Chess::default(),
            headers: BTreeMap::new(),
            outcome: None,
            ply_index: 0,
            marker_comments_seen: 0,
            row_already_captured: false,
            last_move_san: String::new(),
            last_move_uci: String::new(),
            uci_moves: Vec::new(),
            rows: Vec::new(),
            parse_error: None,
        }
    }

    fn record_error(&mut self, message: String) {
        if self.parse_error.is_none() {
            self.parse_error = Some(message);
        }
    }

    fn capture_marker(&mut self) {
        if self.mode == MarkerMode::FirstPerEndingGame && self.row_already_captured {
            return;
        }

        self.row_already_captured = true;
        let fen = Fen::from_position(&self.pos, EnPassantMode::Legal).to_string();
        self.rows.push(PartialMarker {
            marker_index: self.marker_comments_seen,
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

impl Visitor for MarkerVisitor {
    type Result = GameExtraction;

    fn begin_game(&mut self) {
        self.game_index += 1;
        self.pos = Chess::default();
        self.headers.clear();
        self.outcome = None;
        self.ply_index = 0;
        self.marker_comments_seen = 0;
        self.row_already_captured = false;
        self.last_move_san.clear();
        self.last_move_uci.clear();
        self.uci_moves.clear();
        self.rows.clear();
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
        self.marker_comments_seen += 1;
        self.capture_marker();
    }

    fn outcome(&mut self, outcome: Option<Outcome>) {
        self.outcome = outcome.map(|o| o.to_string());
    }

    fn end_game(&mut self) -> Self::Result {
        let parse_error = self.parse_error.take();
        let rows = if parse_error.is_none() {
            std::mem::take(&mut self.rows)
        } else {
            self.rows.clear();
            Vec::new()
        };
        let mut headers = std::mem::take(&mut self.headers);
        if !headers.contains_key("Result") {
            if let Some(outcome) = self.outcome.take() {
                headers.insert("Result".to_string(), outcome);
            }
        }
        let game_key = game_key(&headers, &self.uci_moves);
        self.uci_moves.clear();

        GameExtraction {
            game_index: self.game_index,
            headers,
            game_key,
            rows,
            parse_error,
        }
    }
}

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    let parsed = cli::parse(
        args,
        &["allow-parse-errors", "force"],
        &[
            "output",
            "o",
            "relative-to",
            "marker",
            "mode",
            "limit-files",
            "limit-games",
        ],
    )
    .map_err(|e| format!("{e}\n{USAGE}"))?;

    if parsed.positionals.is_empty() {
        return Err(USAGE.to_string());
    }

    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);
    let relative_to = parsed.get_kv("relative-to").map(PathBuf::from);
    let marker_text = parsed
        .get_kv("marker")
        .map(|v| v.to_string_lossy().into_owned())
        .unwrap_or_else(|| "CQL".to_string());
    let mode = parsed
        .get_kv("mode")
        .map(|v| MarkerMode::parse(&v.to_string_lossy()))
        .transpose()?
        .unwrap_or(MarkerMode::FirstPerEndingGame);

    let limit_files = parse_optional_usize(&parsed, "limit-files")?;
    let limit_games = parse_optional_usize(&parsed, "limit-games")?;

    let allow_parse_errors = parsed.has_flag("allow-parse-errors");
    let force = parsed.has_flag("force");
    let show_progress = !parsed.global.no_progress;

    let opts = FceMarkerOptions {
        inputs: parsed.positionals,
        output,
        relative_to,
        marker_text,
        mode,
        limit_files,
        limit_games,
        allow_parse_errors,
        force,
        show_progress,
    };

    let stats = run_fce_markers(&opts)?;
    println!("{}", stats.to_json(opts.mode));
    Ok(())
}

pub fn run_fce_markers(opts: &FceMarkerOptions) -> Result<FceMarkerStats, String> {
    let mut files =
        expand_inputs(&opts.inputs).map_err(|e| format!("input discovery failed: {e}"))?;
    if let Some(limit) = opts.limit_files {
        files.truncate(limit);
    }

    let stdout = match opts.output.as_deref() {
        None => true,
        Some(path) => path == Path::new("-"),
    };

    if stdout {
        let stdout = io::stdout();
        let mut writer = BufWriter::new(stdout.lock());
        let stats = process_files(opts, &files, &mut writer)?;
        writer
            .flush()
            .map_err(|e| format!("flush stdout failed: {e}"))?;
        return finish_or_error(opts, stats);
    }

    let output_path = opts.output.as_ref().expect("checked stdout");
    if output_path.exists() && !opts.force {
        return Err(format!(
            "output already exists: {} (pass --force to replace it)",
            output_path.display()
        ));
    }
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
    }

    let temp_path = temp_output_path(output_path);
    let result = (|| -> Result<FceMarkerStats, String> {
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
            fs::rename(&temp_path, output_path).map_err(|e| {
                format!(
                    "failed to rename {} to {}: {e}",
                    temp_path.display(),
                    output_path.display()
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
    opts: &FceMarkerOptions,
    files: &[PathBuf],
    writer: &mut W,
) -> Result<FceMarkerStats, String> {
    let total_bytes: u64 = files
        .iter()
        .map(|path| fs::metadata(path).map(|m| m.len()).unwrap_or(0))
        .sum();
    let progress = ProgressReporter::bytes(total_bytes, "fce markers", opts.show_progress);
    let mut stats = FceMarkerStats::default();
    let mut remaining_games = opts.limit_games;

    'files: for path in files {
        if matches!(remaining_games, Some(0)) {
            break;
        }
        let metadata =
            fs::metadata(path).map_err(|e| format!("failed to stat {}: {e}", path.display()))?;
        stats.files_processed += 1;
        stats.bytes_in += metadata.len();

        let context = file_context(path, opts.relative_to.as_deref());
        let file =
            File::open(path).map_err(|e| format!("failed to open {}: {e}", path.display()))?;
        let reader = progress.wrap(file);
        let mut pgn_reader = BufferedReader::new(reader);
        let mut visitor = MarkerVisitor::new(&opts.marker_text, opts.mode);

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
                    context.output_pgn, game.game_index, err
                );
                continue;
            }

            for row in &game.rows {
                write_marker_row(writer, &context, &game, row, &opts.marker_text)
                    .map_err(|e| format!("failed to write JSONL row: {e}"))?;
                stats.marker_positions_written += 1;
            }
        }
    }

    progress.finish("fce markers done");
    Ok(stats)
}

fn finish_or_error(
    opts: &FceMarkerOptions,
    stats: FceMarkerStats,
) -> Result<FceMarkerStats, String> {
    if stats.parse_errors > 0 && !opts.allow_parse_errors {
        return Err(format!(
            "{} PGN game(s) had parse errors; no output was committed. Pass --allow-parse-errors to keep clean rows.",
            stats.parse_errors
        ));
    }
    Ok(stats)
}

fn write_marker_row<W: Write>(
    out: &mut W,
    context: &FileContext,
    game: &GameExtraction,
    row: &PartialMarker,
    marker_text: &str,
) -> io::Result<()> {
    write!(out, "{{\"schema_version\":1")?;
    write_str_field(out, "source_pgn", &context.source_pgn)?;
    write_str_field(out, "source_bucket", &context.source_bucket)?;
    write_str_field(out, "ending", &context.ending)?;
    write_str_field(out, "output_pgn", &context.output_pgn)?;
    write_num_field(out, "game_index", game.game_index)?;
    write_num_field(out, "marker_index", row.marker_index)?;
    write_str_field(out, "marker_text", marker_text)?;
    write_str_field(out, "game_key", &game.game_key)?;
    write_header_field(out, "event", &game.headers, "Event")?;
    write_header_field(out, "site", &game.headers, "Site")?;
    write_header_field(out, "date", &game.headers, "Date")?;
    write_header_field(out, "round", &game.headers, "Round")?;
    write_header_field(out, "white", &game.headers, "White")?;
    write_header_field(out, "black", &game.headers, "Black")?;
    write_header_field(out, "result", &game.headers, "Result")?;
    write_num_field(out, "ply_index", row.ply_index)?;
    write_num_field(out, "fullmove_number", row.fullmove_number)?;
    write_str_field(out, "move_san", &row.move_san)?;
    write_str_field(out, "move_uci", &row.move_uci)?;
    write_str_field(out, "fen", &row.fen)?;
    write_str_field(out, "side_to_move", row.side_to_move)?;
    write_num_field(out, "piece_count", row.piece_count)?;
    writeln!(out, "}}")?;
    Ok(())
}

fn write_header_field<W: Write>(
    out: &mut W,
    json_key: &str,
    headers: &BTreeMap<String, String>,
    header_key: &str,
) -> io::Result<()> {
    write_str_field(
        out,
        json_key,
        headers.get(header_key).map(String::as_str).unwrap_or(""),
    )
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

fn file_context(path: &Path, relative_to: Option<&Path>) -> FileContext {
    let output_pgn_path = relative_to
        .and_then(|root| path.strip_prefix(root).ok())
        .unwrap_or(path);
    let output_pgn = display_path(output_pgn_path);
    let source_bucket = output_pgn_path
        .parent()
        .and_then(|p| p.file_name())
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();
    let source_pgn = if source_bucket.is_empty() {
        String::new()
    } else {
        format!("{source_bucket}.pgn")
    };
    let ending = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();

    FileContext {
        source_pgn,
        source_bucket,
        output_pgn,
        ending,
    }
}

fn display_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn game_key(headers: &BTreeMap<String, String>, uci_moves: &[String]) -> String {
    let mut material = String::new();
    for key in ["Event", "Site", "Date", "Round", "White", "Black", "Result"] {
        material.push_str(headers.get(key).map(String::as_str).unwrap_or(""));
        material.push('\x1f');
    }
    for mv in uci_moves {
        material.push_str(mv);
        material.push(' ');
    }
    format!("{:016x}", xxh3_64(material.as_bytes()))
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
        .unwrap_or("fce-markers.jsonl");
    output_path.with_file_name(format!(".{file_name}.tmp-{}", std::process::id()))
}
