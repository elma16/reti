#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import chess.pgn


def result_outcome_sql() -> str:
    return """
        CASE
            WHEN p.result = '1/2-1/2' THEN 'draw'
            WHEN p.material_side = 'symmetric'
              AND p.result IN ('1-0', '0-1') THEN 'decisive'
            WHEN p.material_side = 'white'
              AND p.result = '1-0' THEN 'win'
            WHEN p.material_side = 'white'
              AND p.result = '0-1' THEN 'loss'
            WHEN p.material_side = 'black'
              AND p.result = '0-1' THEN 'win'
            WHEN p.material_side = 'black'
              AND p.result = '1-0' THEN 'loss'
            ELSE 'unknown'
        END
    """


def tb_outcome_sql() -> str:
    return """
        CASE
            WHEN e.eval_status != 'ok'
              OR e.winning_side = 'unknown'
              OR p.material_side = 'unknown' THEN 'unknown'
            WHEN p.material_side = 'symmetric'
              AND e.winning_side IN ('white', 'black') THEN 'decisive'
            WHEN p.material_side = 'symmetric'
              AND e.winning_side = 'draw' THEN 'draw'
            WHEN p.material_side IN ('white', 'black')
              AND e.winning_side = p.material_side THEN 'win'
            WHEN p.material_side IN ('white', 'black')
              AND e.winning_side = 'draw' THEN 'draw'
            WHEN p.material_side = 'white'
              AND e.winning_side = 'black' THEN 'loss'
            WHEN p.material_side = 'black'
              AND e.winning_side = 'white' THEN 'loss'
            ELSE 'unknown'
        END
    """


def select_marker_rows(
    conn: sqlite3.Connection,
    *,
    ending: str,
    result_outcome: str,
) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"""
        WITH classified AS (
            SELECT
                p.output_pgn,
                p.source_pgn,
                p.game_index,
                p.game_key,
                p.event,
                p.site,
                p.date,
                p.round,
                p.white,
                p.black,
                p.result,
                p.ply_index,
                p.fullmove_number,
                p.move_san,
                p.fen,
                p.material_side,
                p.material_label,
                p.material_signature,
                e.eval_source,
                e.winning_side,
                e.tb_wdl,
                {tb_outcome_sql()} AS tb_outcome,
                {result_outcome_sql()} AS result_outcome
            FROM positions p
            JOIN evaluations e ON e.eval_key = p.eval_key
            WHERE p.ending = ?
        )
        SELECT *
        FROM classified
        WHERE result_outcome = ?
        ORDER BY output_pgn, game_index, ply_index
        """,
        (ending, result_outcome),
    ).fetchall()


def output_pgn_path(run_dir: Path, output_pgn: str) -> Path:
    path = Path(output_pgn)
    if path.is_absolute():
        return path
    return run_dir / path


def game_groups(rows: list[sqlite3.Row]) -> dict[tuple[str, int], list[sqlite3.Row]]:
    grouped: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["output_pgn"]), int(row["game_index"]))].append(row)
    return dict(grouped)


def read_selected_games(
    path: Path,
    selected_indices: set[int],
) -> dict[int, chess.pgn.Game]:
    found: dict[int, chess.pgn.Game] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        game_index = 0
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            game_index += 1
            if game_index in selected_indices:
                found[game_index] = game
                if len(found) == len(selected_indices):
                    break
    return found


def annotate_game(
    game: chess.pgn.Game,
    *,
    ending: str,
    result_outcome: str,
    marker_rows: list[sqlite3.Row],
) -> chess.pgn.Game:
    first = marker_rows[0]
    game.headers["FCEEnding"] = ending
    game.headers["FCEOutcomeFilter"] = f"actual_side_{result_outcome}"
    game.headers["FCEMaterialSide"] = str(first["material_side"])
    game.headers["FCEMaterialLabel"] = str(first["material_label"])
    game.headers["FCEMarkerCount"] = str(len(marker_rows))
    game.headers["FCETBOutcomes"] = ",".join(
        f"{outcome}:{count}"
        for outcome, count in sorted(counts_by(marker_rows, "tb_outcome").items())
    )

    rows_by_ply: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in marker_rows:
        rows_by_ply[int(row["ply_index"])].append(row)

    node = game
    ply = 0
    while node.variations:
        node = node.variation(0)
        ply += 1
        if ply not in rows_by_ply:
            continue
        comments = []
        for row in rows_by_ply[ply]:
            comments.append(
                "FCE marker "
                f"{ending}: actual side result={row['result_outcome']}; "
                f"tablebase={row['tb_outcome']}; "
                f"material side={row['material_side']}; "
                f"winning side={row['winning_side']}; "
                f"FEN={row['fen']}"
            )
        marker_comment = " ".join(comments)
        node.comment = f"{node.comment} {marker_comment}".strip()
    return game


def counts_by(rows: list[sqlite3.Row], column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row[column])
        counts[key] = counts.get(key, 0) + 1
    return counts


def write_games(
    *,
    run_dir: Path,
    output_pgn: Path,
    ending: str,
    result_outcome: str,
    marker_rows: list[sqlite3.Row],
) -> tuple[int, int]:
    groups = game_groups(marker_rows)
    output_pgn.parent.mkdir(parents=True, exist_ok=True)
    exported_games = 0
    exported_markers = 0
    with output_pgn.open("w", encoding="utf-8", newline="\n") as handle:
        for relative_output in sorted({key[0] for key in groups}):
            selected = {
                game_index
                for (output, game_index) in groups
                if output == relative_output
            }
            source_path = output_pgn_path(run_dir, relative_output)
            games = read_selected_games(source_path, selected)
            missing = sorted(selected.difference(games))
            if missing:
                raise RuntimeError(
                    f"{source_path}: missing selected game index(es): "
                    + ", ".join(str(index) for index in missing)
                )
            for game_index in sorted(selected):
                rows = groups[(relative_output, game_index)]
                game = annotate_game(
                    games[game_index],
                    ending=ending,
                    result_outcome=result_outcome,
                    marker_rows=rows,
                )
                print(game, file=handle, end="\n\n")
                exported_games += 1
                exported_markers += len(rows)
    return exported_games, exported_markers


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export FCE games matching an aggregate actual-result outcome."
    )
    parser.add_argument("--db", required=True, help="FCE evaluation SQLite database")
    parser.add_argument("--run-dir", required=True, help="FCE CQL run directory")
    parser.add_argument("--ending", required=True, help="FCE ending stem, e.g. 1-4BN")
    parser.add_argument(
        "--result-outcome",
        required=True,
        choices=("win", "draw", "loss", "decisive", "unknown"),
        help="Actual result outcome from the material side.",
    )
    parser.add_argument("--output-pgn", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    output_pgn = Path(args.output_pgn).expanduser().resolve()
    with sqlite3.connect(db_path) as conn:
        rows = select_marker_rows(
            conn,
            ending=args.ending,
            result_outcome=args.result_outcome,
        )
    if not rows:
        print("No matching marker rows found.")
        return 1
    game_count, marker_count = write_games(
        run_dir=run_dir,
        output_pgn=output_pgn,
        ending=args.ending,
        result_outcome=args.result_outcome,
        marker_rows=rows,
    )
    print(
        f"Wrote {game_count} unique game(s), {marker_count} marker row(s): {output_pgn}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
