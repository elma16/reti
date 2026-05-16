from __future__ import annotations

import argparse
import csv
import errno
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chess

from reti.fce_combined_snapshot import (
    DEFAULT_COMBINED_CQL,
    CombinedSourceStats,
    build_combined_snapshot_payload,
    build_combined_manifest,
    known_combined_stems,
    load_source_totals,
    parse_combined_summary,
)
from reti.fce_eval_snapshot import (
    AGGREGATE_COLUMNS,
    AGGREGATE_INTEGER_COLUMNS,
    DEFAULT_TABLEBASE_THRESHOLD,
    classify_material_side,
    eval_key_for_fen,
    profile_id,
)
from reti.fce_snapshot import (
    REPO_ROOT,
    SCHEMA_VERSION,
    SnapshotBuildResult,
    SnapshotError,
    TABLEBASE_ACTUAL_RESULT_FIELDS,
    TABLEBASE_CROSSTAB_FIELDS,
    TABLEBASE_WDL_INTEGER_FIELDS,
    aggregate_tablebase_wdl_rows,
    build_tablebase_wdl_section,
    canonical_json,
    file_signature,
    load_json,
    manifest_fingerprint,
    render_snapshot_html,
    tablebase_wdl_row_payload,
    write_json,
    write_summary_by_ending_csv,
)


DEFAULT_THRESHOLDS = (1, 2, 5, 10, 20)
DEFAULT_PGN_UTILS_BIN = (
    REPO_ROOT / "native" / "pgn-utils" / "target" / "release" / "reti-pgn-utils"
)
FACT_SCHEMA_VERSION = 1


class CombinedTablebaseSnapshotError(SnapshotError):
    pass


@dataclass(frozen=True)
class CombinedTablebaseBuildResult(SnapshotBuildResult):
    db_path: Path | None = None
    aggregate_csv_path: Path | None = None
    facts_jsonl_path: Path | None = None


def log_phase(message: str, *, enabled: bool = True) -> None:
    if enabled:
        print(
            f"[{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}] {message}",
            file=sys.stderr,
            flush=True,
        )


def create_progress_bar(
    *,
    enabled: bool,
    total: int,
    desc: str,
    unit: str,
    unit_scale: bool = False,
) -> Any | None:
    if not enabled:
        return None
    try:
        from tqdm import tqdm
    except Exception:
        return None
    return tqdm(
        total=total,
        desc=desc,
        unit=unit,
        unit_scale=unit_scale,
        dynamic_ncols=True,
    )


def parse_thresholds(raw: str | None) -> tuple[int, ...]:
    if raw is None or not raw.strip():
        return DEFAULT_THRESHOLDS
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value <= 0:
            raise CombinedTablebaseSnapshotError("thresholds must be positive integers")
        values.append(value)
    unique = tuple(sorted(set(values)))
    if 1 not in unique:
        raise CombinedTablebaseSnapshotError("thresholds must include 1")
    return unique


def syzygy_signature(paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    signatures = []
    for directory in paths:
        expanded = directory.expanduser().resolve()
        if not expanded.is_dir():
            raise CombinedTablebaseSnapshotError(
                f"Syzygy directory does not exist: {expanded}"
            )
        files = [path for path in expanded.iterdir() if path.is_file()]
        signatures.append(
            {
                "path": str(expanded),
                "fileCount": len(files),
                "sizeBytes": sum(path.stat().st_size for path in files),
                "maxMtimeNs": max((path.stat().st_mtime_ns for path in files), default=0),
            }
        )
    return signatures


def tablebase_manifest(
    *,
    annotated_run_dir: Path,
    corpus_dir: Path,
    output_dir: Path,
    title: str,
    combined_cql: Path,
    source_totals_json: Path,
    syzygy_dirs: tuple[Path, ...],
    thresholds: tuple[int, ...],
    tablebase_threshold: int,
    pgn_utils_bin: Path,
    facts_jsonl: Path | None,
    keep_intermediates: bool,
) -> tuple[dict[str, Any], Any]:
    manifest, summary_rows = build_combined_manifest(
        annotated_run_dir=annotated_run_dir,
        corpus_dir=corpus_dir,
        output_dir=output_dir,
        title=title,
        combined_cql=combined_cql,
        source_totals_json=source_totals_json,
        hash_source_pgns=False,
        hash_annotated_pgns=False,
    )
    manifest["kind"] = "fce-combined-tablebase-snapshot"
    manifest["inputs"]["sourceTotalsJson"] = file_signature(
        source_totals_json,
        include_hash=True,
    )
    if facts_jsonl is not None:
        manifest["inputs"]["factsJsonl"] = file_signature(facts_jsonl, include_hash=True)
    manifest["settings"].update(
        {
            "thresholds": list(thresholds),
            "tablebaseThreshold": tablebase_threshold,
            "evaluation": "syzygy-wdl-le-5",
            "evaluationEngine": "rust-shakmaty-syzygy",
            "positionSelection": "first-marker-per-game-stem",
            "thresholdSemantics": "first-stem-run-length",
            "syzygyDirs": syzygy_signature(syzygy_dirs),
            "pgnUtilsBin": (
                file_signature(pgn_utils_bin, include_hash=False)
                if pgn_utils_bin.exists()
                else {"path": str(pgn_utils_bin), "missing": True}
            ),
            "keepIntermediates": keep_intermediates,
        }
    )
    manifest["fingerprint"] = manifest_fingerprint(manifest)
    return manifest, summary_rows


def existing_manifest_matches(output_dir: Path, manifest: dict[str, Any]) -> bool:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        existing = load_json(manifest_path)
    except Exception:
        return False
    if existing != manifest:
        return False
    db_path = output_dir / "evaluations.sqlite3"
    snapshot_path = output_dir / "snapshot.json"
    status = None
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'build_status'"
            ).fetchone()
            status = row[0] if row else None
        finally:
            conn.close()
    return snapshot_path.exists() and db_path.exists() and status == "complete"


