from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from reti.fce_combined_snapshot import (
    SnapshotError,
    build_fce_combined_snapshot,
    classify_source_group,
    extract_known_stems,
    load_source_totals,
    parse_combined_summary,
    scan_combined_annotated_pgn,
)
from reti.fce_snapshot import load_json, render_snapshot_html


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def one_game(event: str, movetext: str = "1. e4 e5 *") -> str:
    return (
        f'[Event "{event}"]\n'
        '[Site "?"]\n'
        '[Date "2026.05.15"]\n'
        '[Round "?"]\n'
        '[White "White"]\n'
        '[Black "Black"]\n'
        '[Result "*"]\n\n'
        f"{movetext}\n\n"
    )


def make_fixture(root: Path, *, bad_summary: bool = False, mismatch: bool = False) -> tuple[Path, Path, Path]:
    run_dir = root / "run"
    corpus_dir = root / "corpus"
    output_dir = root / "snapshot"
    sources = [
        ("LumbrasGigaBase_OTB_2025.pgn", "LumbrasGigaBase_OTB_2025", "1. e4 {3-2NN} e5 {3-2NN} 2. Nf3 {8-3RAra} *"),
        ("LumbrasGigaBase_Online_2025.pgn", "LumbrasGigaBase_Online_2025", "1. d4 {10-2Qr} d5 {not-an-ending} 2. c4 {10-2QrNoPawns} *"),
    ]
    for source, _, _ in sources:
        write_text(corpus_dir / source, one_game(source) + one_game(source + "-2"))

    rows = ["pgn,cql,output_pgn,status,match_count,returncode"]
    for source, bucket, movetext in sources:
        output_rel = f"{bucket}/fce-table-markers.pgn"
        write_text(run_dir / output_rel, one_game(bucket, movetext))
        status = "error" if bad_summary and source.startswith("LumbrasGigaBase_Online") else "ok"
        match_count = "2" if mismatch and source.startswith("LumbrasGigaBase_Online") else "1"
        rows.append(f"{source},fce-table-markers.cql,{output_rel},{status},{match_count},0")
    write_text(run_dir / "summary.csv", "\n".join(rows) + "\n")
    return run_dir, corpus_dir, output_dir


def write_source_totals(
    path: Path,
    corpus_dir: Path,
    games_by_source: dict[str, int],
) -> None:
    files = []
    for source_pgn, games in games_by_source.items():
        source_path = corpus_dir / source_pgn
        stat = source_path.stat()
        files.append(
            {
                "sourcePgn": source_pgn,
                "sourceGroup": classify_source_group(source_pgn),
                "path": str(source_path),
                "sizeBytes": stat.st_size,
                "mtimeNs": stat.st_mtime_ns,
                "games": games,
            }
        )
    payload = {
        "schemaVersion": 1,
        "kind": "reti-pgn-source-totals",
        "countMethod": "event-tag-lines",
        "filesProcessed": len(files),
        "bytesIn": sum(item["sizeBytes"] for item in files),
        "totalGames": sum(item["games"] for item in files),
        "views": {
            "all": sum(item["games"] for item in files),
            "otb": sum(item["games"] for item in files if item["sourceGroup"] == "otb"),
            "online": sum(item["games"] for item in files if item["sourceGroup"] == "online"),
            "unknown": 0,
        },
        "files": files,
    }
    write_text(path, json.dumps(payload, sort_keys=True) + "\n")


