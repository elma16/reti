//! Output-sink policy shared by the PGN-stream subcommands (`concat`, `clean`,
//! `dedup`, `lint`).
//!
//! Two related concerns live here so every subcommand resolves them the same
//! way:
//!
//!   * **Where the primary output goes.** `-o FILE` writes a file, `-o -`
//!     forces stdout, and a missing flag streams to stdout *only when stdout
//!     is not an interactive terminal*. Writing a multi-megabyte PGN straight
//!     to a terminal is the "wall of text" we explicitly refuse: when stdout
//!     is a TTY and no destination was given we error with a hint instead.
//!
//!   * **Where the trailing JSON stats line goes.** When the data stream is
//!     going to stdout (a pipe or `-`), the stats must not be mixed into it or
//!     they would corrupt a downstream `clean`/`dedup`; in that case stats go
//!     to stderr. Otherwise (a real file, or `--inspect`) the stats are the
//!     result and stay on stdout, preserving the contract the Python wrapper
//!     in `src/reti/pgn_utils.py` relies on.

use std::fs::File;
use std::io::{self, BufWriter, IsTerminal, Read, Write};
use std::path::Path;

/// A resolved primary-output destination plus where its stats line belongs.
pub struct OutputSink {
    pub writer: Box<dyn Write>,
    /// True when the data stream is stdout, so the stats line must go to
    /// stderr to keep the pipe clean.
    pub stats_to_stderr: bool,
}

/// Does this path mean "standard stream" (a lone `-`)?
pub fn is_stdin_path(path: &Path) -> bool {
    path == Path::new("-")
}

/// Resolve `--output`/`-o` into a writer, applying the terminal-flood guard.
///
/// `label` names the subcommand so the error message can be specific.
pub fn open_output(output: Option<&Path>, label: &str) -> io::Result<OutputSink> {
    match output {
        Some(path) if is_stdin_path(path) => Ok(stdout_sink()),
        Some(path) => Ok(OutputSink {
            writer: Box::new(BufWriter::new(File::create(path)?)),
            stats_to_stderr: false,
        }),
        None => {
            if io::stdout().is_terminal() {
                Err(io::Error::other(format!(
                    "{label}: refusing to write PGN output to the terminal. \
                     Pass -o FILE to write a file, '-' to force stdout, \
                     or pipe/redirect the output (e.g. `{label} ... | pgn-utils clean -`)."
                )))
            } else {
                Ok(stdout_sink())
            }
        }
    }
}

fn stdout_sink() -> OutputSink {
    OutputSink {
        writer: Box::new(BufWriter::new(io::stdout().lock())),
        stats_to_stderr: true,
    }
}

/// Print a stats JSON line to the side the sink decided on.
pub fn print_stats(json: &str, stats_to_stderr: bool) {
    if stats_to_stderr {
        eprintln!("{json}");
    } else {
        println!("{json}");
    }
}

/// Open an input source: a lone `-` (or, when `default_stdin` is set, the
/// absence of any path while stdin is piped) reads stdin; otherwise the file.
///
/// Returns the reader plus its length in bytes when known (files have a size,
/// stdin does not), so callers can pick a measured bar vs. a spinner.
pub fn open_input(path: &Path) -> io::Result<(Box<dyn Read>, Option<u64>)> {
    if is_stdin_path(path) {
        Ok((Box::new(io::stdin().lock()), None))
    } else {
        let len = std::fs::metadata(path)?.len();
        Ok((Box::new(File::open(path)?), Some(len)))
    }
}
