# reti

A CQL-first repository for chess endgame analysis.

The core of this project is the `cql-files/` tree: collections of Chess Query
Language scripts for identifying endgames and positions in PGN databases. The
Python code in `src/reti/` exists to run those scripts and summarize results at
the command line.

## Repository layout

- `cql-files/`: the main script collections, including the FCE material
- `src/reti/repair_pgn.py`: one-time in-place PGN repair and normalization before CQL runs
- `src/reti/fast_pgn_repair.py`: fast lexical PGN repair path with optional native acceleration
- `src/reti/analyse_cql.py`: batch CLI runner for `pgn|dir x cql|dir` matrix execution
- `src/reti/export_cql_positions.py`: exports `{CQL}`-annotated PGN positions to an evaluated CSV
- `src/reti/fce_sankey.py`: core logic for building an interactive FCE transition Sankey
- `scripts/build_fce_table_subset.py`: builds the curated FCE subset used for the public table workflow
- `scripts/render_fce_table_from_summary.py`: renders markdown table rows from `analyse_cql.py` output
- `scripts/render_fce_sankey.py`: renders a standalone interactive Sankey HTML file from annotated FCE PGNs
- `tests_cql/`: fixtures and tests for the CQL scripts
- `docs/analyse_cql.md`: detailed documentation for the batch CQL runner
- `docs/export_cql_positions.md`: detailed documentation for exporting annotated positions to CSV
- `docs/fce_sankey.md`: workflow for turning annotated FCE PGN output into a public static Sankey page
- `docs/fce_table.md`: workflow for building the curated FCE table subset and rendering the final table
- `docs/repair_pgn.md`: one-time PGN repair workflow for CQL-unfriendly databases

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # use .venv\Scripts\Activate.ps1 on Windows
pip install -e .
```

You will also need a CQL binary. You can point the scripts at any installed
`cql` executable. If you keep a private local copy under `bins/`, that
directory is ignored by Git; the test and CLI resolution logic will still pick
it up automatically.

## CLI usage

Run the batch CQL runner:

```bash
python src/reti/analyse_cql.py \
  --pgn path/to/pgn_or_dir \
  --cql-bin path/to/cql \
  --scripts path/to/script_or_directory \
  --jobs 1 \
  -o path/to/output_dir
```

`src/reti/analyse_cql.py` accepts either a single PGN or a directory of PGNs,
and either a single CQL script or a directory of CQL scripts. It runs the full
cross-product and writes one output PGN per pair plus a `summary.csv`. During
preflight, if a PGN contains text-level incompatibilities that older CQL builds
dislike, the runner uses a sanitized temporary copy for that run and leaves the
original PGN untouched. By default the preflight stays cheap; deeper PGN parser
checks and the up-front CQL smoke test are both opt-in flags. The runner now
defaults to sequential job execution so CQL can use its own internal threading
without process-level oversubscription.

Detailed usage, output layout, and examples are in
[docs/analyse_cql.md](docs/analyse_cql.md).

If a PGN makes CQL abort, repair it once in place before analysis:

```bash
python src/reti/repair_pgn.py \
  --pgn ~/Downloads/LumbrasGigaBase_OTB_1900-1949.pgn \
  --cql-bin ./bins/cql6-2/cql
```

That now defaults to a fast CQL-safe lexical rewrite, optionally backed by the
native Rust helper under `native/repair-pgn-fast/` when you build it with Cargo.
It only replaces the original file if the repaired temp copy passes a CQL smoke
test. If you want the rewrite to finish as quickly as possible, omit
`--cql-bin`. If you need the older canonical python-chess normalization, add
`--mode strict`.
The fast repaired output is intentionally CQL-safe rather than canonical: it
keeps headers and movetext, but strips comments and side variations.

To repair an entire directory of PGNs at once (e.g. the full lumbra-gigabase),
pass the directory path to `--pgn`. Building the native Rust accelerator first
is recommended for large databases:

```bash
cargo build --release --manifest-path native/repair-pgn-fast/Cargo.toml
python src/reti/repair_pgn.py --pgn lumbra-gigabase/ --no-backup
```

This uses `--mode fast` (the default), which is the fastest option and produces
CQL-safe output. The native accelerator is detected automatically when
available. Use `--no-backup` to avoid doubling disk usage on large databases.

Full details are in [docs/repair_pgn.md](docs/repair_pgn.md).

If you already have PGNs containing `{CQL}` move comments, export those marked
positions to CSV like this:

```bash
python src/reti/export_cql_positions.py \
  --pgn path/to/annotated_pgn_or_dir \
  --output-csv output/cql_positions.csv \
  --syzygy-dir /path/to/syzygy \
  --stockfish-bin path/to/stockfish