def init_schema(conn: sqlite3.Connection) -> None:
    integer_columns = ",\n            ".join(
        f"{column} INTEGER NOT NULL" for column in AGGREGATE_INTEGER_COLUMNS
    )
    conn.executescript(
        f"""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE game_stems (
            source_pgn TEXT NOT NULL,
            source_group TEXT NOT NULL,
            source_bucket TEXT NOT NULL,
            output_pgn TEXT NOT NULL,
            game_index INTEGER NOT NULL,
            game_key TEXT NOT NULL,
            event TEXT NOT NULL,
            site TEXT NOT NULL,
            date TEXT NOT NULL,
            round TEXT NOT NULL,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result TEXT NOT NULL,
            stem TEXT NOT NULL,
            max_run_length INTEGER NOT NULL,
            position_count INTEGER NOT NULL,
            PRIMARY KEY(source_pgn, game_key, stem)
        );

        CREATE TABLE positions (
            position_key TEXT PRIMARY KEY,
            source_pgn TEXT NOT NULL,
            source_group TEXT NOT NULL,
            source_bucket TEXT NOT NULL,
            output_pgn TEXT NOT NULL,
            game_index INTEGER NOT NULL,
            game_key TEXT NOT NULL,
            event TEXT NOT NULL,
            site TEXT NOT NULL,
            date TEXT NOT NULL,
            round TEXT NOT NULL,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result TEXT NOT NULL,
            stem TEXT NOT NULL,
            marker_index INTEGER NOT NULL,
            ply_index INTEGER NOT NULL,
            fullmove_number INTEGER NOT NULL,
            move_san TEXT NOT NULL,
            move_uci TEXT NOT NULL,
            fen TEXT NOT NULL,
            side_to_move TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            run_length INTEGER NOT NULL,
            run_start_ply INTEGER NOT NULL,
            run_end_ply INTEGER NOT NULL,
            material_side TEXT NOT NULL,
            material_label TEXT NOT NULL,
            material_signature TEXT NOT NULL,
            eval_key TEXT NOT NULL
        );

        CREATE TABLE evaluations (
            eval_key TEXT PRIMARY KEY,
            fen TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            eval_source TEXT NOT NULL DEFAULT 'pending',
            winning_side TEXT NOT NULL DEFAULT 'unknown',
            tb_wdl INTEGER,
            tb_dtz INTEGER,
            sf_cp_white INTEGER,
            sf_mate_white INTEGER,
            sf_time_seconds REAL,
            draw_threshold_cp INTEGER,
            eval_status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT NOT NULL DEFAULT '',
            evaluated_at TEXT
        );

        CREATE TABLE aggregate_wdl (
            view_key TEXT NOT NULL,
            threshold INTEGER NOT NULL,
            ending TEXT NOT NULL,
            material_label TEXT NOT NULL,
            {integer_columns},
            PRIMARY KEY(view_key, threshold, ending, material_label)
        );
        """
    )


def ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_game_stems_source_threshold
            ON game_stems(source_group, max_run_length, stem);
        CREATE INDEX IF NOT EXISTS idx_game_stems_source_game
            ON game_stems(source_pgn, game_key);
        CREATE INDEX IF NOT EXISTS idx_positions_source_threshold
            ON positions(source_group, run_length, stem);
        CREATE INDEX IF NOT EXISTS idx_positions_eval_key
            ON positions(eval_key);
        CREATE INDEX IF NOT EXISTS idx_evaluations_status
            ON evaluations(eval_status);
        """
    )
    conn.commit()


def set_metadata(conn: sqlite3.Connection, key: str, value: Any) -> None:
    if not isinstance(value, str):
        value = canonical_json(value)
    conn.execute(
        """
        INSERT INTO metadata(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def common_fact_values(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_pgn": str(raw.get("source_pgn", "")),
        "source_group": str(raw.get("source_group", "")),
        "source_bucket": str(raw.get("source_bucket", "")),
        "output_pgn": str(raw.get("output_pgn", "")),
        "game_index": int(raw.get("game_index", 0)),
        "game_key": str(raw.get("game_key", "")),
        "event": str(raw.get("event", "")),
        "site": str(raw.get("site", "")),
        "date": str(raw.get("date", "")),
        "round": str(raw.get("round", "")),
        "white": str(raw.get("white", "")),
        "black": str(raw.get("black", "")),
        "result": str(raw.get("result", "")),
        "stem": str(raw.get("stem", "")),
    }


def position_key(raw: dict[str, Any]) -> str:
    material = {
        "source_pgn": raw.get("source_pgn", ""),
        "game_key": raw.get("game_key", ""),
        "stem": raw.get("stem", ""),
        "ply_index": raw.get("ply_index", 0),
        "fen": raw.get("fen", ""),
    }
    import hashlib

    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def ingest_facts(
    conn: sqlite3.Connection,
    facts_jsonl: Path,
    *,
    known_stems: set[str],
    profile: str,
    tablebase_threshold: int,
    show_progress: bool = False,
) -> tuple[int, int]:
    game_stems_seen = 0
    positions_seen = 0
    facts_size = facts_jsonl.stat().st_size
    bytes_seen = 0
    pending_progress_bytes = 0
    progress = create_progress_bar(
        enabled=show_progress,
        total=facts_size,
        desc="Ingest marker facts",
        unit="B",
        unit_scale=True,
    )
    set_metadata(conn, "build_phase", "ingesting_facts")
    set_metadata(conn, "facts_bytes_total", str(facts_size))
    set_metadata(conn, "facts_bytes_read", "0")
    set_metadata(conn, "facts_lines_seen", "0")
    set_metadata(conn, "game_stems_ingested_progress", "0")
    set_metadata(conn, "positions_ingested_progress", "0")
    conn.commit()
    insert_game_stem = """
        INSERT OR IGNORE INTO game_stems (
            source_pgn, source_group, source_bucket, output_pgn,
            game_index, game_key, event, site, date, round, white, black, result,
            stem, max_run_length, position_count
        ) VALUES (
            :source_pgn, :source_group, :source_bucket, :output_pgn,
            :game_index, :game_key, :event, :site, :date, :round, :white, :black, :result,
            :stem, :max_run_length, :position_count
        )
    """
    insert_position = """
        INSERT OR IGNORE INTO positions (
            position_key, source_pgn, source_group, source_bucket, output_pgn,
            game_index, game_key, event, site, date, round, white, black, result,
            stem, marker_index, ply_index, fullmove_number, move_san, move_uci,
            fen, side_to_move, piece_count, run_length, run_start_ply, run_end_ply,
            material_side, material_label, material_signature, eval_key
        ) VALUES (
            :position_key, :source_pgn, :source_group, :source_bucket, :output_pgn,
            :game_index, :game_key, :event, :site, :date, :round, :white, :black, :result,
            :stem, :marker_index, :ply_index, :fullmove_number, :move_san, :move_uci,
            :fen, :side_to_move, :piece_count, :run_length, :run_start_ply, :run_end_ply,
            :material_side, :material_label, :material_signature, :eval_key
        )
    """

    line_number = 0
    try:
        with facts_jsonl.open("rb") as handle:
            for line_number, line in enumerate(handle, start=1):
                line_bytes = len(line)
                bytes_seen += line_bytes
                pending_progress_bytes += line_bytes
                if progress is not None and pending_progress_bytes >= 1024 * 1024:
                    progress.update(pending_progress_bytes)
                    pending_progress_bytes = 0
                if not line.strip():
                    continue
                raw = json.loads(line)
                if raw.get("schema_version") != FACT_SCHEMA_VERSION:
                    raise CombinedTablebaseSnapshotError(
                        f"{facts_jsonl}:{line_number}: unsupported schema_version"
                    )
                stem = str(raw.get("stem", ""))
                if stem not in known_stems:
                    raise CombinedTablebaseSnapshotError(
                        f"{facts_jsonl}:{line_number}: unknown stem {stem!r}"
                    )
                values = common_fact_values(raw)
                kind = raw.get("kind")
                if kind == "game_stem":
                    values.update(
                        {
                            "max_run_length": int(raw.get("max_run_length", 0)),
                            "position_count": int(raw.get("position_count", 0)),
                        }
                    )
                    conn.execute(insert_game_stem, values)
                    game_stems_seen += 1
                elif kind == "position":
                    piece_count = int(raw.get("piece_count", 0))
                    if piece_count > tablebase_threshold:
                        continue
                    fen = str(raw["fen"])
                    board = chess.Board(fen)
                    material = classify_material_side(stem, board)
                    eval_key = eval_key_for_fen(fen, profile=profile)
                    values.update(
                        {
                            "position_key": position_key(raw),
                            "marker_index": int(raw.get("marker_index", 0)),
                            "ply_index": int(raw.get("ply_index", 0)),
                            "fullmove_number": int(raw.get("fullmove_number", 0)),
                            "move_san": str(raw.get("move_san", "")),
                            "move_uci": str(raw.get("move_uci", "")),
                            "fen": fen,
                            "side_to_move": str(raw.get("side_to_move", "")),
                            "piece_count": piece_count,
                            "run_length": int(raw.get("run_length", 0)),
                            "run_start_ply": int(raw.get("run_start_ply", 0)),
                            "run_end_ply": int(raw.get("run_end_ply", 0)),
                            "material_side": material.material_side,
                            "material_label": material.material_label,
                            "material_signature": material.material_signature,
                            "eval_key": eval_key,
                        }
                    )
                    conn.execute(insert_position, values)
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO evaluations(eval_key, fen, piece_count)
                        VALUES (?, ?, ?)
                        """,
                        (eval_key, fen, piece_count),
                    )
                    positions_seen += 1
                else:
                    raise CombinedTablebaseSnapshotError(
                        f"{facts_jsonl}:{line_number}: unknown fact kind {kind!r}"
                    )
                if (game_stems_seen + positions_seen) % 50000 == 0:
                    set_metadata(conn, "facts_bytes_read", str(bytes_seen))
                    set_metadata(conn, "facts_lines_seen", str(line_number))
                    set_metadata(conn, "game_stems_ingested_progress", str(game_stems_seen))
                    set_metadata(conn, "positions_ingested_progress", str(positions_seen))
                    conn.commit()
    finally:
        if progress is not None:
            if pending_progress_bytes:
                progress.update(pending_progress_bytes)
            progress.close()

    set_metadata(conn, "facts_bytes_read", str(bytes_seen))
    set_metadata(conn, "facts_lines_seen", str(line_number))
    set_metadata(conn, "game_stems_ingested_progress", str(game_stems_seen))
    set_metadata(conn, "positions_ingested_progress", str(positions_seen))
    conn.commit()
    return game_stems_seen, positions_seen


def source_group_where(view_key: str, alias: str = "") -> tuple[str, dict[str, Any]]:
    prefix = f"{alias}." if alias else ""
    if view_key == "all":
        return "", {}
    if view_key in {"otb", "online"}:
        return f" AND {prefix}source_group = :source_group", {"source_group": view_key}
    raise CombinedTablebaseSnapshotError(f"unknown dataset view {view_key!r}")


def aggregate_wdl_for_view(
    conn: sqlite3.Connection,
    *,
    view_key: str,
    threshold: int,
    tablebase_threshold: int,
) -> list[dict[str, Any]]:
    where_group, params = source_group_where(view_key, "p")
    params = {**params, "threshold": threshold, "tablebase_threshold": tablebase_threshold}
    select_columns = ", ".join(AGGREGATE_COLUMNS)
    rows = conn.execute(
        f"""
        WITH classified AS (
            SELECT
                p.stem AS ending,
                p.material_label,
                p.piece_count,
                p.material_side,
                p.result,
                e.eval_status,
                e.eval_source,
                e.winning_side,
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
                END AS tb_outcome,
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
                END AS result_outcome
            FROM positions p
            JOIN evaluations e ON e.eval_key = p.eval_key
            WHERE p.run_length >= :threshold
            {where_group}
        )
        SELECT
            ending,
            material_label,
            COUNT(*) AS total_positions,
            SUM(CASE WHEN eval_status = 'ok' THEN 1 ELSE 0 END) AS evaluated_positions,
            SUM(CASE WHEN piece_count <= :tablebase_threshold THEN 1 ELSE 0 END) AS tablebase_eligible_positions,
            SUM(CASE WHEN eval_status = 'ok' AND eval_source = 'tablebase' THEN 1 ELSE 0 END) AS tablebase_positions,
            0 AS stockfish_positions,
            0 AS skipped_non_tablebase_positions,
            SUM(CASE WHEN eval_status = 'tablebase_error' THEN 1 ELSE 0 END) AS tablebase_error_positions,
            SUM(CASE WHEN eval_status = 'ok' AND winning_side = 'white' THEN 1 ELSE 0 END) AS white_wins,
            SUM(CASE WHEN eval_status = 'ok' AND winning_side = 'draw' THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN eval_status = 'ok' AND winning_side = 'black' THEN 1 ELSE 0 END) AS black_wins,
            SUM(CASE WHEN tb_outcome = 'win' THEN 1 ELSE 0 END) AS side_wins,
            SUM(CASE WHEN tb_outcome = 'draw' THEN 1 ELSE 0 END) AS side_draws,
            SUM(CASE WHEN tb_outcome = 'loss' THEN 1 ELSE 0 END) AS side_losses,
            SUM(CASE WHEN tb_outcome = 'decisive' THEN 1 ELSE 0 END) AS symmetric_decisive,
            SUM(CASE WHEN tb_outcome = 'unknown' THEN 1 ELSE 0 END) AS unknown_positions,
            SUM(CASE WHEN result = '1-0' THEN 1 ELSE 0 END) AS actual_white_wins,
            SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) AS actual_draws,
            SUM(CASE WHEN result = '0-1' THEN 1 ELSE 0 END) AS actual_black_wins,
            SUM(CASE WHEN result_outcome = 'win' THEN 1 ELSE 0 END) AS actual_side_wins,
            SUM(CASE WHEN result_outcome = 'draw' THEN 1 ELSE 0 END) AS actual_side_draws,
            SUM(CASE WHEN result_outcome = 'loss' THEN 1 ELSE 0 END) AS actual_side_losses,
            SUM(CASE WHEN result_outcome = 'decisive' THEN 1 ELSE 0 END) AS actual_symmetric_decisive,
            SUM(CASE WHEN result_outcome = 'unknown' THEN 1 ELSE 0 END) AS actual_unknown_results,
            SUM(CASE WHEN tb_outcome = 'win' AND result_outcome = 'win' THEN 1 ELSE 0 END) AS tb_win_result_win,
            SUM(CASE WHEN tb_outcome = 'win' AND result_outcome = 'draw' THEN 1 ELSE 0 END) AS tb_win_result_draw,
            SUM(CASE WHEN tb_outcome = 'win' AND result_outcome = 'loss' THEN 1 ELSE 0 END) AS tb_win_result_loss,
            SUM(CASE WHEN tb_outcome = 'win' AND result_outcome = 'unknown' THEN 1 ELSE 0 END) AS tb_win_result_unknown,
            SUM(CASE WHEN tb_outcome = 'draw' AND result_outcome = 'win' THEN 1 ELSE 0 END) AS tb_draw_result_win,
            SUM(CASE WHEN tb_outcome = 'draw' AND result_outcome = 'draw' THEN 1 ELSE 0 END) AS tb_draw_result_draw,
            SUM(CASE WHEN tb_outcome = 'draw' AND result_outcome = 'loss' THEN 1 ELSE 0 END) AS tb_draw_result_loss,
            SUM(CASE WHEN tb_outcome = 'draw' AND result_outcome = 'decisive' THEN 1 ELSE 0 END) AS tb_draw_result_decisive,
            SUM(CASE WHEN tb_outcome = 'draw' AND result_outcome = 'unknown' THEN 1 ELSE 0 END) AS tb_draw_result_unknown,
            SUM(CASE WHEN tb_outcome = 'loss' AND result_outcome = 'win' THEN 1 ELSE 0 END) AS tb_loss_result_win,
            SUM(CASE WHEN tb_outcome = 'loss' AND result_outcome = 'draw' THEN 1 ELSE 0 END) AS tb_loss_result_draw,
            SUM(CASE WHEN tb_outcome = 'loss' AND result_outcome = 'loss' THEN 1 ELSE 0 END) AS tb_loss_result_loss,
            SUM(CASE WHEN tb_outcome = 'loss' AND result_outcome = 'unknown' THEN 1 ELSE 0 END) AS tb_loss_result_unknown,
            SUM(CASE WHEN tb_outcome = 'decisive' AND result_outcome = 'decisive' THEN 1 ELSE 0 END) AS tb_decisive_result_decisive,
            SUM(CASE WHEN tb_outcome = 'decisive' AND result_outcome = 'draw' THEN 1 ELSE 0 END) AS tb_decisive_result_draw,
            SUM(CASE WHEN tb_outcome = 'decisive' AND result_outcome = 'unknown' THEN 1 ELSE 0 END) AS tb_decisive_result_unknown
        FROM classified
        GROUP BY ending, material_label
        ORDER BY ending, material_label
        """,
        params,
    ).fetchall()
    return [{column: row[column] for column in select_columns.split(", ")} for row in rows]


def refresh_threshold_aggregates(
    conn: sqlite3.Connection,
    *,
    thresholds: tuple[int, ...],
    tablebase_threshold: int,
    show_progress: bool = False,
    progress_callback: Any | None = None,
) -> int:
    conn.execute("DELETE FROM aggregate_wdl")
    insert_columns = ("view_key", "threshold", *AGGREGATE_COLUMNS)
    placeholders = ", ".join("?" for _ in insert_columns)
    inserted = 0
    total_steps = 3 * len(thresholds)
    step = 0
    progress = create_progress_bar(
        enabled=show_progress,
        total=total_steps,
        desc="Aggregate views",
        unit="view",
    )
    for view_key in ("all", "otb", "online"):
        for threshold in thresholds:
            step += 1
            if progress_callback is not None:
                progress_callback(step, total_steps, view_key, threshold)
            for row in aggregate_wdl_for_view(
                conn,
                view_key=view_key,
                threshold=threshold,
                tablebase_threshold=tablebase_threshold,
            ):
                conn.execute(
                    f"""
                    INSERT INTO aggregate_wdl ({", ".join(insert_columns)})
                    VALUES ({placeholders})
                    """,
                    (view_key, threshold, *[row[column] for column in AGGREGATE_COLUMNS]),
                )
                inserted += 1
            conn.commit()
            if progress is not None:
                progress.update(1)
    if progress is not None:
        progress.close()
    return inserted


def histogram_from_rows(rows: list[sqlite3.Row], key: str, value: str) -> dict[int, int]:
    return {int(row[key]): int(row[value]) for row in rows}


def source_stats_from_db(
    conn: sqlite3.Connection,
    *,
    summary_rows: Any,
    source_totals: dict[str, int],
    known_stems: set[str],
    show_progress: bool = False,
) -> list[CombinedSourceStats]:
    stats = []
    progress = create_progress_bar(
        enabled=show_progress,
        total=len(summary_rows),
        desc="Build source stats",
        unit="source",
    )
    for summary_row in summary_rows:
        if progress is not None:
            progress.set_postfix_str(summary_row.source_stem[-32:])
        source = summary_row.source_pgn
        matched_games = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT game_key FROM game_stems
                    WHERE source_pgn = ?
                    GROUP BY game_key
                )
                """,
                (source,),
            ).fetchone()[0]
        )
        if matched_games != summary_row.expected_matched_games:
            raise CombinedTablebaseSnapshotError(
                f"{summary_row.output_path} produced {matched_games:,} matched game(s), "
                f"but summary.csv reports {summary_row.expected_matched_games:,}"
            )
        incidence_total = int(
            conn.execute(
                "SELECT COUNT(*) FROM game_stems WHERE source_pgn = ?",
                (source,),
            ).fetchone()[0]
        )
        counts = {stem: 0 for stem in known_stems}
        for row in conn.execute(
            """
            SELECT stem, COUNT(*) AS n
            FROM game_stems
            WHERE source_pgn = ?
            GROUP BY stem
            """,
            (source,),
        ):
            counts[str(row["stem"])] = int(row["n"])
        run_length_histograms = {stem: {} for stem in known_stems}
        for row in conn.execute(
            """
            SELECT stem, max_run_length, COUNT(*) AS n
            FROM game_stems
            WHERE source_pgn = ?
            GROUP BY stem, max_run_length
            """,
            (source,),
        ):
            run_length_histograms[str(row["stem"])][int(row["max_run_length"])] = int(row["n"])
        incidence_histogram = histogram_from_rows(
            conn.execute(
                """
                SELECT max_run_length, COUNT(*) AS n
                FROM game_stems
                WHERE source_pgn = ?
                GROUP BY max_run_length
                """,
                (source,),
            ).fetchall(),
            "max_run_length",
            "n",
        )
        matched_game_histogram = histogram_from_rows(
            conn.execute(
                """
                SELECT game_run, COUNT(*) AS n
                FROM (
                    SELECT game_key, MAX(max_run_length) AS game_run
                    FROM game_stems
                    WHERE source_pgn = ?
                    GROUP BY game_key
                )
                GROUP BY game_run
                """,
                (source,),
            ).fetchall(),
            "game_run",
            "n",
        )
        stats.append(
            CombinedSourceStats(
                row=summary_row,
                original_games=source_totals[source],
                matched_games=matched_games,
                incidence_total=incidence_total,
                counts=counts,
                run_length_histograms=run_length_histograms,
                incidence_run_length_histogram=incidence_histogram,
                matched_game_run_length_histogram=matched_game_histogram,
            )
        )
        if progress is not None:
            progress.update(1)
    if progress is not None:
        progress.close()
    return stats


