use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::ffi::OsString;
use std::fmt::Write as _;
use std::fs::{self, File};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

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

#[derive(Debug, Clone)]
struct BuildConfig {
    run_dir: PathBuf,
    output_dir: PathBuf,
    title: String,
}

#[derive(Debug, Clone)]
struct PatternStats {
    stem: String,
    label: String,
    summary_count: u64,
    scanned_count: u64,
    exclusive_games: u64,
    overlap_games: u64,
}

#[derive(Debug, Clone)]
struct SourceStats {
    id: String,
    label: String,
    group: String,
    bucket: String,
    pgn: String,
    output_pgn: String,
    games: u64,
    incidences: u64,
    multi_pattern_games: u64,
    max_patterns_in_game: usize,
    patterns: BTreeMap<String, u64>,
    pairs: BTreeMap<(String, String), u64>,
}

#[derive(Debug)]
struct DashboardData {
    title: String,
    run_dir: String,
    patterns: BTreeMap<String, PatternStats>,
    sources: BTreeMap<String, SourceStats>,
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
    println!("Wrote mate-pattern site: {}", config.output_dir.display());
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

    let mut run_dir = None;
    let mut output_dir = None;
    let mut title = "Checkmate patterns in Lumbra's Gigabase".to_string();
    let mut i = 0usize;
    while i < raw.len() {
        let arg = raw[i].to_string_lossy();
        match arg.as_ref() {
            "--run-dir" => run_dir = Some(next_path(&raw, &mut i, "--run-dir")?),
            "--output-dir" => output_dir = Some(next_path(&raw, &mut i, "--output-dir")?),
            "--title" => title = next_string(&raw, &mut i, "--title")?,
            _ => {
                return Err(SiteError::new(format!(
                    "unknown build option {arg:?}\n{}",
                    usage()
                )));
            }
        }
    }

    Ok(BuildConfig {
        run_dir: required(run_dir, "--run-dir")?,
        output_dir: output_dir.unwrap_or_else(|| PathBuf::from("out/mates-site")),
        title,
    })
}

