use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use pgn_reader::{BufferedReader, Outcome, RawComment, RawTag, SanPlus, Skip, Visitor};
use shakmaty::fen::Fen;
use shakmaty::{CastlingMode, Chess, Color, EnPassantMode, Position};
use xxhash_rust::xxh3::xxh3_128;

type Result<T> = std::result::Result<T, SiteError>;

#[derive(Debug)]
struct SiteError(String);

impl SiteError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl std::fmt::Display for SiteError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for SiteError {}

impl From<std::io::Error> for SiteError {
    fn from(value: std::io::Error) -> Self {
        Self(value.to_string())
    }
}

impl From<serde_json::Error> for SiteError {
    fn from(value: serde_json::Error) -> Self {
        Self(value.to_string())
    }
}

#[derive(Debug, Clone)]
struct BuildConfig {
    annotated_run_dir: Option<PathBuf>,
    pgn_paths: Vec<PathBuf>,
    summary_csv: Option<PathBuf>,
    known_stems: BTreeSet<String>,
    catalog_csv: Option<PathBuf>,
    source_totals_json: Option<PathBuf>,
    output_dir: PathBuf,
    title: String,
    generic_stem: Option<String>,
    examples: bool,
    sample_size: usize,
}

#[derive(Debug, Clone)]
struct SourceInput {
    source_pgn: String,
    output_pgn: String,
    path: PathBuf,
    implicit_stems: BTreeSet<String>,
    source_id: String,
    label: String,
    group: String,
    bucket: String,
}

#[derive(Debug, Clone, Default)]
struct CatalogEntry {
    label: String,
    group: String,
    description: String,
    color: String,
}

#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct CountPair {
    games: u64,
    instances: u64,
    exclusive_games: u64,
    overlap_games: u64,
}

#[derive(Debug, Clone, Default)]
struct PatternAggregate {
    stem: String,
    label: String,
    group: String,
    description: String,
    color: String,
    summary_count: u64,
    games: u64,
    instances: u64,
    exclusive_games: u64,
    overlap_games: u64,
}

#[derive(Debug, Clone)]
struct SourceAggregate {
    input: SourceInput,
    denominator_games: Option<u64>,
    annotated_games: u64,
    games_with_any_marker: u64,
    pattern_game_incidences: u64,
    pattern_instances: u64,
    multi_pattern_games: u64,
    max_patterns_in_game: usize,
    patterns: BTreeMap<String, CountPair>,
    pairs: BTreeMap<(String, String), u64>,
    eco_bases: BTreeMap<String, u64>,
    rating_bands: BTreeMap<String, u64>,
    results: BTreeMap<String, u64>,
}

