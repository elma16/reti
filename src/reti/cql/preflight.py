"""PGN preflight: cheap validation + sanitized-temp creation before the matrix run.

The matrix run sees an arbitrary user-supplied directory of PGNs. Older CQL
builds abort hard on byte-level garbage (BOMs, invalid UTF-8, control chars),
which kills the whole batch. Preflight catches that once per PGN and either
points the runner at a sanitized temp copy or fails the whole run before any
real work happens.
"""

from __future__ import annotations

import io
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import chess.pgn as chess_pgn
from tqdm import tqdm as tqdm_progress

from reti.cql.backend import CqlBackend
from reti.common.pgn_discovery import InputCollection, format_relative
from reti.common.progress import format_progress_label, progress_write
from reti.common.subprocess_helpers import describe_returncode
from reti.pgn_utils import (
    FastPgnRewriteStats,
    inspect_pgn_fast,
    rewrite_pgn_fast,
)


@dataclass(frozen=True)
class PgnPreflightResult:
    pgn_path: Path
    runtime_pgn_path: Path
    success: bool
    sanitized: bool
    message: str


def count_games_in_pgn(pgn_file_path: str | Path) -> int:
    """Count games in a PGN by scanning for ``[Event `` tags."""
    try:
        with open(pgn_file_path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.startswith("[Event "))
    except FileNotFoundError:
        print(f"Error: PGN file not found for counting: {pgn_file_path}")
        return 0
    except Exception as exc:
        print(f"Error reading PGN file {pgn_file_path}: {exc}")
        return 0


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def issues_from_fast_stats(stats: FastPgnRewriteStats) -> list[str]:
    issues: list[str] = []
    if stats.removed_bom:
        issues.append("starts with a UTF-8 BOM")
    if stats.invalid_utf8_replaced:
        issues.append(
            f"contains {stats.invalid_utf8_replaced} invalid UTF-8 replacement character(s)"
        )
    if stats.control_characters_removed:
        issues.append(
            f"contains {stats.control_characters_removed} control character(s)"
        )
    return issues


def inspect_pgn_text_compatibility(pgn_path: Path) -> list[str]:
    """Find text/byte issues that can make older CQL builds abort on specific PGNs."""
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
            replacement_count += chunk.count("�")
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
    """Create a sanitized temp PGN, preserving comments + variations.

    The fast repair pipeline does the byte-level scrub (BOM, invalid UTF-8,
    control chars) we want here without touching markup, since CQL scripts
    using ``{CQL}`` markers need their comments intact.
    """
    destination = runtime_root / pgn_path.relative_to(pgn_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rewrite_pgn_fast(pgn_path, destination, preserve_markup=True)
    return destination


def validate_pgn_with_python_parser(pgn_path: Path) -> str | None:
    """Surface the first parser error from python-chess."""
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
    backend: CqlBackend,
    pgn_path: Path,
    smoke_script: Path,
    smoke_output: Path,
) -> tuple[int, str, str]:
    if smoke_output.exists():
        smoke_output.unlink()

    process = subprocess.run(
        backend.build_run_command(
            pgn_path,
            smoke_script,
            smoke_output,
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.returncode, process.stdout, process.stderr


def preflight_pgn_files(
    pgn_inputs: InputCollection,
    backend: CqlBackend,
    runtime_root: Path,
    *,
    smoke_test_pgns: bool = False,
    strict_pgn_parse: bool = False,
) -> list[PgnPreflightResult]:
    """Validate each PGN once before the full matrix run."""
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

        try:
            inspect_stats = inspect_pgn_fast(pgn_path)
        except Exception as exc:
            inspect_stats = None
            progress_write(
                f"Fast inspect failed for {relative_name}, falling back: {exc}"
            )

        if inspect_stats is not None:
            text_issues = issues_from_fast_stats(inspect_stats)
            event_count = inspect_stats.games_written
        else:
            text_issues = inspect_pgn_text_compatibility(pgn_path)
            event_count = count_games_in_pgn(pgn_path)

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
                backend,
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
