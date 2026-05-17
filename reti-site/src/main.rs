use std::process::ExitCode;

use reti_site::{cli, opening_page, pipeline, render, sankey, SiteError};

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("{err}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<(), SiteError> {
    let args = cli::Args::parse(std::env::args_os().skip(1))?;
    match args.command {
        cli::Command::BuildFceTablebase(config) => {
            let result = pipeline::build_fce_tablebase(config)?;
            if result.up_to_date {
                println!("Up to date: {}", result.output_dir.display());
            } else {
                println!("Wrote snapshot: {}", result.snapshot_json.display());
                println!("Wrote SQLite DB: {}", result.sqlite_db.display());
                println!("Wrote HTML: {}", result.index_html.display());
            }
        }
        cli::Command::RenderSnapshot(config) => {
            render::render_snapshot_file(&config.snapshot_json, &config.output_html)?;
            println!("Wrote HTML: {}", config.output_html.display());
        }
        cli::Command::SamplesJs(config) => {
            render::write_samples_js(&config.samples_json, &config.output_js)?;
            println!("Wrote samples JS: {}", config.output_js.display());
        }
        cli::Command::SankeyJs(config) => {
            sankey::write_sankey_js_from_path(
                &config.sqlite_db,
                &config.output_js,
                &config.thresholds,
            )?;
            println!("Wrote Sankey JS: {}", config.output_js.display());
        }
        cli::Command::OpeningsJs(config) => {
            opening_page::write_openings_js(
                &config.opening_counts_json,
                &config.source_totals_json,
                config.opening_catalog_csv.as_deref(),
                &config.output_js,
            )?;
            println!("Wrote openings JS: {}", config.output_js.display());
        }
    }
    Ok(())
}
