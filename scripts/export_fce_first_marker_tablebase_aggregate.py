#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import chess

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from reti.fce_eval_snapshot import (
    AGGREGATE_COLUMNS,
    AGGREGATE_INTEGER_COLUMNS,
    classify_material_side,
    eval_key_for_fen,
    normalize_marker_row,
)


def metadata_value(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise RuntimeError(f"source eval DB is missing metadata key {key!r}")
    return str(row[0])


def load_evaluations(eval_db: Path) -> tuple[str, dict[str, tuple[str, str, str]]]:
    conn = sqlite3.connect(f"file:{eval_db}?mode=ro", uri=True)
    try:
        profile = metadata_value(conn, "profile_id")
        rows = conn.execute(
            """
            SELECT eval_key, eval_status, eval_source, winning_side
            FROM evaluations
            """
        )
        evaluations = {
            str(eval_key): (str(eval_status), str(eval_source), str(winning_side))
            for eval_key, eval_status, eval_source, winning_side in rows
        }
    finally:
        conn.close()
    return profile, evaluations


def blank_aggregate(ending: str, material_label: str) -> dict[str, Any]:
    return {
        "ending": ending,
        "material_label": material_label,
        **{column: 0 for column in AGGREGATE_INTEGER_COLUMNS},
    }


def tablebase_outcome(
    *,
    eval_status: str,
    winning_side: str,
    material_side: str,
) -> str:
    if eval_status != "ok" or winning_side == "unknown" or material_side == "unknown":
        return "unknown"
    if material_side == "symmetric" and winning_side in {"white", "black"}:
        return "decisive"
    if material_side == "symmetric" and winning_side == "draw":
        return "draw"
    if material_side in {"white", "black"} and winning_side == material_side:
        return "win"
    if material_side in {"white", "black"} and winning_side == "draw":
        return "draw"
    if material_side == "white" and winning_side == "black":
        return "loss"
    if material_side == "black" and winning_side == "white":
        return "loss"
    return "unknown"


def actual_result_outcome(*, result: str, material_side: str) -> str:
    if result == "1/2-1/2":
        return "draw"
    if material_side == "symmetric" and result in {"1-0", "0-1"}:
        return "decisive"
    if material_side == "white" and result == "1-0":
        return "win"
    if material_side == "white" and result == "0-1":
        return "loss"
    if material_side == "black" and result == "0-1":
        return "win"
    if material_side == "black" and result == "1-0":
        return "loss"
    return "unknown"


def increment_aggregate(
    aggregate: dict[str, Any],
    *,
    piece_count: int,
    tablebase_threshold: int,
    eval_status: str,
    eval_source: str,
    winning_side: str,
    material_side: str,
    result: str,
) -> None:
    aggregate["total_positions"] += 1
    if eval_status == "ok":
        aggregate["evaluated_positions"] += 1
    if piece_count <= tablebase_threshold:
        aggregate["tablebase_eligible_positions"] += 1
    if eval_status == "ok" and eval_source == "tablebase":
        aggregate["tablebase_positions"] += 1
    if eval_status == "ok" and eval_source == "stockfish":
        aggregate["stockfish_positions"] += 1
    if eval_status == "skipped_non_tablebase":
        aggregate["skipped_non_tablebase_positions"] += 1
    if eval_status == "tablebase_error":
        aggregate["tablebase_error_positions"] += 1
    if eval_status == "ok" and winning_side == "white":
        aggregate["white_wins"] += 1
    if eval_status == "ok" and winning_side == "draw":
        aggregate["draws"] += 1
    if eval_status == "ok" and winning_side == "black":
        aggregate["black_wins"] += 1

    tb_outcome = tablebase_outcome(
        eval_status=eval_status,
        winning_side=winning_side,
        material_side=material_side,
    )
    result_outcome = actual_result_outcome(result=result, material_side=material_side)
    if tb_outcome == "win":
        aggregate["side_wins"] += 1
    elif tb_outcome == "draw":
        aggregate["side_draws"] += 1
    elif tb_outcome == "loss":
        aggregate["side_losses"] += 1
    elif tb_outcome == "decisive":
        aggregate["symmetric_decisive"] += 1
    else:
        aggregate["unknown_positions"] += 1

    if result == "1-0":
        aggregate["actual_white_wins"] += 1
    elif result == "1/2-1/2":
        aggregate["actual_draws"] += 1
    elif result == "0-1":
        aggregate["actual_black_wins"] += 1

    if result_outcome == "win":
        aggregate["actual_side_wins"] += 1
    elif result_outcome == "draw":
        aggregate["actual_side_draws"] += 1
    elif result_outcome == "loss":
        aggregate["actual_side_losses"] += 1
    elif result_outcome == "decisive":
        aggregate["actual_symmetric_decisive"] += 1
    else:
        aggregate["actual_unknown_results"] += 1

    crosstab_key = {
        ("win", "win"): "tb_win_result_win",
        ("win", "draw"): "tb_win_result_draw",
        ("win", "loss"): "tb_win_result_loss",
        ("win", "unknown"): "tb_win_result_unknown",
        ("draw", "win"): "tb_draw_result_win",
        ("draw", "draw"): "tb_draw_result_draw",
        ("draw", "loss"): "tb_draw_result_loss",
        ("draw", "decisive"): "tb_draw_result_decisive",
        ("draw", "unknown"): "tb_draw_result_unknown",
        ("loss", "win"): "tb_loss_result_win",
        ("loss", "draw"): "tb_loss_result_draw",
        ("loss", "loss"): "tb_loss_result_loss",
        ("loss", "unknown"): "tb_loss_result_unknown",
        ("decisive", "decisive"): "tb_decisive_result_decisive",
        ("decisive", "draw"): "tb_decisive_result_draw",
        ("decisive", "unknown"): "tb_decisive_result_unknown",
    }.get((tb_outcome, result_outcome))
    if crosstab_key:
        aggregate[crosstab_key] += 1


def export_first_marker_aggregate(
    *,
    markers_jsonl: Path,
    source_eval_db: Path,
    output_csv: Path,
    tablebase_threshold: int,
    force: bool,
) -> tuple[int, int, int]:
    if output_csv.exists() and not force:
        raise FileExistsError(f"output already exists: {output_csv} (pass --force)")

    profile, evaluations = load_evaluations(source_eval_db)
    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    rows_seen = 0
    missing_evals = 0

    with markers_jsonl.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            row = normalize_marker_row(raw, line_number=line_number, path=markers_jsonl)
            fen = str(row["fen"])
            board = chess.Board(fen)
            ending = str(row["ending"])
            piece_count = int(row["piece_count"])
            material = classify_material_side(ending, board)
            key = (ending, material.material_label)
            aggregate = aggregates.setdefault(key, blank_aggregate(*key))

            if piece_count <= tablebase_threshold:
                evaluation = evaluations.get(eval_key_for_fen(fen, profile=profile))
                if evaluation is None:
                    missing_evals += 1
                    eval_status, eval_source, winning_side = (
                        "tablebase_error",
                        "tablebase",
                        "unknown",
                    )
                else:
                    eval_status, eval_source, winning_side = evaluation
            else:
                eval_status, eval_source, winning_side = (
                    "skipped_non_tablebase",
                    "none",
                    "unknown",
                )

            increment_aggregate(
                aggregate,
                piece_count=piece_count,
                tablebase_threshold=tablebase_threshold,
                eval_status=eval_status,
                eval_source=eval_source,
                winning_side=winning_side,
                material_side=material.material_side,
                result=str(row["result"]),
            )
            rows_seen += 1
            if rows_seen % 500000 == 0:
                print(f"processed {rows_seen:,} marker row(s)", file=sys.stderr)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_csv.with_name(output_csv.name + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(AGGREGATE_COLUMNS))
        writer.writeheader()
        for key in sorted(aggregates):
            writer.writerow(aggregates[key])
    temp_path.replace(output_csv)
    return rows_seen, len(aggregates), missing_evals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export first-CQL-marker tablebase/result aggregates by reusing an "
            "existing tablebase-only evaluation DB."
        )
    )
    parser.add_argument("--markers-jsonl", required=True, type=Path)
    parser.add_argument("--source-eval-db", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--tablebase-threshold", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, aggregate_rows, missing = export_first_marker_aggregate(
        markers_jsonl=args.markers_jsonl.expanduser().resolve(),
        source_eval_db=args.source_eval_db.expanduser().resolve(),
        output_csv=args.output_csv.expanduser(),
        tablebase_threshold=args.tablebase_threshold,
        force=args.force,
    )
    print(
        f"Wrote {aggregate_rows:,} aggregate row(s) from {rows:,} first-marker row(s); "
        f"missing reused evals: {missing:,}: {args.output_csv}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