fn usage() -> String {
    "usage: mates-site build --run-dir RUN_DIR [--output-dir OUT_DIR] [--title TITLE]".to_string()
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

fn required<T>(value: Option<T>, flag: &str) -> Result<T> {
    value.ok_or_else(|| SiteError::new(format!("missing required option {flag}")))
}

fn build_site(config: &BuildConfig) -> Result<()> {
    let summary_path = config.run_dir.join("summary.csv");
    let mut data = parse_summary(&summary_path, &config.title, &config.run_dir)?;
    let known_stems: BTreeSet<String> = data.patterns.keys().cloned().collect();
    let source_ids: Vec<String> = data.sources.keys().cloned().collect();

    for source_id in source_ids {
        let source = data
            .sources
            .get_mut(&source_id)
            .ok_or_else(|| SiteError::new(format!("missing source state: {source_id}")))?;
        let pgn_path = config.run_dir.join(&source.output_pgn);
        println!("Scanning {}", pgn_path.display());
        scan_annotated_pgn(&pgn_path, source, &known_stems, &mut data.patterns)?;
    }

    fs::create_dir_all(&config.output_dir)?;
    fs::write(
        config.output_dir.join("index.html"),
        include_str!("../static/index.html"),
    )?;
    fs::write(
        config.output_dir.join("mates.css"),
        include_str!("../static/mates.css"),
    )?;
    fs::write(
        config.output_dir.join("mates-app.js"),
        include_str!("../static/mates-app.js"),
    )?;
    let mut data_js = String::from("window.MATE_PATTERN_DATA = ");
    write_dashboard_json(&mut data_js, &data)?;
    data_js.push_str(";\n");
    fs::write(config.output_dir.join("mates-data.js"), data_js)?;
    Ok(())
}

fn parse_summary(path: &Path, title: &str, run_dir: &Path) -> Result<DashboardData> {
    let content = fs::read_to_string(path)?;
    let mut lines = content.lines();
    let header_line = lines
        .next()
        .ok_or_else(|| SiteError::new(format!("empty summary: {}", path.display())))?;
    let header = split_csv_line(header_line);
    let index = |name: &str| -> Result<usize> {
        header
            .iter()
            .position(|field| field == name)
            .ok_or_else(|| SiteError::new(format!("summary missing column {name:?}")))
    };
    let pgn_idx = index("pgn")?;
    let cql_idx = index("cql")?;
    let output_idx = index("output_pgn")?;
    let status_idx = index("status")?;
    let count_idx = index("match_count")?;

    let mut data = DashboardData {
        title: title.to_string(),
        run_dir: run_dir.display().to_string(),
        patterns: BTreeMap::new(),
        sources: BTreeMap::new(),
    };

    for (line_number, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row = split_csv_line(line);
        if row.len() <= count_idx {
            return Err(SiteError::new(format!(
                "{} row {} has too few columns",
                path.display(),
                line_number + 2
            )));
        }
        if row[status_idx] != "ok" {
            continue;
        }
        let stem = file_stem(&row[cql_idx]);
        let count = row[count_idx].parse::<u64>().unwrap_or(0);
        data.patterns
            .entry(stem.clone())
            .or_insert_with(|| PatternStats {
                label: pattern_label(&stem),
                stem: stem.clone(),
                summary_count: 0,
                scanned_count: 0,
                exclusive_games: 0,
                overlap_games: 0,
            })
            .summary_count += count;

        let source_id = source_id_from_pgn(&row[pgn_idx]);
        let source = data.sources.entry(source_id.clone()).or_insert_with(|| {
            let (group, bucket) = source_group_and_bucket(&source_id);
            SourceStats {
                label: source_label(&source_id),
                id: source_id,
                group,
                bucket,
                pgn: row[pgn_idx].clone(),
                output_pgn: row[output_idx].clone(),
                games: 0,
                incidences: 0,
                multi_pattern_games: 0,
                max_patterns_in_game: 0,
                patterns: BTreeMap::new(),
                pairs: BTreeMap::new(),
            }
        });
        if source.output_pgn != row[output_idx] {
            return Err(SiteError::new(format!(
                "source {} maps to multiple retained PGNs: {} and {}",
                source.id, source.output_pgn, row[output_idx]
            )));
        }
    }

    if data.patterns.is_empty() {
        return Err(SiteError::new(format!(
            "summary contains no successful pattern rows: {}",
            path.display()
        )));
    }
    Ok(data)
}

fn scan_annotated_pgn(
    path: &Path,
    source: &mut SourceStats,
    known_stems: &BTreeSet<String>,
    patterns: &mut BTreeMap<String, PatternStats>,
) -> Result<()> {
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mut seen_game = false;
    let mut current_stems: BTreeSet<String> = BTreeSet::new();
    let mut in_comment = false;
    let mut comment = String::new();

    for line in reader.lines() {
        let line = line?;
        if line.starts_with("[Event \"") {
            if seen_game {
                finalize_game(source, patterns, &current_stems);
                current_stems.clear();
            }
            seen_game = true;
            in_comment = false;
            comment.clear();
        }
        if seen_game {
            scan_line_for_comments(
                &line,
                known_stems,
                &mut current_stems,
                &mut in_comment,
                &mut comment,
            );
            scan_line_for_comments(
                "\n",
                known_stems,
                &mut current_stems,
                &mut in_comment,
                &mut comment,
            );
        }
    }
    if seen_game {
        finalize_game(source, patterns, &current_stems);
    }
    Ok(())
}

fn scan_line_for_comments(
    text: &str,
    known_stems: &BTreeSet<String>,
    current_stems: &mut BTreeSet<String>,
    in_comment: &mut bool,
    comment: &mut String,
) {
    for ch in text.chars() {
        if *in_comment {
            if ch == '}' {
                add_comment_stems(comment, known_stems, current_stems);
                comment.clear();
                *in_comment = false;
            } else {
                comment.push(ch);
            }
        } else if ch == '{' {
            *in_comment = true;
            comment.clear();
        }
    }
}

fn add_comment_stems(
    comment: &str,
    known_stems: &BTreeSet<String>,
    current_stems: &mut BTreeSet<String>,
) {
    for token in comment.split_whitespace() {
        let cleaned = token.trim_matches(|ch: char| !ch.is_ascii_alphanumeric());
        if known_stems.contains(cleaned) {
            current_stems.insert(cleaned.to_string());
        }
    }
}

fn finalize_game(
    source: &mut SourceStats,
    patterns: &mut BTreeMap<String, PatternStats>,
    stems: &BTreeSet<String>,
) {
    if stems.is_empty() {
        return;
    }
    source.games += 1;
    source.incidences += stems.len() as u64;
    source.max_patterns_in_game = source.max_patterns_in_game.max(stems.len());
    if stems.len() > 1 {
        source.multi_pattern_games += 1;
    }
    for stem in stems {
        *source.patterns.entry(stem.clone()).or_insert(0) += 1;
        if let Some(pattern) = patterns.get_mut(stem) {
            pattern.scanned_count += 1;
            if stems.len() == 1 {
                pattern.exclusive_games += 1;
            } else {
                pattern.overlap_games += 1;
            }
        }
    }
    let stem_vec: Vec<&String> = stems.iter().collect();
    for i in 0..stem_vec.len() {
        for j in (i + 1)..stem_vec.len() {
            let key = (stem_vec[i].clone(), stem_vec[j].clone());
            *source.pairs.entry(key).or_insert(0) += 1;
        }
    }
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

fn pattern_label(stem: &str) -> String {
    match stem {
        "BN" => "Bishop and knight".to_string(),
        "KBB" => "Two bishops".to_string(),
        "KNN" => "Two knights".to_string(),
        "anastasiamate" => "Anastasia mate".to_string(),
        "anderssen" => "Anderssen mate".to_string(),
        "arabianmate" => "Arabian mate".to_string(),
        "backrankmate" => "Back rank mate".to_string(),
        "balestramate" => "Balestra mate".to_string(),
        "blackburnemate" => "Blackburne mate".to_string(),
        "blindswinemate" => "Blind swine mate".to_string(),
        "bodenmate" => "Boden mate".to_string(),
        "castlingmate" => "Castling mate".to_string(),
        "corner" => "Corner mate".to_string(),
        "damiano" => "Damiano mate".to_string(),
        "damianobishopmate" => "Damiano bishop mate".to_string(),
        "davidandgoliath" => "David and Goliath mate".to_string(),
        "doubleknight" => "Double knight mate".to_string(),
        "dovetailmate" => "Dovetail mate".to_string(),
        "epaulettemate" => "Epaulette mate".to_string(),
        "greco" => "Greco mate".to_string(),
        "hookmate" => "Hook mate".to_string(),
        "ismate" => "Any mate".to_string(),
        "killbox" => "Kill box mate".to_string(),
        "laddermate" => "Ladder mate".to_string(),
        "legalmate" => "Legal mate".to_string(),
        "lolli" => "Lolli mate".to_string(),
        "maxlangemate" => "Max Lange mate".to_string(),
        "mayet" => "Mayet mate".to_string(),
        "morphymate" => "Morphy mate".to_string(),
        "opera" => "Opera mate".to_string(),
        "pillsbury" => "Pillsbury mate".to_string(),
        "queen" => "Queen mate".to_string(),
        "retimate" => "Reti mate".to_string(),
        "rookmate" => "Rook mate".to_string(),
        "smotheredmate" => "Smothered mate".to_string(),
        "suffocationmate" => "Suffocation mate".to_string(),
        "swallowtail" => "Swallowtail mate".to_string(),
        "trianglemate" => "Triangle mate".to_string(),
        "twobishopmate" => "Two-bishop mate".to_string(),
        "twoknightmate" => "Two-knight mate".to_string(),
        "vukovicmate" => "Vukovic mate".to_string(),
        _ => fallback_pattern_label(stem),
    }
}

fn fallback_pattern_label(stem: &str) -> String {
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

fn write_dashboard_json(out: &mut String, data: &DashboardData) -> Result<()> {
    let total_games: u64 = data.sources.values().map(|source| source.games).sum();
    let total_incidences: u64 = data.sources.values().map(|source| source.incidences).sum();
    let total_multi: u64 = data
        .sources
        .values()
        .map(|source| source.multi_pattern_games)
        .sum();

    out.push_str("{\n");
    json_field(out, "title", &data.title, 1, true);
    json_field(out, "runDir", &data.run_dir, 1, true);
    indent(out, 1);
    out.push_str("\"totals\": {");
    push_json_pair_number(out, "games", total_games, true);
    push_json_pair_number(out, "incidences", total_incidences, true);
    push_json_pair_number(out, "multiPatternGames", total_multi, true);
    push_json_pair_number(out, "sourceCount", data.sources.len() as u64, true);
    push_json_pair_number(out, "patternCount", data.patterns.len() as u64, false);
    out.push_str("},\n");

    indent(out, 1);
    out.push_str("\"patterns\": [\n");
    let mut patterns: Vec<&PatternStats> = data.patterns.values().collect();
    patterns.sort_by(|a, b| {
        b.scanned_count
            .cmp(&a.scanned_count)
            .then_with(|| a.stem.cmp(&b.stem))
    });
    for (idx, pattern) in patterns.iter().enumerate() {
        indent(out, 2);
        out.push('{');
        push_json_pair_str(out, "stem", &pattern.stem, true);
        push_json_pair_str(out, "label", &pattern.label, true);
        push_json_pair_number(out, "summaryCount", pattern.summary_count, true);
        push_json_pair_number(out, "scannedCount", pattern.scanned_count, true);
        push_json_pair_number(out, "exclusiveGames", pattern.exclusive_games, true);
        push_json_pair_number(out, "overlapGames", pattern.overlap_games, false);
        out.push('}');
        if idx + 1 != patterns.len() {
            out.push(',');
        }
        out.push('\n');
    }
    indent(out, 1);
    out.push_str("],\n");

    indent(out, 1);
    out.push_str("\"sources\": [\n");
    let mut sources: Vec<&SourceStats> = data.sources.values().collect();
    sources.sort_by(|a, b| a.group.cmp(&b.group).then_with(|| a.bucket.cmp(&b.bucket)));
    for (idx, source) in sources.iter().enumerate() {
        write_source_json(out, source, idx + 1 != sources.len())?;
    }
    indent(out, 1);
    out.push_str("]\n");
    out.push_str("}");
    Ok(())
}

fn write_source_json(out: &mut String, source: &SourceStats, trailing_comma: bool) -> Result<()> {
    indent(out, 2);
    out.push_str("{\n");
    json_field(out, "id", &source.id, 3, true);
    json_field(out, "label", &source.label, 3, true);
    json_field(out, "group", &source.group, 3, true);
    json_field(out, "bucket", &source.bucket, 3, true);
    json_field(out, "pgn", &source.pgn, 3, true);
    json_field(out, "outputPgn", &source.output_pgn, 3, true);
    json_number_field(out, "games", source.games, 3, true);
    json_number_field(out, "incidences", source.incidences, 3, true);
    json_number_field(
        out,
        "multiPatternGames",
        source.multi_pattern_games,
        3,
        true,
    );
    json_number_field(
        out,
        "maxPatternsInGame",
        source.max_patterns_in_game as u64,
        3,
        true,
    );

    indent(out, 3);
    out.push_str("\"patterns\": {");
    for (idx, (stem, count)) in source.patterns.iter().enumerate() {
        if idx > 0 {
            out.push_str(", ");
        }
        push_json_string(out, stem);
        out.push_str(": ");
        out.push_str(&count.to_string());
    }
    out.push_str("},\n");

    indent(out, 3);
    out.push_str("\"pairs\": [");
    for (idx, ((a, b), count)) in source.pairs.iter().enumerate() {
        if idx > 0 {
            out.push_str(", ");
        }
        out.push('[');
        push_json_string(out, a);
        out.push_str(", ");
        push_json_string(out, b);
        out.push_str(", ");
        out.push_str(&count.to_string());
        out.push(']');
    }
    out.push_str("]\n");
    indent(out, 2);
    out.push('}');
    if trailing_comma {
        out.push(',');
    }
    out.push('\n');
    Ok(())
}

fn json_field(out: &mut String, key: &str, value: &str, level: usize, comma: bool) {
    indent(out, level);
    push_json_string(out, key);
    out.push_str(": ");
    push_json_string(out, value);
    if comma {
        out.push(',');
    }
    out.push('\n');
}

fn json_number_field(out: &mut String, key: &str, value: u64, level: usize, comma: bool) {
    indent(out, level);
    push_json_string(out, key);
    out.push_str(": ");
    out.push_str(&value.to_string());
    if comma {
        out.push(',');
    }
    out.push('\n');
}

fn push_json_pair_str(out: &mut String, key: &str, value: &str, comma: bool) {
    push_json_string(out, key);
    out.push_str(": ");
    push_json_string(out, value);
    if comma {
        out.push_str(", ");
    }
}

fn push_json_pair_number(out: &mut String, key: &str, value: u64, comma: bool) {
    push_json_string(out, key);
    out.push_str(": ");
    out.push_str(&value.to_string());
    if comma {
        out.push_str(", ");
    }
}

fn push_json_string(out: &mut String, value: &str) {
    out.push('"');
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            ch if ch < ' ' => {
                write!(out, "\\u{:04x}", ch as u32).expect("write to string");
            }
            _ => out.push(ch),
        }
    }
    out.push('"');
}

fn indent(out: &mut String, level: usize) {
    for _ in 0..level {
        out.push_str("  ");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_known_stems_from_coalesced_comment() {
        let known = BTreeSet::from([
            "anderssen".to_string(),
            "mayet".to_string(),
            "opera".to_string(),
        ]);
        let mut stems = BTreeSet::new();
        add_comment_stems("anderssen mayet opera", &known, &mut stems);
        assert!(stems.contains("anderssen"));
        assert!(stems.contains("mayet"));
        assert!(stems.contains("opera"));
    }

    #[test]
    fn ignores_non_pattern_game_number_comments() {
        let known = BTreeSet::from(["ismate".to_string()]);
        let mut stems = BTreeSet::new();
        add_comment_stems("Game number 12", &known, &mut stems);
        add_comment_stems("ismate", &known, &mut stems);
        assert_eq!(stems, BTreeSet::from(["ismate".to_string()]));
    }

    #[test]
    fn derives_source_metadata() {
        assert_eq!(
            source_id_from_pgn("LumbrasGigaBase_Online_2024.merged.pgn"),
            "LumbrasGigaBase_Online_2024"
        );
        assert_eq!(
            source_group_and_bucket("LumbrasGigaBase_OTB_2010-2014"),
            ("OTB".to_string(), "2010-2014".to_string())
        );
    }
}
