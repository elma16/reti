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

import reti.pgn_utils as pgn_utils
import reti.pgn_cli as pgn_cli


def _python_fast_patch():
    return mock.patch("reti.pgn_utils.find_pgn_utils_binary", return_value=None)


class TestRepairPgn(unittest.TestCase):
    def test_fast_repair_in_place_creates_backup_and_removes_bad_bytes(self):
        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "bad.pgn"
            original_bytes = b'\xef\xbb\xbf[Event "x"]\n\n1. e4 e5 \x1f*\n'
            pgn.write_bytes(original_bytes)

            result = pgn_cli.repair_pgn_file_in_place(pgn)

            self.assertIsNotNone(result.backup_path)
            assert result.backup_path is not None
            self.assertEqual(result.backup_path.read_bytes(), original_bytes)
            repaired_text = pgn.read_text(encoding="utf-8")
            self.assertNotIn("\ufeff", repaired_text)
            self.assertNotIn("\x1f", repaired_text)
            self.assertIn('[Event "x"]', repaired_text)
            self.assertIn("1. e4 e5 *", repaired_text)
            self.assertEqual(result.normalization.games_written, 1)
            self.assertEqual(result.normalization.mode, pgn_cli.FAST_REPAIR_MODE)
            self.assertFalse(result.normalization.used_native_accelerator)
            self.assertTrue(result.sanitization.removed_bom)
            self.assertEqual(result.sanitization.control_characters_removed, 1)

    @mock.patch("reti.pgn_cli.subprocess.run")
    def test_repair_smoke_tests_before_replacing_original(self, run_mock):
        run_mock.return_value = mock.Mock(returncode=0)

        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "comment-bad.pgn"
            original_text = (
                '[Event "x"]\n\n'
                "1. e4 { broken comment\n"
                "2. e5 *\n"
            )
            pgn.write_text(original_text, encoding="utf-8")

            result = pgn_cli.repair_pgn_file_in_place(
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

    def test_fast_repair_drops_comments_and_side_variations_for_cql_safety(self):
        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "annotated.pgn"
            pgn.write_text(
                '[Event "x"]\n\n'
                "1. e4 { note with brace { inside } e5 ( 1... c5 ) 2. Nf3 *\n",
                encoding="utf-8",
            )

            result = pgn_cli.repair_pgn_file_in_place(pgn, backup_suffix=None)

            repaired_text = pgn.read_text(encoding="utf-8")
            self.assertNotIn("{", repaired_text)
            self.assertNotIn("(", repaired_text)
            self.assertIn("1. e4 e5 2. Nf3 *", repaired_text)
            self.assertGreater(result.normalization.comments_removed, 0)
            self.assertGreater(result.normalization.variations_removed, 0)

    def test_fast_repair_preserves_parentheses_in_header_values(self):
        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "header-parens.pgn"
            repaired = root / "repaired.pgn"
            source.write_text(
                '[Event "047.San Remo (E.V.)"]\n'
                '[Site "San Remo ITA"]\n'
                "\n"
                "1. e4 ( 1... c5 ) e5 *\n",
                encoding="utf-8",
            )

            stats = pgn_utils.rewrite_pgn_fast_python(source, repaired)
            repaired_text = repaired.read_text(encoding="utf-8")

            self.assertIn('[Event "047.San Remo (E.V.)"]', repaired_text)
            self.assertNotIn("( 1... c5 )", repaired_text)
            self.assertEqual(stats.variations_removed, 1)

    def test_fast_repair_strips_percent_and_semicolon_line_comments(self):
        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "line-comments.pgn"
            pgn.write_text(
                '[Event "x"]\n\n'
                "% top comment\n"
                "1. e4 e5 ; trailing note\n"
                "; whole line\n"
                "2. Nf3 *\n",
                encoding="utf-8",
            )

            result = pgn_cli.repair_pgn_file_in_place(pgn, backup_suffix=None)
            repaired_text = pgn.read_text(encoding="utf-8")

            self.assertNotIn("top comment", repaired_text)
            self.assertNotIn("trailing note", repaired_text)
            self.assertIn("1. e4 e5", repaired_text)
            self.assertIn("2. Nf3 *", repaired_text)
            self.assertEqual(result.normalization.line_comments_removed, 3)

    def test_fast_repair_recovers_at_blank_line_before_next_header(self):
        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "recover.pgn"
            pgn.write_text(
                '[Event "One"]\n'
                '[Result "*"]\n'
                "\n"
                "1. e4 { broken comment\n"
                "still comment\n"
                "\n"
                '[Event "Two"]\n'
                '[Result "*"]\n'
                "\n"
                "1. d4 d5 *\n",
                encoding="utf-8",
            )

            result = pgn_cli.repair_pgn_file_in_place(pgn, backup_suffix=None)
            repaired_text = pgn.read_text(encoding="utf-8")

            self.assertIn('[Event "One"]', repaired_text)
            self.assertIn('[Event "Two"]', repaired_text)
            self.assertIn("1. d4 d5 *", repaired_text)
            self.assertEqual(result.normalization.games_written, 2)

    def test_fast_repair_falls_back_when_native_helper_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "fallback.pgn"
            repaired = root / "repaired.pgn"
            source.write_text('[Event "x"]\n\n1. e4 { note } e5 *\n', encoding="utf-8")

            with mock.patch(
                "reti.pgn_utils.find_pgn_utils_binary",
                return_value=Path("/fake/native"),
            ), mock.patch(
                "reti.pgn_utils.subprocess.run",
                side_effect=OSError("boom"),
            ):
                stats = pgn_utils.rewrite_pgn_fast(source, repaired)

            self.assertFalse(stats.used_native_accelerator)
            self.assertIn("1. e4 e5 *", repaired.read_text(encoding="utf-8"))

    def test_main_rejects_non_pgn_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "not-pgn.txt"
            path.write_text("x", encoding="utf-8")
            exit_code = pgn_cli.main(["--pgn", str(path)])

        self.assertEqual(exit_code, 1)

    def test_main_rejects_non_positive_cql_lineincrement(self):
        exit_code = pgn_cli.main(["--pgn", "missing.pgn", "--cql-lineincrement", "0"])
        self.assertEqual(exit_code, 1)

    def test_main_repairs_directory_of_pgns_recursively(self):
        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
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

            exit_code = pgn_cli.main(["--pgn", str(root), "--no-backup"])

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

    def test_strict_repair_uses_normalized_header_result_in_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "result-mismatch.pgn"
            pgn.write_text(
                '[Event "x"]\n'
                '[Result "1-0"]\n'
                "\n"
                "1. e4 e5 *\n",
                encoding="utf-8",
            )

            pgn_cli.repair_pgn_file_in_place(
                pgn,
                backup_suffix=None,
                mode=pgn_cli.STRICT_REPAIR_MODE,
            )

            repaired_text = pgn.read_text(encoding="utf-8")
            self.assertIn('[Site "?"]', repaired_text)
            self.assertIn('[Result "1-0"]', repaired_text)
            self.assertIn("1. e4 e5 1-0", repaired_text)
            self.assertNotIn("1. e4 e5 *", repaired_text)

    def test_fast_mode_is_default(self):
        args = pgn_cli.parse_args(["--pgn", "file.pgn"])
        self.assertEqual(args.mode, pgn_cli.FAST_REPAIR_MODE)

    def test_preserve_markup_keeps_comments_variations_and_line_comments(self):
        with _python_fast_patch(), tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "annotated.pgn"
            repaired = root / "repaired.pgn"
            source.write_bytes(
                b'\xef\xbb\xbf[Event "x"]\n\n'
                b"% top\n"
                b"1. e4 { note } e5 ( 1... c5 ) 2. Nf3 \x1f; trailing\n"
                b"*\n"
            )

            stats = pgn_utils.rewrite_pgn_fast_python(
                source, repaired, preserve_markup=True
            )
            repaired_text = repaired.read_text(encoding="utf-8")

            self.assertIn("{ note }", repaired_text)
            self.assertIn("( 1... c5 )", repaired_text)
            self.assertIn("% top", repaired_text)
            self.assertIn("; trailing", repaired_text)
            self.assertTrue(stats.removed_bom)
            self.assertEqual(stats.control_characters_removed, 1)
            self.assertEqual(stats.comments_removed, 0)
            self.assertEqual(stats.variations_removed, 0)
            self.assertEqual(stats.line_comments_removed, 0)
            self.assertNotIn("\x1f", repaired_text)
            self.assertNotIn("\ufeff", repaired_text)

    def test_preserve_markup_rejected_with_strict_mode(self):
        exit_code = pgn_cli.main(
            ["--pgn", "missing.pgn", "--mode", "strict", "--preserve-markup"]
        )
        self.assertEqual(exit_code, 1)

    def test_fast_repair_with_actual_cql_smoke_test_on_malformed_fixture(self):
        cql_binary = Path(__file__).resolve().parents[1] / "bins" / "cql6-2" / "cql"
        if not cql_binary.is_file():
            self.skipTest("local CQL binary is not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "malformed.pgn"
            pgn.write_text(
                '[Event "One"]\n'
                '[Result "*"]\n'
                "\n"
                "1. e4 { broken comment\n"
                "still comment\n"
                "\n"
                '[Event "Two"]\n'
                '[Site "Site (With Parens)"]\n'
                '[Result "*"]\n'
                "\n"
                "1. d4 d5 ; trailing\n"
                "2. c4 *\n",
                encoding="utf-8",
            )

            result = pgn_cli.repair_pgn_file_in_place(
                pgn,
                backup_suffix=None,
                cql_binary=cql_binary,
            )

            self.assertEqual(result.smoke_test_message, "CQL smoke test passed")
            repaired_text = pgn.read_text(encoding="utf-8")
            self.assertIn('[Site "Site (With Parens)"]', repaired_text)
            self.assertIn("1. d4 d5", repaired_text)


if __name__ == "__main__":
    unittest.main()
