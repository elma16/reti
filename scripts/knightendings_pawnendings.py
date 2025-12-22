#!/usr/bin/env python3
"""
Analyse Botvinnik's 'knight endings are pawn endings' idea.

Pipeline:
1. Read one or more PGN files containing games annotated with {CQL} comments.
2. For each {CQL}-tagged node, record the position after that move.
3. If --first_only is set, take only the first {CQL} match per game.
4. Evaluate:
    - The original position (with knights).
    - A modified version with all knights removed.
5. Save results to CSV.
6. Print summary statistics.

Usage:
    python analyse_knight_endings.py \
      --pgn NN1.pgn NN2.pgn \
      --engine /usr/local/bin/stockfish \
      --out_csv knight_pawn_endings.csv \
      --movetime_ms 50 \
      --first_only
"""

from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from typing import Any

import chess
import chess.pgn
import chess.engine
from tqdm import tqdm


@dataclass
class CQLPosition:
    source_file: str
    game_index: int
    position_index: int
    ply: int
    fen: str
    lichess_url: str | None
    event: str | None
    white: str | None
    black: str | None
    result: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate 'knight endings are pawn endings' via engine analysis."
    )
    parser.add_argument("--pgn", nargs="+", required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--out_csv", required=True)

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--movetime_ms", type=int, default=50)
    group.add_argument("--nodes", type=int, default=None)

    parser.add_argument("--cp_threshold", type=int, default=100)
    parser.add_argument("--max_positions", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")

    # NEW FLAG
    parser.add_argument(
        "--first_only",
        action="store_true",
        help="Include only the FIRST {CQL} position per game.",
    )

    return parser.parse_args()


def collect_cql_positions(
    pgn_paths: list[str], first_only: bool, verbose: bool = False
) -> list[CQLPosition]:
    positions: list[CQLPosition] = []

    for pgn_path in pgn_paths:
        if verbose:
            print(f"Scanning {pgn_path} for {{CQL}}-annotated positions...")

        if not os.path.exists(pgn_path):
            print(f"! Warning: PGN file not found: {pgn_path}")
            continue

        with open(pgn_path, "r", encoding="utf-8", errors="replace") as f:
            game_index = 0

            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                game_index += 1

                board = game.board()
                node = game
                ply = 0
                cql_index = 0
                taken_first = False

                while node.variations:
                    next_node = node.variation(0)
                    board.push(next_node.move)
                    ply += 1

                    if next_node.comment and "CQL" in next_node.comment:
                        cql_index += 1

                        if first_only and taken_first:
                            # skip all further CQL hits in this game
                            pass
                        else:
                            taken_first = True
                            headers = game.headers
                            positions.append(
                                CQLPosition(
                                    source_file=os.path.basename(pgn_path),
                                    game_index=game_index,
                                    position_index=cql_index,
                                    ply=ply,
                                    fen=board.fen(),
                                    lichess_url=headers.get("LichessURL"),
                                    event=headers.get("Event"),
                                    white=headers.get("White"),
                                    black=headers.get("Black"),
                                    result=headers.get("Result"),
                                )
                            )

                    node = next_node

    if verbose:
        print(f"Collected {len(positions)} CQL-tagged positions.")
    return positions


def strip_knights(board: chess.Board) -> chess.Board:
    b = board.copy(stack=False)
    for sq in chess.SQUARES:
        piece = b.piece_at(sq)
        if piece and piece.piece_type == chess.KNIGHT:
            b.remove_piece_at(sq)
    return b


def score_to_cp(score: chess.engine.PovScore, mate_score: int = 100000) -> int:
    return int(score.score(mate_score=mate_score))


def classify_cp(cp: int, threshold: int) -> str:
    if cp > threshold:
        return "win"
    elif cp < -threshold:
        return "loss"
    else:
        return "drawish"


def get_limit(args: argparse.Namespace) -> chess.engine.Limit:
    if args.nodes is not None:
        return chess.engine.Limit(nodes=args.nodes)
    else:
        return chess.engine.Limit(time=args.movetime_ms / 1000.0)


def analyse_positions(
    positions: list[CQLPosition],
    engine_path: str,
    out_csv: str,
    cp_threshold: int,
    limit: chess.engine.Limit,
    max_positions: int | None,
    verbose: bool,
) -> None:
    if max_positions is not None:
        positions = positions[:max_positions]

    engine = chess.engine.SimpleEngine.popen_uci([engine_path])

    fieldnames = [
        "source_file",
        "game_index",
        "position_index",
        "ply",
        "lichess_url",
        "event",
        "white",
        "black",
        "result",
        "fen_knights",
        "fen_no_knights",
        "cp_knights",
        "cp_no_knights",
        "class_knights",
        "class_no_knights",
        "delta_cp",
        "same_class",
        "error",
    ]

    n_ok = 0
    n_same_class = 0
    n_within_50 = 0
    n_within_100 = 0
    n_within_200 = 0
    total = len(positions)

    with open(out_csv, "w", newline="", encoding="utf-8") as csv_f:
        writer = csv.DictWriter(csv_f, fieldnames=fieldnames)
        writer.writeheader()

        for pos in tqdm(positions, desc="Analysing positions", unit="pos"):
            row: dict[str, Any] = {
                "source_file": pos.source_file,
                "game_index": pos.game_index,
                "position_index": pos.position_index,
                "ply": pos.ply,
                "lichess_url": pos.lichess_url or "",
                "event": pos.event or "",
                "white": pos.white or "",
                "black": pos.black or "",
                "result": pos.result or "",
                "fen_knights": pos.fen,
                "fen_no_knights": "",
                "cp_knights": "",
                "cp_no_knights": "",
                "class_knights": "",
                "class_no_knights": "",
                "delta_cp": "",
                "same_class": "",
                "error": "",
            }

            try:
                board_knights = chess.Board(pos.fen)
                board_no_knights = strip_knights(board_knights)
                row["fen_no_knights"] = board_no_knights.fen()

                info_knights = engine.analyse(board_knights, limit=limit)
                info_no_knights = engine.analyse(board_no_knights, limit=limit)

                cp_k = score_to_cp(info_knights["score"].pov(board_knights.turn))
                cp_n = score_to_cp(info_no_knights["score"].pov(board_no_knights.turn))

                row["cp_knights"] = cp_k
                row["cp_no_knights"] = cp_n
                row["class_knights"] = classify_cp(cp_k, cp_threshold)
                row["class_no_knights"] = classify_cp(cp_n, cp_threshold)
                row["delta_cp"] = cp_k - cp_n
                row["same_class"] = row["class_knights"] == row["class_no_knights"]

                n_ok += 1
                if row["same_class"]:
                    n_same_class += 1
                if abs(cp_k - cp_n) <= 50:
                    n_within_50 += 1
                if abs(cp_k - cp_n) <= 100:
                    n_within_100 += 1
                if abs(cp_k - cp_n) <= 200:
                    n_within_200 += 1

            except Exception as e:
                row["error"] = str(e)

            writer.writerow(row)

    engine.quit()

    print("\n=== Summary ===")
    print(f"Total CQL positions: {total}")
    print(f"Successfully evaluated: {n_ok}")
    if n_ok > 0:
        print(f"Same class: {n_same_class} ({n_same_class / n_ok:.3f})")
        print(f"|Δcp| ≤ 50:  {n_within_50}  ({n_within_50 / n_ok:.3f})")
        print(f"|Δcp| ≤ 100: {n_within_100} ({n_within_100 / n_ok:.3f})")
        print(f"|Δcp| ≤ 200: {n_within_200} ({n_within_200 / n_ok:.3f})")
    print(f"CSV written to: {out_csv}")


def main() -> None:
    args = parse_args()

    positions = collect_cql_positions(
        args.pgn, first_only=args.first_only, verbose=args.verbose
    )

    if not positions:
        print("No {CQL} positions found.")
        return

    limit = get_limit(args)

    analyse_positions(
        positions,
        engine_path=args.engine,
        out_csv=args.out_csv,
        cp_threshold=args.cp_threshold,
        limit=limit,
        max_positions=args.max_positions,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
