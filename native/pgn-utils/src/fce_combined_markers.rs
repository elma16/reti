//! Export facts from combined FCE marker PGNs.
//!
//! The combined CQL script writes one PGN per source bucket and annotates
//! matching positions with comments such as `{3-2NN}` or `{8-1RNrNoPawns
//! 8-1RNr}`. This subcommand replays each game once, records one incidence fact
//! per `(game, stem)`, and records the first marker position for each stem/game
//! when it is at or below the configured tablebase piece threshold.

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{CStr, CString, OsString};
use std::fs::{self, File};
use std::io::{self, BufWriter, Write};
use std::os::raw::{c_char, c_int, c_void};
use std::path::{Path, PathBuf};
use std::ptr;

use pgn_reader::{BufferedReader, Outcome, RawComment, RawTag, SanPlus, Skip, Visitor};
use shakmaty::fen::Fen;
use shakmaty::{CastlingMode, Chess, Color, EnPassantMode, Position, Role};
use xxhash_rust::xxh3::{xxh3_128, xxh3_64};

use crate::cli;
use crate::concat::expand_inputs;
use crate::progress::ProgressReporter;

const USAGE: &str = "\
usage: reti-pgn-utils fce-combined-markers [options] INPUT_PGN_OR_DIR...

options:
  -o, --output PATH       write JSONL facts to PATH; use '-' or omit for stdout
  --sqlite-db PATH        write facts directly into an existing/new SQLite DB
  --profile-id ID         evaluation profile id used in SQLite eval keys
  --sqlite-batch-rows N   commit SQLite ingest every N inserted rows
                          (default: 100000)
  --relative-to DIR       store output_pgn paths relative to DIR
  --known-stems LIST      comma/whitespace separated FCE stems to recognize
  --max-pieces N          emit position facts only for positions with <= N pieces
                          (default: 5)
  --limit-files N         process at most N input PGN files
  --limit-games N         process at most N games total
  --allow-parse-errors    write rows from clean games and exit 0 despite errors
  --force                 replace an existing output file
  --no-progress           disable the stderr progress bar";

const SAMPLES_USAGE: &str = "\
usage: reti-pgn-utils fce-combined-samples [options] INPUT_PGN_OR_DIR...

options:
  -o, --output PATH       write sampled examples JSON to PATH
  --relative-to DIR       store output_pgn paths relative to DIR
  --known-stems LIST      comma/whitespace separated FCE stems to recognize
  --thresholds LIST       comma separated run thresholds (default: 1,2,5,10,20)
  --sample-size N         maximum examples per view/threshold/stem (default: 60)
  --limit-files N         process at most N input PGN files
  --limit-games N         process at most N games total
  --allow-parse-errors    write rows from clean games and exit 0 despite errors
  --force                 replace an existing output file
  --no-progress           disable the stderr progress bar";

#[derive(Debug, Clone)]
pub struct CombinedMarkerOptions {
    pub inputs: Vec<PathBuf>,
    pub output: Option<PathBuf>,
    pub sqlite_db: Option<PathBuf>,
    pub profile_id: String,
    pub sqlite_batch_rows: usize,
    pub relative_to: Option<PathBuf>,
    pub known_stems: BTreeSet<String>,
    pub max_pieces: usize,
    pub limit_files: Option<usize>,
    pub limit_games: Option<usize>,
    pub allow_parse_errors: bool,
    pub force: bool,
    pub show_progress: bool,
}

#[derive(Debug, Default, Clone, Copy)]
pub struct CombinedMarkerStats {
    pub files_processed: usize,
    pub bytes_in: u64,
    pub games_read: usize,
    pub game_stems_written: usize,
    pub positions_written: usize,
    pub parse_errors: usize,
}

#[derive(Debug, Clone)]
pub struct CombinedSampleOptions {
    pub inputs: Vec<PathBuf>,
    pub output: PathBuf,
    pub relative_to: Option<PathBuf>,
    pub known_stems: BTreeSet<String>,
    pub thresholds: Vec<usize>,
    pub sample_size: usize,
    pub limit_files: Option<usize>,
    pub limit_games: Option<usize>,
    pub allow_parse_errors: bool,
    pub force: bool,
    pub show_progress: bool,
}

#[derive(Debug, Default, Clone, Copy)]
pub struct CombinedSampleStats {
    pub files_processed: usize,
    pub bytes_in: u64,
    pub games_read: usize,
    pub samples_seen: usize,
    pub parse_errors: usize,
}

impl CombinedSampleStats {
    fn to_json(self) -> String {
        format!(
            "{{\"mode\":\"combined-stem-samples\",\"files_processed\":{},\"bytes_in\":{},\"games_read\":{},\"samples_seen\":{},\"parse_errors\":{}}}",
            self.files_processed,
            self.bytes_in,
            self.games_read,
            self.samples_seen,
            self.parse_errors,
        )
    }
}

impl CombinedMarkerStats {
    fn to_json(self) -> String {
        format!(
            "{{\"mode\":\"combined-stem-facts\",\"files_processed\":{},\"bytes_in\":{},\"games_read\":{},\"game_stems_written\":{},\"positions_written\":{},\"parse_errors\":{}}}",
            self.files_processed,
            self.bytes_in,
            self.games_read,
            self.game_stems_written,
            self.positions_written,
            self.parse_errors,
        )
    }
}

#[derive(Debug, Clone)]
struct FileContext {
    source_pgn: String,
    source_group: String,
    source_bucket: String,
    output_pgn: String,
}

#[derive(Debug, Clone)]
struct CapturedMarker {
    marker_index: usize,
    stem: String,
    ply_index: u32,
    fullmove_number: u32,
    move_san: String,
    move_uci: String,
    fen: String,
    side_to_move: &'static str,
    piece_count: usize,
    material_side: &'static str,
    material_label: &'static str,
    material_signature: String,
    run_length: usize,
    run_start_ply: u32,
    run_end_ply: u32,
}

#[derive(Debug, Clone)]
struct GameStemRun {
    stem: String,
    max_run_length: usize,
    position_count: usize,
    first_marker: CapturedMarker,
}

#[derive(Debug, Clone)]
struct GameExtraction {
    game_index: usize,
    headers: BTreeMap<String, String>,
    game_key: String,
    stems: Vec<GameStemRun>,
    markers: Vec<CapturedMarker>,
    parse_error: Option<String>,
}

#[derive(Debug, Clone)]
struct SampleExample {
    source_pgn: String,
    source_group: String,
    source_bucket: String,
    output_pgn: String,
    game_index: usize,
    game_key: String,
    event: String,
    site: String,
    date: String,
    round: String,
    white: String,
    white_elo: String,
    black: String,
    black_elo: String,
    result: String,
    stem: String,
    ply_index: u32,
    fullmove_number: u32,
    move_san: String,
    move_uci: String,
    fen: String,
    side_to_move: &'static str,
    piece_count: usize,
    run_length: usize,
    run_start_ply: u32,
    run_end_ply: u32,
    material_side: &'static str,
    material_label: &'static str,
}

#[derive(Debug, Clone)]
struct ReservoirItem {
    key: u128,
    example: SampleExample,
}

#[derive(Debug, Default, Clone)]
struct Reservoir {
    seen: usize,
    items: Vec<ReservoirItem>,
    max_index: Option<usize>,
}

impl Reservoir {
    fn consider(&mut self, key: u128, example: SampleExample, sample_size: usize) {
        self.seen += 1;
        if sample_size == 0 {
            return;
        }
        if self.items.len() < sample_size {
            self.items.push(ReservoirItem { key, example });
            self.recompute_max();
            return;
        }
        let Some(max_index) = self.max_index else {
            return;
        };
        if key < self.items[max_index].key {
            self.items[max_index] = ReservoirItem { key, example };
            self.recompute_max();
        }
    }

