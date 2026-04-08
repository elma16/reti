"""Benchmark CQL6 vs CQLi: timing, result equivalence, and syntax compatibility."""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


CQL6_BIN = Path("cql-bin/cql6-2/cql")
CQLI_BIN = Path("cql-bin/cqli-1.0.6-macos/cqli-arm64")


@dataclass
class RunResult:
    engine: str
    cql_file: str
    elapsed: float
    matches: int | None
    games: int | None
    returncode: int
    stderr: str


@dataclass
class BenchmarkResult:
    cql_file: str
    cql6_times: list[float] = field(default_factory=list)
    cqli_times: list[float] = field(default_factory=list)
    cql6_matches: int | None = None
    cqli_matches: int | None = None
    cqli_syntax_error: str | None = None
    output_diff: bool = False


UNICODE_TO_KEYWORD = {
    "⬓": "flipcolor",
    "✵": "flip",
    "→": " attacks ",
    "←": " attackedby ",
    "⊢": "line",
    "――": " -- ",
    "×": " captures ",
}


def convert_for_cqli(cql_path: Path, tmp_dir: str) -> Path:
    """Convert CQL6 syntax to CQLi: ;; comments and Unicode operators."""
    text = cql_path.read_text(encoding="utf-8")
    # Convert ;; comments to //
    converted = re.sub(r"(?m)^(\s*);;", r"\1//", text)
    converted = re.sub(r"(?<=\S)\s+;;", " //", converted)
    # Convert Unicode operators to keywords
    for symbol, keyword in UNICODE_TO_KEYWORD.items():
        converted = converted.replace(symbol, keyword)
    # Convert ASCII operator shorthands used in CQL6 but not in CQLi
    # -> (attacks) and <- (attackedby), but not --> or <-- (line directions)
    converted = re.sub(r"(?<!--)(\S+)\s*->\s*(\S+)(?!-)", r"\1 attacks \2", converted)
    converted = re.sub(r"(?<!--)(\S+)\s*<-\s*(\S+)(?!-)", r"\1 attackedby \2", converted)
    out = Path(tmp_dir) / cql_path.name
    out.write_text(converted, encoding="utf-8")
    return out


def parse_cql6_output(output: str) -> tuple[int | None, int | None]:
    """Parse CQL6 output for match/game counts."""
    # "4 matches of 253 games in 0.09 seconds"
    m = re.search(r"(\d+)\s+match(?:es)?\s+of\s+(\d+)\s+game", output)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def parse_cqli_output(output: str) -> tuple[int | None, int | None]:
    """Parse CQLi output for match/game counts."""
    # "7 CQL matches (in 4 games) written to ..."
    # or "Analyzed 253 games ..."
    matches = None
    games = None
    m = re.search(r"(\d+)\s+CQL\s+match", output)
    if m:
        matches = int(m.group(1))
    m = re.search(r"in\s+(\d+)\s+games?\)", output)
    if m:
        games = int(m.group(1))
    if games is None:
        m = re.search(r"Analyzed\s+(\d+)\s+games?", output)
        if m and matches is None:
            # No matches case
            games = int(m.group(1))
    return matches, games


def run_engine(
    engine_bin: Path,
    cql_file: Path,
    pgn_input: Path,
    output_pgn: Path,
    *,
    single_threaded: bool = False,
) -> RunResult:
    """Run a CQL engine and capture timing + output."""
    engine_name = "cql6" if "cql6" in str(engine_bin) else "cqli"
    cmd = [str(engine_bin), "-i", str(pgn_input), "-o", str(output_pgn)]
    if single_threaded:
        cmd.append("-s")
    cmd.append(str(cql_file))

    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    elapsed = time.perf_counter() - start

    combined = result.stdout + result.stderr
    if engine_name == "cql6":
        matches, games = parse_cql6_output(combined)
    else:
        matches, games = parse_cqli_output(combined)

    # CQLi writes errors to stdout, CQL6 uses stderr
    error_output = (result.stdout + result.stderr).strip()
    return RunResult(
        engine=engine_name,
        cql_file=str(cql_file),
        elapsed=elapsed,
        matches=matches,
        games=games,
        returncode=result.returncode,
        stderr=error_output if result.returncode != 0 else "",
    )


def compare_outputs(pgn_a: Path, pgn_b: Path) -> bool:
    """Check if two PGN outputs have the same games (by game count)."""
    if not pgn_a.exists() or not pgn_b.exists():
        return False

    def count_games(p: Path) -> int:
        count = 0
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("[Event "):
                count += 1
        return count

    return count_games(pgn_a) == count_games(pgn_b)


