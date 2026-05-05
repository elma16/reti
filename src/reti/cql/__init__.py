"""CQL execution layer.

The main entrypoint is :func:`reti.cql.cli.main` (also re-exported as
``reti.analyse_cql.main`` for backwards compatibility).

The pieces:

- :mod:`reti.cql.backend` — pluggable CQL executable wrapper
- :mod:`reti.cql.preflight` — per-PGN sanity checks before the matrix
- :mod:`reti.cql.runner` — job specs + parallel execution
- :mod:`reti.cql.output` — summary CSV + per-CQL output merging
- :mod:`reti.cql.cli` — argument parsing + the ``main`` orchestrator
"""

from reti.cql.backend import Cql6Backend, CqlBackend, resolve_cql_binary
from reti.cql.output import merge_outputs_by_cql, write_summary_csv
from reti.cql.preflight import (
    PgnPreflightResult,
    inspect_pgn_text_compatibility,
    issues_from_fast_stats,
    preflight_pgn_files,
    sanitize_pgn_to_temp,
    validate_pgn_text_compatibility,
    validate_pgn_with_python_parser,
)
from reti.cql.runner import (
    JobResult,
    JobSpec,
    build_job_specs,
    count_games_in_pgn,
    parse_cql_threads_value,
    parse_jobs_value,
    resolve_cql_threads,
    resolve_worker_count,
    run_cql_job,
    run_job_matrix,
)

__all__ = [
    "Cql6Backend",
    "CqlBackend",
    "JobResult",
    "JobSpec",
    "PgnPreflightResult",
    "build_job_specs",
    "count_games_in_pgn",
    "inspect_pgn_text_compatibility",
    "issues_from_fast_stats",
    "merge_outputs_by_cql",
    "parse_cql_threads_value",
    "parse_jobs_value",
    "preflight_pgn_files",
    "resolve_cql_binary",
    "resolve_cql_threads",
    "resolve_worker_count",
    "run_cql_job",
    "run_job_matrix",
    "sanitize_pgn_to_temp",
    "validate_pgn_text_compatibility",
    "validate_pgn_with_python_parser",
    "write_summary_csv",
]
