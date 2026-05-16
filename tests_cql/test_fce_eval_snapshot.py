from __future__ import annotations

import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

CHESS_AVAILABLE = importlib.util.find_spec("chess") is not None
if CHESS_AVAILABLE:
    import chess

    from reti.fce_eval_snapshot import (
        EvalSettings,
        classify_material_side,
        init_schema,
        mark_tablebase_skips,
        normalize_marker_row,
        refresh_aggregates,
    )
else:
    EvalSettings = None
    chess = None
    classify_material_side = None
    init_schema = None
    mark_tablebase_skips = None
    normalize_marker_row = None
    refresh_aggregates = None


@unittest.skipIf(not CHESS_AVAILABLE, "python-chess is not installed in this environment")
class MaterialSideTests(unittest.TestCase):
    def test_queen_vs_rook_is_attributed_to_queen_side(self) -> None:
        board = chess.Board("8/8/8/8/8/2k5/8/3QK2r w - - 0 1")
        perspective = classify_material_side("10-2Qr", board)
        self.assertEqual(perspective.material_side, "white")
        self.assertEqual(perspective.material_label, "queen side")

        board = chess.Board("3qk2R/8/2K5/8/8/8/8/8 w - - 0 1")
        perspective = classify_material_side("10-2Qr", board)
        self.assertEqual(perspective.material_side, "black")

    def test_bishop_knight_mate_row_is_attributed_to_bn_side(self) -> None:
        board = chess.Board("8/8/8/8/8/2k5/3NB3/4K3 w - - 0 1")
        perspective = classify_material_side("1-4BN", board)
        self.assertEqual(perspective.material_side, "white")
        self.assertEqual(perspective.material_label, "bishop+knight side")

    def test_symmetric_rows_are_not_forced_onto_a_colour(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/8/3QK2q w - - 0 1")
        perspective = classify_material_side("9-2Qq", board)
        self.assertEqual(perspective.material_side, "symmetric")


@unittest.skipIf(not CHESS_AVAILABLE, "python-chess is not installed in this environment")
class AggregateTests(unittest.TestCase):
    def test_legacy_tablebase_jsonl_row_normalizes(self) -> None:
        row = normalize_marker_row(
            {
                "stem": "1-4BN",
                "output_pgn": "Bucket/1-4BN.pgn",
                "source_pgn": "Bucket.pgn",
                "game_index": 7,
                "headers": {
                    "Event": "event",
                    "White": "w",
                    "Black": "b",
                    "Result": "1-0",
                },
                "ply": 117,
                "fullmove": 59,
                "move_san": "Kxg5",
                "move_uci": "g4g5",
                "fen": "7k/8/8/5BKN/8/8/8/8 b - - 0 59",
                "side_to_move": "black",
                "piece_count": 4,
            },
            line_number=1,
            path=Path("legacy.jsonl"),
        )
        self.assertEqual(row["ending"], "1-4BN")
        self.assertEqual(row["source_bucket"], "Bucket")
        self.assertEqual(row["ply_index"], 117)
        self.assertEqual(row["event"], "event")

    def test_tablebase_only_marks_larger_positions_as_skipped(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.execute(
            """
            INSERT INTO evaluations(eval_key, fen, piece_count, eval_status)
            VALUES ('small', 'fen', 5, 'pending'),
                   ('large', 'fen', 6, 'pending')
            """
        )
        settings = EvalSettings(
            markers_jsonl=Path("markers.jsonl"),
            output_db=Path("out.sqlite3"),
            syzygy_dirs=(),
            stockfish_bin=None,
            tablebase_only=True,
        )
        skipped = mark_tablebase_skips(conn, settings)
        self.assertEqual(skipped, 1)
        large = conn.execute(
            "SELECT eval_status FROM evaluations WHERE eval_key = 'large'"
        ).fetchone()
        small = conn.execute(
            "SELECT eval_status FROM evaluations WHERE eval_key = 'small'"
        ).fetchone()
        self.assertEqual(large["eval_status"], "skipped_non_tablebase")
        self.assertEqual(small["eval_status"], "pending")

    def test_refresh_aggregates_counts_material_side_wdl(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        self.add_position(
            conn,
            "p1",
            "1-4BN",
            "white",
            "bishop+knight side",
            "e1",
            result="1-0",
        )
        self.add_eval(conn, "e1", "white")
        self.add_position(
            conn,
            "p2",
            "1-4BN",
            "black",
            "bishop+knight side",
            "e2",
            result="1-0",
        )
        self.add_eval(conn, "e2", "white")
        self.add_position(
            conn,
            "p3",
            "1-4BN",
            "white",
            "bishop+knight side",
            "e3",
            result="1/2-1/2",
        )
        self.add_eval(conn, "e3", "draw")

        rows = refresh_aggregates(conn)
        self.assertEqual(rows, 1)
        row = conn.execute("SELECT * FROM ending_wdl WHERE ending = '1-4BN'").fetchone()
        self.assertEqual(row["total_positions"], 3)
        self.assertEqual(row["side_wins"], 1)
        self.assertEqual(row["side_losses"], 1)
        self.assertEqual(row["side_draws"], 1)
        self.assertEqual(row["tablebase_eligible_positions"], 3)
        self.assertEqual(row["tablebase_positions"], 3)
        self.assertEqual(row["actual_side_wins"], 1)
        self.assertEqual(row["actual_side_losses"], 1)
        self.assertEqual(row["actual_side_draws"], 1)
        self.assertEqual(row["tb_win_result_win"], 1)
        self.assertEqual(row["tb_draw_result_draw"], 1)
        self.assertEqual(row["tb_loss_result_loss"], 1)

    @staticmethod
    def add_position(
        conn: sqlite3.Connection,
        position_key: str,
        ending: str,
        material_side: str,
        material_label: str,
        eval_key: str,
        *,
        result: str = "*",
    ) -> None:
        conn.execute(
            """
            INSERT INTO positions (
                position_key, source_pgn, source_bucket, ending, output_pgn,
                game_index, marker_index, marker_text, game_key,
                event, site, date, round, white, black, result,
                ply_index, fullmove_number, move_san, move_uci, fen,
                side_to_move, piece_count, material_side, material_label,
                material_signature, eval_key
            ) VALUES (
                ?, 'source.pgn', 'source', ?, 'source/ending.pgn',
                1, 1, 'CQL', 'game',
                '', '', '', '', '', '', ?,
                1, 1, 'e4', 'e2e4', '8/8/8/8/8/2k5/8/3QK2r w - - 0 1',
                'white', 4, ?, ?, 'QvR', ?
            )
            """,
            (position_key, ending, result, material_side, material_label, eval_key),
        )

    @staticmethod
    def add_eval(conn: sqlite3.Connection, eval_key: str, winning_side: str) -> None:
        conn.execute(
            """
            INSERT INTO evaluations (
                eval_key, fen, piece_count, eval_source, winning_side, eval_status
            ) VALUES (?, 'fen', 4, 'tablebase', ?, 'ok')
            """,
            (eval_key, winning_side),
        )


if __name__ == "__main__":
    unittest.main()
