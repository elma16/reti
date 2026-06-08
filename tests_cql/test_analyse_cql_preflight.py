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
import reti.cql.preflight as preflight_module


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

    def test_parse_args_accepts_consolidated_preflight_mode(self):
        args = analyse_cql.parse_args(
            [
                "--pgn",
                "games",
                "--cql-bin",
                "cql",
                "--scripts",
                "filters",
                "--preflight",
                "strict-smoke",
            ]
        )
        self.assertTrue(args.strict_pgn_parse)
        self.assertTrue(args.smoke_test_pgns)

    def test_parse_args_rejects_overlapping_preflight_options(self):
        with self.assertRaises(SystemExit):
            analyse_cql.parse_args(
                [
                    "--pgn",
                    "games",
                    "--cql-bin",
                    "cql",
                    "--scripts",
                    "filters",
                    "--skip-pgn-preflight",
                    "--smoke-test-pgns",
                ]
            )

    def test_parse_args_accepts_consolidated_output_mode(self):
        args = analyse_cql.parse_args(
            [
                "--pgn",
                "games",
                "--cql-bin",
                "cql",
                "--scripts",
                "filters",
                "--output-mode",
                "single",
                "--include-unmatched",
            ]
        )
        self.assertEqual(args.output_mode, "single")
        self.assertTrue(args.include_unmatched)

    def test_describe_returncode_for_signal(self):
        description = analyse_cql.describe_returncode(-6)
        self.assertIn("signal 6", description)
        self.assertIn("SIGABRT", description)

    def test_backend_auto_detection_distinguishes_cqli_name(self):
        self.assertEqual(analyse_cql.infer_backend_name(Path("/tmp/cql")), "cql6")
        self.assertEqual(analyse_cql.infer_backend_name(Path("/tmp/cqli-arm64")), "cqli")

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

    def test_preflight_progress_is_weighted_by_pgn_bytes(self):
        class RecordingProgress:
            def __init__(self, iterable=None, **kwargs):
                self.iterable = iterable
                self.kwargs = kwargs
                self.updates: list[int] = []

            def __iter__(self):
                if self.iterable is None:
                    return iter(())
                return iter(self.iterable)

            def update(self, value: int = 1) -> None:
                self.updates.append(value)

            def set_postfix_str(self, _: str) -> None:
                return None

            def close(self) -> None:
                return None

        progress_instances: list[RecordingProgress] = []

        def recording_tqdm(iterable=None, **kwargs):
            progress = RecordingProgress(iterable=iterable, **kwargs)
            progress_instances.append(progress)
            return progress

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            small = root / "small.pgn"
            large = root / "large.pgn"
            small.write_text('[Event "small"]\n\n*\n', encoding="utf-8")
            large.write_text('[Event "large"]\n\n' + "1. e4 e5 " * 200 + "*\n", encoding="utf-8")
            small_size = small.stat().st_size
            large_size = large.stat().st_size
            runtime_root = root / "runtime"

            with mock.patch.object(preflight_module, "tqdm_progress", recording_tqdm):
                results = analyse_cql.preflight_pgn_files(
                    analyse_cql.InputCollection(root=root, files=[small, large]),
                    Path("/fake/cql"),
                    runtime_root,
                )

        self.assertTrue(all(result.success for result in results))
        self.assertEqual(len(progress_instances), 1)
        progress = progress_instances[0]
        self.assertEqual(progress.kwargs["total"], small_size + large_size)
        self.assertEqual(progress.kwargs["unit"], "B")
        self.assertEqual(progress.updates, [small_size, large_size])

    @mock.patch("reti.cql.runner.subprocess.run")
    def test_run_cql_job_uses_explicit_cql_threads(self, run_mock):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "db.pgn"
            cql = root / "filter.cql"
            out = root / "out.pgn"
            pgn.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
            cql.write_text("cql() check\n", encoding="utf-8")

            def fake_run(command, **_: object):
                out.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout="",
                    stderr="",
                )

            run_mock.side_effect = fake_run

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
        self.assertEqual(
            run_args,
            [
                "/fake/cql",
                "-i",
                str(pgn),
                "-o",
                str(out),
                "-matchstring",
                "filter",
                "-threads",
                "1",
                str(cql),
            ],
        )

    @mock.patch("reti.cql.runner.subprocess.run")
    def test_run_cql_job_leaves_cql_threads_implicit_in_auto_mode(self, run_mock):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn = root / "db.pgn"
            cql = root / "filter.cql"
            out = root / "out.pgn"
            pgn.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
            cql.write_text("cql() check\n", encoding="utf-8")

            def fake_run(command, **_: object):
                out.write_text('[Event "x"]\n\n1. e4 e5 *\n', encoding="utf-8")
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout="",
                    stderr="",
                )

            run_mock.side_effect = fake_run

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

    @mock.patch("reti.cql.runner.subprocess.run")
    def test_run_cql_job_removes_stale_output_and_fails_when_output_missing(self, run_mock):
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
            out.write_text('[Event "stale"]\n\n*\n', encoding="utf-8")

            result = analyse_cql.run_cql_job(
                Path("/fake/cql"),
                pgn,
                pgn,
                cql,
                out,
            )

            self.assertFalse(out.exists())

        self.assertFalse(result.success)
        self.assertTrue(result.missing_output)
        self.assertIn("did not create", result.stderr)

    @mock.patch("reti.cql.preflight.subprocess.run")
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
        run_args = run_mock.call_args.args[0]
        self.assertIn("-input", run_args)
        self.assertIn("-output", run_args)

    @mock.patch("reti.cql.preflight.subprocess.run")
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

    @mock.patch("reti.cql.preflight.subprocess.run")
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
