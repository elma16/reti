from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reti.fce_metadata import FCE_CATALOG
from reti.fce_snapshot import (
    REPO_ROOT,
    SCHEMA_VERSION,
    SnapshotBuildResult,
    SnapshotError,
    catalog_payload,
    file_signature,
    manifest_fingerprint,
    original_fce_reference_payload,
    source_sort_key,
    write_snapshot_directory,
)


DEFAULT_COMBINED_CQL = (
    REPO_ROOT / "cql-files" / "FCE" / "combined" / "fce-table-markers.cql"
)
COMBINED_SCRIPT_NAME = "fce-table-markers.cql"
COMMENT_RE = re.compile(r"\{([^{}]*)\}")
MOVE_TEXT_SPLIT_RE = re.compile(r"\n\s*\n", re.MULTILINE)
AUXILIARY_PARENT_STEMS = {
    "6-2-2RPPrConnected": "6-2-2RPPr",
    "8-1RNrNoPawns": "8-1RNr",
    "8-2RBrNoPawns": "8-2RBr",
    "10-2QrNoPawns": "10-2Qr",
    "10-7-1QbrrNoPawns": "10-7-1Qbrr",
}


@dataclass(frozen=True)
class CombinedSummaryRow:
    source_pgn: str
    source_stem: str
    source_group: str
    output_pgn: str
    output_path: Path
    source_path: Path
    expected_matched_games: int


@dataclass(frozen=True)
class CombinedSourceStats:
    row: CombinedSummaryRow
    original_games: int
    matched_games: int
    incidence_total: int
    counts: dict[str, int]
    run_length_histograms: dict[str, dict[int, int]]
    incidence_run_length_histogram: dict[int, int]
    matched_game_run_length_histogram: dict[int, int]


@dataclass(frozen=True)
class CachedSourceTotal:
    source_pgn: str
    source_group: str | None
    games: int
    size_bytes: int | None
    mtime_ns: int | None


def count_event_tags(path: Path) -> int:
    return count_event_tags_with_progress(path, progress=None)


def count_event_tags_with_progress(path: Path, progress: Any | None = None) -> int:
    try:
        count = 0
        with path.open("rb") as handle:
            for line in handle:
                if progress is not None:
                    progress.update(len(line))
                if line.lstrip(b" \t").startswith(b"[Event "):
                    count += 1
        return count
    except FileNotFoundError as exc:
        raise SnapshotError(f"Required PGN does not exist: {path}") from exc


def classify_source_group(source_pgn: str) -> str:
    stem = Path(source_pgn).stem
    if stem.startswith("LumbrasGigaBase_OTB_"):
        return "otb"
    if stem.startswith("LumbrasGigaBase_Online_"):
        return "online"
    raise SnapshotError(
        f"Could not classify source PGN {source_pgn!r}; expected "
        "LumbrasGigaBase_OTB_* or LumbrasGigaBase_Online_*"
    )


def combined_source_bucket_key(source_pgn: str) -> str:
    stem = Path(source_pgn).stem
    for group, prefix in (
        ("otb", "LumbrasGigaBase_OTB_"),
        ("online", "LumbrasGigaBase_Online_"),
    ):
        if stem.startswith(prefix):
            return f"{group}:{stem[len(prefix):]}"
    return stem


def combined_source_bucket_label(source_pgn: str) -> str:
    stem = Path(source_pgn).stem
    for label, prefix in (
        ("OTB", "LumbrasGigaBase_OTB_"),
        ("Online", "LumbrasGigaBase_Online_"),
    ):
        if stem.startswith(prefix):
            bucket = stem[len(prefix) :].replace("_partial_release", " partial")
            return f"{label} {bucket.replace('_', ' ')}"
    return stem.replace("_partial_release", " partial").replace("_", " ")


def combined_source_sort_key(row: CombinedSummaryRow) -> tuple[int, tuple[int, str]]:
    group_rank = {"otb": 0, "online": 1}[row.source_group]
    return group_rank, source_sort_key(row.source_pgn)


