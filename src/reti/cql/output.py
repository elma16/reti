"""Summary CSV writing and output merging for CQL matrix runs."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from reti.common.pgn_discovery import (
    InputCollection,
    format_relative,
    relative_stem,
)
from reti.cql.preflight import count_games_in_pgn
from reti.cql.runner import JobResult


JobOutputKey = tuple[Path, Path, Path]


def job_output_key(result: JobResult) -> JobOutputKey:
    return result.pgn_path, result.cql_path, result.output_pgn


def _format_output_path(path: Path, output_dir: Path) -> str:
    try:
        return str(path.relative_to(output_dir))
    except ValueError:
        return str(path)


def _first_nonempty_line(*texts: str) -> str:
    for text in texts:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    return ""


def write_summary_csv(
    results: list[JobResult],
    output_dir: Path,
    pgn_root: Path,
    cql_root: Path,
    *,
    output_paths: dict[JobOutputKey, Path] | None = None,
) -> Path:
    summary_path = output_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "pgn",
                "cql",
                "output_pgn",
                "pair_output_pgn",
                "status",
                "match_count",
                "returncode",
                "duration_seconds",
                "timed_out",
                "missing_output",
                "stdout_bytes",
                "stderr_bytes",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            final_output = (
                output_paths.get(job_output_key(result), result.output_pgn)
                if output_paths is not None
                else result.output_pgn
            )
            writer.writerow(
                {
                    "pgn": format_relative(result.pgn_path, pgn_root),
                    "cql": format_relative(result.cql_path, cql_root),
                    "output_pgn": _format_output_path(final_output, output_dir),
                    "pair_output_pgn": _format_output_path(result.output_pgn, output_dir),
                    "status": "ok" if result.success else "error",
                    "match_count": (
                        "" if result.match_count is None else str(result.match_count)
                    ),
                    "returncode": str(result.returncode),
                    "duration_seconds": f"{result.duration_seconds:.3f}",
                    "timed_out": "yes" if result.timed_out else "no",
                    "missing_output": "yes" if result.missing_output else "no",
                    "stdout_bytes": str(len(result.stdout.encode("utf-8"))),
                    "stderr_bytes": str(len(result.stderr.encode("utf-8"))),
                    "error": "" if result.success else _first_nonempty_line(result.stderr, result.stdout),
                }
            )
    return summary_path


def merge_outputs_by_cql(
    results: list[JobResult],
    cql_inputs: InputCollection,
    output_dir: Path,
) -> list[Path]:
    """Concatenate per-PGN output files into one merged file per CQL script.

    After merging, the individual per-pair output files are removed so the
    output directory contains only the merged PGNs and ``summary.csv``.
    """
    by_cql: dict[Path, list[Path]] = defaultdict(list)
    for result in results:
        if result.success and result.output_pgn.exists():
            by_cql[result.cql_path].append(result.output_pgn)

    merged_paths: list[Path] = []
    all_per_pair_files: list[Path] = []

    for cql_path in cql_inputs.files:
        output_pgns = by_cql.get(cql_path, [])
        if not output_pgns:
            continue
        all_per_pair_files.extend(output_pgns)
        merged_name = relative_stem(cql_path, cql_inputs.root)
        merged_path = output_dir / f"{merged_name}.pgn"
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        with merged_path.open("w", encoding="utf-8") as out:
            for pgn_path in output_pgns:
                with pgn_path.open("r", encoding="utf-8", errors="replace") as inp:
                    content = inp.read()
                    out.write(content)
                    if content and not content.endswith("\n\n"):
                        out.write("\n\n" if not content.endswith("\n") else "\n")
        total_games = count_games_in_pgn(merged_path)
        print(
            f"Merged {len(output_pgns)} file(s) into {merged_path} ({total_games} game(s))"
        )
        merged_paths.append(merged_path)

    removed_dirs: set[Path] = set()
    for per_pair in all_per_pair_files:
        if per_pair.exists():
            removed_dirs.add(per_pair.parent)
            per_pair.unlink()
    for directory in sorted(removed_dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            if (
                directory != output_dir
                and directory.exists()
                and not any(directory.iterdir())
            ):
                directory.rmdir()
        except OSError:
            pass

    return merged_paths
