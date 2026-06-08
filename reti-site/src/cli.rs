use std::ffi::OsString;
use std::path::PathBuf;

use crate::{SiteError, SiteResult};

#[derive(Debug, Clone)]
pub enum Command {
    BuildFceTablebase(BuildConfig),
    RenderSnapshot(RenderConfig),
    SamplesJs(SamplesJsConfig),
    SankeyJs(SankeyJsConfig),
    OpeningsJs(OpeningsJsConfig),
}

#[derive(Debug, Clone)]
pub struct BuildConfig {
    pub annotated_run_dir: PathBuf,
    pub source_totals_json: PathBuf,
    pub syzygy_dirs: Vec<PathBuf>,
    pub work_dir: Option<PathBuf>,
    pub output_dir: PathBuf,
    pub title: String,
    pub pgn_utils_bin: PathBuf,
    pub opening_catalog_csv: Option<PathBuf>,
    pub thresholds: Vec<u32>,
    pub sample_size: usize,
    pub workers: usize,
    pub tablebase_threshold: u32,
    pub force: bool,
    pub no_progress: bool,
}

#[derive(Debug, Clone)]
pub struct RenderConfig {
    pub snapshot_json: PathBuf,
    pub output_html: PathBuf,
}

#[derive(Debug, Clone)]
pub struct SamplesJsConfig {
    pub samples_json: PathBuf,
    pub output_js: PathBuf,
}

#[derive(Debug, Clone)]
pub struct SankeyJsConfig {
    pub sqlite_db: PathBuf,
    pub output_js: PathBuf,
    pub thresholds: Vec<u32>,
}

#[derive(Debug, Clone)]
pub struct OpeningsJsConfig {
    pub opening_counts_json: PathBuf,
    pub source_totals_json: PathBuf,
    pub opening_catalog_csv: Option<PathBuf>,
    pub output_js: PathBuf,
}

#[derive(Debug, Clone)]
pub struct Args {
    pub command: Command,
}

impl Args {
    pub fn parse<I>(args: I) -> SiteResult<Self>
    where
        I: IntoIterator<Item = OsString>,
    {
        let mut raw: Vec<OsString> = args.into_iter().collect();
        if raw.is_empty() || matches!(raw[0].to_string_lossy().as_ref(), "--help" | "-h" | "help") {
            return Err(SiteError::new(usage()));
        }
        let command = raw.remove(0).to_string_lossy().into_owned();
        match command.as_str() {
            "build-fce-tablebase" => Ok(Self {
                command: Command::BuildFceTablebase(parse_build(raw)?),
            }),
            "render-snapshot" => Ok(Self {
                command: Command::RenderSnapshot(parse_render(raw)?),
            }),
            "samples-js" => Ok(Self {
                command: Command::SamplesJs(parse_samples_js(raw)?),
            }),
            "sankey-js" => Ok(Self {
                command: Command::SankeyJs(parse_sankey_js(raw)?),
            }),
            "openings-js" => Ok(Self {
                command: Command::OpeningsJs(parse_openings_js(raw)?),
            }),
            _ => Err(SiteError::new(format!(
                "unknown command {command:?}\n{}",
                usage()
            ))),
        }
    }
}

fn parse_openings_js(args: Vec<OsString>) -> SiteResult<OpeningsJsConfig> {
    let mut opening_counts_json = None;
    let mut source_totals_json = None;
    let mut opening_catalog_csv = Some(PathBuf::from("data/openings/lumbras_eco_codes.csv"));
    let mut output_js = None;
    let mut i = 0usize;
    while i < args.len() {
        let arg = args[i].to_string_lossy();
        match arg.as_ref() {
            "--opening-counts-json" => {
                opening_counts_json = Some(next_path(&args, &mut i, "--opening-counts-json")?);
            }
            "--source-totals-json" => {
                source_totals_json = Some(next_path(&args, &mut i, "--source-totals-json")?);
            }
            "--opening-catalog-csv" => {
                opening_catalog_csv = Some(next_path(&args, &mut i, "--opening-catalog-csv")?);
            }
            "--no-opening-catalog" => {
                opening_catalog_csv = None;
                i += 1;
            }
            "--output-js" => {
                output_js = Some(next_path(&args, &mut i, "--output-js")?);
            }
            _ => {
                return Err(SiteError::new(format!(
                    "unknown openings-js option {arg:?}\n{}",
                    openings_js_usage()
                )));
            }
        }
    }
    Ok(OpeningsJsConfig {
        opening_counts_json: required(opening_counts_json, "--opening-counts-json")?,
        source_totals_json: required(source_totals_json, "--source-totals-json")?,
        opening_catalog_csv,
        output_js: required(output_js, "--output-js")?,
    })
}

