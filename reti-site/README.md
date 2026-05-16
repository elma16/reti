# reti-site

`reti-site` is the Rust-first builder for the FCE Gigabase dashboard.

The goal is to make the expensive preprocessing a one-time, reproducible
operation:

1. validate the combined CQL marker run;
2. stream annotated PGNs once;
3. store first-run/game-ending facts in SQLite;
4. evaluate first-marker `<=5`-man positions with Syzygy WDL;
5. precompute dashboard aggregates for `All`, `OTB`, and `Online`;
6. write reusable artifacts and a static HTML page.

The older Python builder is kept for compatibility while this Rust pipeline is
validated.

## Canonical Command

From the repository root:

First make sure the shared Rust utilities are built:

```bash
cargo build --release --manifest-path native/pgn-utils/Cargo.toml
cargo build --release --manifest-path reti-site/Cargo.toml
```

If the source-total denominator JSON does not already exist, create it once:

```bash
native/pgn-utils/target/release/reti-pgn-utils source-totals \
  --force \
  -o /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
  /Volumes/2025archive/lumbra-gigabase
```

After that, the tablebase snapshot build reads the annotated combined marker
run and the source-total JSON. It does not reread original PGNs.

```bash
reti-site/target/release/reti-site build-fce-tablebase \
  --annotated-run-dir /Users/elliottmacneil/Desktop/FCEtable \
  --source-totals-json /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
  --syzygy-dir /Users/elliottmacneil/Documents/chess/tablebases/345/3-4-5-wdl \
  --thresholds 1,2,5,10,20 \
  --workers 4 \
  --work-dir /Users/elliottmacneil/Desktop/FCEtable-work \
  --output-dir /Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-2026-05-15-v2 \
  --title "FCE endings in Lumbra's Gigabase"
```

`--work-dir` should be on the internal SSD. The final output may be on the
archive drive; only the completed directory is copied there at the end.

Every expensive phase prints a status line and the Rust subcommands print JSON
completion stats. If the output directory already matches the manifest, the
command exits as up to date without rescanning or reevaluating.

## Timed Full Rebuild After CQL Changes

Use this when the CQL marker definitions change and the annotated PGNs must be
rebuilt. It creates a timestamped CQL run, a timestamped tablebase snapshot, and
a timing log. The helper is written for `zsh`; do not name a variable `status`,
because that is read-only in `zsh`.

From the repository root:

```bash
cd ~/python/chess-stuff/reti
source .venv/bin/activate

STAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="$HOME/Desktop/FCEtable-knbpawns-$STAMP"
WORK_DIR="$HOME/Desktop/FCEtable-work-knbpawns-$STAMP"
OUT_DIR="/Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-knbpawns-$STAMP"
TIMING_LOG="/Volumes/2025archive/FCE-table/timings/fce-knbpawns-$STAMP.log"
mkdir -p "$(dirname "$TIMING_LOG")"

run_timed() {
  local label="$1"
  shift
  printf '\n== %s ==\n' "$label" | tee -a "$TIMING_LOG"
  local start=$(date +%s)
  /usr/bin/time -l "$@" 2>&1 | tee -a "$TIMING_LOG"
  local exit_code=$pipestatus[1]
  local end=$(date +%s)
  printf '== %s elapsed %ss exit %s ==\n' "$label" "$((end-start))" "$exit_code" | tee -a "$TIMING_LOG"
  return "$exit_code"
}
```

Build the Rust binaries and regenerate the combined marker CQL:

```bash
run_timed "build native pgn-utils" \
  cargo build --release --manifest-path native/pgn-utils/Cargo.toml

run_timed "build reti-site" \
  cargo build --release --manifest-path reti-site/Cargo.toml

run_timed "regenerate combined FCE marker CQL" \
  .venv/bin/python scripts/build_fce_combined_marker_cql.py --force
```

Run CQL against the full Lumbra Gigabase PGN directory. This is the step that
creates the compressed annotated PGNs containing `{stem}` comments.

```bash
run_timed "run combined CQL markers" \
  .venv/bin/python src/reti/analyse_cql.py \
    --pgn /Volumes/2025archive/lumbra-gigabase \
    --cql-bin /Users/elliottmacneil/python/chess-stuff/reti/cql-bin/cqli-1.0.6-macos/cqli-arm64 \
    --scripts cql-files/FCE/combined/fce-table-markers.cql \
    --jobs 1 \
    -o "$RUN_DIR"
```

Build the tablebase-aware snapshot from that annotated run. This reads
`$RUN_DIR`, writes SQLite and dashboard artifacts, and probes only Syzygy
`<=5`-piece first-marker positions.

```bash
run_timed "build tablebase snapshot" \
  reti-site/target/release/reti-site build-fce-tablebase \
    --annotated-run-dir "$RUN_DIR" \
    --source-totals-json /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
    --syzygy-dir /Users/elliottmacneil/Documents/chess/tablebases/345/3-4-5-wdl \
    --thresholds 1,2,5,10,20 \
    --workers 4 \
    --work-dir "$WORK_DIR" \
    --output-dir "$OUT_DIR" \
    --title "FCE endings in Lumbra's Gigabase"
```

Build the lazy-loaded sample-board sidecar. This scans the annotated PGNs again
for deterministic samples, but it does not rerun CQL, rebuild SQLite, or probe
Syzygy.

