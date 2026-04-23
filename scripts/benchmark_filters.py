#!/usr/bin/env python3
"""Benchmark individual CQL filters by timing minimal scripts against a PGN.

Usage:
    python scripts/benchmark_filters.py \
        --pgn lumbra-gigabase/LumbrasGigaBase_OTB_1900-1949.pgn \
        --cql-bin cql-bin/cql6-2/cql \
        --runs 3

Each filter gets a tiny CQL script that exercises it in isolation.  The script
measures wall-clock time for each, subtracts the baseline (bare `cql()`), and
ranks filters by marginal cost.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Filter definitions: (name, cql_body)
#
# Each body is inserted inside  cql()\n<body>
# Filters that cannot be benchmarked in isolation (e.g. require special PGN
# setup, file I/O, or are control-flow only) are skipped.
# ---------------------------------------------------------------------------

# Each spec: (name, cql_body, binary_compat)
#   binary_compat: "all" = CQL6.1 + CQLi, "cqli" = CQLi only
FILTER_SPECS: list[tuple[str, str, str]] = [
    # -- baseline --
    ("baseline", "true", "all"),

    # -- board state --
    ("check", "check", "all"),
    ("mate", "mate", "all"),
    ("stalemate", "stalemate", "all"),
    ("btm", "btm", "all"),
    ("wtm", "wtm", "all"),
    ("initial", "initial", "all"),
    ("terminal", "terminal", "all"),

    # -- piece counting --
    ("piece_count_pawns", "[Pp] == 4", "all"),
    ("piece_count_all", "#[Aa] == 10", "all"),
    ("piece_count_queens", "[Qq] == 0", "all"),
    ("piece_count_rooks", "[Rr] == 2", "all"),

    # -- pawn structure --
    ("passedpawns", "#passedpawns >= 1", "all"),
    ("isolatedpawns", "#isolatedpawns >= 1", "all"),
    ("doubledpawns", "#doubledpawns >= 1", "all"),
    ("connectedpawns", "#connectedpawns >= 2", "all"),

    # -- attacks / attacked-by --
    ("attacks_basic", "K attacks k", "all"),
    ("attackedby_basic", "k attackedby [Rr]", "all"),

    # -- ray filters --
    ("ray_rook", "ray(R . k)", "all"),
    ("ray_bishop", "ray(diagonal B . k)", "all"),
    ("pin", "pin from [RNBQ] through [rnbq] to k", "all"),
    ("xray", "xray(R . k)", "all"),

    # -- between --
    ("between", "#between(K k) >= 3", "all"),

    # -- direction rays --
    ("up", "#up(K) >= 1", "all"),
    ("down", "#down(K) >= 1", "all"),
    ("left", "#left(K) >= 1", "all"),
    ("right", "#right(K) >= 1", "all"),
    ("northeast", "#northeast(K) >= 1", "all"),
    ("diagonal", "#diagonal(K) >= 1", "all"),
    ("orthogonal", "#orthogonal(K) >= 1", "all"),
    ("horizontal", "#horizontal(K) >= 1", "all"),
    ("vertical", "#vertical(K) >= 1", "all"),

    # -- board geometry --
    ("dark", "dark K", "all"),
    ("light", "light K", "all"),
    ("file_rank", "file(K) == 4", "all"),
    ("makesquare", 'makesquare("e4") in [Pp]', "all"),

    # -- power --
    ("power", "power([Aa]) > power([aa])", "all"),

    # -- move number / ply --
    ("movenumber", "movenumber >= 40", "all"),
    ("ply", "ply >= 80", "all"),
    ("halfmoveclock", "halfmoveclock >= 10", "cqli"),

    # -- FEN --
    ("currentfen", 'currentfen ~~ ".*K.*R.*k.*r.*"', "cqli"),
    ("standardfen", 'standardfen ~~ ".*K.*R.*k.*r.*"', "cqli"),

    # -- metadata filters --
    ("result_white", "result 1-0", "all"),
    ("result_draw", "result 1/2-1/2", "all"),
    ("gamenumber", "gamenumber <= 1000", "all"),

    # -- type / colortype --
    ("type", "type(e4) == 1", "all"),
    ("colortype", "colortype(e4) >= 0", "all"),

    # -- find (inter-position) --
    ("find_mate", "find(mate)", "all"),
    ("find_check", "find(check)", "all"),
    ("find_all", "find all { Q attacks k }", "all"),

    # -- line (sequence) --
    ("line_short", "line --> check --> mate", "all"),
    ("line_captures", "line --> move capture [Qq] --> .", "all"),
    ("line_consec_knight", "line --> move from [Nn] --> move from [Nn] --> .", "all"),

    # -- move filter --
    ("move_any", "move from [Nn] to .", "all"),
    ("move_capture", "move capture [Pp]", "all"),
    ("move_promotion", "move promote [Qq]", "all"),
    ("move_enpassant", "move enpassant", "all"),
    ("move_castles", "move primary o-o", "all"),

    # -- transforms --
    ("flipcolor", "flipcolor { mate K attacks [rnbq] }", "all"),
    ("flipvertical", "flipvertical { Ka1 }", "all"),
    ("fliphorizontal", "fliphorizontal { Ka1 }", "all"),
    ("flip", "flip { Ka1 Bb2 }", "all"),
    ("shift", "shift { Ka1 Bb2 }", "all"),
    ("rotate90", "rotate90 { Ka1 Bb2 }", "all"),
    ("rotate45", "rotate45 { Ka1 Bb2 }", "cqli"),

    # -- sort --
    ("sort_power", 'sort "power" power([Aa])', "all"),

    # -- zobristkey --
    ("zobristkey", "zobristkey", "cqli"),

    # -- promoted pieces --
    ("promotedpieces", "#promotedpieces >= 1", "cqli"),

    # -- string operations --
    ("str_concat", 'str(movenumber) + "x" ~~ ".*x"', "cqli"),
    ("lowercase", 'lowercase("HELLO") == "hello"', "cqli"),
    ("uppercase", 'uppercase("hello") == "HELLO"', "cqli"),

    # -- position relationships --
    ("mainline", "mainline", "all"),
    ("depth", "depth == 0", "cqli"),
    ("positionid", "positionid >= 0", "cqli"),

    # -- math --
    ("sqrt", "sqrt(64) == 8", "all"),
    ("abs", "abs(-1) == 1", "all"),
    ("max_min", "max(1 2) == 2", "cqli"),

    # -- square iteration --
    ("square_iter", "square all S in [Pp] { rank(S) >= 5 }", "all"),

    # -- piece iteration --
    ("piece_iter", "piece all X in [Rr] { file(X) == file(K) }", "all"),

    # -- if --
    ("if_filter", "if check then mate", "all"),

    # -- CQLi-only advanced --
    ("legalposition", "legalposition", "cqli"),
    ("reachableposition", "reachableposition", "cqli"),
    ("pieceid", "pieceid(e1) >= 0", "cqli"),
    ("sidetomove", "sidetomove == 1", "cqli"),
]


@dataclass
class BenchResult:
    name: str
    avg_seconds: float
    min_seconds: float
    max_seconds: float
    runs: int
    matches: int | None
    success: bool
    error: str


def run_one(
    cql_bin: Path,
    pgn: Path,
    cql_body: str,
    *,
    singlethreaded: bool = False,
) -> tuple[float, int | None, bool, str]:
    script = f"cql()\n{cql_body}\n"
    with tempfile.NamedTemporaryFile(
        suffix=".cql", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        cql_path = Path(f.name)

    with tempfile.NamedTemporaryFile(suffix=".pgn", delete=False) as out_f:
        out_path = Path(out_f.name)

    cmd = [str(cql_bin), "-i", str(pgn), "-o", str(out_path)]
    if singlethreaded:
        cmd.append("-s")
    cmd.append(str(cql_path))

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300,
        )
    except subprocess.TimeoutExpired:
        cql_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)
        return 300.0, None, False, "TIMEOUT (300s)"
    elapsed = time.perf_counter() - t0

    matches = None
    success = proc.returncode == 0
    error = ""
    if success:
        combined = proc.stdout + proc.stderr
        # CQL: "N matches of M games"  /  CQLi: "N CQL matches"
        import re
        m = re.search(r"(\d+)\s+(?:CQL )?match", combined)
        if m:
            matches = int(m.group(1))
    else:
        error = (proc.stderr or proc.stdout or "").strip()[:200]

    cql_path.unlink(missing_ok=True)
    out_path.unlink(missing_ok=True)
    return elapsed, matches, success, error


def detect_binary_type(cql_bin: Path) -> str:
    """Return 'cqli' or 'cql6' based on --version output."""
    try:
        proc = subprocess.run(
            [str(cql_bin), "--version"],
            capture_output=True, text=True, timeout=10,
        )
        combined = proc.stdout + proc.stderr
        if "CQLi" in combined:
            return "cqli"
    except Exception:
        pass
    return "cql6"


def benchmark(
    cql_bin: Path,
    pgn: Path,
    runs: int,
    singlethreaded: bool,
) -> list[BenchResult]:
    binary_type = detect_binary_type(cql_bin)
    print(f"Detected binary type: {binary_type}")

    specs = [
        (name, body) for name, body, compat in FILTER_SPECS
        if compat == "all" or compat == binary_type
    ]
    skipped = len(FILTER_SPECS) - len(specs)
    if skipped:
        print(f"Skipping {skipped} filter(s) incompatible with {binary_type}")

    results: list[BenchResult] = []
    total = len(specs)

    for idx, (name, body) in enumerate(specs, 1):
        sys.stderr.write(f"\r[{idx}/{total}] {name:<30}")
        sys.stderr.flush()

        timings: list[float] = []
        last_matches: int | None = None
        last_success = True
        last_error = ""

        for _ in range(runs):
            elapsed, matches, success, error = run_one(
                cql_bin, pgn, body, singlethreaded=singlethreaded,
            )
            if not success:
                last_success = False
                last_error = error
                break
            timings.append(elapsed)
            last_matches = matches

        if timings:
            results.append(BenchResult(
                name=name,
                avg_seconds=sum(timings) / len(timings),
                min_seconds=min(timings),
                max_seconds=max(timings),
                runs=len(timings),
                matches=last_matches,
                success=True,
                error="",
            ))
        else:
            results.append(BenchResult(
                name=name,
                avg_seconds=0,
                min_seconds=0,
                max_seconds=0,
                runs=0,
                matches=None,
                success=False,
                error=last_error,
            ))

    sys.stderr.write("\r" + " " * 60 + "\r")
    return results


def print_results(results: list[BenchResult]) -> None:
    baseline = next((r for r in results if r.name == "baseline"), None)
    baseline_avg = baseline.avg_seconds if baseline and baseline.success else 0

    successful = [r for r in results if r.success and r.name != "baseline"]
    successful.sort(key=lambda r: r.avg_seconds, reverse=True)

    print(f"\nBaseline (bare cql()): {baseline_avg:.3f}s\n")
    print(f"{'Rank':<5} {'Filter':<30} {'Avg (s)':<10} {'Marginal':<10} "
          f"{'Slowdown':<10} {'Matches':<10} {'Min':<10} {'Max':<10}")
    print("-" * 95)

    for rank, r in enumerate(successful, 1):
        marginal = r.avg_seconds - baseline_avg
        slowdown = r.avg_seconds / baseline_avg if baseline_avg > 0 else 0
        matches_str = str(r.matches) if r.matches is not None else "?"
        print(f"{rank:<5} {r.name:<30} {r.avg_seconds:<10.3f} "
              f"{marginal:<+10.3f} {slowdown:<10.2f}x "
              f"{matches_str:<10} {r.min_seconds:<10.3f} {r.max_seconds:<10.3f}")

    failed = [r for r in results if not r.success]
    if failed:
        print(f"\n--- Failed ({len(failed)}) ---")
        for r in failed:
            print(f"  {r.name}: {r.error[:100]}")


def write_csv(results: list[BenchResult], path: Path) -> None:
    baseline = next((r for r in results if r.name == "baseline"), None)
    baseline_avg = baseline.avg_seconds if baseline and baseline.success else 0

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "filter", "avg_seconds", "marginal_seconds", "slowdown_factor",
            "matches", "min_seconds", "max_seconds", "runs", "success", "error",
        ])
        for r in results:
            marginal = r.avg_seconds - baseline_avg if r.success else ""
            slowdown = (r.avg_seconds / baseline_avg
                        if r.success and baseline_avg > 0 else "")
            writer.writerow([
                r.name, f"{r.avg_seconds:.4f}", marginal, slowdown,
                r.matches if r.matches is not None else "",
                f"{r.min_seconds:.4f}", f"{r.max_seconds:.4f}",
                r.runs, r.success, r.error,
            ])
    print(f"\nCSV written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pgn", required=True, help="PGN file to benchmark against")
    parser.add_argument("--cql-bin", required=True, help="Path to CQL binary")
    parser.add_argument("--runs", type=int, default=3, help="Runs per filter (default 3)")
    parser.add_argument("--csv", default=None, help="Write results to CSV file")
    parser.add_argument(
        "-s", "--singlethreaded", action="store_true",
        help="Run CQL in single-threaded mode for more stable timing",
    )
    args = parser.parse_args()

    cql_bin = Path(args.cql_bin).expanduser()
    pgn = Path(args.pgn).expanduser()

    if not cql_bin.exists():
        print(f"Error: CQL binary not found: {cql_bin}")
        return 1
    if not pgn.exists():
        print(f"Error: PGN file not found: {pgn}")
        return 1

    print(f"CQL binary: {cql_bin}")
    print(f"PGN: {pgn}")
    print(f"Runs per filter: {args.runs}")
    print(f"Filters to test: {len(FILTER_SPECS)}")
    print(f"Single-threaded: {args.singlethreaded}")

    results = benchmark(cql_bin, pgn, args.runs, args.singlethreaded)
    print_results(results)

    if args.csv:
        write_csv(results, Path(args.csv))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