impl SourceAggregate {
    fn new(input: SourceInput, denominator_games: Option<u64>) -> Self {
        Self {
            input,
            denominator_games,
            annotated_games: 0,
            games_with_any_marker: 0,
            pattern_game_incidences: 0,
            pattern_instances: 0,
            multi_pattern_games: 0,
            max_patterns_in_game: 0,
            patterns: BTreeMap::new(),
            pairs: BTreeMap::new(),
            eco_bases: BTreeMap::new(),
            rating_bands: BTreeMap::new(),
            results: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SourceTotals {
    files: Vec<SourceTotalFile>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SourceTotalFile {
    source_pgn: String,
    games: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DashboardData {
    schema_version: u32,
    title: String,
    input_label: String,
    has_source_totals: bool,
    generic_stem: String,
    totals: DashboardTotals,
    patterns: Vec<PatternOutput>,
    sources: Vec<SourceOutput>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DashboardTotals {
    sources: usize,
    markers: usize,
    annotated_games: u64,
    denominator_games: u64,
    games_with_any_marker: u64,
    pattern_game_incidences: u64,
    pattern_instances: u64,
    multi_pattern_games: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PatternOutput {
    stem: String,
    label: String,
    group: String,
    description: String,
    color: String,
    summary_count: u64,
    games: u64,
    instances: u64,
    exclusive_games: u64,
    overlap_games: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SourceOutput {
    id: String,
    label: String,
    group: String,
    bucket: String,
    source_pgn: String,
    output_pgn: String,
    path: String,
    denominator_games: u64,
    annotated_games: u64,
    games_with_any_marker: u64,
    pattern_game_incidences: u64,
    pattern_instances: u64,
    multi_pattern_games: u64,
    max_patterns_in_game: usize,
    patterns: BTreeMap<String, CountPair>,
    pairs: Vec<(String, String, u64)>,
    eco_bases: BTreeMap<String, u64>,
    rating_bands: BTreeMap<String, u64>,
    results: BTreeMap<String, u64>,
}

#[derive(Debug, Clone)]
struct CapturedExampleMarker {
    stem: String,
    ply_index: u32,
    fullmove_number: u32,
    move_san: String,
    move_uci: String,
    fen: String,
    side_to_move: &'static str,
    piece_count: usize,
}

#[derive(Debug, Clone)]
struct ExampleGame {
    game_index: usize,
    headers: BTreeMap<String, String>,
    game_key: String,
    markers: Vec<CapturedExampleMarker>,
    parse_error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SampleData {
    schema_version: u32,
    kind: String,
    sample_size: usize,
    sampling: String,
    views: BTreeMap<String, SampleView>,
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
struct SampleView {
    stems: BTreeMap<String, StemSamples>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct StemSamples {
    available: usize,
    sampled: usize,
    source_split: Vec<SourceSampleSplit>,
    examples: Vec<SampleExample>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SourceSampleSplit {
    source_pgn: String,
    available: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
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
    eco_raw: String,
    eco_base: String,
    stem: String,
    ply_index: u32,
    fullmove_number: u32,
    move_san: String,
    move_uci: String,
    fen: String,
    side_to_move: &'static str,
    piece_count: usize,
}

#[derive(Debug, Clone)]
struct ReservoirItem {
    key: u128,
    example: SampleExample,
}

#[derive(Debug, Clone, Default)]
struct Reservoir {
    seen: usize,
    items: Vec<ReservoirItem>,
    max_index: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct SampleKey {
    view: String,
    source_pgn: String,
    stem: String,
}

#[derive(Debug, Default)]
struct SampleStore {
    sample_size: usize,
    reservoirs: BTreeMap<SampleKey, Reservoir>,
}

#[derive(Debug, Default)]
struct GameState {
    headers: BTreeMap<String, String>,
    stems: BTreeSet<String>,
    instances: BTreeMap<String, u64>,
    in_comment: bool,
    comment: String,
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("{err}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<()> {
    let config = parse_args(env::args_os().skip(1))?;
    build_site(&config)?;
    println!(
        "Wrote generic CQL dashboard: {}",
        config.output_dir.display()
    );
    println!("Open: {}", config.output_dir.join("index.html").display());
    Ok(())
}

fn parse_args<I>(args: I) -> Result<BuildConfig>
where
    I: IntoIterator<Item = OsString>,
{
    let mut raw: Vec<OsString> = args.into_iter().collect();
    if raw.is_empty() || matches!(raw[0].to_string_lossy().as_ref(), "-h" | "--help" | "help") {
        return Err(SiteError::new(usage()));
    }
    let command = raw.remove(0).to_string_lossy().into_owned();
    if command != "build" {
        return Err(SiteError::new(format!(
            "unknown command {command:?}\n{}",
            usage()
        )));
    }

    let mut annotated_run_dir = None;
    let mut pgn_paths = Vec::new();
    let mut summary_csv = None;
    let mut known_stems = BTreeSet::new();
    let mut catalog_csv = None;
    let mut source_totals_json = None;
    let mut output_dir = PathBuf::from("out/cql-site");
    let mut title = "CQL incidence dashboard".to_string();
    let mut generic_stem = None;
    let mut examples = false;
    let mut sample_size = 32usize;
    let mut i = 0usize;
    while i < raw.len() {
        let arg = raw[i].to_string_lossy();
        match arg.as_ref() {
            "--annotated-run-dir" | "--run-dir" => {
                annotated_run_dir = Some(next_path(&raw, &mut i, "--annotated-run-dir")?);
            }
            "--pgn" => {
                pgn_paths.push(next_path(&raw, &mut i, "--pgn")?);
            }
            "--summary-csv" => {
                summary_csv = Some(next_path(&raw, &mut i, "--summary-csv")?);
            }
            "--known-stems" => {
                for stem in split_stem_list(&next_string(&raw, &mut i, "--known-stems")?) {
                    known_stems.insert(stem);
                }
            }
            "--catalog-csv" => {
                catalog_csv = Some(next_path(&raw, &mut i, "--catalog-csv")?);
            }
            "--source-totals-json" => {
                source_totals_json = Some(next_path(&raw, &mut i, "--source-totals-json")?);
            }
            "--output-dir" => {
                output_dir = next_path(&raw, &mut i, "--output-dir")?;
            }
            "--title" => {
                title = next_string(&raw, &mut i, "--title")?;
            }
            "--generic-stem" => {
                generic_stem = Some(next_string(&raw, &mut i, "--generic-stem")?);
            }
            "--examples" => {
                examples = true;
                i += 1;
            }
            "--sample-size" => {
                sample_size = parse_positive_usize(
                    &next_string(&raw, &mut i, "--sample-size")?,
                    "--sample-size",
                )?;
            }
            _ => {
                return Err(SiteError::new(format!(
                    "unknown build option {arg:?}\n{}",
                    usage()
                )));
            }
        }
    }

    if annotated_run_dir.is_some() && !pgn_paths.is_empty() {
        return Err(SiteError::new(
            "use either --annotated-run-dir or one or more --pgn arguments, not both",
        ));
    }
    if annotated_run_dir.is_none() && pgn_paths.is_empty() {
        return Err(SiteError::new(
            "missing input: pass --annotated-run-dir or one or more --pgn arguments",
        ));
    }

    Ok(BuildConfig {
        annotated_run_dir,
        pgn_paths,
        summary_csv,
        known_stems,
        catalog_csv,
        source_totals_json,
        output_dir,
        title,
        generic_stem,
        examples,
        sample_size,
    })
}

fn usage() -> String {
    "usage: cql-site build (--annotated-run-dir RUN_DIR | --pgn FILE...) [--known-stems a,b,c] [--catalog-csv CSV] [--source-totals-json JSON] [--examples] [--sample-size N] [--output-dir OUT] [--title TITLE]".to_string()
}

fn next_path(args: &[OsString], i: &mut usize, flag: &str) -> Result<PathBuf> {
    *i += 1;
    let value = args
        .get(*i)
        .ok_or_else(|| SiteError::new(format!("{flag} requires a value")))?;
    *i += 1;
    Ok(PathBuf::from(value))
}

fn next_string(args: &[OsString], i: &mut usize, flag: &str) -> Result<String> {
    *i += 1;
    let value = args
        .get(*i)
        .ok_or_else(|| SiteError::new(format!("{flag} requires a value")))?;
    *i += 1;
    Ok(value.to_string_lossy().into_owned())
}

fn parse_positive_usize(text: &str, flag: &str) -> Result<usize> {
    let value = text
        .parse::<usize>()
        .map_err(|err| SiteError::new(format!("{flag} must be a positive integer: {err}")))?;
    if value == 0 {
        return Err(SiteError::new(format!("{flag} must be a positive integer")));
    }
    Ok(value)
}

fn build_site(config: &BuildConfig) -> Result<()> {
    let catalog = load_catalog(config.catalog_csv.as_deref())?;
    let source_totals = load_source_totals(config.source_totals_json.as_deref())?;
    let mut known_stems = config.known_stems.clone();
    known_stems.extend(catalog.keys().cloned());
    let infer_stems_from_summary = known_stems.is_empty();

    let (inputs, summary_counts, input_label) =
        resolve_inputs(config, &mut known_stems, infer_stems_from_summary)?;
    if known_stems.is_empty() {
        return Err(SiteError::new(
            "no known marker stems: provide summary.csv, --known-stems, or --catalog-csv",
        ));
    }

    let mut patterns = build_pattern_map(&known_stems, &catalog, &summary_counts);
    let mut sources = Vec::new();
    for input in &inputs {
        let denominator = denominator_for_source(input, source_totals.as_ref());
        let mut source = SourceAggregate::new(input.to_owned(), denominator);
        println!("Scanning {}", input.path.display());
        scan_pgn(&input.path, &known_stems, &mut source, &mut patterns)?;
        sources.push(source);
    }
    let samples = if config.examples {
        Some(sample_examples(&inputs, &known_stems, config.sample_size)?)
    } else {
        None
    };

    let dashboard = make_dashboard(
        &config.title,
        input_label,
        source_totals.is_some(),
        config.generic_stem.clone().unwrap_or_default(),
        patterns,
        sources,
    );
    fs::create_dir_all(&config.output_dir)?;
    fs::write(
        config.output_dir.join("index.html"),
        include_str!("../static/index.html"),
    )?;
    fs::write(
        config.output_dir.join("cql-site.css"),
        include_str!("../static/cql-site.css"),
    )?;
    fs::write(
        config.output_dir.join("cql-site.js"),
        include_str!("../static/cql-site.js"),
    )?;
    let samples_js = match samples {
        Some(samples) => {
            let json = serde_json::to_string_pretty(&samples)?;
            format!("window.CQL_SAMPLED_EXAMPLES = {json};\n")
        }
        None => "window.CQL_SAMPLED_EXAMPLES = null;\n".to_string(),
    };
    fs::write(config.output_dir.join("cql-samples.js"), samples_js)?;
    let json = serde_json::to_string_pretty(&dashboard)?;
    fs::write(
        config.output_dir.join("cql-data.js"),
        format!("window.CQL_SITE_DATA = {json};\n"),
    )?;
    Ok(())
}

fn resolve_inputs(
    config: &BuildConfig,
    known_stems: &mut BTreeSet<String>,
    infer_stems_from_summary: bool,
) -> Result<(Vec<SourceInput>, BTreeMap<String, u64>, String)> {
    if let Some(run_dir) = &config.annotated_run_dir {
        let summary = config
            .summary_csv
            .clone()
            .unwrap_or_else(|| run_dir.join("summary.csv"));
        let (inputs, counts) =
            parse_summary_csv(&summary, run_dir, known_stems, infer_stems_from_summary)?;
        return Ok((inputs, counts, run_dir.display().to_string()));
    }

    let inputs = config
        .pgn_paths
        .iter()
        .map(|path| {
            let source_pgn = path
                .file_name()
                .map(|value| value.to_string_lossy().into_owned())
                .unwrap_or_else(|| path.display().to_string());
            source_input_from_parts(source_pgn.clone(), source_pgn, path.clone())
        })
        .collect::<Vec<_>>();
    Ok((inputs, BTreeMap::new(), "explicit PGN input".to_string()))
}

fn parse_summary_csv(
    summary: &Path,
    run_dir: &Path,
    known_stems: &mut BTreeSet<String>,
    infer_stems_from_summary: bool,
) -> Result<(Vec<SourceInput>, BTreeMap<String, u64>)> {
    let text = fs::read_to_string(summary)
        .map_err(|err| SiteError::new(format!("failed to read {}: {err}", summary.display())))?;
    let mut lines = text.lines();
    let header = lines
        .next()
        .ok_or_else(|| SiteError::new(format!("empty summary CSV: {}", summary.display())))?;
    let fields = split_csv_line(header);
    let idx = |name: &str| -> Result<usize> {
        fields
            .iter()
            .position(|field| field == name)
            .ok_or_else(|| SiteError::new(format!("summary.csv missing {name:?} column")))
    };
    let pgn_idx = idx("pgn")?;
    let cql_idx = idx("cql")?;
    let output_idx = idx("output_pgn")?;
    let status_idx = idx("status")?;
    let count_idx = idx("match_count")?;

    let mut inputs_by_output = BTreeMap::new();
    let mut stems_by_output: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut summary_counts = BTreeMap::new();
    for (line_number, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row = split_csv_line(line);
        if row.len() <= count_idx {
            return Err(SiteError::new(format!(
                "{} row {} has too few columns",
                summary.display(),
                line_number + 2
            )));
        }
        if row[status_idx] != "ok" {
            continue;
        }
        let stem = file_stem(&row[cql_idx]);
        if infer_stems_from_summary {
            known_stems.insert(stem.clone());
        }
        let stem_known = known_stems.contains(&stem);
        let count = row[count_idx].parse::<u64>().unwrap_or(0);
        if stem_known {
            *summary_counts.entry(stem.clone()).or_insert(0) += count;
        }

        let output_pgn = row[output_idx].clone();
        if stem_known {
            stems_by_output
                .entry(output_pgn.clone())
                .or_default()
                .insert(stem);
        }
        let source_pgn = row[pgn_idx].clone();
        let path = run_dir.join(&output_pgn);
        if !path.is_file() {
            return Err(SiteError::new(format!(
                "summary output PGN does not exist: {}",
                path.display()
            )));
        }
        inputs_by_output
            .entry(output_pgn.clone())
            .or_insert_with(|| source_input_from_parts(source_pgn, output_pgn, path));
    }
    let mut inputs = Vec::new();
    for (output_pgn, mut input) in inputs_by_output {
        if let Some(stems) = stems_by_output.get(&output_pgn) {
            if stems.len() == 1 {
                input.implicit_stems = stems.clone();
            }
        }
        inputs.push(input);
    }
    Ok((inputs, summary_counts))
}

fn source_input_from_parts(source_pgn: String, output_pgn: String, path: PathBuf) -> SourceInput {
    let source_id = source_id_from_pgn(&source_pgn);
    let (group, bucket) = source_group_and_bucket(&source_id);
    SourceInput {
        label: source_label(&source_id),
        source_pgn,
        output_pgn,
        path,
        implicit_stems: BTreeSet::new(),
        source_id,
        group,
        bucket,
    }
}

fn build_pattern_map(
    known_stems: &BTreeSet<String>,
    catalog: &BTreeMap<String, CatalogEntry>,
    summary_counts: &BTreeMap<String, u64>,
) -> BTreeMap<String, PatternAggregate> {
    known_stems
        .iter()
        .map(|stem| {
            let entry = catalog.get(stem).cloned().unwrap_or_default();
            let label = if entry.label.is_empty() {
                fallback_label(stem)
            } else {
                entry.label
            };
            (
                stem.clone(),
                PatternAggregate {
                    stem: stem.clone(),
                    label,
                    group: entry.group,
                    description: entry.description,
                    color: entry.color,
                    summary_count: summary_counts.get(stem).copied().unwrap_or(0),
                    games: 0,
                    instances: 0,
                    exclusive_games: 0,
                    overlap_games: 0,
                },
            )
        })
        .collect()
}

fn load_catalog(path: Option<&Path>) -> Result<BTreeMap<String, CatalogEntry>> {
    let Some(path) = path else {
        return Ok(BTreeMap::new());
    };
    let text = fs::read_to_string(path)
        .map_err(|err| SiteError::new(format!("failed to read {}: {err}", path.display())))?;
    let mut lines = text.lines();
    let header = lines
        .next()
        .ok_or_else(|| SiteError::new(format!("empty catalog CSV: {}", path.display())))?;
    let fields = split_csv_line(header);
    let column = |name: &str| fields.iter().position(|field| field == name);
    let stem_idx =
        column("stem").ok_or_else(|| SiteError::new("catalog CSV must contain a stem column"))?;
    let label_idx = column("label");
    let group_idx = column("group");
    let description_idx = column("description");
    let color_idx = column("color");

    let mut catalog = BTreeMap::new();
    for (line_number, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row = split_csv_line(line);
        let stem = row.get(stem_idx).cloned().unwrap_or_default();
        if stem.trim().is_empty() {
            return Err(SiteError::new(format!(
                "{} row {} has an empty stem",
                path.display(),
                line_number + 2
            )));
        }
        catalog.insert(
            stem,
            CatalogEntry {
                label: get_csv_cell(&row, label_idx),
                group: get_csv_cell(&row, group_idx),
                description: get_csv_cell(&row, description_idx),
                color: get_csv_cell(&row, color_idx),
            },
        );
    }
    Ok(catalog)
}

fn get_csv_cell(row: &[String], index: Option<usize>) -> String {
    index
        .and_then(|idx| row.get(idx))
        .cloned()
        .unwrap_or_default()
}

fn load_source_totals(path: Option<&Path>) -> Result<Option<SourceTotals>> {
    let Some(path) = path else {
        return Ok(None);
    };
    let text = fs::read_to_string(path)
        .map_err(|err| SiteError::new(format!("failed to read {}: {err}", path.display())))?;
    Ok(Some(serde_json::from_str(&text)?))
}

fn denominator_for_source(input: &SourceInput, totals: Option<&SourceTotals>) -> Option<u64> {
    let totals = totals?;
    for candidate in [
        input.source_pgn.as_str(),
        input.output_pgn.as_str(),
        &format!("{}.pgn", input.source_id),
        &format!("{}.merged.pgn", input.source_id),
    ] {
        if let Some(file) = totals
            .files
            .iter()
            .find(|file| file.source_pgn == candidate)
        {
            return Some(file.games);
        }
    }
    None
}

struct CqlExampleVisitor<'a> {
    known_stems: &'a BTreeSet<String>,
    game_index: usize,
    pos: Chess,
    headers: BTreeMap<String, String>,
    outcome: Option<String>,
    ply_index: u32,
    last_move_san: String,
    last_move_uci: String,
    uci_moves: Vec<String>,
    markers: BTreeMap<String, CapturedExampleMarker>,
    parse_error: Option<String>,
}

impl<'a> CqlExampleVisitor<'a> {
    fn new(known_stems: &'a BTreeSet<String>) -> Self {
        Self {
            known_stems,
            game_index: 0,
            pos: Chess::default(),
            headers: BTreeMap::new(),
            outcome: None,
            ply_index: 0,
            last_move_san: String::new(),
            last_move_uci: String::new(),
            uci_moves: Vec::new(),
            markers: BTreeMap::new(),
            parse_error: None,
        }
    }

    fn record_error(&mut self, message: String) {
        if self.parse_error.is_none() {
            self.parse_error = Some(message);
        }
    }

    fn capture_stem(&mut self, stem: &str) {
        if self.markers.contains_key(stem) {
            return;
        }
        let fen = Fen::from_position(&self.pos, EnPassantMode::Legal).to_string();
        self.markers.insert(
            stem.to_string(),
            CapturedExampleMarker {
                stem: stem.to_string(),
                ply_index: self.ply_index,
                fullmove_number: self.pos.fullmoves().get(),
                move_san: self.last_move_san.clone(),
                move_uci: self.last_move_uci.clone(),
                fen,
                side_to_move: color_name(self.pos.turn()),
                piece_count: self.pos.board().occupied().count(),
            },
        );
    }
}

impl Visitor for CqlExampleVisitor<'_> {
    type Result = ExampleGame;

    fn begin_game(&mut self) {
        self.game_index += 1;
        self.pos = Chess::default();
        self.headers.clear();
        self.outcome = None;
        self.ply_index = 0;
        self.last_move_san.clear();
        self.last_move_uci.clear();
        self.uci_moves.clear();
        self.markers.clear();
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
        let Ok(chess_move) = san_plus.san.to_move(&self.pos) else {
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
        let text = String::from_utf8_lossy(comment.as_bytes());
        for stem in comment_stems(&text, self.known_stems) {
            self.capture_stem(&stem);
        }
    }

    fn outcome(&mut self, outcome: Option<Outcome>) {
        self.outcome = outcome.map(|value| value.to_string());
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
        let markers = if parse_error.is_none() {
            std::mem::take(&mut self.markers)
                .into_values()
                .collect::<Vec<_>>()
        } else {
            self.markers.clear();
            Vec::new()
        };

        ExampleGame {
            game_index: self.game_index,
            headers,
            game_key,
            markers,
            parse_error,
        }
    }
}

fn sample_examples(
    inputs: &[SourceInput],
    known_stems: &BTreeSet<String>,
    sample_size: usize,
) -> Result<SampleData> {
    let mut store = SampleStore::new(sample_size);
    let mut parse_errors = 0usize;
    for input in inputs {
        println!("Sampling examples from {}", input.path.display());
        let file = File::open(&input.path)?;
        let mut reader = BufferedReader::new(file);
        let mut visitor = CqlExampleVisitor::new(known_stems);
        loop {
            let game = reader.read_game(&mut visitor).map_err(|err| {
                SiteError::new(format!("failed to parse {}: {err}", input.path.display()))
            })?;
            let Some(game) = game else {
                break;
            };
            if let Some(err) = &game.parse_error {
                parse_errors += 1;
                eprintln!(
                    "sample parse error in {} game {}: {}",
                    input.output_pgn, game.game_index, err
                );
                continue;
            }
            for marker in &game.markers {
                let example = sample_example(input, &game, marker);
                store.consider(example);
            }
        }
    }
    if parse_errors > 0 {
        eprintln!("Skipped {parse_errors} game(s) with SAN/FEN replay errors while sampling.");
    }
    Ok(store.into_data(inputs))
}

impl SampleStore {
    fn new(sample_size: usize) -> Self {
        Self {
            sample_size,
            reservoirs: BTreeMap::new(),
        }
    }

    fn consider(&mut self, example: SampleExample) {
        for view in sample_views_for_source(&example.source_group) {
            let key = SampleKey {
                view,
                source_pgn: example.source_pgn.clone(),
                stem: example.stem.clone(),
            };
            let hash = sample_hash(&example);
            self.reservoirs.entry(key).or_default().consider(
                hash,
                example.clone(),
                self.sample_size,
            );
        }
    }

    fn into_data(self, inputs: &[SourceInput]) -> SampleData {
        let mut views = BTreeSet::from(["all".to_string()]);
        for input in inputs {
            views.insert(input.group.clone());
        }
        let mut output_views = BTreeMap::new();
        for view in views {
            output_views.insert(
                view.clone(),
                SampleView {
                    stems: self.stems_for_view(&view),
                },
            );
        }
        SampleData {
            schema_version: 1,
            kind: "cql-sampled-examples".to_string(),
            sample_size: self.sample_size,
            sampling: "source-stratified deterministic reservoir over first marker per game"
                .to_string(),
            views: output_views,
        }
    }

    fn stems_for_view(&self, view: &str) -> BTreeMap<String, StemSamples> {
        let mut stems = BTreeSet::new();
        for key in self.reservoirs.keys() {
            if key.view == view {
                stems.insert(key.stem.clone());
            }
        }
        stems
            .into_iter()
            .map(|stem| {
                let samples = self.samples_for_view_stem(view, &stem);
                (stem, samples)
            })
            .collect()
    }

    fn samples_for_view_stem(&self, view: &str, stem: &str) -> StemSamples {
        let mut sources = self
            .reservoirs
            .iter()
            .filter(|(key, reservoir)| {
                key.view == view
                    && key.stem == stem
                    && (!reservoir.items.is_empty() || reservoir.seen > 0)
            })
            .collect::<Vec<_>>();
        sources.sort_by(|(a, _), (b, _)| a.source_pgn.cmp(&b.source_pgn));
        let available = sources
            .iter()
            .map(|(_, reservoir)| reservoir.seen)
            .sum::<usize>();
        let source_split = sources
            .iter()
            .map(|(key, reservoir)| SourceSampleSplit {
                source_pgn: key.source_pgn.clone(),
                available: reservoir.seen,
            })
            .collect::<Vec<_>>();

        let mut per_source = sources
            .into_iter()
            .map(|(_, reservoir)| {
                let mut items = reservoir.items.clone();
                items.sort_by_key(|item| item.key);
                items
            })
            .collect::<Vec<_>>();
        let mut selected = Vec::new();
        while selected.len() < self.sample_size {
            let mut made_progress = false;
            for items in &mut per_source {
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
        let examples = selected
            .into_iter()
            .map(|item| item.example)
            .collect::<Vec<_>>();
        StemSamples {
            available,
            sampled: examples.len(),
            source_split,
            examples,
        }
    }
}

impl Reservoir {
    fn consider(&mut self, key: u128, example: SampleExample, sample_size: usize) {
        self.seen += 1;
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

fn sample_views_for_source(source_group: &str) -> Vec<String> {
    let mut views = vec!["all".to_string()];
    if !source_group.is_empty() {
        views.push(source_group.to_string());
    }
    views
}

fn sample_example(
    input: &SourceInput,
    game: &ExampleGame,
    marker: &CapturedExampleMarker,
) -> SampleExample {
    SampleExample {
        source_pgn: input.source_pgn.clone(),
        source_group: input.group.clone(),
        source_bucket: input.bucket.clone(),
        output_pgn: input.output_pgn.clone(),
        game_index: game.game_index,
        game_key: game.game_key.clone(),
        event: header_value(&game.headers, "Event").to_string(),
        site: header_value(&game.headers, "Site").to_string(),
        date: header_value(&game.headers, "Date").to_string(),
        round: header_value(&game.headers, "Round").to_string(),
        white: header_value(&game.headers, "White").to_string(),
        white_elo: header_value(&game.headers, "WhiteElo").to_string(),
        black: header_value(&game.headers, "Black").to_string(),
        black_elo: header_value(&game.headers, "BlackElo").to_string(),
        result: header_value(&game.headers, "Result").to_string(),
        eco_raw: header_value(&game.headers, "ECO").to_string(),
        eco_base: eco_base(game.headers.get("ECO")),
        stem: marker.stem.clone(),
        ply_index: marker.ply_index,
        fullmove_number: marker.fullmove_number,
        move_san: marker.move_san.clone(),
        move_uci: marker.move_uci.clone(),
        fen: marker.fen.clone(),
        side_to_move: marker.side_to_move,
        piece_count: marker.piece_count,
    }
}

fn header_value<'a>(headers: &'a BTreeMap<String, String>, key: &str) -> &'a str {
    headers.get(key).map(String::as_str).unwrap_or("")
}

fn color_name(color: Color) -> &'static str {
    match color {
        Color::White => "white",
        Color::Black => "black",
    }
}

fn game_key(headers: &BTreeMap<String, String>, uci_moves: &[String]) -> String {
    let mut material = String::new();
    for key in ["Event", "Site", "Date", "Round", "White", "Black", "Result"] {
        material.push_str(header_value(headers, key));
        material.push('\x1f');
    }
    for mv in uci_moves {
        material.push_str(mv);
        material.push(' ');
    }
    format!("{:032x}", xxh3_128(material.as_bytes()))
}

fn sample_hash(example: &SampleExample) -> u128 {
    let mut material = String::new();
    material.push_str(&example.source_pgn);
    material.push('\x1f');
    material.push_str(&example.game_key);
    material.push('\x1f');
    material.push_str(&example.stem);
    material.push('\x1f');
    material.push_str(&example.ply_index.to_string());
    material.push('\x1f');
    material.push_str(&example.fen);
    xxh3_128(material.as_bytes())
}

fn scan_pgn(
    path: &Path,
    known_stems: &BTreeSet<String>,
    source: &mut SourceAggregate,
    patterns: &mut BTreeMap<String, PatternAggregate>,
) -> Result<()> {
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mut current: Option<GameState> = None;

    for raw_line in reader.lines() {
        let line = raw_line?;
        if line.starts_with("[Event \"") {
            if let Some(game) = current.take() {
                finalize_game(game, source, patterns);
            }
            current = Some(GameState::default());
        }
        let Some(game) = current.as_mut() else {
            continue;
        };
        if let Some((tag, value)) = parse_header_line(&line) {
            game.headers.insert(tag, value);
        }
        scan_comment_text(&line, known_stems, game);
        scan_comment_text("\n", known_stems, game);
    }
    if let Some(game) = current.take() {
        finalize_game(game, source, patterns);
    }
    Ok(())
}

fn scan_comment_text(text: &str, known_stems: &BTreeSet<String>, game: &mut GameState) {
    for ch in text.chars() {
        if game.in_comment {
            if ch == '}' {
                add_comment_stems(
                    &game.comment,
                    known_stems,
                    &mut game.stems,
                    &mut game.instances,
                );
                game.comment.clear();
                game.in_comment = false;
            } else {
                game.comment.push(ch);
            }
        } else if ch == '{' {
            game.in_comment = true;
            game.comment.clear();
        }
    }
}

fn add_comment_stems(
    comment: &str,
    known_stems: &BTreeSet<String>,
    stems: &mut BTreeSet<String>,
    instances: &mut BTreeMap<String, u64>,
) {
    for stem in comment_stems(comment, known_stems) {
        stems.insert(stem.clone());
        *instances.entry(stem).or_insert(0) += 1;
    }
}

fn comment_stems(comment: &str, known_stems: &BTreeSet<String>) -> Vec<String> {
    let mut stems = Vec::new();
    for token in comment.split_whitespace() {
        let cleaned =
            token.trim_matches(|ch: char| !ch.is_ascii_alphanumeric() && ch != '-' && ch != '_');
        if known_stems.contains(cleaned) {
            stems.push(cleaned.to_string());
        }
    }
    stems
}

fn finalize_game(
    mut game: GameState,
    source: &mut SourceAggregate,
    patterns: &mut BTreeMap<String, PatternAggregate>,
) {
    source.annotated_games += 1;
    *source
        .eco_bases
        .entry(eco_base(game.headers.get("ECO")))
        .or_insert(0) += 1;
    *source
        .rating_bands
        .entry(rating_band(&game.headers))
        .or_insert(0) += 1;
    *source
        .results
        .entry(
            game.headers
                .get("Result")
                .cloned()
                .unwrap_or_else(|| "?".to_string()),
        )
        .or_insert(0) += 1;

    for stem in &source.input.implicit_stems {
        game.stems.insert(stem.clone());
        game.instances.entry(stem.clone()).or_insert(1);
    }

    if game.stems.is_empty() {
        return;
    }
    source.games_with_any_marker += 1;
    source.pattern_game_incidences += game.stems.len() as u64;
    source.pattern_instances += game.instances.values().sum::<u64>();
    source.max_patterns_in_game = source.max_patterns_in_game.max(game.stems.len());
    if game.stems.len() > 1 {
        source.multi_pattern_games += 1;
    }

    for stem in &game.stems {
        let instances = game.instances.get(stem).copied().unwrap_or(1);
        let source_pair = source.patterns.entry(stem.clone()).or_default();
        source_pair.games += 1;
        source_pair.instances += instances;
        if game.stems.len() == 1 {
            source_pair.exclusive_games += 1;
        } else {
            source_pair.overlap_games += 1;
        }

        if let Some(pattern) = patterns.get_mut(stem) {
            pattern.games += 1;
            pattern.instances += instances;
            if game.stems.len() == 1 {
                pattern.exclusive_games += 1;
            } else {
                pattern.overlap_games += 1;
            }
        }
    }

    let stems: Vec<&String> = game.stems.iter().collect();
    for i in 0..stems.len() {
        for j in (i + 1)..stems.len() {
            *source
                .pairs
                .entry((stems[i].clone(), stems[j].clone()))
                .or_insert(0) += 1;
        }
    }
}

fn make_dashboard(
    title: &str,
    input_label: String,
    has_source_totals: bool,
    generic_stem: String,
    patterns: BTreeMap<String, PatternAggregate>,
    sources: Vec<SourceAggregate>,
) -> DashboardData {
    let annotated_games = sources.iter().map(|source| source.annotated_games).sum();
    let denominator_games = sources
        .iter()
        .map(|source| source.denominator_games.unwrap_or(source.annotated_games))
        .sum();
    let games_with_any_marker = sources
        .iter()
        .map(|source| source.games_with_any_marker)
        .sum();
    let pattern_game_incidences = sources
        .iter()
        .map(|source| source.pattern_game_incidences)
        .sum();
    let pattern_instances = sources.iter().map(|source| source.pattern_instances).sum();
    let multi_pattern_games = sources
        .iter()
        .map(|source| source.multi_pattern_games)
        .sum();

    let pattern_outputs = patterns
        .into_values()
        .map(|pattern| PatternOutput {
            stem: pattern.stem,
            label: pattern.label,
            group: pattern.group,
            description: pattern.description,
            color: pattern.color,
            summary_count: pattern.summary_count,
            games: pattern.games,
            instances: pattern.instances,
            exclusive_games: pattern.exclusive_games,
            overlap_games: pattern.overlap_games,
        })
        .collect::<Vec<_>>();

    let source_outputs = sources
        .into_iter()
        .map(|source| SourceOutput {
            id: source.input.source_id,
            label: source.input.label,
            group: source.input.group,
            bucket: source.input.bucket,
            source_pgn: source.input.source_pgn,
            output_pgn: source.input.output_pgn,
            path: source.input.path.display().to_string(),
            denominator_games: source.denominator_games.unwrap_or(source.annotated_games),
            annotated_games: source.annotated_games,
            games_with_any_marker: source.games_with_any_marker,
            pattern_game_incidences: source.pattern_game_incidences,
            pattern_instances: source.pattern_instances,
            multi_pattern_games: source.multi_pattern_games,
            max_patterns_in_game: source.max_patterns_in_game,
            patterns: source.patterns,
            pairs: source
                .pairs
                .into_iter()
                .map(|((a, b), count)| (a, b, count))
                .collect(),
            eco_bases: source.eco_bases,
            rating_bands: source.rating_bands,
            results: source.results,
        })
        .collect::<Vec<_>>();

    DashboardData {
        schema_version: 1,
        title: title.to_string(),
        input_label,
        has_source_totals,
        generic_stem,
        totals: DashboardTotals {
            sources: source_outputs.len(),
            markers: pattern_outputs.len(),
            annotated_games,
            denominator_games,
            games_with_any_marker,
            pattern_game_incidences,
            pattern_instances,
            multi_pattern_games,
        },
        patterns: pattern_outputs,
        sources: source_outputs,
    }
}

fn split_stem_list(text: &str) -> Vec<String> {
    text.split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn split_csv_line(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut field = String::new();
    let mut chars = line.chars().peekable();
    let mut in_quotes = false;
    while let Some(ch) = chars.next() {
        match ch {
            '"' if in_quotes && matches!(chars.peek(), Some('"')) => {
                chars.next();
                field.push('"');
            }
            '"' => in_quotes = !in_quotes,
            ',' if !in_quotes => {
                fields.push(std::mem::take(&mut field));
            }
            _ => field.push(ch),
        }
    }
    fields.push(field);
    fields
}

fn parse_header_line(line: &str) -> Option<(String, String)> {
    if !line.starts_with('[') {
        return None;
    }
    let space = line.find(' ')?;
    let tag = line.get(1..space)?.to_string();
    let first_quote = line[space..].find('"')? + space + 1;
    let last_quote = line.rfind('"')?;
    if last_quote < first_quote {
        return None;
    }
    Some((tag, line[first_quote..last_quote].to_string()))
}

fn file_stem(path: &str) -> String {
    Path::new(path)
        .file_stem()
        .map(|value| value.to_string_lossy().into_owned())
        .unwrap_or_else(|| path.to_string())
}

fn source_id_from_pgn(path: &str) -> String {
    let mut id = file_stem(path);
    if let Some(stripped) = id.strip_suffix(".merged") {
        id = stripped.to_string();
    }
    id
}

fn source_group_and_bucket(id: &str) -> (String, String) {
    if let Some(bucket) = id.strip_prefix("LumbrasGigaBase_OTB_") {
        ("OTB".to_string(), bucket.to_string())
    } else if let Some(bucket) = id.strip_prefix("LumbrasGigaBase_Online_") {
        ("Online".to_string(), bucket.to_string())
    } else if id.to_ascii_lowercase().contains("online") {
        ("Online".to_string(), id.to_string())
    } else if id.to_ascii_lowercase().contains("otb") {
        ("OTB".to_string(), id.to_string())
    } else {
        ("Unknown".to_string(), id.to_string())
    }
}

fn source_label(id: &str) -> String {
    let (group, bucket) = source_group_and_bucket(id);
    if group == "Unknown" {
        id.replace('_', " ")
    } else {
        format!("{group} {}", bucket.replace('_', " "))
    }
}

fn fallback_label(stem: &str) -> String {
    match stem {
        "ismate" => "Any mate".to_string(),
        "BN" => "Bishop and knight".to_string(),
        "KBB" => "Two bishops".to_string(),
        "KNN" => "Two knights".to_string(),
        _ => {
            let mut out = String::new();
            for (i, ch) in stem.chars().enumerate() {
                if i == 0 {
                    out.push(ch.to_ascii_uppercase());
                } else if ch.is_ascii_uppercase() {
                    out.push(' ');
                    out.push(ch);
                } else if ch == '_' || ch == '-' {
                    out.push(' ');
                } else {
                    out.push(ch);
                }
            }
            out
        }
    }
}

fn eco_base(value: Option<&String>) -> String {
    let Some(value) = value else {
        return "Unknown".to_string();
    };
    let trimmed = value.trim();
    if trimmed.len() >= 3 {
        trimmed[..3].to_string()
    } else if trimmed.is_empty() || trimmed == "?" {
        "Unknown".to_string()
    } else {
        trimmed.to_string()
    }
}

fn rating_band(headers: &BTreeMap<String, String>) -> String {
    let ratings = ["WhiteElo", "BlackElo"]
        .into_iter()
        .filter_map(|tag| headers.get(tag))
        .filter_map(|value| value.parse::<u32>().ok())
        .filter(|value| *value > 0)
        .collect::<Vec<_>>();
    if ratings.is_empty() {
        return "Unknown".to_string();
    }
    let average = ratings.iter().sum::<u32>() / ratings.len() as u32;
    match average {
        0..=1599 => "<1600".to_string(),
        1600..=1799 => "1600-1799".to_string(),
        1800..=1999 => "1800-1999".to_string(),
        2000..=2199 => "2000-2199".to_string(),
        2200..=2399 => "2200-2399".to_string(),
        2400..=2599 => "2400-2599".to_string(),
        _ => "2600+".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn extracts_known_stems_from_comments() {
        let known = BTreeSet::from([
            "anderssen".to_string(),
            "mayet".to_string(),
            "opera".to_string(),
        ]);
        let mut stems = BTreeSet::new();
        let mut instances = BTreeMap::new();
        add_comment_stems("anderssen mayet opera", &known, &mut stems, &mut instances);
        assert_eq!(stems.len(), 3);
        assert_eq!(instances["anderssen"], 1);
    }

    #[test]
    fn ignores_non_marker_comments() {
        let known = BTreeSet::from(["ismate".to_string()]);
        let mut stems = BTreeSet::new();
        let mut instances = BTreeMap::new();
        add_comment_stems("Game number 12", &known, &mut stems, &mut instances);
        add_comment_stems("ismate", &known, &mut stems, &mut instances);
        assert_eq!(stems, BTreeSet::from(["ismate".to_string()]));
    }

    #[test]
    fn derives_lumbras_source_metadata() {
        assert_eq!(
            source_id_from_pgn("LumbrasGigaBase_Online_2024.merged.pgn"),
            "LumbrasGigaBase_Online_2024"
        );
        assert_eq!(
            source_group_and_bucket("LumbrasGigaBase_OTB_2010-2014"),
            ("OTB".to_string(), "2010-2014".to_string())
        );
    }

    #[test]
    fn parses_csv_quotes() {
        assert_eq!(
            split_csv_line("stem,label\n\"a,b\",Label").get(0),
            Some(&"stem".to_string())
        );
        assert_eq!(split_csv_line("\"a,b\",Label")[0], "a,b");
    }

    #[test]
    fn parses_example_options() {
        let config = parse_args([
            OsString::from("build"),
            OsString::from("--pgn"),
            OsString::from("annotated.pgn"),
            OsString::from("--known-stems"),
            OsString::from("ismate,greco"),
            OsString::from("--examples"),
            OsString::from("--sample-size"),
            OsString::from("8"),
        ])
        .unwrap();
        assert!(config.examples);
        assert_eq!(config.sample_size, 8);
        assert_eq!(config.known_stems.len(), 2);
    }

    #[test]
    fn summary_counts_catalog_stems_without_inference() {
        let run_dir = temp_test_dir("catalog-summary");
        fs::create_dir_all(&run_dir).unwrap();
        fs::write(run_dir.join("known.pgn"), "").unwrap();
        fs::write(
            run_dir.join("summary.csv"),
            "pgn,cql,output_pgn,status,match_count\nsource.pgn,cql/known.cql,known.pgn,ok,7\n",
        )
        .unwrap();

        let mut known_stems = BTreeSet::from(["known".to_string()]);
        let (inputs, counts) = parse_summary_csv(
            &run_dir.join("summary.csv"),
            &run_dir,
            &mut known_stems,
            false,
        )
        .unwrap();

        assert_eq!(counts["known"], 7);
        assert_eq!(inputs.len(), 1);
        assert_eq!(
            inputs[0].implicit_stems,
            BTreeSet::from(["known".to_string()])
        );

        let _ = fs::remove_dir_all(run_dir);
    }

    #[test]
    fn summary_does_not_make_unknown_script_stems_implicit() {
        let run_dir = temp_test_dir("combined-summary");
        fs::create_dir_all(&run_dir).unwrap();
        fs::write(run_dir.join("combined.pgn"), "").unwrap();
        fs::write(
            run_dir.join("summary.csv"),
            "pgn,cql,output_pgn,status,match_count\nsource.pgn,cql/fce-table-markers.cql,combined.pgn,ok,99\n",
        )
        .unwrap();

        let mut known_stems = BTreeSet::from(["internal_marker".to_string()]);
        let (inputs, counts) = parse_summary_csv(
            &run_dir.join("summary.csv"),
            &run_dir,
            &mut known_stems,
            false,
        )
        .unwrap();

        assert!(counts.is_empty());
        assert_eq!(inputs.len(), 1);
        assert!(inputs[0].implicit_stems.is_empty());

        let _ = fs::remove_dir_all(run_dir);
    }

    fn temp_test_dir(name: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("cql-site-{name}-{}-{nanos}", std::process::id()))
    }
}
