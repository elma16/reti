from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

CHESS_AVAILABLE = importlib.util.find_spec("chess") is not None

if CHESS_AVAILABLE:
    from reti.fce_combined_tablebase_snapshot import (
        attach_threshold_views,
        incidence_for_view_threshold,
        ingest_facts,
        init_schema,
        parse_thresholds,
        refresh_threshold_aggregates,
    )
    from reti.fce_eval_snapshot import profile_id
    from reti.fce_snapshot import render_snapshot_html


@unittest.skipIf(not CHESS_AVAILABLE, "python-chess is not installed in this environment")
class CombinedTablebaseSnapshotTests(unittest.TestCase):
    def test_thresholds_must_include_one(self) -> None:
        self.assertEqual(parse_thresholds("1,2,5,10,20"), (1, 2, 5, 10, 20))
        with self.assertRaises(Exception):
            parse_thresholds("2,5")

    def test_threshold_aggregates_filter_incidence_and_tablebase_positions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            facts = root / "facts.jsonl"
            self.write_facts(facts)
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            init_schema(conn)
            profile = profile_id({"evaluation": {"tablebase": "fixture"}})
            game_stems, positions = ingest_facts(
                conn,
                facts,
                known_stems={"1-4BN"},
                profile=profile,
                tablebase_threshold=5,
            )
            self.assertEqual(game_stems, 2)
            self.assertEqual(positions, 3)
            conn.execute(
                """
                UPDATE evaluations
                SET eval_source = 'tablebase',
                    winning_side = 'white',
                    eval_status = 'ok'
                """
            )
            refresh_threshold_aggregates(conn, thresholds=(1, 2, 5), tablebase_threshold=5)

            all_t1 = incidence_for_view_threshold(
                conn, view_key="all", threshold=1, total_games=3
            )
            self.assertEqual(all_t1["matchedRows"], 2)
            self.assertEqual(all_t1["rows"]["1-4BN"]["quantity"], 2)
            otb_t2 = incidence_for_view_threshold(
                conn, view_key="otb", threshold=2, total_games=2
            )
            self.assertEqual(otb_t2["matchedRows"], 1)
            online_t2 = incidence_for_view_threshold(
                conn, view_key="online", threshold=2, total_games=1
            )
            self.assertEqual(online_t2["matchedRows"], 0)

            row = conn.execute(
                """
                SELECT *
                FROM aggregate_wdl
                WHERE view_key = 'all' AND threshold = 1 AND ending = '1-4BN'
                """
            ).fetchone()
            self.assertEqual(row["evaluated_positions"], 3)
            self.assertEqual(row["side_wins"], 3)
            self.assertEqual(row["actual_side_wins"], 2)
            self.assertEqual(row["actual_side_losses"], 1)
            self.assertEqual(row["tb_win_result_loss"], 1)

            row = conn.execute(
                """
                SELECT *
                FROM aggregate_wdl
                WHERE view_key = 'otb' AND threshold = 2 AND ending = '1-4BN'
                """
            ).fetchone()
            self.assertEqual(row["evaluated_positions"], 2)

    def test_renderer_embeds_precomputed_threshold_tablebase_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            facts = root / "facts.jsonl"
            self.write_facts(facts)
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            init_schema(conn)
            profile = profile_id({"evaluation": {"tablebase": "fixture"}})
            ingest_facts(
                conn,
                facts,
                known_stems={"1-4BN"},
                profile=profile,
                tablebase_threshold=5,
            )
            conn.execute(
                """
                UPDATE evaluations
                SET eval_source = 'tablebase',
                    winning_side = 'white',
                    eval_status = 'ok'
                """
            )
            refresh_threshold_aggregates(conn, thresholds=(1, 2), tablebase_threshold=5)
            snapshot = self.minimal_snapshot()
            attach_threshold_views(
                snapshot,
                conn,
                thresholds=(1, 2),
                aggregate_csv=root / "aggregate.csv",
            )
            html = render_snapshot_html(snapshot)
            self.assertIn('"thresholds"', html)
            self.assertIn('"tablebasePositions":3', html)
            self.assertIn('"tablebasePositions":2', html)
            self.assertIn("updateTablebaseCells", html)
            self.assertIn("data-dataset-view=\"online\"", html)

    @staticmethod
    def write_facts(path: Path) -> None:
        board_fen = "8/8/8/8/8/2k5/3NB3/4K3 w - - 0 1"
        rows = [
            {
                "schema_version": 1,
                "kind": "game_stem",
                "source_pgn": "LumbrasGigaBase_OTB_2025.pgn",
                "source_group": "otb",
                "source_bucket": "LumbrasGigaBase_OTB_2025",
                "output_pgn": "LumbrasGigaBase_OTB_2025/fce-table-markers.pgn",
                "game_index": 1,
                "game_key": "otb-game",
                "event": "otb",
                "site": "?",
                "date": "2026.05.15",
                "round": "?",
                "white": "W",
                "black": "B",
                "result": "1-0",
                "stem": "1-4BN",
                "max_run_length": 2,
                "position_count": 2,
            },
            {
                "schema_version": 1,
                "kind": "position",
                "source_pgn": "LumbrasGigaBase_OTB_2025.pgn",
                "source_group": "otb",
                "source_bucket": "LumbrasGigaBase_OTB_2025",
                "output_pgn": "LumbrasGigaBase_OTB_2025/fce-table-markers.pgn",
                "game_index": 1,
                "game_key": "otb-game",
                "event": "otb",
                "site": "?",
                "date": "2026.05.15",
                "round": "?",
                "white": "W",
                "black": "B",
                "result": "1-0",
                "stem": "1-4BN",
                "marker_index": 1,
                "ply_index": 70,
                "fullmove_number": 35,
                "move_san": "Ke2",
                "move_uci": "e1e2",
                "fen": board_fen,
                "side_to_move": "white",
                "piece_count": 4,
                "run_length": 2,
                "run_start_ply": 70,
                "run_end_ply": 71,
            },
            {
                "schema_version": 1,
                "kind": "position",
                "source_pgn": "LumbrasGigaBase_OTB_2025.pgn",
                "source_group": "otb",
                "source_bucket": "LumbrasGigaBase_OTB_2025",
                "output_pgn": "LumbrasGigaBase_OTB_2025/fce-table-markers.pgn",
                "game_index": 1,
                "game_key": "otb-game",
                "event": "otb",
                "site": "?",
                "date": "2026.05.15",
                "round": "?",
                "white": "W",
                "black": "B",
                "result": "1-0",
                "stem": "1-4BN",
                "marker_index": 2,
                "ply_index": 71,
                "fullmove_number": 36,
                "move_san": "Kd4",
                "move_uci": "c3d4",
                "fen": board_fen,
                "side_to_move": "white",
                "piece_count": 4,
                "run_length": 2,
                "run_start_ply": 70,
                "run_end_ply": 71,
            },
            {
                "schema_version": 1,
                "kind": "game_stem",
                "source_pgn": "LumbrasGigaBase_Online_2025.pgn",
                "source_group": "online",
                "source_bucket": "LumbrasGigaBase_Online_2025",
                "output_pgn": "LumbrasGigaBase_Online_2025/fce-table-markers.pgn",
                "game_index": 1,
                "game_key": "online-game",
                "event": "online",
                "site": "?",
                "date": "2026.05.15",
                "round": "?",
                "white": "W",
                "black": "B",
                "result": "0-1",
                "stem": "1-4BN",
                "max_run_length": 1,
                "position_count": 1,
            },
            {
                "schema_version": 1,
                "kind": "position",
                "source_pgn": "LumbrasGigaBase_Online_2025.pgn",
                "source_group": "online",
                "source_bucket": "LumbrasGigaBase_Online_2025",
                "output_pgn": "LumbrasGigaBase_Online_2025/fce-table-markers.pgn",
                "game_index": 1,
                "game_key": "online-game",
                "event": "online",
                "site": "?",
                "date": "2026.05.15",
                "round": "?",
                "white": "W",
                "black": "B",
                "result": "0-1",
                "stem": "1-4BN",
                "marker_index": 1,
                "ply_index": 80,
                "fullmove_number": 40,
                "move_san": "Ke2",
                "move_uci": "e1e2",
                "fen": board_fen,
                "side_to_move": "white",
                "piece_count": 4,
                "run_length": 1,
                "run_start_ply": 80,
                "run_end_ply": 80,
            },
        ]
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    @staticmethod
    def minimal_snapshot() -> dict:
        return {
            "schemaVersion": 1,
            "snapshotId": "fixture",
            "generatedAt": "2026-05-15T00:00:00+00:00",
            "title": "Fixture",
            "corpus": {
                "name": "fixture",
                "source": "fixture",
                "totalGames": 3,
                "sourceBucketCount": 2,
                "sourceGroups": ["otb", "online"],
                "exactness": "exact",
            },
            "inputs": {},
            "catalog": {"name": "fce", "chapters": [], "rows": []},
            "totals": {
                "summaryRows": 2,
                "sourceBuckets": 2,
                "endingRows": 1,
                "matchedGames": 2,
                "matchedRows": 2,
                "exactness": "exact",
            },
            "sourceBuckets": [
                {
                    "sourcePgn": "LumbrasGigaBase_OTB_2025.pgn",
                    "sourceStem": "LumbrasGigaBase_OTB_2025",
                    "sourceGroup": "otb",
                    "bucket": "otb:2025",
                    "displayLabel": "OTB 2025",
                    "sortIndex": 0,
                    "originalGameCount": 2,
                    "matchedGames": 1,
                    "matchTotal": 1,
                    "file": {"sizeBytes": 0},
                    "annotatedFile": {"sizeBytes": 0},
                    "exactness": "exact",
                },
                {
                    "sourcePgn": "LumbrasGigaBase_Online_2025.pgn",
                    "sourceStem": "LumbrasGigaBase_Online_2025",
                    "sourceGroup": "online",
                    "bucket": "online:2025",
                    "displayLabel": "Online 2025",
                    "sortIndex": 1,
                    "originalGameCount": 1,
                    "matchedGames": 1,
                    "matchTotal": 1,
                    "file": {"sizeBytes": 0},
                    "annotatedFile": {"sizeBytes": 0},
                    "exactness": "exact",
                },
            ],
            "datasetViews": {
                "default": "all",
                "views": {
                    key: {
                        "key": key,
                        "label": label,
                        "shortLabel": label,
                        "description": label,
                        "totalGames": total,
                        "matchedGames": matched,
                        "matchedRows": matched,
                        "sourceBuckets": buckets,
                        "sourcePgns": sources,
                        "rows": {
                            "1-4BN": {
                                "quantity": matched,
                                "percentage": matched / total * 100.0,
                                "matchedShare": 100.0,
                                "runLengthHistogram": {"1": 1},
                            }
                        },
                    }
                    for key, label, total, matched, buckets, sources in [
                        (
                            "all",
                            "All",
                            3,
                            2,
                            2,
                            [
                                "LumbrasGigaBase_OTB_2025.pgn",
                                "LumbrasGigaBase_Online_2025.pgn",
                            ],
                        ),
                        ("otb", "OTB", 2, 1, 1, ["LumbrasGigaBase_OTB_2025.pgn"]),
                        (
                            "online",
                            "Online",
                            1,
                            1,
                            1,
                            ["LumbrasGigaBase_Online_2025.pgn"],
                        ),
                    ]
                },
            },
            "rows": [
                {
                    "stem": "1-4BN",
                    "sortIndex": 1,
                    "rowId": "1.4",
                    "label": "Bishop + Knight vs King",
                    "displayLabel": "Bishop + Knight vs King",
                    "chapterKey": "1",
                    "chapter": "Minor Pieces vs King",
                    "color": "#4E79A7",
                    "quantity": 2,
                    "percentage": 66.666,
                    "matchedShare": 100.0,
                    "sourceCounts": {
                        "LumbrasGigaBase_OTB_2025.pgn": 1,
                        "LumbrasGigaBase_Online_2025.pgn": 1,
                    },
                }
            ],
            "methodology": {
                "countingSemantics": "per-ending game incidence",
                "combinedComments": True,
                "runLengthThresholds": True,
            },
        }


if __name__ == "__main__":
    unittest.main()