def incidence_for_view_threshold(
    conn: sqlite3.Connection,
    *,
    view_key: str,
    threshold: int,
    total_games: int,
) -> dict[str, Any]:
    where_group, params = source_group_where(view_key)
    params = {**params, "threshold": threshold}
    matched_rows = int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM game_stems
            WHERE max_run_length >= :threshold
            {where_group}
            """,
            params,
        ).fetchone()[0]
    )
    matched_games = int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT source_pgn, game_key
                FROM game_stems
                WHERE max_run_length >= :threshold
                {where_group}
                GROUP BY source_pgn, game_key
            )
            """,
            params,
        ).fetchone()[0]
    )
    rows: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        f"""
        SELECT stem, COUNT(*) AS quantity
        FROM game_stems
        WHERE max_run_length >= :threshold
        {where_group}
        GROUP BY stem
        """,
        params,
    ):
        quantity = int(row["quantity"])
        rows[str(row["stem"])] = {
            "quantity": quantity,
            "percentage": quantity / total_games * 100.0 if total_games else None,
            "matchedShare": quantity / matched_rows * 100.0 if matched_rows else None,
        }
    source_buckets: dict[str, Any] = {}
    for row in conn.execute(
        f"""
        SELECT source_pgn,
               COUNT(*) AS incidences,
               COUNT(DISTINCT game_key) AS matched_games
        FROM game_stems
        WHERE max_run_length >= :threshold
        {where_group}
        GROUP BY source_pgn
        """,
        params,
    ):
        source_buckets[str(row["source_pgn"])] = {
            "incidences": int(row["incidences"]),
            "matchedGames": int(row["matched_games"]),
        }
    return {
        "matchedRows": matched_rows,
        "matchedGames": matched_games,
        "rows": rows,
        "sourceBuckets": source_buckets,
    }