```

For marked positions with 5 pieces or fewer, the exporter uses Syzygy. For
larger positions, it uses Stockfish for a configurable fixed time budget per
position. The CSV includes the source PGN, ending label from the PGN filename,
move context, FEN, and raw evaluation fields. Do not run `repair_pgn.py` on
these annotated PGNs first: the repair step deliberately strips comments.
Full details are in [docs/export_cql_positions.md](docs/export_cql_positions.md).

For the FCE table workflow, first build the curated subset:

```bash
python scripts/build_fce_table_subset.py
```

Then run the batch analysis over your PGN directory and render the markdown
table:

```bash
python src/reti/analyse_cql.py \
  --pgn path/to/pgn_dir \
  --cql-bin path/to/cql \
  --scripts cql-files/FCE/table \
  --jobs 1 \
  -o output/fce-table
python scripts/render_fce_table_from_summary.py output/fce-table/summary.csv path/to/pgn_dir
```

Detailed FCE instructions are in [docs/fce_table.md](docs/fce_table.md).

If you want an interactive web-facing view of how games move between FCE
endings, render the annotated output PGNs directly into a standalone HTML
Sankey:

```bash
python scripts/render_fce_sankey.py \
  --pgn-dir output/fce-table \
  --output-html docs/fce_sankey.html
```

That HTML file uses Plotly from a CDN and can be published as-is on GitHub
Pages or any other static host. Full details are in
[docs/fce_sankey.md](docs/fce_sankey.md).

## FCE table reference

Reference table from
https://en.wikipedia.org/wiki/Chess_endgame#Frequency_table

| ID | Ending | Quantity | Percentage |
|---|---|---|---|
| 1.4 | Bishop + Knight vs King | 283 (62 draws) | 0.02 |
| 2 | Pawn Endings | 48,465 | 2.87 |
|  | King + Pawn vs King | 3,920 | 0.23 |
| 3.1 | Knight vs Pawns | 15,512 | 0.92 |
| 3.2 | Knight vs Knight | 26,263 | 1.56 |
| 4.1 | Bishop vs Pawns | 16,953 | 1.01 |
| 4.2 | Bishop vs Bishop (Same Colour) | 27,864 (11,351 draws) | 1.65 |
| 4.3 | Bishop vs Bishop (Opposite Colour) | 18,653 (11,045 draws) | 1.11 |
| 5 | Bishop vs Knight | 55,476 (19,670 draws) | 3.29 |
| 6.1 | Rook vs Pawns | 12,723 | 0.75 |
| 6.2 | Rook vs Rook | 142,488 (55,974 draws) | 8.45 |
| 6.2 A1 | Rook + Pawn vs Rook | 11,318 | 0.67 |
| 6.2 A2 | Rook + Two Pawns vs Rook | 9,398 (3,574 connected) | 0.56 |
| 6.3 | Two Rooks vs Two Rooks | 58,211 | 3.45 |
| 7.1 | Rook vs Knight | 16,298 | 0.97 |
| 7.2 | Rook vs Bishop | 25,524 | 1.51 |
| 8.1 | Rook + Knight vs Rook | 23,910 (467 without pawns; 418 draws) | 1.42 |
| 8.2 | Rook + Bishop vs Rook | 29,785 (736 without pawns; 401 draws) | 1.77 |
| 8.3 | Rook + Minor Piece vs Rook + Minor Piece | 255,317 | 15.13 |
| 9.1 | Queen vs Pawns | 7,066 | 0.42 |
| 9.2 | Queen vs Queen | 30,834 | 1.83 |
| 9.3 | Queen + Pawn vs Queen | 1,575 | 0.09 |
| 10.1 | Queen vs One Minor Piece | 2,798 | 0.17 |
| 10.2 | Queen vs Rook | 6,769 (263 without pawns and 10 half-moves; 22 draws) | 0.40 |
| 10.3 | Queen vs Two Minor Pieces | 1,276 | 0.08 |
| 10.4 | Queen vs Rook + Minor Piece | 11,637 | 0.69 |
| 10.5 | Queen vs Two Rooks | 5,257 | 0.31 |
| 10.6 | Queen vs Three Minor Pieces | 239 | 0.01 |
| 10.7 | Queen and Minor Piece vs Queen | 15,128 | 0.90 |
|  | Queen + Bishop vs Two Rooks | Only one without pawns! | 0.00006 |
