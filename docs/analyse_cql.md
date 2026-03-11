# Batch CQL Runner

`src/reti/analyse_cql.py` runs a full cross-product of PGN inputs and CQL
scripts:

- one PGN file x one CQL script
- one PGN file x a directory of CQL scripts
- a directory of PGNs x one CQL script
- a directory of PGNs x a directory of CQL scripts

If you give it directories, it scans them recursively for `.pgn` and `.cql`
files.

## Command

```bash
python src/reti/analyse_cql.py PGN_INPUT CQL_BINARY CQL_INPUT -o OUTPUT_DIR
```

Arguments:

- `PGN_INPUT`: a `.pgn` file or a directory containing `.pgn` files
- `CQL_BINARY`: a path to the `cql` executable, or an executable name on `PATH`
- `CQL_INPUT`: a `.cql` file or a directory containing `.cql` files
- `-o OUTPUT_DIR`: directory where result PGNs and `summary.csv` are written

Optional flags:

- `--keep-output`: when `-o` is omitted, keep the temporary output directory

## Discovery rules

- If `PGN_INPUT` is a file, only that file is used.
- If `PGN_INPUT` is a directory, every `.pgn` below it is used recursively.
- If `CQL_INPUT` is a file, only that script is used.
- If `CQL_INPUT` is a directory, every `.cql` below it is used recursively.
- File matching is case-insensitive on the final suffix.
- If a directory contains no matching files, the command exits with status `1`.

## Output layout

The runner writes one output PGN per `(input PGN, input CQL)` pair.

The output path is deterministic:

```text
OUTPUT_DIR/<relative-pgn-path-without-.pgn>/<relative-cql-path-without-.cql>.pgn
```

Examples:

- input PGN `games/db.pgn`
- input CQL `cql-files/mates/ismate.cql`
- output PGN `results/db/mates/ismate.pgn`

- input PGN `pgns/club/week1.pgn`
- input CQL `cql-files/FCE/8-2RBr.cql`
- output PGN `results/club/week1/FCE/8-2RBr.pgn`

This layout avoids filename collisions when:

- two PGNs share the same filename in different directories
- two CQL scripts share the same filename in different directories
- you rerun the same job matrix into the same output directory

If an output file already exists, the runner overwrites it.

## Summary file

The runner also writes `OUTPUT_DIR/summary.csv`.

Columns:

- `pgn`: input PGN path relative to the PGN root you supplied
- `cql`: input CQL path relative to the CQL root you supplied
- `output_pgn`: output PGN path relative to `OUTPUT_DIR`
- `status`: `ok` or `error`
- `match_count`: number of matched games for successful jobs
- `returncode`: process exit code from `cql`

This is the easiest way to inspect a large batch run without opening every
result PGN.

## Console behavior

For each job, the runner prints:

- the current job number
- the PGN/CQL pair being run
- the output path
- either the matched-game count or the failure return code

At the end it prints totals for successful and failed jobs.

Exit codes:

- `0`: every job completed successfully
- `1`: invalid inputs, missing files, or at least one failed CQL run

## Examples

Run one PGN against one CQL:

```bash
python src/reti/analyse_cql.py \
  tests_cql/fixtures/db.pgn \
  bins/cql6-2/cql \
  cql-files/mates/ismate.cql \
  -o output/ismate-demo
```

Run one PGN against a whole CQL directory:

```bash
python src/reti/analyse_cql.py \
  tests_cql/fixtures/db.pgn \
  bins/cql6-2/cql \
  cql-files/mates \
  -o output/mates-on-db
```

Run a directory of PGNs against one CQL:

```bash
python src/reti/analyse_cql.py \
  tests_cql/fixtures \
  bins/cql6-2/cql \
  cql-files/mates/ismate.cql \
  -o output/ismate-on-fixtures
```

Run a directory of PGNs against a directory of CQL scripts:

```bash
python src/reti/analyse_cql.py \
  tests_cql/fixtures \
  bins/cql6-2/cql \
  cql-files/FCE \
  -o output/fce-batch
```

Use a temporary output directory and keep it:

```bash
python src/reti/analyse_cql.py \
  tests_cql/fixtures/db.pgn \
  bins/cql6-2/cql \
  cql-files/mates \
  --keep-output
```

## Practical notes

- The runner does not delete or clear an explicit `OUTPUT_DIR` for you.
- If you omit `-o`, a temporary output directory is created and deleted unless
  you pass `--keep-output`.
- Large matrix runs can generate many PGN files quickly; prefer a dedicated
  output directory per run.
- The script counts matched games by scanning the output PGN for `[Event `
  tags. That is fast and sufficient for summary reporting.
- If you want to rerun the same batch and compare outputs, use a fresh output
  directory rather than sharing one between experiments.