def run_benchmark(
    cql_files: list[Path],
    pgn_input: Path,
    iterations: int,
    single_threaded: bool,
    cql6_bin: Path = CQL6_BIN,
    cqli_bin: Path = CQLI_BIN,
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for cql_file in cql_files:
            br = BenchmarkResult(cql_file=cql_file.name)
            cqli_file = convert_for_cqli(cql_file, tmp_dir)

            print(f"\n{'='*60}")
            print(f"  {cql_file.name}")
            print(f"{'='*60}")

            # First run: check if cqli can parse it
            cqli_out = Path(tmp_dir) / f"{cql_file.stem}_cqli_check.pgn"
            check = run_engine(
                cqli_bin, cqli_file, pgn_input, cqli_out,
                single_threaded=single_threaded,
            )
            if check.returncode != 0:
                br.cqli_syntax_error = check.stderr
                print(f"  CQLi SYNTAX ERROR: {check.stderr[:120]}")
                # Still benchmark CQL6
                for i in range(iterations):
                    cql6_out = Path(tmp_dir) / f"{cql_file.stem}_cql6_{i}.pgn"
                    r = run_engine(
                        cql6_bin, cql_file, pgn_input, cql6_out,
                        single_threaded=single_threaded,
                    )
                    br.cql6_times.append(r.elapsed)
                    if i == 0:
                        br.cql6_matches = r.matches
                results.append(br)
                continue

            # Benchmark both engines
            for i in range(iterations):
                cql6_out = Path(tmp_dir) / f"{cql_file.stem}_cql6_{i}.pgn"
                cqli_out = Path(tmp_dir) / f"{cql_file.stem}_cqli_{i}.pgn"

                r6 = run_engine(
                    cql6_bin, cql_file, pgn_input, cql6_out,
                    single_threaded=single_threaded,
                )
                ri = run_engine(
                    cqli_bin, cqli_file, pgn_input, cqli_out,
                    single_threaded=single_threaded,
                )

                br.cql6_times.append(r6.elapsed)
                br.cqli_times.append(ri.elapsed)

                if i == 0:
                    br.cql6_matches = r6.matches
                    br.cqli_matches = ri.matches
                    br.output_diff = not compare_outputs(cql6_out, cqli_out)

            # Print inline summary
            c6_mean = statistics.mean(br.cql6_times)
            ci_mean = statistics.mean(br.cqli_times)
            speedup = c6_mean / ci_mean if ci_mean > 0 else float("inf")
            match_ok = "SAME" if br.cql6_matches == br.cqli_matches else "DIFFER"
            out_ok = "DIFFER" if br.output_diff else "SAME"
            print(f"  CQL6:  {c6_mean:.4f}s (matches: {br.cql6_matches})")
            print(f"  CQLi:  {ci_mean:.4f}s (matches: {br.cqli_matches})")
            print(f"  Speedup: {speedup:.2f}x {'(CQLi faster)' if speedup > 1 else '(CQL6 faster)'}")
            print(f"  Match counts: {match_ok}  |  Output games: {out_ok}")

            results.append(br)

    return results


def print_summary(results: list[BenchmarkResult]) -> None:
    print(f"\n{'='*80}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*80}")
    print(
        f"{'Query':<30} {'CQL6 (s)':>10} {'CQLi (s)':>10} {'Speedup':>10} "
        f"{'Matches':>10} {'Notes'}"
    )
    print("-" * 90)

    speedups = []
    for br in results:
        c6 = statistics.mean(br.cql6_times) if br.cql6_times else float("nan")
        notes = []

        if br.cqli_syntax_error:
            ci_str = "ERROR"
            sp_str = "N/A"
            notes.append("syntax")
        elif br.cqli_times:
            ci = statistics.mean(br.cqli_times)
            ci_str = f"{ci:.4f}"
            sp = c6 / ci if ci > 0 else float("inf")
            sp_str = f"{sp:.2f}x"
            speedups.append(sp)
        else:
            ci_str = "N/A"
            sp_str = "N/A"

        if br.output_diff:
            notes.append("output-diff")
        if br.cql6_matches != br.cqli_matches and not br.cqli_syntax_error:
            notes.append("match-diff")

        match_str = (
            f"{br.cql6_matches}/{br.cqli_matches}"
            if not br.cqli_syntax_error
            else f"{br.cql6_matches}/-"
        )

        print(
            f"{br.cql_file:<30} {c6:>10.4f} {ci_str:>10} {sp_str:>10} "
            f"{match_str:>10} {', '.join(notes)}"
        )

    if speedups:
        geo_mean = statistics.geometric_mean(speedups)
        print("-" * 90)
        print(f"{'Geometric mean speedup':<30} {'':>10} {'':>10} {geo_mean:>9.2f}x")
        syntax_errors = sum(1 for br in results if br.cqli_syntax_error)
        if syntax_errors:
            print(f"  ({syntax_errors} queries had CQLi syntax errors)")


def write_csv(results: list[BenchmarkResult], path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "query", "cql6_mean_s", "cql6_stdev_s",
            "cqli_mean_s", "cqli_stdev_s", "speedup",
            "cql6_matches", "cqli_matches", "output_same", "cqli_syntax_error",
        ])
        for br in results:
            c6_mean = statistics.mean(br.cql6_times) if br.cql6_times else None
            c6_std = statistics.stdev(br.cql6_times) if len(br.cql6_times) > 1 else None
            ci_mean = statistics.mean(br.cqli_times) if br.cqli_times else None
            ci_std = statistics.stdev(br.cqli_times) if len(br.cqli_times) > 1 else None
            sp = (c6_mean / ci_mean) if (c6_mean and ci_mean) else None
            w.writerow([
                br.cql_file,
                f"{c6_mean:.6f}" if c6_mean else "",
                f"{c6_std:.6f}" if c6_std else "",
                f"{ci_mean:.6f}" if ci_mean else "",
                f"{ci_std:.6f}" if ci_std else "",
                f"{sp:.4f}" if sp else "",
                br.cql6_matches,
                br.cqli_matches,
                not br.output_diff if not br.cqli_syntax_error else "",
                br.cqli_syntax_error or "",
            ])
    print(f"\nCSV written to {path}")