fn parse_sankey_js(args: Vec<OsString>) -> SiteResult<SankeyJsConfig> {
    let mut sqlite_db = None;
    let mut output_js = None;
    let mut thresholds = vec![1, 2, 5, 10, 20];
    let mut i = 0usize;
    while i < args.len() {
        let arg = args[i].to_string_lossy();
        match arg.as_ref() {
            "--sqlite-db" => {
                sqlite_db = Some(next_path(&args, &mut i, "--sqlite-db")?);
            }
            "--output-js" => {
                output_js = Some(next_path(&args, &mut i, "--output-js")?);
            }
            "--thresholds" => {
                thresholds = parse_thresholds(&next_string(&args, &mut i, "--thresholds")?)?;
            }
            _ => {
                return Err(SiteError::new(format!(
                    "unknown sankey-js option {arg:?}\n{}",
                    sankey_js_usage()
                )));
            }
        }
    }
    Ok(SankeyJsConfig {
        sqlite_db: required(sqlite_db, "--sqlite-db")?,
        output_js: required(output_js, "--output-js")?,
        thresholds,
    })
}

fn parse_samples_js(args: Vec<OsString>) -> SiteResult<SamplesJsConfig> {
    let mut samples_json = None;
    let mut output_js = None;
    let mut i = 0usize;
    while i < args.len() {
        let arg = args[i].to_string_lossy();
        match arg.as_ref() {
            "--samples-json" => {
                samples_json = Some(next_path(&args, &mut i, "--samples-json")?);
            }
            "--output-js" => {
                output_js = Some(next_path(&args, &mut i, "--output-js")?);
            }
            _ => {
                return Err(SiteError::new(format!(
                    "unknown samples-js option {arg:?}\n{}",
                    samples_js_usage()
                )));
            }
        }
    }
    Ok(SamplesJsConfig {
        samples_json: required(samples_json, "--samples-json")?,
        output_js: required(output_js, "--output-js")?,
    })
}

fn parse_build(args: Vec<OsString>) -> SiteResult<BuildConfig> {
    let mut annotated_run_dir = None;
    let mut source_totals_json = None;
    let mut syzygy_dirs = Vec::new();
    let mut work_dir = None;
    let mut output_dir = None;
    let mut title = None;
    let mut pgn_utils_bin = PathBuf::from("native/pgn-utils/target/release/pgn-utils");
    let mut opening_catalog_csv = Some(PathBuf::from("data/openings/lumbras_eco_codes.csv"));
    let mut thresholds = vec![1, 2, 5, 10, 20];
    let mut sample_size = 32usize;
    let mut workers = 1usize;
    let mut tablebase_threshold = 5u32;
    let mut force = false;
    let mut no_progress = false;

    let mut i = 0usize;
    while i < args.len() {
        let arg = args[i].to_string_lossy();
        match arg.as_ref() {
            "--annotated-run-dir" => {
                annotated_run_dir = Some(next_path(&args, &mut i, "--annotated-run-dir")?);
            }
            "--source-totals-json" => {
                source_totals_json = Some(next_path(&args, &mut i, "--source-totals-json")?);
            }
            "--syzygy-dir" => {
                syzygy_dirs.push(next_path(&args, &mut i, "--syzygy-dir")?);
            }
            "--work-dir" => {
                work_dir = Some(next_path(&args, &mut i, "--work-dir")?);
            }
            "--output-dir" => {
                output_dir = Some(next_path(&args, &mut i, "--output-dir")?);
            }
            "--title" => {
                title = Some(next_string(&args, &mut i, "--title")?);
            }
            "--pgn-utils-bin" => {
                pgn_utils_bin = next_path(&args, &mut i, "--pgn-utils-bin")?;
            }
            "--opening-catalog-csv" => {
                opening_catalog_csv = Some(next_path(&args, &mut i, "--opening-catalog-csv")?);
            }
            "--no-opening-catalog" => {
                opening_catalog_csv = None;
                i += 1;
            }
            "--thresholds" => {
                thresholds = parse_thresholds(&next_string(&args, &mut i, "--thresholds")?)?;
            }
            "--sample-size" => {
                sample_size = parse_positive_usize(
                    &next_string(&args, &mut i, "--sample-size")?,
                    "--sample-size",
                )?;
            }
            "--workers" => {
                workers =
                    parse_positive_usize(&next_string(&args, &mut i, "--workers")?, "--workers")?;
            }
            "--tablebase-threshold" => {
                tablebase_threshold = parse_positive_u32(
                    &next_string(&args, &mut i, "--tablebase-threshold")?,
                    "--tablebase-threshold",
                )?;
            }
            "--force" => {
                force = true;
                i += 1;
            }
            "--no-progress" => {
                no_progress = true;
                i += 1;
            }
            _ => {
                return Err(SiteError::new(format!(
                    "unknown build-fce-tablebase option {arg:?}\n{}",
                    build_usage()
                )));
            }
        }
    }

    if syzygy_dirs.is_empty() {
        return Err(SiteError::new("--syzygy-dir is required"));
    }
    if !thresholds.contains(&1) {
        return Err(SiteError::new("--thresholds must include 1"));
    }
    thresholds.sort_unstable();
    thresholds.dedup();

    Ok(BuildConfig {
        annotated_run_dir: required(annotated_run_dir, "--annotated-run-dir")?,
        source_totals_json: required(source_totals_json, "--source-totals-json")?,
        syzygy_dirs,
        work_dir,
        output_dir: required(output_dir, "--output-dir")?,
        title: required(title, "--title")?,
        pgn_utils_bin,
        opening_catalog_csv,
        thresholds,
        sample_size,
        workers,
        tablebase_threshold,
        force,
        no_progress,
    })
}