    fn recompute_max(&mut self) {
        self.max_index = self
            .items
            .iter()
            .enumerate()
            .max_by_key(|(_, item)| item.key)
            .map(|(idx, _)| idx);
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct SourceSampleKey {
    source_pgn: String,
    source_group: String,
    threshold: usize,
    stem: String,
}

#[derive(Debug, Clone, Copy, Default)]
struct SideCounts {
    q: usize,
    r: usize,
    b: usize,
    n: usize,
    p: usize,
}

#[derive(Debug, Clone)]
struct MaterialPerspective {
    material_side: &'static str,
    material_label: &'static str,
    material_signature: String,
}

struct CombinedMarkerVisitor<'a> {
    known_stems: &'a BTreeSet<String>,
    max_pieces: usize,
    game_index: usize,
    pos: Chess,
    headers: BTreeMap<String, String>,
    outcome: Option<String>,
    ply_index: u32,
    marker_comments_seen: usize,
    last_move_san: String,
    last_move_uci: String,
    uci_moves: Vec<String>,
    markers: Vec<CapturedMarker>,
    seen_stem_ply: BTreeSet<(String, u32)>,
    parse_error: Option<String>,
}

impl<'a> CombinedMarkerVisitor<'a> {
    fn new(known_stems: &'a BTreeSet<String>, max_pieces: usize) -> Self {
        Self {
            known_stems,
            max_pieces,
            game_index: 0,
            pos: Chess::default(),
            headers: BTreeMap::new(),
            outcome: None,
            ply_index: 0,
            marker_comments_seen: 0,
            last_move_san: String::new(),
            last_move_uci: String::new(),
            uci_moves: Vec::new(),
            markers: Vec::new(),
            seen_stem_ply: BTreeSet::new(),
            parse_error: None,
        }
    }

    fn record_error(&mut self, message: String) {
        if self.parse_error.is_none() {
            self.parse_error = Some(message);
        }
    }

    fn capture_stem(&mut self, stem: &str) {
        let key = (stem.to_string(), self.ply_index);
        if !self.seen_stem_ply.insert(key) {
            return;
        }
        let fen = Fen::from_position(&self.pos, EnPassantMode::Legal).to_string();
        let material = classify_material_side(stem, &self.pos);
        self.markers.push(CapturedMarker {
            marker_index: self.marker_comments_seen,
            stem: stem.to_string(),
            ply_index: self.ply_index,
            fullmove_number: self.pos.fullmoves().get(),
            move_san: self.last_move_san.clone(),
            move_uci: self.last_move_uci.clone(),
            fen,
            side_to_move: color_name(self.pos.turn()),
            piece_count: self.pos.board().occupied().count(),
            material_side: material.material_side,
            material_label: material.material_label,
            material_signature: material.material_signature,
            run_length: 0,
            run_start_ply: 0,
            run_end_ply: 0,
        });
    }
}

impl Visitor for CombinedMarkerVisitor<'_> {
    type Result = GameExtraction;

    fn begin_game(&mut self) {
        self.game_index += 1;
        self.pos = Chess::default();
        self.headers.clear();
        self.outcome = None;
        self.ply_index = 0;
        self.marker_comments_seen = 0;
        self.last_move_san.clear();
        self.last_move_uci.clear();
        self.uci_moves.clear();
        self.markers.clear();
        self.seen_stem_ply.clear();
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
        let stems = extract_known_stems(comment.as_bytes(), self.known_stems);
        if stems.is_empty() {
            return;
        }
        self.marker_comments_seen += 1;
        for stem in stems {
            self.capture_stem(&stem);
        }
    }

    fn outcome(&mut self, outcome: Option<Outcome>) {
        self.outcome = outcome.map(|o| o.to_string());
    }

    fn end_game(&mut self) -> Self::Result {
        let parse_error = self.parse_error.take();
        let mut headers = std::mem::take(&mut self.headers);
        if !headers.contains_key("Result") {
            if let Some(outcome) = self.outcome.take() {
                headers.insert("Result".to_string(), outcome);
            }
        }
        let game_key = game_key(&headers, &self.uci_moves);
        self.uci_moves.clear();

        let (stems, markers) = if parse_error.is_none() {
            finalize_runs(std::mem::take(&mut self.markers), self.max_pieces)
        } else {
            self.markers.clear();
            (Vec::new(), Vec::new())
        };

        GameExtraction {
            game_index: self.game_index,
            headers,
            game_key,
            stems,
            markers,
            parse_error,
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
        &[
            "output",
            "o",
            "sqlite-db",
            "profile-id",
            "sqlite-batch-rows",
            "relative-to",
            "known-stems",
            "max-pieces",
            "limit-files",
            "limit-games",
        ],
    )
    .map_err(|e| format!("{e}\n{USAGE}"))?;

    if parsed.positionals.is_empty() {
        return Err(USAGE.to_string());
    }

    let known_stems = parse_known_stems(
        parsed
            .get_kv("known-stems")
            .map(|value| value.to_string_lossy().into_owned())
            .unwrap_or_default()
            .as_str(),
    );
    if known_stems.is_empty() {
        return Err(format!(
            "fce-combined-markers: --known-stems is required\n{USAGE}"
        ));
    }

    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from);
    let sqlite_db = parsed.get_kv("sqlite-db").map(PathBuf::from);
    if output.is_some() && sqlite_db.is_some() {
        return Err(
            "fce-combined-markers: choose either --output or --sqlite-db, not both".to_string(),
        );
    }
    let profile_id = parsed
        .get_kv("profile-id")
        .map(|value| value.to_string_lossy().into_owned())
        .unwrap_or_else(|| "default".to_string());
    let sqlite_batch_rows = parse_optional_usize(&parsed, "sqlite-batch-rows")?.unwrap_or(100_000);
    if sqlite_db.is_some() && sqlite_batch_rows == 0 {
        return Err("fce-combined-markers: --sqlite-batch-rows must be positive".to_string());
    }
    let relative_to = parsed.get_kv("relative-to").map(PathBuf::from);
    let max_pieces = parse_optional_usize(&parsed, "max-pieces")?.unwrap_or(5);
    let limit_files = parse_optional_usize(&parsed, "limit-files")?;
    let limit_games = parse_optional_usize(&parsed, "limit-games")?;
    let allow_parse_errors = parsed.has_flag("allow-parse-errors");
    let force = parsed.has_flag("force");
    let show_progress = !parsed.global.no_progress;
    let opts = CombinedMarkerOptions {
        inputs: parsed.positionals,
        output,
        sqlite_db,
        profile_id,
        sqlite_batch_rows,
        relative_to,
        known_stems,
        max_pieces,
        limit_files,
        limit_games,
        allow_parse_errors,
        force,
        show_progress,
    };

    let stats = run_fce_combined_markers(&opts)?;
    println!("{}", stats.to_json());
    Ok(())
}

pub fn run_samples_subcommand(args: &[OsString]) -> Result<(), String> {
    if args.iter().any(|arg| {
        let text = arg.to_string_lossy();
        text == "--help" || text == "-h" || text == "help"
    }) {
        println!("{SAMPLES_USAGE}");
        return Ok(());
    }
    let parsed = cli::parse(
        args,
        &["allow-parse-errors", "force"],
        &[
            "output",
            "o",
            "relative-to",
            "known-stems",
            "thresholds",
            "sample-size",
            "limit-files",
            "limit-games",
        ],
    )
    .map_err(|e| format!("{e}\n{SAMPLES_USAGE}"))?;

    if parsed.positionals.is_empty() {
        return Err(SAMPLES_USAGE.to_string());
    }

    let known_stems = parse_known_stems(
        parsed
            .get_kv("known-stems")
            .map(|value| value.to_string_lossy().into_owned())
            .unwrap_or_default()
            .as_str(),
    );
    if known_stems.is_empty() {
        return Err(format!(
            "fce-combined-samples: --known-stems is required\n{SAMPLES_USAGE}"
        ));
    }
    let output = parsed
        .get_kv("output")
        .or_else(|| parsed.get_kv("o"))
        .map(PathBuf::from)
        .ok_or_else(|| format!("fce-combined-samples: --output is required\n{SAMPLES_USAGE}"))?;
    let thresholds = parse_threshold_list(
        parsed
            .get_kv("thresholds")
            .map(|value| value.to_string_lossy().into_owned())
            .unwrap_or_else(|| "1,2,5,10,20".to_string())
            .as_str(),
    )?;
    let sample_size = parse_optional_usize(&parsed, "sample-size")?.unwrap_or(60);
    if sample_size == 0 {
        return Err("fce-combined-samples: --sample-size must be positive".to_string());
    }

    let opts = CombinedSampleOptions {
        inputs: parsed.positionals.clone(),
        output,
        relative_to: parsed.get_kv("relative-to").map(PathBuf::from),
        known_stems,
        thresholds,
        sample_size,
        limit_files: parse_optional_usize(&parsed, "limit-files")?,
        limit_games: parse_optional_usize(&parsed, "limit-games")?,
        allow_parse_errors: parsed.has_flag("allow-parse-errors"),
        force: parsed.has_flag("force"),
        show_progress: !parsed.global.no_progress,
    };
    let stats = run_fce_combined_samples(&opts)?;
    println!("{}", stats.to_json());
    Ok(())
}

