from __future__ import annotations

import argparse
import csv
import shutil
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
from tqdm import tqdm as tqdm_progress

CSV_COLUMNS = [
    "source_pgn",
    "ending",
    "game_index",
    "event",
    "site",
    "date",
    "round",
    "white",
    "black",
    "result",
    "ply_index",
    "fullmove_number",
    "move_san",
    "move_uci",
    "fen",
    "side_to_move",
    "piece_count",
    "marker_text",
    "eval_source",
    "winning_side",
    "tb_wdl",
    "tb_dtz",
    "sf_cp_white",
    "sf_mate_white",
    "sf_time_seconds",
    "draw_threshold_cp",
    "eval_status",
    "error_message",
]


def progress_write(message: str) -> None:
    tqdm_progress.write(make_terminal_safe(message))


def make_terminal_safe(text: str) -> str:
    safe_parts: list[str] = []
    for char in text:
        codepoint = ord(char)
        if char in "\n\r\t":
            safe_parts.append(char)
        elif codepoint < 32 or codepoint == 127:
            safe_parts.append(f"\\x{codepoint:02x}")
        else:
            safe_parts.append(char)
    return "".join(safe_parts)


def format_progress_label(text: str, *, max_length: int = 80) -> str:
    safe = make_terminal_safe(text).replace("\n", " ").replace("\r", " ").replace(
        "\t", " "
    )
    if len(safe) <= max_length:
        return safe
    head = max(10, max_length // 2 - 2)
    tail = max(10, max_length - head - 3)
    return f"{safe[:head]}...{safe[-tail:]}"


@dataclass(frozen=True)
class ExportStats:
    marker_rows: int = 0
    failures: int = 0
    parse_error_rows: int = 0


@dataclass(frozen=True)
class EvaluationResult:
    eval_source: str
    winning_side: str
    tb_wdl: int | None = None
    tb_dtz: int | None = None
    sf_cp_white: int | None = None
    sf_mate_white: int | None = None
    sf_time_seconds: float | None = None
    draw_threshold_cp: int | None = None
    eval_status: str = "ok"
    error_message: str = ""
def resolve_executable(binary: str) -> Path | None:
    candidate = Path(binary).expanduser()
    if candidate.is_file():
        return candidate

    on_path = shutil.which(binary)
    if on_path:
        return Path(on_path)

    return None
def classify_side_to_move_wdl(wdl: int, turn: bool) -> str:
    if wdl > 0:
        return side_name(turn)
    if wdl < 0:
        return side_name(not turn)
    return "draw"


def classify_stockfish_winner(
    cp_white: int | None,
    mate_white: int | None,
    draw_threshold_cp: int,
) -> str:
    if mate_white is not None:
        if mate_white > 0:
            return "white"
        if mate_white < 0:
            return "black"
        return "draw"

    if cp_white is None:
        return "unknown"

    if abs(cp_white) <= draw_threshold_cp:
        return "draw"
    return "white" if cp_white > 0 else "black"


def empty_row(
    *,
    source_pgn: str,
    ending: str,
    marker_text: str,
    game_index: int | str = "",
    event: str = "",
    site: str = "",
    date: str = "",
    round_value: str = "",
    white: str = "",
    black: str = "",
    result: str = "",
    ply_index: int | str = "",
    fullmove_number: int | str = "",
    move_san: str = "",
    move_uci: str = "",
    fen: str = "",
    side_to_move_value: str = "",
    piece_count: int | str = "",
    eval_source: str = "",
    winning_side: str = "unknown",
    tb_wdl: int | str = "",
    tb_dtz: int | str = "",
    sf_cp_white: int | str = "",
    sf_mate_white: int | str = "",
    sf_time_seconds: float | str = "",
    draw_threshold_cp: int | str = "",
    eval_status: str = "",
    error_message: str = "",
) -> dict[str, str | int | float]:
    return {
        "source_pgn": source_pgn,
        "ending": ending,
        "game_index": game_index,
        "event": event,
        "site": site,
        "date": date,
        "round": round_value,
        "white": white,
        "black": black,
        "result": result,
        "ply_index": ply_index,
        "fullmove_number": fullmove_number,
        "move_san": move_san,
        "move_uci": move_uci,
        "fen": fen,
        "side_to_move": side_to_move_value,
        "piece_count": piece_count,
        "marker_text": marker_text,
        "eval_source": eval_source,
        "winning_side": winning_side,
        "tb_wdl": tb_wdl,
        "tb_dtz": tb_dtz,
        "sf_cp_white": sf_cp_white,
        "sf_mate_white": sf_mate_white,
        "sf_time_seconds": sf_time_seconds,
        "draw_threshold_cp": draw_threshold_cp,
        "eval_status": eval_status,
        "error_message": error_message,
    }


def prepare_output_csv(output_csv: Path) -> bool:
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not output_csv.exists() or output_csv.stat().st_size == 0:
        return True

    with output_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return True

    if header != CSV_COLUMNS:
        expected = ", ".join(CSV_COLUMNS)
        found = ", ".join(header)
        raise ValueError(
            "Existing CSV header does not match the exporter schema.\n"
            f"Expected: {expected}\n"
            f"Found: {found}"
        )

    return False


def open_tablebase_from_directories(
    syzygy_dirs: list[str],
) -> tuple[chess.syzygy.Tablebase | None, str | None]:
    if not syzygy_dirs:
        return None, None

    expanded_dirs = [Path(directory).expanduser() for directory in syzygy_dirs]
    for directory in expanded_dirs:
        if not directory.is_dir():
            return None, f"Syzygy directory not found: {directory}"

    tablebase = chess.syzygy.open_tablebase(str(expanded_dirs[0]))
    for directory in expanded_dirs[1:]:
        tablebase.add_directory(str(directory))
    return tablebase, None


class StockfishSession:
    def __init__(self, binary: str | None, threads: int) -> None:
        self._binary = binary
        self._threads = threads
        self._engine: chess.engine.SimpleEngine | None = None
        self._init_error: str | None = None

    def _ensure_engine(self) -> chess.engine.SimpleEngine:
        if self._engine is not None:
            return self._engine
        if self._init_error is not None:
            raise RuntimeError(self._init_error)
        if not self._binary:
            self._init_error = (
                "Stockfish is required for positions with more than 5 pieces; "
                "pass --stockfish-bin."
            )
            raise RuntimeError(self._init_error)

        resolved = resolve_executable(self._binary)
        if resolved is None:
            self._init_error = f"Stockfish binary not found: {self._binary}"
            raise RuntimeError(self._init_error)

        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(str(resolved))
            self._engine.configure({"Threads": self._threads})
        except Exception as exc:
            self._init_error = f"Failed to start Stockfish: {exc}"
            raise RuntimeError(self._init_error) from exc
        return self._engine

    def analyse(
        self,
        board: chess.Board,
        *,
        sf_time_seconds: float,
        draw_threshold_cp: int,
    ) -> EvaluationResult:
        try:
            engine = self._ensure_engine()
            info = engine.analyse(board, chess.engine.Limit(time=sf_time_seconds))
            score = info.get("score")
            if score is None:
                raise RuntimeError("Stockfish returned no score.")

            white_score = score.white()
            cp_white = white_score.score()
            mate_white = white_score.mate()
            winning_side = classify_stockfish_winner(
                cp_white, mate_white, draw_threshold_cp
            )
            return EvaluationResult(
                eval_source="stockfish",
                winning_side=winning_side,
                sf_cp_white=cp_white,
                sf_mate_white=mate_white,
                sf_time_seconds=sf_time_seconds,
                draw_threshold_cp=draw_threshold_cp,
                eval_status="ok",
            )
        except Exception as exc:
            return EvaluationResult(
                eval_source="stockfish",
                winning_side="unknown",
                sf_time_seconds=sf_time_seconds,
                draw_threshold_cp=draw_threshold_cp,
                eval_status="stockfish_error",
                error_message=str(exc),
            )

    def close(self) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None


def evaluate_with_tablebase(
    board: chess.Board,
    tablebase: chess.syzygy.Tablebase | None,
) -> EvaluationResult:
    if tablebase is None:
        return EvaluationResult(
            eval_source="tablebase",
            winning_side="unknown",
            eval_status="tablebase_error",
            error_message=(
                "Syzygy tablebases are required for positions with 5 or fewer "
                "pieces; pass --syzygy-dir."
            ),
        )

    try:
        wdl = tablebase.probe_wdl(board)
        dtz = tablebase.probe_dtz(board)
        return EvaluationResult(
            eval_source="tablebase",
            winning_side=classify_side_to_move_wdl(wdl, board.turn),
            tb_wdl=wdl,
            tb_dtz=dtz,
            eval_status="ok",
        )
    except Exception as exc:
        return EvaluationResult(
            eval_source="tablebase",
            winning_side="unknown",
            eval_status="tablebase_error",
            error_message=str(exc),
        )


def evaluate_position(
    board: chess.Board,
    *,
    tablebase: chess.syzygy.Tablebase | None,
    stockfish: StockfishSession,
    sf_time_seconds: float,
    draw_threshold_cp: int,
) -> EvaluationResult:
    piece_count = len(board.piece_map())
    if piece_count <= 5:
        return evaluate_with_tablebase(board, tablebase)

    return stockfish.analyse(
        board,
        sf_time_seconds=sf_time_seconds,
        draw_threshold_cp=draw_threshold_cp,
    )


def build_marker_row(
    *,
    source_pgn: str,
    ending: str,
    game_index: int,
    headers: dict[str, str],
    marker_text: str,
    position: AnnotatedPosition,
    evaluation: EvaluationResult,
) -> dict[str, str | int | float]:
    return empty_row(
        source_pgn=source_pgn,
        ending=ending,
        game_index=game_index,
        event=headers.get("Event", ""),
        site=headers.get("Site", ""),
        date=headers.get("Date", ""),
        round_value=headers.get("Round", ""),
        white=headers.get("White", ""),
        black=headers.get("Black", ""),
        result=headers.get("Result", ""),
        ply_index=position.ply_index,
        fullmove_number=position.fullmove_number,
        move_san=position.move_san,
        move_uci=position.move_uci,
        fen=position.fen,
        side_to_move_value=position.side_to_move,
        piece_count=position.piece_count,
        marker_text=marker_text,
        eval_source=evaluation.eval_source,
        winning_side=evaluation.winning_side,
        tb_wdl="" if evaluation.tb_wdl is None else evaluation.tb_wdl,
        tb_dtz="" if evaluation.tb_dtz is None else evaluation.tb_dtz,
        sf_cp_white="" if evaluation.sf_cp_white is None else evaluation.sf_cp_white,
        sf_mate_white=""
        if evaluation.sf_mate_white is None
        else evaluation.sf_mate_white,
        sf_time_seconds=""
        if evaluation.sf_time_seconds is None
        else evaluation.sf_time_seconds,
        draw_threshold_cp=""
        if evaluation.draw_threshold_cp is None
        else evaluation.draw_threshold_cp,
        eval_status=evaluation.eval_status,
        error_message=evaluation.error_message,
    )


def build_parse_error_row(
    *,
    source_pgn: str,
    ending: str,
    marker_text: str,
    game_index: int,
    headers: dict[str, str],
    error_message: str,
) -> dict[str, str | int | float]:
    return empty_row(
        source_pgn=source_pgn,
        ending=ending,
        marker_text=marker_text,
        game_index=game_index,
        event=headers.get("Event", ""),
        site=headers.get("Site", ""),
        date=headers.get("Date", ""),
        round_value=headers.get("Round", ""),
        white=headers.get("White", ""),
        black=headers.get("Black", ""),
        result=headers.get("Result", ""),
        eval_status="parse_error",
        error_message=error_message,
    )


def build_file_error_row(
    *,
    source_pgn: str,
    ending: str,
    marker_text: str,
    error_message: str,
) -> dict[str, str | int | float]:
    return empty_row(
        source_pgn=source_pgn,
        ending=ending,
        marker_text=marker_text,
        eval_status="file_error",
        error_message=error_message,
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
