"""
repair_pgn_v2.py — fast single-pass PGN repair.

Same public API as repair_pgn.py.  Drop-in replacement for benchmarking.

What changed vs v1
------------------
v1 pipeline (two passes, two temp files on disk):
    source.pgn
      → [sanitize: char-by-char Python loop]     → sanitized.pgn  (fsync)
      → [normalize: python-chess read+rewrite,
         strips comments AND variations]          → repaired.pgn   (fsync)

v2 pipeline (one pass, one temp file):
    source.pgn
      → [sanitize: str.translate at C speed,
         encoding repair ONLY — content preserved] → repaired.pgn  (one fsync)

Why no markup stripping in v2:
  v1 stripped comments and variations as a side-effect of running every game
  through python-chess's FileExporter.  That is unnecessary for CQL
  compatibility (CQL handles both) and on a heavily-annotated database it
  reduces a 1+ GB file to tens of MB — discarding real chess content.
  v2 only removes what actually breaks parsers: BOMs, invalid UTF-8, and
  ASCII control characters.

Key improvements over v1:
  - str.translate()  replaces the char-by-char Python loop → C-speed filtering
  - No intermediate sanitized.pgn written to disk
  - One fsync instead of two
  - Peak memory ~2–3 MB regardless of input size
"""

from __future__ import annotations

import argparse
import codecs
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import chess.pgn as chess_pgn  # still used for the optional CQL smoke test

from tqdm import tqdm as tqdm_progress


# ---------------------------------------------------------------------------
# Module-level constants (built once)
# ---------------------------------------------------------------------------

# Keep \t (9), \n (10), \r (13).  Delete everything else < 32, plus DEL (127).
_SANITIZE_TABLE = str.maketrans(
    {
        "\ufffd": "?",
        **{chr(cp): None for cp in range(32) if cp not in (9, 10, 13)},
        chr(127): None,
    }
)

# Used only for counting before the translate wipes them.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Finds every PGN markup delimiter for the optional strip-markup pass.
_MARKUP_TOKEN = re.compile(r"[{}()]")

# Matches { and } only — used by the brace-repair pass.
_BRACE_RE = re.compile(r"[{}]")


# ---------------------------------------------------------------------------
# Shared data-classes and utilities (identical to repair_pgn.py)
# ---------------------------------------------------------------------------


def progress_write(message: str) -> None:
    tqdm_progress.write(make_terminal_safe(message))


