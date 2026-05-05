"""Argument parsing + ``main()`` for the batch CQL runner."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from reti.cql.backend import Cql6Backend, resolve_cql_binary
from reti.cql.output import merge_outputs_by_cql, write_summary_csv
from reti.cql.preflight import PgnPreflightResult, preflight_pgn_files
from reti.cql.runner import (
    JobResult,
    build_job_specs,
    parse_cql_threads_value,
    parse_jobs_value,
    run_job_matrix,
)
from reti.common.pgn_discovery import InputCollection, discover_input_files
from reti.common.progress import progress_write


def run_cql_analysis(
    pgn_location: str,
    cql_binary: str,
    scripts_location: str,
    output_dir: str | Path,
    *,
    jobs: str | int = 1,
    cql_threads: str | int = "auto",
    skip_pgn_preflight: bool = False,
    smoke_test_pgns: bool = False,
    strict_pgn_parse: bool = False,
    game_progress: bool = False,
) -> tuple[list[JobResult], InputCollection, InputCollection] | None:
    cql_bin_path = resolve_cql_binary(cql_binary)
    if cql_bin_path is None:
        return None
    backend = Cql6Backend(cql_bin_path)

    pgn_inputs = discover_input_files(pgn_location, ".pgn")
    if pgn_inputs is None:
        return None

    cql_inputs = discover_input_files(scripts_location, ".cql")
    if cql_inputs is None:
        return None

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cql_runtime_") as runtime_tmpdir:
        runtime_root = Path(runtime_tmpdir)
        if skip_pgn_preflight:
            prepared_pgns = [
                PgnPreflightResult(
                    pgn_path=pgn_path,
                    runtime_pgn_path=pgn_path,
                    success=True,
                    sanitized=False,
                    message="preflight skipped",
                )
                for pgn_path in pgn_inputs.files
            ]
        else:
            prepared_pgns = preflight_pgn_files(
                pgn_inputs,
                backend,
                runtime_root,
                smoke_test_pgns=smoke_test_pgns,
                strict_pgn_parse=strict_pgn_parse,
            )
            if any(not result.success for result in prepared_pgns):
                return None

        print(f"Using CQL binary: {cql_bin_path}")
        print(
            f"Discovered {len(prepared_pgns)} PGN file(s) and "
            f"{len(cql_inputs.files)} CQL script(s)."
        )
        job_specs = build_job_specs(prepared_pgns, pgn_inputs, cql_inputs, output_path)
        results = run_job_matrix(
            backend,
            job_specs,
            jobs=jobs,
            cql_threads=cql_threads,
            game_progress=game_progress,
        )

    return results, pgn_inputs, cql_inputs


def print_summary(results: list[JobResult], output_dir: Path, summary_csv: Path) -> int:
    successes = sum(1 for result in results if result.success)
    failures = len(results) - successes

    print("\n--- Summary ---")
    print(f"Jobs: {len(results)}")
    print(f"Successful: {successes}")
    print(f"Failed: {failures}")
    print(f"Output directory: {output_dir}")
    print(f"Summary CSV: {summary_csv}")
    print("---------------")

    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run every discovered CQL script against every discovered PGN file. "
            "Both PGN and CQL inputs may be a single file or a directory scanned recursively."
        )
    )

    parser.add_argument(
        "--pgn",
        "--pgn-input",
        dest="pgn_location",
        default=None,
        help="Path to a .pgn file or a directory containing .pgn files.",
    )
    parser.add_argument(
        "--cql-bin",
        "--cql-binary",
        dest="cql_binary",
        default=None,
        help="Path to the CQL executable, or an executable name available on PATH.",
    )
    parser.add_argument(
        "--scripts",
        "--cql-input",
        dest="scripts_location",
        default=None,
        help="Path to a .cql file or a directory containing .cql files.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        "--output_dir",
        dest="output_dir",
        default=None,
        help=(
            "Directory where output PGNs and summary.csv will be written. "
            "Defaults to a temporary directory."
        ),
    )
    parser.add_argument(
        "--keep-output",
        "--keep_output",
        dest="keep_output",
        action="store_true",
        help="Keep the temporary output directory when --output-dir is omitted.",
    )
    parser.add_argument(
        "--skip-pgn-preflight",
        "--skip_pgn_preflight",
        dest="skip_pgn_preflight",
        action="store_true",
        help=(
            "Skip the initial PGN validation pass. By default the runner checks "
            "that each PGN looks like an export PGN and uses a sanitized "
            "temporary copy if needed for text-compatibility issues."
        ),
    )
    parser.add_argument(
        "--smoke-test-pgns",
        dest="smoke_test_pgns",
        action="store_true",
        help=(
            "During preflight, run one cheap CQL smoke query per PGN before the "
            "full matrix. This catches CQL-level PGN failures earlier but adds "
            "startup time on large databases."
        ),
    )
    parser.add_argument(
        "-j",
        "--jobs",
        dest="jobs",
        type=parse_jobs_value,
        default=1,
        help=(
            "Number of CQL jobs to run in parallel. Defaults to 1 so CQL can "
            "use its own internal threading without process-level oversubscription."
        ),
    )
    parser.add_argument(
        "--cql-threads",
        dest="cql_threads",
        type=parse_cql_threads_value,
        default="auto",
        help=(
            "Thread count passed to each CQL process. Use 'auto' to let CQL "
            "choose when running sequentially; when --jobs is greater than 1, "
            "'auto' becomes 1 to avoid oversubscription."
        ),
    )
    parser.add_argument(
        "--strict-pgn-parse",
        dest="strict_pgn_parse",
        action="store_true",
        help=(
            "Run a full python-chess PGN parse during preflight. This is slower "
            "on large databases but can surface parser-level PGN issues earlier."
        ),
    )
    parser.add_argument(
        "--game-progress",
        dest="game_progress",
        action="store_true",
        help=(
            "Show progress in games instead of jobs. Pre-counts games in each "
            "PGN so the progress bar reflects actual game throughput."
        ),
    )
    parser.add_argument(
        "--merge-output",
        dest="merge_output",
        action="store_true",
        help=(
            "After all jobs finish, merge output PGNs into one file per CQL "
            "script instead of one file per PGN/CQL pair."
        ),
    )
    parser.add_argument(
        "legacy_args",
        nargs="*",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args(argv)

    if args.legacy_args:
        if len(args.legacy_args) != 3:
            parser.error(
                "legacy positional usage requires exactly 3 arguments: "
                "PGN_INPUT CQL_BINARY CQL_INPUT"
            )
        if args.pgn_location or args.cql_binary or args.scripts_location:
            parser.error(
                "use either the explicit flags (--pgn, --cql-bin, --scripts) "
                "or the legacy positional form, not both"
            )
        args.pgn_location, args.cql_binary, args.scripts_location = args.legacy_args
        progress_write(
            "Warning: positional analyse_cql.py arguments are deprecated; "
            "prefer --pgn, --cql-bin, and --scripts."
        )
    else:
        missing = []
        if not args.pgn_location:
            missing.append("--pgn")
        if not args.cql_binary:
            missing.append("--cql-bin")
        if not args.scripts_location:
            missing.append("--scripts")
        if missing:
            parser.error(
                "the following arguments are required: " + ", ".join(missing)
            )

    return args


def main() -> int:
    args = parse_args()

    if args.output_dir:
        output_directory = Path(args.output_dir)
        cleanup_needed = False
    else:
        output_directory = Path(tempfile.mkdtemp(prefix="cql_results_"))
        cleanup_needed = not args.keep_output
        print(f"Using temporary output directory: {output_directory}")

    result = run_cql_analysis(
        args.pgn_location,
        args.cql_binary,
        args.scripts_location,
        output_directory,
        jobs=args.jobs,
        cql_threads=args.cql_threads,
        skip_pgn_preflight=args.skip_pgn_preflight,
        smoke_test_pgns=args.smoke_test_pgns,
        strict_pgn_parse=args.strict_pgn_parse,
        game_progress=args.game_progress,
    )

    if result is None:
        if cleanup_needed:
            shutil.rmtree(output_directory, ignore_errors=True)
        return 1

    results, pgn_inputs, cql_inputs = result

    if args.merge_output:
        merge_outputs_by_cql(results, cql_inputs, output_directory)

    summary_csv = write_summary_csv(
        results, output_directory, pgn_inputs.root, cql_inputs.root
    )
    failures = print_summary(results, output_directory, summary_csv)

    if cleanup_needed:
        shutil.rmtree(output_directory, ignore_errors=True)
        print(f"Removed temporary directory: {output_directory}")
    elif not args.output_dir and args.keep_output:
        print(f"Output PGN files kept in: {output_directory}")

    return 1 if failures else 0
