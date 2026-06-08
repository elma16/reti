from __future__ import annotations

import argparse
import copy
import csv
import html
import json
import shutil
import tempfile
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reti.common.hashing import canonical_json, manifest_fingerprint, sha256_file
from reti.common.json_io import load_json, write_json
from reti.common.source_metadata import (
    source_bucket_key,
    source_bucket_label,
    source_sort_key,
)
from reti.fce_metadata import FCE_CATALOG


SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CQL_TABLE_DIR = REPO_ROOT / "cql-files" / "FCE" / "table"
TABLEBASE_WDL_BASE_FIELDS = (
    "ending",
    "material_label",
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
TABLEBASE_ACTUAL_RESULT_FIELDS = (
    "actual_white_wins",
    "actual_draws",
    "actual_black_wins",
    "actual_side_wins",
    "actual_side_draws",
    "actual_side_losses",
    "actual_symmetric_decisive",
    "actual_unknown_results",
)
TABLEBASE_CROSSTAB_FIELDS = (
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
TABLEBASE_WDL_FIELDS = (
    *TABLEBASE_WDL_BASE_FIELDS,
    *TABLEBASE_ACTUAL_RESULT_FIELDS,
    *TABLEBASE_CROSSTAB_FIELDS,
)
TABLEBASE_WDL_INTEGER_FIELDS = tuple(
    field for field in TABLEBASE_WDL_FIELDS if field not in {"ending", "material_label"}
)
FCE_REFERENCE_SOURCE_URL = "https://en.wikipedia.org/wiki/Chess_endgame#Frequency_table"
FCE_REFERENCE_ROWS = (
    {"stem": "1-4BN", "quantity": "283 (62 draws)", "quantitySort": 283, "percentage": 0.02},
    {"stem": "1-5NNp", "quantity": "not listed", "quantitySort": 0, "percentage": 0.0},
    {"stem": "2-0Pp", "quantity": "48,465", "quantitySort": 48465, "percentage": 2.87},
    {"stem": "2-1P", "quantity": "3,920", "quantitySort": 3920, "percentage": 0.23},
    {"stem": "3-1Np", "quantity": "15,512", "quantitySort": 15512, "percentage": 0.92},
    {"stem": "3-2NN", "quantity": "26,263", "quantitySort": 26263, "percentage": 1.56},
    {"stem": "4-1Bp", "quantity": "16,953", "quantitySort": 16953, "percentage": 1.01},
    {"stem": "4-2scBB", "quantity": "27,864 (11,351 draws)", "quantitySort": 27864, "percentage": 1.65},
    {"stem": "4-3ocBB", "quantity": "18,653 (11,045 draws)", "quantitySort": 18653, "percentage": 1.11},
    {"stem": "5-0BN", "quantity": "55,476 (19,670 draws)", "quantitySort": 55476, "percentage": 3.29},
    {"stem": "6-1-0RP", "quantity": "12,723", "quantitySort": 12723, "percentage": 0.75},
    {"stem": "6-2-0Rr", "quantity": "142,488 (55,974 draws)", "quantitySort": 142488, "percentage": 8.45},
    {"stem": "6-2-1RPr", "quantity": "11,318", "quantitySort": 11318, "percentage": 0.67},
    {"stem": "6-2-2RPPr", "quantity": "9,398 (3,574 connected)", "quantitySort": 9398, "percentage": 0.56},
    {"stem": "6-3RRrr", "quantity": "58,211", "quantitySort": 58211, "percentage": 3.45},
    {"stem": "7-1RN", "quantity": "16,298", "quantitySort": 16298, "percentage": 0.97},
    {"stem": "7-2RB", "quantity": "25,524", "quantitySort": 25524, "percentage": 1.51},
    {"stem": "8-1RNr", "quantity": "23,910 (467 without pawns; 418 draws)", "quantitySort": 23910, "percentage": 1.42},
    {"stem": "8-2RBr", "quantity": "29,785 (736 without pawns; 401 draws)", "quantitySort": 29785, "percentage": 1.77},
    {"stem": "8-3RAra", "quantity": "255,317", "quantitySort": 255317, "percentage": 15.13},
    {"stem": "9-1Qp", "quantity": "7,066", "quantitySort": 7066, "percentage": 0.42},
    {"stem": "9-2Qq", "quantity": "30,834", "quantitySort": 30834, "percentage": 1.83},
    {"stem": "9-3QPq", "quantity": "1,575", "quantitySort": 1575, "percentage": 0.09},
    {"stem": "10-1Qa", "quantity": "2,798", "quantitySort": 2798, "percentage": 0.17},
    {"stem": "10-2Qr", "quantity": "6,769 (263 without pawns and 10 half-moves; 22 draws)", "quantitySort": 6769, "percentage": 0.40},
    {"stem": "10-3Qaa", "quantity": "1,276", "quantitySort": 1276, "percentage": 0.08},
    {"stem": "10-4Qra", "quantity": "11,637", "quantitySort": 11637, "percentage": 0.69},
    {"stem": "10-5Qrr", "quantity": "5,257", "quantitySort": 5257, "percentage": 0.31},
    {"stem": "10-6Qaaa", "quantity": "239", "quantitySort": 239, "percentage": 0.01},
    {"stem": "10-7QAq", "quantity": "15,128", "quantitySort": 15128, "percentage": 0.90},
    {"stem": "10-7-1Qbrr", "quantity": "Only one without pawns", "quantitySort": 1, "percentage": 0.00006},
)


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class SummaryData:
    sources: tuple[str, ...]
    counts_by_source: dict[str, dict[str, int]]
    total_by_stem: dict[str, int]
    total_matches: int
    row_count: int


@dataclass(frozen=True)
class SnapshotBuildResult:
    output_dir: Path
    snapshot_path: Path
    manifest_path: Path
    summary_csv_path: Path
    html_path: Path
    snapshot_id: str
    up_to_date: bool = False


def file_signature(path: Path, *, include_hash: bool) -> dict[str, Any]:
    if not path.exists():
        raise SnapshotError(f"Required input does not exist: {path}")
    stat = path.stat()
    payload: dict[str, Any] = {
        "path": str(path),
        "sizeBytes": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
    }
    if include_hash:
        payload["sha256"] = sha256_file(path)
    return payload


def parse_match_count(raw_value: str, *, row_number: int) -> int:
    try:
        count = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(
            f"summary.csv row {row_number}: invalid match_count {raw_value!r}"
        ) from exc
    if count < 0:
        raise SnapshotError(f"summary.csv row {row_number}: negative match_count {count}")
    return count


def load_summary_data(summary_csv: Path) -> SummaryData:
    expected_stems = {ending.stem for ending in FCE_CATALOG.endings}
    required_fields = {"pgn", "cql", "output_pgn", "status", "match_count"}
    counts_by_source: dict[str, dict[str, int]] = {}
    row_count = 0

    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_fields = required_fields.difference(reader.fieldnames or [])
        if missing_fields:
            raise SnapshotError(
                f"summary.csv missing required field(s): {', '.join(sorted(missing_fields))}"
            )

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            status = row.get("status") or ""
            if status != "ok":
                raise SnapshotError(
                    f"summary.csv row {row_number}: status is {status!r}, expected 'ok'"
                )

            source = row.get("pgn") or ""
            if not source:
                raise SnapshotError(f"summary.csv row {row_number}: missing pgn value")

            stem = Path(row.get("cql") or "").stem
            if stem not in expected_stems:
                raise SnapshotError(
                    f"summary.csv row {row_number}: unexpected FCE stem {stem!r}"
                )

            output_stem = Path(row.get("output_pgn") or "").stem
            if output_stem and output_stem != stem:
                raise SnapshotError(
                    f"summary.csv row {row_number}: output_pgn stem {output_stem!r} "
                    f"does not match cql stem {stem!r}"
                )

            count = parse_match_count(row.get("match_count") or "", row_number=row_number)
            source_counts = counts_by_source.setdefault(source, {})
            source_counts[stem] = source_counts.get(stem, 0) + count

    if row_count == 0:
        raise SnapshotError(f"summary.csv has no data rows: {summary_csv}")

    for source, counts in sorted(counts_by_source.items()):
        missing = expected_stems.difference(counts)
        if missing:
            raise SnapshotError(
                f"summary.csv is missing {len(missing)} FCE row(s) for {source}: "
                + ", ".join(sorted(missing))
            )

    sources = tuple(sorted(counts_by_source, key=source_sort_key))
    total_by_stem = {
        ending.stem: sum(counts_by_source[source][ending.stem] for source in sources)
        for ending in FCE_CATALOG.endings
    }
    total_matches = sum(total_by_stem.values())
    return SummaryData(
        sources=sources,
        counts_by_source=counts_by_source,
        total_by_stem=total_by_stem,
        total_matches=total_matches,
        row_count=row_count,
    )


def catalog_payload() -> dict[str, Any]:
    return {
        "name": FCE_CATALOG.name,
        "exactness": "exact",
        "rows": [
            {
                "stem": ending.stem,
                "sortIndex": index,
                "rowId": ending.row_id,
                "label": ending.label,
                "displayLabel": ending.display_label,
                "chapterKey": ending.chapter_key,
                "chapter": ending.chapter_label,
                "color": ending.color,
                "specificityRank": ending.specificity_rank,
            }
            for index, ending in enumerate(FCE_CATALOG.endings)
        ],
    }


def original_fce_reference_payload() -> dict[str, Any]:
    rows = []
    for index, reference in enumerate(FCE_REFERENCE_ROWS):
        ending = FCE_CATALOG.endings_by_stem[str(reference["stem"])]
        rows.append(
            {
                "stem": ending.stem,
                "sortIndex": index,
                "rowId": ending.row_id,
                "label": ending.label,
                "chapter": ending.chapter_label,
                "quantity": str(reference["quantity"]),
                "quantitySort": int(reference["quantitySort"]),
                "percentage": float(reference["percentage"]),
            }
        )
    return {
        "name": "Fundamental Chess Endings frequency table",
        "sourceUrl": FCE_REFERENCE_SOURCE_URL,
        "exactness": "reference",
        "rows": rows,
    }


def cql_input_signatures(cql_table_dir: Path) -> dict[str, Any]:
    scripts = []
    for ending in FCE_CATALOG.endings:
        cql_path = cql_table_dir / f"{ending.stem}.cql"
        scripts.append({"stem": ending.stem, **file_signature(cql_path, include_hash=True)})
    return {
        "tableDir": str(cql_table_dir),
        "manifestCsv": file_signature(cql_table_dir / "manifest.csv", include_hash=True),
        "scripts": scripts,
    }


def source_pgn_signatures(
    *,
    sources: tuple[str, ...],
    corpus_dir: Path,
    hash_source_pgns: bool,
) -> list[dict[str, Any]]:
    signatures = []
    for source in sources:
        signatures.append(
            {
                "sourcePgn": source,
                **file_signature(corpus_dir / source, include_hash=hash_source_pgns),
                "hashIncluded": hash_source_pgns,
            }
        )
    return signatures


def build_current_manifest(
    *,
    summary_csv: Path,
    run_dir: Path,
    corpus_dir: Path,
    total_games: int,
    title: str,
    cql_table_dir: Path,
    hash_source_pgns: bool,
    examples_jsonl: Path | None,
) -> tuple[dict[str, Any], SummaryData]:
    summary_data = load_summary_data(summary_csv)
    inputs: dict[str, Any] = {
        "summaryCsv": file_signature(summary_csv, include_hash=True),
        "runDir": str(run_dir),
        "corpusDir": str(corpus_dir),
        "cql": cql_input_signatures(cql_table_dir),
        "sourcePgns": source_pgn_signatures(
            sources=summary_data.sources,
            corpus_dir=corpus_dir,
            hash_source_pgns=hash_source_pgns,
        ),
    }
    if examples_jsonl is not None:
        inputs["examplesJsonl"] = file_signature(examples_jsonl, include_hash=True)

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "builder": "reti.fce_snapshot",
        "settings": {
            "title": title,
            "totalGames": total_games,
            "hashSourcePgns": hash_source_pgns,
            "summaryCsv": str(summary_csv),
            "runDir": str(run_dir),
            "corpusDir": str(corpus_dir),
            "cqlTableDir": str(cql_table_dir),
            "examplesJsonl": str(examples_jsonl) if examples_jsonl else None,
        },
        "inputs": inputs,
    }
    manifest["fingerprint"] = manifest_fingerprint(manifest)
    return manifest, summary_data


def build_source_buckets(
    summary_data: SummaryData,
    source_signatures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signatures_by_source = {
        str(signature["sourcePgn"]): signature for signature in source_signatures
    }
    buckets = []
    for sort_index, source in enumerate(summary_data.sources):
        counts = {
            ending.stem: summary_data.counts_by_source[source][ending.stem]
            for ending in FCE_CATALOG.endings
        }
        buckets.append(
            {
                "sourcePgn": source,
                "sourceStem": Path(source).stem,
                "bucket": source_bucket_key(source),
                "displayLabel": source_bucket_label(source),
                "sortIndex": sort_index,
                "matchTotal": sum(counts.values()),
                "counts": counts,
                "file": signatures_by_source[source],
                "exactness": "exact",
            }
        )
    return buckets


def build_rows(summary_data: SummaryData, total_games: int) -> list[dict[str, Any]]:
    rows = []
    for sort_index, ending in enumerate(FCE_CATALOG.endings):
        quantity = summary_data.total_by_stem[ending.stem]
        rows.append(
            {
                "stem": ending.stem,
                "sortIndex": sort_index,
                "rowId": ending.row_id,
                "label": ending.label,
                "displayLabel": ending.display_label,
                "chapterKey": ending.chapter_key,
                "chapter": ending.chapter_label,
                "color": ending.color,
                "quantity": quantity,
                "percentage": quantity / total_games * 100.0 if total_games else None,
                "matchedShare": (
                    quantity / summary_data.total_matches * 100.0
                    if summary_data.total_matches
                    else None
                ),
                "sourceCounts": {
                    source: summary_data.counts_by_source[source][ending.stem]
                    for source in summary_data.sources
                },
                "exactness": "exact",
            }
        )
    return rows


def sampled_game_key(row: dict[str, Any]) -> tuple[str, str, int, str]:
    headers = row.get("headers") if isinstance(row.get("headers"), dict) else {}
    return (
        str(row.get("source_pgn", "")),
        str(row.get("output_pgn", "")),
        int(row.get("game_index", 0)),
        canonical_json(headers),
    )


def compact_sampled_example_rows(
    rows: list[dict[str, Any]],
    *,
    limit: int = 100,
) -> dict[str, Any]:
    examples_by_key: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    marker_rows = 0
    for row in rows:
        marker_rows += 1
        key = sampled_game_key(row)
        if key not in examples_by_key:
            if len(examples_by_key) >= limit:
                continue
            headers = row.get("headers") if isinstance(row.get("headers"), dict) else {}
            source_pgn = str(row.get("source_pgn", ""))
            examples_by_key[key] = {
                "sourcePgn": source_pgn,
                "sourceBucket": source_bucket_label(source_pgn),
                "outputPgn": str(row.get("output_pgn", "")),
                "gameIndex": int(row.get("game_index", 0)),
                "event": str(headers.get("Event", "")),
                "site": str(headers.get("Site", "")),
                "date": str(headers.get("Date", "")),
                "round": str(headers.get("Round", "")),
                "white": str(headers.get("White", "")),
                "black": str(headers.get("Black", "")),
                "result": str(headers.get("Result", "")),
                "firstFullmove": int(row.get("fullmove", row.get("fullmove_number", 0)) or 0),
                "firstMoveSan": str(row.get("move_san", "")),
                "firstFen": str(row.get("fen", "")),
                "markerCount": 0,
            }
        if key in examples_by_key:
            examples_by_key[key]["markerCount"] += 1

    source_counts: dict[str, dict[str, Any]] = {}
    for example in examples_by_key.values():
        source_pgn = str(example["sourcePgn"])
        bucket = source_counts.setdefault(
            source_pgn,
            {
                "sourcePgn": source_pgn,
                "displayLabel": str(example["sourceBucket"]),
                "count": 0,
            },
        )
        bucket["count"] += 1

    return {
        "exactness": "sampled",
        "sampleLimit": limit,
        "gameCount": len(examples_by_key),
        "markerRowCount": marker_rows,
        "sourceSplit": list(source_counts.values()),
        "examples": list(examples_by_key.values()),
    }


def load_sampled_examples(examples_jsonl: Path) -> dict[str, Any]:
    raw_by_stem: dict[str, list[dict[str, Any]]] = {}
    with examples_jsonl.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SnapshotError(
                    f"{examples_jsonl}:{line_number}: invalid JSONL row"
                ) from exc
            stem = str(row.get("stem") or Path(str(row.get("output_pgn", ""))).stem)
            if stem not in FCE_CATALOG.endings_by_stem:
                continue
            raw_by_stem.setdefault(stem, []).append(row)
    by_stem = {
        stem: compact_sampled_example_rows(rows)
        for stem, rows in raw_by_stem.items()
    }
    return {
        "exactness": "sampled",
        "source": str(examples_jsonl),
        "sampleBasis": "up to 100 sampled games per ending, roughly balanced by source PGN",
        "byStem": by_stem,
    }


def parse_nonnegative_int_field(
    raw_value: str | None,
    *,
    path: Path,
    row_number: int,
    field: str,
) -> int:
    try:
        value = int(raw_value or "0")
    except ValueError as exc:
        raise SnapshotError(
            f"{path}:{row_number}: invalid integer for {field}: {raw_value!r}"
        ) from exc
    if value < 0:
        raise SnapshotError(f"{path}:{row_number}: negative integer for {field}: {value}")
    return value


def load_marker_count_views_csv(path: str | Path) -> dict[str, Any]:
    csv_path = Path(path).expanduser().resolve()
    by_ending: dict[str, dict[str, Any]] = {}
    row_count = 0
    first_total = 0
    all_total = 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ending", "first_game_count", "all_marker_count"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise SnapshotError(
                f"{csv_path} missing required field(s): " + ", ".join(sorted(missing))
            )
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            stem = str(row.get("ending", "")).strip()
            if stem not in FCE_CATALOG.endings_by_stem:
                raise SnapshotError(f"{csv_path}:{row_number}: unknown ending {stem!r}")
            first_count = parse_nonnegative_int_field(
                row.get("first_game_count"),
                path=csv_path,
                row_number=row_number,
                field="first_game_count",
            )
            all_count = parse_nonnegative_int_field(
                row.get("all_marker_count"),
                path=csv_path,
                row_number=row_number,
                field="all_marker_count",
            )
            if all_count < first_count:
                raise SnapshotError(
                    f"{csv_path}:{row_number}: all_marker_count {all_count} is less "
                    f"than first_game_count {first_count}"
                )
            item = by_ending.setdefault(stem, {"first": 0, "all": 0})
            item["first"] += first_count
            item["all"] += all_count
            first_total += first_count
            all_total += all_count
    return {
        "sourceCsv": str(csv_path),
        "rowCount": row_count,
        "totals": {"first": first_total, "all": all_total},
        "byEnding": by_ending,
    }


def attach_counting_views(
    snapshot: dict[str, Any],
    marker_count_views_csv: str | Path,
) -> dict[str, Any]:
    marker_counts = load_marker_count_views_csv(marker_count_views_csv)
    enriched = copy.deepcopy(snapshot)
    total_games = int(enriched["corpus"]["totalGames"])
    expected_stems = {str(row["stem"]) for row in enriched.get("rows", [])}
    missing = expected_stems.difference(marker_counts["byEnding"])
    if missing:
        raise SnapshotError(
            f"{marker_counts['sourceCsv']} is missing marker counts for: "
            + ", ".join(sorted(missing))
        )

    first_total = int(enriched["totals"]["matchedRows"])
    csv_first_total = int(marker_counts["totals"]["first"])
    if csv_first_total != first_total:
        raise SnapshotError(
            f"{marker_counts['sourceCsv']} first total {csv_first_total:,} does not "
            f"match snapshot matchedRows {first_total:,}"
        )

    all_total = int(marker_counts["totals"]["all"])
    enriched["countingViews"] = {
        "default": "first",
        "sourceCsv": marker_counts["sourceCsv"],
        "views": {
            "first": {
                "label": "First CQL marker",
                "shortLabel": "First",
                "quantityHeader": "Quantity",
                "rateHeader": "Corpus %",
                "shareHeader": "Matched Share",
                "description": (
                    "one match per output game: the first CQL marker for that "
                    "ending in that game"
                ),
                "totalMatches": first_total,
            },
            "all": {
                "label": "Every CQL marker",
                "shortLabel": "Every",
                "quantityHeader": "Half-moves",
                "rateHeader": "HM/game",
                "shareHeader": "Matched Share",
                "description": (
                    "every CQL marker is counted, so longer-lasting endings "
                    "contribute more half-move occurrences"
                ),
                "totalMatches": all_total,
            },
        },
    }

    for row in enriched.get("rows", []):
        stem = str(row["stem"])
        first_count = int(row["quantity"])
        all_count = int(marker_counts["byEnding"][stem]["all"])
        row["countingViews"] = {
            "first": {
                "quantity": first_count,
                "rateKind": "percentage",
                "rate": first_count / total_games * 100.0 if total_games else None,
                "matchedShare": first_count / first_total * 100.0 if first_total else None,
            },
            "all": {
                "quantity": all_count,
                "rateKind": "perGame",
                "rate": all_count / total_games if total_games else None,
                "matchedShare": all_count / all_total * 100.0 if all_total else None,
            },
        }
    return enriched


def load_tablebase_wdl_csv(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    csv_path = Path(path).expanduser().resolve()
    by_ending: dict[str, dict[str, dict[str, Any]]] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_fields = set(TABLEBASE_WDL_BASE_FIELDS).difference(reader.fieldnames or [])
        if missing_fields:
            raise SnapshotError(
                f"{csv_path} missing required field(s): "
                + ", ".join(sorted(missing_fields))
            )

        for row_number, row in enumerate(reader, start=2):
            ending = (row.get("ending") or "").strip()
            if not ending:
                raise SnapshotError(f"{csv_path}:{row_number}: missing ending")
            material_label = (row.get("material_label") or "").strip() or "unknown"
            material_rows = by_ending.setdefault(ending, {})
            parsed = material_rows.setdefault(
                material_label,
                {
                    "ending": ending,
                    "material_label": material_label,
                    **{field: 0 for field in TABLEBASE_WDL_INTEGER_FIELDS},
                },
            )
            for field in TABLEBASE_WDL_INTEGER_FIELDS:
                parsed[field] += parse_nonnegative_int_field(
                    row.get(field),
                    path=csv_path,
                    row_number=row_number,
                    field=field,
                )

    return {
        ending: [rows[label] for label in sorted(rows)]
        for ending, rows in sorted(by_ending.items())
    }


def aggregate_tablebase_wdl_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "ending": "",
            "material_label": "",
            **{field: 0 for field in TABLEBASE_WDL_INTEGER_FIELDS},
        }
    return {
        "ending": str(rows[0]["ending"]),
        "material_label": (
            str(rows[0]["material_label"])
            if len(rows) == 1
            else "multiple material sides"
        ),
        **{
            field: sum(int(row[field]) for row in rows)
            for field in TABLEBASE_WDL_INTEGER_FIELDS
        },
    }


def percentage_payload(count: int, denominator: int) -> dict[str, Any]:
    return {
        "count": count,
        "percentage": count / denominator * 100.0 if denominator else None,
    }


def tablebase_outcome_payload(aggregate: dict[str, Any]) -> dict[str, Any]:
    denominator = int(aggregate["evaluated_positions"])
    label = str(aggregate.get("material_label") or "")
    symmetric = (
        "symmetric" in label
        or (
            int(aggregate["symmetric_decisive"]) > 0
            and int(aggregate["side_wins"]) == 0
            and int(aggregate["side_losses"]) == 0
        )
    )
    if symmetric:
        known = int(aggregate["symmetric_decisive"]) + int(aggregate["draws"])
        items = [
            {
                "key": "decisive",
                "label": "Decisive",
                **percentage_payload(int(aggregate["symmetric_decisive"]), denominator),
            },
            {
                "key": "draw",
                "label": "Draw",
                **percentage_payload(int(aggregate["draws"]), denominator),
            },
        ]
        basis = "symmetric"
    else:
        known = (
            int(aggregate["side_wins"])
            + int(aggregate["side_draws"])
            + int(aggregate["side_losses"])
        )
        items = [
            {
                "key": "side_win",
                "label": "Win",
                **percentage_payload(int(aggregate["side_wins"]), denominator),
            },
            {
                "key": "side_draw",
                "label": "Draw",
                **percentage_payload(int(aggregate["side_draws"]), denominator),
            },
            {
                "key": "side_loss",
                "label": "Loss",
                **percentage_payload(int(aggregate["side_losses"]), denominator),
            },
        ]
        basis = "material_side"

    unknown = max(0, denominator - known)
    if unknown:
        items.append(
            {
                "key": "unknown",
                "label": "Unknown",
                **percentage_payload(unknown, denominator),
            }
        )
    return {
        "basis": basis,
        "denominator": denominator,
        "items": items,
    }


def actual_result_payload(aggregate: dict[str, Any]) -> dict[str, Any]:
    tablebase_basis = tablebase_outcome_payload(aggregate)["basis"]
    if tablebase_basis == "symmetric":
        denominator = (
            int(aggregate["actual_symmetric_decisive"])
            + int(aggregate["actual_side_draws"])
            + int(aggregate["actual_unknown_results"])
        )
        items = [
            {
                "key": "actual_decisive",
                "label": "Decisive",
                **percentage_payload(
                    int(aggregate["actual_symmetric_decisive"]),
                    denominator,
                ),
            },
            {
                "key": "actual_draw",
                "label": "Draw",
                **percentage_payload(int(aggregate["actual_side_draws"]), denominator),
            },
        ]
        basis = "symmetric"
    else:
        denominator = (
            int(aggregate["actual_side_wins"])
            + int(aggregate["actual_side_draws"])
            + int(aggregate["actual_side_losses"])
            + int(aggregate["actual_unknown_results"])
        )
        items = [
            {
                "key": "actual_side_win",
                "label": "Win",
                **percentage_payload(int(aggregate["actual_side_wins"]), denominator),
            },
            {
                "key": "actual_side_draw",
                "label": "Draw",
                **percentage_payload(int(aggregate["actual_side_draws"]), denominator),
            },
            {
                "key": "actual_side_loss",
                "label": "Loss",
                **percentage_payload(int(aggregate["actual_side_losses"]), denominator),
            },
        ]
        basis = "material_side"

    unknown = int(aggregate["actual_unknown_results"])
    if unknown:
        items.append(
            {
                "key": "actual_unknown",
                "label": "Unknown",
                **percentage_payload(unknown, denominator),
            }
        )
    return {"basis": basis, "denominator": denominator, "items": items}


def crosstab_row_payload(
    *,
    label: str,
    columns: list[tuple[str, int]],
) -> dict[str, Any]:
    denominator = sum(count for _, count in columns)
    return {
        "label": label,
        "denominator": denominator,
        "items": [
            {
                "label": item_label,
                **percentage_payload(count, denominator),
            }
            for item_label, count in columns
            if count or denominator
        ],
    }


def tablebase_result_crosstab_payload(aggregate: dict[str, Any]) -> dict[str, Any]:
    basis = tablebase_outcome_payload(aggregate)["basis"]
    if basis == "symmetric":
        rows = [
            crosstab_row_payload(
                label="TB decisive",
                columns=[
                    ("actual decisive", int(aggregate["tb_decisive_result_decisive"])),
                    ("actual draw", int(aggregate["tb_decisive_result_draw"])),
                    ("unknown", int(aggregate["tb_decisive_result_unknown"])),
                ],
            ),
            crosstab_row_payload(
                label="TB draw",
                columns=[
                    ("actual decisive", int(aggregate["tb_draw_result_decisive"])),
                    ("actual draw", int(aggregate["tb_draw_result_draw"])),
                    ("unknown", int(aggregate["tb_draw_result_unknown"])),
                ],
            ),
        ]
    else:
        rows = [
            crosstab_row_payload(
                label="TB win",
                columns=[
                    ("actual win", int(aggregate["tb_win_result_win"])),
                    ("actual draw", int(aggregate["tb_win_result_draw"])),
                    ("actual loss", int(aggregate["tb_win_result_loss"])),
                    ("unknown", int(aggregate["tb_win_result_unknown"])),
                ],
            ),
            crosstab_row_payload(
                label="TB draw",
                columns=[
                    ("actual win", int(aggregate["tb_draw_result_win"])),
                    ("actual draw", int(aggregate["tb_draw_result_draw"])),
                    ("actual loss", int(aggregate["tb_draw_result_loss"])),
                    ("unknown", int(aggregate["tb_draw_result_unknown"])),
                ],
            ),
            crosstab_row_payload(
                label="TB loss",
                columns=[
                    ("actual win", int(aggregate["tb_loss_result_win"])),
                    ("actual draw", int(aggregate["tb_loss_result_draw"])),
                    ("actual loss", int(aggregate["tb_loss_result_loss"])),
                    ("unknown", int(aggregate["tb_loss_result_unknown"])),
                ],
            ),
        ]

    denominator = int(aggregate["evaluated_positions"])
    aligned = (
        int(aggregate["tb_win_result_win"])
        + int(aggregate["tb_draw_result_draw"])
        + int(aggregate["tb_loss_result_loss"])
        + int(aggregate["tb_decisive_result_decisive"])
    )
    return {
        "basis": basis,
        "denominator": denominator,
        "aligned": percentage_payload(aligned, denominator),
        "rows": [row for row in rows if row["denominator"]],
    }


def build_tablebase_wdl_section(
    stats_by_ending: dict[str, list[dict[str, Any]]],
    *,
    source_csv: Path,
    position_basis: str = "all precomputed <=5-man FCE marker positions",
) -> dict[str, Any]:
    aggregates = [
        aggregate_tablebase_wdl_rows(rows) for rows in stats_by_ending.values()
    ]
    totals = {
        field: sum(int(row[field]) for row in aggregates)
        for field in TABLEBASE_WDL_INTEGER_FIELDS
    }
    has_actual_results = sum(
        int(totals[field]) for field in TABLEBASE_ACTUAL_RESULT_FIELDS
    ) > 0
    has_crosstab = sum(int(totals[field]) for field in TABLEBASE_CROSSTAB_FIELDS) > 0
    return {
        "exactness": "exact",
        "sourceCsv": str(source_csv),
        "rowCount": sum(len(rows) for rows in stats_by_ending.values()),
        "endingCount": len(stats_by_ending),
        "positionBasis": position_basis,
        "hasActualResults": has_actual_results,
        "hasResultCrosstab": has_crosstab,
        "totals": totals,
    }


def tablebase_wdl_row_payload(
    material_rows: list[dict[str, Any]],
    *,
    position_basis: str,
) -> dict[str, Any] | None:
    if not material_rows:
        return None
    aggregate = aggregate_tablebase_wdl_rows(material_rows)
    return {
        "exactness": "exact",
        "positionBasis": position_basis,
        "materialRows": material_rows,
        "aggregate": aggregate,
        "outcome": tablebase_outcome_payload(aggregate),
        "actualResult": actual_result_payload(aggregate),
        "resultCrosstab": tablebase_result_crosstab_payload(aggregate),
    }


def attach_tablebase_wdl_view(
    snapshot: dict[str, Any],
    tablebase_wdl_csv: str | Path,
    *,
    view_key: str = "all",
    label: str = "Every CQL marker",
    position_basis: str = "all precomputed <=5-man FCE marker positions",
) -> dict[str, Any]:
    csv_path = Path(tablebase_wdl_csv).expanduser().resolve()
    stats_by_ending = load_tablebase_wdl_csv(csv_path)
    known_stems = {str(row["stem"]) for row in snapshot.get("rows", [])}
    unknown_stems = set(stats_by_ending).difference(known_stems)
    if unknown_stems:
        raise SnapshotError(
            f"{csv_path} contains ending(s) not present in snapshot: "
            + ", ".join(sorted(unknown_stems))
        )

    enriched = copy.deepcopy(snapshot)
    section = build_tablebase_wdl_section(
        stats_by_ending,
        source_csv=csv_path,
        position_basis=position_basis,
    )
    section["viewKey"] = view_key
    section["label"] = label
    views = enriched.setdefault("tablebaseWdlViews", {})
    views[view_key] = section
    if "tablebaseWdl" not in enriched:
        enriched["tablebaseWdl"] = section
    for row in enriched.get("rows", []):
        material_rows = stats_by_ending.get(str(row["stem"]), [])
        row_views = row.setdefault("tablebaseWdlViews", {})
        row_views[view_key] = tablebase_wdl_row_payload(
            material_rows,
            position_basis=position_basis,
        )
        if "tablebaseWdl" not in row:
            row["tablebaseWdl"] = row_views[view_key]
    return enriched


def attach_tablebase_wdl(
    snapshot: dict[str, Any],
    tablebase_wdl_csv: str | Path,
) -> dict[str, Any]:
    return attach_tablebase_wdl_view(snapshot, tablebase_wdl_csv)


def build_snapshot_payload(
    *,
    manifest: dict[str, Any],
    summary_data: SummaryData,
    total_games: int,
    title: str,
    corpus_dir: Path,
    examples_jsonl: Path | None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotId": f"fce-gigabase-{manifest['fingerprint'][:12]}",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "corpus": {
            "name": "Lumbra/Lumbras Gigabase OTB",
            "source": str(corpus_dir),
            "totalGames": total_games,
            "sourceBucketCount": len(summary_data.sources),
            "exactness": "exact",
        },
        "inputs": manifest["inputs"],
        "catalog": catalog_payload(),
        "totals": {
            "summaryRows": summary_data.row_count,
            "sourceBuckets": len(summary_data.sources),
            "endingRows": len(FCE_CATALOG.endings),
            "matchedRows": summary_data.total_matches,
            "exactness": "exact",
        },
        "sourceBuckets": build_source_buckets(
            summary_data,
            manifest["inputs"]["sourcePgns"],
        ),
        "originalFceReference": original_fce_reference_payload(),
        "rows": build_rows(summary_data, total_games),
    }
    if examples_jsonl is not None:
        snapshot["sampledExamples"] = load_sampled_examples(examples_jsonl)
    return snapshot