fn parse_render(args: Vec<OsString>) -> SiteResult<RenderConfig> {
    let mut snapshot_json = None;
    let mut output_html = None;
    let mut i = 0usize;
    while i < args.len() {
        let arg = args[i].to_string_lossy();
        match arg.as_ref() {
            "--snapshot-json" => {
                snapshot_json = Some(next_path(&args, &mut i, "--snapshot-json")?);
            }
            "--output-html" => {
                output_html = Some(next_path(&args, &mut i, "--output-html")?);
            }
            _ => {
                return Err(SiteError::new(format!(
                    "unknown render-snapshot option {arg:?}\n{}",
                    render_usage()
                )));
            }
        }
    }
    Ok(RenderConfig {
        snapshot_json: required(snapshot_json, "--snapshot-json")?,
        output_html: required(output_html, "--output-html")?,
    })
}

fn next_path(args: &[OsString], i: &mut usize, flag: &str) -> SiteResult<PathBuf> {
    Ok(PathBuf::from(next_string(args, i, flag)?))
}

fn next_string(args: &[OsString], i: &mut usize, flag: &str) -> SiteResult<String> {
    if *i + 1 >= args.len() {
        return Err(SiteError::new(format!("{flag} requires a value")));
    }
    let value = args[*i + 1].to_string_lossy().into_owned();
    *i += 2;
    Ok(value)
}

fn required<T>(value: Option<T>, flag: &str) -> SiteResult<T> {
    value.ok_or_else(|| SiteError::new(format!("{flag} is required")))
}

pub fn parse_thresholds(raw: &str) -> SiteResult<Vec<u32>> {
    let mut values = Vec::new();
    for token in raw.split(',') {
        let trimmed = token.trim();
        if trimmed.is_empty() {
            continue;
        }
        values.push(parse_positive_u32(trimmed, "--thresholds")?);
    }
    if values.is_empty() {
        return Err(SiteError::new("--thresholds must not be empty"));
    }
    values.sort_unstable();
    values.dedup();
    Ok(values)
}

fn parse_positive_usize(raw: &str, flag: &str) -> SiteResult<usize> {
    let value = raw
        .parse::<usize>()
        .map_err(|e| SiteError::new(format!("invalid {flag}: {e}")))?;
    if value == 0 {
        return Err(SiteError::new(format!("{flag} must be positive")));
    }
    Ok(value)
}

fn parse_positive_u32(raw: &str, flag: &str) -> SiteResult<u32> {
    let value = raw
        .parse::<u32>()
        .map_err(|e| SiteError::new(format!("invalid {flag}: {e}")))?;
    if value == 0 {
        return Err(SiteError::new(format!("{flag} must be positive")));
    }
    Ok(value)
}

fn usage() -> &'static str {
    "usage: reti-site <build-fce-tablebase|render-snapshot|samples-js|sankey-js|openings-js> [options]"
}

fn build_usage() -> &'static str {
    "usage: reti-site build-fce-tablebase --annotated-run-dir DIR --source-totals-json FILE --syzygy-dir DIR --output-dir DIR --title TITLE [--work-dir DIR] [--workers N] [--thresholds 1,2,5,10,20] [--sample-size 32] [--opening-catalog-csv FILE|--no-opening-catalog]"
}

fn render_usage() -> &'static str {
    "usage: reti-site render-snapshot --snapshot-json FILE --output-html FILE"
}

fn samples_js_usage() -> &'static str {
    "usage: reti-site samples-js --samples-json FILE --output-js FILE"
}

fn sankey_js_usage() -> &'static str {
    "usage: reti-site sankey-js --sqlite-db FILE --output-js FILE [--thresholds 1,2,5,10,20]"
}

