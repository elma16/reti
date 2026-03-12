from __future__ import annotations

import csv
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import chess
import chess.syzygy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _DummyProgress:
    def __init__(self, iterable=None, **_: object) -> None:
        self.iterable = iterable

    def __iter__(self):
        if self.iterable is None:
            return iter(())
        return iter(self.iterable)

    def update(self, _: int = 1) -> None:
        return None

    def set_postfix_str(self, _: str) -> None:
        return None

    def close(self) -> None:
        return None


def _dummy_tqdm(iterable=None, **kwargs):
    return _DummyProgress(iterable=iterable, **kwargs)


_dummy_tqdm.write = lambda message: None
sys.modules.setdefault("tqdm", types.SimpleNamespace(tqdm=_dummy_tqdm))

import reti.export_cql_positions as export_cql_positions


class _FakeTablebase:
    def __init__(self, *, wdl: int = 2, dtz: int = 11, error: Exception | None = None):
        self.wdl = wdl
        self.dtz = dtz
        self.error = error
        self.closed = False

    def probe_wdl(self, board: chess.Board) -> int:
        _ = board
        if self.error is not None:
            raise self.error
        return self.wdl

    def probe_dtz(self, board: chess.Board) -> int:
        _ = board
        if self.error is not None:
            raise self.error
        return self.dtz

    def close(self) -> None:
        self.closed = True


