from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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

import reti.repair_pgn as repair_pgn


class TestRepairPgn(unittest.TestCase):
    def test_repair_in_place_creates_backup_and_removes_bad_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "bad.pgn"
            original_bytes = b'\xef\xbb\xbf[Event "x"]\n\n1. e4 e5 \x1f*\n'
            pgn.write_bytes(original_bytes)

            result = repair_pgn.repair_pgn_file_in_place(pgn)

            self.assertIsNotNone(result.backup_path)
            assert result.backup_path is not None
            self.assertEqual(result.backup_path.read_bytes(), original_bytes)
            repaired_text = pgn.read_text(encoding="utf-8")
            self.assertNotIn("\ufeff", repaired_text)
            self.assertNotIn("\x1f", repaired_text)
            self.assertIn('[Event "x"]', repaired_text)
            self.assertEqual(result.normalization.games_written, 1)
            self.assertTrue(result.sanitization.removed_bom)
            self.assertEqual(result.sanitization.control_characters_removed, 1)
            self.assertNotIn("{", repaired_text)

    @mock.patch("reti.repair_pgn.subprocess.run")
    def test_repair_smoke_tests_before_replacing_original(self, run_mock):
        run_mock.return_value = mock.Mock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "comment-bad.pgn"
            original_text = (
                '[Event "x"]\n\n'
                "1. e4 { broken comment\n"
                "2. e5 *\n"
            )
            pgn.write_text(original_text, encoding="utf-8")

            result = repair_pgn.repair_pgn_file_in_place(
                pgn,
                backup_suffix=None,
                cql_binary=Path("/fake/cql"),
            )

            repaired_text = pgn.read_text(encoding="utf-8")
            self.assertNotIn("broken comment", repaired_text)
            self.assertNotIn("{", repaired_text)
            self.assertNotIn("(", repaired_text)
            self.assertIn("1. e4", repaired_text)
            self.assertIn("*", repaired_text)
            self.assertEqual(result.smoke_test_message, "CQL smoke test passed")
            run_args = run_mock.call_args.args[0]
            self.assertEqual(run_args[0], "/fake/cql")
            self.assertEqual(run_args[1], "-lineincrement")
            self.assertEqual(run_args[2], "1000")
            self.assertEqual(run_args[3], "-input")
            self.assertTrue(run_args[4].endswith("repaired.pgn"))

    def test_repair_drops_comments_and_side_variations_for_cql_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "annotated.pgn"
            pgn.write_text(
                '[Event "x"]\n\n'
                "1. e4 { note with brace { inside } e5 ( 1... c5 ) 2. Nf3 *\n",
                encoding="utf-8",
            )

            repair_pgn.repair_pgn_file_in_place(pgn, backup_suffix=None)

            repaired_text = pgn.read_text(encoding="utf-8")
            self.assertNotIn("{", repaired_text)
            self.assertNotIn("(", repaired_text)
            self.assertIn("1. e4 e5 2. Nf3 *", repaired_text)

    def test_main_rejects_non_pgn_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "not-pgn.txt"
            path.write_text("x", encoding="utf-8")
            exit_code = repair_pgn.main(["--pgn", str(path)])

        self.assertEqual(exit_code, 1)

    def test_main_rejects_non_positive_cql_lineincrement(self):
        exit_code = repair_pgn.main(["--pgn", "missing.pgn", "--cql-lineincrement", "0"])
        self.assertEqual(exit_code, 1)

    def test_main_repairs_directory_of_pgns_recursively(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "nested"
            nested.mkdir()

            first = root / "first.pgn"
            second = nested / "second.pgn"
            ignored = nested / "notes.txt"

            first.write_bytes(b'\xef\xbb\xbf[Event "a"]\n\n1. e4 e5 \x1f*\n')
            second.write_text(
                '[Event "b"]\n\n'
                "1. d4 { note with brace { inside } d5 ( 1... Nf6 ) 2. c4 *\n",
                encoding="utf-8",
            )
            ignored.write_text("not a pgn", encoding="utf-8")

            exit_code = repair_pgn.main(["--pgn", str(root), "--no-backup"])

            self.assertEqual(exit_code, 0)
            first_text = first.read_text(encoding="utf-8")
            second_text = second.read_text(encoding="utf-8")
            self.assertNotIn("\ufeff", first_text)
            self.assertNotIn("\x1f", first_text)
            self.assertIn('[Event "a"]', first_text)
            self.assertNotIn("{", second_text)
            self.assertNotIn("(", second_text)
            self.assertIn("1. d4 d5 2. c4 *", second_text)
            self.assertEqual(ignored.read_text(encoding="utf-8"), "not a pgn")


if __name__ == "__main__":
    unittest.main()
