from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Iterable

import chess

from reti.common.hashing import canonical_json, sha256_file, sha256_text
from reti.common.source_metadata import source_stem
from reti.evaluation.backends import (
    StockfishSession,
    open_tablebase_from_directories,
)
from reti.evaluation.csv_schema import EvaluationResult, classify_side_to_move_wdl


SCHEMA_VERSION = 1
DEFAULT_DRAW_THRESHOLD_CP = 30
DEFAULT_SF_TIME_SECONDS = 0.1
DEFAULT_SF_THREADS = 1
DEFAULT_TABLEBASE_THRESHOLD = 5
AGGREGATE_ID_COLUMNS = ("ending", "material_label")
AGGREGATE_BASE_INTEGER_COLUMNS = (
    "total_positions",
    "evaluated_positions",
    "tablebase_eligible_positions",
    "tablebase_positions",
    "stockfish_positions",
    "skipped_non_tablebase_positions",
    "tablebase_error_positions",
    "white_wins",
    "draws",
    "black_wins",
    "side_wins",
    "side_draws",
    "side_losses",
    "symmetric_decisive",
    "unknown_positions",
)
AGGREGATE_ACTUAL_RESULT_COLUMNS = (
    "actual_white_wins",
    "actual_draws",
    "actual_black_wins",
    "actual_side_wins",
    "actual_side_draws",
    "actual_side_losses",
    "actual_symmetric_decisive",
    "actual_unknown_results",
)
AGGREGATE_CROSSTAB_COLUMNS = (
    "tb_win_result_win",
    "tb_win_result_draw",
    "tb_win_result_loss",
    "tb_win_result_unknown",
    "tb_draw_result_win",
    "tb_draw_result_draw",
    "tb_draw_result_loss",
    "tb_draw_result_decisive",
    "tb_draw_result_unknown",
    "tb_loss_result_win",
    "tb_loss_result_draw",
    "tb_loss_result_loss",
    "tb_loss_result_unknown",
    "tb_decisive_result_decisive",
    "tb_decisive_result_draw",
    "tb_decisive_result_unknown",
)
AGGREGATE_INTEGER_COLUMNS = (
    *AGGREGATE_BASE_INTEGER_COLUMNS,
    *AGGREGATE_ACTUAL_RESULT_COLUMNS,
    *AGGREGATE_CROSSTAB_COLUMNS,
)
AGGREGATE_COLUMNS = (*AGGREGATE_ID_COLUMNS, *AGGREGATE_INTEGER_COLUMNS)


class EvalSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvalSettings:
    markers_jsonl: Path
    output_db: Path
    syzygy_dirs: tuple[str, ...]
    stockfish_bin: str | None
    sf_time_seconds: float = DEFAULT_SF_TIME_SECONDS
    sf_threads: int = DEFAULT_SF_THREADS
    draw_threshold_cp: int = DEFAULT_DRAW_THRESHOLD_CP
    tablebase_threshold: int = DEFAULT_TABLEBASE_THRESHOLD
    tablebase_only: bool = False
    probe_dtz: bool = False
    workers: int = 1
    max_markers: int | None = None
    max_evals: int | None = None
    hash_markers: bool = False
    force: bool = False


@dataclass(frozen=True)
class EvalRunStats:
    positions_ingested: int
    evaluations_pending_before: int
    evaluations_completed: int
    evaluations_skipped: int
    evaluations_pending_after: int
    aggregate_rows: int
    db_path: Path


@dataclass(frozen=True)
class MaterialPerspective:
    material_side: str
    material_label: str
    material_signature: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_progress_bar(
    *,
    enabled: bool,
    total: int,
    desc: str,
    unit: str,
) -> Any | None:
    if not enabled:
        return None
    try:
        from tqdm import tqdm
    except Exception:
        return None
    return tqdm(total=total, desc=desc, unit=unit, dynamic_ncols=True)


def file_signature(path: Path, *, include_hash: bool = False) -> dict[str, Any]:
    stat = path.stat()
    payload: dict[str, Any] = {
        "path": str(path),
        "sizeBytes": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
    }
    if include_hash:
        payload["sha256"] = sha256_file(path)
    return payload


