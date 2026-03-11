# Repair PGN In Place

If CQL aborts on a PGN because of control bytes, invalid UTF-8, malformed
comments, or other parser-hostile formatting, use `src/reti/repair_pgn.py`
once before running the normal CQL analysis.

The repair step:

1. strips UTF-8 BOMs, invalid UTF-8 bytes, and unexpected control characters
2. reparses the PGN game-by-game with `python-chess`
3. rewrites the file in CQL-safe PGN form: headers plus mainline only
4. optionally smoke-tests the repaired temp file with CQL before replacing the
   original file

This is intentionally a one-time destructive normalization step. By default it
keeps a backup of the original file next to the repaired PGN.

## Command

```bash
python src/reti/repair_pgn.py --pgn PGN_INPUT [--cql-bin CQL_BINARY]
```

Arguments:

- `--pgn PGN_INPUT`: a `.pgn` file or a directory containing `.pgn` files
- `--cql-bin CQL_BINARY`: optional path to the `cql` executable, or an
  executable name on `PATH`

Optional flags:

- `--backup-suffix SUFFIX`: suffix for the saved original file, default `.bak`
- `--no-backup`: do not keep a backup copy
- `--overwrite-backup`: allow overwriting an existing backup file
- `--cql-lineincrement N`: when `--cql-bin` is supplied, ask CQL to print
  progress every `N` games during the smoke test, default `1000`

## Recommended usage

For a one-off repair of a large database that you want CQL to accept:

```bash
python src/reti/repair_pgn.py \
  --pgn ~/Downloads/LumbrasGigaBase_OTB_1900-1949.pgn \
  --cql-bin ./bins/cql6-2/cql
```

That does not replace the original file until the repaired temp output has
already passed a cheap `cql() check` smoke test. On large files, that final
smoke test can still take a while because CQL must read the whole repaired PGN.
The script now lets CQL print its own progress during that step.

If you do not want to keep a backup copy:

```bash
python src/reti/repair_pgn.py \
  --pgn ~/Downloads/LumbrasGigaBase_OTB_1900-1949.pgn \
  --cql-bin ./bins/cql6-2/cql \
  --no-backup
```

If you want to repair a whole directory of PGNs:

```bash
python src/reti/repair_pgn.py \
  --pgn path/to/pgn_dir \
  --cql-bin ./bins/cql6-2/cql
```

## What changes

The rewritten PGN is intentionally normalized, not byte-for-byte preserved.
Typical changes include:

- removal of stray control bytes
- replacement of invalid UTF-8 bytes with `?`
- canonicalized spacing and line breaks
- removal of comments and side variations

The goal is CQL readability and stable downstream processing, not exact textual
preservation.

## When to use this

Use the repair step when:

- direct `cql` runs abort with parser or internal buffer errors
- `analyse_cql.py` reports repeated PGN-specific failures
- you want to normalize a large database once rather than sanitize a temporary
  copy on every analysis run

For normal clean PGNs, you can skip this and run `analyse_cql.py` directly.
If you want the repair to finish without the extra CQL validation pass, omit
`--cql-bin`.
