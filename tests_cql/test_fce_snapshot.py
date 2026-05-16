from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reti.fce_metadata import FCE_CATALOG
from reti.fce_snapshot import (
    SnapshotError,
    build_fce_gigabase_snapshot,
    load_summary_data,
    render_fce_snapshot_dashboard,
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _summary_text(
    sources: list[str],
    *,
    missing: tuple[str, str] | None = None,
    failed: tuple[str, str] | None = None,
    duplicate: tuple[str, str, int] | None = None,
) -> str:
    lines = ["pgn,cql,output_pgn,status,match_count,returncode"]
    for source in sources:
        source_stem = Path(source).stem
        for ending in FCE_CATALOG.endings:
            if missing == (source, ending.stem):
                continue
            status = "error" if failed == (source, ending.stem) else "ok"
            count = ending.specificity_rank + 1
            returncode = 1 if status == "error" else 0
            lines.append(
                f"{source},{ending.stem}.cql,{source_stem}/{ending.stem}.pgn,"
                f"{status},{count},{returncode}"
            )
    if duplicate is not None:
        source, stem, count = duplicate
        source_stem = Path(source).stem
        lines.append(
            f"{source},{stem}.cql,{source_stem}/{stem}.pgn,ok,{count},0"
        )
    return "\n".join(lines) + "\n"


def _write_corpus_files(corpus_dir: Path, sources: list[str]) -> None:
    for source in sources:
        _write_text(corpus_dir / source, f'[Event "{source}"]\n\n*\n')


def _write_cql_table(cql_dir: Path) -> None:
    lines = ["target,source,mode,score"]
    for ending in FCE_CATALOG.endings:
        _write_text(cql_dir / f"{ending.stem}.cql", "cql()\ntrue\n")
        lines.append(f"{ending.stem},{ending.stem},fixture,1.000")
    _write_text(cql_dir / "manifest.csv", "\n".join(lines) + "\n")


def _write_tablebase_wdl_csv(path: Path) -> None:
    columns = [
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
        "actual_white_wins",
        "actual_draws",
        "actual_black_wins",
        "actual_side_wins",
        "actual_side_draws",
        "actual_side_losses",
        "actual_symmetric_decisive",
        "actual_unknown_results",
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
    ]

    def row(**values: object) -> str:
        payload = {column: 0 for column in columns}
        payload.update(values)
        return ",".join(str(payload[column]) for column in columns)

    rows = [
        ",".join(columns),
        row(
            ending="1-4BN",
            material_label="bishop+knight side",
            total_positions=8,
            evaluated_positions=8,
            tablebase_eligible_positions=8,
            tablebase_positions=8,
            white_wins=6,
            draws=2,
            side_wins=6,
            side_draws=2,
            actual_white_wins=5,
            actual_draws=2,
            actual_black_wins=1,
            actual_side_wins=5,
            actual_side_draws=2,
            actual_side_losses=1,
            tb_win_result_win=5,
            tb_win_result_draw=1,
            tb_draw_result_draw=1,
            tb_draw_result_loss=1,
        ),
        row(
            ending="2-0Pp",
            material_label="symmetric/either side",
            total_positions=10,
            evaluated_positions=10,
            tablebase_eligible_positions=10,
            tablebase_positions=10,
            white_wins=3,
            draws=4,
            black_wins=3,
            side_draws=4,
            symmetric_decisive=6,
            actual_white_wins=4,
            actual_draws=3,
            actual_black_wins=3,
            actual_side_draws=3,
            actual_symmetric_decisive=7,
            tb_draw_result_decisive=2,
            tb_draw_result_draw=2,
            tb_decisive_result_decisive=5,
            tb_decisive_result_draw=1,
        ),
    ]
    _write_text(path, "\n".join(rows) + "\n")


def _write_examples_jsonl(path: Path) -> None:
    rows = [
        {
            "stem": "1-4BN",
            "output_pgn": "LumbrasGigaBase_OTB_2020-2024/1-4BN.pgn",
            "source_pgn": "LumbrasGigaBase_OTB_2020-2024.pgn",
            "game_index": 7,
            "headers": {
                "Event": "Fixture Event",
                "Site": "Fixture Site",
                "Date": "2024.01.01",
                "Round": "1",
                "White": "Example, White",
                "Black": "Example, Black",
                "Result": "1-0",
            },
            "fullmove": 59,
            "move_san": "Kxg5",
            "fen": "7k/8/8/5BKN/8/8/8/8 b - - 0 59",
        },
        {
            "stem": "1-4BN",
            "output_pgn": "LumbrasGigaBase_OTB_2020-2024/1-4BN.pgn",
            "source_pgn": "LumbrasGigaBase_OTB_2020-2024.pgn",
            "game_index": 7,
            "headers": {
                "Event": "Fixture Event",
                "Site": "Fixture Site",
                "Date": "2024.01.01",
                "Round": "1",
                "White": "Example, White",
                "Black": "Example, Black",
                "Result": "1-0",
            },
            "fullmove": 60,
            "move_san": "Kg8",
            "fen": "6k1/8/8/5BKN/8/8/8/8 w - - 1 60",
        },
    ]
    _write_text(path, "\n".join(json.dumps(row) for row in rows) + "\n")


def _snapshot_payload(html: str) -> dict:
    match = re.search(
        r'<script id="snapshot-data" type="application/json">(.*?)</script>',
        html,
        flags=re.S,
    )
    if match is None:
        raise AssertionError("snapshot JSON payload not found")
    return json.loads(match.group(1))


class TestFceSnapshot(unittest.TestCase):
    def test_load_summary_requires_every_fce_row_for_every_source(self) -> None:
        source = "LumbrasGigaBase_OTB_2020-2024.pgn"
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "summary.csv"
            _write_text(
                summary,
                _summary_text([source], missing=(source, FCE_CATALOG.endings[0].stem)),
            )

            with self.assertRaisesRegex(SnapshotError, "missing 1 FCE row"):
                load_summary_data(summary)

    def test_load_summary_rejects_failed_rows(self) -> None:
        source = "LumbrasGigaBase_OTB_2020-2024.pgn"
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "summary.csv"
            _write_text(
                summary,
                _summary_text([source], failed=(source, FCE_CATALOG.endings[1].stem)),
            )

            with self.assertRaisesRegex(SnapshotError, "expected 'ok'"):
                load_summary_data(summary)

    def test_load_summary_aggregates_duplicate_source_stem_rows(self) -> None:
        source = "LumbrasGigaBase_OTB_2020-2024.pgn"
        stem = FCE_CATALOG.endings[0].stem
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "summary.csv"
            _write_text(summary, _summary_text([source], duplicate=(source, stem, 11)))
            data = load_summary_data(summary)

        self.assertEqual(data.counts_by_source[source][stem], 12)
        self.assertEqual(data.total_by_stem[stem], 12)

    def test_snapshot_build_is_idempotent_and_detects_input_mismatch(self) -> None:
        sources = [
            "LumbrasGigaBase_OTB_1900-1949.pgn",
            "LumbrasGigaBase_OTB_2020-2024.pgn",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "run" / "summary.csv"
            corpus = root / "corpus"
            cql_dir = root / "cql-table"
            output = root / "snapshot"
            _write_text(summary, _summary_text(sources))
            _write_corpus_files(corpus, sources)
            _write_cql_table(cql_dir)

            first = build_fce_gigabase_snapshot(
                summary_csv=summary,
                run_dir=summary.parent,
                corpus_dir=corpus,
                total_games=1000,
                output_dir=output,
                title="Fixture snapshot",
                cql_table_dir=cql_dir,
            )
            first_mtime = first.snapshot_path.stat().st_mtime_ns

            second = build_fce_gigabase_snapshot(
                summary_csv=summary,
                run_dir=summary.parent,
                corpus_dir=corpus,
                total_games=1000,
                output_dir=output,
                title="Fixture snapshot",
                cql_table_dir=cql_dir,
            )

            self.assertFalse(first.up_to_date)
            self.assertTrue(second.up_to_date)
            self.assertEqual(first.snapshot_id, second.snapshot_id)
            self.assertEqual(first_mtime, first.snapshot_path.stat().st_mtime_ns)
            with self.assertRaisesRegex(SnapshotError, "manifest does not match"):
                build_fce_gigabase_snapshot(
                    summary_csv=summary,
                    run_dir=summary.parent,
                    corpus_dir=corpus,
                    total_games=1001,
                    output_dir=output,
                    title="Fixture snapshot",
                    cql_table_dir=cql_dir,
                )

    def test_snapshot_dashboard_renders_from_json_without_pgn_inputs(self) -> None:
        sources = ["LumbrasGigaBase_OTB_2020-2024.pgn"]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "run" / "summary.csv"
            corpus = root / "corpus"
            cql_dir = root / "cql-table"
            output = root / "snapshot"
            rendered = root / "rendered.html"
            _write_text(summary, _summary_text(sources))
            _write_corpus_files(corpus, sources)
            _write_cql_table(cql_dir)

            result = build_fce_gigabase_snapshot(
                summary_csv=summary,
                run_dir=summary.parent,
                corpus_dir=corpus,
                total_games=1000,
                output_dir=output,
                title="Fixture snapshot",
                cql_table_dir=cql_dir,
            )
            for source in sources:
                (corpus / source).unlink()

            render_fce_snapshot_dashboard(
                snapshot_json=result.snapshot_path,
                output_html=rendered,
                title="Rendered from snapshot",
            )
            html = rendered.read_text(encoding="utf-8")
            payload = _snapshot_payload(html)

        self.assertIn("Rendered from snapshot", html)
        self.assertIn("Methodology", html)
        self.assertIn("Original Fundamental Chess Endings Table", html)
        self.assertEqual(payload["corpus"]["totalGames"], 1000)
        self.assertEqual(
            len(payload["originalFceReference"]["rows"]),
            len(FCE_CATALOG.endings),
        )
        self.assertEqual(
            [row["stem"] for row in payload["rows"]],
            [ending.stem for ending in FCE_CATALOG.endings],
        )
        self.assertEqual(payload["rows"][0]["quantity"], 1)
        self.assertEqual(payload["totals"]["exactness"], "exact")

    def test_snapshot_dashboard_can_include_tablebase_wdl_csv(self) -> None:
        sources = ["LumbrasGigaBase_OTB_2020-2024.pgn"]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = root / "run" / "summary.csv"
            corpus = root / "corpus"
            cql_dir = root / "cql-table"
            output = root / "snapshot"
            tablebase_csv = root / "ending_tablebase_wdl.csv"
            examples_jsonl = root / "examples.jsonl"
            rendered = root / "rendered.html"
            _write_text(summary, _summary_text(sources))
            _write_corpus_files(corpus, sources)
            _write_cql_table(cql_dir)
            _write_tablebase_wdl_csv(tablebase_csv)
            _write_examples_jsonl(examples_jsonl)

            result = build_fce_gigabase_snapshot(
                summary_csv=summary,
                run_dir=summary.parent,
                corpus_dir=corpus,
                total_games=1000,
                output_dir=output,
                title="Fixture snapshot",
                cql_table_dir=cql_dir,
            )
            for source in sources:
                (corpus / source).unlink()

            render_fce_snapshot_dashboard(
                snapshot_json=result.snapshot_path,
                output_html=rendered,
                tablebase_wdl_csv=tablebase_csv,
                examples_jsonl=examples_jsonl,
            )
            html = rendered.read_text(encoding="utf-8")
            payload = _snapshot_payload(html)

        self.assertIn("Tablebase positions", html)
        self.assertIn("wdl-bar", html)
        self.assertIn("detail-row", html)
        self.assertIn("ending-table", html)
        self.assertIn('data-label="Tablebase WDL"', html)
        self.assertIn("@media (max-width: 900px)", html)
        self.assertIn("theme-toggle", html)
        self.assertIn("theme-icon-moon", html)
        self.assertIn("theme-icon-sun", html)
        self.assertIn("board-link", html)
        self.assertIn("https://lichess.org/analysis/standard/", html)
        self.assertIn("raw.githubusercontent.com/lichess-org/lila/master/public/piece/cburnett", html)
        self.assertIn("How To Read", html)
        self.assertIn("Sampled Examples", html)
        self.assertIn("Example, White", html)
        self.assertNotIn("<th>Material side</th>", html)
        self.assertNotIn('data-label="Material side"', html)
        self.assertNotIn("<th>TB exactness</th>", html)
        self.assertNotIn('data-label="TB exactness"', html)
        self.assertIn("6 (75.0%)", html)
        self.assertIn("Actual result", html)
        self.assertIn("actual win", html)
        self.assertIn("Aligned", html)
        self.assertIn("Decisive", html)
        self.assertEqual(payload["tablebaseWdl"]["totals"]["evaluated_positions"], 18)
        self.assertTrue(payload["tablebaseWdl"]["hasActualResults"])
        self.assertEqual(payload["sampledExamples"]["byStem"]["1-4BN"]["gameCount"], 1)
        self.assertEqual(
            payload["sampledExamples"]["byStem"]["1-4BN"]["examples"][0]["markerCount"],
            2,
        )
        self.assertEqual(payload["rows"][0]["tablebaseWdl"]["aggregate"]["side_wins"], 6)
        self.assertEqual(
            payload["rows"][0]["tablebaseWdl"]["aggregate"]["actual_side_wins"],
            5,
        )
        self.assertEqual(
            payload["rows"][0]["tablebaseWdl"]["resultCrosstab"]["aligned"]["count"],
            6,
        )
        self.assertIsNone(payload["rows"][2]["tablebaseWdl"])
        self.assertEqual(
            [row["stem"] for row in payload["rows"]],
            [ending.stem for ending in FCE_CATALOG.endings],
        )


if __name__ == "__main__":
    unittest.main()