def build_manifest(settings: EvalSettings) -> dict[str, Any]:
    stockfish_payload: dict[str, Any] | None = None
    if settings.stockfish_bin and not settings.tablebase_only:
        resolved = shutil.which(settings.stockfish_bin) or settings.stockfish_bin
        stockfish_path = Path(resolved).expanduser()
        stockfish_payload = {
            "requested": settings.stockfish_bin,
            "resolved": str(stockfish_path),
        }
        if stockfish_path.exists():
            stockfish_payload.update(file_signature(stockfish_path))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "markers": file_signature(settings.markers_jsonl, include_hash=settings.hash_markers),
        "limits": {
            "maxMarkers": settings.max_markers,
            "maxEvals": settings.max_evals,
        },
        "evaluation": {
            "routing": (
                "syzygy_le_5_skip_gt_5"
                if settings.tablebase_only
                else "syzygy_le_5_else_stockfish"
            ),
            "tablebaseThreshold": settings.tablebase_threshold,
            "syzygyDirs": list(settings.syzygy_dirs),
            "stockfish": stockfish_payload,
            "sfTimeSeconds": settings.sf_time_seconds,
            "sfThreads": settings.sf_threads,
            "drawThresholdCp": settings.draw_threshold_cp,
            "probeDtz": settings.probe_dtz,
        },
    }


def profile_id(manifest: dict[str, Any]) -> str:
    return sha256_text(canonical_json(manifest["evaluation"]))[:16]


def eval_key_for_fen(fen: str, *, profile: str) -> str:
    return sha256_text(f"{profile}\0{fen}")


def position_key(row: dict[str, Any]) -> str:
    payload = {
        "source_pgn": row.get("source_pgn", ""),
        "output_pgn": row.get("output_pgn", ""),
        "ending": row.get("ending", ""),
        "game_index": row.get("game_index", ""),
        "marker_index": row.get("marker_index", ""),
        "ply_index": row.get("ply_index", ""),
        "fen": row.get("fen", ""),
    }
    return sha256_text(canonical_json(payload))


def source_bucket_from_source_pgn(source_pgn: str) -> str:
    return source_stem(source_pgn) if source_pgn else ""


def legacy_game_key(row: dict[str, Any]) -> str:
    payload = {
        "source_pgn": row.get("source_pgn", ""),
        "output_pgn": row.get("output_pgn", ""),
        "game_index": row.get("game_index", ""),
        "headers": row.get("headers", {}),
    }
    return sha256_text(canonical_json(payload))[:16]


