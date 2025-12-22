#!/usr/bin/env python3

#!/usr/bin/env python3
"""
Extract mating positions from a PGN file using a UCI engine.

For each position in each game:
- Analyse for a fixed amount of time (M milliseconds).
- If the side to move has a forced mate, save a row to CSV with:
    - FEN
    - mate_in (in moves, not plies)
    - pv_moves (space-separated UCI moves for the mating line)
    - Event
    - White
    - Black
    - game_index (0-based)
    - ply_index (0-based, half-move index in the game)

Example:
    python3 extract_mates_from_pgn.py \
        --pgn games.pgn \
        --out_csv mates.csv \
        --engine /usr/local/bin/stockfish \
        --movetime_ms 50
"""

import argparse
import csv
import sys
from pathlib import Path

import chess
import chess.pgn
import chess.engine
from tqdm import tqdm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan PGN for positions where the side to move has a forced mate."
    )
    parser.add_argument(
        "--pgn",
        type=str,
        required=True,
        help="Path to input PGN file.",
    )
    parser.add_argument(
        "--out_csv",
        type=str,
        required=True,
        help="Path to output CSV file.",
    )
    parser.add_argument(
        "--engine",
        type=str,
        required=True,
        help="Path to UCI engine executable (e.g. stockfish).",
    )
    parser.add_argument(
        "--movetime_ms",
        type=int,
        default=50,
        help="Analysis time per position in milliseconds (default: 50).",
    )
    parser.add_argument(
        "--max_games",
        type=int,
        default=None,
        help="Optional limit on number of games to process.",
    )
    return parser.parse_args()


def analyse_position_for_mate(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    movetime_ms: int,
) -> tuple[bool, int | None, list[chess.Move] | None]:
    """
    Analyse a single position.

    Returns:
        (has_mate, mate_in_moves, pv_moves)

        has_mate: True if side to move has a forced mate.
        mate_in_moves: number of moves to mate (int) if has_mate, else None.
        pv_moves: list of chess.Move describing the mating line if has_mate, else None.
    """
    limit = chess.engine.Limit(time=movetime_ms / 1000.0)

    info = engine.analyse(board, limit)

    score = info.get("score")
    if score is None:
        return False, None, None

    # Score from POV of the side to move
    pov_score = score.pov(board.turn)

    if not pov_score.is_mate():
        return False, None, None

    # Positive mate value means side-to-move is winning (we want those)
    mate_plies = pov_score.mate()
    if mate_plies is None or mate_plies <= 0:
        # Mate for the *other* side, not a "mate in N" puzzle for side to move.
        return False, None, None

    # Convert plies to full moves: 1 ply -> "mate in 1"
    mate_in_moves = (mate_plies + 1) // 2

    pv = info.get("pv")
    if pv is None:
        pv_moves: list[chess.Move] | None = None
    else:
        # Use the first mate_plies moves of the PV, if available
        pv_moves = list(pv[:mate_plies])

    return True, mate_in_moves, pv_moves


def iter_games(pgn_path: Path):
    """Generator over games in a PGN file."""
    with pgn_path.open("r", encoding="utf-8", errors="replace") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            yield game


def main() -> None:
    args = parse_args()

    pgn_path = Path(args.pgn)
    if not pgn_path.is_file():
        print(f"Error: PGN file not found: {pgn_path}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Open engine once, reuse it for all positions
    try:
        engine = chess.engine.SimpleEngine.popen_uci([args.engine])
    except FileNotFoundError:
        print(f"Error: Engine not found at path: {args.engine}", file=sys.stderr)
        sys.exit(1)

    rows = []

    try:
        game_iter = iter_games(pgn_path)
        game_bar = tqdm(desc="Games processed", unit="game")

        for game_idx, game in enumerate(game_iter):
            if args.max_games is not None and game_idx >= args.max_games:
                break

            event = game.headers.get("Event", "")
            white = game.headers.get("White", "")
            black = game.headers.get("Black", "")

            board = game.board()

            # Count number of positions (plies) so we can have a per-game bar
            # We need to iterate mainline_moves twice, so collect them
            mainline_moves = list(game.mainline_moves())

            if not mainline_moves:
                game_bar.update(1)
                continue

            move_bar = tqdm(
                total=len(mainline_moves),
                desc=f"Game {game_idx} positions",
                leave=False,
                unit="pos",
            )

            for ply_index, move in enumerate(mainline_moves):
                # Analyse *before* making the move: the side to move is about to play
                has_mate, mate_in_moves, pv_moves = analyse_position_for_mate(
                    engine, board, args.movetime_ms
                )

                if has_mate and mate_in_moves is not None:
                    # Convert PV to space-separated UCI string
                    if pv_moves is not None:
                        pv_uci = " ".join(m.uci() for m in pv_moves)
                    else:
                        pv_uci = ""

                    rows.append(
                        {
                            "FEN": board.fen(),
                            "mate_in": mate_in_moves,
                            "pv_moves": pv_uci,
                            "Event": event,
                            "White": white,
                            "Black": black,
                            "game_index": game_idx,
                            "ply_index": ply_index,
                        }
                    )

                # Now actually make the game move to advance the position
                board.push(move)
                move_bar.update(1)

            move_bar.close()
            game_bar.update(1)

        game_bar.close()

    finally:
        engine.quit()

    # Write CSV
    fieldnames = [
        "FEN",
        "mate_in",
        "pv_moves",
        "Event",
        "White",
        "Black",
        "game_index",
        "ply_index",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} mating positions to {out_path}")


if __name__ == "__main__":
    main()
