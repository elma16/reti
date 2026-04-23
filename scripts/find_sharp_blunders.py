"""
Find blunders played in sharp {CQL} positions.

Sharpness has the same definition as find_sharp_cql.py:
  * SHARP-WIN  — winning, exactly one move preserves the win.
  * SHARP-DRAW — drawn, exactly one move preserves the draw.
  * losing positions are never sharp.

A "sharp blunder" is a position that is sharp *and* the player whose
turn it is actually played some move other than the unique preserving
move in the game. The resulting PGN contains only games with at least
one sharp blunder; the node is annotated {CQL-SHARP-WIN-BLUNDER} or
{CQL-SHARP-DRAW-BLUNDER}. An optional CSV dumps one row per blunder
with columns matching the other analysis scripts.

Sharpness is verified with the Syzygy tablebase by default; a UCI
engine backend stub is inherited from find_sharp_cql for later use.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import chess
import chess.pgn
from tqdm import tqdm

from find_sharp_cql import (
    CQL_MARKER,
    SharpnessAnalyzer,
    build_analyzer,
    count_games,
    iter_cql_nodes,
    resolve_pgn_paths,
)

SHARP_WIN_BLUNDER = "CQL-SHARP-WIN-BLUNDER"
SHARP_DRAW_BLUNDER = "CQL-SHARP-DRAW-BLUNDER"

BLUNDER_CSV_FIELDS = [
    "event",
    "white",
    "black",
    "date",
    "result",
    "move_number",
    "side",
    "sharpness",
    "played_move",
    "best_move",
    "outcome_lost",
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
    blunders = 0
    sharp_total = 0

    pgn_out = output_pgn.open("w", encoding="utf-8") if output_pgn else None
    csv_out = None
    csv_writer = None
    if output_csv is not None:
        csv_out = output_csv.open("w", newline="", encoding="utf-8")
        csv_writer = csv.DictWriter(csv_out, fieldnames=BLUNDER_CSV_FIELDS)
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

                        any_blunder = False
                        for node in iter_cql_nodes(game):
                            board = node.board()
                            v = analyzer.verdict(board)
                            if not v.sharp or v.preserving_move is None:
                                continue
                            sharp_total += 1

                            # The reply to the CQL-marked position is
                            # node's first child (the next game move).
                            if not node.variations:
                                continue
                            played_move = node.variations[0].move
                            if played_move == v.preserving_move:
                                continue

                            any_blunder = True
                            blunders += 1
                            label = (
                                SHARP_WIN_BLUNDER
                                if v.outcome == "win"
                                else SHARP_DRAW_BLUNDER
                            )
                            node.comment = label

                            if csv_writer is not None:
                                row = _headers(game)
                                row.update(
                                    move_number=board.fullmove_number,
                                    side="White" if board.turn == chess.WHITE else "Black",
                                    sharpness="WIN" if v.outcome == "win" else "DRAW",
                                    played_move=board.san(played_move),
                                    best_move=board.san(v.preserving_move),
                                    outcome_lost=True,
                                    fen=board.fen(),
                                )
                                csv_writer.writerow(row)

                        progress.set_postfix_str(
                            f"{pgn_path.name} blunders={blunders}/{sharp_total}"
                        )
                        if any_blunder and pgn_out is not None:
                            print(game, file=pgn_out, end="\n\n")
                            games_written += 1
    finally:
        if pgn_out is not None:
            pgn_out.close()
        if csv_out is not None:
            csv_out.close()

    return games_written, blunders, sharp_total


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find games where a player blundered from a sharp {CQL} position "
            "(any move other than the unique preserving move)."
        )
    )
    parser.add_argument("pgn", nargs="+", help="Input PGN file(s) or directory(ies).")
    parser.add_argument(
        "-o", "--output", default="bahr_sharp_blunders.pgn",
        help="Output PGN path, or '' to skip (default: bahr_sharp_blunders.pgn).",
    )
    parser.add_argument(
        "--csv", default="", help="Optional CSV output path for blunder rows."
    )
    parser.add_argument(
        "--backend", choices=("tablebase", "engine"), default="tablebase",
        help="Sharpness backend (default: tablebase; 'engine' is a stub).",
    )
    parser.add_argument(
        "--tablebase",
        default="/Users/elliottmacneil/Documents/chess/tablebases/345/3-4-5-wdl",
        help="Directory containing Syzygy WDL files.",
    )
    parser.add_argument("--engine", default="stockfish", help="UCI engine path.")
    parser.add_argument("--time", type=float, default=0.1)
    parser.add_argument("--threshold", type=int, default=200)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    pgn_paths = resolve_pgn_paths(args.pgn)
    if not pgn_paths:
        print("Error: no PGN files found.", file=sys.stderr)
        return 1
    assert CQL_MARKER  # imported for shared-constant parity with sibling script

    pgn_path_out = Path(args.output) if args.output else None
    csv_path_out = Path(args.csv) if args.csv else None
    if pgn_path_out is None and csv_path_out is None:
        print("Error: specify --output and/or --csv.", file=sys.stderr)
        return 1

    with build_analyzer(args) as analyzer:
        games, blunders, sharp_total = process(
            pgn_paths, analyzer, pgn_path_out, csv_path_out
        )

    print(
        f"Wrote {games} games ({blunders} blunders in {sharp_total} sharp positions).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
