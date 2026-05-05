"""Backwards-compatible facade for the batch CQL runner.

The implementation moved to :mod:`reti.cql`. New code should import from
``reti.cql`` directly. Tests and the existing CLI entrypoint
(``python src/reti/analyse_cql.py``) continue to work via this module.
"""

from __future__ import annotations

import subprocess  # re-exported so tests can patch reti.analyse_cql.subprocess.run
from pathlib import Path

from reti.cql.backend import Cql6Backend, CqlBackend, resolve_cql_binary
from reti.cql.cli import (
    main,
    parse_args,
    print_summary,
    run_cql_analysis,
)
from reti.cql.output import merge_outputs_by_cql, write_summary_csv
from reti.cql.preflight import (
    PgnPreflightResult,
    count_games_in_pgn,
    first_nonempty_line,
    inspect_pgn_text_compatibility,
    issues_from_fast_stats,
    preflight_pgn_files as _preflight_pgn_files,
    sanitize_pgn_to_temp,
    smoke_test_pgn_with_cql as _smoke_test_pgn_with_cql,
    validate_pgn_text_compatibility,
    validate_pgn_with_python_parser,
)
from reti.cql.runner import (
    JobResult,
    JobSpec,
    build_job_specs,
    build_output_path,
    parse_cql_threads_value,
    parse_jobs_value,
    resolve_cql_threads,
    resolve_worker_count,
    run_cql_job as _run_cql_job,
    run_job_matrix as _run_job_matrix,
)
from reti.common.pgn_discovery import (
    InputCollection,
    discover_input_files,
    format_relative,
    relative_stem,
)
from reti.common.progress import (
    format_progress_label,
    make_terminal_safe,
    progress_write,
)
from reti.common.subprocess_helpers import describe_returncode

__all__ = [
    "Cql6Backend",
    "CqlBackend",
    "InputCollection",
    "JobResult",
    "JobSpec",
    "PgnPreflightResult",
    "build_job_specs",
    "build_output_path",
    "count_games_in_pgn",
    "describe_returncode",
    "discover_input_files",
    "first_nonempty_line",
    "format_progress_label",
    "format_relative",
    "inspect_pgn_text_compatibility",
    "issues_from_fast_stats",
    "main",
    "make_terminal_safe",
    "merge_outputs_by_cql",
    "parse_args",
    "parse_cql_threads_value",
    "parse_jobs_value",
    "preflight_pgn_files",
    "print_summary",
    "progress_write",
    "relative_stem",
    "resolve_cql_binary",
    "resolve_cql_threads",
    "resolve_worker_count",
    "run_cql_analysis",
    "run_cql_job",
    "run_job_matrix",
    "sanitize_pgn_to_temp",
    "smoke_test_pgn_with_cql",
    "subprocess",
    "validate_pgn_text_compatibility",
    "validate_pgn_with_python_parser",
    "write_summary_csv",
]


def _as_backend(cql: CqlBackend | Path | str) -> CqlBackend:
    if isinstance(cql, CqlBackend):
        return cql
    return Cql6Backend(Path(cql))


def preflight_pgn_files(
    pgn_inputs: InputCollection,
    cql_binary: CqlBackend | Path | str,
    runtime_root: Path,
    *,
    smoke_test_pgns: bool = False,
    strict_pgn_parse: bool = False,
) -> list[PgnPreflightResult]:
    """Legacy entrypoint accepting a ``Path``; new code should pass a ``CqlBackend``."""
    return _preflight_pgn_files(
        pgn_inputs,
        _as_backend(cql_binary),
        runtime_root,
        smoke_test_pgns=smoke_test_pgns,
        strict_pgn_parse=strict_pgn_parse,
    )


def run_cql_job(
    cql_binary: CqlBackend | Path | str,
    source_pgn_path: Path,
    runtime_pgn_path: Path,
    cql_path: Path,
    output_pgn: Path,
    *,
    cql_threads: str | int = "auto",
) -> JobResult:
    """Legacy entrypoint accepting a ``Path``; new code should pass a ``CqlBackend``."""
    return _run_cql_job(
        _as_backend(cql_binary),
        source_pgn_path,
        runtime_pgn_path,
        cql_path,
        output_pgn,
        cql_threads=cql_threads,
    )


def run_job_matrix(
    cql_bin_path: CqlBackend | Path | str,
    job_specs: list[JobSpec],
    *,
    jobs: str | int,
    cql_threads: str | int,
    game_progress: bool = False,
) -> list[JobResult]:
    return _run_job_matrix(
        _as_backend(cql_bin_path),
        job_specs,
        jobs=jobs,
        cql_threads=cql_threads,
        game_progress=game_progress,
    )


def smoke_test_pgn_with_cql(
    cql_binary: CqlBackend | Path | str,
    pgn_path: Path,
    smoke_script: Path,
    smoke_output: Path,
) -> tuple[int, str, str]:
    return _smoke_test_pgn_with_cql(
        _as_backend(cql_binary),
        pgn_path,
        smoke_script,
        smoke_output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