```bash
run_timed "build sampled example JSON" \
  native/pgn-utils/target/release/reti-pgn-utils fce-combined-samples \
    --relative-to "$RUN_DIR" \
    --known-stems 1-4BN,2-0Pp,2-1P,3-1Np,3-2NN,4-1Bp,4-2scBB,4-3ocBB,5-0BN,6-1-0RP,6-2-0Rr,6-2-1RPr,6-2-2RPPr,6-2-2RPPrConnected,6-3RRrr,7-1RN,7-2RB,8-1RNr,8-1RNrNoPawns,8-2RBr,8-2RBrNoPawns,8-3RAra,9-1Qp,9-2Qq,9-3QPq,10-1Qa,10-2Qr,10-2QrNoPawns,10-3Qaa,10-4Qra,10-5Qrr,10-6Qaaa,10-7QAq,10-7-1Qbrr,10-7-1QbrrNoPawns \
    --thresholds 1,2,5,10,20 \
    --sample-size 60 \
    --force \
    -o "$OUT_DIR/sampled_examples.json" \
    "$RUN_DIR"

run_timed "split sampled examples into lazy JS chunks" \
  reti-site/target/release/reti-site samples-js \
    --samples-json "$OUT_DIR/sampled_examples.json" \
    --output-js "$OUT_DIR/sampled_examples.js"
```

Open the completed dashboard and print the artifact paths:

```bash
open "$OUT_DIR/index.html"
echo "Output directory: $OUT_DIR"
echo "Annotated PGNs: $RUN_DIR"
echo "Timing log: $TIMING_LOG"
```

## Sample Boards

The dashboard can use a sidecar sample artifact for expandable boards. This
scan reads only the combined annotated PGNs; it does not run CQL, probe Syzygy,
or rebuild the SQLite database.

```bash
native/pgn-utils/target/release/reti-pgn-utils fce-combined-samples \
  --relative-to /Users/elliottmacneil/Desktop/FCEtable \
  --known-stems 1-4BN,2-0Pp,2-1P,3-1Np,3-2NN,4-1Bp,4-2scBB,4-3ocBB,5-0BN,6-1-0RP,6-2-0Rr,6-2-1RPr,6-2-2RPPr,6-2-2RPPrConnected,6-3RRrr,7-1RN,7-2RB,8-1RNr,8-1RNrNoPawns,8-2RBr,8-2RBrNoPawns,8-3RAra,9-1Qp,9-2Qq,9-3QPq,10-1Qa,10-2Qr,10-2QrNoPawns,10-3Qaa,10-4Qra,10-5Qrr,10-6Qaaa,10-7QAq,10-7-1Qbrr,10-7-1QbrrNoPawns \
  --thresholds 1,2,5,10,20 \
  --sample-size 60 \
  --force \
  -o /Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-2026-05-15-v2/sampled_examples.json \
  /Users/elliottmacneil/Desktop/FCEtable

reti-site/target/release/reti-site samples-js \
  --samples-json /Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-2026-05-15-v2/sampled_examples.json \
  --output-js /Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-2026-05-15-v2/sampled_examples.js
```

The sampler keeps at most 60 examples per `corpus view + threshold + stem`.
If fewer than 60 qualifying games exist, all available examples are emitted.
Sampling is source-stratified: each source PGN keeps a deterministic reservoir,
then the final display sample is drawn round-robin across eligible sources so
large recent PGNs do not dominate every row.

The HTML references `sampled_examples.js` as a sidecar. This keeps the initial
HTML small and works well for static hosting such as GitHub Pages.

## Semantics

For each source game and FCE ending stem:

- repeated comments for the same stem at the same ply are deduplicated by the
  marker extractor;
- consecutive same-stem marker plies form runs;
- the first run is the canonical occurrence for that `(game, stem)`;
- incidence at threshold `X` counts the game/stem if that first run has at
  least `X` half-move positions;
- tablebase stats use only the first marker position of that first run;
- duplicate FENs are evaluated once in SQLite, but each game/stem contributes
  separately to aggregate WDL/result counts.

This intentionally excludes later longer recurrences when the first occurrence
was short. That is the cost of the “first match per game/ending” rule.

## Output

The output directory contains:

```text
evaluations.sqlite3
snapshot.json
manifest.json
summary_by_ending.csv
tablebase_wdl_by_view_threshold.csv
index.html
```

`evaluations.sqlite3` is the reusable preprocessing artifact. `snapshot.json`
and the CSVs are derived from it.

## Idempotency

If `manifest.json`, `snapshot.json`, `evaluations.sqlite3`, and `index.html`
already exist and the manifest matches the current inputs/settings, the command
exits as up to date.

If the output directory exists with a different manifest, the build fails unless
`--force` is supplied or a new `--output-dir` is chosen.

## Module Layout

- `cli.rs`: command parsing and validation.
- `source.rs`: `summary.csv` and source-total validation.
- `catalog.rs`: FCE canonical rows and auxiliary subrows.
- `pipeline.rs`: build orchestration and atomic output install.
- `aggregate.rs`: SQL indexes, incidence aggregates, WDL/result aggregates.
- `csv_export.rs`: human-readable CSV exports.
- `render.rs`: self-contained static dashboard HTML.
- `manifest.rs`: input signatures and build fingerprinting.
- `sqlite.rs`: small SQLite FFI wrapper used by aggregation.

The marker extraction and Syzygy probing are Rust subcommands in
`native/pgn-utils`:

- `fce-combined-markers`
- `fce-syzygy-eval`

`reti-site` calls those Rust tools and then performs the remaining aggregation
and artifact writing in Rust.
