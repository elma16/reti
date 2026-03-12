#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reti.fce_metadata import FCE_TABLE_ROWS

RESULT_TAG_RE = re.compile(r"\[Event ")


def count_games_in_pgn(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return len(RESULT_TAG_RE.findall(f.read()))


def discover_pgns(location: Path) -> list[Path]:
    if location.is_file():
        return [location]
    if location.is_dir():
        return sorted(
            path
            for path in location.rglob("*")
            if path.is_file() and path.suffix == ".pgn"
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
    for stem, row_id, ending_name in FCE_TABLE_ROWS:
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
    parser.add_argument(
        "summary_csv", type=Path, help="Path to analyse_cql.py summary.csv"
    )
    parser.add_argument(
        "pgn_input",
        type=Path,
        help="Original PGN file or directory used to create the summary.",
    )
    args = parser.parse_args()

    counts = load_counts(args.summary_csv)
    total_games = sum(
        count_games_in_pgn(path) for path in discover_pgns(args.pgn_input)
    )
    print(render_markdown(counts, total_games))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
