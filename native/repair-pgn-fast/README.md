# repair-pgn-fast

Optional native accelerator for the lexical PGN repair path.

## What it does

A line-by-line lexical rewriter that scrubs CQL-hostile bytes from a PGN file:

- strips a UTF-8 BOM if present
- replaces invalid UTF-8 with `?`
- drops control characters other than `\n` / `\t`
- by default, removes `{...}` block comments, `;...` / `%...` line comments,
  and `(...)` side variations
- with `--preserve-markup`, keeps comments and variations and only does the
  byte-level scrub
- inserts a `*` result token if a game ends without one

Output is intentionally CQL-safe rather than canonical: headers and movetext
survive; comments and variations are stripped (unless `--preserve-markup`).

## Contract with Python

The Rust binary is a drop-in optional accelerator for the pure-Python
implementation in [`src/reti/fast_pgn_repair.py`](../../src/reti/fast_pgn_repair.py).
The Python module looks for the binary at
`native/repair-pgn-fast/target/{release,debug}/reti-fast-pgn-repair`,
on `$PATH`, or at `$RETI_FAST_PGN_REPAIR_BIN`. Set
`RETI_FAST_PGN_REPAIR_NO_NATIVE=1` to force the Python path.

The CLI surface the Python wrapper depends on:

| invocation | behaviour |
|---|---|
| `reti-fast-pgn-repair <input> <output>` | rewrite, strip markup |
| `reti-fast-pgn-repair --preserve-markup <input> <output>` | rewrite, keep markup |
| `reti-fast-pgn-repair --inspect <input>` | scan only, write nothing |

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

The Python parser ([`_parse_native_stats`](../../src/reti/fast_pgn_repair.py))
sets `used_native_accelerator=True` after a successful native run.

## Build

```
cargo build --release --manifest-path native/repair-pgn-fast/Cargo.toml
```

## Why it exists

Rewriting `lumbra-gigabase` (~2 GB across hundreds of files) through Python's
character-by-character scanner is the only step in the CQL workflow that ever
felt slow. The Rust port is ~10x faster on the same input. Keep it; do not
add new Rust until there is a similar bottleneck.

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
