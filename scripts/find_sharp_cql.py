"""
Find {CQL}-annotated positions in a PGN whose evaluation is "sharp":
the side to move has exactly one move that preserves the optimal result
(a win must be kept as a win; a draw as a draw; losing positions are
never sharp).

By default the sharpness verdict is taken from a Syzygy tablebase
(fast, exact, suitable for the 3/4/5-man positions that arise from
Bahr's rule). An engine backend stub is included so a UCI engine (e.g.
Stockfish) can be plugged in later for positions outside tablebase
coverage.

Output: a new PGN containing only games that have at least one sharp
{CQL} position. At each sharp node the {CQL} comment is rewritten to
{CQL-SHARP} so downstream tooling (and a human reader) can tell them
apart from the non-sharp {CQL} comments that are kept unchanged.
"""

from __future__ import annotations

import argparse
import csv
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import chess
import chess.engine
import chess.pgn
import chess.syzygy
from tqdm import tqdm

CQL_MARKER = "CQL"
SHARP_WIN_MARKER = "CQL-SHARP-WIN"
SHARP_DRAW_MARKER = "CQL-SHARP-DRAW"


@dataclass
class SharpVerdict:
    sharp: bool
    # Optimal result from side-to-move's POV at the queried position.
    # "win" / "draw" / "loss" / "unknown".
    outcome: str
    # How many legal moves preserve the optimal result.
    preserving_moves: int
    # The unique preserving move, set iff sharp.
    preserving_move: chess.Move | None = None


class SharpnessAnalyzer(ABC):
    @abstractmethod
    def verdict(self, board: chess.Board) -> SharpVerdict: ...

    def close(self) -> None:  # pragma: no cover - default no-op
        pass

    def __enter__(self) -> "SharpnessAnalyzer":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _wdl_bucket(wdl: int) -> str:
    # Syzygy WDL: 2 win, 1 cursed win, 0 draw, -1 blessed loss, -2 loss.
    # For "sharpness" we lump cursed/blessed with their nominal result.
    if wdl >= 1:
        return "win"
    if wdl <= -1:
        return "loss"
    return "draw"


class TablebaseAnalyzer(SharpnessAnalyzer):
    """Sharpness from Syzygy WDL.

    A move "preserves" a win if it leads to a position where the
    opponent is losing; it "preserves" a draw if it leads to a position
    where the opponent is drawing or losing. A position with no legal
    moves (mate/stalemate), or a losing position, is never sharp.
    """

    def __init__(self, path: Path) -> None:
        self._tb = chess.syzygy.open_tablebase(str(path))

    def close(self) -> None:
        self._tb.close()

    def verdict(self, board: chess.Board) -> SharpVerdict:
        if board.is_game_over(claim_draw=False):
            return SharpVerdict(False, "unknown", 0)

        try:
            wdl = self._tb.probe_wdl(board)
        except (chess.syzygy.MissingTableError, KeyError, IndexError):
            return SharpVerdict(False, "unknown", 0)

        outcome = _wdl_bucket(wdl)
        if outcome == "loss":
            return SharpVerdict(False, "loss", 0)

        preserving = 0
        sole_move: chess.Move | None = None
        for move in board.legal_moves:
            board.push(move)
            try:
                child_wdl = self._tb.probe_wdl(board)
            except (chess.syzygy.MissingTableError, KeyError, IndexError):
                board.pop()
                return SharpVerdict(False, "unknown", 0)
            board.pop()
            # child_wdl is from the opponent's POV after our move.
            # Mover's achieved result = _wdl_bucket(-child_wdl).
            achieved = _wdl_bucket(-child_wdl)
            keeps = (outcome == "win" and achieved == "win") or (
                outcome == "draw" and achieved in ("draw", "win")
            )
            if keeps:
                preserving += 1
                if preserving == 1:
                    sole_move = move
                else:
                    sole_move = None
                    break  # early exit: not sharp

        return SharpVerdict(preserving == 1, outcome, preserving, sole_move)


class EngineAnalyzer(SharpnessAnalyzer):
    """Placeholder for a UCI-engine-driven sharpness check.

    Not wired into the CLI yet — kept here so the interface is already
    in place for when tablebase coverage runs out (e.g. 6+ men).
    """

    def __init__(self, engine_path: str, think_time: float, threshold_cp: int) -> None:
        self._engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self._limit = chess.engine.Limit(time=think_time)
        self._threshold = threshold_cp

    def close(self) -> None:
        self._engine.close()

    def verdict(self, board: chess.Board) -> SharpVerdict:  # pragma: no cover - stub
        raise NotImplementedError("EngineAnalyzer is a stub; tablebase backend only for now.")


def iter_cql_nodes(game: chess.pgn.Game) -> Iterator[chess.pgn.ChildNode]:
    node: chess.pgn.GameNode = game
    while not node.is_end():
        node = node.next()  # type: ignore[assignment]
        if node.comment.strip() == CQL_MARKER:
            yield node  # type: ignore[misc]


def count_games(pgn_path: Path) -> int:
    try:
        with pgn_path.open("r", encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.startswith("[Event "))
    except OSError:
        return 0


SHARP_CSV_FIELDS = [
    "event",
    "white",
    "black",
    "date",
    "result",
    "move_number",
    "side",
    "sharpness",
    "best_move",
    "fen",
]