def make_terminal_safe(text: str) -> str:
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
    safe = (
        make_terminal_safe(text)
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
    )
    if len(safe) <= max_length:
        return safe
    head = max(10, max_length // 2 - 2)
    tail = max(10, max_length - head - 3)
    return f"{safe[:head]}...{safe[-tail:]}"


@dataclass(frozen=True)
class TextSanitizationStats:
    removed_bom: bool
    invalid_utf8_replaced: int
    control_characters_removed: int


@dataclass(frozen=True)
class PgnNormalizationStats:
    games_written: int
    parser_error_games: int  # always 0 in v2 (not tracked without python-chess)
    parser_errors: int       # always 0 in v2


@dataclass(frozen=True)
class PgnRepairResult:
    pgn_path: Path
    backup_path: Path | None
    sanitization: TextSanitizationStats
    normalization: PgnNormalizationStats
    smoke_test_message: str | None


def describe_returncode(returncode: int) -> str:
    if returncode >= 0:
        return f"return code {returncode}"
    signal_number = -returncode
    try:
        signal_name = signal.Signals(signal_number).name
    except ValueError:
        signal_name = f"SIG{signal_number}"
    return f"terminated by signal {signal_number} ({signal_name})"


def resolve_cql_binary(cql_binary: str) -> Path | None:
    candidate = Path(cql_binary).expanduser()
    if candidate.is_file():
        return candidate
    on_path = shutil.which(cql_binary)
    if on_path:
        return Path(on_path)
    print(f"Error: CQL binary not found: '{cql_binary}'")
    return None


def discover_pgn_files(location: str) -> list[Path] | None:
    path = Path(location).expanduser()
    if path.is_file():
        if path.suffix.lower() != ".pgn":
            print(f"Error: '{location}' is not a .pgn file.")
            return None
        return [path]
    if path.is_dir():
        files = sorted(
            (
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() == ".pgn"
            ),
            key=lambda item: str(item.relative_to(path)),
        )
        if not files:
            print(f"Error: No .pgn files found under '{location}'.")
            return None
        return files
    print(f"Error: '{location}' is not a valid file or directory.")
    return None


def format_pgn_display_path(pgn_path: Path, root: Path | None) -> str:
    if root is None:
        return pgn_path.name
    try:
        return str(pgn_path.relative_to(root))
    except ValueError:
        return pgn_path.name


def count_games_in_pgn(pgn_file_path: Path) -> int:
    try:
        with pgn_file_path.open("r", encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.startswith("[Event "))
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Brace repair (always-on) — removes nested { inside PGN comments
# ---------------------------------------------------------------------------


def _fix_braces_chunk(
    chunk: str,
    out: list[str],
    in_comment: bool,
) -> bool:
    """
    Remove any ``{`` that appears inside a ``{…}`` PGN comment.

    CQL (and some other readers) treat a nested ``{`` as opening a second
    comment.  The single ``}`` then only closes the inner one, leaving the
    outer comment unclosed — which causes CQL to read the rest of the file
    as one huge comment and eventually overflow its buffer.

    Removing the nested ``{`` preserves the comment text while making the
    PGN structurally valid.  State (*in_comment*) is carried across chunks.
    """
    pos = 0
    for m in _BRACE_RE.finditer(chunk):
        c = m.group()
        s = m.start()

        if in_comment:
            if c == "}":
                # close comment — emit everything up to and including }
                out.append(chunk[pos : m.end()])
                pos = m.end()
                in_comment = False
            else:
                # nested { — emit text before it, skip the {
                out.append(chunk[pos:s])
                pos = m.end()
        else:
            if c == "{":
                # normal open — emit up to and including {
                out.append(chunk[pos : m.end()])
                pos = m.end()
                in_comment = True
            # stray } in normal state: pass through unchanged

    out.append(chunk[pos:])
    return in_comment


# ---------------------------------------------------------------------------
# Optional markup stripping (used only with --strip-markup)
# ---------------------------------------------------------------------------


def _process_markup_chunk(
    chunk: str,
    out: list[str],
    depth: int,
    in_comment: bool,
) -> tuple[int, bool]:
    """
    Scan one sanitized chunk, strip {comments} and (variations), append
    normal text to *out*.  State (depth, in_comment) is carried between calls
    so tokens spanning chunk boundaries are handled correctly.
    """
    pos = 0
    for m in _MARKUP_TOKEN.finditer(chunk):
        c = m.group()
        s = m.start()

        if in_comment:
            if c == "}":
                in_comment = False
                pos = m.end()

        elif depth:
            if c == "{":
                in_comment = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if not depth:
                    pos = m.end()

        else:
            out.append(chunk[pos:s])
            pos = m.end()
            if c == "{":
                in_comment = True
            elif c == "(":
                depth = 1
            # stray ) or } in normal state: skip the delimiter

    if not in_comment and not depth:
        out.append(chunk[pos:])

    return depth, in_comment


# ---------------------------------------------------------------------------
# Core: single-pass encoding repair
# ---------------------------------------------------------------------------


def sanitize_pgn(
    source_path: Path,
    dest_path: Path,
    *,
    strip_markup: bool = False,
) -> TextSanitizationStats:
    """
    Read *source_path* in 1 MB binary chunks, decode UTF-8 with error
    replacement, remove the BOM and control characters via str.translate,
    normalise line endings, and write clean output to *dest_path*.

    If *strip_markup* is True, also strip PGN {comments} and (variations)
    using a re.finditer state machine.  Required for CQL compatibility when
    the source database contains games with very large annotations.

    No intermediate file is created.  Peak memory is ~2–3 MB.
    """
    removed_bom = False
    invalid_utf8_replaced = 0
    control_characters_removed = 0

    progress = tqdm_progress(
        total=source_path.stat().st_size,
        desc=f"Repairing {format_progress_label(source_path.name, max_length=48)}",
        unit="B",
        unit_scale=True,
        dynamic_ncols=sys.stderr.isatty(),
        file=sys.stderr,
    )

    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    first_chunk = True
    # Brace-repair state (always on)
    brace_in_comment = False
    # Strip-markup state (only when strip_markup=True)
    depth = 0
    strip_in_comment = False

    with (
        source_path.open("rb") as src,
        dest_path.open("w", encoding="utf-8", newline="\n") as dst,
    ):
        while True:
            raw = src.read(1024 * 1024)
            if not raw:
                break

            progress.update(len(raw))

            if first_chunk and raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
                removed_bom = True
            first_chunk = False

            text = decoder.decode(raw)

            # Count before wiping (C-level operations)
            invalid_utf8_replaced += text.count("\ufffd")
            control_characters_removed += len(_CONTROL_RE.findall(text))

            # Sanitize and normalise line endings at C speed
            sanitized = text.translate(_SANITIZE_TABLE)
            sanitized = sanitized.replace("\r\n", "\n").replace("\r", "\n")

            # Always fix nested braces (removes { inside {…} comments)
            brace_out: list[str] = []
            brace_in_comment = _fix_braces_chunk(sanitized, brace_out, brace_in_comment)
            sanitized = "".join(brace_out)

            if strip_markup:
                out: list[str] = []
                depth, strip_in_comment = _process_markup_chunk(
                    sanitized, out, depth, strip_in_comment
                )
                dst.write("".join(out))
            else:
                dst.write(sanitized)

        final_text = decoder.decode(b"", final=True)
        if final_text:
            invalid_utf8_replaced += final_text.count("\ufffd")
            control_characters_removed += len(_CONTROL_RE.findall(final_text))
            sanitized = final_text.translate(_SANITIZE_TABLE)
            sanitized = sanitized.replace("\r\n", "\n").replace("\r", "\n")

            brace_out = []
            brace_in_comment = _fix_braces_chunk(sanitized, brace_out, brace_in_comment)
            sanitized = "".join(brace_out)

            if strip_markup:
                out = []
                depth, strip_in_comment = _process_markup_chunk(
                    sanitized, out, depth, strip_in_comment
                )
                dst.write("".join(out))
            else:
                dst.write(sanitized)

        dst.flush()
        os.fsync(dst.fileno())

    progress.close()

    return TextSanitizationStats(
        removed_bom=removed_bom,
        invalid_utf8_replaced=invalid_utf8_replaced,
        control_characters_removed=control_characters_removed,
    )


# ---------------------------------------------------------------------------
# CQL smoke test (unchanged from v1)
# ---------------------------------------------------------------------------


def smoke_test_pgn_with_cql(
    cql_binary: Path,
    pgn_path: Path,
    smoke_script: Path,
    smoke_output: Path,
    *,
    lineincrement: int = 1000,
) -> int:
    command = [
        str(cql_binary),
        "-lineincrement",
        str(lineincrement),
        "-input",
        str(pgn_path),
        "-output",
        str(smoke_output),
        str(smoke_script),
    ]
    process = subprocess.run(command)
    return process.returncode


def validate_with_cql_smoke_test(
    cql_binary: Path,
    pgn_path: Path,
    *,
    lineincrement: int = 1000,
) -> str:
    progress_write(
        "Running CQL smoke test on repaired PGN: "
        f"{format_progress_label(pgn_path.name, max_length=64)}"
    )
    with tempfile.TemporaryDirectory(prefix="cql_smoke_") as tmpdir:
        tmp_path = Path(tmpdir)
        smoke_script = tmp_path / "smoke_check.cql"
        smoke_output = tmp_path / "smoke_output.pgn"
        smoke_script.write_text("cql() check\n", encoding="utf-8")
        returncode = smoke_test_pgn_with_cql(
            cql_binary,
            pgn_path,
            smoke_script,
            smoke_output,
            lineincrement=lineincrement,
        )
    if returncode != 0:
        detail = describe_returncode(returncode)
        raise RuntimeError(
            f"CQL smoke test failed ({detail})"
            "; see terminal output above for CQL details"
        )
    return "CQL smoke test passed"


# ---------------------------------------------------------------------------
# File finalisation (unchanged from v1)
# ---------------------------------------------------------------------------


def finalize_in_place_repair(
    original_path: Path,
    repaired_path: Path,
    *,
    backup_suffix: str | None,
    overwrite_backup: bool,
) -> Path | None:
    shutil.copymode(original_path, repaired_path)

    if backup_suffix is None:
        os.replace(repaired_path, original_path)
        return None

    backup_path = original_path.with_name(original_path.name + backup_suffix)
    if backup_path.exists():
        if not overwrite_backup:
            raise FileExistsError(
                f"Backup path already exists: {backup_path}. "
                "Pass --overwrite-backup or choose a different suffix."
            )
        if backup_path.is_dir():
            raise IsADirectoryError(f"Backup path is a directory: {backup_path}")
        backup_path.unlink()

    os.replace(original_path, backup_path)
    try:
        os.replace(repaired_path, original_path)
    except Exception:
        os.replace(backup_path, original_path)
        raise

    return backup_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def repair_pgn_file_in_place(
    pgn_path: Path,
    *,
    backup_suffix: str | None = ".bak",
    overwrite_backup: bool = False,
    cql_binary: Path | None = None,
    cql_lineincrement: int = 1000,
    strip_markup: bool = False,
) -> PgnRepairResult:
    if not pgn_path.exists():
        raise FileNotFoundError(f"PGN file not found: {pgn_path}")

    with tempfile.TemporaryDirectory(
        prefix=f".{pgn_path.stem}.repair_",
        dir=pgn_path.parent,
    ) as tmpdir:
        repaired_path = Path(tmpdir) / "repaired.pgn"

        sanitization = sanitize_pgn(pgn_path, repaired_path, strip_markup=strip_markup)

        games_written = count_games_in_pgn(repaired_path)
        if games_written == 0:
            raise RuntimeError("No PGN games could be found in the repaired output.")
        normalization = PgnNormalizationStats(
            games_written=games_written,
            parser_error_games=0,
            parser_errors=0,
        )

        smoke_test_message = None
        if cql_binary is not None:
            smoke_test_message = validate_with_cql_smoke_test(
                cql_binary,
                repaired_path,
                lineincrement=cql_lineincrement,
            )

        backup_path = finalize_in_place_repair(
            pgn_path,
            repaired_path,
            backup_suffix=backup_suffix,
            overwrite_backup=overwrite_backup,
        )

    return PgnRepairResult(
        pgn_path=pgn_path,
        backup_path=backup_path,
        sanitization=sanitization,
        normalization=normalization,
        smoke_test_message=smoke_test_message,
    )


# ---------------------------------------------------------------------------
# CLI (identical to v1)
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite PGN files in place once so they are cleaner and more likely "
            "to be readable by CQL. "
            "(v2: single-pass encoding repair only — comments and variations kept.)"
        )
    )
    parser.add_argument(
        "--pgn",
        dest="pgn_location",
        required=True,
        help="Path to a .pgn file or a directory containing .pgn files.",
    )
    parser.add_argument(
        "--cql-bin",
        dest="cql_binary",
        default=None,
        help=(
            "Optional path to the CQL executable, or an executable name on PATH. "
            "If supplied, the repaired temp PGN must pass a CQL smoke test before "
            "the original file is replaced."
        ),
    )
    parser.add_argument(
        "--backup-suffix",
        dest="backup_suffix",
        default=".bak",
        help="Suffix for the backup of the original PGN before replacing it.",
    )
    parser.add_argument(
        "--no-backup",
        dest="no_backup",
        action="store_true",
        help="Do not keep a backup copy of the original PGN.",
    )
    parser.add_argument(
        "--overwrite-backup",
        dest="overwrite_backup",
        action="store_true",
        help="Allow overwriting an existing backup file.",
    )
    parser.add_argument(
        "--cql-lineincrement",
        dest="cql_lineincrement",
        type=int,
        default=1000,
        help="Tell CQL to print progress every N games during the smoke test.",
    )
    parser.add_argument(
        "--strip-markup",
        dest="strip_markup",
        action="store_true",
        default=False,
        help=(
            "Strip PGN {comments} and (variations) in addition to encoding repair. "
            "Required for CQL compatibility when the database contains games with "
            "very large annotations that exceed CQL's internal buffer (~1 MB per game)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cql_lineincrement < 1:
        print("Error: --cql-lineincrement must be at least 1.")
        return 1

    pgn_files = discover_pgn_files(args.pgn_location)
    if pgn_files is None:
        return 1

    cql_binary = None
    if args.cql_binary:
        cql_binary = resolve_cql_binary(args.cql_binary)
        if cql_binary is None:
            return 1

    pgn_root = Path(args.pgn_location).expanduser()
    if not pgn_root.is_dir():
        pgn_root = None

    backup_suffix = None if args.no_backup else args.backup_suffix

    print(f"Repairing {len(pgn_files)} PGN file(s) in place... (v2)")
    overall_progress = tqdm_progress(
        pgn_files,
        total=len(pgn_files),
        desc="PGN repair",
        unit="file",
        dynamic_ncols=sys.stderr.isatty(),
        file=sys.stderr,
    )

    failures = 0
    results: list[PgnRepairResult] = []
    for pgn_path in overall_progress:
        display_path = format_pgn_display_path(pgn_path, pgn_root)
        overall_progress.set_postfix_str(format_progress_label(display_path))
        try:
            result = repair_pgn_file_in_place(
                pgn_path,
                backup_suffix=backup_suffix,
                overwrite_backup=args.overwrite_backup,
                cql_binary=cql_binary,
                cql_lineincrement=args.cql_lineincrement,
                strip_markup=args.strip_markup,
            )
        except Exception as exc:
            failures += 1
            progress_write(f"FAILED repair: {pgn_path}: {exc}")
            continue

        results.append(result)
        summary = (
            f"Repaired {display_path}: "
            f"{result.normalization.games_written} game(s), "
            f"{result.sanitization.control_characters_removed} control char(s) removed, "
            f"{result.sanitization.invalid_utf8_replaced} invalid UTF-8 byte(s) replaced"
        )
        if result.sanitization.removed_bom:
            summary += ", BOM removed"
        if result.backup_path is not None:
            summary += f", backup: {result.backup_path.name}"
        if result.smoke_test_message is not None:
            summary += f", {result.smoke_test_message}"
        progress_write(summary)

    overall_progress.close()

    print("\n--- Repair Summary (v2) ---")
    print(f"Files: {len(pgn_files)}")
    print(f"Repaired: {len(results)}")
    print(f"Failed: {failures}")
    print("---------------------------")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