def parse_combined_summary(
    *,
    annotated_run_dir: Path,
    corpus_dir: Path,
) -> tuple[CombinedSummaryRow, ...]:
    summary_csv = annotated_run_dir / "summary.csv"
    if not summary_csv.exists():
        raise SnapshotError(f"Missing combined CQL summary.csv: {summary_csv}")

    rows_by_source: dict[str, CombinedSummaryRow] = {}
    required = {"pgn", "cql", "output_pgn", "status", "match_count"}
    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise SnapshotError(
                f"{summary_csv} missing required field(s): {', '.join(sorted(missing))}"
            )
        for row_number, raw in enumerate(reader, start=2):
            status = raw.get("status") or ""
            if status != "ok":
                raise SnapshotError(
                    f"{summary_csv} row {row_number}: status is {status!r}, expected 'ok'"
                )
            cql_name = Path(raw.get("cql") or "").name
            if cql_name != COMBINED_SCRIPT_NAME:
                raise SnapshotError(
                    f"{summary_csv} row {row_number}: expected cql "
                    f"{COMBINED_SCRIPT_NAME!r}, got {cql_name!r}"
                )
            source = raw.get("pgn") or ""
            if not source:
                raise SnapshotError(f"{summary_csv} row {row_number}: missing pgn value")
            if source in rows_by_source:
                raise SnapshotError(f"{summary_csv} row {row_number}: duplicate source {source}")
            try:
                expected_matched_games = int(raw.get("match_count") or "")
            except ValueError as exc:
                raise SnapshotError(
                    f"{summary_csv} row {row_number}: invalid match_count "
                    f"{raw.get('match_count')!r}"
                ) from exc
            if expected_matched_games < 0:
                raise SnapshotError(
                    f"{summary_csv} row {row_number}: negative match_count "
                    f"{expected_matched_games}"
                )

            output_pgn = raw.get("output_pgn") or ""
            output_path = annotated_run_dir / output_pgn
            if not output_path.exists():
                raise SnapshotError(f"Annotated output PGN does not exist: {output_path}")
            source_path = corpus_dir / source
            if not source_path.exists():
                raise SnapshotError(f"Source corpus PGN does not exist: {source_path}")

            rows_by_source[source] = CombinedSummaryRow(
                source_pgn=source,
                source_stem=Path(source).stem,
                source_group=classify_source_group(source),
                output_pgn=output_pgn,
                output_path=output_path,
                source_path=source_path,
                expected_matched_games=expected_matched_games,
            )

    if not rows_by_source:
        raise SnapshotError(f"{summary_csv} contains no data rows")
    return tuple(sorted(rows_by_source.values(), key=combined_source_sort_key))