def _headers(game: chess.pgn.Game) -> dict[str, str]:
    h = game.headers
    return {
        "event": h.get("Event", "?"),
        "white": h.get("White", "?"),
        "black": h.get("Black", "?"),
        "date": h.get("Date", "?"),
        "result": h.get("Result", "?"),
    }


def process(
    pgn_paths: list[Path],
    analyzer: SharpnessAnalyzer,
    output_pgn: Path | None,
    output_csv: Path | None,
) -> tuple[int, int, int]:
    total_games = sum(count_games(p) for p in pgn_paths)
    games_written = 0
    sharp_positions = 0
    cql_positions = 0

    pgn_out = output_pgn.open("w", encoding="utf-8") if output_pgn else None
    csv_out = None
    csv_writer = None
    if output_csv is not None:
        csv_out = output_csv.open("w", newline="", encoding="utf-8")
        csv_writer = csv.DictWriter(csv_out, fieldnames=SHARP_CSV_FIELDS)
        csv_writer.writeheader()

    try:
        with tqdm(
            total=total_games,
            desc="games",
            unit="game",
            dynamic_ncols=sys.stderr.isatty(),
            file=sys.stderr,
        ) as progress:
            for pgn_path in pgn_paths:
                progress.set_postfix_str(pgn_path.name)
                with pgn_path.open("r", encoding="utf-8", errors="replace") as f:
                    while True:
                        game = chess.pgn.read_game(f)
                        if game is None:
                            break
                        progress.update(1)

                        any_sharp = False
                        for node in iter_cql_nodes(game):
                            cql_positions += 1
                            board = node.board()
                            v = analyzer.verdict(board)
                            if v.sharp:
                                node.comment = (
                                    SHARP_WIN_MARKER if v.outcome == "win" else SHARP_DRAW_MARKER
                                )
                                any_sharp = True
                                sharp_positions += 1
                                if csv_writer is not None:
                                    parent = node.parent
                                    assert parent is not None
                                    parent_board = parent.board()
                                    row = _headers(game)
                                    row.update(
                                        move_number=parent_board.fullmove_number,
                                        side="White" if board.turn == chess.WHITE else "Black",
                                        sharpness="WIN" if v.outcome == "win" else "DRAW",
                                        best_move=(
                                            board.san(v.preserving_move)
                                            if v.preserving_move
                                            else "?"
                                        ),
                                        fen=board.fen(),
                                    )
                                    csv_writer.writerow(row)

                        progress.set_postfix_str(
                            f"{pgn_path.name} sharp={sharp_positions}/{cql_positions}"
                        )
                        if any_sharp and pgn_out is not None:
                            print(game, file=pgn_out, end="\n\n")
                            games_written += 1
    finally:
        if pgn_out is not None:
            pgn_out.close()
        if csv_out is not None:
            csv_out.close()

    return games_written, sharp_positions, cql_positions


def resolve_pgn_paths(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser()
        if p.is_file():
            paths.append(p)
        elif p.is_dir():
            paths.extend(sorted(p.rglob("*.pgn")))
        else:
            print(f"Warning: '{raw}' is not a file or directory, skipping.", file=sys.stderr)
    return paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter {CQL} positions down to those that are tablebase-sharp."
    )
    parser.add_argument("pgn", nargs="+", help="Input PGN file(s) or directory(ies).")
    parser.add_argument(
        "-o", "--output", default="bahr_sharp.pgn",
        help="Output PGN path, or '' to skip (default: bahr_sharp.pgn).",
    )
    parser.add_argument(
        "--csv", default="", help="Optional CSV output path for sharp positions."
    )
    parser.add_argument(
        "--backend",
        choices=("tablebase", "engine"),
        default="tablebase",
        help="Sharpness backend (default: tablebase; 'engine' is a stub).",
    )
    parser.add_argument(
        "--tablebase",
        default="/Users/elliottmacneil/Documents/chess/tablebases/345/3-4-5-wdl",
        help="Directory containing Syzygy WDL files.",
    )
    parser.add_argument("--engine", default="stockfish", help="UCI engine path (engine backend).")
    parser.add_argument(
        "--time", type=float, default=0.1, help="Per-position engine think time (seconds)."
    )
    parser.add_argument("--threshold", type=int, default=200, help="Engine cp threshold.")
    return parser.parse_args(argv)


def build_analyzer(args: argparse.Namespace) -> SharpnessAnalyzer:
    if args.backend == "tablebase":
        return TablebaseAnalyzer(Path(args.tablebase).expanduser())
    return EngineAnalyzer(args.engine, args.time, args.threshold)


def main() -> int:
    args = parse_args()
    pgn_paths = resolve_pgn_paths(args.pgn)
    if not pgn_paths:
        print("Error: no PGN files found.", file=sys.stderr)
        return 1

    pgn_path_out = Path(args.output) if args.output else None
    csv_path_out = Path(args.csv) if args.csv else None
    if pgn_path_out is None and csv_path_out is None:
        print("Error: specify --output and/or --csv.", file=sys.stderr)
        return 1

    with build_analyzer(args) as analyzer:
        games, sharp, total = process(pgn_paths, analyzer, pgn_path_out, csv_path_out)

    print(
        f"Wrote {games} games to {args.output} "
        f"({sharp}/{total} CQL positions were sharp).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