pub fn run_fce_combined_markers(
    opts: &CombinedMarkerOptions,
) -> Result<CombinedMarkerStats, String> {
    let mut files =
        expand_inputs(&opts.inputs).map_err(|e| format!("input discovery failed: {e}"))?;
    files.retain(|path| path.file_name().and_then(|s| s.to_str()) == Some("fce-table-markers.pgn"));
    if let Some(limit) = opts.limit_files {
        files.truncate(limit);
    }

    if let Some(db_path) = opts.sqlite_db.as_deref() {
        let mut sink = SqliteFactSink::open(db_path, &opts.profile_id, opts.sqlite_batch_rows)?;
        let stats = process_files(opts, &files, &mut sink)?;
        sink.finish()?;
        return finish_or_error(opts, stats);
    }

    let stdout = match opts.output.as_deref() {
        None => true,
        Some(path) => path == Path::new("-"),
    };

    if stdout {
        let stdout = io::stdout();
        let mut writer = BufWriter::new(stdout.lock());
        let mut sink = JsonFactSink {
            writer: &mut writer,
        };
        let stats = process_files(opts, &files, &mut sink)?;
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
    let result = (|| -> Result<CombinedMarkerStats, String> {
        let file = File::create(&temp_path)
            .map_err(|e| format!("failed to create {}: {e}", temp_path.display()))?;
        let mut writer = BufWriter::new(file);
        let mut sink = JsonFactSink {
            writer: &mut writer,
        };
        let stats = process_files(opts, &files, &mut sink)?;
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

pub fn run_fce_combined_samples(
    opts: &CombinedSampleOptions,
) -> Result<CombinedSampleStats, String> {
    let mut files =
        expand_inputs(&opts.inputs).map_err(|e| format!("input discovery failed: {e}"))?;
    files.retain(|path| path.file_name().and_then(|s| s.to_str()) == Some("fce-table-markers.pgn"));
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

    let marker_opts = CombinedMarkerOptions {
        inputs: opts.inputs.clone(),
        output: None,
        sqlite_db: None,
        profile_id: "samples".to_string(),
        sqlite_batch_rows: 100_000,
        relative_to: opts.relative_to.clone(),
        known_stems: opts.known_stems.clone(),
        max_pieces: 64,
        limit_files: opts.limit_files,
        limit_games: opts.limit_games,
        allow_parse_errors: opts.allow_parse_errors,
        force: opts.force,
        show_progress: opts.show_progress,
    };
    let mut sink = SampleSink::new(opts.thresholds.clone(), opts.sample_size);
    let stats = process_files(&marker_opts, &files, &mut sink)?;
    let stats = finish_or_error(&marker_opts, stats)?;
    let temp_path = temp_output_path(&opts.output);
    let write_result = (|| -> Result<(), String> {
        let file = File::create(&temp_path)
            .map_err(|e| format!("failed to create {}: {e}", temp_path.display()))?;
        let mut writer = BufWriter::new(file);
        sink.write_json(&mut writer)?;
        writer
            .flush()
            .map_err(|e| format!("flush {} failed: {e}", temp_path.display()))
    })();
    match write_result {
        Ok(()) => {
            fs::rename(&temp_path, &opts.output).map_err(|e| {
                format!(
                    "failed to rename {} to {}: {e}",
                    temp_path.display(),
                    opts.output.display()
                )
            })?;
        }
        Err(err) => {
            let _ = fs::remove_file(&temp_path);
            return Err(err);
        }
    }
    Ok(CombinedSampleStats {
        files_processed: stats.files_processed,
        bytes_in: stats.bytes_in,
        games_read: stats.games_read,
        samples_seen: sink.total_seen(),
        parse_errors: stats.parse_errors,
    })
}

trait FactSink {
    fn write_game_stem(
        &mut self,
        context: &FileContext,
        game: &GameExtraction,
        stem: &GameStemRun,
    ) -> Result<(), String>;

    fn write_position(
        &mut self,
        context: &FileContext,
        game: &GameExtraction,
        marker: &CapturedMarker,
    ) -> Result<(), String>;
}

struct JsonFactSink<'a, W: Write> {
    writer: &'a mut W,
}

impl<W: Write> FactSink for JsonFactSink<'_, W> {
    fn write_game_stem(
        &mut self,
        context: &FileContext,
        game: &GameExtraction,
        stem: &GameStemRun,
    ) -> Result<(), String> {
        write_game_stem_fact(self.writer, context, game, stem)
            .map_err(|e| format!("failed to write game_stem fact: {e}"))
    }

    fn write_position(
        &mut self,
        context: &FileContext,
        game: &GameExtraction,
        marker: &CapturedMarker,
    ) -> Result<(), String> {
        write_position_fact(self.writer, context, game, marker)
            .map_err(|e| format!("failed to write position fact: {e}"))
    }
}

struct SqliteFactSink {
    insert_game_stem: SqliteStatement,
    insert_position: SqliteStatement,
    insert_evaluation: SqliteStatement,
    db: SqliteDb,
    profile_id: String,
    batch_rows: usize,
    rows_since_commit: usize,
}

impl SqliteFactSink {
    fn open(db_path: &Path, profile_id: &str, batch_rows: usize) -> Result<Self, String> {
        if let Some(parent) = db_path.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
        }
        let db = SqliteDb::open(db_path)?;
        db.exec_batch(
            "
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            PRAGMA cache_size=-200000;
            PRAGMA locking_mode=EXCLUSIVE;
            ",
        )?;
        ensure_sqlite_schema(&db)?;
        db.exec_batch("BEGIN IMMEDIATE TRANSACTION;")?;
        let insert_game_stem = db.prepare(
            "
            INSERT OR IGNORE INTO game_stems (
                source_pgn, source_group, source_bucket, output_pgn,
                game_index, game_key, event, site, date, round, white, black, result,
                stem, max_run_length, position_count,
                marker_index, ply_index, fullmove_number, move_san, move_uci,
                fen, side_to_move, piece_count, run_start_ply, run_end_ply,
                material_side, material_label, material_signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ",
        )?;
        let insert_position = db.prepare(
            "
            INSERT OR IGNORE INTO positions (
                position_key, source_pgn, source_group, source_bucket, output_pgn,
                game_index, game_key, event, site, date, round, white, black, result,
                stem, marker_index, ply_index, fullmove_number, move_san, move_uci,
                fen, side_to_move, piece_count, run_length, run_start_ply, run_end_ply,
                material_side, material_label, material_signature, eval_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ",
        )?;
        let insert_evaluation = db.prepare(
            "
            INSERT OR IGNORE INTO evaluations(eval_key, fen, piece_count)
            VALUES (?, ?, ?)
            ",
        )?;
        Ok(Self {
            insert_game_stem,
            insert_position,
            insert_evaluation,
            db,
            profile_id: profile_id.to_string(),
            batch_rows,
            rows_since_commit: 0,
        })
    }

    fn bump_rows(&mut self, rows: usize) -> Result<(), String> {
        self.rows_since_commit += rows;
        if self.rows_since_commit >= self.batch_rows {
            self.db.exec_batch("COMMIT; BEGIN IMMEDIATE TRANSACTION;")?;
            self.rows_since_commit = 0;
        }
        Ok(())
    }

    fn finish(&mut self) -> Result<(), String> {
        self.db.exec_batch("COMMIT;")?;
        self.rows_since_commit = 0;
        Ok(())
    }
}

impl FactSink for SqliteFactSink {
    fn write_game_stem(
        &mut self,
        context: &FileContext,
        game: &GameExtraction,
        stem: &GameStemRun,
    ) -> Result<(), String> {
        bind_common_game_fields(&mut self.insert_game_stem, context, game, 1)?;
        self.insert_game_stem.bind_text(14, &stem.stem)?;
        self.insert_game_stem
            .bind_i64(15, stem.max_run_length as i64)?;
        self.insert_game_stem
            .bind_i64(16, stem.position_count as i64)?;
        self.insert_game_stem
            .bind_i64(17, stem.first_marker.marker_index as i64)?;
        self.insert_game_stem
            .bind_i64(18, stem.first_marker.ply_index as i64)?;
        self.insert_game_stem
            .bind_i64(19, stem.first_marker.fullmove_number as i64)?;
        self.insert_game_stem
            .bind_text(20, &stem.first_marker.move_san)?;
        self.insert_game_stem
            .bind_text(21, &stem.first_marker.move_uci)?;
        self.insert_game_stem
            .bind_text(22, &stem.first_marker.fen)?;
        self.insert_game_stem
            .bind_text(23, stem.first_marker.side_to_move)?;
        self.insert_game_stem
            .bind_i64(24, stem.first_marker.piece_count as i64)?;
        self.insert_game_stem
            .bind_i64(25, stem.first_marker.run_start_ply as i64)?;
        self.insert_game_stem
            .bind_i64(26, stem.first_marker.run_end_ply as i64)?;
        self.insert_game_stem
            .bind_text(27, stem.first_marker.material_side)?;
        self.insert_game_stem
            .bind_text(28, stem.first_marker.material_label)?;
        self.insert_game_stem
            .bind_text(29, &stem.first_marker.material_signature)?;
        self.insert_game_stem.step_done()?;
        self.insert_game_stem.reset_clear()?;
        self.bump_rows(1)
    }

    fn write_position(
        &mut self,
        context: &FileContext,
        game: &GameExtraction,
        marker: &CapturedMarker,
    ) -> Result<(), String> {
        let eval_key = eval_key_for_fen(&self.profile_id, &marker.fen);
        let position_key = marker_position_key(context, game, marker);
        self.insert_position.bind_text(1, &position_key)?;
        bind_common_game_fields(&mut self.insert_position, context, game, 2)?;
        self.insert_position.bind_text(15, &marker.stem)?;
        self.insert_position
            .bind_i64(16, marker.marker_index as i64)?;
        self.insert_position.bind_i64(17, marker.ply_index as i64)?;
        self.insert_position
            .bind_i64(18, marker.fullmove_number as i64)?;
        self.insert_position.bind_text(19, &marker.move_san)?;
        self.insert_position.bind_text(20, &marker.move_uci)?;
        self.insert_position.bind_text(21, &marker.fen)?;
        self.insert_position.bind_text(22, marker.side_to_move)?;
        self.insert_position
            .bind_i64(23, marker.piece_count as i64)?;
        self.insert_position
            .bind_i64(24, marker.run_length as i64)?;
        self.insert_position
            .bind_i64(25, marker.run_start_ply as i64)?;
        self.insert_position
            .bind_i64(26, marker.run_end_ply as i64)?;
        self.insert_position.bind_text(27, marker.material_side)?;
        self.insert_position.bind_text(28, marker.material_label)?;
        self.insert_position
            .bind_text(29, &marker.material_signature)?;
        self.insert_position.bind_text(30, &eval_key)?;
        self.insert_position.step_done()?;
        self.insert_position.reset_clear()?;

        self.insert_evaluation.bind_text(1, &eval_key)?;
        self.insert_evaluation.bind_text(2, &marker.fen)?;
        self.insert_evaluation
            .bind_i64(3, marker.piece_count as i64)?;
        self.insert_evaluation.step_done()?;
        self.insert_evaluation.reset_clear()?;
        self.bump_rows(2)
    }
}

struct SampleSink {
    thresholds: Vec<usize>,
    sample_size: usize,
    reservoirs: BTreeMap<SourceSampleKey, Reservoir>,
}

impl SampleSink {
    fn new(mut thresholds: Vec<usize>, sample_size: usize) -> Self {
        thresholds.sort_unstable();
        thresholds.dedup();
        Self {
            thresholds,
            sample_size,
            reservoirs: BTreeMap::new(),
        }
    }

    fn total_seen(&self) -> usize {
        self.reservoirs
            .values()
            .map(|reservoir| reservoir.seen)
            .sum()
    }

    fn write_json<W: Write>(&self, out: &mut W) -> Result<(), String> {
        write!(
            out,
            "{{\"schemaVersion\":1,\"kind\":\"fce-sampled-examples\""
        )
        .map_err(|e| format!("failed to write samples: {e}"))?;
        write!(out, ",\"exactness\":\"sampled\"").map_err(|e| e.to_string())?;
        write!(
            out,
            ",\"sampling\":\"source-stratified reservoir over first markers\""
        )
        .map_err(|e| e.to_string())?;
        write!(out, ",\"sampleSize\":{}", self.sample_size).map_err(|e| e.to_string())?;
        write!(out, ",\"thresholds\":[").map_err(|e| e.to_string())?;
        for (idx, threshold) in self.thresholds.iter().enumerate() {
            if idx > 0 {
                write!(out, ",").map_err(|e| e.to_string())?;
            }
            write!(out, "{threshold}").map_err(|e| e.to_string())?;
        }
        write!(out, "],\"views\":{{").map_err(|e| e.to_string())?;
        for (view_idx, view) in ["all", "otb", "online"].iter().enumerate() {
            if view_idx > 0 {
                write!(out, ",").map_err(|e| e.to_string())?;
            }
            write_json_string(out, view).map_err(|e| e.to_string())?;
            write!(out, ":{{\"thresholds\":{{").map_err(|e| e.to_string())?;
            for (threshold_idx, threshold) in self.thresholds.iter().enumerate() {
                if threshold_idx > 0 {
                    write!(out, ",").map_err(|e| e.to_string())?;
                }
                write_json_string(out, &threshold.to_string()).map_err(|e| e.to_string())?;
                write!(out, ":{{\"stems\":{{").map_err(|e| e.to_string())?;
                let stems = self.stems_for_view_threshold(view, *threshold);
                for (stem_idx, stem) in stems.iter().enumerate() {
                    if stem_idx > 0 {
                        write!(out, ",").map_err(|e| e.to_string())?;
                    }
                    write_json_string(out, stem).map_err(|e| e.to_string())?;
                    self.write_view_stem(out, view, *threshold, stem)?;
                }
                write!(out, "}}}}").map_err(|e| e.to_string())?;
            }
            write!(out, "}}}}").map_err(|e| e.to_string())?;
        }
        writeln!(out, "}}}}").map_err(|e| e.to_string())
    }

    fn stems_for_view_threshold(&self, view: &str, threshold: usize) -> Vec<String> {
        let mut stems = BTreeSet::new();
        for key in self.reservoirs.keys() {
            if key.threshold == threshold && source_in_view(&key.source_group, view) {
                stems.insert(key.stem.clone());
            }
        }
        stems.into_iter().collect()
    }

    fn write_view_stem<W: Write>(
        &self,
        out: &mut W,
        view: &str,
        threshold: usize,
        stem: &str,
    ) -> Result<(), String> {
        let mut sources: Vec<(&SourceSampleKey, &Reservoir)> = self
            .reservoirs
            .iter()
            .filter(|(key, reservoir)| {
                key.threshold == threshold
                    && key.stem == stem
                    && source_in_view(&key.source_group, view)
                    && (!reservoir.items.is_empty() || reservoir.seen > 0)
            })
            .collect();
        sources.sort_by(|(a, _), (b, _)| a.source_pgn.cmp(&b.source_pgn));
        let available: usize = sources.iter().map(|(_, reservoir)| reservoir.seen).sum();
        let mut per_source: Vec<(String, Vec<ReservoirItem>, usize)> = sources
            .iter()
            .map(|(key, reservoir)| {
                let mut items = reservoir.items.clone();
                items.sort_by_key(|item| item.key);
                (key.source_pgn.clone(), items, reservoir.seen)
            })
            .collect();
        let mut selected = Vec::new();
        while selected.len() < self.sample_size {
            let mut made_progress = false;
            for (_, items, _) in per_source.iter_mut() {
                if selected.len() >= self.sample_size {
                    break;
                }
                if !items.is_empty() {
                    selected.push(items.remove(0));
                    made_progress = true;
                }
            }
            if !made_progress {
                break;
            }
        }
        selected.sort_by(|a, b| {
            a.example
                .source_pgn
                .cmp(&b.example.source_pgn)
                .then(a.example.game_index.cmp(&b.example.game_index))
                .then(a.example.stem.cmp(&b.example.stem))
        });

        write!(
            out,
            ":{{\"available\":{available},\"sampled\":{}",
            selected.len()
        )
        .map_err(|e| e.to_string())?;
        write!(out, ",\"sourceSplit\":[").map_err(|e| e.to_string())?;
        for (idx, (source_pgn, _, seen)) in per_source.iter().enumerate() {
            if idx > 0 {
                write!(out, ",").map_err(|e| e.to_string())?;
            }
            write!(out, "{{\"sourcePgn\":").map_err(|e| e.to_string())?;
            write_json_string(out, source_pgn).map_err(|e| e.to_string())?;
            write!(out, ",\"available\":{seen}}}").map_err(|e| e.to_string())?;
        }
        write!(out, "],\"examples\":[").map_err(|e| e.to_string())?;
        for (idx, item) in selected.iter().enumerate() {
            if idx > 0 {
                write!(out, ",").map_err(|e| e.to_string())?;
            }
            write_sample_example(out, &item.example).map_err(|e| e.to_string())?;
        }
        write!(out, "]}}").map_err(|e| e.to_string())
    }
}

impl FactSink for SampleSink {
    fn write_game_stem(
        &mut self,
        _context: &FileContext,
        _game: &GameExtraction,
        _stem: &GameStemRun,
    ) -> Result<(), String> {
        Ok(())
    }

    fn write_position(
        &mut self,
        context: &FileContext,
        game: &GameExtraction,
        marker: &CapturedMarker,
    ) -> Result<(), String> {
        let example = sample_example(context, game, marker);
        for threshold in &self.thresholds {
            if marker.run_length < *threshold {
                continue;
            }
            let key = SourceSampleKey {
                source_pgn: context.source_pgn.clone(),
                source_group: context.source_group.clone(),
                threshold: *threshold,
                stem: marker.stem.clone(),
            };
            let sample_key = sample_hash(&example, *threshold);
            self.reservoirs.entry(key).or_default().consider(
                sample_key,
                example.clone(),
                self.sample_size,
            );
        }
        Ok(())
    }
}

fn process_files<S: FactSink>(
    opts: &CombinedMarkerOptions,
    files: &[PathBuf],
    sink: &mut S,
) -> Result<CombinedMarkerStats, String> {
    let total_bytes: u64 = files
        .iter()
        .map(|path| fs::metadata(path).map(|m| m.len()).unwrap_or(0))
        .sum();
    let progress = ProgressReporter::bytes(total_bytes, "fce combined markers", opts.show_progress);
    let mut stats = CombinedMarkerStats::default();
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
        let mut visitor = CombinedMarkerVisitor::new(&opts.known_stems, opts.max_pieces);

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
            for stem in &game.stems {
                sink.write_game_stem(&context, &game, stem)?;
                stats.game_stems_written += 1;
            }
            for marker in &game.markers {
                sink.write_position(&context, &game, marker)?;
                stats.positions_written += 1;
            }
        }
    }

    progress.finish("fce combined markers done");
    Ok(stats)
}

fn finish_or_error(
    opts: &CombinedMarkerOptions,
    stats: CombinedMarkerStats,
) -> Result<CombinedMarkerStats, String> {
    if stats.parse_errors > 0 && !opts.allow_parse_errors {
        return Err(format!(
            "{} PGN game(s) had parse errors; no output was committed. Pass --allow-parse-errors to keep clean rows.",
            stats.parse_errors
        ));
    }
    Ok(stats)
}

fn finalize_runs(
    mut markers: Vec<CapturedMarker>,
    max_pieces: usize,
) -> (Vec<GameStemRun>, Vec<CapturedMarker>) {
    markers.sort_by(|a, b| a.stem.cmp(&b.stem).then(a.ply_index.cmp(&b.ply_index)));
    let mut stems = Vec::new();
    let mut keep_positions = Vec::new();
    let mut cursor = 0usize;
    while cursor < markers.len() {
        let stem = markers[cursor].stem.clone();
        let start = cursor;
        while cursor < markers.len() && markers[cursor].stem == stem {
            cursor += 1;
        }
        let end = cursor;
        let mut first_marker: Option<CapturedMarker> = None;
        let mut run_start = start;
        while run_start < end {
            let mut run_end = run_start + 1;
            while run_end < end && markers[run_end].ply_index == markers[run_end - 1].ply_index + 1
            {
                run_end += 1;
            }
            let length = run_end - run_start;
            let start_ply = markers[run_start].ply_index;
            let end_ply = markers[run_end - 1].ply_index;
            for marker in markers.iter_mut().take(run_end).skip(run_start) {
                marker.run_length = length;
                marker.run_start_ply = start_ply;
                marker.run_end_ply = end_ply;
            }
            if first_marker.is_none() {
                first_marker = Some(markers[run_start].clone());
            }
            run_start = run_end;
        }
        if let Some(marker) = first_marker {
            stems.push(GameStemRun {
                stem,
                max_run_length: marker.run_length,
                position_count: marker.run_length,
                first_marker: marker.clone(),
            });
            if marker.piece_count <= max_pieces {
                keep_positions.push(marker);
            }
        }
    }

    (stems, keep_positions)
}

fn write_game_stem_fact<W: Write>(
    out: &mut W,
    context: &FileContext,
    game: &GameExtraction,
    stem: &GameStemRun,
) -> io::Result<()> {
    write!(out, "{{\"schema_version\":1,\"kind\":\"game_stem\"")?;
    write_common_game_fields(out, context, game)?;
    write_str_field(out, "stem", &stem.stem)?;
    write_num_field(out, "max_run_length", stem.max_run_length)?;
    write_num_field(out, "position_count", stem.position_count)?;
    write_num_field(out, "marker_index", stem.first_marker.marker_index)?;
    write_num_field(out, "ply_index", stem.first_marker.ply_index)?;
    write_num_field(out, "fullmove_number", stem.first_marker.fullmove_number)?;
    write_str_field(out, "move_san", &stem.first_marker.move_san)?;
    write_str_field(out, "move_uci", &stem.first_marker.move_uci)?;
    write_str_field(out, "fen", &stem.first_marker.fen)?;
    write_str_field(out, "side_to_move", stem.first_marker.side_to_move)?;
    write_num_field(out, "piece_count", stem.first_marker.piece_count)?;
    write_num_field(out, "run_start_ply", stem.first_marker.run_start_ply)?;
    write_num_field(out, "run_end_ply", stem.first_marker.run_end_ply)?;
    write_str_field(out, "material_side", stem.first_marker.material_side)?;
    write_str_field(out, "material_label", stem.first_marker.material_label)?;
    write_str_field(
        out,
        "material_signature",
        &stem.first_marker.material_signature,
    )?;
    writeln!(out, "}}")
}

fn write_position_fact<W: Write>(
    out: &mut W,
    context: &FileContext,
    game: &GameExtraction,
    marker: &CapturedMarker,
) -> io::Result<()> {
    write!(out, "{{\"schema_version\":1,\"kind\":\"position\"")?;
    write_common_game_fields(out, context, game)?;
    write_str_field(out, "stem", &marker.stem)?;
    write_num_field(out, "marker_index", marker.marker_index)?;
    write_num_field(out, "ply_index", marker.ply_index)?;
    write_num_field(out, "fullmove_number", marker.fullmove_number)?;
    write_str_field(out, "move_san", &marker.move_san)?;
    write_str_field(out, "move_uci", &marker.move_uci)?;
    write_str_field(out, "fen", &marker.fen)?;
    write_str_field(out, "side_to_move", marker.side_to_move)?;
    write_num_field(out, "piece_count", marker.piece_count)?;
    write_num_field(out, "run_length", marker.run_length)?;
    write_num_field(out, "run_start_ply", marker.run_start_ply)?;
    write_num_field(out, "run_end_ply", marker.run_end_ply)?;
    writeln!(out, "}}")
}

fn sample_example(
    context: &FileContext,
    game: &GameExtraction,
    marker: &CapturedMarker,
) -> SampleExample {
    SampleExample {
        source_pgn: context.source_pgn.clone(),
        source_group: context.source_group.clone(),
        source_bucket: context.source_bucket.clone(),
        output_pgn: context.output_pgn.clone(),
        game_index: game.game_index,
        game_key: game.game_key.clone(),
        event: header_value(game, "Event").to_string(),
        site: header_value(game, "Site").to_string(),
        date: header_value(game, "Date").to_string(),
        round: header_value(game, "Round").to_string(),
        white: header_value(game, "White").to_string(),
        white_elo: header_value(game, "WhiteElo").to_string(),
        black: header_value(game, "Black").to_string(),
        black_elo: header_value(game, "BlackElo").to_string(),
        result: header_value(game, "Result").to_string(),
        stem: marker.stem.clone(),
        ply_index: marker.ply_index,
        fullmove_number: marker.fullmove_number,
        move_san: marker.move_san.clone(),
        move_uci: marker.move_uci.clone(),
        fen: marker.fen.clone(),
        side_to_move: marker.side_to_move,
        piece_count: marker.piece_count,
        run_length: marker.run_length,
        run_start_ply: marker.run_start_ply,
        run_end_ply: marker.run_end_ply,
        material_side: marker.material_side,
        material_label: marker.material_label,
    }
}

fn write_sample_example<W: Write>(out: &mut W, example: &SampleExample) -> io::Result<()> {
    write!(out, "{{")?;
    write_json_pair(out, "sourcePgn", &example.source_pgn, true)?;
    write_json_pair(out, "sourceGroup", &example.source_group, false)?;
    write_json_pair(out, "sourceBucket", &example.source_bucket, false)?;
    write_json_pair(out, "outputPgn", &example.output_pgn, false)?;
    write_num_pair(out, "gameIndex", example.game_index, false)?;
    write_json_pair(out, "gameKey", &example.game_key, false)?;
    write_json_pair(out, "event", &example.event, false)?;
    write_json_pair(out, "site", &example.site, false)?;
    write_json_pair(out, "date", &example.date, false)?;
    write_json_pair(out, "round", &example.round, false)?;
    write_json_pair(out, "white", &example.white, false)?;
    write_json_pair(out, "whiteElo", &example.white_elo, false)?;
    write_json_pair(out, "black", &example.black, false)?;
    write_json_pair(out, "blackElo", &example.black_elo, false)?;
    write_json_pair(out, "result", &example.result, false)?;
    write_json_pair(out, "stem", &example.stem, false)?;
    write_num_pair(out, "plyIndex", example.ply_index, false)?;
    write_num_pair(out, "fullmoveNumber", example.fullmove_number, false)?;
    write_json_pair(out, "moveSan", &example.move_san, false)?;
    write_json_pair(out, "moveUci", &example.move_uci, false)?;
    write_json_pair(out, "fen", &example.fen, false)?;
    write_json_pair(out, "sideToMove", example.side_to_move, false)?;
    write_num_pair(out, "pieceCount", example.piece_count, false)?;
    write_num_pair(out, "runLength", example.run_length, false)?;
    write_num_pair(out, "runStartPly", example.run_start_ply, false)?;
    write_num_pair(out, "runEndPly", example.run_end_ply, false)?;
    write_json_pair(out, "materialSide", example.material_side, false)?;
    write_json_pair(out, "materialLabel", example.material_label, false)?;
    write!(out, "}}")
}

fn write_json_pair<W: Write>(out: &mut W, key: &str, value: &str, first: bool) -> io::Result<()> {
    if !first {
        write!(out, ",")?;
    }
    write_json_string(out, key)?;
    write!(out, ":")?;
    write_json_string(out, value)
}

fn write_num_pair<W: Write, T: std::fmt::Display>(
    out: &mut W,
    key: &str,
    value: T,
    first: bool,
) -> io::Result<()> {
    if !first {
        write!(out, ",")?;
    }
    write_json_string(out, key)?;
    write!(out, ":{value}")
}

fn write_common_game_fields<W: Write>(
    out: &mut W,
    context: &FileContext,
    game: &GameExtraction,
) -> io::Result<()> {
    write_str_field(out, "source_pgn", &context.source_pgn)?;
    write_str_field(out, "source_group", &context.source_group)?;
    write_str_field(out, "source_bucket", &context.source_bucket)?;
    write_str_field(out, "output_pgn", &context.output_pgn)?;
    write_num_field(out, "game_index", game.game_index)?;
    write_str_field(out, "game_key", &game.game_key)?;
    write_header_field(out, "event", &game.headers, "Event")?;
    write_header_field(out, "site", &game.headers, "Site")?;
    write_header_field(out, "date", &game.headers, "Date")?;
    write_header_field(out, "round", &game.headers, "Round")?;
    write_header_field(out, "white", &game.headers, "White")?;
    write_header_field(out, "black", &game.headers, "Black")?;
    write_header_field(out, "result", &game.headers, "Result")
}

fn bind_common_game_fields(
    stmt: &mut SqliteStatement,
    context: &FileContext,
    game: &GameExtraction,
    start_index: c_int,
) -> Result<(), String> {
    stmt.bind_text(start_index, &context.source_pgn)?;
    stmt.bind_text(start_index + 1, &context.source_group)?;
    stmt.bind_text(start_index + 2, &context.source_bucket)?;
    stmt.bind_text(start_index + 3, &context.output_pgn)?;
    stmt.bind_i64(start_index + 4, game.game_index as i64)?;
    stmt.bind_text(start_index + 5, &game.game_key)?;
    stmt.bind_text(start_index + 6, header_value(game, "Event"))?;
    stmt.bind_text(start_index + 7, header_value(game, "Site"))?;
    stmt.bind_text(start_index + 8, header_value(game, "Date"))?;
    stmt.bind_text(start_index + 9, header_value(game, "Round"))?;
    stmt.bind_text(start_index + 10, header_value(game, "White"))?;
    stmt.bind_text(start_index + 11, header_value(game, "Black"))?;
    stmt.bind_text(start_index + 12, header_value(game, "Result"))
}

fn header_value<'a>(game: &'a GameExtraction, key: &str) -> &'a str {
    game.headers.get(key).map(String::as_str).unwrap_or("")
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

