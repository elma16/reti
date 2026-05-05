"""CQL job specification, dispatch, and parallel execution."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm as tqdm_progress

from reti.cql.backend import CqlBackend
from reti.cql.preflight import PgnPreflightResult, count_games_in_pgn
from reti.common.pgn_discovery import (
    InputCollection,
    format_relative,
    relative_stem,
)
from reti.common.progress import format_progress_label, progress_write
from reti.common.subprocess_helpers import describe_returncode


@dataclass(frozen=True)
class JobResult:
    pgn_path: Path
    cql_path: Path
    output_pgn: Path
    success: bool
    match_count: int | None
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class JobSpec:
    job_index: int
    pair_label: str
    source_pgn_path: Path
    runtime_pgn_path: Path
    cql_path: Path
    output_pgn: Path


def parse_jobs_value(value: str) -> str | int:
    text = value.strip().lower()
    if text == "auto":
        return "auto"

    try:
        parsed = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--jobs must be a positive integer or 'auto'"
        ) from exc

    if parsed < 1:
        raise argparse.ArgumentTypeError("--jobs must be at least 1")
    return parsed


def parse_cql_threads_value(value: str) -> str | int:
    text = value.strip().lower()
    if text == "auto":
        return "auto"

    try:
        parsed = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--cql-threads must be a positive integer or 'auto'"
        ) from exc

    if parsed < 1:
        raise argparse.ArgumentTypeError("--cql-threads must be at least 1")
    return parsed


def resolve_worker_count(requested_jobs: str | int, total_jobs: int) -> int:
    if total_jobs <= 1:
        return 1

    if requested_jobs == "auto":
        requested = os.cpu_count() or 1
    else:
        requested = int(requested_jobs)

    return max(1, min(total_jobs, requested))


def resolve_cql_threads(
    requested_cql_threads: str | int,
    worker_count: int,
) -> str | int:
    if requested_cql_threads == "auto":
        if worker_count > 1:
            return 1
        return "auto"

    return int(requested_cql_threads)


def build_output_path(
    output_dir: Path,
    pgn_path: Path,
    pgn_root: Path,
    cql_path: Path,
    cql_root: Path,
) -> Path:
    """Keep outputs deterministic and collision-free across matrix runs."""
    return (
        output_dir
        / relative_stem(pgn_path, pgn_root)
        / relative_stem(cql_path, cql_root).with_suffix(".pgn")
    )


def build_job_specs(
    prepared_pgns: list[PgnPreflightResult],
    pgn_inputs: InputCollection,
    cql_inputs: InputCollection,
    output_path: Path,
) -> list[JobSpec]:
    job_specs: list[JobSpec] = []
    for prepared_pgn in prepared_pgns:
        for cql_path in cql_inputs.files:
            pair_label = (
                f"{format_relative(prepared_pgn.pgn_path, pgn_inputs.root)} x "
                f"{format_relative(cql_path, cql_inputs.root)}"
            )
            job_specs.append(
                JobSpec(
                    job_index=len(job_specs) + 1,
                    pair_label=pair_label,
                    source_pgn_path=prepared_pgn.pgn_path,
                    runtime_pgn_path=prepared_pgn.runtime_pgn_path,
                    cql_path=cql_path,
                    output_pgn=build_output_path(
                        output_path,
                        prepared_pgn.pgn_path,
                        pgn_inputs.root,
                        cql_path,
                        cql_inputs.root,
                    ),
                )
            )
    return job_specs


def run_cql_job(
    backend: CqlBackend,
    source_pgn_path: Path,
    runtime_pgn_path: Path,
    cql_path: Path,
    output_pgn: Path,
    *,
    cql_threads: str | int = "auto",
) -> JobResult:
    output_pgn.parent.mkdir(parents=True, exist_ok=True)
    command = backend.build_run_command(
        runtime_pgn_path,
        cql_path,
        output_pgn,
        threads=cql_threads,
    )

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        return JobResult(
            pgn_path=source_pgn_path,
            cql_path=cql_path,
            output_pgn=output_pgn,
            success=False,
            match_count=None,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )
    except Exception as exc:
        return JobResult(
            pgn_path=source_pgn_path,
            cql_path=cql_path,
            output_pgn=output_pgn,
            success=False,
            match_count=None,
            returncode=1,
            stdout="",
            stderr=str(exc),
        )

    if process.returncode != 0:
        return JobResult(
            pgn_path=source_pgn_path,
            cql_path=cql_path,
            output_pgn=output_pgn,
            success=False,
            match_count=None,
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )

    match_count = count_games_in_pgn(output_pgn)
    return JobResult(
        pgn_path=source_pgn_path,
        cql_path=cql_path,
        output_pgn=output_pgn,
        success=True,
        match_count=match_count,
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
    )


def _count_games_for_specs(
    job_specs: list[JobSpec],
) -> dict[Path, int]:
    """Pre-count games per source PGN (deduplicated across CQL scripts)."""
    counts: dict[Path, int] = {}
    for spec in job_specs:
        if spec.source_pgn_path not in counts:
            counts[spec.source_pgn_path] = count_games_in_pgn(spec.source_pgn_path)
    return counts


def run_job_matrix(
    backend: CqlBackend,
    job_specs: list[JobSpec],
    *,
    jobs: str | int,
    cql_threads: str | int,
    game_progress: bool = False,
) -> list[JobResult]:
    total_jobs = len(job_specs)
    worker_count = resolve_worker_count(jobs, total_jobs)
    effective_cql_threads = resolve_cql_threads(cql_threads, worker_count)
    print(
        f"Running {total_jobs} job(s) with {worker_count} worker(s); "
        f"CQL threads per process: {effective_cql_threads}..."
    )

    game_counts: dict[Path, int] = {}
    if game_progress:
        print("Counting games for progress bar...")
        game_counts = _count_games_for_specs(job_specs)
        total_games = sum(
            game_counts.get(spec.source_pgn_path, 0) for spec in job_specs
        )
        progress = tqdm_progress(
            total=total_games,
            desc="CQL jobs",
            unit="game",
            dynamic_ncols=sys.stderr.isatty(),
            file=sys.stderr,
        )
    else:
        progress = tqdm_progress(
            total=total_jobs,
            desc="CQL jobs",
            unit="job",
            dynamic_ncols=sys.stderr.isatty(),
            file=sys.stderr,
        )

    indexed_results: list[tuple[int, JobResult]] = []

    def _on_job_done(job_spec: JobSpec, result: JobResult) -> None:
        indexed_results.append((job_spec.job_index, result))
        if game_progress:
            progress.update(game_counts.get(job_spec.source_pgn_path, 0))
        else:
            progress.update(1)
        if not result.success:
            progress_write(
                f"FAILED job {job_spec.job_index}/{total_jobs}: "
                f"{job_spec.pair_label}: {describe_returncode(result.returncode)}"
            )
            if result.stderr.strip():
                progress_write(result.stderr.strip())

    if worker_count == 1:
        for job_spec in job_specs:
            progress.set_postfix_str(format_progress_label(job_spec.pair_label))
            result = run_cql_job(
                backend,
                job_spec.source_pgn_path,
                job_spec.runtime_pgn_path,
                job_spec.cql_path,
                job_spec.output_pgn,
                cql_threads=effective_cql_threads,
            )
            _on_job_done(job_spec, result)

        progress.close()
        indexed_results.sort(key=lambda item: item[0])
        return [result for _, result in indexed_results]

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_spec = {
            executor.submit(
                run_cql_job,
                backend,
                job_spec.source_pgn_path,
                job_spec.runtime_pgn_path,
                job_spec.cql_path,
                job_spec.output_pgn,
                cql_threads=effective_cql_threads,
            ): job_spec
            for job_spec in job_specs
        }

        for future in concurrent.futures.as_completed(future_to_spec):
            job_spec = future_to_spec[future]
            progress.set_postfix_str(format_progress_label(job_spec.pair_label))
            result = future.result()
            _on_job_done(job_spec, result)

    progress.close()
    indexed_results.sort(key=lambda item: item[0])
    return [result for _, result in indexed_results]
