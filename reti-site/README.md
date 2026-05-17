# reti-site

`reti-site` is the Rust-first builder for the FCE Gigabase dashboard.

The goal is to make the expensive preprocessing a one-time, reproducible
operation:

1. validate the combined CQL marker run;
2. stream annotated PGNs once;
3. store first-run/game-ending facts in SQLite;
4. evaluate first-marker `<=5`-man positions with Syzygy WDL;
5. precompute dashboard aggregates for `All`, `OTB`, and `Online`;
6. precompute the optional ending-transition Sankey sidecar;
7. precompute optional ECO-base opening distribution sidecars;
8. write reusable artifacts and static site files.

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

This pass also stores exact source-game denominators by ECO base code
(`A00`-`E99`) for the opening-distribution page.

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
`$RUN_DIR`, writes SQLite and dashboard artifacts, probes only Syzygy
`<=5`-piece first-marker positions, emits the static frontend files, and emits
the ending-transition Sankey sidecar and lazy-loaded board examples. The
default sample cap is 32 games per `corpus view + threshold + ending`.

```bash
run_timed "build tablebase snapshot" \
  reti-site/target/release/reti-site build-fce-tablebase \
    --annotated-run-dir "$RUN_DIR" \
    --source-totals-json /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
    --syzygy-dir /Users/elliottmacneil/Documents/chess/tablebases/345/3-4-5-wdl \
    --thresholds 1,2,5,10,20 \
    --sample-size 32 \
    --workers 4 \
    --work-dir "$WORK_DIR" \
    --output-dir "$OUT_DIR" \
    --title "FCE endings in Lumbra's Gigabase"
```

Optionally build the opening-distribution sidecar for the same completed
snapshot. This scans the annotated marker PGNs once, counts ending incidence by
ECO base code, and then writes a small `openings.js` manifest plus lazy-loaded
per-ECO chunks under `openings/`. It does not run CQL, probe Syzygy, or rebuild
SQLite.

```bash
FCE_STEMS="1-4BN,2-0Pp,2-1P,3-1Np,3-2NN,4-1Bp,4-2scBB,4-3ocBB,5-0BN,6-1-0RP,6-2-0Rr,6-2-1RPr,6-2-2RPPr,6-2-2RPPrConnected,6-3RRrr,7-1RN,7-2RB,8-1RNr,8-1RNrNoPawns,8-2RBr,8-2RBrNoPawns,8-3RAra,9-1Qp,9-2Qq,9-3QPq,10-1Qa,10-2Qr,10-2QrNoPawns,10-3Qaa,10-4Qra,10-5Qrr,10-6Qaaa,10-7QAq,10-7-1Qbrr,10-7-1QbrrNoPawns"

run_timed "build opening distribution counts" \
  native/pgn-utils/target/release/reti-pgn-utils fce-combined-openings \
    --relative-to "$RUN_DIR" \
    --known-stems "$FCE_STEMS" \
    --thresholds 1,2,5,10,20 \
    --force \
    -o "$OUT_DIR/opening_counts.json" \
    "$RUN_DIR"

run_timed "write opening distribution page data" \
  reti-site/target/release/reti-site openings-js \
    --opening-counts-json "$OUT_DIR/opening_counts.json" \
    --source-totals-json /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
    --opening-catalog-csv data/openings/lumbras_eco_codes.csv \
    --output-js "$OUT_DIR/openings.js"
```

Open the completed dashboard and print the artifact paths:

```bash
open "$OUT_DIR/index.html"
echo "Output directory: $OUT_DIR"
echo "Annotated PGNs: $RUN_DIR"
echo "Timing log: $TIMING_LOG"
```

## Sample Boards

`build-fce-tablebase` now creates the sample-board sidecars by default:
`sampled_examples.json`, `sampled_examples.js`, and chunk files under
`sampled_examples/`. The extra scan reads only the combined annotated PGNs; it
does not run CQL, probe Syzygy, or rebuild the SQLite database.

The manual commands below are only needed if you intentionally want to rebuild
the examples for an existing snapshot without rebuilding the database:

```bash
native/pgn-utils/target/release/reti-pgn-utils fce-combined-samples \
  --relative-to /Users/elliottmacneil/Desktop/FCEtable \
  --known-stems 1-4BN,2-0Pp,2-1P,3-1Np,3-2NN,4-1Bp,4-2scBB,4-3ocBB,5-0BN,6-1-0RP,6-2-0Rr,6-2-1RPr,6-2-2RPPr,6-2-2RPPrConnected,6-3RRrr,7-1RN,7-2RB,8-1RNr,8-1RNrNoPawns,8-2RBr,8-2RBrNoPawns,8-3RAra,9-1Qp,9-2Qq,9-3QPq,10-1Qa,10-2Qr,10-2QrNoPawns,10-3Qaa,10-4Qra,10-5Qrr,10-6Qaaa,10-7QAq,10-7-1Qbrr,10-7-1QbrrNoPawns \
  --thresholds 1,2,5,10,20 \
  --sample-size 32 \
  --force \
  -o /Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-2026-05-15-v2/sampled_examples.json \
  /Users/elliottmacneil/Desktop/FCEtable

reti-site/target/release/reti-site samples-js \
  --samples-json /Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-2026-05-15-v2/sampled_examples.json \
  --output-js /Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-2026-05-15-v2/sampled_examples.js
```

The sampler keeps at most 32 examples per `corpus view + threshold + stem`.
If fewer than 32 qualifying games exist, all available examples are emitted.
Sampling is source-stratified: each source PGN keeps a deterministic reservoir,
then the final display sample is drawn round-robin across eligible sources so
large recent PGNs do not dominate every row.

The frontend references `sampled_examples.js` as a sidecar. This keeps the
initial page small and works well for static hosting such as GitHub Pages.

## Sankey Transitions

`build-fce-tablebase` now also writes a separate page and data sidecar:

```text
sankey.html
fce-sankey.js
sankey.js
```

The Sankey page is deliberately separate from the main statistics table. A
link counts a game-level consecutive transition from one FCE ending stem to the
next first-marker stage in the same game, after applying the selected corpus
and half-move threshold. Different endings that first appear on the same ply
are treated as co-present; no artificial order is inserted between same-ply
markers. Auxiliary rows such as pawnless and connected-pawn endings are kept as
separate nodes. Hovering a link highlights that transition and its endpoints;
hovering a node highlights its incoming and outgoing transitions.

If you already have `evaluations.sqlite3` and only need to regenerate the
Sankey sidecar, run:

```bash
OUT_DIR=/Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-knbpawns-20260516-223833

reti-site/target/release/reti-site sankey-js \
  --sqlite-db "$OUT_DIR/evaluations.sqlite3" \
  --output-js "$OUT_DIR/sankey.js" \
  --thresholds 1,2,5,10,20
```

The first run against an older SQLite DB may create a narrow covering index for
the Sankey export. Fresh builds create that index during the normal SQLite
indexing phase, while the DB is still in the configured work directory.

## Opening Distributions

The opening page is separate from the main statistics table:

```text
openings.html
fce-openings.js
openings.js
openings/
```

It shows one ECO base code at a time. The source-game denominator for
`Opening corpus %` comes from `source-totals`; the ending numerator comes from
the annotated marker PGNs. The page intentionally omits tablebase columns and
examples, because the goal is to compare the distribution of endings reached
from a selected opening. The table can be sorted, and the same data can be
shown as a compact bar chart.

If `opening_counts.json` already exists and only the browser payload needs to
be regenerated, run:

```bash
OUT_DIR=/Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-knbpawns-20260516-223833

reti-site/target/release/reti-site openings-js \
  --opening-counts-json "$OUT_DIR/opening_counts.json" \
  --source-totals-json /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
  --opening-catalog-csv data/openings/lumbras_eco_codes.csv \
  --output-js "$OUT_DIR/openings.js"
```

## Editing the Frontend

The frontend is deliberately split from the Rust code:

```text
reti-site/static/index.html
reti-site/static/sankey.html
reti-site/static/openings.html
reti-site/static/fce.css
reti-site/static/fce-app.js
reti-site/static/fce-sankey.js
reti-site/static/fce-openings.js
```

The Rust pipeline writes data files that those static assets import:

```text
snapshot.js
sankey.js
sampled_examples.js
sampled_examples/
openings.js
openings/
```

For copy, layout, CSS, or table-interaction edits, change the files under
`reti-site/static/` and rerun `render-snapshot` with the existing compiled
binary. This refreshes `index.html`, `sankey.html`, `openings.html`, `fce.css`,
`fce-app.js`, `fce-sankey.js`, `fce-openings.js`, and `snapshot.js`. No Rust
rebuild is needed:

```bash
OUT_DIR=/Volumes/2025archive/FCE-table/eval-snapshots/fce-lumbras-all-tablebase-knbpawns-20260516-223833

reti-site/target/release/reti-site render-snapshot \
  --snapshot-json "$OUT_DIR/snapshot.json" \
  --output-html "$OUT_DIR/index.html"
```

The main article prose and references can be edited in Markdown instead of raw
HTML:

```text
reti-site/content/index.md
```

After editing it, update the static page template:

```bash
python3 scripts/render_fce_article_markdown.py
```

Then rerun `render-snapshot` as above. The Markdown renderer only updates the
article copy, table explainer bullets, results/discussion copy, transition
explainer, conclusion, title/byline, and references; it does not touch the
interactive table or Sankey markup.

For the fastest local iteration, you can also edit the generated
`index.html`, `sankey.html`, `openings.html`, `fce.css`, `fce-app.js`,
`fce-sankey.js`, or `fce-openings.js` directly in the output directory and
refresh the browser. Those edits are not durable unless copied back to
`reti-site/static/`.

## Opening Catalog Scrape

Lumbra's PGNs use extended ECO tags such as `A00q`. The matching reference page
can be scraped once into a generated CSV for opening-distribution labels:

```bash
.venv/bin/python scripts/scrape_lumbras_eco_codes.py \
  --output data/openings/lumbras_eco_codes.csv
```

The generated CSV has one row per opening line:

```text
row_number,eco,eco_base,eco_group,name,moves,source_url
```

`eco` preserves the raw extended code, `eco_base` keeps the standard A00-E99
prefix, and `eco_group` is the A-E family. The repository currently ignores
`data/` and `*.csv`, so this scrape remains a local generated artifact unless
we explicitly decide to publish or vendor the source data.

`openings-js` reads `data/openings/lumbras_eco_codes.csv` for display
labels/autocomplete names. The exact denominator data comes from source PGN
`ECO` tags normalized to ECO base, not from the scraped catalog. Override or
disable the catalog with:

```bash
reti-site/target/release/reti-site openings-js \
  --opening-counts-json "$OUT_DIR/opening_counts.json" \
  --source-totals-json /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
  --opening-catalog-csv data/openings/lumbras_eco_codes.csv \
  --output-js "$OUT_DIR/openings.js"

reti-site/target/release/reti-site openings-js \
  --opening-counts-json "$OUT_DIR/opening_counts.json" \
  --source-totals-json /Volumes/2025archive/FCE-table/source-totals/lumbras-source-totals-2026-05-15.json \
  --no-opening-catalog \
  --output-js "$OUT_DIR/openings.js"
```

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
snapshot.js
sankey.js
manifest.json
summary_by_ending.csv
tablebase_wdl_by_view_threshold.csv
index.html
sankey.html
openings.html
fce.css
fce-app.js
fce-sankey.js
fce-openings.js
sampled_examples.js
sampled_examples/
opening_counts.json
openings.js
openings/
```

`evaluations.sqlite3` is the reusable preprocessing artifact. `snapshot.json`,
`snapshot.js`, `sankey.js`, `openings.js`, `openings/`, the CSVs, and the
static site files are derived artifacts. For GitHub Pages, publish
`index.html`, `sankey.html`, `openings.html`, `fce.css`, `fce-app.js`,
`fce-sankey.js`, `fce-openings.js`, `snapshot.js`, `sankey.js`,
`sampled_examples.js`, `sampled_examples/`, `openings.js`, and `openings/`;
do not publish `evaluations.sqlite3` or the raw `opening_counts.json`.

## Idempotency

If `manifest.json`, `snapshot.json`, `evaluations.sqlite3`, the static frontend
files, and the sampled-example sidecars already exist and the manifest matches
the current inputs/settings, the command exits as up to date.

If the output directory exists with a different manifest, the build fails unless
`--force` is supplied or a new `--output-dir` is chosen.

## Module Layout

- `cli.rs`: command parsing and validation.
- `source.rs`: `summary.csv` and source-total validation.
- `catalog.rs`: FCE canonical rows and auxiliary subrows.
- `pipeline.rs`: build orchestration and atomic output install.
- `aggregate.rs`: SQL indexes, incidence aggregates, WDL/result aggregates.
- `csv_export.rs`: human-readable CSV exports.
- `render.rs`: copies static frontend assets and writes `snapshot.js`.
- `sankey.rs`: derives consecutive ending-transition data and writes
  `sankey.js`.
- `opening_page.rs`: converts raw opening aggregates into lazy browser chunks.
- `openings.rs`: loads the scraped ECO catalog for display labels.
- `static/`: hand-editable HTML, CSS, and browser JavaScript.
- `manifest.rs`: input signatures and build fingerprinting.
- `sqlite.rs`: small SQLite FFI wrapper used by aggregation.

The marker extraction and Syzygy probing are Rust subcommands in
`native/pgn-utils`:

- `fce-combined-markers`
- `fce-combined-openings`
- `fce-syzygy-eval`

`reti-site` calls those Rust tools and then performs the remaining aggregation
and artifact writing in Rust.