fn extract_known_stems(comment: &[u8], known_stems: &BTreeSet<String>) -> Vec<String> {
    let text = String::from_utf8_lossy(trim_ascii(comment));
    if known_stems.contains(text.as_ref()) {
        return vec![text.into_owned()];
    }
    let mut stems = BTreeSet::new();
    for token in text.split_whitespace() {
        if known_stems.contains(token) {
            stems.insert(token.to_string());
        }
    }
    stems.into_iter().collect()
}

fn parse_known_stems(raw: &str) -> BTreeSet<String> {
    raw.split(|ch: char| ch == ',' || ch.is_ascii_whitespace())
        .map(str::trim)
        .filter(|stem| !stem.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn parse_threshold_list(raw: &str) -> Result<Vec<usize>, String> {
    let mut values = Vec::new();
    for token in raw.split(',') {
        let token = token.trim();
        if token.is_empty() {
            continue;
        }
        let value = token
            .parse::<usize>()
            .map_err(|e| format!("invalid --thresholds value {token:?}: {e}"))?;
        if value == 0 {
            return Err("fce-combined-samples: thresholds must be positive".to_string());
        }
        values.push(value);
    }
    if values.is_empty() {
        return Err("fce-combined-samples: --thresholds must not be empty".to_string());
    }
    values.sort_unstable();
    values.dedup();
    Ok(values)
}

fn source_in_view(source_group: &str, view: &str) -> bool {
    view == "all" || source_group == view
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
    let source_group = classify_source_group(&source_pgn).to_string();
    FileContext {
        source_pgn,
        source_group,
        source_bucket,
        output_pgn,
    }
}

fn display_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn classify_source_group(source_pgn: &str) -> &'static str {
    if source_pgn.starts_with("LumbrasGigaBase_OTB_") {
        "otb"
    } else if source_pgn.starts_with("LumbrasGigaBase_Online_") {
        "online"
    } else {
        "unknown"
    }
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

fn eval_key_for_fen(profile_id: &str, fen: &str) -> String {
    let mut material = String::with_capacity(profile_id.len() + fen.len() + 1);
    material.push_str(profile_id);
    material.push('\0');
    material.push_str(fen);
    format!("{:032x}", xxh3_128(material.as_bytes()))
}

fn marker_position_key(
    context: &FileContext,
    game: &GameExtraction,
    marker: &CapturedMarker,
) -> String {
    let mut material = String::new();
    material.push_str(&context.source_pgn);
    material.push('\x1f');
    material.push_str(&game.game_key);
    material.push('\x1f');
    material.push_str(&marker.stem);
    material.push('\x1f');
    material.push_str(&marker.ply_index.to_string());
    material.push('\x1f');
    material.push_str(&marker.fen);
    format!("{:032x}", xxh3_128(material.as_bytes()))
}

fn sample_hash(example: &SampleExample, threshold: usize) -> u128 {
    let mut material = String::new();
    material.push_str(&example.source_pgn);
    material.push('\x1f');
    material.push_str(&example.game_key);
    material.push('\x1f');
    material.push_str(&example.stem);
    material.push('\x1f');
    material.push_str(&example.ply_index.to_string());
    material.push('\x1f');
    material.push_str(&threshold.to_string());
    material.push('\x1f');
    material.push_str(&example.fen);
    xxh3_128(material.as_bytes())
}

fn side_counts(pos: &Chess, color: Color) -> SideCounts {
    let board = pos.board();
    let side = board.by_color(color);
    SideCounts {
        q: (board.by_role(Role::Queen) & side).count(),
        r: (board.by_role(Role::Rook) & side).count(),
        b: (board.by_role(Role::Bishop) & side).count(),
        n: (board.by_role(Role::Knight) & side).count(),
        p: (board.by_role(Role::Pawn) & side).count(),
    }
}

fn nonking(counts: SideCounts) -> usize {
    counts.q + counts.r + counts.b + counts.n + counts.p
}

fn minor_count(counts: SideCounts) -> usize {
    counts.b + counts.n
}

fn side_material_text(counts: SideCounts) -> String {
    let mut parts = String::new();
    push_piece_count(&mut parts, "Q", counts.q);
    push_piece_count(&mut parts, "R", counts.r);
    push_piece_count(&mut parts, "B", counts.b);
    push_piece_count(&mut parts, "N", counts.n);
    push_piece_count(&mut parts, "P", counts.p);
    if parts.is_empty() {
        "bare".to_string()
    } else {
        parts
    }
}

fn push_piece_count(out: &mut String, symbol: &str, count: usize) {
    if count == 1 {
        out.push_str(symbol);
    } else if count > 1 {
        out.push_str(symbol);
        out.push_str(&count.to_string());
    }
}

fn material_signature(pos: &Chess) -> String {
    format!(
        "{}v{}",
        side_material_text(side_counts(pos, Color::White)),
        side_material_text(side_counts(pos, Color::Black))
    )
}

fn select_material_side<F>(pos: &Chess, label: &'static str, predicate: F) -> MaterialPerspective
where
    F: Fn(SideCounts, SideCounts) -> bool,
{
    let white = side_counts(pos, Color::White);
    let black = side_counts(pos, Color::Black);
    let white_match = predicate(white, black);
    let black_match = predicate(black, white);
    let material_side = match (white_match, black_match) {
        (true, false) => "white",
        (false, true) => "black",
        (true, true) => "symmetric",
        (false, false) => "unknown",
    };
    MaterialPerspective {
        material_side,
        material_label: label,
        material_signature: material_signature(pos),
    }
}

fn classify_material_side(ending: &str, pos: &Chess) -> MaterialPerspective {
    if matches!(
        ending,
        "2-0Pp" | "3-2NN" | "4-2scBB" | "4-3ocBB" | "6-2-0Rr" | "6-3RRrr" | "8-3RAra" | "9-2Qq"
    ) {
        return MaterialPerspective {
            material_side: "symmetric",
            material_label: "symmetric/either side",
            material_signature: material_signature(pos),
        };
    }

    match ending {
        "1-4BN" => select_material_side(pos, "bishop+knight side", |own, opp| {
            own.b >= 1 && own.n >= 1 && nonking(opp) == 0
        }),
        "2-1P" => {
            select_material_side(pos, "pawn side", |own, opp| own.p >= 1 && nonking(opp) == 0)
        }
        "3-1Np" => select_material_side(pos, "knight side", |own, opp| own.n >= 1 && opp.p >= 1),
        "4-1Bp" => select_material_side(pos, "bishop side", |own, opp| own.b >= 1 && opp.p >= 1),
        "5-0BN" => select_material_side(pos, "bishop side", |own, opp| own.b >= 1 && opp.n >= 1),
        "6-1-0RP" => select_material_side(pos, "rook side", |own, opp| own.r >= 1 && opp.p >= 1),
        "6-2-1RPr" => select_material_side(pos, "rook+pawn side", |own, opp| {
            own.r >= 1 && own.p >= 1 && opp.r >= 1
        }),
        "6-2-2RPPr" | "6-2-2RPPrConnected" => {
            select_material_side(pos, "rook+two-pawns side", |own, opp| {
                own.r >= 1 && own.p >= 2 && opp.r >= 1
            })
        }
        "7-1RN" => select_material_side(pos, "rook side", |own, opp| own.r >= 1 && opp.n >= 1),
        "7-2RB" => select_material_side(pos, "rook side", |own, opp| own.r >= 1 && opp.b >= 1),
        "8-1RNr" | "8-1RNrNoPawns" => select_material_side(pos, "rook+knight side", |own, opp| {
            own.r >= 1 && own.n >= 1 && opp.r >= 1
        }),
        "8-2RBr" | "8-2RBrNoPawns" => select_material_side(pos, "rook+bishop side", |own, opp| {
            own.r >= 1 && own.b >= 1 && opp.r >= 1
        }),
        "9-1Qp" => select_material_side(pos, "queen side", |own, opp| own.q >= 1 && opp.p >= 1),
        "9-3QPq" => select_material_side(pos, "queen+pawn side", |own, opp| {
            own.q >= 1 && own.p >= 1 && opp.q >= 1
        }),
        "10-1Qa" => select_material_side(pos, "queen side", |own, opp| {
            own.q >= 1 && minor_count(opp) >= 1
        }),
        "10-3Qaa" => select_material_side(pos, "queen side", |own, opp| {
            own.q >= 1 && minor_count(opp) >= 2
        }),
        "10-6Qaaa" => select_material_side(pos, "queen side", |own, opp| {
            own.q >= 1 && minor_count(opp) >= 3
        }),
        "10-2Qr" | "10-2QrNoPawns" => {
            select_material_side(pos, "queen side", |own, opp| own.q >= 1 && opp.r >= 1)
        }
        "10-4Qra" => select_material_side(pos, "queen side", |own, opp| {
            own.q >= 1 && opp.r >= 1 && minor_count(opp) >= 1
        }),
        "10-5Qrr" => select_material_side(pos, "queen side", |own, opp| own.q >= 1 && opp.r >= 2),
        "10-7QAq" => select_material_side(pos, "queen+minor side", |own, opp| {
            own.q >= 1 && minor_count(own) >= 1 && opp.q >= 1
        }),
        "10-7-1Qbrr" | "10-7-1QbrrNoPawns" => {
            select_material_side(pos, "queen+bishop side", |own, opp| {
                own.q >= 1 && own.b >= 1 && opp.r >= 2
            })
        }
        _ => MaterialPerspective {
            material_side: "unknown",
            material_label: "unknown",
            material_signature: material_signature(pos),
        },
    }
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
        .unwrap_or("fce-combined-markers.jsonl");
    output_path.with_file_name(format!(".{file_name}.tmp-{}", std::process::id()))
}

fn ensure_sqlite_schema(db: &SqliteDb) -> Result<(), String> {
    db.exec_batch(
        "
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS game_stems (
            source_pgn TEXT NOT NULL,
            source_group TEXT NOT NULL,
            source_bucket TEXT NOT NULL,
            output_pgn TEXT NOT NULL,
            game_index INTEGER NOT NULL,
            game_key TEXT NOT NULL,
            event TEXT NOT NULL,
            site TEXT NOT NULL,
            date TEXT NOT NULL,
            round TEXT NOT NULL,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result TEXT NOT NULL,
            stem TEXT NOT NULL,
            max_run_length INTEGER NOT NULL,
            position_count INTEGER NOT NULL,
            marker_index INTEGER NOT NULL,
            ply_index INTEGER NOT NULL,
            fullmove_number INTEGER NOT NULL,
            move_san TEXT NOT NULL,
            move_uci TEXT NOT NULL,
            fen TEXT NOT NULL,
            side_to_move TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            run_start_ply INTEGER NOT NULL,
            run_end_ply INTEGER NOT NULL,
            material_side TEXT NOT NULL,
            material_label TEXT NOT NULL,
            material_signature TEXT NOT NULL,
            PRIMARY KEY(source_pgn, game_key, stem)
        );

        CREATE TABLE IF NOT EXISTS positions (
            position_key TEXT PRIMARY KEY,
            source_pgn TEXT NOT NULL,
            source_group TEXT NOT NULL,
            source_bucket TEXT NOT NULL,
            output_pgn TEXT NOT NULL,
            game_index INTEGER NOT NULL,
            game_key TEXT NOT NULL,
            event TEXT NOT NULL,
            site TEXT NOT NULL,
            date TEXT NOT NULL,
            round TEXT NOT NULL,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result TEXT NOT NULL,
            stem TEXT NOT NULL,
            marker_index INTEGER NOT NULL,
            ply_index INTEGER NOT NULL,
            fullmove_number INTEGER NOT NULL,
            move_san TEXT NOT NULL,
            move_uci TEXT NOT NULL,
            fen TEXT NOT NULL,
            side_to_move TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            run_length INTEGER NOT NULL,
            run_start_ply INTEGER NOT NULL,
            run_end_ply INTEGER NOT NULL,
            material_side TEXT NOT NULL,
            material_label TEXT NOT NULL,
            material_signature TEXT NOT NULL,
            eval_key TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evaluations (
            eval_key TEXT PRIMARY KEY,
            fen TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            eval_source TEXT NOT NULL DEFAULT 'pending',
            winning_side TEXT NOT NULL DEFAULT 'unknown',
            tb_wdl INTEGER,
            tb_dtz INTEGER,
            sf_cp_white INTEGER,
            sf_mate_white INTEGER,
            sf_time_seconds REAL,
            draw_threshold_cp INTEGER,
            eval_status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT NOT NULL DEFAULT '',
            evaluated_at TEXT
        );
        ",
    )
}

#[repr(C)]
struct sqlite3 {
    _private: [u8; 0],
}

#[repr(C)]
struct sqlite3_stmt {
    _private: [u8; 0],
}

type SqliteDestructor = Option<unsafe extern "C" fn(*mut c_void)>;

const SQLITE_OK: c_int = 0;
const SQLITE_DONE: c_int = 101;
const SQLITE_OPEN_READWRITE: c_int = 0x0000_0002;
const SQLITE_OPEN_CREATE: c_int = 0x0000_0004;
const SQLITE_OPEN_NOMUTEX: c_int = 0x0000_8000;

#[link(name = "sqlite3")]
extern "C" {
    fn sqlite3_open_v2(
        filename: *const c_char,
        pp_db: *mut *mut sqlite3,
        flags: c_int,
        z_vfs: *const c_char,
    ) -> c_int;
    fn sqlite3_close(db: *mut sqlite3) -> c_int;
    fn sqlite3_errmsg(db: *mut sqlite3) -> *const c_char;
    fn sqlite3_exec(
        db: *mut sqlite3,
        sql: *const c_char,
        callback: Option<
            unsafe extern "C" fn(*mut c_void, c_int, *mut *mut c_char, *mut *mut c_char) -> c_int,
        >,
        arg: *mut c_void,
        errmsg: *mut *mut c_char,
    ) -> c_int;
    fn sqlite3_prepare_v2(
        db: *mut sqlite3,
        sql: *const c_char,
        n_byte: c_int,
        pp_stmt: *mut *mut sqlite3_stmt,
        pz_tail: *mut *const c_char,
    ) -> c_int;
    fn sqlite3_finalize(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_step(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_reset(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_clear_bindings(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_bind_int64(stmt: *mut sqlite3_stmt, idx: c_int, value: i64) -> c_int;
    fn sqlite3_bind_text(
        stmt: *mut sqlite3_stmt,
        idx: c_int,
        value: *const c_char,
        n: c_int,
        destructor: SqliteDestructor,
    ) -> c_int;
}

fn sqlite_transient() -> SqliteDestructor {
    unsafe { std::mem::transmute::<isize, SqliteDestructor>(-1) }
}

struct SqliteDb {
    raw: *mut sqlite3,
}

impl SqliteDb {
    fn open(path: &Path) -> Result<Self, String> {
        let path_text = path.to_string_lossy();
        let c_path = CString::new(path_text.as_bytes())
            .map_err(|_| format!("SQLite path contains NUL byte: {}", path.display()))?;
        let mut raw = ptr::null_mut();
        let rc = unsafe {
            sqlite3_open_v2(
                c_path.as_ptr(),
                &mut raw,
                SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_NOMUTEX,
                ptr::null(),
            )
        };
        if rc != SQLITE_OK {
            let message = sqlite_error(raw);
            if !raw.is_null() {
                unsafe {
                    sqlite3_close(raw);
                }
            }
            return Err(format!(
                "failed to open SQLite DB {}: {message}",
                path.display()
            ));
        }
        Ok(Self { raw })
    }

    fn exec_batch(&self, sql: &str) -> Result<(), String> {
        let c_sql = CString::new(sql)
            .map_err(|_| "SQLite SQL text unexpectedly contains NUL byte".to_string())?;
        let rc = unsafe {
            sqlite3_exec(
                self.raw,
                c_sql.as_ptr(),
                None,
                ptr::null_mut(),
                ptr::null_mut(),
            )
        };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.raw));
        }
        Ok(())
    }

    fn prepare(&self, sql: &str) -> Result<SqliteStatement, String> {
        let c_sql = CString::new(sql)
            .map_err(|_| "SQLite SQL text unexpectedly contains NUL byte".to_string())?;
        let mut stmt = ptr::null_mut();
        let rc =
            unsafe { sqlite3_prepare_v2(self.raw, c_sql.as_ptr(), -1, &mut stmt, ptr::null_mut()) };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.raw));
        }
        Ok(SqliteStatement {
            db: self.raw,
            raw: stmt,
        })
    }
}

impl Drop for SqliteDb {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe {
                sqlite3_close(self.raw);
            }
        }
    }
}