def load_source_totals(
    source_totals_json: Path,
    summary_rows: tuple[CombinedSummaryRow, ...],
) -> dict[str, int]:
    payload = load_json(source_totals_json)
    if payload.get("schemaVersion") != 1:
        raise SnapshotError(
            f"{source_totals_json} has unsupported schemaVersion "
            f"{payload.get('schemaVersion')!r}"
        )
    if payload.get("kind") != "reti-pgn-source-totals":
        raise SnapshotError(
            f"{source_totals_json} is not a reti-pgn-source-totals artifact"
        )
    if payload.get("countMethod") != "event-tag-lines":
        raise SnapshotError(
            f"{source_totals_json} uses unsupported countMethod "
            f"{payload.get('countMethod')!r}"
        )

    by_source: dict[str, CachedSourceTotal] = {}
    for raw in payload.get("files", []):
        if not isinstance(raw, dict):
            raise SnapshotError(f"{source_totals_json} contains a non-object file entry")
        source_pgn = str(raw.get("sourcePgn", ""))
        if not source_pgn:
            raise SnapshotError(f"{source_totals_json} contains a file without sourcePgn")
        if source_pgn in by_source:
            raise SnapshotError(f"{source_totals_json} has duplicate sourcePgn {source_pgn}")
        try:
            games = int(raw["games"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotError(
                f"{source_totals_json} entry {source_pgn} has invalid games value"
            ) from exc
        by_source[source_pgn] = CachedSourceTotal(
            source_pgn=source_pgn,
            source_group=(
                str(raw["sourceGroup"]) if raw.get("sourceGroup") is not None else None
            ),
            games=games,
            size_bytes=(
                int(raw["sizeBytes"]) if raw.get("sizeBytes") is not None else None
            ),
            mtime_ns=int(raw["mtimeNs"]) if raw.get("mtimeNs") is not None else None,
        )

    totals: dict[str, int] = {}
    for row in summary_rows:
        cached = by_source.get(row.source_pgn)
        if cached is None:
            raise SnapshotError(
                f"{source_totals_json} is missing source total for {row.source_pgn}"
            )
        if cached.source_group not in (None, row.source_group):
            raise SnapshotError(
                f"{source_totals_json} classifies {row.source_pgn} as "
                f"{cached.source_group!r}, expected {row.source_group!r}"
            )
        if cached.games < row.expected_matched_games:
            raise SnapshotError(
                f"{source_totals_json} reports {cached.games:,} total game(s) for "
                f"{row.source_pgn}, fewer than the {row.expected_matched_games:,} "
                "matched game(s) in summary.csv"
            )
        stat = row.source_path.stat()
        if cached.size_bytes is not None and cached.size_bytes != stat.st_size:
            raise SnapshotError(
                f"{source_totals_json} is stale for {row.source_pgn}: size is "
                f"{stat.st_size}, cached {cached.size_bytes}"
            )
        if cached.mtime_ns not in (None, 0) and cached.mtime_ns != stat.st_mtime_ns:
            raise SnapshotError(
                f"{source_totals_json} is stale for {row.source_pgn}: mtimeNs is "
                f"{stat.st_mtime_ns}, cached {cached.mtime_ns}"
            )
        totals[row.source_pgn] = cached.games
    return totals


def known_combined_stems() -> set[str]:
    return {ending.stem for ending in FCE_CATALOG.endings} | set(AUXILIARY_PARENT_STEMS)


def extract_known_stems(game_text: str, known_stems: set[str]) -> set[str]:
    stems: set[str] = set()
    for match in COMMENT_RE.finditer(game_text):
        text = match.group(1).strip()
        if text in known_stems:
            stems.add(text)
            continue
        for token in re.split(r"\s+", text):
            if token in known_stems:
                stems.add(token)
    return stems


def extract_known_stems_from_comment(comment_text: str, known_stems: set[str]) -> set[str]:
    text = comment_text.strip()
    if text in known_stems:
        return {text}
    return {token for token in re.split(r"\s+", text) if token in known_stems}


def movetext_section(game_text: str) -> str:
    parts = MOVE_TEXT_SPLIT_RE.split(game_text, maxsplit=1)
    return parts[1] if len(parts) == 2 else game_text


def count_move_tokens(text: str) -> int:
    count = 0
    for raw_token in re.split(r"\s+", text):
        token = raw_token.strip()
        if not token:
            continue
        token = token.strip("()")
        if not token or token.startswith("$"):
            continue
        token = re.sub(r"^\d+\.(?:\.\.)?", "", token)
        if not token or token in {"*", "1-0", "0-1", "1/2-1/2"}:
            continue
        if token.startswith("{") or token.endswith("}"):
            continue
        count += 1
    return count


def marker_positions_by_stem(game_text: str, known_stems: set[str]) -> dict[str, set[int]]:
    movetext = movetext_section(game_text)
    positions: dict[str, set[int]] = defaultdict(set)
    ply_index = 0
    cursor = 0
    for match in COMMENT_RE.finditer(movetext):
        ply_index += count_move_tokens(movetext[cursor : match.start()])
        for stem in extract_known_stems_from_comment(match.group(1), known_stems):
            positions[stem].add(ply_index)
        cursor = match.end()
    return positions


def max_consecutive_run(positions: set[int]) -> int:
    if not positions:
        return 0
    longest = 0
    current = 0
    previous: int | None = None
    for position in sorted(positions):
        if previous is not None and position == previous + 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = position
    return longest


def histogram_payload(histogram: dict[int, int]) -> dict[str, int]:
    return {str(length): int(count) for length, count in sorted(histogram.items()) if count}


def sum_histograms(histograms: list[dict[int, int]]) -> dict[int, int]:
    merged: Counter[int] = Counter()
    for histogram in histograms:
        merged.update({int(length): int(count) for length, count in histogram.items()})
    return dict(merged)


def iter_pgn_game_chunks(path: Path, *, progress: Any | None = None):
    current: list[str] = []
    with path.open("rb") as handle:
        for raw_line in handle:
            if progress is not None:
                progress.update(len(raw_line))
            line = raw_line.decode("utf-8", errors="replace")
            if line.startswith("[Event ") and current:
                yield "".join(current)
                current = [line]
            else:
                current.append(line)
    if current:
        yield "".join(current)


def scan_combined_annotated_pgn(
    *,
    summary_row: CombinedSummaryRow,
    known_stems: set[str] | None = None,
    progress: Any | None = None,
    original_games: int | None = None,
) -> CombinedSourceStats:
    known = known_stems or known_combined_stems()
    counts = {stem: 0 for stem in known}
    run_length_histograms: dict[str, Counter[int]] = {
        stem: Counter() for stem in known
    }
    incidence_run_length_histogram: Counter[int] = Counter()
    matched_game_run_length_histogram: Counter[int] = Counter()
    matched_games = 0
    incidence_total = 0
    for game_text in iter_pgn_game_chunks(summary_row.output_path, progress=progress):
        matched_games += 1
        positions_by_stem = marker_positions_by_stem(game_text, known)
        stems = set(positions_by_stem)
        incidence_total += len(stems)
        max_game_run = 0
        for stem in stems:
            counts[stem] += 1
            run_length = max_consecutive_run(positions_by_stem[stem])
            if run_length > 0:
                run_length_histograms[stem][run_length] += 1
                incidence_run_length_histogram[run_length] += 1
                max_game_run = max(max_game_run, run_length)
        if max_game_run > 0:
            matched_game_run_length_histogram[max_game_run] += 1

    if matched_games != summary_row.expected_matched_games:
        raise SnapshotError(
            f"{summary_row.output_path} contains {matched_games:,} game(s), "
            f"but summary.csv reports {summary_row.expected_matched_games:,}"
        )

    return CombinedSourceStats(
        row=summary_row,
        original_games=(
            original_games
            if original_games is not None
            else count_event_tags_with_progress(summary_row.source_path, progress=progress)
        ),
        matched_games=matched_games,
        incidence_total=incidence_total,
        counts=counts,
        run_length_histograms={
            stem: dict(histogram) for stem, histogram in run_length_histograms.items()
        },
        incidence_run_length_histogram=dict(incidence_run_length_histogram),
        matched_game_run_length_histogram=dict(matched_game_run_length_histogram),
    )


def progress_total_bytes(
    summary_rows: tuple[CombinedSummaryRow, ...],
    *,
    include_source_pgns: bool,
) -> int:
    return sum(
        row.output_path.stat().st_size
        + (row.source_path.stat().st_size if include_source_pgns else 0)
        for row in summary_rows
    )


def create_progress_bar(*, enabled: bool, total: int) -> Any | None:
    if not enabled:
        return None
    try:
        from tqdm import tqdm
    except Exception:
        print(
            "Progress disabled because tqdm is not installed.",
            file=sys.stderr,
        )
        return None
    return tqdm(
        total=total,
        desc="FCE snapshot",
        unit="B",
        unit_scale=True,
        dynamic_ncols=True,
        leave=True,
    )


def build_combined_manifest(
    *,
    annotated_run_dir: Path,
    corpus_dir: Path,
    output_dir: Path,
    title: str,
    combined_cql: Path,
    source_totals_json: Path | None,
    hash_source_pgns: bool,
    hash_annotated_pgns: bool,
) -> tuple[dict[str, Any], tuple[CombinedSummaryRow, ...]]:
    rows = parse_combined_summary(
        annotated_run_dir=annotated_run_dir,
        corpus_dir=corpus_dir,
    )
    inputs: dict[str, Any] = {
        "summaryCsv": file_signature(annotated_run_dir / "summary.csv", include_hash=True),
        "annotatedRunDir": str(annotated_run_dir),
        "corpusDir": str(corpus_dir),
        "combinedCql": (
            file_signature(combined_cql, include_hash=True)
            if combined_cql.exists()
            else {"path": str(combined_cql), "missing": True}
        ),
        "sourcePgns": [
            {
                "sourcePgn": row.source_pgn,
                "sourceGroup": row.source_group,
                **file_signature(row.source_path, include_hash=hash_source_pgns),
                "hashIncluded": hash_source_pgns,
            }
            for row in rows
        ],
        "annotatedPgns": [
            {
                "sourcePgn": row.source_pgn,
                "outputPgn": row.output_pgn,
                **file_signature(row.output_path, include_hash=hash_annotated_pgns),
                "hashIncluded": hash_annotated_pgns,
            }
            for row in rows
        ],
    }
    if source_totals_json is not None:
        inputs["sourceTotalsJson"] = file_signature(
            source_totals_json,
            include_hash=True,
        )
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "builder": "reti.fce_combined_snapshot",
        "settings": {
            "title": title,
            "annotatedRunDir": str(annotated_run_dir),
            "corpusDir": str(corpus_dir),
            "outputDir": str(output_dir),
            "combinedCql": str(combined_cql),
            "sourceTotalsJson": (
                str(source_totals_json) if source_totals_json is not None else None
            ),
            "hashSourcePgns": hash_source_pgns,
            "hashAnnotatedPgns": hash_annotated_pgns,
            "countingSemantics": "per-ending game incidence",
            "denominatorSource": (
                "source-totals-json"
                if source_totals_json is not None
                else "source-pgn-event-scan"
            ),
        },
        "inputs": inputs,
    }
    manifest["fingerprint"] = manifest_fingerprint(manifest)
    return manifest, rows


def view_row_payload(stem: str, source_stats: list[CombinedSourceStats]) -> dict[str, Any]:
    quantity = sum(stats.counts.get(stem, 0) for stats in source_stats)
    total_games = sum(stats.original_games for stats in source_stats)
    matched_rows = sum(stats.incidence_total for stats in source_stats)
    run_length_histogram = sum_histograms(
        [stats.run_length_histograms.get(stem, {}) for stats in source_stats]
    )
    return {
        "quantity": quantity,
        "percentage": quantity / total_games * 100.0 if total_games else None,
        "matchedShare": quantity / matched_rows * 100.0 if matched_rows else None,
        "runLengthHistogram": histogram_payload(run_length_histogram),
        "sourceCounts": {
            stats.row.source_pgn: stats.counts.get(stem, 0) for stats in source_stats
        },
        "exactness": "exact",
    }


def build_dataset_view(
    key: str,
    label: str,
    source_stats: list[CombinedSourceStats],
) -> dict[str, Any]:
    canonical_stems = [ending.stem for ending in FCE_CATALOG.endings]
    stems = [*canonical_stems, *AUXILIARY_PARENT_STEMS.keys()]
    rows = {stem: view_row_payload(stem, source_stats) for stem in stems}
    total_games = sum(stats.original_games for stats in source_stats)
    matched_games = sum(stats.matched_games for stats in source_stats)
    matched_rows = sum(stats.incidence_total for stats in source_stats)
    incidence_run_length_histogram = sum_histograms(
        [stats.incidence_run_length_histogram for stats in source_stats]
    )
    matched_game_run_length_histogram = sum_histograms(
        [stats.matched_game_run_length_histogram for stats in source_stats]
    )
    return {
        "key": key,
        "label": label,
        "shortLabel": label,
        "description": (
            "each game contributes at most once to each ending in this corpus view"
        ),
        "totalGames": total_games,
        "matchedGames": matched_games,
        "matchedRows": matched_rows,
        "incidenceRunLengthHistogram": histogram_payload(incidence_run_length_histogram),
        "matchedGameRunLengthHistogram": histogram_payload(matched_game_run_length_histogram),
        "sourceBuckets": len(source_stats),
        "sourcePgns": [stats.row.source_pgn for stats in source_stats],
        "sourceIncidenceRunLengthHistograms": {
            stats.row.source_pgn: histogram_payload(stats.incidence_run_length_histogram)
            for stats in source_stats
        },
        "sourceMatchedGameRunLengthHistograms": {
            stats.row.source_pgn: histogram_payload(stats.matched_game_run_length_histogram)
            for stats in source_stats
        },
        "rows": rows,
        "exactness": "exact",
    }


def auxiliary_label(stem: str) -> str:
    labels = {
        "6-2-2RPPrConnected": "Connected pawns",
        "8-1RNrNoPawns": "Without pawns",
        "8-2RBrNoPawns": "Without pawns",
        "10-2QrNoPawns": "Without pawns",
        "10-7-1QbrrNoPawns": "Without pawns",
    }
    return labels.get(stem, stem)


def build_rows_from_dataset_view(view: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    view_rows = view["rows"]
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for child, parent in AUXILIARY_PARENT_STEMS.items():
        children_by_parent[parent].append(child)

    for sort_index, ending in enumerate(FCE_CATALOG.endings):
        counts = view_rows[ending.stem]
        row = {
            "stem": ending.stem,
            "sortIndex": sort_index,
            "rowId": ending.row_id,
            "label": ending.label,
            "displayLabel": ending.display_label,
            "chapterKey": ending.chapter_key,
            "chapter": ending.chapter_label,
            "color": ending.color,
            **counts,
        }
        auxiliary_rows = []
        for offset, child_stem in enumerate(children_by_parent.get(ending.stem, []), start=1):
            child_counts = view_rows[child_stem]
            auxiliary_rows.append(
                {
                    "stem": child_stem,
                    "parentStem": ending.stem,
                    "sortIndex": sort_index + offset / 10.0,
                    "rowId": "",
                    "label": auxiliary_label(child_stem),
                    "displayLabel": auxiliary_label(child_stem),
                    "chapterKey": ending.chapter_key,
                    "chapter": ending.chapter_label,
                    "color": ending.color,
                    **child_counts,
                }
            )
        if auxiliary_rows:
            row["auxiliaryRows"] = auxiliary_rows
        rows.append(row)
    return rows


def build_source_buckets_from_stats(
    source_stats: list[CombinedSourceStats],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    source_files = {
        str(item["sourcePgn"]): item for item in manifest["inputs"]["sourcePgns"]
    }
    output_files = {
        str(item["sourcePgn"]): item for item in manifest["inputs"]["annotatedPgns"]
    }
    buckets = []
    for sort_index, stats in enumerate(source_stats):
        source = stats.row.source_pgn
        buckets.append(
            {
                "sourcePgn": source,
                "sourceStem": stats.row.source_stem,
                "sourceGroup": stats.row.source_group,
                "bucket": combined_source_bucket_key(source),
                "displayLabel": combined_source_bucket_label(source),
                "sortIndex": sort_index,
                "originalGameCount": stats.original_games,
                "matchedGames": stats.matched_games,
                "matchTotal": stats.incidence_total,
                "incidenceRunLengthHistogram": histogram_payload(
                    stats.incidence_run_length_histogram
                ),
                "matchedGameRunLengthHistogram": histogram_payload(
                    stats.matched_game_run_length_histogram
                ),
                "counts": {
                    ending.stem: stats.counts.get(ending.stem, 0)
                    for ending in FCE_CATALOG.endings
                },
                "file": source_files[source],
                "annotatedFile": output_files[source],
                "exactness": "exact",
            }
        )
    return buckets


def build_combined_snapshot_payload(
    *,
    manifest: dict[str, Any],
    source_stats: list[CombinedSourceStats],
    title: str,
    corpus_dir: Path,
) -> dict[str, Any]:
    all_view = build_dataset_view("all", "All", source_stats)
    otb_view = build_dataset_view(
        "otb",
        "OTB",
        [stats for stats in source_stats if stats.row.source_group == "otb"],
    )
    online_view = build_dataset_view(
        "online",
        "Online",
        [stats for stats in source_stats if stats.row.source_group == "online"],
    )
    dataset_views = {
        "default": "all",
        "views": {
            "all": all_view,
            "otb": otb_view,
            "online": online_view,
        },
    }
    snapshot: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotId": f"fce-combined-{manifest['fingerprint'][:12]}",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "corpus": {
            "name": "Lumbra/Lumbras Gigabase",
            "source": str(corpus_dir),
            "totalGames": all_view["totalGames"],
            "sourceBucketCount": len(source_stats),
            "sourceGroups": ["otb", "online"],
            "exactness": "exact",
        },
        "inputs": manifest["inputs"],
        "catalog": catalog_payload(),
        "totals": {
            "summaryRows": len(source_stats),
            "sourceBuckets": len(source_stats),
            "endingRows": len(FCE_CATALOG.endings),
            "matchedGames": all_view["matchedGames"],
            "matchedRows": all_view["matchedRows"],
            "exactness": "exact",
        },
        "sourceBuckets": build_source_buckets_from_stats(source_stats, manifest),
        "originalFceReference": original_fce_reference_payload(),
        "datasetViews": dataset_views,
        "rows": build_rows_from_dataset_view(all_view),
        "methodology": {
            "countingSemantics": "per-ending game incidence",
            "combinedComments": True,
            "runLengthThresholds": True,
        },
    }
    return snapshot


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        import json

        return json.load(handle)


def build_fce_combined_snapshot(
    *,
    annotated_run_dir: str | Path,
    corpus_dir: str | Path,
    output_dir: str | Path,
    title: str,
    combined_cql: str | Path = DEFAULT_COMBINED_CQL,
    source_totals_json: str | Path | None = None,
    hash_source_pgns: bool = False,
    hash_annotated_pgns: bool = False,
    force: bool = False,
    show_progress: bool = False,
) -> SnapshotBuildResult:
    run_path = Path(annotated_run_dir).expanduser().resolve()
    corpus_path = Path(corpus_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    cql_path = Path(combined_cql).expanduser().resolve()
    source_totals_path = (
        Path(source_totals_json).expanduser().resolve()
        if source_totals_json is not None
        else None
    )

    manifest, summary_rows = build_combined_manifest(
        annotated_run_dir=run_path,
        corpus_dir=corpus_path,
        output_dir=output_path,
        title=title,
        combined_cql=cql_path,
        source_totals_json=source_totals_path,
        hash_source_pgns=hash_source_pgns,
        hash_annotated_pgns=hash_annotated_pgns,
    )

    manifest_path = output_path / "manifest.json"
    if output_path.exists():
        if not output_path.is_dir():
            raise SnapshotError(f"Output path exists and is not a directory: {output_path}")
        if not force and manifest_path.exists() and load_json(manifest_path) == manifest:
            return SnapshotBuildResult(
                output_dir=output_path,
                snapshot_path=output_path / "snapshot.json",
                manifest_path=manifest_path,
                summary_csv_path=output_path / "summary_by_ending.csv",
                html_path=output_path / "index.html",
                snapshot_id=f"fce-combined-{manifest['fingerprint'][:12]}",
                up_to_date=True,
            )
        if not force:
            raise SnapshotError(
                f"{output_path} already exists but its manifest does not match "
                "the current inputs. Use --force to rebuild or choose a new output directory."
            )

    source_totals = (
        load_source_totals(source_totals_path, summary_rows)
        if source_totals_path is not None
        else None
    )
    known_stems = known_combined_stems()
    progress = create_progress_bar(
        enabled=show_progress,
        total=progress_total_bytes(
            summary_rows,
            include_source_pgns=source_totals is None,
        ),
    )
    try:
        source_stats = []
        for row in summary_rows:
            if progress is not None:
                progress.set_postfix_str(row.source_stem[-36:])
            source_stats.append(
                scan_combined_annotated_pgn(
                    summary_row=row,
                    known_stems=known_stems,
                    progress=progress,
                    original_games=(
                        source_totals[row.source_pgn]
                        if source_totals is not None
                        else None
                    ),
                )
            )
    finally:
        if progress is not None:
            progress.close()
    snapshot = build_combined_snapshot_payload(
        manifest=manifest,
        source_stats=source_stats,
        title=title,
        corpus_dir=corpus_path,
    )
    return write_snapshot_directory(
        target_dir=output_path,
        manifest=manifest,
        snapshot=snapshot,
        force=force,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a reusable FCE snapshot from combined-comment annotated PGNs."
    )
    parser.add_argument("--annotated-run-dir", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--combined-cql", type=Path, default=DEFAULT_COMBINED_CQL)
    parser.add_argument(
        "--source-totals-json",
        type=Path,
        help=(
            "Reusable denominator artifact from "
            "`reti-pgn-utils source-totals`; avoids rereading source PGNs."
        ),
    )
    parser.add_argument("--hash-source-pgns", action="store_true")
    parser.add_argument("--hash-annotated-pgns", action="store_true")
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the byte progress bar while scanning PGNs.",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_fce_combined_snapshot(
        annotated_run_dir=args.annotated_run_dir,
        corpus_dir=args.corpus_dir,
        output_dir=args.output_dir,
        title=args.title,
        combined_cql=args.combined_cql,
        source_totals_json=args.source_totals_json,
        hash_source_pgns=args.hash_source_pgns,
        hash_annotated_pgns=args.hash_annotated_pgns,
        force=args.force,
        show_progress=not args.no_progress,
    )
    if result.up_to_date:
        print(f"Up to date: {result.output_dir}")
    else:
        print(f"Wrote snapshot: {result.snapshot_path}")
        print(f"Wrote HTML: {result.html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