def aggregate_rows_by_ending(
    conn: sqlite3.Connection,
    *,
    view_key: str,
    threshold: int,
) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        f"""
        SELECT {", ".join(AGGREGATE_COLUMNS)}
        FROM aggregate_wdl
        WHERE view_key = ? AND threshold = ?
        ORDER BY ending, material_label
        """,
        (view_key, threshold),
    ).fetchall()
    by_ending: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        payload = {column: row[column] for column in AGGREGATE_COLUMNS}
        by_ending.setdefault(str(payload["ending"]), []).append(payload)
    return by_ending


def attach_threshold_views(
    snapshot: dict[str, Any],
    conn: sqlite3.Connection,
    *,
    thresholds: tuple[int, ...],
    aggregate_csv: Path,
) -> None:
    views = snapshot["datasetViews"]["views"]
    known_stems = {str(row["stem"]) for row in snapshot["rows"]}
    known_stems.update(
        str(aux["stem"])
        for row in snapshot["rows"]
        for aux in row.get("auxiliaryRows", [])
    )
    default_stats: dict[str, Any] = {}
    default_section: dict[str, Any] | None = None
    for view_key, view in views.items():
        threshold_views: dict[str, Any] = {}
        for threshold in thresholds:
            total_games = int(view["totalGames"])
            incidence = incidence_for_view_threshold(
                conn,
                view_key=view_key,
                threshold=threshold,
                total_games=total_games,
            )
            material_rows = aggregate_rows_by_ending(
                conn,
                view_key=view_key,
                threshold=threshold,
            )
            stats_by_stem = {
                stem: tablebase_wdl_row_payload(
                    material_rows.get(stem, []),
                    position_basis=(
                        f"first <=5-man marker position per game/stem in {view_key} "
                        f"games with first stem run length >= {threshold}"
                    ),
                )
                for stem in known_stems
            }
            stats_by_stem = {
                stem: stats for stem, stats in stats_by_stem.items() if stats is not None
            }
            section = build_tablebase_wdl_section(
                material_rows,
                source_csv=aggregate_csv,
                position_basis=(
                    f"first <=5-man marker position per game/stem in {view_key} "
                    f"games with first stem run length >= {threshold}"
                ),
            )
            section["viewKey"] = view_key
            section["threshold"] = threshold
            rows: dict[str, Any] = {}
            for stem in known_stems:
                base = incidence["rows"].get(
                    stem,
                    {
                        "quantity": 0,
                        "percentage": 0.0 if total_games else None,
                        "matchedShare": 0.0 if incidence["matchedRows"] else None,
                    },
                )
                row_payload = dict(base)
                if stem in stats_by_stem:
                    row_payload["tablebaseWdl"] = stats_by_stem[stem]
                rows[stem] = row_payload
            threshold_views[str(threshold)] = {
                "metrics": {
                    "totalGames": total_games,
                    "matchedGames": incidence["matchedGames"],
                    "matchedRows": incidence["matchedRows"],
                    "sourceBuckets": int(view["sourceBuckets"]),
                    "tablebasePositions": int(section["totals"]["evaluated_positions"]),
                    "tablebaseEndings": int(section["endingCount"]),
                },
                "sourceBuckets": incidence["sourceBuckets"],
                "tablebaseWdl": section,
                "rows": rows,
            }
            if view_key == "all" and threshold == 1:
                default_section = section
                default_stats = stats_by_stem
        view["thresholdViews"] = threshold_views

    if default_section is not None:
        snapshot["tablebaseMode"] = "combined-filtered"
        snapshot["tablebaseWdl"] = default_section
        for row in snapshot["rows"]:
            stats = default_stats.get(str(row["stem"]))
            if stats is not None:
                row["tablebaseWdl"] = stats
            for auxiliary in row.get("auxiliaryRows", []):
                stats = default_stats.get(str(auxiliary["stem"]))
                if stats is not None:
                    auxiliary["tablebaseWdl"] = stats


