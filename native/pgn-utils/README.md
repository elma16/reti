# pgn-utils

Native PGN utility binary. Started life as the lexical-repair accelerator for
the Python pipeline; now also handles concatenation, deduplication, and
linting. The legacy positional invocations are preserved exactly so the
Python wrapper does not need to change.

## What it does

The binary exposes subcommands plus a backwards-compatible legacy form:

- `clean` — line-by-line lexical rewrite (the original behaviour). Strips
  BOM, replaces invalid UTF-8 with `?`, drops control characters other than
  `\n` / `\t`, removes `{...}` block comments, `;...` / `%...` line
  comments, and `(...)` side variations (`--preserve-markup` keeps them),
  and inserts a `*` result token for games that end without one. In strip
  mode the movetext is then re-flowed into standard export formatting —
  headers one per line, one blank line before the movetext, and move tokens
  wrapped at 80 columns — so stripping per-move comment dumps (e.g. TCEC eval
  logs) doesn't leave a ragged one-move-per-line layout. `--preserve-markup`
  keeps the source's exact line layout untouched.
- `concat` — combine multiple PGN files / directories into one output. Walks
  directories recursively for `*.pgn` and visits files in deterministic
  sorted order. Optional `--clean` runs the lexical rewriter on each input;
  optional `--dedup` drops duplicate games as it concatenates.
- `count` — count games and break them down by header or derived fields,
  printing an aligned text table. With no `--by` it tallies games per source
  file plus a grand total; `--by FIELD` regroups by any PGN tag (`White`,
  `Event`, `Result`, `ECO`, …) or a derived key (`year`, `month`, `eco-base`,
  `file`), and repeating `--by` builds a cross-tab (one column per dimension,
  one row per distinct combination). Rows sort by count descending (`--sort
  key` for alphabetical); `--top N` keeps the N largest groups and reports how
  many were omitted. A game is one `[Event ...]` boundary (same splitter as the
  other subcommands); a game missing the field counts under `unknown`.
- `dedup` — drop duplicate games from a single file by hashing normalized
  movetext (move numbers, comments, variations, NAGs, result tokens, and
  whitespace are stripped before hashing).
- `eco` — label games with `[ECO]` and `[Opening]` tags. Each game is replayed
  with `shakmaty` and matched against an opening book built from
  `data/openings/lumbras_eco_codes.csv` (embedded in the binary). Matching is
  position-based, so transpositions still classify, and the deepest reached
  opening wins. By default only games missing an `[ECO]` are tagged; `--force`
  recomputes and overwrites every game. Games with a non-standard start
  (`[FEN]`/`[SetUp "1"]`) are left alone. The movetext is emitted unchanged, so
  `eco` composes with `clean`. `--eco-csv PATH` overrides the embedded book.
- `annotated-pgn` — stream annotated PGNs, replay mainlines with `shakmaty`,
  and write JSONL records containing headers, UCI moves, replay errors, and
  positions marked by a chosen comment such as `{CQL}`.
- `set` — set operations over two PGN sources (each a file, directory, or
  `-` for stdin): `intersect` (games in both), `union` (every distinct game),
  `diff` (games in A but not B). Two games are equal when byte-identical
  (after trimming the trailing blank line); run `clean` first for
  format-insensitive comparison. Output is deduplicated.
- `grep` — find games whose header fields match a query and emit the whole
  matching games. Matching is token-based with case + accent folding, so
  `--player "Magnus Carlsen"` and `--player "Carlsen, Magnus"` both match
  `[White "Carlsen, Magnus"]`, and `muller` matches `Müller`. Filters:
  `--player` (White **or** Black), `--white`/`--black`/`--event`/`--site`,
  `--year`/`--year-min`/`--year-max`, and a repeatable `--tag NAME=Q` for any
  header; all supplied filters must match. The default is a native single-pass
  scan (reads each byte once, smooth progress). `--prefilter` opts into an
  accent-sound `ripgrep` prefilter that skips files which cannot match before
  the native scan — only a win for a sparse query over a warm, cached corpus;
  on a large disk-bound corpus it is slower (it reads everything via rg first).
- `lint` — report (does **not** fix) structural, header-consistency, and
  move-legality issues. Move legality is checked by replaying SAN moves with
  the `shakmaty` engine. Exits with status 2 if any issues are found.