class _FakeStockfishSession:
    def __init__(self, binary: str | None, threads: int) -> None:
        self.binary = binary
        self.threads = threads
        self.closed = False

    def analyse(
        self,
        board: chess.Board,
        *,
        sf_time_seconds: float,
        draw_threshold_cp: int,
    ) -> export_cql_positions.EvaluationResult:
        _ = board
        cp_white = 65
        return export_cql_positions.EvaluationResult(
            eval_source="stockfish",
            winning_side=export_cql_positions.classify_stockfish_winner(
                cp_white, None, draw_threshold_cp
            ),
            sf_cp_white=cp_white,
            sf_mate_white=None,
            sf_time_seconds=sf_time_seconds,
            draw_threshold_cp=draw_threshold_cp,
            eval_status="ok",
        )

    def close(self) -> None:
        self.closed = True


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestExportCqlPositions(unittest.TestCase):
    def test_parse_args_accepts_explicit_flags(self):
        args = export_cql_positions.parse_args(
            [
                "--pgn",
                "games",
                "--output-csv",
                "out.csv",
                "--marker-text",
                "SPECIAL",
                "--syzygy-dir",
                "/tb1",
                "--syzygy-dir",
                "/tb2",
                "--stockfish-bin",
                "stockfish",
                "--sf-time-seconds",
                "2.5",
                "--sf-threads",
                "3",
                "--draw-threshold-cp",
                "45",
            ]
        )

        self.assertEqual(args.pgn_location, "games")
        self.assertEqual(args.output_csv, "out.csv")
        self.assertEqual(args.marker_text, "SPECIAL")
        self.assertEqual(args.syzygy_dirs, ["/tb1", "/tb2"])
        self.assertEqual(args.stockfish_bin, "stockfish")
        self.assertEqual(args.sf_time_seconds, 2.5)
        self.assertEqual(args.sf_threads, 3)
        self.assertEqual(args.draw_threshold_cp, 45)

    def test_classify_stockfish_winner_uses_draw_band_and_mate_scores(self):
        self.assertEqual(
            export_cql_positions.classify_stockfish_winner(20, None, 30),
            "draw",
        )
        self.assertEqual(
            export_cql_positions.classify_stockfish_winner(65, None, 30),
            "white",
        )
        self.assertEqual(
            export_cql_positions.classify_stockfish_winner(-80, None, 30),
            "black",
        )
        self.assertEqual(
            export_cql_positions.classify_stockfish_winner(None, 4, 30),
            "white",
        )
        self.assertEqual(
            export_cql_positions.classify_stockfish_winner(None, -2, 30),
            "black",
        )

    def test_main_exports_marker_rows_from_directory_and_appends_to_matching_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_root = root / "pgns"
            csv_path = root / "positions.csv"

            _write_text(
                pgn_root / "alpha.pgn",
                '[Event "Alpha"]\n'
                '[Site "X"]\n'
                '[Date "2026.03.11"]\n'
                '[Round "1"]\n'
                '[White "A"]\n'
                '[Black "B"]\n'
                '[Result "*"]\n'
                '[SetUp "1"]\n'
                '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
                "\n"
                "1. Kd2 {CQL} Kh1 {not CQL} *\n",
            )
            _write_text(
                pgn_root / "nested" / "beta.pgn",
                '[Event "Beta"]\n'
                '[Result "*"]\n'
                '[SetUp "1"]\n'
                '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
                "\n"
                "1. Kd2 {CQL} *\n",
            )

            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=export_cql_positions.CSV_COLUMNS)
                writer.writeheader()
                writer.writerow(
                    export_cql_positions.empty_row(
                        source_pgn="existing.pgn",
                        ending="existing",
                        marker_text="CQL",
                        eval_status="ok",
                    )
                )

            with mock.patch.object(
                export_cql_positions,
                "open_tablebase_from_directories",
                return_value=(_FakeTablebase(wdl=2, dtz=7), None),
            ):
                exit_code = export_cql_positions.main(
                    [
                        "--pgn",
                        str(pgn_root),
                        "--output-csv",
                        str(csv_path),
                        "--syzygy-dir",
                        "/fake/syzygy",
                    ]
                )

            self.assertEqual(exit_code, 0)
            rows = _read_rows(csv_path)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[1]["source_pgn"], "alpha.pgn")
            self.assertEqual(rows[1]["ending"], "alpha")
            self.assertEqual(rows[1]["event"], "Alpha")
            self.assertEqual(rows[1]["eval_source"], "tablebase")
            self.assertEqual(rows[1]["winning_side"], "black")
            self.assertEqual(rows[1]["tb_wdl"], "2")
            self.assertEqual(rows[2]["source_pgn"], "nested/beta.pgn")
            self.assertEqual(rows[2]["ending"], "beta")

    def test_main_preserves_duplicate_fens_as_separate_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_path = root / "dupes.pgn"
            csv_path = root / "positions.csv"

            _write_text(
                pgn_path,
                '[Event "One"]\n'
                '[Result "*"]\n'
                '[SetUp "1"]\n'
                '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
                "\n"
                "1. Kd2 {CQL} *\n"
                "\n"
                '[Event "Two"]\n'
                '[Result "*"]\n'
                '[SetUp "1"]\n'
                '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
                "\n"
                "1. Kd2 {CQL} *\n",
            )

            with mock.patch.object(
                export_cql_positions,
                "open_tablebase_from_directories",
                return_value=(_FakeTablebase(wdl=0, dtz=0), None),
            ):
                exit_code = export_cql_positions.main(
                    [
                        "--pgn",
                        str(pgn_path),
                        "--output-csv",
                        str(csv_path),
                        "--syzygy-dir",
                        "/fake/syzygy",
                    ]
                )

            self.assertEqual(exit_code, 0)
            rows = _read_rows(csv_path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["fen"], rows[1]["fen"])
            self.assertEqual(rows[0]["game_index"], "1")
            self.assertEqual(rows[1]["game_index"], "2")

    def test_marker_text_matches_exact_stripped_comment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_path = root / "special.pgn"
            csv_path = root / "positions.csv"

            _write_text(
                pgn_path,
                '[Event "Special"]\n'
                '[Result "*"]\n'
                '[SetUp "1"]\n'
                '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
                "\n"
                "1. Kd2 {SPECIAL extra} Kh1 { SPECIAL } *\n",
            )

            with mock.patch.object(
                export_cql_positions,
                "open_tablebase_from_directories",
                return_value=(_FakeTablebase(wdl=0, dtz=0), None),
            ):
                exit_code = export_cql_positions.main(
                    [
                        "--pgn",
                        str(pgn_path),
                        "--output-csv",
                        str(csv_path),
                        "--syzygy-dir",
                        "/fake/syzygy",
                        "--marker-text",
                        "SPECIAL",
                    ]
                )

            self.assertEqual(exit_code, 0)
            rows = _read_rows(csv_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["move_san"], "Kh1")
            self.assertEqual(rows[0]["marker_text"], "SPECIAL")

    def test_header_mismatch_aborts_before_processing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_path = root / "single.pgn"
            csv_path = root / "positions.csv"
            _write_text(
                pgn_path,
                '[Event "X"]\n'
                '[Result "*"]\n'
                '[SetUp "1"]\n'
                '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
                "\n"
                "1. Kd2 {CQL} *\n",
            )
            csv_path.write_text("wrong,header\n", encoding="utf-8")

            exit_code = export_cql_positions.main(
                ["--pgn", str(pgn_path), "--output-csv", str(csv_path)]
            )

            self.assertEqual(exit_code, 1)
            self.assertEqual(csv_path.read_text(encoding="utf-8"), "wrong,header\n")

    def test_missing_stockfish_for_more_than_five_pieces_writes_error_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_path = root / "opening.pgn"
            csv_path = root / "positions.csv"

            _write_text(
                pgn_path,
                '[Event "Opening"]\n'
                '[Result "*"]\n'
                "\n"
                "1. e4 {CQL} *\n",
            )

            exit_code = export_cql_positions.main(
                ["--pgn", str(pgn_path), "--output-csv", str(csv_path)]
            )

            self.assertEqual(exit_code, 1)
            rows = _read_rows(csv_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["eval_source"], "stockfish")
            self.assertEqual(rows[0]["eval_status"], "stockfish_error")
            self.assertIn("pass --stockfish-bin", rows[0]["error_message"])

    def test_unprobeable_tablebase_writes_error_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_path = root / "tb.pgn"
            csv_path = root / "positions.csv"

            _write_text(
                pgn_path,
                '[Event "TB"]\n'
                '[Result "*"]\n'
                '[SetUp "1"]\n'
                '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
                "\n"
                "1. Kd2 {CQL} *\n",
            )

            with mock.patch.object(
                export_cql_positions,
                "open_tablebase_from_directories",
                return_value=(
                    _FakeTablebase(
                        error=chess.syzygy.MissingTableError("missing table")
                    ),
                    None,
                ),
            ):
                exit_code = export_cql_positions.main(
                    [
                        "--pgn",
                        str(pgn_path),
                        "--output-csv",
                        str(csv_path),
                        "--syzygy-dir",
                        "/fake/syzygy",
                    ]
                )

            self.assertEqual(exit_code, 1)
            rows = _read_rows(csv_path)
            self.assertEqual(rows[0]["eval_source"], "tablebase")
            self.assertEqual(rows[0]["eval_status"], "tablebase_error")
            self.assertIn("missing table", rows[0]["error_message"])

    def test_stockfish_rows_include_raw_scores(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_path = root / "stockfish.pgn"
            csv_path = root / "positions.csv"

            _write_text(
                pgn_path,
                '[Event "Opening"]\n'
                '[Result "*"]\n'
                "\n"
                "1. e4 {CQL} *\n",
            )

            with mock.patch.object(
                export_cql_positions,
                "StockfishSession",
                _FakeStockfishSession,
            ):
                exit_code = export_cql_positions.main(
                    [
                        "--pgn",
                        str(pgn_path),
                        "--output-csv",
                        str(csv_path),
                        "--stockfish-bin",
                        "stockfish",
                        "--sf-time-seconds",
                        "1.5",
                        "--draw-threshold-cp",
                        "30",
                    ]
                )

            self.assertEqual(exit_code, 0)
            rows = _read_rows(csv_path)
            self.assertEqual(rows[0]["eval_source"], "stockfish")
            self.assertEqual(rows[0]["sf_cp_white"], "65")
            self.assertEqual(rows[0]["sf_time_seconds"], "1.5")
            self.assertEqual(rows[0]["draw_threshold_cp"], "30")
            self.assertEqual(rows[0]["winning_side"], "white")


if __name__ == "__main__":
    unittest.main()