def collect_cql_files(paths: list[str]) -> list[Path]:
    """Expand directories and glob patterns into CQL file list."""
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.glob("*.cql")))
        else:
            # Try glob
            files.extend(sorted(Path(".").glob(p)))
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark CQL6 vs CQLi")
    parser.add_argument(
        "cql_files", nargs="+",
        help="CQL files or directories to benchmark",
    )
    parser.add_argument(
        "-i", "--input", required=True,
        help="Input PGN file",
    )
    parser.add_argument(
        "-n", "--iterations", type=int, default=5,
        help="Number of iterations per query (default: 5)",
    )
    parser.add_argument(
        "-s", "--single-threaded", action="store_true",
        help="Run in single-threaded mode",
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Write results to CSV file",
    )
    parser.add_argument(
        "--cql6", type=str, default=str(CQL6_BIN),
        help=f"Path to CQL6 binary (default: {CQL6_BIN})",
    )
    parser.add_argument(
        "--cqli", type=str, default=str(CQLI_BIN),
        help=f"Path to CQLi binary (default: {CQLI_BIN})",
    )
    args = parser.parse_args()

    cql6_bin = Path(args.cql6)
    cqli_bin = Path(args.cqli)

    pgn_input = Path(args.input)
    if not pgn_input.exists():
        print(f"Error: PGN file not found: {pgn_input}", file=sys.stderr)
        sys.exit(1)

    for name, binary in [("CQL6", cql6_bin), ("CQLi", cqli_bin)]:
        if not binary.exists():
            print(f"Error: {name} binary not found: {binary}", file=sys.stderr)
            sys.exit(1)

    cql_files = collect_cql_files(args.cql_files)
    if not cql_files:
        print("Error: No CQL files found", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmarking {len(cql_files)} queries x {args.iterations} iterations")
    print(f"PGN input: {pgn_input} ({pgn_input.stat().st_size / 1024:.0f} KB)")
    print(f"CQL6: {cql6_bin}")
    print(f"CQLi: {cqli_bin}")
    print(f"Mode: {'single-threaded' if args.single_threaded else 'multi-threaded'}")

    results = run_benchmark(
        cql_files, pgn_input, args.iterations, args.single_threaded,
        cql6_bin=cql6_bin, cqli_bin=cqli_bin,
    )

    print_summary(results)

    if args.csv:
        write_csv(results, Path(args.csv))


if __name__ == "__main__":
    main()