def write_aggregate_csv(conn: sqlite3.Connection, output_csv: Path) -> None:
    fieldnames = ["view_key", "threshold", *AGGREGATE_COLUMNS]
    rows = conn.execute(
        f"""
        SELECT {", ".join(fieldnames)}
        FROM aggregate_wdl
        ORDER BY view_key, threshold, ending, material_label
        """
    ).fetchall()
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fieldnames})


def run_rust_extractor(
    *,
    pgn_utils_bin: Path,
    annotated_run_dir: Path,
    facts_jsonl: Path,
    known_stems: set[str],
    tablebase_threshold: int,
    show_progress: bool,
) -> None:
    if not pgn_utils_bin.exists():
        raise CombinedTablebaseSnapshotError(
            f"Missing Rust PGN utility: {pgn_utils_bin}. Build it with "
            "`cargo build --release --manifest-path native/pgn-utils/Cargo.toml`."
        )
    cmd = [
        str(pgn_utils_bin),
        "fce-combined-markers",
        "--relative-to",
        str(annotated_run_dir),
        "--known-stems",
        ",".join(sorted(known_stems)),
        "--max-pieces",
        str(tablebase_threshold),
        "-o",
        str(facts_jsonl),
        str(annotated_run_dir),
    ]
    if not show_progress:
        cmd.insert(2, "--no-progress")
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        raise CombinedTablebaseSnapshotError(
            f"Rust combined marker extraction failed with exit code {completed.returncode}"
        )


def run_rust_sqlite_ingest(
    *,
    pgn_utils_bin: Path,
    annotated_run_dir: Path,
    db_path: Path,
    known_stems: set[str],
    profile: str,
    tablebase_threshold: int,
    sqlite_batch_rows: int,
    show_progress: bool,
) -> tuple[int, int]:
    if not pgn_utils_bin.exists():
        raise CombinedTablebaseSnapshotError(
            f"Missing Rust PGN utility: {pgn_utils_bin}. Build it with "
            "`cargo build --release --manifest-path native/pgn-utils/Cargo.toml`."
        )
    cmd = [
        str(pgn_utils_bin),
        "fce-combined-markers",
        "--relative-to",
        str(annotated_run_dir),
        "--known-stems",
        ",".join(sorted(known_stems)),
        "--max-pieces",
        str(tablebase_threshold),
        "--sqlite-db",
        str(db_path),
        "--profile-id",
        profile,
        "--sqlite-batch-rows",
        str(sqlite_batch_rows),
        str(annotated_run_dir),
    ]
    if not show_progress:
        cmd.insert(2, "--no-progress")
    completed = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, end="", file=sys.stderr)
        raise CombinedTablebaseSnapshotError(
            f"Rust SQLite marker ingest failed with exit code {completed.returncode}"
        )
    stats_line = ""
    for line in completed.stdout.splitlines():
        if line.strip():
            stats_line = line.strip()
    try:
        stats = json.loads(stats_line)
    except Exception as exc:
        raise CombinedTablebaseSnapshotError(
            f"Rust SQLite marker ingest did not return JSON stats: {stats_line!r}"
        ) from exc
    return int(stats.get("game_stems_written", 0)), int(stats.get("positions_written", 0))


def run_rust_syzygy_eval(
    *,
    pgn_utils_bin: Path,
    db_path: Path,
    syzygy_dirs: tuple[Path, ...],
    tablebase_threshold: int,
    batch_rows: int,
    workers: int,
    show_progress: bool,
) -> int:
    if not pgn_utils_bin.exists():
        raise CombinedTablebaseSnapshotError(
            f"Missing Rust PGN utility: {pgn_utils_bin}. Build it with "
            "`cargo build --release --manifest-path native/pgn-utils/Cargo.toml`."
        )
    cmd = [
        str(pgn_utils_bin),
        "fce-syzygy-eval",
        "--db",
        str(db_path),
        "--max-pieces",
        str(tablebase_threshold),
        "--batch-rows",
        str(batch_rows),
        "--workers",
        str(max(1, workers)),
    ]
    for syzygy_dir in syzygy_dirs:
        cmd.extend(["--syzygy-dir", str(syzygy_dir)])
    if not show_progress:
        cmd.insert(2, "--no-progress")
    completed = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, end="", file=sys.stderr)
        raise CombinedTablebaseSnapshotError(
            f"Rust Syzygy evaluation failed with exit code {completed.returncode}"
        )
    stats_line = ""
    for line in completed.stdout.splitlines():
        if line.strip():
            stats_line = line.strip()
    try:
        stats = json.loads(stats_line)
    except Exception as exc:
        raise CombinedTablebaseSnapshotError(
            f"Rust Syzygy evaluation did not return JSON stats: {stats_line!r}"
        ) from exc
    return int(stats.get("attempted", 0))


def install_output_dir(temp_dir: Path, output_dir: Path, *, force: bool) -> None:
    parent = output_dir.parent
    backup_dir: Path | None = None
    try:
        if output_dir.exists():
            if not force:
                raise CombinedTablebaseSnapshotError(f"Output directory already exists: {output_dir}")
            backup_dir = parent / f".{output_dir.name}.backup-{uuid.uuid4().hex}"
            output_dir.rename(backup_dir)
        try:
            temp_dir.rename(output_dir)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            shutil.copytree(temp_dir, output_dir)
            shutil.rmtree(temp_dir)
        if backup_dir is not None:
            shutil.rmtree(backup_dir)
    except Exception:
        if backup_dir is not None and backup_dir.exists():
            if output_dir.exists():
                shutil.rmtree(output_dir, ignore_errors=True)
            backup_dir.rename(output_dir)
        raise


