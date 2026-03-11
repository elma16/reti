#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


ENDING_ROWS = [
    ("1-4BN", "1.4", "Bishop + Knight vs King"),
    ("2-0Pp", "2", "Pawn Endings"),
    ("2-1P", "", "King + Pawn vs King"),
    ("3-1Np", "3.1", "Knight vs Pawns"),
    ("3-2NN", "3.2", "Knight vs Knight"),
    ("4-1Bp", "4.1", "Bishop vs Pawns"),
    ("4-2scBB", "4.2", "Bishop vs Bishop (Same Colour)"),
    ("4-3ocBB", "4.3", "Bishop vs Bishop (Opposite Colour)"),
    ("5-0BN", "5", "Bishop vs Knight"),
    ("6-1-0RP", "6.1", "Rook vs Pawns"),
    ("6-2-0Rr", "6.2", "Rook vs Rook"),
    ("6-2-1RPr", "6.2 A1", "Rook + Pawn vs Rook"),
    ("6-2-2RPPr", "6.2 A2", "Rook + Two Pawns vs Rook"),
    ("6-3RRrr", "6.3", "Two Rooks vs Two Rooks"),
    ("7-1RN", "7.1", "Rook vs Knight"),
    ("7-2RB", "7.2", "Rook vs Bishop"),
    ("8-1RNr", "8.1", "Rook + Knight vs Rook"),
    ("8-2RBr", "8.2", "Rook + Bishop vs Rook"),
    ("8-3RAra", "8.3", "Rook + Minor Piece vs Rook + Minor Piece"),
    ("9-1Qp", "9.1", "Queen vs Pawns"),
    ("9-2Qq", "9.2", "Queen vs Queen"),
    ("9-3QPq", "9.3", "Queen + Pawn vs Queen"),
    ("10-1Qa", "10.1", "Queen vs One Minor Piece"),
    ("10-2Qr", "10.2", "Queen vs Rook"),
    ("10-3Qaa", "10.3", "Queen vs Two Minor Pieces"),
    ("10-4Qra", "10.4", "Queen vs Rook + Minor Piece"),
    ("10-5Qrr", "10.5", "Queen vs Two Rooks"),
    ("10-6Qaaa", "10.6", "Queen vs Three Minor Pieces"),
    ("10-7QAq", "10.7", "Queen and Minor Piece vs Queen"),
    ("10-7-1Qbrr", "", "Queen + Bishop vs Two Rooks"),
]

RESULT_TAG_RE = re.compile(r"\[Event ")


def count_games_in_pgn(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return len(RESULT_TAG_RE.findall(f.read()))


def discover_pgns(location: Path) -> list[Path]:
    if location.is_file():
        return [location]
    if location.is_dir():
        return sorted(
            path for path in location.rglob("*") if path.is_file() and path.suffix == ".pgn"
        )
    raise SystemExit(f"Invalid PGN input: {location}")


def load_counts(summary_csv: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with summary_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["status"] != "ok":
                continue
            stem = Path(row["cql"]).stem
            counts[stem] = counts.get(stem, 0) + int(row["match_count"] or "0")
    return counts


def render_markdown(counts: dict[str, int], total_games: int) -> str:
    lines = [
        "| ID | Ending | Quantity | Percentage |",
        "|---|---|---|---|",
    ]
    for stem, row_id, ending_name in ENDING_ROWS:
        qty = counts.get(stem, 0)
        pct = (qty / total_games * 100) if total_games else 0.0
        lines.append(f"| {row_id} | {ending_name} | {qty:,} | {pct:.2f} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render the FCE markdown table from analyse_cql.py summary.csv output."
        )
    )
    parser.add_argument("summary_csv", type=Path, help="Path to analyse_cql.py summary.csv")
    parser.add_argument(
        "pgn_input",
        type=Path,
        help="Original PGN file or directory used to create the summary.",
    )
    args = parser.parse_args()

    counts = load_counts(args.summary_csv)
    total_games = sum(count_games_in_pgn(path) for path in discover_pgns(args.pgn_input))
    print(render_markdown(counts, total_games))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
