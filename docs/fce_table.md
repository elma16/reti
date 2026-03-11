# FCE Table Workflow

The broad `cql-files/FCE/` directory contains more than the subset used for the
frequency table in *Fundamental Chess Endings*. The public-facing workflow in
this repo is:

1. Build the curated `cql-files/FCE/table/` subset once.
2. Run `analyse_cql.py` over your PGN file or PGN directory with that subset.
3. Render the final markdown table from `summary.csv`.

## 1. Build the curated subset

```bash
python scripts/build_fce_table_subset.py
```

This creates `cql-files/FCE/table/` and writes
`cql-files/FCE/table/manifest.csv`.

Most table scripts are copied by exact filename. A few are normalized from the
broader corpus to match the 30-row markdown table in [README.md](../README.md):

- `2-1P.cql <- 2-AP.cql`
- `5-0BN.cql <- 5-0Bn.cql`
- `6-1-0RP.cql <- 6-1Rp.cql`
- `6-2-0Rr.cql <- 6-2-0RPrp.cql`
- `7-1RN.cql <- 7-1Rn.cql`
- `7-2RB.cql <- 7-2Rb.cql`
- `8-1RNr.cql <- 8-1RNrPp.cql`
- `8-2RBr.cql <- 8-2RBrPp.cql`
- `9-3QPq.cql <- 9-21QPq.cql`
- `10-2Qr.cql <- 10-2QrPp.cql`
- `10-7-1Qbrr.cql <- 10-7-1QbrrPp.cql`

The builder uses explicit source overrides first, then exact matching, then
fuzzy matching only as a fallback. The manifest records how each output file
was resolved.

## 2. Run the batch analysis

If your PGNs live in a directory:

```bash
python src/reti/analyse_cql.py \
  --pgn path/to/pgn_dir \
  --cql-bin path/to/cql \
  --scripts cql-files/FCE/table \
  --jobs 1 \
  -o output/fce-table
```

This writes:

- one output PGN per `(input PGN, table CQL)` pair
- `output/fce-table/summary.csv`

## 3. Render the markdown table

```bash
python scripts/render_fce_table_from_summary.py \
  output/fce-table/summary.csv \
  path/to/pgn_dir
```

That prints a markdown table with:

- the canonical FCE table ordering
- total matched games per table script
- percentage of the original PGN corpus

## Notes

- `analyse_cql.py` accepts either a single PGN or a directory of PGNs.
- `--jobs 1` is now the default and is a sensible choice for the FCE table
  workflow because CQL itself is multithreaded.
- If you want process-level parallelism across scripts, raise `--jobs` and
  consider `--cql-threads 1`.
- The rendered percentages use the total number of games across the original
  PGN input, not the number of matched games.
- Rebuild `cql-files/FCE/table/` whenever you make changes to the broader
  `cql-files/FCE/` corpus and want the curated subset to stay in sync.
