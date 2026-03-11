from __future__ import annotations

import argparse
import concurrent.futures
import csv
import io
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import chess.pgn as chess_pgn

from tqdm import tqdm as tqdm_progress


def progress_write(message: str) -> None:
    tqdm_progress.write(make_terminal_safe(message))


def make_terminal_safe(text: str) -> str:
    """
    Escape control characters before sending text to the terminal.
    """
    safe_parts: list[str] = []
    for char in text:
        codepoint = ord(char)
        if char in "\n\r\t":
            safe_parts.append(char)
        elif codepoint < 32 or codepoint == 127:
            safe_parts.append(f"\\x{codepoint:02x}")
        else:
            safe_parts.append(char)
    return "".join(safe_parts)


def format_progress_label(text: str, *, max_length: int = 80) -> str:
    safe = make_terminal_safe(text).replace("\n", " ").replace("\r", " ").replace(
        "\t", " "
    )
    if len(safe) <= max_length:
        return safe
    head = max(10, max_length // 2 - 2)
    tail = max(10, max_length - head - 3)
    return f"{safe[:head]}...{safe[-tail:]}"


@dataclass(frozen=True)
class InputCollection:
    root: Path
    files: list[Path]


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
class PgnPreflightResult:
    pgn_path: Path
    runtime_pgn_path: Path
    success: bool
    sanitized: bool
    message: str


@dataclass(frozen=True)
class JobSpec:
    job_index: int
    pair_label: str
    source_pgn_path: Path
    runtime_pgn_path: Path
    cql_path: Path
    output_pgn: Path


def count_games_in_pgn(pgn_file_path: str | Path) -> int:
    """
    Count games in a PGN by scanning for '[Event ' tags.
    """
    try:
        with open(pgn_file_path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.startswith("[Event "))
    except FileNotFoundError:
        print(f"Error: PGN file not found for counting: {pgn_file_path}")
        return 0
    except Exception as exc:
        print(f"Error reading PGN file {pgn_file_path}: {exc}")
        return 0


def resolve_cql_binary(cql_binary: str) -> Path | None:
    """
    Resolve a CQL binary from either an explicit path or an executable on PATH.
    """
    candidate = Path(cql_binary).expanduser()
    if candidate.is_file():
        return candidate

    on_path = shutil.which(cql_binary)
    if on_path:
        return Path(on_path)

    print(f"Error: CQL binary not found: '{cql_binary}'")
    return None


def describe_returncode(returncode: int) -> str:
    """
    Negative subprocess return codes mean the process was terminated by a signal.
    """
    if returncode >= 0:
        return f"return code {returncode}"

    signal_number = -returncode
    try:
        signal_name = signal.Signals(signal_number).name
    except ValueError:
        signal_name = f"SIG{signal_number}"
    return f"terminated by signal {signal_number} ({signal_name})"


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def discover_input_files(location: str, suffix: str) -> InputCollection | None:
    """
    Resolve either a single file or recursively discover matching files in a directory.
    """
    path = Path(location).expanduser()
    expected_suffix = suffix.lower()

    if path.is_file():
        if path.suffix.lower() != expected_suffix:
            print(f"Error: '{location}' is not a {suffix} file.")
            return None
        return InputCollection(root=path.parent, files=[path])

    if path.is_dir():
        files = sorted(
            (
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() == expected_suffix
            ),
            key=lambda item: str(item.relative_to(path)),
        )
        if not files:
            print(f"Error: No {suffix} files found under '{location}'.")
            return None
        return InputCollection(root=path, files=files)

    print(f"Error: '{location}' is not a valid file or directory.")
    return None


def relative_stem(path: Path, root: Path) -> Path:
    """
    Return a path relative to root with the final suffix removed.
    """
    return path.relative_to(root).with_suffix("")


def build_output_path(
    output_dir: Path,
    pgn_path: Path,
    pgn_root: Path,
    cql_path: Path,
    cql_root: Path,
) -> Path:
    """
    Keep outputs deterministic and collision-free across matrix runs.
    """
    return (
        output_dir
        / relative_stem(pgn_path, pgn_root)
        / relative_stem(cql_path, cql_root).with_suffix(".pgn")
    )


def format_relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


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


def inspect_pgn_text_compatibility(pgn_path: Path) -> list[str]:
    """
    Find text/byte issues that can make older CQL builds abort on specific PGNs.
    """
    try:
        raw_handle = pgn_path.open("rb")
    except Exception as exc:
        return [f"could not read PGN bytes: {exc}"]

    issues: list[str] = []
    replacement_count = 0
    control_count = 0
    first_control_codepoint: int | None = None

    with raw_handle:
        prefix = raw_handle.read(3)
        if prefix == b"\xef\xbb\xbf":
            issues.append("starts with a UTF-8 BOM")
        else:
            raw_handle.seek(0)

        text_handle = io.TextIOWrapper(
            raw_handle,
            encoding="utf-8",
            errors="replace",
            newline="",
        )
        for chunk in iter(lambda: text_handle.read(1024 * 1024), ""):
            replacement_count += chunk.count("\ufffd")
            for char in chunk:
                codepoint = ord(char)
                if codepoint < 32 and char not in "\n\r\t":
                    control_count += 1
                    if first_control_codepoint is None:
                        first_control_codepoint = codepoint

    if replacement_count:
        issues.append(
            f"contains {replacement_count} invalid UTF-8 replacement character(s)"
        )
    if control_count:
        if first_control_codepoint is None:
            issues.append(f"contains {control_count} control character(s)")
        else:
            issues.append(
                "contains "
                f"{control_count} control character(s), first U+{first_control_codepoint:04X}"
            )

    return issues


def validate_pgn_text_compatibility(pgn_path: Path) -> str | None:
    issues = inspect_pgn_text_compatibility(pgn_path)
    if not issues:
        return None
    return "; ".join(issues)


def sanitize_pgn_to_temp(
    pgn_path: Path,
    pgn_root: Path,
    runtime_root: Path,
) -> Path:
    """
    Create a sanitized temporary PGN copy without modifying the original file.
    """
    destination = runtime_root / pgn_path.relative_to(pgn_root)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with pgn_path.open("rb") as raw_handle:
        prefix = raw_handle.read(3)
        if prefix != b"\xef\xbb\xbf":
            raw_handle.seek(0)

        text_handle = io.TextIOWrapper(
            raw_handle,
            encoding="utf-8",
            errors="replace",
            newline="",
        )
        with destination.open("w", encoding="utf-8", newline="") as output_handle:
            for chunk in iter(lambda: text_handle.read(1024 * 1024), ""):
                cleaned = "".join(
                    char
                    for char in chunk
                    if ord(char) >= 32 or char in "\n\r\t"
                )
                output_handle.write(cleaned)

    return destination


def validate_pgn_with_python_parser(pgn_path: Path) -> str | None:
    """
    Surface the first parser error from python-chess.
    """
    try:
        with pgn_path.open("r", encoding="utf-8", errors="replace") as handle:
            game_index = 0
            while True:
                game = chess_pgn.read_game(handle)
                if game is None:
                    break
                game_index += 1
                errors = getattr(game, "errors", None) or []
                if errors:
                    return f"python-chess parse error in game {game_index}: {errors[0]}"
    except Exception as exc:
        return f"python-chess could not read the PGN: {exc}"

    return None


def smoke_test_pgn_with_cql(
    cql_binary: Path,
    pgn_path: Path,
    smoke_script: Path,
    smoke_output: Path,
) -> tuple[int, str, str]:
    if smoke_output.exists():
        smoke_output.unlink()

    process = subprocess.run(
        [
            str(cql_binary),
            "-i",
            str(pgn_path),
            "-o",
            str(smoke_output),
            str(smoke_script),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.returncode, process.stdout, process.stderr


def preflight_pgn_files(
    pgn_inputs: InputCollection,
    cql_binary: Path,
    runtime_root: Path,
    *,
    smoke_test_pgns: bool = False,
    strict_pgn_parse: bool = False,
) -> list[PgnPreflightResult]:
    """
    Validate each PGN once before the full matrix run.

    This catches obviously non-PGN files and CQL crashes that happen before any
    user script-specific logic gets involved.
    """
    print(f"Preflighting {len(pgn_inputs.files)} PGN file(s)...")

    results: list[PgnPreflightResult] = []
    runtime_root.mkdir(parents=True, exist_ok=True)
    smoke_script: Path | None = None
    if smoke_test_pgns:
        smoke_script = runtime_root / "smoke_check.cql"
        smoke_script.write_text("cql() check\n", encoding="utf-8")

    progress = tqdm_progress(
        pgn_inputs.files,
        total=len(pgn_inputs.files),
        desc="PGN preflight",
        unit="pgn",
        dynamic_ncols=sys.stderr.isatty(),
        file=sys.stderr,
    )
    for index, pgn_path in enumerate(progress, start=1):
        relative_name = format_relative(pgn_path, pgn_inputs.root)
        progress.set_postfix_str(format_progress_label(relative_name))
        runtime_pgn_path = pgn_path
        sanitized = False

        text_issues = inspect_pgn_text_compatibility(pgn_path)
        if text_issues:
            runtime_pgn_path = sanitize_pgn_to_temp(
                pgn_path,
                pgn_inputs.root,
                runtime_root / "sanitized-pgns",
            )
            sanitized = True
            progress_write(
                "Using sanitized temporary copy for "
                f"{relative_name}: {'; '.join(text_issues)}"
            )

        event_count = count_games_in_pgn(runtime_pgn_path)
        if event_count == 0:
            results.append(
                PgnPreflightResult(
                    pgn_path=pgn_path,
                    runtime_pgn_path=runtime_pgn_path,
                    success=False,
                    sanitized=sanitized,
                    message="no [Event] tags found; file does not look like an export PGN",
                )
            )
            progress_write(
                f"FAILED preflight: {relative_name}: "
                "no [Event] tags found; file does not look like an export PGN"
            )
            continue

        if strict_pgn_parse:
            parse_error = validate_pgn_with_python_parser(runtime_pgn_path)
            if parse_error:
                results.append(
                    PgnPreflightResult(
                        pgn_path=pgn_path,
                        runtime_pgn_path=runtime_pgn_path,
                        success=False,
                        sanitized=sanitized,
                        message=parse_error,
                    )
                )
                progress_write(f"FAILED preflight: {relative_name}: {parse_error}")
                continue

        if smoke_test_pgns:
            assert smoke_script is not None
            smoke_output = runtime_root / f"smoke-{index}.pgn"
            returncode, stdout, stderr = smoke_test_pgn_with_cql(
                cql_binary,
                runtime_pgn_path,
                smoke_script,
                smoke_output,
            )
            if returncode != 0:
                detail = describe_returncode(returncode)
                extra = first_nonempty_line(stderr) or first_nonempty_line(stdout)
                message = f"CQL smoke test failed ({detail})"
                if extra:
                    message += f": {extra}"
                results.append(
                    PgnPreflightResult(
                        pgn_path=pgn_path,
                        runtime_pgn_path=runtime_pgn_path,
                        success=False,
                        sanitized=sanitized,
                        message=message,
                    )
                )
                progress_write(f"FAILED preflight: {relative_name}: {message}")
                continue

        ok_message = f"OK ({event_count} game(s) by [Event] count)"
        if sanitized:
            ok_message += "; using sanitized temporary copy"
        results.append(
            PgnPreflightResult(
                pgn_path=pgn_path,
                runtime_pgn_path=runtime_pgn_path,
                success=True,
                sanitized=sanitized,
                message=ok_message,
            )
        )
    progress.close()

    failures = [result for result in results if not result.success]
    if failures:
        print("\nPGN preflight failed before the matrix run:")
        for failure in failures:
            print(
                f"- {format_relative(failure.pgn_path, pgn_inputs.root)}: {failure.message}"
            )
    else:
        print("PGN preflight passed.")

    return results


def run_cql_job(
    cql_binary: Path,
    source_pgn_path: Path,
    runtime_pgn_path: Path,
    cql_path: Path,
    output_pgn: Path,
    *,
    cql_threads: str | int = "auto",
) -> JobResult:
    output_pgn.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(cql_binary),
        "-i",
        str(runtime_pgn_path),
        "-o",
        str(output_pgn),
    ]
    if cql_threads != "auto":
        command.extend(["-threads", str(cql_threads)])
    command.append(str(cql_path))

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


def write_summary_csv(
    results: list[JobResult],
    output_dir: Path,
    pgn_root: Path,
    cql_root: Path,
) -> Path:
    summary_path = output_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "pgn",
                "cql",
                "output_pgn",
                "status",
                "match_count",
                "returncode",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "pgn": format_relative(result.pgn_path, pgn_root),
                    "cql": format_relative(result.cql_path, cql_root),
                    "output_pgn": str(result.output_pgn.relative_to(output_dir)),
                    "status": "ok" if result.success else "error",
                    "match_count": (
                        "" if result.match_count is None else str(result.match_count)
                    ),
                    "returncode": str(result.returncode),
                }
            )
    return summary_path


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