- `source-totals` — stream source PGNs once, count `[Event ...]` game
  headers, classify Lumbras buckets as `otb` / `online`, and write a stable
  JSON denominator artifact for snapshot rebuilds.

A progress bar is printed to stderr by default; pass `--no-progress` to
silence it (it also disappears automatically when stderr is not a TTY).

## Piping

`clean`, `concat`, `dedup`, and `lint` are pipe-friendly so multi-step work
needs no intermediate files:

```
pgn-utils concat . | pgn-utils clean - | pgn-utils dedup - -o unique.pgn
```

- A lone `-` as an input reads stdin; `concat`/`clean` also default to stdin
  when no input is given and stdin is piped.
- Output goes to `-o FILE`, to `-o -` (forced stdout), or — when stdout is
  **not** an interactive terminal — straight to stdout for piping.
- To avoid dumping a multi-megabyte PGN into your terminal, a writer with no
  `-o` and an interactive stdout **refuses** with a hint instead of flooding
  the screen (so the progress bar stays readable). Add `-o FILE`, `-o -`, or a
  pipe/redirect.
- When the data stream goes to stdout, the trailing JSON stats line is written
  to **stderr** so it never corrupts a downstream parser. With `-o FILE` (or
  `--inspect`) the stats stay on stdout, exactly as before.

## Contract with Python

The Rust binary is a drop-in optional accelerator for the pure-Python
implementation in [`src/reti/pgn_utils.py`](../../src/reti/pgn_utils.py).
The Python module looks for the binary at
`native/pgn-utils/target/{release,debug}/pgn-utils`,
on `$PATH`, or at `$PGN_UTILS_BIN`. Set
`PGN_UTILS_NO_NATIVE=1` to force the Python path.

The CLI surface the Python wrapper depends on (still supported as the
"legacy form"):

| invocation | behaviour |
|---|---|
| `pgn-utils <input> <output>` | rewrite, strip markup |
| `pgn-utils --preserve-markup <input> <output>` | rewrite, keep markup |
| `pgn-utils --inspect <input>` | scan only, write nothing |

The new subcommand form, for direct human use:

| invocation | behaviour |
|---|---|
| `pgn-utils clean [--preserve-markup] [--inspect] [-o OUT] INPUT` | same lexical rewrite as legacy, exposed as a subcommand (`INPUT`/`OUT` may be `-`) |
| `pgn-utils concat [-o OUT] [--clean] [--dedup] INPUTS...` | concatenate files / directories / stdin into one PGN |
| `pgn-utils count [--by FIELD]... [--sort count\|key] [--top N] INPUT...` | count games as an aligned table; group by any tag or a derived key (`year`/`month`/`eco-base`/`file`), repeat `--by` for a cross-tab (`INPUT` may be `-`) |
| `pgn-utils dedup [-o OUT] INPUT` | drop duplicate games by movetext (`INPUT` may be `-`) |
| `pgn-utils eco [--force] [-o OUT] INPUT` | add `[ECO]`/`[Opening]` tags (position-based; `--force` overwrites; `INPUT` may be `-`) |
| `pgn-utils set <intersect\|union\|diff> A B [-o OUT]` | set operations on two PGN sources (exact-bytes identity) |
| `pgn-utils grep [FILTERS] INPUT... [-o OUT]` | find games by player/event/year/tag (token + accent fold) and emit them |
| `pgn-utils annotated-pgn -o OUT [--marker CQL] INPUTS...` | replay annotated PGNs and export per-game marker JSONL |
| `pgn-utils lint [--json] INPUT` | report issues (exit 2 on any); `INPUT` may be `-` |
| `pgn-utils source-totals -o OUT INPUTS...` | count games per source PGN once |

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
  output.rs     stdin/stdout/-o resolution: terminal-flood guard + stats routing
  clean.rs      FastRewriter + run_clean
  concat.rs     run_concat (files / dirs / --clean / --dedup)
  count.rs      count games grouped by header/derived fields into a table
  dedup.rs      streaming game dedup with xxh3-64 hashing
  eco.rs        position-based ECO/Opening classifier (embedded Lumbras book)
  set_ops.rs    intersect / union / diff of two PGN sources (exact-bytes key)
  search.rs     grep: token + accent-fold header matching, optional rg prefilter
  lint.rs       structural / consistency / shakmaty legality checks
  pgn_split.rs  shared streaming game splitter and movetext normalizer
  source_totals.rs  one-time source denominator JSON builder
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
