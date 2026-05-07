# Export `{CQL}` Positions to CSV

`src/reti/export_cql_positions.py` scans PGNs that already contain move comments
such as `{CQL}` and appends one CSV row per marked position.

The exporter treats a marker comment as applying to the position after the move
it follows. For directory input, `.pgn` files are discovered recursively.

## Usage

```bash
python src/reti/export_cql_positions.py \
  --pgn PGN_INPUT \
  --output-csv OUTPUT_CSV \
  --syzygy-dir /path/to/syzygy \
  --stockfish-bin /path/to/stockfish
```

Required flags:

- `--pgn PGN_INPUT`: a `.pgn` file or a directory containing `.pgn` files
- `--output-csv OUTPUT_CSV`: CSV file to append rows to

Optional flags:

- `--marker-text TEXT`: comment text to match exactly after stripping whitespace;
  defaults to `CQL`
- `--syzygy-dir DIR`: local Syzygy directory; repeat the flag for multiple roots
- `--stockfish-bin PATH`: local Stockfish binary path, or an executable name on
  `PATH`
- `--sf-time-seconds N`: Stockfish time budget per position; defaults to `1.0`
- `--sf-threads N`: Stockfish thread count; defaults to `1`
- `--draw-threshold-cp N`: classify Stockfish scores within `N` centipawns of
  zero as draws; defaults to `30`

## Evaluation policy

- If a marked position has `5` pieces or fewer, including both kings, the
  exporter probes Syzygy and records `eval_source=tablebase`.
- If a marked position has more than `5` pieces, the exporter runs Stockfish
  once for that position and records `eval_source=stockfish`.
- For Stockfish positions, the CSV stores raw White-POV score fields
  (`sf_cp_white` or `sf_mate_white`) and a derived `winning_side`.
- `winning_side` is one of `white`, `black`, `draw`, or `unknown`.

If an evaluation cannot be completed, the exporter still writes a row with
`eval_status` and `error_message`, keeps going, and exits non-zero at the end.

## Output schema

The exporter writes these columns, in this exact order:

```text
source_pgn, ending, game_index, event, site, date, round, white, black, result,
ply_index, fullmove_number, move_san, move_uci, fen, side_to_move, piece_count,
marker_text, eval_source, winning_side, tb_wdl, tb_dtz, sf_cp_white,
sf_mate_white, sf_time_seconds, draw_threshold_cp, eval_status, error_message
```

Append behavior:

- if the CSV does not exist or is empty, the exporter writes the header once
- if the CSV already exists, the header must match exactly or the run aborts
  before processing any PGNs

`ending` is derived from the source PGN filename stem. For directory input,
`source_pgn` is written relative to the input directory.

## Example workflow

Run CQL first to generate annotated PGNs:

```bash
python src/reti/analyse_cql.py \
  --pgn path/to/pgn_dir \
  --cql-bin path/to/cql \
  --scripts cql-files/FCE/table \
  -o output/fce-table
```

Then export the marked positions:

```bash
python src/reti/export_cql_positions.py \
  --pgn output/fce-table \
  --output-csv output/fce-table/positions.csv \
  --syzygy-dir /path/to/syzygy \
  --stockfish-bin /path/to/stockfish
```

Do not run `pgn_cli.py` on the annotated PGNs before this step. The repair
workflow is intentionally CQL-safe and removes comments, so it would also remove
the `{CQL}` markers you want to export.