def format_pct(value: float | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0%"
    if abs(value) < 0.01:
        return f"{value:.4f}%"
    if abs(value) < 1:
        return f"{value:.2f}%"
    return f"{value:.1f}%"


def format_count_pct(count: int, percentage: float | None) -> str:
    if percentage is None:
        return f"{count:,}"
    return f"{count:,} ({format_pct(percentage)})"


def format_per_game(value: float | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0"
    if abs(value) < 0.01:
        return f"{value:.4f}"
    if abs(value) < 1:
        return f"{value:.2f}"
    return f"{value:.1f}"


def default_counting_basis(snapshot: dict[str, Any]) -> str:
    views = snapshot.get("countingViews")
    if isinstance(views, dict):
        default = str(views.get("default", "first"))
        if default in (views.get("views") or {}):
            return default
    return "first"


def available_counting_bases(snapshot: dict[str, Any]) -> list[str]:
    views = snapshot.get("countingViews")
    if not isinstance(views, dict) or not isinstance(views.get("views"), dict):
        return ["first"]
    bases = [basis for basis in ("first", "all") if basis in views["views"]]
    return bases or ["first"]


def row_counting_view(row: dict[str, Any], basis: str) -> dict[str, Any]:
    views = row.get("countingViews") if isinstance(row.get("countingViews"), dict) else {}
    if basis in views:
        return views[basis]
    quantity = int(row["quantity"])
    return {
        "quantity": quantity,
        "rateKind": "percentage",
        "rate": row.get("percentage"),
        "matchedShare": row.get("matchedShare"),
    }


def format_counting_rate(view: dict[str, Any]) -> str:
    value = view.get("rate")
    if view.get("rateKind") == "perGame":
        return format_per_game(None if value is None else float(value))
    return format_pct(None if value is None else float(value))


def default_dataset_view(snapshot: dict[str, Any]) -> str:
    views = snapshot.get("datasetViews")
    if isinstance(views, dict):
        default = str(views.get("default", "all"))
        if default in (views.get("views") or {}):
            return default
    return "all"


def available_dataset_views(snapshot: dict[str, Any]) -> list[str]:
    views = snapshot.get("datasetViews")
    if not isinstance(views, dict) or not isinstance(views.get("views"), dict):
        return ["all"]
    preferred = [key for key in ("all", "otb", "online") if key in views["views"]]
    rest = [key for key in views["views"] if key not in preferred]
    return preferred + rest or ["all"]


def dataset_view(snapshot: dict[str, Any], key: str | None = None) -> dict[str, Any] | None:
    views = snapshot.get("datasetViews")
    if not isinstance(views, dict) or not isinstance(views.get("views"), dict):
        return None
    view_key = key or default_dataset_view(snapshot)
    view = views["views"].get(view_key)
    return view if isinstance(view, dict) else None


def format_dataset_row_payload(row_view: dict[str, Any]) -> dict[str, Any]:
    quantity = int(row_view.get("quantity", 0))
    percentage = row_view.get("percentage")
    matched_share = row_view.get("matchedShare")
    payload = {
        "quantity": {"text": f"{quantity:,}", "sort": quantity},
        "rate": {
            "text": format_pct(None if percentage is None else float(percentage)),
            "sort": 0 if percentage is None else float(percentage),
        },
        "share": {
            "text": format_pct(None if matched_share is None else float(matched_share)),
            "sort": 0 if matched_share is None else float(matched_share),
        },
    }
    if isinstance(row_view.get("runLengthHistogram"), dict):
        payload["runLengthHistogram"] = {
            str(length): int(count)
            for length, count in row_view["runLengthHistogram"].items()
        }
    stats = row_view.get("tablebaseWdl")
    if isinstance(stats, dict):
        aggregate = stats["aggregate"]
        tablebase_payload: dict[str, Any] = {
            "positions": {
                "text": f"{int(aggregate['evaluated_positions']):,}",
                "sort": int(aggregate["evaluated_positions"]),
            },
            "wdl": {
                "html": render_tablebase_outcome(stats),
                "sort": outcome_sort_value(stats["outcome"]),
            },
            "detailHtml": render_tablebase_detail_inner(stats),
        }
        if "actualResult" in stats:
            tablebase_payload["actual"] = {
                "html": render_actual_result(stats),
                "sort": outcome_sort_value(stats["actualResult"]),
            }
        payload["tablebase"] = tablebase_payload
    return payload


def build_dataset_view_render_data(snapshot: dict[str, Any]) -> dict[str, Any]:
    views = snapshot.get("datasetViews", {}).get("views", {})
    payload: dict[str, Any] = {
        "default": default_dataset_view(snapshot),
        "views": {},
    }
    for key in available_dataset_views(snapshot):
        view = views.get(key, {}) if isinstance(views, dict) else {}
        rows = {
            stem: format_dataset_row_payload(row_view)
            for stem, row_view in (view.get("rows") or {}).items()
        }
        payload["views"][key] = {
            "label": str(view.get("label") or key),
            "shortLabel": str(view.get("shortLabel") or view.get("label") or key),
            "description": str(view.get("description") or ""),
            "metrics": {
                "totalGames": int(view.get("totalGames", 0)),
                "matchedGames": int(view.get("matchedGames", 0)),
                "sourceBuckets": int(view.get("sourceBuckets", 0)),
                "matchedRows": int(view.get("matchedRows", 0)),
                "incidenceRunLengthHistogram": {
                    str(length): int(count)
                    for length, count in (view.get("incidenceRunLengthHistogram") or {}).items()
                },
                "matchedGameRunLengthHistogram": {
                    str(length): int(count)
                    for length, count in (view.get("matchedGameRunLengthHistogram") or {}).items()
                },
            },
            "sourcePgns": [str(source) for source in view.get("sourcePgns", [])],
            "sourceIncidenceRunLengthHistograms": {
                str(source): {
                    str(length): int(count)
                    for length, count in histogram.items()
                }
                for source, histogram in (
                    view.get("sourceIncidenceRunLengthHistograms") or {}
                ).items()
            },
            "sourceMatchedGameRunLengthHistograms": {
                str(source): {
                    str(length): int(count)
                    for length, count in histogram.items()
                }
                for source, histogram in (
                    view.get("sourceMatchedGameRunLengthHistograms") or {}
                ).items()
            },
            "rows": rows,
        }
        threshold_views = view.get("thresholdViews")
        if isinstance(threshold_views, dict):
            payload["views"][key]["thresholds"] = {}
            for threshold, threshold_view in threshold_views.items():
                if not isinstance(threshold_view, dict):
                    continue
                metrics = threshold_view.get("metrics") or {}
                payload["views"][key]["thresholds"][str(threshold)] = {
                    "metrics": {
                        "totalGames": int(metrics.get("totalGames", 0)),
                        "matchedGames": int(metrics.get("matchedGames", 0)),
                        "sourceBuckets": int(metrics.get("sourceBuckets", 0)),
                        "matchedRows": int(metrics.get("matchedRows", 0)),
                        "tablebasePositions": int(metrics.get("tablebasePositions", 0)),
                        "tablebaseEndings": int(metrics.get("tablebaseEndings", 0)),
                    },
                    "sourceBuckets": {
                        str(source): {
                            "incidences": int(values.get("incidences", 0)),
                            "matchedGames": int(values.get("matchedGames", 0)),
                        }
                        for source, values in (
                            threshold_view.get("sourceBuckets") or {}
                        ).items()
                    },
                    "rows": {
                        stem: format_dataset_row_payload(row_view)
                        for stem, row_view in (
                            threshold_view.get("rows") or {}
                        ).items()
                    },
                }
    return payload


def has_run_length_histograms(snapshot: dict[str, Any]) -> bool:
    views = snapshot.get("datasetViews", {}).get("views", {})
    if not isinstance(views, dict):
        return False
    for view in views.values():
        if isinstance(view, dict) and view.get("incidenceRunLengthHistogram"):
            return True
    return False


def tablebase_stats_for_basis(row: dict[str, Any], basis: str) -> dict[str, Any] | None:
    views = row.get("tablebaseWdlViews")
    if isinstance(views, dict) and basis in views:
        stats = views[basis]
        return stats if isinstance(stats, dict) else None
    stats = row.get("tablebaseWdl")
    return stats if isinstance(stats, dict) else None


def tablebase_section_for_basis(snapshot: dict[str, Any], basis: str) -> dict[str, Any] | None:
    views = snapshot.get("tablebaseWdlViews")
    if isinstance(views, dict) and basis in views:
        section = views[basis]
        return section if isinstance(section, dict) else None
    section = snapshot.get("tablebaseWdl")
    return section if isinstance(section, dict) else None


def render_metric(label: str, value: str, *, metric_id: str | None = None) -> str:
    id_attr = f' id="{html.escape(metric_id)}"' if metric_id else ""
    return (
        '<div class="metric">'
        f"<span>{html.escape(label)}</span>"
        f"<strong{id_attr}>{html.escape(value)}</strong>"
        "</div>"
    )


def outcome_sort_value(payload: dict[str, Any]) -> str:
    if not payload.get("items"):
        return "-1"
    percentage = payload["items"][0].get("percentage")
    return "-1" if percentage is None else f"{float(percentage):.8f}"


def outcome_segment_class(key: str) -> str:
    if "win" in key:
        return "wdl-win"
    if "loss" in key:
        return "wdl-loss"
    if "decisive" in key:
        return "wdl-decisive"
    if "unknown" in key:
        return "wdl-unknown"
    return "wdl-draw"


def outcome_short_label(label: str) -> str:
    short_labels = {
        "Win": "W",
        "Draw": "D",
        "Loss": "L",
        "Decisive": "Dec",
        "Unknown": "Unk",
    }
    return short_labels.get(label, label)


def render_wdl_bar(payload: dict[str, Any]) -> str:
    if not payload.get("items") or int(payload.get("denominator") or 0) == 0:
        return '<span class="muted">No WDL data</span>'

    aria_parts = []
    segments = []
    summary = []
    for item in payload["items"]:
        percentage = item.get("percentage")
        pct = 0.0 if percentage is None else float(percentage)
        count = int(item["count"])
        label = str(item["label"])
        pct_text = format_pct(pct)
        count_pct = format_count_pct(count, percentage)
        aria_parts.append(f"{label} {count_pct}")
        segment_text = pct_text if pct >= 7.0 else ""
        tiny_class = " is-tiny" if pct < 7.0 else ""
        segments.append(
            f'<span class="wdl-segment {outcome_segment_class(str(item["key"]))}{tiny_class}" '
            f'style="width:{pct:.8f}%" title="{html.escape(label)} {html.escape(count_pct)}">'
            f"{html.escape(segment_text)}</span>"
        )
        summary.append(
            f"<span><strong>{html.escape(outcome_short_label(label))}</strong> "
            f"{html.escape(f'{count:,}')}</span>"
        )

    return (
        f'<div class="wdl-widget" role="img" aria-label="{html.escape(", ".join(aria_parts))}">'
        f'<div class="wdl-bar">{"".join(segments)}</div>'
        f'<div class="wdl-counts">{"".join(summary)}</div>'
        "</div>"
    )


def render_outcome_payload(payload: dict[str, Any]) -> str:
    return render_wdl_bar(payload)


def render_tablebase_outcome(stats: dict[str, Any]) -> str:
    return render_outcome_payload(stats["outcome"])


def render_actual_result(stats: dict[str, Any]) -> str:
    return render_outcome_payload(stats["actualResult"])


def render_result_crosstab(stats: dict[str, Any]) -> str:
    rows = []
    for matrix_row in stats["resultCrosstab"]["rows"]:
        cells = []
        for item in matrix_row["items"]:
            cells.append(
                "<span>"
                f"<strong>{html.escape(str(item['label']))}</strong> "
                f"{html.escape(format_count_pct(int(item['count']), item['percentage']))}"
                "</span>"
            )
        rows.append(
            '<div class="matrix-row">'
            f"<span>{html.escape(str(matrix_row['label']))}</span>"
            f"<div>{''.join(cells)}</div>"
            "</div>"
        )
    aligned = stats["resultCrosstab"]["aligned"]
    rows.append(
        '<div class="matrix-row matrix-summary">'
        "<span>Aligned</span>"
        f"<div>{html.escape(format_count_pct(int(aligned['count']), aligned['percentage']))}</div>"
        "</div>"
    )
    return '<div class="matrix-cell-inner">' + "".join(rows) + "</div>"


def render_tablebase_cells(
    row: dict[str, Any],
    *,
    show_actual_results: bool,
    basis: str = "first",
) -> str:
    stats = tablebase_stats_for_basis(row, basis)
    if not stats:
        base_cells = (
            '<td class="num tb-positions-cell" data-label="TB positions" data-sort="0">0</td>'
            '<td class="muted wdl-cell tb-wdl-cell" data-label="Tablebase WDL" data-sort="-1">No &lt;=5-man marker positions</td>'
        )
        result_cells = (
            '<td class="muted wdl-cell actual-result-cell" data-label="Actual result" data-sort="-1">No result stats</td>'
            if show_actual_results
            else ""
        )
        return base_cells + result_cells
    aggregate = stats["aggregate"]
    result_cells = ""
    if show_actual_results:
        result_cells = (
            f'<td class="wdl-cell actual-result-cell" data-label="Actual result" data-sort="{outcome_sort_value(stats["actualResult"])}">'
            f"{render_actual_result(stats)}</td>"
        )
    return (
        f'<td class="num tb-positions-cell" data-label="TB positions" data-sort="{int(aggregate["evaluated_positions"])}">{int(aggregate["evaluated_positions"]):,}</td>'
        f'<td class="wdl-cell tb-wdl-cell" data-label="Tablebase WDL" data-sort="{outcome_sort_value(stats["outcome"])}">{render_tablebase_outcome(stats)}</td>'
        f"{result_cells}"
    )


def render_methodology(snapshot: dict[str, Any], *, show_actual_results: bool) -> str:
    corpus = snapshot["corpus"]
    combined_comments = bool(
        isinstance(snapshot.get("methodology"), dict)
        and snapshot["methodology"].get("combinedComments")
    )
    tb = snapshot.get("tablebaseWdl") or {}
    tablebase_text = ""
    if tb:
        if snapshot.get("tablebaseMode") == "combined-filtered":
            tablebase_text = (
                "<p>"
                f"Tablebase WDL uses {int(tb['totals']['evaluated_positions']):,} "
                "first marker positions per game and FCE ending with five pieces "
                "or fewer in the default All/1 view. The corpus and half-move "
                "controls switch to precomputed Syzygy WDL/result aggregates for "
                "the active view; no Stockfish scores are included in this page."
                "</p>"
            )
        else:
            tablebase_text = (
                "<p>"
                f"Tablebase WDL uses {int(tb['totals']['evaluated_positions']):,} "
                "first-CQL-marker positions with five pieces or fewer. Each position "
                "was evaluated once with Syzygy WDL; no Stockfish scores are included "
                "in this page. If the first marker in a matched game has more than "
                "five pieces, it is kept in the incidence and actual-result counts "
                "but skipped for tablebase WDL."
                "</p>"
            )
    result_text = ""
    if show_actual_results:
        if snapshot.get("tablebaseMode") == "combined-filtered":
            result_text = (
                "<p>"
                "Actual results are PGN Result tags interpreted from the "
                "named-material perspective. The TB -> result matrix compares "
                "Syzygy WDL with the final PGN result for the same first <=5-man "
                "marker positions that pass the active source and persistence filters."
                "</p>"
            )
        else:
            result_text = (
                "<p>"
                "Actual results are PGN Result tags for the first CQL marker in each "
                "matched game, interpreted from the named-material perspective. The "
                "TB -> result matrix is narrower: it compares Syzygy WDL with the "
                "final PGN result only for first markers that are tablebase-eligible."
                "</p>"
            )
    run_length_text = ""
    if combined_comments and bool(
        isinstance(snapshot.get("methodology"), dict)
        and snapshot["methodology"].get("runLengthThresholds")
    ):
        run_length_text = (
            "<p>"
            "The half-move run control filters incidence by persistence. A "
            "threshold of 1 is the normal per-game incidence count; a threshold "
            "of 2 counts only game-ending pairs where that ending's first run "
            "lasts at least two consecutive half-move positions, and so on."
            "</p>"
        )
    if combined_comments:
        incidence_text = (
            "<p>"
            f"The incidence snapshot covers {int(corpus['totalGames']):,} "
            "Lumbra/Lumbras Gigabase games across OTB and online source buckets. "
            "It is built from compressed combined CQL output PGNs whose comments "
            "are FCE stems such as {10-2Qr}. Within one source game, repeated "
            "comments for the same ending count once; different endings in the "
            "same game can still each count, preserving FCE-style overlapping "
            "per-ending incidence."
            "</p>"
        )
    else:
        incidence_text = (
            "<p>"
            f"The incidence snapshot covers {int(corpus['totalGames']):,} "
            "Lumbra/Lumbras Gigabase OTB games across 13 source buckets. Counts are "
            "the exact FCE CQL row matches from the completed 390-job run. For the "
            "tablebase and actual-result sections, each matched output game contributes "
            "its first CQL marker only. Endings can overlap, so row matches are not "
            "unique-game counts."
            "</p>"
        )
    return (
        '<section class="methodology">'
        "<h2>Methodology</h2>"
        f"{incidence_text}"
        f"{run_length_text}"
        f"{tablebase_text}"
        "<p>"
        "W/D/L is colour-neutral. For asymmetric endings, wins and losses are "
        "assigned to the player with the named material, such as the queen player "
        "in Q vs R. Symmetric endings are shown as decisive/draw."
        "</p>"
        "<p>"
        "Sample boards use the Lichess lila cburnett SVG piece set and link "
        "directly to the corresponding Lichess analysis position."
        "</p>"
        f"{result_text}"
        "<p>"
        "The reference table below is the original Fundamental Chess Endings "
        f"frequency table transcription from <a href=\"{html.escape(FCE_REFERENCE_SOURCE_URL)}\">"
        "the chess endgame frequency table</a>; it is included as a baseline, not "
        "as a recomputation from this corpus."
        "</p>"
        "</section>"
    )


def render_original_reference_rows(snapshot: dict[str, Any]) -> str:
    current_by_stem = {str(row["stem"]): row for row in snapshot["rows"]}
    reference = snapshot.get("originalFceReference") or original_fce_reference_payload()
    rows = []
    for row in reference["rows"]:
        stem = str(row["stem"])
        current = current_by_stem.get(stem, {})
        current_quantity = int(current.get("quantity", 0))
        current_percentage = current.get("percentage")
        rows.append(
            f'<tr class="reference-row" data-stem="{html.escape(stem)}">'
            f'<td data-label="ID" data-sort="{int(row["sortIndex"])}">{html.escape(str(row["rowId"]))}</td>'
            f'<td data-label="Ending" data-sort="{html.escape(str(row["label"]))}">{html.escape(str(row["label"]))}</td>'
            f'<td data-label="FCE quantity" data-sort="{int(row["quantitySort"])}">{html.escape(str(row["quantity"]))}</td>'
            f'<td class="num" data-label="FCE %" data-sort="{float(row["percentage"])}">{format_pct(float(row["percentage"]))}</td>'
            f'<td class="num gigabase-quantity-cell" data-label="Gigabase quantity" data-sort="{current_quantity}">{current_quantity:,}</td>'
            f'<td class="num gigabase-rate-cell" data-label="Gigabase %" data-sort="{current_percentage or 0}">{format_pct(current_percentage)}</td>'
            "</tr>"
        )
    return "\n".join(rows)


def render_column_explainer(
    *,
    has_tablebase_wdl: bool,
    show_actual_results: bool,
) -> str:
    items = [
        (
            "Quantity",
            "exact count of CQL row matches for that FCE ending across the corpus.",
        ),
        (
            "Corpus %",
            "Quantity divided by total original games. Because endings can overlap, "
            "this is not a unique-game percentage.",
        ),
        (
            "Matched share",
            "Quantity divided by all FCE row matches in the snapshot. This answers "
            "how much of the overlapping FCE table each ending occupies.",
        ),
    ]
    if has_tablebase_wdl:
        items.extend(
            [
                (
                    "TB positions",
                    "first CQL marker occurrences with five pieces or fewer that "
                    "were evaluated with Syzygy.",
                ),
                (
                    "Tablebase WDL",
                    "Syzygy result at the marker position, viewed from the "
                    "named-material perspective. These are exact position-occurrence counts.",
                ),
            ]
        )
    if show_actual_results:
        items.extend(
            [
                (
                    "Actual result",
                    "final PGN Result tag for the first CQL marker in each matched "
                    "ending game, viewed from the named-material perspective.",
                ),
                (
                    "TB -> result",
                    "the expandable cross-tab comparing tablebase WDL with the "
                    "final PGN result for tablebase-eligible first markers.",
                ),
            ]
        )
    return (
        '<section class="column-guide">'
        "<h2>How To Read</h2>"
        "<dl>"
        + "".join(
            f"<dt>{html.escape(label)}</dt><dd>{html.escape(description)}</dd>"
            for label, description in items
        )
        + "</dl>"
        "</section>"
    )


def sampled_examples_for_stem(
    snapshot: dict[str, Any],
    stem: str,
) -> dict[str, Any] | None:
    sampled = snapshot.get("sampledExamples")
    if not isinstance(sampled, dict):
        return None
    by_stem = sampled.get("byStem")
    if not isinstance(by_stem, dict):
        return None
    stem_payload = by_stem.get(stem)
    if isinstance(stem_payload, list):
        return compact_sampled_example_rows(stem_payload)
    if isinstance(stem_payload, dict):
        return stem_payload
    return None


def render_source_split(source_split: list[dict[str, Any]]) -> str:
    if not source_split:
        return ""
    items = []
    for bucket in sorted(source_split, key=lambda item: str(item.get("displayLabel", ""))):
        items.append(
            "<span>"
            f"{html.escape(str(bucket.get('displayLabel', '')))} "
            f"{int(bucket.get('count', 0)):,}"
            "</span>"
        )
    return '<div class="example-split">' + "".join(items) + "</div>"


LILA_CBURNETT_PIECE_BASE_URL = (
    "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece/cburnett"
)
PIECE_ASSET_NAMES = {
    "K": "wK.svg",
    "Q": "wQ.svg",
    "R": "wR.svg",
    "B": "wB.svg",
    "N": "wN.svg",
    "P": "wP.svg",
    "k": "bK.svg",
    "q": "bQ.svg",
    "r": "bR.svg",
    "b": "bB.svg",
    "n": "bN.svg",
    "p": "bP.svg",
}


def lichess_analysis_url(fen: str) -> str:
    if not fen:
        return "https://lichess.org/analysis"
    fen_path = urllib.parse.quote(fen.replace(" ", "_"), safe="/_-")
    return f"https://lichess.org/analysis/standard/{fen_path}"


def render_position_board(fen: str, *, label: str) -> str:
    pieces = []
    board_part = fen.split()[0] if fen else ""
    ranks = board_part.split("/")
    if len(ranks) == 8:
        for rank_index, rank_text in enumerate(ranks):
            file_index = 0
            for token in rank_text:
                if token.isdigit():
                    file_index += int(token)
                    continue
                asset_name = PIECE_ASSET_NAMES.get(token)
                if asset_name is not None and file_index < 8:
                    piece_class = "piece-white" if token.isupper() else "piece-black"
                    src = f"{LILA_CBURNETT_PIECE_BASE_URL}/{asset_name}"
                    pieces.append(
                        f'<img class="board-piece {piece_class}" '
                        f'style="--file:{file_index};--rank:{rank_index}" '
                        f'src="{html.escape(src)}" alt="" loading="lazy" decoding="async">'
                    )
                file_index += 1
    return (
        '<a class="board-link" '
        f'href="{html.escape(lichess_analysis_url(fen))}" '
        'target="_blank" rel="noopener noreferrer" '
        f'aria-label="{html.escape(label)}">'
        f"{''.join(pieces)}"
        "</a>"
    )


def render_example_card(example: dict[str, Any]) -> str:
    white = str(example.get("white", ""))
    black = str(example.get("black", ""))
    title = " vs ".join(part for part in (white, black) if part) or "Sampled game"
    fen = str(example.get("firstFen", ""))
    move = str(example.get("firstMoveSan", ""))
    fullmove = int(example.get("firstFullmove", 0) or 0)
    marker_label = f"{move} ({fullmove})" if move and fullmove else move or str(fullmove or "")
    meta_items = [
        ("Result", str(example.get("result", ""))),
        ("Date", str(example.get("date", ""))),
        ("Source", str(example.get("sourceBucket", ""))),
        ("Game", f"{int(example.get('gameIndex', 0)):,}"),
        ("First marker", marker_label),
        ("Markers", f"{int(example.get('markerCount', 0)):,}"),
    ]
    meta_html = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>"
        for label, value in meta_items
        if value
    )
    subtitle_parts = [
        str(example.get("event", "")),
        str(example.get("site", "")),
        str(example.get("round", "")),
    ]
    subtitle = " | ".join(part for part in subtitle_parts if part)
    return (
        '<article class="example-card">'
        f"{render_position_board(fen, label='Open sampled position on Lichess analysis board')}"
        '<div class="example-meta">'
        f'<strong class="example-title">{html.escape(title)}</strong>'
        f'<span class="example-subtitle">{html.escape(subtitle)}</span>'
        f'<dl>{meta_html}</dl>'
        "</div>"
        "</article>"
    )


def render_sampled_examples(sampled: dict[str, Any] | None) -> str:
    if not sampled:
        return (
            '<section class="detail-panel">'
            "<h3>Sampled Examples</h3>"
            '<p class="detail-note">No sampled examples are embedded for this ending.</p>'
            "</section>"
        )
    examples = sampled.get("examples") if isinstance(sampled.get("examples"), list) else []
    cards_html = (
        '<div class="examples-grid">'
        + "".join(render_example_card(example) for example in examples)
        + "</div>"
        if examples
        else '<p class="detail-note">No sampled examples are embedded for this ending.</p>'
    )
    return (
        '<section class="detail-panel examples-panel">'
        "<h3>Sampled Examples</h3>"
        '<p class="detail-note">'
        f"{int(sampled.get('gameCount', 0)):,} sampled game(s), "
        f"{int(sampled.get('markerRowCount', 0)):,} sampled marker row(s). "
        "The sample is approximate and balanced across source PGNs where possible."
        "</p>"
        f"{render_source_split(list(sampled.get('sourceSplit') or []))}"
        f"{cards_html}"
        "</section>"
    )


def render_tablebase_detail_inner(stats: dict[str, Any] | None) -> str:
    if stats and stats.get("resultCrosstab", {}).get("rows"):
        return "<h3>TB -> Result</h3>" + render_result_crosstab(stats)
    return (
        "<h3>TB -> Result</h3>"
        '<p class="detail-note">No <=5-man tablebase/result matrix is available for this ending.</p>'
    )


def render_row_detail(
    row: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    show_actual_results: bool,
    basis: str = "first",
) -> str:
    panels = []
    stats = tablebase_stats_for_basis(row, basis)
    if show_actual_results:
        panels.append(
            '<section class="detail-panel tb-result-panel">'
            f"{render_tablebase_detail_inner(stats)}"
            "</section>"
        )
    panels.append(render_sampled_examples(sampled_examples_for_stem(snapshot, str(row["stem"]))))
    return '<div class="detail-grid">' + "".join(panels) + "</div>"


def build_counting_view_render_data(
    snapshot: dict[str, Any],
    *,
    has_tablebase_wdl: bool,
    show_actual_results: bool,
) -> dict[str, Any]:
    counting_views = snapshot.get("countingViews", {})
    view_meta = counting_views.get("views", {}) if isinstance(counting_views, dict) else {}
    bases = available_counting_bases(snapshot)
    payload: dict[str, Any] = {
        "default": default_counting_basis(snapshot),
        "views": {},
    }
    for basis in bases:
        meta = dict(view_meta.get(basis, {})) if isinstance(view_meta, dict) else {}
        meta.setdefault("quantityHeader", "Quantity" if basis == "first" else "Half-moves")
        meta.setdefault("rateHeader", "Corpus %" if basis == "first" else "HM/game")
        meta.setdefault("shareHeader", "Matched Share")
        meta.setdefault(
            "description",
            "one match per output game"
            if basis == "first"
            else "every CQL marker is counted as a half-move occurrence",
        )
        section = tablebase_section_for_basis(snapshot, basis)
        meta["tablebasePositions"] = (
            int(section["totals"]["evaluated_positions"]) if section else 0
        )
        rows: dict[str, Any] = {}
        for row in snapshot.get("rows", []):
            stem = str(row["stem"])
            count_view = row_counting_view(row, basis)
            rate = count_view.get("rate")
            share = count_view.get("matchedShare")
            row_payload: dict[str, Any] = {
                "quantity": {
                    "text": f"{int(count_view['quantity']):,}",
                    "sort": int(count_view["quantity"]),
                },
                "rate": {
                    "text": format_counting_rate(count_view),
                    "sort": 0 if rate is None else float(rate),
                },
                "share": {
                    "text": format_pct(None if share is None else float(share)),
                    "sort": 0 if share is None else float(share),
                },
            }
            if has_tablebase_wdl:
                stats = tablebase_stats_for_basis(row, basis)
                if stats:
                    aggregate = stats["aggregate"]
                    row_payload["tablebase"] = {
                        "positions": {
                            "text": f"{int(aggregate['evaluated_positions']):,}",
                            "sort": int(aggregate["evaluated_positions"]),
                        },
                        "wdl": {
                            "html": render_tablebase_outcome(stats),
                            "sort": outcome_sort_value(stats["outcome"]),
                        },
                        "detailHtml": render_tablebase_detail_inner(stats),
                    }
                    if show_actual_results:
                        row_payload["tablebase"]["actual"] = {
                            "html": render_actual_result(stats),
                            "sort": outcome_sort_value(stats["actualResult"]),
                        }
                else:
                    tablebase_payload: dict[str, Any] = {
                        "positions": {"text": "0", "sort": 0},
                        "wdl": {
                            "html": "No &lt;=5-man marker positions",
                            "sort": -1,
                        },
                        "detailHtml": render_tablebase_detail_inner(None),
                    }
                    if show_actual_results:
                        tablebase_payload["actual"] = {
                            "html": "No result stats",
                            "sort": -1,
                        }
                    row_payload["tablebase"] = tablebase_payload
            rows[stem] = row_payload
        payload["views"][basis] = {"meta": meta, "rows": rows}
    return payload


def render_counting_basis_controls(snapshot: dict[str, Any]) -> str:
    bases = available_counting_bases(snapshot)
    if len(bases) <= 1:
        return ""
    views = snapshot.get("countingViews", {}).get("views", {})
    default = default_counting_basis(snapshot)
    buttons = []
    for basis in bases:
        meta = views.get(basis, {})
        label = str(meta.get("shortLabel") or meta.get("label") or basis)
        pressed = "true" if basis == default else "false"
        active = " is-active" if basis == default else ""
        buttons.append(
            f'<button class="segmented-button{active}" type="button" '
            f'data-counting-basis="{html.escape(basis)}" aria-pressed="{pressed}">'
            f"{html.escape(label)}</button>"
        )
    return (
        '<div class="table-controls">'
        '<span class="control-label">Counting basis</span>'
        f'<div class="segmented" role="group" aria-label="Counting basis">{"".join(buttons)}</div>'
        '<span id="counting-basis-note" class="control-note"></span>'
        "</div>"
    )


def render_dataset_view_controls(snapshot: dict[str, Any]) -> str:
    view_keys = available_dataset_views(snapshot)
    if len(view_keys) <= 1:
        return ""
    views = snapshot.get("datasetViews", {}).get("views", {})
    default = default_dataset_view(snapshot)
    buttons = []
    for key in view_keys:
        meta = views.get(key, {}) if isinstance(views, dict) else {}
        label = str(meta.get("shortLabel") or meta.get("label") or key)
        pressed = "true" if key == default else "false"
        active = " is-active" if key == default else ""
        buttons.append(
            f'<button class="segmented-button{active}" type="button" '
            f'data-dataset-view="{html.escape(key)}" aria-pressed="{pressed}">'
            f"{html.escape(label)}</button>"
        )
    return (
        '<div class="table-controls">'
        '<span class="control-label">Corpus</span>'
        f'<div class="segmented" role="group" aria-label="Corpus view">{"".join(buttons)}</div>'
        '<span id="dataset-view-note" class="control-note"></span>'
        "</div>"
    )


def render_run_length_controls(snapshot: dict[str, Any]) -> str:
    if not has_run_length_histograms(snapshot):
        return ""
    buttons = []
    for threshold in (1, 2, 5, 10, 20):
        active = " is-active" if threshold == 1 else ""
        pressed = "true" if threshold == 1 else "false"
        label = str(threshold)
        buttons.append(
            f'<button class="segmented-button{active}" type="button" '
            f'data-run-length-threshold="{threshold}" aria-pressed="{pressed}">'
            f"{label}</button>"
        )
    return (
        '<div class="table-controls run-length-controls">'
        '<span class="control-label">Minimum half-move run</span>'
        f'<div class="segmented" role="group" aria-label="Minimum half-move run">{"".join(buttons)}</div>'
        '<span id="run-length-note" class="control-note">1 keeps every matched game-ending incidence.</span>'
        "</div>"
    )


def render_snapshot_html(snapshot: dict[str, Any], *, title: str | None = None) -> str:
    snapshot = copy.deepcopy(snapshot)
    snapshot.setdefault("originalFceReference", original_fce_reference_payload())
    page_title = title or snapshot.get("title", "FCE Gigabase Snapshot")
    data_json = canonical_json(snapshot).replace("</", "<\\/")
    default_basis = default_counting_basis(snapshot)
    tablebase_sections = [
        tablebase_section_for_basis(snapshot, basis)
        for basis in available_counting_bases(snapshot)
    ]
    has_tablebase_wdl = any(bool(section) for section in tablebase_sections)
    show_actual_results = any(
        bool(section and section.get("hasActualResults")) for section in tablebase_sections
    )
    counting_view_json = canonical_json(
        build_counting_view_render_data(
            snapshot,
            has_tablebase_wdl=has_tablebase_wdl,
            show_actual_results=show_actual_results,
        )
    ).replace("</", "<\\/")
    dataset_view_json = canonical_json(
        build_dataset_view_render_data(snapshot)
    ).replace("</", "<\\/")
    active_dataset_view = dataset_view(snapshot, default_dataset_view(snapshot))
    active_tablebase_section = (
        tablebase_section_for_basis(snapshot, default_basis) or snapshot.get("tablebaseWdl")
    )
    has_sampled_examples = bool(snapshot.get("sampledExamples"))
    has_detail_rows = show_actual_results or has_sampled_examples
    actual_headers = "<th>Actual result</th>" if show_actual_results else ""
    tablebase_headers = (
        f"<th class=\"num\">TB positions</th><th>Tablebase WDL</th>{actual_headers}"
        if has_tablebase_wdl
        else ""
    )
    ending_colspan = 5 + (2 + (1 if show_actual_results else 0) if has_tablebase_wdl else 0)
    ending_table_rows = []
    for row in snapshot["rows"]:
        count_view = row_counting_view(row, default_basis)
        stem_attr = html.escape(str(row["stem"]))
        detail_id = f"ending-detail-{int(row['sortIndex'])}"
        row_attrs = (
            f'class="ending-row{" expandable" if has_detail_rows else ""}" '
            f'data-row-kind="data" data-stem="{stem_attr}" data-detail-id="{detail_id}" '
            f'aria-expanded="false" tabindex="0"'
            if has_detail_rows
            else f'data-row-kind="data" data-stem="{stem_attr}"'
        )
        toggle_html = (
            '<button class="row-toggle" type="button" aria-label="Show row details">+</button>'
            if has_detail_rows
            else ""
        )
        ending_table_rows.append(
            f"<tr {row_attrs}>"
            f'<td data-label="ID" data-sort="{row["sortIndex"]}">{toggle_html}{html.escape(row["rowId"] or "")}</td>'
            f'<td data-label="Ending" data-sort="{html.escape(row["label"])}"><span class="swatch" style="background:{html.escape(row["color"])}"></span>'
            f"{html.escape(row['label'])}</td>"
            f'<td class="num quantity-cell" data-label="Quantity" data-sort="{int(count_view["quantity"])}">{int(count_view["quantity"]):,}</td>'
            f'<td class="num rate-cell" data-label="Corpus %" data-sort="{count_view["rate"] or 0}">{format_counting_rate(count_view)}</td>'
            f'<td class="num share-cell" data-label="Matched share" data-sort="{count_view["matchedShare"] or 0}">{format_pct(count_view["matchedShare"])}</td>'
            f"{render_tablebase_cells(row, show_actual_results=show_actual_results, basis=default_basis) if has_tablebase_wdl else ''}"
            "</tr>"
        )
        for auxiliary in row.get("auxiliaryRows", []):
            aux_count_view = row_counting_view(auxiliary, default_basis)
            empty_tb_cells = ""
            if has_tablebase_wdl:
                empty_tb_cells = (
                    '<td class="num tb-positions-cell" data-label="TB positions" data-sort="0">0</td>'
                    '<td class="muted wdl-cell tb-wdl-cell" data-label="Tablebase WDL" data-sort="-1">No &lt;=5-man marker positions</td>'
                )
                if show_actual_results:
                    empty_tb_cells += (
                        '<td class="muted wdl-cell actual-result-cell" data-label="Actual result" data-sort="-1">No result stats</td>'
                    )
            ending_table_rows.append(
                f'<tr class="auxiliary-row" data-row-kind="auxiliary" '
                f'data-parent-stem="{stem_attr}" data-stem="{html.escape(str(auxiliary["stem"]))}">'
                f'<td data-label="ID" data-sort="{auxiliary["sortIndex"]}"></td>'
                f'<td data-label="Ending" data-sort="{html.escape(auxiliary["label"])}">'
                f'<span class="subrow-marker">&#8627;</span>{html.escape(auxiliary["label"])}</td>'
                f'<td class="num quantity-cell" data-label="Quantity" data-sort="{int(aux_count_view["quantity"])}">{int(aux_count_view["quantity"]):,}</td>'
                f'<td class="num rate-cell" data-label="Corpus %" data-sort="{aux_count_view["rate"] or 0}">{format_counting_rate(aux_count_view)}</td>'
                f'<td class="num share-cell" data-label="Matched share" data-sort="{aux_count_view["matchedShare"] or 0}">{format_pct(aux_count_view["matchedShare"])}</td>'
                f"{empty_tb_cells}"
                "</tr>"
            )
        if has_detail_rows:
            ending_table_rows.append(
                f'<tr id="{detail_id}" class="detail-row" data-row-kind="detail" hidden>'
                f'<td colspan="{ending_colspan}">'
                f"{render_row_detail(row, snapshot=snapshot, show_actual_results=show_actual_results, basis=default_basis)}"
                "</td></tr>"
            )
    rows_html = "\n".join(ending_table_rows)
    has_source_game_counts = any(
        "originalGameCount" in bucket or "matchedGames" in bucket
        for bucket in snapshot["sourceBuckets"]
    )
    source_rows = "\n".join(
        f'<tr class="source-bucket-row" data-source-pgn="{html.escape(bucket["sourcePgn"])}" '
        f'data-source-group="{html.escape(str(bucket.get("sourceGroup", "")))}">'
        f'<td data-label="Bucket" data-sort="{bucket["sortIndex"]}">{html.escape(bucket["displayLabel"])}</td>'
        f'<td data-label="PGN" data-sort="{html.escape(bucket["sourcePgn"])}">{html.escape(bucket["sourcePgn"])}</td>'
        + (
            f'<td class="num" data-label="Original games" data-sort="{int(bucket.get("originalGameCount", 0))}">{int(bucket.get("originalGameCount", 0)):,}</td>'
            f'<td class="num source-matched-games-cell" data-label="Matched games" data-sort="{int(bucket.get("matchedGames", 0))}">{int(bucket.get("matchedGames", 0)):,}</td>'
            if has_source_game_counts
            else ""
        )
        + f'<td class="num source-incidence-cell" data-label="Incidences" data-sort="{bucket["matchTotal"]}">{bucket["matchTotal"]:,}</td>'
        f'<td class="num" data-label="Size bytes" data-sort="{bucket["file"]["sizeBytes"]}">{bucket["file"]["sizeBytes"]:,}</td>'
        "</tr>"
        for bucket in snapshot["sourceBuckets"]
    )
    active_total_games = (
        int(active_dataset_view.get("totalGames", 0))
        if active_dataset_view
        else int(snapshot["corpus"]["totalGames"])
    )
    active_matched_games = (
        int(active_dataset_view.get("matchedGames", 0)) if active_dataset_view else None
    )
    active_source_buckets = (
        int(active_dataset_view.get("sourceBuckets", 0))
        if active_dataset_view
        else int(snapshot["totals"]["sourceBuckets"])
    )
    active_matched_rows = (
        int(active_dataset_view.get("matchedRows", 0))
        if active_dataset_view
        else int(snapshot["totals"]["matchedRows"])
    )
    metric_items = [
        render_metric("Original games", f"{active_total_games:,}", metric_id="total-games-metric"),
        render_metric("FCE rows", f"{snapshot['totals']['endingRows']:,}"),
        render_metric("Source buckets", f"{active_source_buckets:,}", metric_id="source-bucket-metric"),
        render_metric("Matched games", f"{active_matched_games:,}", metric_id="matched-games-metric")
        if active_matched_games is not None
        else "",
        render_metric("Overlapping incidences", f"{active_matched_rows:,}", metric_id="matched-rows-metric"),
    ]
    if has_tablebase_wdl and active_tablebase_section:
        tb = active_tablebase_section
        metric_items.extend(
            [
                render_metric(
                    "Tablebase positions",
                    f"{int(tb['totals']['evaluated_positions']):,}",
                    metric_id="tablebase-position-metric",
                ),
                render_metric(
                    "Tablebase endings",
                    f"{int(tb['endingCount']):,}/{snapshot['totals']['endingRows']:,}",
                ),
            ]
        )
    metrics_html = "\n".join(metric_items)
    methodology_html = render_methodology(
        snapshot,
        show_actual_results=show_actual_results,
    )
    explainer_html = render_column_explainer(
        has_tablebase_wdl=has_tablebase_wdl,
        show_actual_results=show_actual_results,
    )
    dataset_controls_html = render_dataset_view_controls(snapshot)
    run_length_controls_html = render_run_length_controls(snapshot)
    counting_controls_html = render_counting_basis_controls(snapshot)
    original_reference_rows = render_original_reference_rows(snapshot)
    meta_items = [
        f"Snapshot <code>{html.escape(snapshot['snapshotId'])}</code>",
        f"Generated {html.escape(snapshot['generatedAt'])}",
        "Exact incidence counts",
    ]
    if has_tablebase_wdl:
        meta_items.append("Exact tablebase WDL for <=5-man marker positions")
    if show_actual_results:
        meta_items.append("Actual results are PGN result tags viewed from the named-material perspective")
    meta_html = "\n".join(f"<span>{item}</span>" for item in meta_items)
    note_html = ""
    if has_tablebase_wdl:
        if snapshot.get("tablebaseMode") == "combined-filtered":
            note_html = (
                '<p class="note">'
                "Tablebase positions are all marked half-move positions with five "
                "pieces or fewer whose same-ending run meets the active persistence "
                "threshold."
                "</p>"
            )
        else:
            note_html = (
                '<p class="note">'
                "Tablebase positions are first CQL marker occurrences with five pieces "
                "or fewer. First markers with more than five pieces are skipped for "
                "tablebase WDL."
                "</p>"
            )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <script>
    (() => {{
      try {{
        const theme = localStorage.getItem("fce-theme");
        if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
      }} catch (error) {{}}
    }})();
  </script>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f8;
      --surface: #ffffff;
      --text: #1f2933;
      --muted: #627180;
      --border: #d8e0e7;
      --accent: #256f8f;
      --table-head: #eef3f7;
      --hover: #f8fafb;
      --detail-bg: #fbfcfd;
      --button-bg: #ffffff;
      --example-bg: #ffffff;
      --board-light: #f0d9b5;
      --board-dark: #b58863;
      --board-border: #9b836e;
    }}
    :root[data-theme="dark"] {{
      color-scheme: dark;
      --bg: #11161a;
      --surface: #182027;
      --text: #e7edf2;
      --muted: #9aa8b3;
      --border: #34424d;
      --accent: #82c7e6;
      --table-head: #222e36;
      --hover: #1f2a32;
      --detail-bg: #131b21;
      --button-bg: #24313a;
      --example-bg: #151d23;
      --board-light: #d8c09a;
      --board-dark: #7f8f59;
      --board-border: #4b5a42;
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]) {{
        color-scheme: dark;
        --bg: #11161a;
        --surface: #182027;
        --text: #e7edf2;
        --muted: #9aa8b3;
        --border: #34424d;
        --accent: #82c7e6;
        --table-head: #222e36;
        --hover: #1f2a32;
        --detail-bg: #131b21;
        --button-bg: #24313a;
        --example-bg: #151d23;
        --board-light: #d8c09a;
        --board-dark: #7f8f59;
        --board-border: #4b5a42;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    header {{
      padding: 20px 24px 14px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
    }}
    .header-main {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 16px;
    }}
    .theme-toggle {{
      display: grid;
      width: 36px;
      height: 36px;
      place-items: center;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--button-bg);
      color: var(--text);
      padding: 0;
      cursor: pointer;
    }}
    .theme-toggle:hover {{ border-color: var(--accent); }}
    .theme-toggle:focus-visible {{
      outline: 3px solid var(--accent);
      outline-offset: 2px;
    }}
    .theme-icon {{
      display: block;
      width: 19px;
      height: 19px;
      fill: none;
      stroke: currentColor;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-width: 2;
    }}
    .theme-icon-sun {{ display: none; }}
    .theme-toggle[data-active-theme="dark"] .theme-icon-moon {{ display: none; }}
    .theme-toggle[data-active-theme="dark"] .theme-icon-sun {{ display: block; }}
    main {{ padding: 18px 24px 36px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.45rem; line-height: 1.2; }}
    h2 {{ margin: 24px 0 10px; font-size: 1rem; }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 18px;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin: 0 0 16px;
    }}
    .metric {{
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      padding: 10px 12px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 0.76rem; margin-bottom: 4px; }}
    .metric strong {{ font-size: 1.08rem; }}
    .methodology {{
      max-width: 980px;
      margin: 0 0 18px;
      color: var(--text);
      font-size: 0.9rem;
      line-height: 1.45;
    }}
    .methodology p {{ margin: 0 0 8px; }}
    .methodology a {{ color: var(--accent); }}
    .column-guide {{
      max-width: 1120px;
      margin: 0 0 18px;
      font-size: 0.86rem;
      line-height: 1.4;
    }}
    .column-guide dl {{
      display: grid;
      grid-template-columns: minmax(110px, 160px) minmax(0, 1fr);
      gap: 6px 14px;
      margin: 0;
    }}
    .column-guide dt {{ font-weight: 650; }}
    .column-guide dd {{ margin: 0; color: var(--muted); }}
    .table-controls {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px 12px;
      margin: 0 0 12px;
      font-size: 0.84rem;
    }}
    .control-label {{
      color: var(--muted);
      font-weight: 650;
    }}
    .segmented {{
      display: inline-flex;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: var(--button-bg);
    }}
    .segmented-button {{
      border: 0;
      border-right: 1px solid var(--border);
      background: transparent;
      color: var(--text);
      padding: 6px 10px;
      font: inherit;
      font-size: 0.8rem;
      cursor: pointer;
    }}
    .segmented-button:last-child {{ border-right: 0; }}
    .segmented-button.is-active {{
      background: var(--accent);
      color: #ffffff;
    }}
    .control-note {{
      color: var(--muted);
      line-height: 1.35;
    }}
    .number-input {{
      width: 74px;
      min-height: 31px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--button-bg);
      color: var(--text);
      padding: 5px 8px;
      font: inherit;
      font-size: 0.82rem;
      font-variant-numeric: tabular-nums;
    }}
    .number-input:focus {{
      outline: 3px solid var(--accent);
      outline-offset: 1px;
    }}
    .table-wrap {{
      max-width: 100%;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      -webkit-overflow-scrolling: touch;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    th, td {{ padding: 8px 9px; border-bottom: 1px solid var(--border); white-space: nowrap; vertical-align: top; }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      text-align: left;
      color: var(--muted);
      background: var(--table-head);
      font-weight: 600;
      font-size: 0.76rem;
    }}
    .sortable-table th {{ cursor: pointer; user-select: none; }}
    .sortable-table th[aria-sort="ascending"]::after {{ content: " ^"; }}
    .sortable-table th[aria-sort="descending"]::after {{ content: " v"; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .ending-row.expandable {{ cursor: pointer; }}
    .ending-row.expandable:hover {{ background: var(--hover); }}
    .auxiliary-row td {{ background: var(--detail-bg); color: var(--muted); }}
    .auxiliary-row td[data-label="Ending"] {{ padding-left: 28px; }}
    .subrow-marker {{ display: inline-block; width: 18px; color: var(--accent); }}
    .row-toggle {{
      width: 18px;
      height: 18px;
      margin: -2px 7px -2px 0;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: var(--button-bg);
      color: var(--accent);
      font-size: 0.78rem;
      line-height: 1;
      cursor: pointer;
    }}
    .detail-row > td {{
      padding: 0;
      background: var(--detail-bg);
      white-space: normal;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: minmax(320px, 0.8fr) minmax(520px, 1.2fr);
      gap: 16px;
      padding: 14px;
      border-bottom: 1px solid var(--border);
    }}
    .detail-panel h3 {{ margin: 0 0 8px; font-size: 0.86rem; }}
    .detail-note {{ margin: 0 0 8px; color: var(--muted); font-size: 0.82rem; line-height: 1.4; }}
    .example-split {{ display: flex; flex-wrap: wrap; gap: 4px 8px; margin: 0 0 8px; }}
    .example-split span {{ color: var(--muted); font-size: 0.74rem; white-space: nowrap; }}
    .examples-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
      gap: 12px;
      max-height: 620px;
      overflow: auto;
      padding: 2px;
    }}
    .example-card {{
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--example-bg);
    }}
    .board-link {{
      position: relative;
      display: block;
      width: 100%;
      aspect-ratio: 1;
      overflow: hidden;
      border-bottom: 1px solid var(--border);
      background-color: var(--board-light);
      background-image: conic-gradient(
        var(--board-dark) 25%,
        var(--board-light) 0 50%,
        var(--board-dark) 0 75%,
        var(--board-light) 0
      );
      background-size: 25% 25%;
    }}
    .board-link:focus-visible {{
      outline: 3px solid var(--accent);
      outline-offset: -3px;
    }}
    .board-piece {{
      position: absolute;
      left: calc(var(--file) * 12.5%);
      top: calc(var(--rank) * 12.5%);
      width: 12.5%;
      height: 12.5%;
      padding: 1.2%;
      object-fit: contain;
      pointer-events: none;
      filter: drop-shadow(0 1px 1px rgba(0,0,0,0.35));
    }}
    .example-meta {{ padding: 9px 10px 10px; }}
    .example-title {{
      display: block;
      color: var(--text);
      font-size: 0.82rem;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .example-subtitle {{
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 0.72rem;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .example-meta dl {{
      display: grid;
      grid-template-columns: minmax(70px, auto) minmax(0, 1fr);
      gap: 3px 8px;
      margin: 8px 0 0;
      font-size: 0.72rem;
      line-height: 1.25;
    }}
    .example-meta dt {{ color: var(--muted); }}
    .example-meta dd {{ margin: 0; overflow-wrap: anywhere; }}
    .swatch {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; }}
    .muted {{ color: var(--muted); }}
    .wdl-cell {{ min-width: 310px; white-space: normal; }}
    .wdl-widget {{ width: 300px; max-width: 100%; }}
    .wdl-bar {{
      display: flex;
      width: 100%;
      height: 20px;
      overflow: hidden;
      border: 1px solid #c8d0d6;
      border-radius: 7px;
      background: #d7dce0;
      box-shadow: inset 0 1px 1px rgba(255,255,255,0.8), inset 0 -1px 1px rgba(0,0,0,0.12);
    }}
    .wdl-segment {{
      display: flex;
      min-width: 0;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      color: #ffffff;
      font-size: 0.74rem;
      font-variant-numeric: tabular-nums;
      line-height: 1;
      white-space: nowrap;
      text-shadow: 0 1px 1px rgba(0,0,0,0.25);
    }}
    .wdl-segment.is-tiny {{ color: transparent; text-shadow: none; }}
    .wdl-win {{ background: linear-gradient(#f2f5f7, #c9d3da); color: #1f2933; text-shadow: none; }}
    .wdl-draw {{ background: linear-gradient(#aab2b8, #7d858b); }}
    .wdl-loss {{ background: linear-gradient(#606970, #30383d); }}
    .wdl-decisive {{ background: linear-gradient(#879199, #59636a); }}
    .wdl-unknown {{
      background: repeating-linear-gradient(
        135deg,
        #e6eaed 0,
        #e6eaed 6px,
        #c8d0d6 6px,
        #c8d0d6 12px
      );
      color: #1f2933;
      text-shadow: none;
    }}
    .wdl-counts {{
      display: flex;
      flex-wrap: wrap;
      gap: 2px 9px;
      margin-top: 4px;
      color: var(--muted);
      font-size: 0.74rem;
      font-variant-numeric: tabular-nums;
      line-height: 1.2;
    }}
    .outcome-row {{ display: flex; flex-wrap: wrap; gap: 4px 12px; }}
    .outcome-row span {{ white-space: nowrap; }}
    .matrix-cell {{ min-width: 360px; white-space: normal; }}
    .matrix-row {{ display: grid; grid-template-columns: 78px minmax(0, 1fr); gap: 8px; margin-bottom: 3px; }}
    .matrix-row > span {{ color: var(--muted); }}
    .matrix-row > div {{ display: flex; flex-wrap: wrap; gap: 4px 10px; }}
    .matrix-row > div span {{ white-space: nowrap; }}
    .matrix-summary {{ border-top: 1px solid var(--border); padding-top: 3px; margin-top: 4px; }}
    .note {{ color: var(--muted); margin: 8px 0 0; max-width: 780px; font-size: 0.84rem; }}
    code {{ color: var(--accent); }}
    @media (max-width: 900px) {{
      header {{ padding: 16px 14px 12px; }}
      main {{ padding: 14px 12px 28px; }}
      h1 {{ font-size: 1.18rem; }}
      h2 {{ margin-top: 20px; }}
      .meta {{ gap: 6px 12px; font-size: 0.78rem; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
      .metric {{ padding: 9px 10px; }}
      .metric strong {{ font-size: 0.98rem; }}
      .methodology, .column-guide {{ font-size: 0.84rem; }}
      .column-guide dl {{ grid-template-columns: 1fr; gap: 3px; }}
      .column-guide dd {{ margin: 0 0 8px; }}
      .table-controls {{ align-items: stretch; }}
      .control-note {{ flex-basis: 100%; }}
      .detail-grid {{ grid-template-columns: 1fr; }}
      .table-wrap {{
        overflow: visible;
        border: 0;
        border-radius: 0;
        background: transparent;
      }}
      .sortable-table th {{
        position: static;
      }}
      .sortable-table thead {{
        display: none;
      }}
      .sortable-table,
      .sortable-table tbody,
      .sortable-table tr,
      .sortable-table td {{
        display: block;
        width: 100%;
      }}
      .sortable-table tr {{
        margin: 0 0 10px;
        border: 1px solid var(--border);
        border-radius: 8px;
        background: var(--surface);
        overflow: hidden;
      }}
      .sortable-table td {{
        display: grid;
        grid-template-columns: minmax(96px, 42%) minmax(0, 1fr);
        gap: 10px;
        align-items: start;
        padding: 8px 10px;
        border-bottom: 1px solid var(--border);
        white-space: normal;
        text-align: left;
      }}
      .sortable-table td:last-child {{ border-bottom: 0; }}
      .sortable-table td::before {{
        content: attr(data-label);
        color: var(--muted);
        font-size: 0.72rem;
        font-weight: 650;
        line-height: 1.25;
      }}
      .ending-row.expandable:hover {{ background: var(--surface); }}
      .ending-row td[data-label="ID"] {{
        display: flex;
        gap: 8px;
        align-items: center;
      }}
      .ending-row td[data-label="ID"]::before {{ content: none; }}
      .ending-row td[data-label="Ending"],
      .ending-row td[data-label="Tablebase WDL"],
      .ending-row td[data-label="Actual result"] {{
        grid-template-columns: 1fr;
        gap: 5px;
      }}
      .ending-row td[data-label="Ending"] {{
        font-size: 0.98rem;
        font-weight: 650;
      }}
      .ending-row td[data-label="Ending"]::before {{
        font-size: 0.7rem;
        font-weight: 650;
      }}
      .num {{ text-align: left; }}
      .wdl-cell {{ min-width: 0; }}
      .wdl-widget {{ width: 100%; }}
      .wdl-bar {{ height: 22px; }}
      .wdl-counts {{ font-size: 0.72rem; }}
      .detail-row {{
        margin-top: -10px;
        border-top: 0;
      }}
      .detail-row > td {{
        display: block;
        padding: 0;
        border-bottom: 0;
      }}
      .detail-row > td::before {{ content: none; }}
      .detail-grid {{
        padding: 12px;
        border-bottom: 0;
      }}
      .matrix-cell {{ min-width: 0; }}
      .matrix-row {{
        grid-template-columns: 1fr;
        gap: 3px;
        padding: 5px 0;
      }}
      .matrix-row > div {{
        gap: 4px 8px;
      }}
      .matrix-row > div span {{
        white-space: normal;
      }}
      .examples-grid {{
        grid-template-columns: repeat(auto-fill, minmax(142px, 1fr));
        max-height: 560px;
      }}
      .example-meta {{ padding: 8px; }}
      .example-meta dl {{ grid-template-columns: 1fr; gap: 2px; }}
      .example-meta dd {{ margin: 0 0 4px; }}
      .source-table td[data-label="PGN"],
      .reference-table td[data-label="Ending"] {{
        overflow-wrap: anywhere;
      }}
    }}
    @media (max-width: 520px) {{
      .metrics {{ grid-template-columns: 1fr; }}
      .sortable-table td {{
        grid-template-columns: 1fr;
        gap: 3px;
      }}
      .wdl-segment {{ font-size: 0.68rem; }}
      .examples-grid {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
      .example-title {{ font-size: 0.76rem; }}
    }}
  </style>
</head>
<body>
<header>
  <div class="header-main">
    <h1>{html.escape(page_title)}</h1>
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle light and dark mode">
      <svg class="theme-icon theme-icon-moon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8z"></path>
      </svg>
      <svg class="theme-icon theme-icon-sun" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="4"></circle>
        <path d="M12 2v2"></path><path d="M12 20v2"></path>
        <path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path>
        <path d="M2 12h2"></path><path d="M20 12h2"></path>
        <path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path>
      </svg>
    </button>
  </div>
  <div class="meta">{meta_html}</div>
</header>
<main>
  <section class="metrics">{metrics_html}</section>
  {methodology_html}
  {explainer_html}
  <h2>Ending Incidence</h2>
  {dataset_controls_html}
  {run_length_controls_html}
  {counting_controls_html}
  <div class="table-wrap">
    <table class="sortable-table ending-table">
      <thead><tr><th>ID</th><th>Ending</th><th class="num quantity-header">Quantity</th><th class="num rate-header">Corpus %</th><th class="num share-header">Matched Share</th>{tablebase_headers}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  {note_html}
  <h2>Original Fundamental Chess Endings Table</h2>
  <p class="note">Reference quantities and percentages are the published FCE baseline; the Gigabase columns are this snapshot's exact matching rows for comparison.</p>
  <div class="table-wrap">
    <table class="sortable-table reference-table">
      <thead><tr><th>ID</th><th>Ending</th><th>FCE quantity</th><th class="num">FCE %</th><th class="num">Gigabase quantity</th><th class="num">Gigabase %</th></tr></thead>
      <tbody>{original_reference_rows}</tbody>
    </table>
  </div>
  <h2>Source Buckets</h2>
  <div class="table-wrap">
    <table class="sortable-table source-table">
      <thead><tr><th>Bucket</th><th>PGN</th>{'<th class="num">Original games</th><th class="num">Matched games</th>' if has_source_game_counts else ''}<th class="num">Incidences</th><th class="num">Size Bytes</th></tr></thead>
      <tbody>{source_rows}</tbody>
    </table>
  </div>
</main>
<script id="dataset-view-data" type="application/json">{dataset_view_json}</script>
<script id="counting-view-data" type="application/json">{counting_view_json}</script>
<script>
(() => {{
  const themeToggle = document.getElementById("theme-toggle");
  const systemPrefersDark = () =>
    window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const activeTheme = () => document.documentElement.dataset.theme || (systemPrefersDark() ? "dark" : "light");
  const updateThemeToggle = () => {{
    if (!themeToggle) return;
    const theme = activeTheme();
    themeToggle.dataset.activeTheme = theme;
    themeToggle.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
  }};
  if (themeToggle) {{
    themeToggle.addEventListener("click", () => {{
      const nextTheme = activeTheme() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = nextTheme;
      try {{ localStorage.setItem("fce-theme", nextTheme); }} catch (error) {{}}
      updateThemeToggle();
    }});
    updateThemeToggle();
  }}
  const countingViewElement = document.getElementById("counting-view-data");
  const countingViewData = (() => {{
    if (!countingViewElement) return {{}};
    try {{ return JSON.parse(countingViewElement.textContent || "{{}}"); }}
    catch (error) {{ return {{}}; }}
  }})();
  const datasetViewElement = document.getElementById("dataset-view-data");
  const datasetViewData = (() => {{
    if (!datasetViewElement) return {{}};
    try {{ return JSON.parse(datasetViewElement.textContent || "{{}}"); }}
    catch (error) {{ return {{}}; }}
  }})();
  const setTextCell = (cell, payload, label) => {{
    if (!cell || !payload) return;
    cell.textContent = payload.text ?? "";
    cell.dataset.sort = String(payload.sort ?? "");
    if (label) cell.dataset.label = label;
  }};
  const setHtmlCell = (cell, payload, label) => {{
    if (!cell || !payload) return;
    cell.innerHTML = payload.html ?? "";
    cell.dataset.sort = String(payload.sort ?? "");
    if (label) cell.dataset.label = label;
  }};
  const setMetric = (id, value) => {{
    const node = document.getElementById(id);
    if (!node || !Number.isFinite(Number(value))) return;
    node.textContent = Number(value).toLocaleString();
  }};
  let activeDatasetViewKey = datasetViewData.default || "all";
  let activeRunLengthThreshold = 1;
  const setActiveRunLengthThreshold = (threshold) => {{
    activeRunLengthThreshold = threshold;
    document.querySelectorAll("[data-run-length-threshold]").forEach((button) => {{
      const active = Number(button.dataset.runLengthThreshold) === activeRunLengthThreshold;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }});
  }};
  const hasHistogram = (histogram) => histogram && Object.keys(histogram).length > 0;
  const histogramCount = (histogram, threshold) => {{
    if (!hasHistogram(histogram)) return null;
    return Object.entries(histogram).reduce((total, [length, count]) => {{
      return Number(length) >= threshold ? total + Number(count || 0) : total;
    }}, 0);
  }};
  const formatPctJs = (value) => {{
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "";
    const numeric = Number(value);
    if (numeric === 0) return "0%";
    if (Math.abs(numeric) < 0.01) return `${{numeric.toFixed(4)}}%`;
    if (Math.abs(numeric) < 1) return `${{numeric.toFixed(2)}}%`;
    return `${{numeric.toFixed(1)}}%`;
  }};
  const thresholdPayload = (quantity, totalGames, matchedRows) => {{
    const rate = totalGames > 0 ? quantity / totalGames * 100 : null;
    const share = matchedRows > 0 ? quantity / matchedRows * 100 : null;
    return {{
      quantity: {{ text: Number(quantity).toLocaleString(), sort: quantity }},
      rate: {{ text: formatPctJs(rate), sort: rate ?? 0 }},
      share: {{ text: formatPctJs(share), sort: share ?? 0 }},
    }};
  }};
  const rowPayloadForThreshold = (rowData, totalGames, matchedRows) => {{
    const count = histogramCount(rowData?.runLengthHistogram, activeRunLengthThreshold);
    return count === null ? rowData : thresholdPayload(count, totalGames, matchedRows);
  }};
  const emptyTablebasePayload = () => {{
    const payload = {{
      positions: {{ text: "0", sort: 0 }},
      wdl: {{ html: "No &lt;=5-man marker positions", sort: -1 }},
      detailHtml: "<p class=\\"detail-note\\">No &lt;=5-man tablebase/result matrix is available for this ending.</p>",
    }};
    if (document.querySelector(".actual-result-cell")) {{
      payload.actual = {{ html: "No result stats", sort: -1 }};
    }}
    return payload;
  }};
  const updateTablebaseCells = (row, tablebase) => {{
    if (!row.querySelector(".tb-positions-cell")) return;
    const payload = tablebase || emptyTablebasePayload();
    setTextCell(row.querySelector(".tb-positions-cell"), payload.positions, "TB positions");
    setHtmlCell(row.querySelector(".tb-wdl-cell"), payload.wdl, "Tablebase WDL");
    setHtmlCell(row.querySelector(".actual-result-cell"), payload.actual, "Actual result");
    const detail = row.dataset.detailId ? document.getElementById(row.dataset.detailId) : null;
    const panel = detail?.querySelector(".tb-result-panel");
    if (panel && payload.detailHtml) panel.innerHTML = payload.detailHtml;
  }};
  const renderActiveDatasetView = () => {{
    const view = datasetViewData.views?.[activeDatasetViewKey];
    if (!view) return;
    const thresholdView = view.thresholds?.[String(activeRunLengthThreshold)] || null;
    const metrics = thresholdView?.metrics || view.metrics || {{}};
    const thresholdedMatchedRows = histogramCount(
      metrics.incidenceRunLengthHistogram,
      activeRunLengthThreshold
    );
    const thresholdedMatchedGames = histogramCount(
      metrics.matchedGameRunLengthHistogram,
      activeRunLengthThreshold
    );
    const totalGames = Number(metrics.totalGames || 0);
    const matchedRows = thresholdedMatchedRows ?? Number(metrics.matchedRows || 0);
    const matchedGames = thresholdedMatchedGames ?? Number(metrics.matchedGames || 0);
    setMetric("total-games-metric", totalGames);
    setMetric("matched-games-metric", matchedGames);
    setMetric("source-bucket-metric", metrics.sourceBuckets);
    setMetric("matched-rows-metric", matchedRows);
    if (Number.isFinite(Number(metrics.tablebasePositions))) {{
      setMetric("tablebase-position-metric", Number(metrics.tablebasePositions));
    }}
    const runNote = document.getElementById("run-length-note");
    if (runNote) {{
      runNote.textContent = activeRunLengthThreshold <= 1
        ? "1 keeps every matched game-ending incidence."
        : `${{activeRunLengthThreshold}} requires the ending on consecutive half-move positions.`;
    }}
    const visibleSources = new Set(view.sourcePgns || []);
    document.querySelectorAll(".source-bucket-row[data-source-pgn]").forEach((row) => {{
      row.hidden = visibleSources.size > 0 && !visibleSources.has(row.dataset.sourcePgn);
      if (row.hidden) return;
      const source = row.dataset.sourcePgn;
      const sourceThreshold = thresholdView?.sourceBuckets?.[source];
      const sourceIncidences = sourceThreshold
        ? Number(sourceThreshold.incidences || 0)
        : histogramCount(
            view.sourceIncidenceRunLengthHistograms?.[source],
            activeRunLengthThreshold
          );
      if (sourceIncidences !== null) {{
        setTextCell(
          row.querySelector(".source-incidence-cell"),
          {{ text: Number(sourceIncidences).toLocaleString(), sort: sourceIncidences }},
          "Incidences"
        );
      }}
      const sourceMatchedGames = sourceThreshold
        ? Number(sourceThreshold.matchedGames || 0)
        : histogramCount(
            view.sourceMatchedGameRunLengthHistograms?.[source],
            activeRunLengthThreshold
          );
      if (sourceMatchedGames !== null) {{
        setTextCell(
          row.querySelector(".source-matched-games-cell"),
          {{ text: Number(sourceMatchedGames).toLocaleString(), sort: sourceMatchedGames }},
          "Matched games"
        );
      }}
    }});
    document.querySelectorAll(".ending-row[data-stem], .auxiliary-row[data-stem]").forEach((row) => {{
      const rowData = thresholdView?.rows?.[row.dataset.stem] || view.rows?.[row.dataset.stem];
      if (!rowData) return;
      const payload = thresholdView
        ? rowData
        : rowPayloadForThreshold(rowData, totalGames, matchedRows);
      setTextCell(row.querySelector(".quantity-cell"), payload.quantity, "Quantity");
      setTextCell(row.querySelector(".rate-cell"), payload.rate, "Corpus %");
      setTextCell(row.querySelector(".share-cell"), payload.share, "Matched share");
      updateTablebaseCells(row, payload.tablebase);
    }});
    document.querySelectorAll(".reference-row[data-stem]").forEach((row) => {{
      const rowData = view.rows?.[row.dataset.stem];
      if (!rowData) return;
      const payload = rowPayloadForThreshold(rowData, totalGames, matchedRows);
      setTextCell(row.querySelector(".gigabase-quantity-cell"), payload.quantity, "Gigabase quantity");
      setTextCell(row.querySelector(".gigabase-rate-cell"), payload.rate, "Gigabase %");
    }});
    document.querySelectorAll(".ending-table th, .reference-table th, .source-table th").forEach((header) => header.removeAttribute("aria-sort"));
  }};
  const applyDatasetView = (key) => {{
    const view = datasetViewData.views?.[key];
    if (!view) return;
    activeDatasetViewKey = key;
    document.querySelectorAll("[data-dataset-view]").forEach((button) => {{
      const active = button.dataset.datasetView === key;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }});
    const note = document.getElementById("dataset-view-note");
    if (note) note.textContent = view.description || "";
    renderActiveDatasetView();
  }};
  const applyCountingBasis = (basis) => {{
    const view = countingViewData.views?.[basis];
    if (!view) return;
    const meta = view.meta || {{}};
    document.querySelectorAll("[data-counting-basis]").forEach((button) => {{
      const active = button.dataset.countingBasis === basis;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }});
    const quantityHeader = document.querySelector(".ending-table .quantity-header");
    const rateHeader = document.querySelector(".ending-table .rate-header");
    const shareHeader = document.querySelector(".ending-table .share-header");
    if (quantityHeader) quantityHeader.textContent = meta.quantityHeader || "Quantity";
    if (rateHeader) rateHeader.textContent = meta.rateHeader || "Corpus %";
    if (shareHeader) shareHeader.textContent = meta.shareHeader || "Matched Share";
    const note = document.getElementById("counting-basis-note");
    if (note) note.textContent = meta.description || "";
    const tbMetric = document.getElementById("tablebase-position-metric");
    if (tbMetric && Number.isFinite(Number(meta.tablebasePositions))) {{
      tbMetric.textContent = Number(meta.tablebasePositions).toLocaleString();
    }}
    document.querySelectorAll(".ending-table th").forEach((header) => header.removeAttribute("aria-sort"));
    document.querySelectorAll("tr.ending-row[data-stem]").forEach((row) => {{
      const rowData = view.rows?.[row.dataset.stem];
      if (!rowData) return;
      setTextCell(row.querySelector(".quantity-cell"), rowData.quantity, meta.quantityHeader || "Quantity");
      setTextCell(row.querySelector(".rate-cell"), rowData.rate, meta.rateHeader || "Corpus %");
      setTextCell(row.querySelector(".share-cell"), rowData.share, meta.shareHeader || "Matched Share");
      const tablebase = rowData.tablebase;
      if (tablebase) {{
        setTextCell(row.querySelector(".tb-positions-cell"), tablebase.positions, "TB positions");
        setHtmlCell(row.querySelector(".tb-wdl-cell"), tablebase.wdl, "Tablebase WDL");
        setHtmlCell(row.querySelector(".actual-result-cell"), tablebase.actual, "Actual result");
        const detail = row.dataset.detailId ? document.getElementById(row.dataset.detailId) : null;
        const panel = detail?.querySelector(".tb-result-panel");
        if (panel && tablebase.detailHtml) panel.innerHTML = tablebase.detailHtml;
      }}
    }});
  }};
  document.querySelectorAll("[data-counting-basis]").forEach((button) => {{
    button.addEventListener("click", () => applyCountingBasis(button.dataset.countingBasis));
  }});
  document.querySelectorAll("[data-dataset-view]").forEach((button) => {{
    button.addEventListener("click", () => applyDatasetView(button.dataset.datasetView));
  }});
  document.querySelectorAll("[data-run-length-threshold]").forEach((button) => {{
    button.addEventListener("click", () => {{
      const parsed = Math.floor(Number(button.dataset.runLengthThreshold || 1));
      setActiveRunLengthThreshold(Number.isFinite(parsed) && parsed > 0 ? parsed : 1);
      renderActiveDatasetView();
    }});
  }});
  setActiveRunLengthThreshold(activeRunLengthThreshold);
  if (countingViewData.default) applyCountingBasis(countingViewData.default);
  if (datasetViewData.default) applyDatasetView(datasetViewData.default);
  const parseValue = (cell) => {{
    const raw = cell?.dataset?.sort ?? cell?.textContent ?? "";
    const numeric = Number(raw);
    return Number.isFinite(numeric) && raw.trim() !== "" ? numeric : raw.toLowerCase();
  }};
  const setExpanded = (row, expanded) => {{
    const detailId = row.dataset.detailId;
    const detail = detailId ? document.getElementById(detailId) : null;
    if (!detail) return;
    row.setAttribute("aria-expanded", expanded ? "true" : "false");
    detail.hidden = !expanded;
    const toggle = row.querySelector(".row-toggle");
    if (toggle) {{
      toggle.textContent = expanded ? "-" : "+";
      toggle.setAttribute("aria-label", expanded ? "Hide row details" : "Show row details");
    }}
  }};
  document.querySelectorAll("tr.ending-row.expandable").forEach((row) => {{
    row.addEventListener("click", (event) => {{
      if (event.target.closest("a")) return;
      setExpanded(row, row.getAttribute("aria-expanded") !== "true");
    }});
    row.addEventListener("keydown", (event) => {{
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      setExpanded(row, row.getAttribute("aria-expanded") !== "true");
    }});
  }});
  document.querySelectorAll(".sortable-table").forEach((table) => {{
    const headers = Array.from(table.querySelectorAll("thead th"));
    headers.forEach((header, index) => {{
      header.addEventListener("click", () => {{
        const tbody = table.tBodies[0];
        const isEndingTable = table.classList.contains("ending-table");
        const previous = header.getAttribute("aria-sort");
        const direction = previous === "ascending" ? "descending" : "ascending";
        headers.forEach((item) => item.removeAttribute("aria-sort"));
        header.setAttribute("aria-sort", direction);
        const multiplier = direction === "ascending" ? 1 : -1;
        Array.from(tbody.rows)
          .filter((row) => isEndingTable ? row.dataset.rowKind === "data" : row.dataset.rowKind !== "detail" && row.dataset.rowKind !== "auxiliary")
          .map((row, originalIndex) => ({{ row, originalIndex, value: parseValue(row.cells[index]) }}))
          .sort((a, b) => {{
            if (a.value < b.value) return -1 * multiplier;
            if (a.value > b.value) return 1 * multiplier;
            return a.originalIndex - b.originalIndex;
          }})
          .forEach((item) => {{
            tbody.appendChild(item.row);
            if (isEndingTable) {{
              Array.from(tbody.querySelectorAll(".auxiliary-row[data-parent-stem]"))
                .filter((auxiliary) => auxiliary.dataset.parentStem === (item.row.dataset.stem || ""))
                .forEach((auxiliary) => tbody.appendChild(auxiliary));
            }}
            const detailId = item.row.dataset.detailId;
            const detail = detailId ? document.getElementById(detailId) : null;
            if (detail) tbody.appendChild(detail);
          }});
      }});
    }});
  }});
}})();
</script>
<script id="snapshot-data" type="application/json">{data_json}</script>
</body>
</html>
"""


def write_summary_by_ending_csv(snapshot: dict[str, Any], path: Path) -> None:
    source_columns = [
        f"count:{bucket['sourceStem']}" for bucket in snapshot.get("sourceBuckets", [])
    ]
    sources = [bucket["sourcePgn"] for bucket in snapshot.get("sourceBuckets", [])]
    fieldnames = [
        "sort_index",
        "stem",
        "row_id",
        "ending",
        "chapter",
        "quantity",
        "percentage",
        "matched_share",
        *source_columns,
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        def write_row(row: dict[str, Any]) -> None:
            csv_row: dict[str, Any] = {
                "sort_index": row["sortIndex"],
                "stem": row["stem"],
                "row_id": row["rowId"],
                "ending": row["label"],
                "chapter": row["chapter"],
                "quantity": row["quantity"],
                "percentage": f"{row['percentage']:.8f}"
                if row["percentage"] is not None
                else "",
                "matched_share": f"{row['matchedShare']:.8f}"
                if row["matchedShare"] is not None
                else "",
            }
            for source, column in zip(sources, source_columns):
                csv_row[column] = row["sourceCounts"][source]
            writer.writerow(csv_row)

        for row in snapshot["rows"]:
            write_row(row)
            for auxiliary in row.get("auxiliaryRows", []):
                write_row(auxiliary)


def write_snapshot_directory(
    *,
    target_dir: Path,
    manifest: dict[str, Any],
    snapshot: dict[str, Any],
    force: bool,
) -> SnapshotBuildResult:
    parent = target_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{target_dir.name}.tmp-", dir=str(parent))
    )
    try:
        assert temp_dir is not None
        write_json(temp_dir / "snapshot.json", snapshot)
        write_json(temp_dir / "manifest.json", manifest)
        write_summary_by_ending_csv(snapshot, temp_dir / "summary_by_ending.csv")
        (temp_dir / "index.html").write_text(
            render_snapshot_html(snapshot), encoding="utf-8"
        )

        backup_dir: Path | None = None
        try:
            if target_dir.exists():
                if not force:
                    raise SnapshotError(f"Output directory already exists: {target_dir}")
                backup_dir = parent / f".{target_dir.name}.backup-{uuid.uuid4().hex}"
                target_dir.rename(backup_dir)
            temp_dir.rename(target_dir)
            temp_dir = None
            if backup_dir is not None:
                shutil.rmtree(backup_dir)
        except Exception:
            if backup_dir is not None and backup_dir.exists() and not target_dir.exists():
                backup_dir.rename(target_dir)
            raise
    finally:
        if temp_dir is not None and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    return SnapshotBuildResult(
        output_dir=target_dir,
        snapshot_path=target_dir / "snapshot.json",
        manifest_path=target_dir / "manifest.json",
        summary_csv_path=target_dir / "summary_by_ending.csv",
        html_path=target_dir / "index.html",
        snapshot_id=snapshot["snapshotId"],
    )


def build_fce_gigabase_snapshot(
    *,
    summary_csv: str | Path,
    run_dir: str | Path,
    corpus_dir: str | Path,
    total_games: int,
    output_dir: str | Path,
    title: str,
    cql_table_dir: str | Path = DEFAULT_CQL_TABLE_DIR,
    examples_jsonl: str | Path | None = None,
    hash_source_pgns: bool = False,
    force: bool = False,
) -> SnapshotBuildResult:
    if total_games <= 0:
        raise SnapshotError("--total-games must be a positive integer")

    summary_path = Path(summary_csv).expanduser().resolve()
    run_path = Path(run_dir).expanduser().resolve()
    corpus_path = Path(corpus_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    cql_path = Path(cql_table_dir).expanduser().resolve()
    examples_path = (
        Path(examples_jsonl).expanduser().resolve() if examples_jsonl else None
    )

    manifest, summary_data = build_current_manifest(
        summary_csv=summary_path,
        run_dir=run_path,
        corpus_dir=corpus_path,
        total_games=total_games,
        title=title,
        cql_table_dir=cql_path,
        hash_source_pgns=hash_source_pgns,
        examples_jsonl=examples_path,
    )

    manifest_path = output_path / "manifest.json"
    if output_path.exists():
        if not output_path.is_dir():
            raise SnapshotError(f"Output path exists and is not a directory: {output_path}")
        if manifest_path.exists() and load_json(manifest_path) == manifest:
            snapshot_id = f"fce-gigabase-{manifest['fingerprint'][:12]}"
            return SnapshotBuildResult(
                output_dir=output_path,
                snapshot_path=output_path / "snapshot.json",
                manifest_path=manifest_path,
                summary_csv_path=output_path / "summary_by_ending.csv",
                html_path=output_path / "index.html",
                snapshot_id=snapshot_id,
                up_to_date=True,
            )
        if not force:
            raise SnapshotError(
                f"{output_path} already exists but its manifest does not match "
                "the current inputs. Use --force to rebuild or choose a new output directory."
            )

    snapshot = build_snapshot_payload(
        manifest=manifest,
        summary_data=summary_data,
        total_games=total_games,
        title=title,
        corpus_dir=corpus_path,
        examples_jsonl=examples_path,
    )
    return write_snapshot_directory(
        target_dir=output_path,
        manifest=manifest,
        snapshot=snapshot,
        force=force,
    )


def render_fce_snapshot_dashboard(
    *,
    snapshot_json: str | Path,
    output_html: str | Path,
    title: str | None = None,
    tablebase_wdl_csv: str | Path | None = None,
    tablebase_wdl_first_csv: str | Path | None = None,
    marker_count_views_csv: str | Path | None = None,
    examples_jsonl: str | Path | None = None,
) -> Path:
    snapshot_path = Path(snapshot_json).expanduser().resolve()
    output_path = Path(output_html).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = load_json(snapshot_path)
    if marker_count_views_csv is not None:
        snapshot = attach_counting_views(snapshot, marker_count_views_csv)
    if tablebase_wdl_first_csv is not None:
        snapshot = attach_tablebase_wdl_view(
            snapshot,
            tablebase_wdl_first_csv,
            view_key="first",
            label="First CQL marker",
            position_basis="first <=5-man FCE marker position per ending/game",
        )
    if tablebase_wdl_csv is not None:
        snapshot = attach_tablebase_wdl_view(
            snapshot,
            tablebase_wdl_csv,
            view_key="all",
            label="Every CQL marker",
            position_basis="all precomputed <=5-man FCE marker positions",
        )
    if examples_jsonl is not None:
        snapshot["sampledExamples"] = load_sampled_examples(
            Path(examples_jsonl).expanduser().resolve()
        )
    output_path.write_text(render_snapshot_html(snapshot, title=title), encoding="utf-8")
    return output_path


def parse_build_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a durable FCE Gigabase incidence snapshot."
    )
    parser.add_argument("--summary-csv", required=True, help="analyse_cql summary.csv")
    parser.add_argument("--run-dir", required=True, help="Annotated FCE run directory")
    parser.add_argument("--corpus-dir", required=True, help="Original OTB PGN directory")
    parser.add_argument("--total-games", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--cql-table-dir",
        default=str(DEFAULT_CQL_TABLE_DIR),
        help="Curated FCE CQL table directory.",
    )
    parser.add_argument(
        "--examples-jsonl",
        default=None,
        help="Optional sampled pgn-utils sample-fens JSONL to embed.",
    )
    parser.add_argument(
        "--hash-source-pgns",
        action="store_true",
        help="Hash full source PGNs for stronger provenance.",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def build_main(argv: list[str] | None = None) -> int:
    args = parse_build_args(argv)
    try:
        result = build_fce_gigabase_snapshot(
            summary_csv=args.summary_csv,
            run_dir=args.run_dir,
            corpus_dir=args.corpus_dir,
            total_games=args.total_games,
            output_dir=args.output_dir,
            title=args.title,
            cql_table_dir=args.cql_table_dir,
            examples_jsonl=args.examples_jsonl,
            hash_source_pgns=args.hash_source_pgns,
            force=args.force,
        )
    except SnapshotError as exc:
        print(f"Snapshot build failed: {exc}")
        return 1

    if result.up_to_date:
        print(f"Snapshot is up to date: {result.output_dir}")
    else:
        print(f"Wrote snapshot: {result.snapshot_path}")
        print(f"Wrote summary CSV: {result.summary_csv_path}")
        print(f"Wrote dashboard: {result.html_path}")
    print(f"Snapshot ID: {result.snapshot_id}")
    return 0


def parse_render_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render an FCE snapshot JSON file to static dashboard HTML."
    )
    parser.add_argument("--snapshot-json", required=True)
    parser.add_argument("--output-html", required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--tablebase-wdl-csv",
        default=None,
        help=(
            "Optional precomputed ending_tablebase_wdl.csv to include tablebase "
            "position WDL columns."
        ),
    )
    parser.add_argument(
        "--tablebase-wdl-first-csv",
        default=None,
        help="Optional first-marker tablebase aggregate CSV for the counting-basis toggle.",
    )
    parser.add_argument(
        "--marker-count-views-csv",
        default=None,
        help="Optional marker count view CSV with first_game_count and all_marker_count.",
    )
    parser.add_argument(
        "--examples-jsonl",
        default=None,
        help="Optional sampled examples JSONL to embed in expandable row details.",
    )
    return parser.parse_args(argv)


def render_main(argv: list[str] | None = None) -> int:
    args = parse_render_args(argv)
    try:
        output_path = render_fce_snapshot_dashboard(
            snapshot_json=args.snapshot_json,
            output_html=args.output_html,
            title=args.title,
            tablebase_wdl_csv=args.tablebase_wdl_csv,
            tablebase_wdl_first_csv=args.tablebase_wdl_first_csv,
            marker_count_views_csv=args.marker_count_views_csv,
            examples_jsonl=args.examples_jsonl,
        )
    except (OSError, json.JSONDecodeError, KeyError, SnapshotError) as exc:
        print(f"Snapshot render failed: {exc}")
        return 1
    print(f"Wrote dashboard: {output_path}")
    return 0
