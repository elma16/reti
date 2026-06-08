# cql-site

`cql-site` builds reusable static dashboards from already-annotated PGNs.

It does **not** run CQL. It expects the CQL stage to have produced PGNs whose
comments contain marker stems, for example an `analyse_cql.py --output-mode
single` directory such as `outmatesSORTED`.

For each annotated PGN it streams the games once and computes:

- unique games containing each marker
- marker comment instances
- exclusive vs overlapping marker games
- marker co-occurrence pairs
- ECO base, result, rating-band, and OTB/online source breakdowns

## Build From An Annotated Run

```bash
cargo run --manifest-path cql-site/Cargo.toml -- build \
  --annotated-run-dir outmatesSORTED \
  --output-dir out/cql-mates-site \
  --title "Checkmate patterns in Lumbra's Gigabase" \
  --generic-stem ismate
```

The builder reads `summary.csv` to discover output PGNs and CQL-script stems,
then streams each retained annotated PGN once.

It also supports older per-CQL output directories: if `summary.csv` says a
retained output PGN came from exactly one known CQL stem, every game in that PGN
is counted for that stem even if the marker comment is not present.

## Build From PGNs Directly

When no `summary.csv` is available, pass the annotated PGN files and the marker
stems explicitly:

```bash
cargo run --manifest-path cql-site/Cargo.toml -- build \
  --pgn annotated-a.pgn \
  --pgn annotated-b.pgn \
  --known-stems ismate,greco,backrankmate \
  --output-dir out/custom-cql-site
```

## Optional Metadata

`--catalog-csv` may provide labels and grouping:

```csv
stem,label,group,description,color
greco,Greco mate,Mate pattern,Queen and bishop mating net,#1c6c8c
```

`--source-totals-json` may provide true corpus denominators using the same shape
as `reti-site` source-total files. Without it, percentages use the annotated PGN
games scanned as the denominator.

`--generic-stem` marks a broad marker, such as `ismate`, that can be hidden from
the co-occurrence table:

```bash
cargo run --manifest-path cql-site/Cargo.toml -- build \
  --annotated-run-dir outmatesSORTED \
  --generic-stem ismate \
  --output-dir out/cql-mates-site
```

`--examples` adds FCE-table-style expandable sample boards for each marker.
This performs a second pass over the annotated PGNs so it can replay moves and
capture FENs at marker comments:

```bash
cargo run --manifest-path cql-site/Cargo.toml -- build \
  --annotated-run-dir out/mates/outmatesSORTED \
  --examples \
  --sample-size 24 \
  --generic-stem ismate \
  --output-dir out/mates/cql-mates-site
```

Examples are source-stratified deterministic samples over the first marker
position for each game and stem. They require marker comments in the PGN; older
whole-file per-CQL outputs can still be counted, but cannot produce board
examples unless the comments are present.

The generated site is static: open `OUTPUT_DIR/index.html`.
