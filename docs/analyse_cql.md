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
python src/reti/analyse_cql.py --pgn PGN_INPUT --cql-bin CQL_BINARY --scripts CQL_INPUT --jobs 1 -o OUTPUT_DIR
```

Arguments:

- `--pgn PGN_INPUT`: a `.pgn` file or a directory containing `.pgn` files
- `--cql-bin CQL_BINARY`: a path to the `cql` executable, or an executable name on `PATH`
- `--scripts CQL_INPUT`: a `.cql` file or a directory containing `.cql` files
- `--jobs JOBS`: number of CQL subprocesses to run in parallel, default `1`
- `--cql-threads THREADS`: thread count per CQL process, or `auto`
- `-o OUTPUT_DIR`: directory where result PGNs and `summary.csv` are written

Optional flags:

- `--keep-output`: when `-o` is omitted, keep the temporary output directory
- `--skip-pgn-preflight`: skip the initial PGN validation pass
- `--smoke-test-pgns`: run one cheap CQL smoke query per PGN during preflight
- `--strict-pgn-parse`: run a full `python-chess` parse during preflight

Legacy positional syntax still works for now, but the explicit flag form above
is the intended interface.

Threading model:

- By default the runner uses `--jobs 1`, so it runs scripts sequentially and
  lets CQL choose its own internal thread count.
- If you raise `--jobs` above `1`, the runner automatically treats
  `--cql-threads auto` as `1` to avoid oversubscribing the machine.
- If you want full manual control, pass both `--jobs` and `--cql-threads`
  explicitly.

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

Before the full matrix run, the runner does a PGN preflight by default:

- it rejects files with no `[Event ` tags
- if a PGN contains a UTF-8 BOM, invalid UTF-8, NUL bytes, or other control
  characters, it creates a sanitized temporary runtime copy and leaves the
  original file untouched
- by default it does not run a full `python-chess` parse or a CQL smoke test,
  so startup stays cheap on large databases
- `--strict-pgn-parse` enables the full `python-chess` parse check
- `--smoke-test-pgns` enables one cheap CQL smoke query per PGN so CQL-level
  crashes caused by the PGN itself show up before the `PGN x CQL`
  cross-product starts

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
  --pgn tests_cql/fixtures/db.pgn \
  --cql-bin path/to/cql \
  --scripts cql-files/mates/ismate.cql \
  --jobs 1 \
  -o output/ismate-demo
```

Run one PGN against a whole CQL directory:

```bash
python src/reti/analyse_cql.py \
  --pgn tests_cql/fixtures/db.pgn \
  --cql-bin path/to/cql \
  --scripts cql-files/mates \
  --jobs 1 \
  -o output/mates-on-db
```

Run a directory of PGNs against one CQL:

```bash
python src/reti/analyse_cql.py \
  --pgn tests_cql/fixtures \
  --cql-bin path/to/cql \
  --scripts cql-files/mates/ismate.cql \
  --jobs 1 \
  -o output/ismate-on-fixtures
```

Run a directory of PGNs against a directory of CQL scripts:

```bash
python src/reti/analyse_cql.py \
  --pgn tests_cql/fixtures \
  --cql-bin path/to/cql \
  --scripts cql-files/FCE \
  --jobs 1 \
  -o output/fce-batch
```

Use a temporary output directory and keep it:

```bash
python src/reti/analyse_cql.py \
  --pgn tests_cql/fixtures/db.pgn \
  --cql-bin path/to/cql \
  --scripts cql-files/mates \
  --jobs 1 \
  --keep-output
```

## Practical notes

- The runner does not delete or clear an explicit `OUTPUT_DIR` for you.
- If you omit `-o`, a temporary output directory is created and deleted unless
  you pass `--keep-output`.
- Large matrix runs can generate many PGN files quickly; prefer a dedicated
  output directory per run.
- The runner shows a `tqdm` progress bar for both the PGN preflight pass and
  the overall CQL job matrix.
- The default execution model is sequential at the process level: `--jobs 1`.
- If you raise `--jobs`, the runner constrains each CQL process to one thread
  unless you explicitly override `--cql-threads`.
- The script counts matched games by scanning the output PGN for `[Event `
  tags. That is fast and sufficient for summary reporting.
- If preflight reports that it is using a sanitized temporary copy, that copy
  exists only for the current run; the source PGN on disk is not modified.
- If you want to normalize a problematic PGN once and then reuse that repaired
  file for future analyses, run `src/reti/pgn_cli.py` first.
- If you want to rerun the same batch and compare outputs, use a fresh output
  directory rather than sharing one between experiments.
- Negative subprocess return codes mean CQL was terminated by a signal. For
  example, `-6` is reported as `SIGABRT`.
- If you keep a private local CQL binary under `bins/`, you can pass that path
  here as well. `bins/` is ignored by Git; the public repo does not rely on
  committed binaries.
