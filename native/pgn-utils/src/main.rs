//! Binary entry point.
//!
//! Two argument shapes are accepted:
//!
//!   subcommand form:  `reti-pgn-utils <clean|concat|dedup|lint> ...`
//!   legacy form:      `reti-pgn-utils [--preserve-markup] INPUT OUTPUT`
//!                     `reti-pgn-utils --inspect INPUT`
//!
//! The legacy form is what the Python wrapper at
//! `src/reti/pgn_utils.py` invokes; preserving it byte-for-byte means
//! we can extend the binary without touching Python.
//!
//! The dispatcher picks the form by inspecting the first argument: if it
//! matches a known subcommand name we route there, otherwise we treat the
//! whole argv as the legacy form (which itself just delegates to `clean`).

use std::env;
use std::ffi::OsString;
use std::process::ExitCode;

use reti_pgn_utils::{clean, concat, dedup, lint};

const USAGE: &str = "\
usage: reti-pgn-utils <SUBCOMMAND> [options]
       reti-pgn-utils [--preserve-markup] INPUT_PGN OUTPUT_PGN
       reti-pgn-utils --inspect INPUT_PGN

subcommands:
  clean   rewrite a PGN file (strips markup, normalizes whitespace, etc.)
  concat  concatenate one or more PGN files / directories into one
  dedup   drop duplicate games by normalized movetext
  lint    report (does not fix) structural / consistency / legality issues

global flags (any subcommand):
  --no-progress   disable the stderr progress bar
  --json          machine-readable output (currently used by `lint`)";

fn main() -> ExitCode {
    let args: Vec<OsString> = env::args_os().skip(1).collect();
    match dispatch(&args) {
        Ok(code) => ExitCode::from(code as u8),
        Err(message) => {
            eprintln!("{message}");
            ExitCode::from(2)
        }
    }
}

fn dispatch(args: &[OsString]) -> Result<i32, String> {
    let first = args.first().map(|a| a.to_string_lossy().into_owned());
    match first.as_deref() {
        Some("clean") => clean::run_subcommand(&args[1..]).map(|_| 0),
        Some("concat") => concat::run_subcommand(&args[1..]).map(|_| 0),
        Some("dedup") => dedup::run_subcommand(&args[1..]).map(|_| 0),
        Some("lint") => lint::run_subcommand(&args[1..]),
        Some("--help") | Some("-h") | Some("help") => {
            println!("{USAGE}");
            Ok(0)
        }
        _ => run_legacy(args),
    }
}

/// Legacy form, preserved exactly for the Python wrapper:
///   reti-pgn-utils [--preserve-markup] INPUT OUTPUT
///   reti-pgn-utils --inspect INPUT
fn run_legacy(args: &[OsString]) -> Result<i32, String> {
    use std::path::PathBuf;

    let mut preserve_markup = false;
    let mut inspect = false;
    let mut positionals: Vec<PathBuf> = Vec::with_capacity(2);
    let mut no_progress = false;

    for arg in args {
        let as_string = arg.to_string_lossy();
        if as_string == "--preserve-markup" {
            preserve_markup = true;
        } else if as_string == "--inspect" {
            inspect = true;
        } else if as_string == "--no-progress" {
            no_progress = true;
        } else if as_string.starts_with("--") {
            return Err(format!("unknown option: {as_string}\n{USAGE}"));
        } else {
            positionals.push(PathBuf::from(arg));
        }
    }

    let expected = if inspect { 1 } else { 2 };
    if positionals.len() != expected {
        return Err(USAGE.to_string());
    }

    let (input_path, output_path) = if inspect {
        (positionals.pop().unwrap(), None)
    } else {
        let out = positionals.pop().unwrap();
        (positionals.pop().unwrap(), Some(out))
    };

    let stats = clean::run_clean(
        &input_path,
        output_path.as_deref(),
        preserve_markup,
        !no_progress,
    )
    .map_err(|e| format!("clean failed: {e}"))?;

    println!("{}", stats.to_json());
    Ok(0)
}
