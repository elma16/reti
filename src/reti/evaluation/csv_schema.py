"""CSV column schema and result classification for the position exporter.

The column list and the ``EvaluationResult`` dataclass are deliberately the
serialization contract: callers write rows by handing an ``EvaluationResult``
to :func:`build_marker_row`. Adding a new column means adding a field here and
an entry in ``CSV_COLUMNS`` — nothing else changes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import chess

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


def _side_name(turn: bool) -> str:
    return "white" if turn == chess.WHITE else "black"


def classify_side_to_move_wdl(wdl: int, turn: bool) -> str:
    if wdl > 0:
        return _side_name(turn)
    if wdl < 0:
        return _side_name(not turn)
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


def build_marker_row(
    *,
    source_pgn: str,
    ending: str,
    game_index: int,
    headers: dict[str, str],
    marker_text: str,
    position,  # AnnotatedPosition; lazy-imported to avoid a circular dep
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
