from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark fast and strict PGN repair modes on a local backup."
    )
    parser.add_argument(
        "--pgn-bak",
        default="LumbrasGigaBase_OTB_1900-1949.pgn.bak",
        help="Path to a .pgn.bak file to benchmark.",
    )
    parser.add_argument(
        "--cql-bin",
        default=None,
        help="Optional CQL binary for an extra fast-mode smoke-test run.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter to use for invoking repair_pgn.py.",
    )
    parser.add_argument(
        "--build-native",
        action="store_true",
        help="Build the Rust fast-path helper before running the benchmark.",
    )
    return parser.parse_args()


def _run_command(command: list[str]) -> tuple[float, subprocess.CompletedProcess[str]]:
    start = time.perf_counter()
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - start
    return elapsed, result


def _tail_summary(output: str) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    return "\n".join(lines[-6:])


def _build_native_helper(repo_root: Path) -> None:
    manifest = repo_root / "native" / "repair-pgn-fast" / "Cargo.toml"
    subprocess.run(
        ["cargo", "build", "--release", "--manifest-path", str(manifest)],
        check=True,
    )


def _benchmark_case(
    repo_root: Path,
    source_backup: Path,
    *,
    mode: str,
    cql_binary: str | None,
    python_binary: str,
) -> tuple[float, subprocess.CompletedProcess[str]]:
    with tempfile.TemporaryDirectory(prefix="repair_pgn_bench_") as tmpdir:
        tmp_root = Path(tmpdir)
        working_copy = tmp_root / f"{source_backup.stem}.{mode}.pgn"
        shutil.copy2(source_backup, working_copy)

        command = [
            python_binary,
            str(repo_root / "src" / "reti" / "repair_pgn.py"),
            "--pgn",
            str(working_copy),
            "--mode",
            mode,
            "--no-backup",
        ]
        if cql_binary:
            command.extend(["--cql-bin", cql_binary])
        return _run_command(command)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    source_backup = Path(args.pgn_bak).expanduser()
    if not source_backup.is_file():
        print(f"Error: backup PGN not found: {source_backup}")
        return 1

    if args.build_native:
        print("Building Rust fast-path helper...")
        _build_native_helper(repo_root)

    cases = [
        ("fast", None),
        ("strict", None),
    ]
    if args.cql_bin:
        cases.insert(1, ("fast+smoke", args.cql_bin))

    print(f"Benchmarking {source_backup}...")
    for label, cql_binary in cases:
        mode = "fast" if label.startswith("fast") else "strict"
        elapsed, result = _benchmark_case(
            repo_root,
            source_backup,
            mode=mode,
            cql_binary=cql_binary,
            python_binary=args.python,
        )
        print(f"\n[{label}] {elapsed:.2f}s exit={result.returncode}")
        if result.stdout.strip():
            print(_tail_summary(result.stdout))
        if result.returncode != 0 and result.stderr.strip():
            print(result.stderr.strip())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
