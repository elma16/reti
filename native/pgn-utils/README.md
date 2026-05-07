# pgn-utils

Native PGN utility binary. Started life as the lexical-repair accelerator for
the Python pipeline; now also handles concatenation, deduplication, and
linting. The legacy positional invocations are preserved exactly so the
Python wrapper does not need to change.

## What it does

The binary exposes four subcommands plus a backwards-compatible legacy form:

- `clean` — line-by-line lexical rewrite (the original behaviour). Strips
  BOM, replaces invalid UTF-8 with `?`, drops control characters other than
  `\n` / `\t`, removes `{...}` block comments, `;...` / `%...` line
  comments, and `(...)` side variations (`--preserve-markup` keeps them),
  and inserts a `*` result token for games that end without one.
- `concat` — combine multiple PGN files / directories into one output. Walks
  directories recursively for `*.pgn` and visits files in deterministic
  sorted order. Optional `--clean` runs the lexical rewriter on each input;
  optional `--dedup` drops duplicate games as it concatenates.
- `dedup` — drop duplicate games from a single file by hashing normalized
  movetext (move numbers, comments, variations, NAGs, result tokens, and
  whitespace are stripped before hashing).
- `lint` — report (does **not** fix) structural, header-consistency, and
  move-legality issues. Move legality is checked by replaying SAN moves with
  the `shakmaty` engine. Exits with status 2 if any issues are found.

A progress bar is printed to stderr by default; pass `--no-progress` to
silence it (it also disappears automatically when stderr is not a TTY).

## Contract with Python

The Rust binary is a drop-in optional accelerator for the pure-Python
implementation in [`src/reti/pgn_utils.py`](../../src/reti/pgn_utils.py).
The Python module looks for the binary at
`native/pgn-utils/target/{release,debug}/reti-pgn-utils`,
on `$PATH`, or at `$RETI_PGN_UTILS_BIN`. Set
`RETI_PGN_UTILS_NO_NATIVE=1` to force the Python path.

The CLI surface the Python wrapper depends on (still supported as the
"legacy form"):

| invocation | behaviour |
|---|---|
| `reti-pgn-utils <input> <output>` | rewrite, strip markup |
| `reti-pgn-utils --preserve-markup <input> <output>` | rewrite, keep markup |
| `reti-pgn-utils --inspect <input>` | scan only, write nothing |

The new subcommand form, for direct human use:

| invocation | behaviour |
|---|---|
| `reti-pgn-utils clean [--preserve-markup] [--inspect] INPUT [OUTPUT]` | same lexical rewrite as legacy, exposed as a subcommand |
| `reti-pgn-utils concat -o OUT [--clean] [--dedup] INPUTS...` | concatenate files / directories into one PGN |
| `reti-pgn-utils dedup -o OUT INPUT` | drop duplicate games by movetext |
| `reti-pgn-utils lint [--json] INPUT` | report issues (exit 2 on any) |

All three forms must print a single JSON object on stdout with these fields:

```
removed_bom: bool
invalid_utf8_replaced: int
control_characters_removed: int
games_written: int
comments_removed: int
variations_removed: int
line_comments_removed: int
```

The Python parser ([`_parse_native_stats`](../../src/reti/pgn_utils.py))
sets `used_native_accelerator=True` after a successful native run.

## Build

```
cargo build --release --manifest-path native/pgn-utils/Cargo.toml
```

## Why it exists

Rewriting `lumbra-gigabase` (~2 GB across hundreds of files) through Python's
character-by-character scanner is the only step in the CQL workflow that ever
felt slow. The Rust port is ~10x faster on the same input. Keep it; do not
add new Rust until there is a similar bottleneck.

## Layout

The crate is split into small modules so each subcommand stays
independently testable:

```
src/
  main.rs       dispatcher: legacy form vs. subcommand
  lib.rs        re-exports each module
  cli.rs        tiny argument parser shared by all subcommands
  progress.rs   indicatif wrapper that hides on non-TTY / --no-progress
  clean.rs      FastRewriter + run_clean
  concat.rs     run_concat (files / dirs / --clean / --dedup)
  dedup.rs      streaming game dedup with xxh3-64 hashing
  lint.rs       structural / consistency / shakmaty legality checks
  pgn_split.rs  shared streaming game splitter and movetext normalizer
tests/cli.rs    end-to-end regression tests for legacy + new subcommands
```

## What is *not* worth porting to Rust

Recorded so we don't relitigate this:

- The argparse / CLI plumbing in Python is fine.
- CQL itself is the workhorse and is already C++ — there is nothing to
  recover by wrapping its invocation in Rust.
- Stockfish is already C++; we drive it as a subprocess.
- One-shot scripts that the user runs by hand do not benefit from native
  speed.

A future PyO3 in-process binding for this repair lexer + the SAN scanner in
`reti.annotated_pgn` would remove the per-file subprocess overhead, but is
out of scope for the current refactor.
