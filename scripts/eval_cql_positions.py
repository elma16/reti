"""
Evaluate positions marked with {CQL} comments using Stockfish.

For each game in the input PGN(s), find moves annotated with a comment that
is exactly "CQL", evaluate those positions for 0.1 s with Stockfish, and
classify each result as:
  - white   (score >= +THRESHOLD centipawns)
  - black   (score <= -THRESHOLD centipawns)
  - draw    (otherwise)

By default only the first CQL position per game is evaluated; pass --all to
evaluate every CQL position.

Output CSV columns: white, black, fen, date, eval_result[, game_result]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import chess
import chess.engine
import chess.pgn
from tqdm import tqdm

DEFAULT_THRESHOLD_CP = 200
DEFAULT_THINK_TIME = 0.1
DEFAULT_STOCKFISH = "stockfish"


def classify(score: chess.engine.PovScore, threshold_cp: int) -> str:
    mate = score.white().mate()
    if mate is not None:
        return "white" if mate > 0 else "black"

    cp = score.white().score()
    if cp is None:
        return "draw"
    if cp >= threshold_cp:
        return "white"
    if cp <= -threshold_cp:
        return "black"
    return "draw"


def find_cql_boards(game: chess.pgn.Game, *, all_comments: bool) -> list[chess.Board]:
    """Return boards at nodes whose comment is exactly 'CQL'.

    If all_comments is False, stop after the first match.
    """
    boards: list[chess.Board] = []
    node: chess.pgn.GameNode = game
    while True:
        if node.comment.strip() == "CQL":
            boards.append(node.board())
            if not all_comments:
                break
        if node.is_end():
            break
        node = node.next()  # type: ignore[assignment]
    return boards


def count_games(pgn_path: Path) -> int:
    try:
        with pgn_path.open("r", encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.startswith("[Event "))
    except OSError:
        return 0


def process_pgns(
    pgn_paths: list[Path],
    stockfish_path: str,
    threshold_cp: int,
    think_time: float,
    output_csv: Path,
    *,
    all_comments: bool,
    include_game_result: bool,
) -> None:
    total_games = sum(count_games(p) for p in pgn_paths)

    fieldnames = ["white", "black", "fen", "date", "eval_result"]
    if include_game_result:
        fieldnames.append("game_result")

    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        with output_csv.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

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
                            boards = find_cql_boards(game, all_comments=all_comments)
                            if not boards:
                                continue

                            headers = game.headers
                            base_row: dict[str, str] = {
                                "white": headers.get("White", ""),
                                "black": headers.get("Black", ""),
                                "date": headers.get("Date", ""),
                            }
                            if include_game_result:
                                base_row["game_result"] = headers.get("Result", "")

                            for board in boards:
                                info = engine.analyse(
                                    board,
                                    chess.engine.Limit(time=think_time),
                                )
                                score: chess.engine.PovScore = info["score"]
                                row = {
                                    **base_row,
                                    "fen": board.fen(),
                                    "eval_result": classify(score, threshold_cp),
                                }
                                writer.writerow(row)

    print(f"Written: {output_csv}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate CQL-annotated positions with Stockfish and write a CSV."
    )
    parser.add_argument(
        "pgn",
        nargs="+",
        help="One or more .pgn files (or directories scanned recursively).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="cql_eval.csv",
        help="Output CSV path (default: cql_eval.csv).",
    )
    parser.add_argument(
        "--stockfish",
        default=DEFAULT_STOCKFISH,
        help=f"Path to Stockfish binary (default: {DEFAULT_STOCKFISH}).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD_CP,
        metavar="CP",
        help=(
            f"Centipawn threshold for 'winning' classification "
            f"(default: {DEFAULT_THRESHOLD_CP})."
        ),
    )
    parser.add_argument(
        "--time",
        type=float,
        default=DEFAULT_THINK_TIME,
        dest="think_time",
        metavar="SEC",
        help=f"Stockfish analysis time per position in seconds (default: {DEFAULT_THINK_TIME}).",
    )
    parser.add_argument(
        "--all",
        dest="all_comments",
        action="store_true",
        default=False,
        help="Evaluate all CQL-annotated positions per game (default: first only).",
    )
    parser.add_argument(
        "--no-game-result",
        dest="include_game_result",
        action="store_false",
        default=True,
        help="Omit the game result column from the CSV (included by default).",
    )
    return parser.parse_args(argv)


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


def main() -> int:
    args = parse_args()
    pgn_paths = resolve_pgn_paths(args.pgn)
    if not pgn_paths:
        print("Error: no PGN files found.", file=sys.stderr)
        return 1

    process_pgns(
        pgn_paths=pgn_paths,
        stockfish_path=args.stockfish,
        threshold_cp=args.threshold,
        think_time=args.think_time,
        output_csv=Path(args.output),
        all_comments=args.all_comments,
        include_game_result=args.include_game_result,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
