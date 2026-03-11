from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


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


def count_games_in_pgn(pgn_file_path: str | Path) -> int:
    """
    Count games in a PGN by scanning for '[Event ' tags.
    """
    try:
        with open(pgn_file_path, "r", encoding="utf-8", errors="replace") as f:
            return len(re.findall(r"\[Event ", f.read()))
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


def run_cql_job(
    cql_binary: Path,
    pgn_path: Path,
    cql_path: Path,
    output_pgn: Path,
) -> JobResult:
    output_pgn.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(cql_binary),
        "-i",
        str(pgn_path),
        "-o",
        str(output_pgn),
        str(cql_path),
    ]

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
            pgn_path=pgn_path,
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
            pgn_path=pgn_path,
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
            pgn_path=pgn_path,
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
        pgn_path=pgn_path,
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


def run_cql_analysis(
    pgn_location: str,
    cql_binary: str,
    scripts_location: str,
    output_dir: str | Path,
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

    total_jobs = len(pgn_inputs.files) * len(cql_inputs.files)
    print(f"Using CQL binary: {cql_bin_path}")
    print(
        f"Discovered {len(pgn_inputs.files)} PGN file(s) and {len(cql_inputs.files)} CQL script(s)."
    )
    print(f"Running {total_jobs} job(s)...")

    results: list[JobResult] = []
    job_index = 0

    for pgn_path in pgn_inputs.files:
        for cql_path in cql_inputs.files:
            job_index += 1
            output_pgn = build_output_path(
                output_path,
                pgn_path,
                pgn_inputs.root,
                cql_path,
                cql_inputs.root,
            )
            print(
                f"\n[{job_index}/{total_jobs}] "
                f"{format_relative(pgn_path, pgn_inputs.root)} x "
                f"{format_relative(cql_path, cql_inputs.root)}"
            )
            print(f"Output: {output_pgn.relative_to(output_path)}")

            result = run_cql_job(cql_bin_path, pgn_path, cql_path, output_pgn)
            results.append(result)

            if result.success:
                print(f"OK: {result.match_count} matching game(s)")
            else:
                print(f"FAILED: return code {result.returncode}")
                if result.stderr.strip():
                    print(result.stderr.strip())

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run every discovered CQL script against every discovered PGN file. "
            "Both PGN and CQL inputs may be a single file or a directory scanned recursively."
        )
    )

    parser.add_argument(
        "pgn_location",
        help="Path to a .pgn file or a directory containing .pgn files.",
    )
    parser.add_argument(
        "cql_binary",
        help="Path to the CQL executable, or an executable name available on PATH.",
    )
    parser.add_argument(
        "scripts_location",
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

    args = parser.parse_args()

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
