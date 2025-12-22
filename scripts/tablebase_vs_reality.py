#!/usr/bin/env python3
"""
Compare tablebase truth to actual game results at the first {CQL} position in each game.

For every game in a PGN:
  - Walk the mainline until the first node with a comment containing "{CQL}".
  - If that position has 7 or fewer pieces, query the Lichess 7-man tablebase.
  - Record the tablebase verdict (win/draw/loss for side to move) and the game result.
  - Output a summary to stdout.

Requires: python-chess, requests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote

import chess
import chess.pgn
import requests
from tqdm import tqdm
import chess.syzygy

TABLEBASE_URL = "https://tablebase.lichess.ovh/standard?fen={fen}"


def tablebase_wdl(
    fen: str,
    cache: dict[str, int],
    syzygy_tb: chess.syzygy.Tablebase | None,
    allow_network: bool,
    network_failed: dict[str, bool],
) -> int | None:
    if fen in cache:
        return cache[fen]

    if syzygy_tb is not None:
        try:
            board = chess.Board(fen)
            wdl = syzygy_tb.probe_wdl(board)
            cache[fen] = wdl
            return wdl
        except Exception:
            pass

    if not allow_network:
        return None

    url = TABLEBASE_URL.format(fen=quote(fen))
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        wdl = data.get("wdl")
        cache[fen] = wdl
        return wdl
    except (requests.RequestException, json.JSONDecodeError):
        network_failed["failed"] = True
        return None


def wdl_label(wdl: int, stm_white: bool) -> str:
    if wdl == 2:
        return "side to move wins"
    if wdl == 0:
        return "draw"
    if wdl == -2:
        return "side to move loses"
    return "unknown"


def game_result_label(result: str) -> str:
    if result == "1-0":
        return "white wins"
    if result == "0-1":
        return "black wins"
    if result in ("1/2-1/2", "½-½", "0.5-0.5"):
        return "draw"
    return "unknown"


def first_cql_position(game: chess.pgn.Game) -> tuple[chess.Board | None, int]:
    board = game.board()
    seen_cql = 0
    after_tag = False
    for node in game.mainline():
        if node.move is None:
            continue  # root
        if not board.is_legal(node.move):
            return None, seen_cql  # malformed game
        board.push(node.move)
        comment = node.comment or ""
        if "CQL" in comment:
            after_tag = True
            seen_cql += 1
        if after_tag and len(board.piece_map()) <= 7:
            return board.copy(), seen_cql
    return None, seen_cql


def process_pgn(
    path: Path, syzygy_tb: chess.syzygy.Tablebase | None, allow_network: bool
):
    cache: dict[str, int] = {}
    summaries = []
    network_failed = {"failed": False}
    total_games = 0
    cql_tags = 0
    cql_leq7 = 0
    with path.open("r", encoding="utf-8", errors="ignore") as pgn:
        game_iter = iter(lambda: chess.pgn.read_game(pgn), None)
        for game in tqdm(game_iter, desc="Games", unit="game"):
            if game is None:
                break
            total_games += 1
            board, tags_seen = first_cql_position(game)
            cql_tags += tags_seen
            if board is None:
                continue
            cql_leq7 += 1
            fen = board.fen()
            wdl = tablebase_wdl(fen, cache, syzygy_tb, allow_network, network_failed)
            if wdl is None:
                continue
            stm_white = board.turn
            tb_verdict = wdl_label(wdl, stm_white)
            game_result = game_result_label(game.headers.get("Result", ""))
            summaries.append(
                {
                    "event": game.headers.get("Event", ""),
                    "white": game.headers.get("White", ""),
                    "black": game.headers.get("Black", ""),
                    "result": game_result,
                    "tb": tb_verdict,
                    "ply": board.ply(),
                    "fen": fen,
                }
            )
    return summaries, network_failed["failed"], total_games, cql_tags, cql_leq7


def main():
    parser = argparse.ArgumentParser(
        description="Compare tablebase verdict vs game result at first {CQL} position."
    )
    parser.add_argument("pgn", type=Path, help="Path to PGN with {CQL} markers")
    parser.add_argument(
        "--syzygy",
        type=Path,
        help="Path to Syzygy tablebase directory (offline); preferred over network.",
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="Disable network tablebase lookup (use only syzygy if provided).",
    )
    args = parser.parse_args()

    syzygy_tb = None
    if args.syzygy:
        syzygy_tb = chess.syzygy.open_tablebase(args.syzygy)

    summaries, network_failed, total_games, cql_tags, cql_leq7 = process_pgn(
        args.pgn, syzygy_tb=syzygy_tb, allow_network=not args.no_network
    )
    if not summaries:
        msg = "No tablebase-eligible {CQL} positions found."
        msg += f" (games scanned: {total_games}, CQL tags seen: {cql_tags}, CQL tags reaching <=7 pieces: {cql_leq7})"
        if network_failed and not args.no_network:
            msg += " (network tablebase lookup failed)"
        print(msg)
        return

    for s in summaries:
        print(
            f"{s['white']} - {s['black']} ({s['event']}), ply {s['ply']}: "
            f"tablebase={s['tb']} vs result={s['result']}  FEN={s['fen']}"
        )


if __name__ == "__main__":
    main()
