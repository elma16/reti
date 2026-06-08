//! Library facade for the PGN utility binary.
//!
//! Each subcommand lives in its own module; the binary in `main.rs` is a thin
//! dispatcher that parses the CLI and calls into one of these `run_*` entry
//! points. Splitting the logic into a library lets us unit-test the parsers,
//! splitters, and rewriters directly without spawning a subprocess.

pub mod annotated;
pub mod clean;
pub mod cli;
pub mod concat;
pub mod count;
pub mod dedup;
pub mod eco;
pub mod fce_combined_markers;
pub mod fce_markers;
pub mod fce_syzygy;
pub mod lint;
pub mod output;
pub mod pgn_split;
pub mod progress;
pub mod search;
pub mod set_ops;
pub mod source_totals;