def run_job_matrix(
    cql_bin_path: Path,
    job_specs: list[JobSpec],
    *,
    jobs: str | int,
    cql_threads: str | int,
) -> list[JobResult]:
    total_jobs = len(job_specs)
    worker_count = resolve_worker_count(jobs, total_jobs)
    effective_cql_threads = resolve_cql_threads(cql_threads, worker_count)
    print(
        f"Running {total_jobs} job(s) with {worker_count} worker(s); "
        f"CQL threads per process: {effective_cql_threads}..."
    )

    progress = tqdm_progress(
        total=total_jobs,
        desc="CQL jobs",
        unit="job",
        dynamic_ncols=sys.stderr.isatty(),
        file=sys.stderr,
    )

    indexed_results: list[tuple[int, JobResult]] = []

    if worker_count == 1:
        for job_spec in job_specs:
            progress.set_postfix_str(format_progress_label(job_spec.pair_label))
            result = run_cql_job(
                cql_bin_path,
                job_spec.source_pgn_path,
                job_spec.runtime_pgn_path,
                job_spec.cql_path,
                job_spec.output_pgn,
                cql_threads=effective_cql_threads,
            )
            indexed_results.append((job_spec.job_index, result))
            progress.update(1)

            if not result.success:
                progress_write(
                    f"FAILED job {job_spec.job_index}/{total_jobs}: "
                    f"{job_spec.pair_label}: {describe_returncode(result.returncode)}"
                )
                if result.stderr.strip():
                    progress_write(result.stderr.strip())

        progress.close()
        indexed_results.sort(key=lambda item: item[0])
        return [result for _, result in indexed_results]

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_spec = {
            executor.submit(
                run_cql_job,
                cql_bin_path,
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
            indexed_results.append((job_spec.job_index, result))
            progress.update(1)

            if not result.success:
                progress_write(
                    f"FAILED job {job_spec.job_index}/{total_jobs}: "
                    f"{job_spec.pair_label}: {describe_returncode(result.returncode)}"
                )
                if result.stderr.strip():
                    progress_write(result.stderr.strip())

    progress.close()
    indexed_results.sort(key=lambda item: item[0])
    return [result for _, result in indexed_results]


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
) -> tuple[list[JobResult], InputCollection, InputCollection] | None:
    cql_bin_path = resolve_cql_binary(cql_binary)
    if cql_bin_path is None:
        return None

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
                cql_bin_path,
                runtime_root,
                smoke_test_pgns=smoke_test_pgns,
                strict_pgn_parse=strict_pgn_parse,
            )
            if any(not result.success for result in prepared_pgns):
                return None

        print(f"Using CQL binary: {cql_bin_path}")
        print(
            f"Discovered {len(prepared_pgns)} PGN file(s) and {len(cql_inputs.files)} CQL script(s)."
        )
        job_specs = build_job_specs(prepared_pgns, pgn_inputs, cql_inputs, output_path)
        results = run_job_matrix(
            cql_bin_path,
            job_specs,
            jobs=jobs,
            cql_threads=cql_threads,
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
    )

    if result is None:
        if cleanup_needed:
            shutil.rmtree(output_directory, ignore_errors=True)
        return 1

    results, pgn_inputs, cql_inputs = result
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


if __name__ == "__main__":
    raise SystemExit(main())
