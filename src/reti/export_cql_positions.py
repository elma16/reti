"""CLI orchestration for exporting ``{CQL}``-marked PGN positions to CSV.

The position-evaluation backends and the CSV schema moved to
:mod:`reti.evaluation`. This module is the user-facing CLI: it parses
arguments, walks PGN files, dispatches each marker to a
:class:`PositionEvaluator`, and writes one CSV row per marker.

The names ``open_tablebase_from_directories`` and ``StockfishSession`` are
imported here so test fixtures can monkey-patch them at this module level.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine
import chess.syzygy

from reti.annotated_pgn import (
    AnnotatedPosition,
    discover_pgn_files,
    format_pgn_display_path,
    parse_annotated_pgn,
    side_name,
)
from reti.common.progress import (
    format_progress_label,
    make_terminal_safe,
    progress_write,
)
from reti.common.subprocess_helpers import resolve_executable
from reti.evaluation.backends import (
    PositionEvaluator,
    RoutingEvaluator,
    StockfishEvaluator,
    StockfishSession,
    TablebaseEvaluator,
    evaluate_with_tablebase,
    open_tablebase_from_directories,
)
from reti.evaluation.csv_schema import (
    CSV_COLUMNS,
    EvaluationResult,
    build_file_error_row,
    build_marker_row,
    build_parse_error_row,
    classify_side_to_move_wdl,
    classify_stockfish_winner,
    empty_row,
    prepare_output_csv,
)
from tqdm import tqdm as tqdm_progress

__all__ = [
    "CSV_COLUMNS",
    "EvaluationResult",
    "ExportStats",
    "PositionEvaluator",
    "RoutingEvaluator",
    "StockfishEvaluator",
    "StockfishSession",
    "TablebaseEvaluator",
    "build_file_error_row",
    "build_marker_row",
    "build_parse_error_row",
    "classify_side_to_move_wdl",
    "classify_stockfish_winner",
    "empty_row",
    "evaluate_position",
    "evaluate_with_tablebase",
    "export_cql_positions",
    "format_progress_label",
    "main",
    "make_terminal_safe",
    "open_tablebase_from_directories",
    "parse_args",
    "prepare_output_csv",
    "process_pgn_file",
    "progress_write",
    "resolve_executable",
]


@dataclass(frozen=True)
class ExportStats:
    marker_rows: int = 0
    failures: int = 0
    parse_error_rows: int = 0


def evaluate_position(
    board: chess.Board,
    *,
    tablebase: chess.syzygy.Tablebase | None,
    stockfish: StockfishSession,
    sf_time_seconds: float,
    draw_threshold_cp: int,
) -> EvaluationResult:
    """Legacy dispatcher: ≤5 pieces uses tablebase, larger positions Stockfish.

    New code should compose a :class:`RoutingEvaluator` directly. This wrapper
    is preserved so the in-tree CLI stays drop-in compatible.
    """
    piece_count = len(board.piece_map())
    if piece_count <= 5:
        return evaluate_with_tablebase(board, tablebase)

    return stockfish.analyse(
        board,
        sf_time_seconds=sf_time_seconds,
        draw_threshold_cp=draw_threshold_cp,
    )


def process_pgn_file(
    *,
    pgn_path: Path,
    source_pgn: str,
    marker_text: str,
    writer: csv.DictWriter,
    tablebase: chess.syzygy.Tablebase | None,
    stockfish: StockfishSession,
    sf_time_seconds: float,
    draw_threshold_cp: int,
) -> ExportStats:
    stats = ExportStats()
    ending = pgn_path.stem

    try:
        parsed_games = parse_annotated_pgn(pgn_path, marker_text=marker_text)
        for parsed_game in parsed_games:
            if parsed_game.parse_errors:
                writer.writerow(
                    build_parse_error_row(
                        source_pgn=source_pgn,
                        ending=ending,
                        marker_text=marker_text,
                        game_index=parsed_game.game_index,
                        headers=parsed_game.headers,
                        error_message=" | ".join(parsed_game.parse_errors),
                    )
                )
                stats = ExportStats(
                    marker_rows=stats.marker_rows,
                    failures=stats.failures + 1,
                    parse_error_rows=stats.parse_error_rows + 1,
                )

            for position in parsed_game.positions:
                evaluation = evaluate_position(
                    chess.Board(position.fen),
                    tablebase=tablebase,
                    stockfish=stockfish,
                    sf_time_seconds=sf_time_seconds,
                    draw_threshold_cp=draw_threshold_cp,
                )
                writer.writerow(
                    build_marker_row(
                        source_pgn=source_pgn,
                        ending=ending,
                        game_index=parsed_game.game_index,
                        headers=parsed_game.headers,
                        marker_text=marker_text,
                        position=position,
                        evaluation=evaluation,
                    )
                )
                stats = ExportStats(
                    marker_rows=stats.marker_rows + 1,
                    failures=stats.failures
                    + (0 if evaluation.eval_status == "ok" else 1),
                    parse_error_rows=stats.parse_error_rows,
                )
    except Exception as exc:
        writer.writerow(
            build_file_error_row(
                source_pgn=source_pgn,
                ending=ending,
                marker_text=marker_text,
                error_message=str(exc),
            )
        )
        return ExportStats(
            marker_rows=stats.marker_rows,
            failures=stats.failures + 1,
            parse_error_rows=stats.parse_error_rows,
        )

    return stats


def export_cql_positions(
    *,
    pgn_location: str,
    output_csv: str,
    marker_text: str,
    syzygy_dirs: list[str],
    stockfish_bin: str | None,
    sf_time_seconds: float,
    sf_threads: int,
    draw_threshold_cp: int,
) -> int:
    discovery = discover_pgn_files(pgn_location)
    if discovery is None:
        return 1
    pgn_files, pgn_root = discovery

    output_csv_path = Path(output_csv).expanduser()
    try:
        write_header = prepare_output_csv(output_csv_path)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    tablebase, tablebase_error = open_tablebase_from_directories(syzygy_dirs)
    if tablebase_error:
        progress_write(f"Tablebase setup warning: {tablebase_error}")
    stockfish = StockfishSession(stockfish_bin, sf_threads)

    total_rows = 0
    total_failures = 0
    total_parse_error_rows = 0

    print(f"Exporting {len(pgn_files)} PGN file(s) to {output_csv_path}...")
    try:
        with output_csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            if write_header:
                writer.writeheader()

            progress = tqdm_progress(
                pgn_files,
                total=len(pgn_files),
                desc="CQL export",
                unit="file",
                dynamic_ncols=sys.stderr.isatty(),
                file=sys.stderr,
            )
            for pgn_path in progress:
                display_path = format_pgn_display_path(pgn_path, pgn_root)
                progress.set_postfix_str(format_progress_label(display_path))

                stats = process_pgn_file(
                    pgn_path=pgn_path,
                    source_pgn=display_path,
                    marker_text=marker_text,
                    writer=writer,
                    tablebase=tablebase,
                    stockfish=stockfish,
                    sf_time_seconds=sf_time_seconds,
                    draw_threshold_cp=draw_threshold_cp,
                )
                total_rows += stats.marker_rows
                total_failures += stats.failures
                total_parse_error_rows += stats.parse_error_rows
                handle.flush()
        progress.close()
    finally:
        stockfish.close()
        if tablebase is not None:
            tablebase.close()

    print("\n--- Export Summary ---")
    print(f"Files: {len(pgn_files)}")
    print(f"Marker rows written: {total_rows}")
    print(f"Parse error rows: {total_parse_error_rows}")
    print(f"Failures: {total_failures}")
    print(f"CSV: {output_csv_path}")
    print("----------------------")

    return 1 if total_failures else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan PGNs containing {CQL}-style marker comments and append one "
            "evaluated CSV row per marked position."
        )
    )
    parser.add_argument(
        "--pgn",
        dest="pgn_location",
        required=True,
        help="Path to a .pgn file or a directory containing .pgn files.",
    )
    parser.add_argument(
        "--output-csv",
        dest="output_csv",
        required=True,
        help="CSV file to append rows to.",
    )
    parser.add_argument(
        "--marker-text",
        dest="marker_text",
        default="CQL",
        help="Comment text that marks a position after a move. Defaults to CQL.",
    )
    parser.add_argument(
        "--syzygy-dir",
        dest="syzygy_dirs",
        action="append",
        default=[],
        help="Path to a local Syzygy tablebase directory. Repeat for multiple roots.",
    )
    parser.add_argument(
        "--stockfish-bin",
        dest="stockfish_bin",
        default=None,
        help=(
            "Path to the Stockfish executable, or an executable name on PATH. "
            "Required in practice when a marked position has more than 5 pieces."
        ),
    )
    parser.add_argument(
        "--sf-time-seconds",
        dest="sf_time_seconds",
        type=float,
        default=1.0,
        help="Stockfish analysis time per position in seconds. Defaults to 1.0.",
    )
    parser.add_argument(
        "--sf-threads",
        dest="sf_threads",
        type=int,
        default=1,
        help="Stockfish thread count. Defaults to 1.",
    )
    parser.add_argument(
        "--draw-threshold-cp",
        dest="draw_threshold_cp",
        type=int,
        default=30,
        help=(
            "Classify Stockfish scores within this centipawn band as draws. "
            "Defaults to 30."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.marker_text.strip():
        print("Error: --marker-text must contain at least one non-whitespace character.")
        return 1
    if args.sf_time_seconds <= 0:
        print("Error: --sf-time-seconds must be greater than 0.")
        return 1
    if args.sf_threads < 1:
        print("Error: --sf-threads must be at least 1.")
        return 1
    if args.draw_threshold_cp < 0:
        print("Error: --draw-threshold-cp must be at least 0.")
        return 1

    return export_cql_positions(
        pgn_location=args.pgn_location,
        output_csv=args.output_csv,
        marker_text=args.marker_text.strip(),
        syzygy_dirs=args.syzygy_dirs,
        stockfish_bin=args.stockfish_bin,
        sf_time_seconds=args.sf_time_seconds,
        sf_threads=args.sf_threads,
        draw_threshold_cp=args.draw_threshold_cp,
    )


if __name__ == "__main__":
    raise SystemExit(main())