def build_fce_combined_tablebase_snapshot(
    *,
    annotated_run_dir: str | Path,
    corpus_dir: str | Path,
    source_totals_json: str | Path,
    output_dir: str | Path,
    title: str,
    syzygy_dirs: tuple[str | Path, ...],
    work_dir: str | Path | None = None,
    thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS,
    combined_cql: str | Path = DEFAULT_COMBINED_CQL,
    pgn_utils_bin: str | Path = DEFAULT_PGN_UTILS_BIN,
    facts_jsonl: str | Path | None = None,
    workers: int = 1,
    tablebase_threshold: int = DEFAULT_TABLEBASE_THRESHOLD,
    sqlite_batch_rows: int = 1_000_000,
    keep_intermediates: bool = False,
    force: bool = False,
    show_progress: bool = True,
) -> CombinedTablebaseBuildResult:
    run_path = Path(annotated_run_dir).expanduser().resolve()
    corpus_path = Path(corpus_dir).expanduser().resolve()
    source_totals_path = Path(source_totals_json).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    work_path = Path(work_dir).expanduser().resolve() if work_dir else None
    cql_path = Path(combined_cql).expanduser().resolve()
    pgn_utils_path = Path(pgn_utils_bin).expanduser().resolve()
    syzygy_paths = tuple(Path(path).expanduser().resolve() for path in syzygy_dirs)
    facts_path = Path(facts_jsonl).expanduser().resolve() if facts_jsonl else None
    if not syzygy_paths:
        raise CombinedTablebaseSnapshotError("At least one --syzygy-dir is required")
    if sqlite_batch_rows <= 0:
        raise CombinedTablebaseSnapshotError("--sqlite-batch-rows must be positive")

    manifest, summary_rows = tablebase_manifest(
        annotated_run_dir=run_path,
        corpus_dir=corpus_path,
        output_dir=output_path,
        title=title,
        combined_cql=cql_path,
        source_totals_json=source_totals_path,
        syzygy_dirs=syzygy_paths,
        thresholds=thresholds,
        tablebase_threshold=tablebase_threshold,
        pgn_utils_bin=pgn_utils_path,
        facts_jsonl=facts_path,
        keep_intermediates=keep_intermediates,
    )

    if output_path.exists():
        if not output_path.is_dir():
            raise CombinedTablebaseSnapshotError(
                f"Output path exists and is not a directory: {output_path}"
            )
        if not force and existing_manifest_matches(output_path, manifest):
            return CombinedTablebaseBuildResult(
                output_dir=output_path,
                snapshot_path=output_path / "snapshot.json",
                manifest_path=output_path / "manifest.json",
                summary_csv_path=output_path / "summary_by_ending.csv",
                html_path=output_path / "index.html",
                snapshot_id=f"fce-combined-tablebase-{manifest['fingerprint'][:12]}",
                up_to_date=True,
                db_path=output_path / "evaluations.sqlite3",
                aggregate_csv_path=output_path / "tablebase_wdl_by_view_threshold.csv",
                facts_jsonl_path=(
                    output_path / "combined_marker_facts.jsonl"
                    if (output_path / "combined_marker_facts.jsonl").exists()
                    else None
                ),
            )
        if not force:
            raise CombinedTablebaseSnapshotError(
                f"{output_path} already exists but its manifest does not match "
                "the current inputs. Use --force or choose a new output directory."
            )

    log_phase("Validating cached source totals", enabled=show_progress)
    source_totals = load_source_totals(source_totals_path, summary_rows)
    known_stems = known_combined_stems()

    temp_parent = work_path or output_path.parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_path.name}.tmp-", dir=str(temp_parent)))
    committed = False
    try:
        db_path = temp_dir / "evaluations.sqlite3"
        aggregate_csv = temp_dir / "tablebase_wdl_by_view_threshold.csv"
        generated_facts = temp_dir / "combined_marker_facts.jsonl"
        active_facts = facts_path or generated_facts
        if facts_path is None:
            log_phase(
                "Phase 1/8: direct Rust PGN scan will populate SQLite (no JSONL facts file)",
                enabled=show_progress,
            )
        else:
            log_phase(f"Phase 1/8: using existing facts JSONL {facts_path}", enabled=show_progress)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            log_phase("Phase 2/8: initializing SQLite snapshot DB", enabled=show_progress)
            init_schema(conn)
            set_metadata(conn, "input_manifest", manifest)
            set_metadata(conn, "build_status", "building")
            set_metadata(conn, "build_phase", "initializing")
            set_metadata(conn, "created_at", datetime.now(timezone.utc).isoformat())
            profile = profile_id({"evaluation": manifest["settings"]})
            set_metadata(conn, "profile_id", profile)
            conn.commit()
            if facts_path is None:
                set_metadata(conn, "build_phase", "rust_sqlite_marker_ingest")
                conn.commit()
                conn.close()
                log_phase(
                    "Phase 3/8: streaming annotated PGNs into SQLite with Rust",
                    enabled=show_progress,
                )
                game_stems, positions = run_rust_sqlite_ingest(
                    pgn_utils_bin=pgn_utils_path,
                    annotated_run_dir=run_path,
                    db_path=db_path,
                    known_stems=known_stems,
                    profile=profile,
                    tablebase_threshold=tablebase_threshold,
                    sqlite_batch_rows=sqlite_batch_rows,
                    show_progress=show_progress,
                )
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
            else:
                log_phase("Phase 3/8: ingesting marker facts into SQLite", enabled=show_progress)
                game_stems, positions = ingest_facts(
                    conn,
                    active_facts,
                    known_stems=known_stems,
                    profile=profile,
                    tablebase_threshold=tablebase_threshold,
                    show_progress=show_progress,
                )
            set_metadata(conn, "game_stems_ingested", str(game_stems))
            set_metadata(conn, "positions_ingested", str(positions))
            set_metadata(conn, "build_phase", "indexing")
            conn.commit()
            log_phase("Phase 4/8: creating SQLite indexes", enabled=show_progress)
            ensure_indexes(conn)
            pending_evaluations = int(
                conn.execute(
                    "SELECT COUNT(*) FROM evaluations WHERE eval_status = 'pending'"
                ).fetchone()[0]
            )
            set_metadata(conn, "build_phase", "evaluating_syzygy")
            set_metadata(conn, "evaluations_pending_total", str(pending_evaluations))
            set_metadata(conn, "evaluations_completed_progress", "0")
            conn.commit()
            log_phase(
                f"Phase 5/8: evaluating {pending_evaluations:,} first-marker <=5-man FEN(s) with Rust Syzygy",
                enabled=show_progress,
            )
            conn.close()
            completed = run_rust_syzygy_eval(
                pgn_utils_bin=pgn_utils_path,
                db_path=db_path,
                syzygy_dirs=syzygy_paths,
                tablebase_threshold=tablebase_threshold,
                batch_rows=max(10_000, workers * 4096),
                workers=workers,
                show_progress=show_progress,
            )
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            set_metadata(conn, "evaluations_completed", str(completed))
            set_metadata(conn, "evaluations_completed_progress", str(completed))
            failed_evaluations = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM evaluations
                    WHERE eval_status != 'ok'
                    """
                ).fetchone()[0]
            )
            if failed_evaluations:
                raise CombinedTablebaseSnapshotError(
                    f"{failed_evaluations:,} tablebase evaluation(s) did not complete; "
                    "check --syzygy-dir coverage"
                )
            set_metadata(conn, "build_phase", "aggregating_threshold_views")
            set_metadata(conn, "aggregate_steps_total", str(3 * len(thresholds)))
            set_metadata(conn, "aggregate_steps_completed", "0")
            conn.commit()
            log_phase("Phase 6/8: aggregating WDL/result stats by corpus and threshold", enabled=show_progress)

            def aggregate_progress(
                step: int,
                total: int,
                view_key: str,
                threshold: int,
            ) -> None:
                set_metadata(conn, "aggregate_steps_total", str(total))
                set_metadata(conn, "aggregate_steps_completed", str(step - 1))
                set_metadata(conn, "aggregate_current_view", view_key)
                set_metadata(conn, "aggregate_current_threshold", str(threshold))
                conn.commit()

            aggregate_rows = refresh_threshold_aggregates(
                conn,
                thresholds=thresholds,
                tablebase_threshold=tablebase_threshold,
                show_progress=show_progress,
                progress_callback=aggregate_progress,
            )
            set_metadata(conn, "aggregate_rows", str(aggregate_rows))
            set_metadata(conn, "aggregate_steps_completed", str(3 * len(thresholds)))
            set_metadata(conn, "build_phase", "building_snapshot_payload")
            conn.commit()

            log_phase("Phase 7/8: building snapshot payload and HTML data", enabled=show_progress)
            source_stats = source_stats_from_db(
                conn,
                summary_rows=summary_rows,
                source_totals=source_totals,
                known_stems=known_stems,
                show_progress=show_progress,
            )
            snapshot = build_combined_snapshot_payload(
                manifest=manifest,
                source_stats=source_stats,
                title=title,
                corpus_dir=corpus_path,
            )
            snapshot["snapshotId"] = f"fce-combined-tablebase-{manifest['fingerprint'][:12]}"
            snapshot["methodology"]["tablebaseThreshold"] = tablebase_threshold
            snapshot["methodology"]["tablebasePositionFiltering"] = (
                "first <=5-man marker position per game and FCE stem; the active "
                "threshold filters by the length of that stem's first run"
            )
            write_aggregate_csv(conn, aggregate_csv)
            attach_threshold_views(
                snapshot,
                conn,
                thresholds=thresholds,
                aggregate_csv=aggregate_csv,
            )
            set_metadata(conn, "build_phase", "writing_outputs")
            set_metadata(conn, "build_status", "complete")
            set_metadata(conn, "updated_at", datetime.now(timezone.utc).isoformat())
            conn.commit()
        finally:
            conn.close()

        log_phase("Phase 8/8: writing JSON/CSV/HTML artifacts", enabled=show_progress)
        write_json(temp_dir / "snapshot.json", snapshot)
        write_json(temp_dir / "manifest.json", manifest)
        write_summary_by_ending_csv(snapshot, temp_dir / "summary_by_ending.csv")
        (temp_dir / "index.html").write_text(
            render_snapshot_html(snapshot),
            encoding="utf-8",
        )
        if facts_path is None and not keep_intermediates and generated_facts.exists():
            log_phase("Removing temporary marker facts JSONL", enabled=show_progress)
            generated_facts.unlink()
        log_phase("Installing completed snapshot directory", enabled=show_progress)
        install_output_dir(temp_dir, output_path, force=force)
        log_phase(f"Finished: {output_path}", enabled=show_progress)
        committed = True
        return CombinedTablebaseBuildResult(
            output_dir=output_path,
            snapshot_path=output_path / "snapshot.json",
            manifest_path=output_path / "manifest.json",
            summary_csv_path=output_path / "summary_by_ending.csv",
            html_path=output_path / "index.html",
            snapshot_id=snapshot["snapshotId"],
            db_path=output_path / "evaluations.sqlite3",
            aggregate_csv_path=output_path / "tablebase_wdl_by_view_threshold.csv",
            facts_jsonl_path=facts_path,
        )
    finally:
        if not committed and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a combined FCE tablebase-aware snapshot."
    )
    parser.add_argument("--annotated-run-dir", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--source-totals-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--syzygy-dir", action="append", default=[], type=Path)
    parser.add_argument(
        "--work-dir",
        type=Path,
        help=(
            "Directory for the temporary build. Use an internal SSD path here "
            "when --output-dir is on a slow external/archive drive."
        ),
    )
    parser.add_argument("--thresholds", default="1,2,5,10,20")
    parser.add_argument("--combined-cql", default=DEFAULT_COMBINED_CQL, type=Path)
    parser.add_argument("--pgn-utils-bin", default=DEFAULT_PGN_UTILS_BIN, type=Path)
    parser.add_argument("--facts-jsonl", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--tablebase-threshold", type=int, default=DEFAULT_TABLEBASE_THRESHOLD)
    parser.add_argument(
        "--sqlite-batch-rows",
        type=int,
        default=1_000_000,
        help="Rows per Rust SQLite transaction during marker ingest.",
    )
    parser.add_argument("--keep-intermediates", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_fce_combined_tablebase_snapshot(
            annotated_run_dir=args.annotated_run_dir,
            corpus_dir=args.corpus_dir,
            source_totals_json=args.source_totals_json,
            output_dir=args.output_dir,
            title=args.title,
            syzygy_dirs=tuple(args.syzygy_dir),
            work_dir=args.work_dir,
            thresholds=parse_thresholds(args.thresholds),
            combined_cql=args.combined_cql,
            pgn_utils_bin=args.pgn_utils_bin,
            facts_jsonl=args.facts_jsonl,
            workers=args.workers,
            tablebase_threshold=args.tablebase_threshold,
            sqlite_batch_rows=args.sqlite_batch_rows,
            keep_intermediates=args.keep_intermediates,
            force=args.force,
            show_progress=not args.no_progress,
        )
    except (OSError, sqlite3.Error, json.JSONDecodeError, SnapshotError) as exc:
        print(f"Error: {exc}")
        return 2
    if result.up_to_date:
        print(f"Up to date: {result.output_dir}")
    else:
        print(f"Wrote snapshot: {result.snapshot_path}")
        print(f"Wrote SQLite DB: {result.db_path}")
        print(f"Wrote HTML: {result.html_path}")
    return 0