struct SqliteStatement {
    db: *mut sqlite3,
    raw: *mut sqlite3_stmt,
}

impl SqliteStatement {
    fn bind_text(&mut self, idx: c_int, value: &str) -> Result<(), String> {
        let c_value = CString::new(value.as_bytes())
            .map_err(|_| format!("SQLite text value for bind {idx} contains NUL byte"))?;
        let rc = unsafe {
            sqlite3_bind_text(
                self.raw,
                idx,
                c_value.as_ptr(),
                value.len() as c_int,
                sqlite_transient(),
            )
        };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }

    fn bind_i64(&mut self, idx: c_int, value: i64) -> Result<(), String> {
        let rc = unsafe { sqlite3_bind_int64(self.raw, idx, value) };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }

    fn step_done(&mut self) -> Result<(), String> {
        let rc = unsafe { sqlite3_step(self.raw) };
        if rc != SQLITE_DONE {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }

    fn reset_clear(&mut self) -> Result<(), String> {
        let reset_rc = unsafe { sqlite3_reset(self.raw) };
        if reset_rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        let clear_rc = unsafe { sqlite3_clear_bindings(self.raw) };
        if clear_rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }
}

impl Drop for SqliteStatement {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe {
                sqlite3_finalize(self.raw);
            }
        }
    }
}

