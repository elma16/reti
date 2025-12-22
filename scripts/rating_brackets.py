#!/usr/bin/env python3
"""
Summarize each player's score vs opponents in rating brackets.
Reads a PGN file, collects games with numeric WhiteElo/BlackElo and a result,
and prints, for every player, the points and percentage vs each rating bucket.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from collections.abc import Iterable


BRACKET_SIZE = 100  # change to widen/narrow buckets


def bucket(rating: int, size: int = BRACKET_SIZE) -> str:
    low = (rating // size) * size
    high = low + size - 1
    return f"{low}-{high}"


def parse_pgn_headers(path: Path) -> Iterable[dict[str, str]]:
    """Yield tag dictionaries for each game; skip movetext."""
    tag_re = re.compile(r'^\[(\w+)\s+"(.*)"\]')
    headers: dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                if headers:
                    yield headers
                    headers = {}
                continue
            m = tag_re.match(line)
            if m:
                headers[m.group(1)] = m.group(2)
        if headers:
            yield headers


def score(result: str, as_white: bool) -> float | None:
    if result == "1-0":
        return 1.0 if as_white else 0.0
    if result == "0-1":
        return 0.0 if as_white else 1.0
    if result in {"1/2-1/2", "½-½", "0.5-0.5"}:
        return 0.5
    return None


def process_games(pgn_path: Path) -> dict[str, dict[str, tuple[float, int]]]:
    """Return stats[player][bucket] = (points, games)."""
    stats: dict[str, dict[str, tuple[float, int]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0])
    )
    for tags in parse_pgn_headers(pgn_path):
        try:
            w_name, b_name = tags["White"], tags["Black"]
            w_elo, b_elo = int(tags["WhiteElo"]), int(tags["BlackElo"])
            result = tags["Result"]
        except (KeyError, ValueError):
            continue

        w_score = score(result, True)
        b_score = score(result, False)
        if w_score is None or b_score is None:
            continue

        bkt_w = bucket(b_elo)
        bkt_b = bucket(w_elo)

        sw = stats[w_name][bkt_w]
        sw[0] += w_score
        sw[1] += 1

        sb = stats[b_name][bkt_b]
        sb[0] += b_score
        sb[1] += 1

    return stats


def print_stats(stats: dict[str, dict[str, tuple[float, int]]]) -> None:
    for player in sorted(stats):
        print(player)
        for bkt, (pts, games) in sorted(stats[player].items()):
            pct = 100 * pts / games if games else 0.0
            print(f"  vs {bkt}: {pts:.1f} / {games}  ({pct:.1f}%)")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize scores vs rating brackets from a PGN file."
    )
    parser.add_argument("pgn", type=Path, help="Path to PGN file")
    parser.add_argument(
        "--bucket",
        type=int,
        default=BRACKET_SIZE,
        help=f"Rating bucket size (default {BRACKET_SIZE})",
    )
    args = parser.parse_args()

    global BRACKET_SIZE
    BRACKET_SIZE = args.bucket

    stats = process_games(args.pgn)
    print_stats(stats)


if __name__ == "__main__":
    main()
