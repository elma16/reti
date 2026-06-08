# mates-site

`mates-site` builds a static dashboard for checkmate-pattern incidence runs.

The expected input is an `analyse_cql.py --output-mode single` run directory
like `outmatesSORTED`: a `summary.csv` plus one retained merged PGN per source
PGN. The builder uses `summary.csv` for the known pattern list and streamed PGN
comments for unique-game incidence and co-occurrence.

From the repository root:

```bash
cargo build --release --manifest-path mates-site/Cargo.toml

mates-site/target/release/mates-site build \
  --run-dir outmatesSORTED \
  --output-dir out/mates-site \
  --title "Checkmate patterns in Lumbra's Gigabase"
```

Open `out/mates-site/index.html` in a browser. No dev server is required.