def normalize_marker_row(raw: dict[str, Any], *, line_number: int, path: Path) -> dict[str, Any]:
    """Accept both the new Rust schema and the existing tablebase JSONL schema."""
    if "schema_version" in raw:
        if raw.get("schema_version") != 1:
            raise EvalSnapshotError(
                f"{path}:{line_number}: unsupported marker schema "
                f"{raw.get('schema_version')!r}"
            )
        return {
            "source_pgn": str(raw.get("source_pgn", "")),
            "source_bucket": str(raw.get("source_bucket", "")),
            "ending": str(raw.get("ending", "")),
            "output_pgn": str(raw.get("output_pgn", "")),
            "game_index": int(raw.get("game_index", 0)),
            "marker_index": int(raw.get("marker_index", 0)),
            "marker_text": str(raw.get("marker_text", "CQL")),
            "game_key": str(raw.get("game_key", "")),
            "event": str(raw.get("event", "")),
            "site": str(raw.get("site", "")),
            "date": str(raw.get("date", "")),
            "round": str(raw.get("round", "")),
            "white": str(raw.get("white", "")),
            "black": str(raw.get("black", "")),
            "result": str(raw.get("result", "")),
            "ply_index": int(raw.get("ply_index", 0)),
            "fullmove_number": int(raw.get("fullmove_number", 0)),
            "move_san": str(raw.get("move_san", "")),
            "move_uci": str(raw.get("move_uci", "")),
            "fen": str(raw["fen"]),
            "side_to_move": str(raw.get("side_to_move", "")),
            "piece_count": int(raw.get("piece_count", 0)),
        }

    if "stem" not in raw or "fen" not in raw:
        raise EvalSnapshotError(
            f"{path}:{line_number}: expected Rust marker schema or legacy "
            "tablebase-position schema"
        )

    headers = raw.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    source_pgn = str(raw.get("source_pgn", ""))
    ply_index = int(raw.get("ply", 0))
    return {
        "source_pgn": source_pgn,
        "source_bucket": source_bucket_from_source_pgn(source_pgn),
        "ending": str(raw.get("stem", "")),
        "output_pgn": str(raw.get("output_pgn", "")),
        "game_index": int(raw.get("game_index", 0)),
        "marker_index": int(raw.get("marker_index", ply_index)),
        "marker_text": str(raw.get("marker_text", "CQL")),
        "game_key": str(raw.get("game_key") or legacy_game_key(raw)),
        "event": str(headers.get("Event", "")),
        "site": str(headers.get("Site", "")),
        "date": str(headers.get("Date", "")),
        "round": str(headers.get("Round", "")),
        "white": str(headers.get("White", "")),
        "black": str(headers.get("Black", "")),
        "result": str(headers.get("Result", "")),
        "ply_index": ply_index,
        "fullmove_number": int(raw.get("fullmove", 0)),
        "move_san": str(raw.get("move_san", "")),
        "move_uci": str(raw.get("move_uci", "")),
        "fen": str(raw["fen"]),
        "side_to_move": str(raw.get("side_to_move", "")),
        "piece_count": int(raw.get("piece_count", 0)),
    }


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positions (
            position_id INTEGER PRIMARY KEY,
            position_key TEXT NOT NULL UNIQUE,
            source_pgn TEXT NOT NULL,
            source_bucket TEXT NOT NULL,
            ending TEXT NOT NULL,
            output_pgn TEXT NOT NULL,
            game_index INTEGER NOT NULL,
            marker_index INTEGER NOT NULL,
            marker_text TEXT NOT NULL,
            game_key TEXT NOT NULL,
            event TEXT NOT NULL,
            site TEXT NOT NULL,
            date TEXT NOT NULL,
            round TEXT NOT NULL,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result TEXT NOT NULL,
            ply_index INTEGER NOT NULL,
            fullmove_number INTEGER NOT NULL,
            move_san TEXT NOT NULL,
            move_uci TEXT NOT NULL,
            fen TEXT NOT NULL,
            side_to_move TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            material_side TEXT NOT NULL,
            material_label TEXT NOT NULL,
            material_signature TEXT NOT NULL,
            eval_key TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evaluations (
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

        """
    )
    conn.executescript(ending_wdl_schema_sql())


def get_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


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


def ending_wdl_schema_sql() -> str:
    integer_columns = ",\n            ".join(
        f"{column} INTEGER NOT NULL" for column in AGGREGATE_INTEGER_COLUMNS
    )
    return f"""
        CREATE TABLE IF NOT EXISTS ending_wdl (
            ending TEXT NOT NULL,
            material_label TEXT NOT NULL,
            {integer_columns},
            PRIMARY KEY (ending, material_label)
        );
        """


def ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_positions_ending ON positions(ending);
        CREATE INDEX IF NOT EXISTS idx_positions_eval_key ON positions(eval_key);
        CREATE INDEX IF NOT EXISTS idx_positions_game_key ON positions(game_key);
        CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(eval_status);
        """
    )
    conn.commit()


def remove_database_files(db_path: Path) -> None:
    for path in (db_path, db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
        if path.exists():
            path.unlink()


def open_snapshot_db(settings: EvalSettings, manifest: dict[str, Any]) -> sqlite3.Connection:
    db_path = settings.output_db
    if settings.force and db_path.exists():
        remove_database_files(db_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    had_db = db_path.exists()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    manifest_text = canonical_json(manifest)
    existing_manifest = get_metadata(conn, "input_manifest")
    if existing_manifest is not None and existing_manifest != manifest_text:
        conn.close()
        raise EvalSnapshotError(
            f"existing DB manifest does not match current inputs: {db_path}. "
            "Use --force or choose a new --output-db."
        )
    if had_db and existing_manifest is None:
        has_user_tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name != 'metadata'"
        ).fetchone()[0]
        if has_user_tables:
            conn.close()
            raise EvalSnapshotError(
                f"existing DB is not an FCE eval snapshot: {db_path}. "
                "Use --force or choose a new --output-db."
            )

    if existing_manifest is None:
        set_metadata(conn, "input_manifest", manifest)
        set_metadata(conn, "profile_id", profile_id(manifest))
        set_metadata(conn, "created_at", utc_now())
        set_metadata(conn, "build_status", "building")
        conn.commit()
    return conn


def piece_counts(board: chess.Board, color: chess.Color) -> dict[str, int]:
    return {
        "P": len(board.pieces(chess.PAWN, color)),
        "N": len(board.pieces(chess.KNIGHT, color)),
        "B": len(board.pieces(chess.BISHOP, color)),
        "R": len(board.pieces(chess.ROOK, color)),
        "Q": len(board.pieces(chess.QUEEN, color)),
    }


def nonking(counts: dict[str, int]) -> int:
    return sum(counts.values())


def minor_count(counts: dict[str, int]) -> int:
    return counts["B"] + counts["N"]


def side_material_text(counts: dict[str, int]) -> str:
    parts: list[str] = []
    for symbol in ("Q", "R", "B", "N", "P"):
        count = counts[symbol]
        if count == 1:
            parts.append(symbol)
        elif count > 1:
            parts.append(f"{symbol}{count}")
    return "".join(parts) or "bare"


def material_signature(board: chess.Board) -> str:
    white = side_material_text(piece_counts(board, chess.WHITE))
    black = side_material_text(piece_counts(board, chess.BLACK))
    return f"{white}v{black}"


def select_material_side(
    board: chess.Board,
    label: str,
    predicate,
) -> MaterialPerspective:
    white = piece_counts(board, chess.WHITE)
    black = piece_counts(board, chess.BLACK)
    white_match = predicate(white, black)
    black_match = predicate(black, white)
    if white_match and not black_match:
        side = "white"
    elif black_match and not white_match:
        side = "black"
    elif white_match and black_match:
        side = "symmetric"
    else:
        side = "unknown"
    return MaterialPerspective(side, label, material_signature(board))


SYMMETRIC_ENDINGS = {
    "2-0Pp",
    "3-2NN",
    "4-2scBB",
    "4-3ocBB",
    "6-2-0Rr",
    "6-3RRrr",
    "8-3RAra",
    "9-2Qq",
}


def classify_material_side(ending: str, board: chess.Board) -> MaterialPerspective:
    if ending in SYMMETRIC_ENDINGS:
        return MaterialPerspective("symmetric", "symmetric/either side", material_signature(board))

    if ending == "1-4BN":
        return select_material_side(
            board,
            "bishop+knight side",
            lambda own, opp: own["B"] >= 1 and own["N"] >= 1 and nonking(opp) == 0,
        )
    if ending == "1-5NNp":
        return select_material_side(
            board,
            "two-knights side",
            lambda own, opp: own["N"] >= 2 and opp["P"] >= 1,
        )
    if ending == "2-1P":
        return select_material_side(
            board,
            "pawn side",
            lambda own, opp: own["P"] >= 1 and nonking(opp) == 0,
        )
    if ending == "3-1Np":
        return select_material_side(
            board,
            "knight side",
            lambda own, opp: own["N"] >= 1 and opp["P"] >= 1,
        )
    if ending == "4-1Bp":
        return select_material_side(
            board,
            "bishop side",
            lambda own, opp: own["B"] >= 1 and opp["P"] >= 1,
        )
    if ending == "5-0BN":
        return select_material_side(
            board,
            "bishop side",
            lambda own, opp: own["B"] >= 1 and opp["N"] >= 1,
        )
    if ending == "6-1-0RP":
        return select_material_side(
            board,
            "rook side",
            lambda own, opp: own["R"] >= 1 and opp["P"] >= 1,
        )
    if ending == "6-2-1RPr":
        return select_material_side(
            board,
            "rook+pawn side",
            lambda own, opp: own["R"] >= 1 and own["P"] >= 1 and opp["R"] >= 1,
        )
    if ending == "6-2-2RPPr":
        return select_material_side(
            board,
            "rook+two-pawns side",
            lambda own, opp: own["R"] >= 1 and own["P"] >= 2 and opp["R"] >= 1,
        )
    if ending == "7-1RN":
        return select_material_side(
            board,
            "rook side",
            lambda own, opp: own["R"] >= 1 and opp["N"] >= 1,
        )
    if ending == "7-2RB":
        return select_material_side(
            board,
            "rook side",
            lambda own, opp: own["R"] >= 1 and opp["B"] >= 1,
        )
    if ending == "8-1RNr":
        return select_material_side(
            board,
            "rook+knight side",
            lambda own, opp: own["R"] >= 1 and own["N"] >= 1 and opp["R"] >= 1,
        )
    if ending == "8-2RBr":
        return select_material_side(
            board,
            "rook+bishop side",
            lambda own, opp: own["R"] >= 1 and own["B"] >= 1 and opp["R"] >= 1,
        )
    if ending == "9-1Qp":
        return select_material_side(
            board,
            "queen side",
            lambda own, opp: own["Q"] >= 1 and opp["P"] >= 1,
        )
    if ending == "9-3QPq":
        return select_material_side(
            board,
            "queen+pawn side",
            lambda own, opp: own["Q"] >= 1 and own["P"] >= 1 and opp["Q"] >= 1,
        )
    if ending in {"10-1Qa", "10-3Qaa", "10-6Qaaa"}:
        required_minors = {"10-1Qa": 1, "10-3Qaa": 2, "10-6Qaaa": 3}[ending]
        return select_material_side(
            board,
            "queen side",
            lambda own, opp: own["Q"] >= 1 and minor_count(opp) >= required_minors,
        )
    if ending == "10-2Qr":
        return select_material_side(
            board,
            "queen side",
            lambda own, opp: own["Q"] >= 1 and opp["R"] >= 1,
        )
    if ending == "10-4Qra":
        return select_material_side(
            board,
            "queen side",
            lambda own, opp: own["Q"] >= 1 and opp["R"] >= 1 and minor_count(opp) >= 1,
        )
    if ending == "10-5Qrr":
        return select_material_side(
            board,
            "queen side",
            lambda own, opp: own["Q"] >= 1 and opp["R"] >= 2,
        )
    if ending == "10-7QAq":
        return select_material_side(
            board,
            "queen+minor side",
            lambda own, opp: own["Q"] >= 1 and minor_count(own) >= 1 and opp["Q"] >= 1,
        )
    if ending == "10-7-1Qbrr":
        return select_material_side(
            board,
            "queen+bishop side",
            lambda own, opp: own["Q"] >= 1 and own["B"] >= 1 and opp["R"] >= 2,
        )

    return MaterialPerspective("unknown", "unknown", material_signature(board))


def ingest_markers(
    conn: sqlite3.Connection,
    settings: EvalSettings,
    *,
    profile: str,
) -> int:
    if get_metadata(conn, "positions_ingest_complete") == "true":
        return conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]

    inserted_or_seen = 0
    set_metadata(conn, "positions_ingest_started_at", utc_now())
    conn.commit()

    insert_position_sql = """
        INSERT OR IGNORE INTO positions (
            position_key, source_pgn, source_bucket, ending, output_pgn,
            game_index, marker_index, marker_text, game_key,
            event, site, date, round, white, black, result,
            ply_index, fullmove_number, move_san, move_uci, fen,
            side_to_move, piece_count, material_side, material_label,
            material_signature, eval_key
        ) VALUES (
            :position_key, :source_pgn, :source_bucket, :ending, :output_pgn,
            :game_index, :marker_index, :marker_text, :game_key,
            :event, :site, :date, :round, :white, :black, :result,
            :ply_index, :fullmove_number, :move_san, :move_uci, :fen,
            :side_to_move, :piece_count, :material_side, :material_label,
            :material_signature, :eval_key
        )
    """

    with settings.markers_jsonl.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if settings.max_markers is not None and inserted_or_seen >= settings.max_markers:
                break
            line = line.strip()
            if not line:
                continue
            row = normalize_marker_row(
                json.loads(line),
                line_number=line_number,
                path=settings.markers_jsonl,
            )

            fen = str(row["fen"])
            board = chess.Board(fen)
            ending = str(row["ending"])
            material = classify_material_side(ending, board)
            eval_key = eval_key_for_fen(fen, profile=profile)
            values = {
                "position_key": position_key(row),
                "source_pgn": str(row.get("source_pgn", "")),
                "source_bucket": str(row.get("source_bucket", "")),
                "ending": ending,
                "output_pgn": str(row.get("output_pgn", "")),
                "game_index": int(row.get("game_index", 0)),
                "marker_index": int(row.get("marker_index", 0)),
                "marker_text": str(row.get("marker_text", "")),
                "game_key": str(row.get("game_key", "")),
                "event": str(row.get("event", "")),
                "site": str(row.get("site", "")),
                "date": str(row.get("date", "")),
                "round": str(row.get("round", "")),
                "white": str(row.get("white", "")),
                "black": str(row.get("black", "")),
                "result": str(row.get("result", "")),
                "ply_index": int(row.get("ply_index", 0)),
                "fullmove_number": int(row.get("fullmove_number", 0)),
                "move_san": str(row.get("move_san", "")),
                "move_uci": str(row.get("move_uci", "")),
                "fen": fen,
                "side_to_move": str(row.get("side_to_move", "")),
                "piece_count": int(row.get("piece_count", len(board.piece_map()))),
                "material_side": material.material_side,
                "material_label": material.material_label,
                "material_signature": material.material_signature,
                "eval_key": eval_key,
            }
            conn.execute(insert_position_sql, values)
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluations(eval_key, fen, piece_count)
                VALUES (?, ?, ?)
                """,
                (eval_key, fen, values["piece_count"]),
            )
            inserted_or_seen += 1
            if inserted_or_seen % 10000 == 0:
                conn.commit()

    set_metadata(conn, "positions_ingest_complete", "true")
    set_metadata(conn, "positions_ingest_completed_at", utc_now())
    set_metadata(conn, "positions_seen_in_input", str(inserted_or_seen))
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]


def evaluation_to_update(eval_key: str, result: EvaluationResult) -> tuple[Any, ...]:
    return (
        result.eval_source,
        result.winning_side,
        result.tb_wdl,
        result.tb_dtz,
        result.sf_cp_white,
        result.sf_mate_white,
        result.sf_time_seconds,
        result.draw_threshold_cp,
        result.eval_status,
        result.error_message,
        utc_now(),
        eval_key,
    )


def update_evaluation(conn: sqlite3.Connection, eval_key: str, result: EvaluationResult) -> None:
    conn.execute(
        """
        UPDATE evaluations
        SET eval_source = ?,
            winning_side = ?,
            tb_wdl = ?,
            tb_dtz = ?,
            sf_cp_white = ?,
            sf_mate_white = ?,
            sf_time_seconds = ?,
            draw_threshold_cp = ?,
            eval_status = ?,
            error_message = ?,
            evaluated_at = ?
        WHERE eval_key = ?
        """,
        evaluation_to_update(eval_key, result),
    )


def mark_tablebase_skips(conn: sqlite3.Connection, settings: EvalSettings) -> int:
    if not settings.tablebase_only:
        return 0
    cursor = conn.execute(
        """
        UPDATE evaluations
        SET eval_source = 'none',
            winning_side = 'unknown',
            eval_status = 'skipped_non_tablebase',
            error_message = ?,
            evaluated_at = ?
        WHERE eval_status = 'pending'
          AND piece_count > ?
        """,
        (
            f"tablebase-only profile skips positions with more than {settings.tablebase_threshold} pieces",
            utc_now(),
            settings.tablebase_threshold,
        ),
    )
    conn.commit()
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


_WORKER_TABLEBASE = None
_WORKER_TABLEBASE_ERROR: str | None = None
_WORKER_STOCKFISH: StockfishSession | None = None
_WORKER_SETTINGS: dict[str, Any] = {}


def evaluate_with_tablebase_for_snapshot(
    board: chess.Board,
    tablebase,
    *,
    probe_dtz: bool,
) -> EvaluationResult:
    if tablebase is None:
        return EvaluationResult(
            eval_source="tablebase",
            winning_side="unknown",
            eval_status="tablebase_error",
            error_message=(
                "Syzygy tablebases are required for positions with 5 or fewer "
                "pieces; pass --syzygy-dir."
            ),
        )

    try:
        wdl = tablebase.probe_wdl(board)
        dtz = tablebase.probe_dtz(board) if probe_dtz else None
        return EvaluationResult(
            eval_source="tablebase",
            winning_side=classify_side_to_move_wdl(wdl, board.turn),
            tb_wdl=wdl,
            tb_dtz=dtz,
            eval_status="ok",
        )
    except Exception as exc:
        return EvaluationResult(
            eval_source="tablebase",
            winning_side="unknown",
            eval_status="tablebase_error",
            error_message=str(exc),
        )


def _init_worker(
    syzygy_dirs: tuple[str, ...],
    stockfish_bin: str | None,
    sf_threads: int,
    sf_time_seconds: float,
    draw_threshold_cp: int,
    tablebase_threshold: int,
    tablebase_only: bool,
    probe_dtz: bool,
) -> None:
    global _WORKER_TABLEBASE, _WORKER_TABLEBASE_ERROR, _WORKER_STOCKFISH, _WORKER_SETTINGS
    _WORKER_TABLEBASE, _WORKER_TABLEBASE_ERROR = open_tablebase_from_directories(list(syzygy_dirs))
    _WORKER_STOCKFISH = None if tablebase_only else StockfishSession(stockfish_bin, sf_threads)
    _WORKER_SETTINGS = {
        "sf_time_seconds": sf_time_seconds,
        "draw_threshold_cp": draw_threshold_cp,
        "tablebase_threshold": tablebase_threshold,
        "tablebase_only": tablebase_only,
        "probe_dtz": probe_dtz,
    }


def _evaluate_task(task: tuple[str, str, int]) -> tuple[str, EvaluationResult]:
    eval_key, fen, piece_count = task
    board = chess.Board(fen)
    if piece_count <= int(_WORKER_SETTINGS["tablebase_threshold"]):
        result = evaluate_with_tablebase_for_snapshot(
            board,
            _WORKER_TABLEBASE,
            probe_dtz=bool(_WORKER_SETTINGS["probe_dtz"]),
        )
        if result.eval_status != "ok" and _WORKER_TABLEBASE_ERROR:
            result = EvaluationResult(
                eval_source="tablebase",
                winning_side="unknown",
                eval_status="tablebase_error",
                error_message=_WORKER_TABLEBASE_ERROR,
            )
        return eval_key, result

    if bool(_WORKER_SETTINGS["tablebase_only"]):
        return eval_key, EvaluationResult(
            eval_source="none",
            winning_side="unknown",
            eval_status="skipped_non_tablebase",
            error_message=(
                "tablebase-only profile skips positions with more than "
                f"{_WORKER_SETTINGS['tablebase_threshold']} pieces"
            ),
        )

    assert _WORKER_STOCKFISH is not None
    return eval_key, _WORKER_STOCKFISH.analyse(
        board,
        sf_time_seconds=float(_WORKER_SETTINGS["sf_time_seconds"]),
        draw_threshold_cp=int(_WORKER_SETTINGS["draw_threshold_cp"]),
    )


def pending_count(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM evaluations WHERE eval_status = 'pending'").fetchone()[0]
    )


def pending_batches(
    conn: sqlite3.Connection,
    *,
    max_evals: int | None,
    batch_size: int,
) -> Iterable[list[tuple[str, str, int]]]:
    remaining = max_evals
    while True:
        limit = batch_size if remaining is None else min(batch_size, remaining)
        if limit <= 0:
            break
        rows = conn.execute(
            """
            SELECT eval_key, fen, piece_count
            FROM evaluations
            WHERE eval_status = 'pending'
            ORDER BY piece_count, eval_key
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        if not rows:
            break
        yield [(str(row["eval_key"]), str(row["fen"]), int(row["piece_count"])) for row in rows]
        if remaining is not None:
            remaining -= len(rows)


def evaluate_pending(
    conn: sqlite3.Connection,
    settings: EvalSettings,
    *,
    show_progress: bool = False,
    progress_callback: Any | None = None,
) -> int:
    completed = 0
    batch_size = max(4096, settings.workers * 1024)
    total_pending = pending_count(conn)
    if settings.max_evals is not None:
        total_pending = min(total_pending, settings.max_evals)
    progress = create_progress_bar(
        enabled=show_progress,
        total=total_pending,
        desc="Syzygy evaluations" if settings.tablebase_only else "Position evaluations",
        unit="eval",
    )

    def report_progress() -> None:
        if progress_callback is not None:
            progress_callback(completed, total_pending)

    if settings.workers <= 1:
        _init_worker(
            settings.syzygy_dirs,
            settings.stockfish_bin,
            settings.sf_threads,
            settings.sf_time_seconds,
            settings.draw_threshold_cp,
            settings.tablebase_threshold,
            settings.tablebase_only,
            settings.probe_dtz,
        )
        try:
            for batch in pending_batches(conn, max_evals=settings.max_evals, batch_size=batch_size):
                for task in batch:
                    eval_key, result = _evaluate_task(task)
                    update_evaluation(conn, eval_key, result)
                    completed += 1
                    if progress is not None:
                        progress.update(1)
                conn.commit()
                report_progress()
        finally:
            if _WORKER_STOCKFISH is not None:
                _WORKER_STOCKFISH.close()
            if _WORKER_TABLEBASE is not None:
                _WORKER_TABLEBASE.close()
            if progress is not None:
                progress.close()
        return completed

    try:
        with Pool(
            processes=settings.workers,
            initializer=_init_worker,
            initargs=(
                settings.syzygy_dirs,
                settings.stockfish_bin,
                settings.sf_threads,
                settings.sf_time_seconds,
                settings.draw_threshold_cp,
                settings.tablebase_threshold,
                settings.tablebase_only,
                settings.probe_dtz,
            ),
        ) as pool:
            for batch in pending_batches(conn, max_evals=settings.max_evals, batch_size=batch_size):
                for eval_key, result in pool.imap_unordered(_evaluate_task, batch, chunksize=128):
                    update_evaluation(conn, eval_key, result)
                    completed += 1
                    if progress is not None:
                        progress.update(1)
                conn.commit()
                report_progress()
    finally:
        if progress is not None:
            progress.close()

    return completed


def refresh_aggregates(
    conn: sqlite3.Connection,
    *,
    tablebase_threshold: int = DEFAULT_TABLEBASE_THRESHOLD,
) -> int:
    column_names = ", ".join(AGGREGATE_COLUMNS)
    conn.executescript("DROP TABLE IF EXISTS ending_wdl;")
    conn.executescript(ending_wdl_schema_sql().replace("IF NOT EXISTS ", ""))
    conn.execute(
        f"""
        INSERT INTO ending_wdl (
            {column_names}
        )
        WITH classified AS (
            SELECT
                p.ending,
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
        )
        SELECT
            ending,
            material_label,
            COUNT(*) AS total_positions,
            SUM(CASE WHEN eval_status = 'ok' THEN 1 ELSE 0 END) AS evaluated_positions,
            SUM(CASE WHEN piece_count <= :tablebase_threshold THEN 1 ELSE 0 END) AS tablebase_eligible_positions,
            SUM(CASE WHEN eval_status = 'ok' AND eval_source = 'tablebase' THEN 1 ELSE 0 END) AS tablebase_positions,
            SUM(CASE WHEN eval_status = 'ok' AND eval_source = 'stockfish' THEN 1 ELSE 0 END) AS stockfish_positions,
            SUM(CASE WHEN eval_status = 'skipped_non_tablebase' THEN 1 ELSE 0 END) AS skipped_non_tablebase_positions,
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
        {"tablebase_threshold": tablebase_threshold},
    )
    conn.commit()
    return int(conn.execute("SELECT COUNT(*) FROM ending_wdl").fetchone()[0])


def export_aggregate_csv(conn: sqlite3.Connection, output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    column_names = ", ".join(AGGREGATE_COLUMNS)
    rows = conn.execute(
        f"""
        SELECT {column_names}
        FROM ending_wdl
        ORDER BY ending, material_label
        """
    ).fetchall()
    columns = list(AGGREGATE_COLUMNS)
    import csv

    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def build_eval_snapshot(
    settings: EvalSettings,
    *,
    aggregate_csv: Path | None = None,
) -> EvalRunStats:
    manifest = build_manifest(settings)
    conn = open_snapshot_db(settings, manifest)
    try:
        profile = profile_id(manifest)
        positions = ingest_markers(conn, settings, profile=profile)
        ensure_indexes(conn)
        skipped = mark_tablebase_skips(conn, settings)
        pending_before = pending_count(conn)
        completed = evaluate_pending(conn, settings)
        pending_after = pending_count(conn)
        aggregate_rows = refresh_aggregates(
            conn,
            tablebase_threshold=settings.tablebase_threshold,
        )
        if aggregate_csv is not None:
            export_aggregate_csv(conn, aggregate_csv)
        set_metadata(conn, "updated_at", utc_now())
        set_metadata(
            conn,
            "build_status",
            "complete" if pending_after == 0 else "positions_ingested",
        )
        conn.commit()
        return EvalRunStats(
            positions_ingested=positions,
            evaluations_pending_before=pending_before,
            evaluations_completed=completed,
            evaluations_skipped=skipped,
            evaluations_pending_after=pending_after,
            aggregate_rows=aggregate_rows,
            db_path=settings.output_db,
        )
    finally:
        conn.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or resume an FCE marker evaluation SQLite snapshot."
    )
    parser.add_argument("--markers-jsonl", required=True, type=Path)
    parser.add_argument("--output-db", required=True, type=Path)
    parser.add_argument("--syzygy-dir", action="append", default=[])
    parser.add_argument("--stockfish-bin")
    parser.add_argument("--sf-time-seconds", type=float, default=DEFAULT_SF_TIME_SECONDS)
    parser.add_argument("--sf-threads", type=int, default=DEFAULT_SF_THREADS)
    parser.add_argument("--draw-threshold-cp", type=int, default=DEFAULT_DRAW_THRESHOLD_CP)
    parser.add_argument(
        "--tablebase-only",
        action="store_true",
        help="Evaluate <=5-man positions with Syzygy and mark larger positions as skipped.",
    )
    parser.add_argument(
        "--probe-dtz",
        action="store_true",
        help="Also probe Syzygy DTZ. Off by default because WDL stats only need WDL.",
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-markers", type=int)
    parser.add_argument("--max-evals", type=int)
    parser.add_argument("--hash-markers", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--aggregate-csv", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = EvalSettings(
        markers_jsonl=args.markers_jsonl.expanduser(),
        output_db=args.output_db.expanduser(),
        syzygy_dirs=tuple(args.syzygy_dir),
        stockfish_bin=args.stockfish_bin,
        sf_time_seconds=args.sf_time_seconds,
        sf_threads=args.sf_threads,
        draw_threshold_cp=args.draw_threshold_cp,
        tablebase_only=args.tablebase_only,
        probe_dtz=args.probe_dtz,
        workers=args.workers,
        max_markers=args.max_markers,
        max_evals=args.max_evals,
        hash_markers=args.hash_markers,
        force=args.force,
    )
    try:
        stats = build_eval_snapshot(settings, aggregate_csv=args.aggregate_csv)
    except EvalSnapshotError as exc:
        print(f"Error: {exc}")
        return 2

    print(
        canonical_json(
            {
                "db": str(stats.db_path),
                "positions": stats.positions_ingested,
                "evaluationsPendingBefore": stats.evaluations_pending_before,
                "evaluationsCompleted": stats.evaluations_completed,
                "evaluationsSkipped": stats.evaluations_skipped,
                "evaluationsPendingAfter": stats.evaluations_pending_after,
                "aggregateRows": stats.aggregate_rows,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