fn sqlite_error(db: *mut sqlite3) -> String {
    if db.is_null() {
        return "unknown SQLite error".to_string();
    }
    unsafe {
        let ptr = sqlite3_errmsg(db);
        if ptr.is_null() {
            "unknown SQLite error".to_string()
        } else {
            CStr::from_ptr(ptr).to_string_lossy().into_owned()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_full_comment_or_tokens() {
        let known = parse_known_stems("3-2NN,8-1RNrNoPawns 8-1RNr");
        assert_eq!(extract_known_stems(b" 3-2NN ", &known), vec!["3-2NN"]);
        assert_eq!(
            extract_known_stems(b"8-1RNrNoPawns 8-1RNr", &known),
            vec!["8-1RNr", "8-1RNrNoPawns"]
        );
        assert!(extract_known_stems(b"Game number 1", &known).is_empty());
    }

    #[test]
    fn finalizes_consecutive_runs() {
        let markers = vec![
            marker("A", 3, 4),
            marker("A", 4, 4),
            marker("A", 8, 6),
            marker("B", 9, 4),
        ];
        let (stems, positions) = finalize_runs(markers, 5);
        assert_eq!(stems.len(), 2);
        assert_eq!(stems[0].stem, "A");
        assert_eq!(stems[0].max_run_length, 2);
        assert_eq!(stems[0].position_count, 2);
        assert_eq!(stems[1].stem, "B");
        assert_eq!(positions.len(), 2);
        assert_eq!(positions[0].run_length, 2);
        assert_eq!(positions[1].stem, "B");
        assert_eq!(positions[1].run_length, 1);
    }

    fn marker(stem: &str, ply_index: u32, piece_count: usize) -> CapturedMarker {
        CapturedMarker {
            marker_index: 1,
            stem: stem.to_string(),
            ply_index,
            fullmove_number: 1,
            move_san: String::new(),
            move_uci: String::new(),
            fen: String::new(),
            side_to_move: "white",
            piece_count,
            material_side: "unknown",
            material_label: "unknown",
            material_signature: "barevbare".to_string(),
            run_length: 0,
            run_start_ply: 0,
            run_end_ply: 0,
        }
    }
}