class TestFceCombinedSnapshot(unittest.TestCase):
    def test_extract_known_stems_deduplicates_repeated_comments_and_ignores_unknowns(self) -> None:
        stems = extract_known_stems(
            "1. e4 {3-2NN} e5 {3-2NN} 2. Nf3 {8-3RAra} {unknown} *",
            {"3-2NN", "8-3RAra"},
        )
        self.assertEqual(stems, {"3-2NN", "8-3RAra"})

    def test_extract_known_stems_handles_coalesced_marker_comments(self) -> None:
        stems = extract_known_stems(
            "1. e4 {Game number 1} {8-1RNrNoPawns 8-1RNr} *",
            {"8-1RNrNoPawns", "8-1RNr"},
        )
        self.assertEqual(stems, {"8-1RNrNoPawns", "8-1RNr"})

    def test_source_group_classification(self) -> None:
        self.assertEqual(classify_source_group("LumbrasGigaBase_OTB_2025.pgn"), "otb")
        self.assertEqual(
            classify_source_group("LumbrasGigaBase_Online_2025.pgn"), "online"
        )
        with self.assertRaises(SnapshotError):
            classify_source_group("LumbrasGigaBase_Blitz_2025.pgn")

    def test_scan_combined_pgn_counts_each_stem_once_per_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir, corpus_dir, _ = make_fixture(root)
            summary_row = parse_combined_summary(
                annotated_run_dir=run_dir,
                corpus_dir=corpus_dir,
            )[0]
            stats = scan_combined_annotated_pgn(
                summary_row=summary_row,
                known_stems={"3-2NN", "8-3RAra"},
            )
            self.assertEqual(stats.matched_games, 1)
            self.assertEqual(stats.counts["3-2NN"], 1)
            self.assertEqual(stats.counts["8-3RAra"], 1)
            self.assertEqual(stats.incidence_total, 2)
            self.assertEqual(stats.run_length_histograms["3-2NN"], {2: 1})
            self.assertEqual(stats.run_length_histograms["8-3RAra"], {1: 1})
            self.assertEqual(stats.incidence_run_length_histogram, {1: 1, 2: 1})
            self.assertEqual(stats.matched_game_run_length_histogram, {2: 1})

    def test_builder_validates_failures_and_match_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir, corpus_dir, output_dir = make_fixture(Path(tmpdir), bad_summary=True)
            with self.assertRaises(SnapshotError):
                build_fce_combined_snapshot(
                    annotated_run_dir=run_dir,
                    corpus_dir=corpus_dir,
                    output_dir=output_dir,
                    title="Combined FCE",
                )
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir, corpus_dir, output_dir = make_fixture(Path(tmpdir), mismatch=True)
            with self.assertRaises(SnapshotError):
                build_fce_combined_snapshot(
                    annotated_run_dir=run_dir,
                    corpus_dir=corpus_dir,
                    output_dir=output_dir,
                    title="Combined FCE",
                )

    def test_builder_writes_dataset_views_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir, corpus_dir, output_dir = make_fixture(Path(tmpdir))
            result = build_fce_combined_snapshot(
                annotated_run_dir=run_dir,
                corpus_dir=corpus_dir,
                output_dir=output_dir,
                title="Combined FCE",
            )
            self.assertFalse(result.up_to_date)
            payload = load_json(result.snapshot_path)
            self.assertEqual(payload["datasetViews"]["views"]["all"]["totalGames"], 4)
            self.assertEqual(payload["datasetViews"]["views"]["otb"]["totalGames"], 2)
            self.assertEqual(payload["datasetViews"]["views"]["online"]["totalGames"], 2)
            self.assertEqual(payload["datasetViews"]["views"]["all"]["rows"]["3-2NN"]["quantity"], 1)
            self.assertEqual(payload["datasetViews"]["views"]["all"]["rows"]["10-2QrNoPawns"]["quantity"], 1)
            self.assertEqual(
                payload["datasetViews"]["views"]["all"]["rows"]["3-2NN"]["runLengthHistogram"],
                {"2": 1},
            )
            self.assertEqual(
                payload["datasetViews"]["views"]["all"]["incidenceRunLengthHistogram"],
                {"1": 3, "2": 1},
            )
            self.assertEqual(
                payload["datasetViews"]["views"]["all"]["matchedGameRunLengthHistogram"],
                {"1": 1, "2": 1},
            )
            self.assertIn(
                "10-2QrNoPawns",
                result.summary_csv_path.read_text(encoding="utf-8"),
            )

            second = build_fce_combined_snapshot(
                annotated_run_dir=run_dir,
                corpus_dir=corpus_dir,
                output_dir=output_dir,
                title="Combined FCE",
            )
            self.assertTrue(second.up_to_date)

            forced = build_fce_combined_snapshot(
                annotated_run_dir=run_dir,
                corpus_dir=corpus_dir,
                output_dir=output_dir,
                title="Combined FCE",
                force=True,
            )
            self.assertFalse(forced.up_to_date)

    def test_builder_uses_cached_source_totals_without_counting_source_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir, corpus_dir, output_dir = make_fixture(root)
            totals_json = root / "source_totals.json"
            write_text(corpus_dir / "LumbrasGigaBase_OTB_2025.pgn", "not a pgn\n")
            write_text(corpus_dir / "LumbrasGigaBase_Online_2025.pgn", "also not a pgn\n")
            write_source_totals(
                totals_json,
                corpus_dir,
                {
                    "LumbrasGigaBase_OTB_2025.pgn": 10,
                    "LumbrasGigaBase_Online_2025.pgn": 20,
                },
            )
            result = build_fce_combined_snapshot(
                annotated_run_dir=run_dir,
                corpus_dir=corpus_dir,
                output_dir=output_dir,
                title="Combined FCE",
                source_totals_json=totals_json,
            )
            payload = load_json(result.snapshot_path)
            self.assertEqual(payload["datasetViews"]["views"]["all"]["totalGames"], 30)
            self.assertEqual(payload["datasetViews"]["views"]["otb"]["totalGames"], 10)
            self.assertEqual(payload["datasetViews"]["views"]["online"]["totalGames"], 20)
            manifest = load_json(result.manifest_path)
            self.assertEqual(
                manifest["settings"]["denominatorSource"], "source-totals-json"
            )
            self.assertIn("sourceTotalsJson", manifest["inputs"])

    def test_source_totals_staleness_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir, corpus_dir, _ = make_fixture(root)
            rows = parse_combined_summary(
                annotated_run_dir=run_dir,
                corpus_dir=corpus_dir,
            )
            totals_json = root / "source_totals.json"
            write_source_totals(
                totals_json,
                corpus_dir,
                {
                    "LumbrasGigaBase_OTB_2025.pgn": 2,
                    "LumbrasGigaBase_Online_2025.pgn": 2,
                },
            )
            payload = json.loads(totals_json.read_text(encoding="utf-8"))
            payload["files"][0]["sizeBytes"] += 1
            write_text(totals_json, json.dumps(payload) + "\n")
            with self.assertRaises(SnapshotError):
                load_source_totals(totals_json, rows)

    def test_rendered_html_has_dataset_tabs_auxiliary_rows_and_no_tablebase_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir, corpus_dir, output_dir = make_fixture(Path(tmpdir))
            result = build_fce_combined_snapshot(
                annotated_run_dir=run_dir,
                corpus_dir=corpus_dir,
                output_dir=output_dir,
                title="Combined FCE",
            )
            payload = load_json(result.snapshot_path)
            html = render_snapshot_html(payload)
            self.assertIn("data-dataset-view=\"all\"", html)
            self.assertIn("data-dataset-view=\"otb\"", html)
            self.assertIn("data-dataset-view=\"online\"", html)
            for threshold in ("1", "2", "5", "10", "20"):
                self.assertIn(f'data-run-length-threshold="{threshold}"', html)
            self.assertIn("runLengthHistogram", html)
            self.assertIn("data-stem=\"10-2QrNoPawns\"", html)
            self.assertIn("data-stem=\"10-7-1QbrrNoPawns\"", html)
            self.assertNotIn('<th class="num">TB positions</th>', html)
            self.assertNotIn("<th>Tablebase WDL</th>", html)


if __name__ == "__main__":
    unittest.main()
