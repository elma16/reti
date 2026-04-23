"""Analyse a PGN with Stockfish and flag blunders to CSV.

For every position in every game the engine evaluates:
  1. The best move (top-1) score
  2. The score after the move actually played

If the difference exceeds a threshold the position is written to a CSV.

Usage:
    python scripts/blunder_check.py [--pgn PATH] [--time 0.005] [--threshold 200]
"""

import argparse
import csv
import sys
from pathlib import Path

import chess
import chess.engine
import chess.pgn
from tqdm import tqdm


def cp_score(pov_score: chess.engine.PovScore, turn: chess.Color) -> float | None:
    """Return centipawn score from White's perspective, or None for mate."""
    score = pov_score.white()
    cp = score.score(mate_score=10_000)
    return cp


def analyse_game(engine, game, time_limit, threshold):
    """Yield blunder rows for a single game."""
    headers = game.headers
    event = headers.get("Event", "?")
    white = headers.get("White", "?")
    black = headers.get("Black", "?")
    date = headers.get("Date", "?")
    result = headers.get("Result", "?")

    board = game.board()
    evaluate_next = False

    for node in game.mainline():
        move = node.move

        if evaluate_next:
            turn = board.turn  # side to move BEFORE this move
            move_number_display = board.fullmove_number
            side = "White" if turn == chess.WHITE else "Black"

            # 1. Engine's best move evaluation
            best_info = engine.analyse(board, chess.engine.Limit(time=time_limit))
            best_score = cp_score(best_info["score"], turn)
            best_move = best_info.get("pv", [None])[0]

            # 2. Evaluate the position after the move actually played
            board.push(move)
            played_info = engine.analyse(board, chess.engine.Limit(time=time_limit))
            played_score = cp_score(played_info["score"], turn)
            board.pop()

            if best_score is not None and played_score is not None:
                # Eval drop from the perspective of the side that moved
                if turn == chess.WHITE:
                    drop = best_score - played_score
                else:
                    drop = played_score - best_score

                if drop >= threshold:
                    fen = board.fen()
                    yield {
                        "event": event,
                        "white": white,
                        "black": black,
                        "date": date,
                        "result": result,
                        "move_number": move_number_display,
                        "side": side,
                        "played_move": board.san(move),
                        "best_move": board.san(best_move) if best_move else "?",
                        "played_eval": played_score,
                        "best_eval": best_score,
                        "eval_drop": drop,
                        "fen": fen,
                    }

        # {CQL} on this node means evaluate the NEXT move from this position
        evaluate_next = "CQL" in (node.comment or "")

        # Advance the board
        board.push(move)


def main():
    parser = argparse.ArgumentParser(description="Detect blunders in a PGN file using Stockfish.")
    parser.add_argument("--pgn", type=str, default="output/bahr/bahr.pgn", help="Path to PGN file")
    parser.add_argument("--out", type=str, default="output/bahr/blunders.csv", help="Output CSV path")
    parser.add_argument("--time", type=float, default=0.005, help="Stockfish time per position in seconds")
    parser.add_argument("--threshold", type=int, default=200, help="Centipawn drop to flag as blunder")
    parser.add_argument("--stockfish", type=str, default="/opt/homebrew/bin/stockfish", help="Path to Stockfish binary")
    args = parser.parse_args()

    pgn_path = Path(args.pgn)
    if not pgn_path.exists():
        print(f"PGN not found: {pgn_path}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "event", "white", "black", "date", "result",
        "move_number", "side", "played_move", "best_move",
        "played_eval", "best_eval", "eval_drop", "fen",
    ]

    # Count total games for progress bar
    print("Counting games ...", end=" ", flush=True)
    total_games = 0
    with open(pgn_path) as f:
        for line in f:
            if line.startswith("[Event "):
                total_games += 1
    print(f"{total_games} games found.")

    engine = chess.engine.SimpleEngine.popen_uci(args.stockfish)
    engine.configure({"Threads": 1, "Hash": 16})

    blunder_count = 0

    with open(pgn_path) as pgn_file, open(out_path, "w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        pbar = tqdm(total=total_games, unit="game", desc="Analysing", dynamic_ncols=True)
        while True:
            game = chess.pgn.read_game(pgn_file)
            if game is None:
                break

            for row in analyse_game(engine, game, args.time, args.threshold):
                writer.writerow(row)
                blunder_count += 1

            pbar.set_postfix(blunders=blunder_count)
            pbar.update(1)

        pbar.close()

    engine.quit()
    print(f"Done. {total_games} games, {blunder_count} blunders -> {out_path}")


if __name__ == "__main__":
    main()