fn openings_js_usage() -> &'static str {
    "usage: reti-site openings-js --opening-counts-json FILE --source-totals-json FILE --output-js FILE [--opening-catalog-csv FILE|--no-opening-catalog]"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_thresholds_sorted_unique() {
        assert_eq!(parse_thresholds("10,1,2,2").unwrap(), vec![1, 2, 10]);
        assert!(parse_thresholds("0").is_err());
    }

    #[test]
    fn build_requires_syzygy() {
        let err = Args::parse([
            OsString::from("build-fce-tablebase"),
            OsString::from("--annotated-run-dir"),
            OsString::from("run"),
            OsString::from("--source-totals-json"),
            OsString::from("totals.json"),
            OsString::from("--output-dir"),
            OsString::from("out"),
            OsString::from("--title"),
            OsString::from("T"),
        ])
        .unwrap_err();
        assert!(err.to_string().contains("--syzygy-dir"));
    }

    #[test]
    fn parses_render_snapshot() {
        let args = Args::parse([
            OsString::from("render-snapshot"),
            OsString::from("--snapshot-json"),
            OsString::from("snapshot.json"),
            OsString::from("--output-html"),
            OsString::from("index.html"),
        ])
        .unwrap();
        match args.command {
            Command::RenderSnapshot(config) => {
                assert_eq!(config.snapshot_json, PathBuf::from("snapshot.json"));
                assert_eq!(config.output_html, PathBuf::from("index.html"));
            }
            _ => panic!("wrong command"),
        }
    }

    #[test]
    fn parses_build_sample_size() {
        let args = Args::parse([
            OsString::from("build-fce-tablebase"),
            OsString::from("--annotated-run-dir"),
            OsString::from("run"),
            OsString::from("--source-totals-json"),
            OsString::from("totals.json"),
            OsString::from("--syzygy-dir"),
            OsString::from("tb"),
            OsString::from("--output-dir"),
            OsString::from("out"),
            OsString::from("--title"),
            OsString::from("T"),
            OsString::from("--sample-size"),
            OsString::from("12"),
        ])
        .unwrap();
        match args.command {
            Command::BuildFceTablebase(config) => {
                assert_eq!(config.sample_size, 12);
            }
            _ => panic!("wrong command"),
        }

        let err = Args::parse([
            OsString::from("build-fce-tablebase"),
            OsString::from("--annotated-run-dir"),
            OsString::from("run"),
            OsString::from("--source-totals-json"),
            OsString::from("totals.json"),
            OsString::from("--syzygy-dir"),
            OsString::from("tb"),
            OsString::from("--output-dir"),
            OsString::from("out"),
            OsString::from("--title"),
            OsString::from("T"),
            OsString::from("--sample-size"),
            OsString::from("0"),
        ])
        .unwrap_err();
        assert!(err.to_string().contains("--sample-size must be positive"));
    }

    #[test]
    fn parses_samples_js() {
        let args = Args::parse([
            OsString::from("samples-js"),
            OsString::from("--samples-json"),
            OsString::from("samples.json"),
            OsString::from("--output-js"),
            OsString::from("sampled_examples.js"),
        ])
        .unwrap();
        match args.command {
            Command::SamplesJs(config) => {
                assert_eq!(config.samples_json, PathBuf::from("samples.json"));
                assert_eq!(config.output_js, PathBuf::from("sampled_examples.js"));
            }
            _ => panic!("wrong command"),
        }
    }

    #[test]
    fn parses_sankey_js() {
        let args = Args::parse([
            OsString::from("sankey-js"),
            OsString::from("--sqlite-db"),
            OsString::from("evaluations.sqlite3"),
            OsString::from("--output-js"),
            OsString::from("sankey.js"),
            OsString::from("--thresholds"),
            OsString::from("1,5"),
        ])
        .unwrap();
        match args.command {
            Command::SankeyJs(config) => {
                assert_eq!(config.sqlite_db, PathBuf::from("evaluations.sqlite3"));
                assert_eq!(config.output_js, PathBuf::from("sankey.js"));
                assert_eq!(config.thresholds, vec![1, 5]);
            }
            _ => panic!("wrong command"),
        }
    }

    #[test]
    fn parses_openings_js() {
        let args = Args::parse([
            OsString::from("openings-js"),
            OsString::from("--opening-counts-json"),
            OsString::from("opening_counts.json"),
            OsString::from("--source-totals-json"),
            OsString::from("source_totals.json"),
            OsString::from("--output-js"),
            OsString::from("openings.js"),
            OsString::from("--no-opening-catalog"),
        ])
        .unwrap();
        match args.command {
            Command::OpeningsJs(config) => {
                assert_eq!(
                    config.opening_counts_json,
                    PathBuf::from("opening_counts.json")
                );
                assert_eq!(
                    config.source_totals_json,
                    PathBuf::from("source_totals.json")
                );
                assert_eq!(config.output_js, PathBuf::from("openings.js"));
                assert!(config.opening_catalog_csv.is_none());
            }
            _ => panic!("wrong command"),
        }
    }
}
