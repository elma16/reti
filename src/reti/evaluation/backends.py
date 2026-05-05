"""Pluggable position-evaluation backends.

The shape we want is "give me a board, get back an :class:`EvaluationResult`".
Three concrete backends ship in this module:

- :class:`TablebaseEvaluator` — Syzygy WDL/DTZ probe.
- :class:`StockfishEvaluator` — UCI engine analysis with a fixed time budget.
- :class:`RoutingEvaluator` — picks a backend per position. Defaults to
  "≤5 pieces → tablebase, else engine", which is what the existing exporter
  hardcoded; pass a different ``decide`` to plug in a different policy.

The legacy free function :func:`evaluate_with_tablebase` is preserved so the
old ``export_cql_positions`` flow keeps working without ceremony.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

import chess
import chess.engine
import chess.syzygy

from reti.common.subprocess_helpers import resolve_executable
from reti.evaluation.csv_schema import (
    EvaluationResult,
    classify_side_to_move_wdl,
    classify_stockfish_winner,
)


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


class StockfishSession:
    """Lazy UCI engine handle.

    The engine isn't started until the first analysis call; close() is a no-op
    if it was never started.
    """

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


class PositionEvaluator(ABC):
    """Anything that turns a board into an :class:`EvaluationResult`."""

    @abstractmethod
    def evaluate(self, board: chess.Board) -> EvaluationResult: ...

    def close(self) -> None:  # pragma: no cover - default no-op
        pass


class TablebaseEvaluator(PositionEvaluator):
    def __init__(self, tablebase: chess.syzygy.Tablebase | None) -> None:
        self.tablebase = tablebase

    def evaluate(self, board: chess.Board) -> EvaluationResult:
        return evaluate_with_tablebase(board, self.tablebase)

    def close(self) -> None:
        if self.tablebase is not None:
            self.tablebase.close()


class StockfishEvaluator(PositionEvaluator):
    def __init__(
        self,
        session: StockfishSession,
        *,
        sf_time_seconds: float,
        draw_threshold_cp: int,
    ) -> None:
        self.session = session
        self.sf_time_seconds = sf_time_seconds
        self.draw_threshold_cp = draw_threshold_cp

    def evaluate(self, board: chess.Board) -> EvaluationResult:
        return self.session.analyse(
            board,
            sf_time_seconds=self.sf_time_seconds,
            draw_threshold_cp=self.draw_threshold_cp,
        )

    def close(self) -> None:
        self.session.close()


class RoutingEvaluator(PositionEvaluator):
    """Pick one of two backends per position.

    Default policy: positions with ``piece_count <= threshold`` go to the
    primary evaluator (typically Syzygy), everything else to the fallback
    (typically Stockfish). Override with ``decide`` for any other policy.
    """

    def __init__(
        self,
        primary: PositionEvaluator,
        fallback: PositionEvaluator,
        *,
        threshold: int = 5,
        decide: Callable[[chess.Board], bool] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.threshold = threshold
        self._decide = decide

    def _use_primary(self, board: chess.Board) -> bool:
        if self._decide is not None:
            return self._decide(board)
        return len(board.piece_map()) <= self.threshold

    def evaluate(self, board: chess.Board) -> EvaluationResult:
        if self._use_primary(board):
            return self.primary.evaluate(board)
        return self.fallback.evaluate(board)

    def close(self) -> None:
        self.primary.close()
        self.fallback.close()
