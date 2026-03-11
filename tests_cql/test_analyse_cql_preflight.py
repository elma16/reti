from __future__ import annotations

import subprocess
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

import reti.analyse_cql as analyse_cql


class TestAnalyseCqlPreflight(unittest.TestCase):
    def test_parse_args_defaults_to_sequential_jobs_and_auto_cql_threads(self):
        args = analyse_cql.parse_args(
            ["--pgn", "games", "--cql-bin", "cql", "--scripts", "filters"]
        )
        self.assertEqual(args.jobs, 1)
        self.assertEqual(args.cql_threads, "auto")

    def test_parse_args_accepts_explicit_flags(self):
        args = analyse_cql.parse_args(
            [
                "--pgn",
                "games",
                "--cql-bin",
                "cql",
                "--scripts",
                "filters",
                "--jobs",
                "4",
                "--cql-threads",
                "1",
                "--strict-pgn-parse",
            ]
        )
        self.assertEqual(args.pgn_location, "games")
        self.assertEqual(args.cql_binary, "cql")
        self.assertEqual(args.scripts_location, "filters")
        self.assertEqual(args.jobs, 4)
        self.assertEqual(args.cql_threads, 1)
        self.assertTrue(args.strict_pgn_parse)
        self.assertFalse(args.smoke_test_pgns)

    def test_describe_returncode_for_signal(self):
        description = analyse_cql.describe_returncode(-6)
        self.assertIn("signal 6", description)
        self.assertIn("SIGABRT", description)

    def test_text_validation_rejects_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pgn = Path(tmpdir) / "bom.pgn"
            pgn.write_bytes(b"\xef\xbb\xbf[Event \"x\"]\n\n*\n")
            message = analyse_cql.validate_pgn_text_compatibility(pgn)

        self.assertIsNotNone(message)
        self.assertIn("UTF-8 BOM", message)

    def test_preflight_rejects_file_without_event_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "bad.pgn"
            pgn.write_text("*\n", encoding="utf-8")
            runtime_root = root / "runtime"

            results = analyse_cql.preflight_pgn_files(
                analyse_cql.InputCollection(root=root, files=[pgn]),
                Path("/fake/cql"),
                runtime_root,
            )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("no [Event] tags", results[0].message)

    @mock.patch("reti.analyse_cql.subprocess.run")
    def test_run_cql_job_uses_explicit_cql_threads(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "db.pgn"
            cql = root / "filter.cql"
            out = root / "out.pgn"
            pgn.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
            cql.write_text("cql() check\n", encoding="utf-8")
            out.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")

            result = analyse_cql.run_cql_job(
                Path("/fake/cql"),
                pgn,
                pgn,
                cql,
                out,
                cql_threads=1,
            )

        self.assertTrue(result.success)
        run_args = run_mock.call_args.args[0]
        self.assertEqual(run_args[:6], [
            "/fake/cql",
            "-i",
            str(pgn),
            "-o",
            str(out),
            "-threads",
        ])
        self.assertEqual(run_args[6], "1")

    @mock.patch("reti.analyse_cql.subprocess.run")
    def test_run_cql_job_leaves_cql_threads_implicit_in_auto_mode(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "db.pgn"
            cql = root / "filter.cql"
            out = root / "out.pgn"
            pgn.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
            cql.write_text("cql() check\n", encoding="utf-8")
            out.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")

            result = analyse_cql.run_cql_job(
                Path("/fake/cql"),
                pgn,
                pgn,
                cql,
                out,
            )

        self.assertTrue(result.success)
        run_args = run_mock.call_args.args[0]
        self.assertNotIn("-threads", run_args)

    @mock.patch("reti.analyse_cql.subprocess.run")
    def test_preflight_skips_python_parse_by_default(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "db.pgn"
            pgn.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
            runtime_root = root / "runtime"

            with mock.patch.object(
                analyse_cql,
                "validate_pgn_with_python_parser",
                side_effect=AssertionError("python parser should be skipped"),
            ):
                results = analyse_cql.preflight_pgn_files(
                    analyse_cql.InputCollection(root=root, files=[pgn]),
                    Path("/fake/cql"),
                    runtime_root,
                    smoke_test_pgns=True,
                )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)

    @mock.patch("reti.analyse_cql.subprocess.run")
    def test_preflight_reports_cql_signal_abort(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=-6,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "db.pgn"
            pgn.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
            runtime_root = root / "runtime"

            results = analyse_cql.preflight_pgn_files(
                analyse_cql.InputCollection(root=root, files=[pgn]),
                Path("/fake/cql"),
                runtime_root,
                smoke_test_pgns=True,
            )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("SIGABRT", results[0].message)

    @mock.patch("reti.analyse_cql.subprocess.run")
    def test_preflight_uses_sanitized_temp_copy_without_touching_original(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "db.pgn"
            original_bytes = b'[Event "x"]\n\n1. e4 e5 \x1f*\n'
            pgn.write_bytes(original_bytes)
            runtime_root = root / "runtime"

            results = analyse_cql.preflight_pgn_files(
                analyse_cql.InputCollection(root=root, files=[pgn]),
                Path("/fake/cql"),
                runtime_root,
                smoke_test_pgns=True,
            )

            self.assertEqual(pgn.read_bytes(), original_bytes)
            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertTrue(result.success)
            self.assertTrue(result.sanitized)
            self.assertNotEqual(result.runtime_pgn_path, pgn)
            self.assertTrue(result.runtime_pgn_path.exists())
            self.assertNotIn("\x1f", result.runtime_pgn_path.read_text(encoding="utf-8"))
            self.assertIn("sanitized temporary copy", result.message)
            run_args = run_mock.call_args.args[0]
            self.assertEqual(run_args[2], str(result.runtime_pgn_path))


if __name__ == "__main__":
    unittest.main()
