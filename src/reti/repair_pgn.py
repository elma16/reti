from __future__ import annotations

import argparse
import codecs
import functools
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import chess.pgn as chess_pgn

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reti.fast_pgn_repair import FastPgnRewriteStats, rewrite_pgn_fast
from tqdm import tqdm as tqdm_progress

FAST_REPAIR_MODE = "fast"
STRICT_REPAIR_MODE = "strict"
REPAIR_MODES = (FAST_REPAIR_MODE, STRICT_REPAIR_MODE)


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
    safe = make_terminal_safe(text).replace("\n", " ").replace("\r", " ").replace(
        "\t", " "
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
    parser_error_games: int
    parser_errors: int
    mode: str
    used_native_accelerator: bool
    comments_removed: int
    variations_removed: int
    line_comments_removed: int


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


def sanitize_pgn_to_path(source_path: Path, destination_path: Path) -> TextSanitizationStats:
    removed_bom = False
    invalid_utf8_replaced = 0
    control_characters_removed = 0

    progress = tqdm_progress(
        total=source_path.stat().st_size,
        desc=f"Sanitizing {format_progress_label(source_path.name, max_length=48)}",
        unit="B",
        unit_scale=True,
        dynamic_ncols=sys.stderr.isatty(),
        file=sys.stderr,
    )

    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    with source_path.open("rb") as input_handle, destination_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as output_handle:
        first_chunk = True
        while True:
            raw_chunk = input_handle.read(1024 * 1024)
            if not raw_chunk:
                break

            progress.update(len(raw_chunk))
            if first_chunk and raw_chunk.startswith(b"\xef\xbb\xbf"):
                raw_chunk = raw_chunk[3:]
                removed_bom = True
            first_chunk = False

            text_chunk = decoder.decode(raw_chunk)
            cleaned_chars: list[str] = []
            for char in text_chunk:
                if char == "\ufffd":
                    invalid_utf8_replaced += 1
                    cleaned_chars.append("?")
                    continue

                codepoint = ord(char)
                if codepoint < 32 and char not in "\n\r\t":
                    control_characters_removed += 1
                    continue

                cleaned_chars.append(char)

            output_handle.write("".join(cleaned_chars))

        final_chunk = decoder.decode(b"", final=True)
        if final_chunk:
            cleaned_chars = []
            for char in final_chunk:
                if char == "\ufffd":
                    invalid_utf8_replaced += 1
                    cleaned_chars.append("?")
                    continue

                codepoint = ord(char)
                if codepoint < 32 and char not in "\n\r\t":
                    control_characters_removed += 1
                    continue

                cleaned_chars.append(char)

            output_handle.write("".join(cleaned_chars))
        output_handle.flush()
        os.fsync(output_handle.fileno())

    progress.close()
    return TextSanitizationStats(
        removed_bom=removed_bom,
        invalid_utf8_replaced=invalid_utf8_replaced,
        control_characters_removed=control_characters_removed,
    )


class _StreamingPgnNormalizer(
    chess_pgn.StringExporterMixin,
    chess_pgn.BaseVisitor["_StreamingPgnNormalizer"],
):
    """Normalize a game directly from the parser without building a Game tree."""

    def __init__(self, handle: io.TextIOBase) -> None:
        super().__init__(columns=80, headers=True, comments=False, variations=False)
        self.handle = handle
        self.game_headers = chess_pgn.Headers()
        self.error_count = 0

    def begin_game(self) -> None:
        self.force_movenumber = True
        self.lines = []
        self.current_line = ""
        self.variation_depth = 0
        self.game_headers = chess_pgn.Headers()
        self.error_count = 0

    def begin_headers(self) -> chess_pgn.Headers:
        return self.game_headers

    def visit_header(self, tagname: str, tagvalue: str) -> None:
        self.game_headers[tagname] = tagvalue

    def end_headers(self) -> None:
        return None

    def visit_result(self, result: str) -> None:
        if self.game_headers.get("Result", "*") == "*":
            self.game_headers["Result"] = result

    def handle_error(self, error: Exception) -> None:
        self.error_count += 1

    def end_game(self) -> None:
        for tagname, tagvalue in self.game_headers.items():
            self.handle.write(f'[{tagname} "{tagvalue}"]\n')
        self.handle.write("\n")
        self.write_token(self.game_headers.get("Result", "*") + " ")
        self.flush_current_line()
        for line in self.lines:
            self.handle.write(line + "\n")
        self.handle.write("\n")

    def result(self) -> _StreamingPgnNormalizer:
        return self


def _normalization_stats_from_fast(stats: FastPgnRewriteStats) -> PgnNormalizationStats:
    return PgnNormalizationStats(
        games_written=stats.games_written,
        parser_error_games=0,
        parser_errors=0,
        mode=FAST_REPAIR_MODE,
        used_native_accelerator=stats.used_native_accelerator,
        comments_removed=stats.comments_removed,
        variations_removed=stats.variations_removed,
        line_comments_removed=stats.line_comments_removed,
    )


def normalize_pgn_file(source_path: Path, destination_path: Path) -> PgnNormalizationStats:
    games_written = 0
    parser_error_games = 0
    parser_errors = 0

    total_bytes = source_path.stat().st_size
    progress = tqdm_progress(
        total=total_bytes,
        desc=f"Normalizing {format_progress_label(source_path.name, max_length=48)}",
        unit="B",
        unit_scale=True,
        dynamic_ncols=sys.stderr.isatty(),
        file=sys.stderr,
    )

    with source_path.open("r", encoding="utf-8", newline="") as input_handle, destination_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as output_handle:
        normalizer_factory = functools.partial(_StreamingPgnNormalizer, output_handle)
        last_position = 0
        while True:
            game = chess_pgn.read_game(input_handle, Visitor=normalizer_factory)
            current_position = input_handle.tell()
            progress.update(max(0, current_position - last_position))
            last_position = current_position

            if game is None:
                break

            if game.error_count:
                parser_error_games += 1
                parser_errors += game.error_count
            games_written += 1

        if last_position < total_bytes:
            progress.update(total_bytes - last_position)

        output_handle.flush()
        os.fsync(output_handle.fileno())

    progress.close()
    if games_written == 0:
        raise RuntimeError("No PGN games could be parsed from the sanitized input.")

    return PgnNormalizationStats(
        games_written=games_written,
        parser_error_games=parser_error_games,
        parser_errors=parser_errors,
        mode=STRICT_REPAIR_MODE,
        used_native_accelerator=False,
        comments_removed=0,
        variations_removed=0,
        line_comments_removed=0,
    )


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
        message = f"CQL smoke test failed ({detail})"
        message += "; see terminal output above for CQL details"
        raise RuntimeError(message)

    return "CQL smoke test passed"


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


def repair_pgn_file_in_place(
    pgn_path: Path,
    *,
    backup_suffix: str | None = ".bak",
    overwrite_backup: bool = False,
    cql_binary: Path | None = None,
    cql_lineincrement: int = 1000,
    mode: str = FAST_REPAIR_MODE,
    preserve_markup: bool = False,
) -> PgnRepairResult:
    if mode not in REPAIR_MODES:
        raise ValueError(f"Unsupported repair mode: {mode}")
    if preserve_markup and mode != FAST_REPAIR_MODE:
        raise ValueError("preserve_markup is only supported in fast repair mode")
    if not pgn_path.exists():
        raise FileNotFoundError(f"PGN file not found: {pgn_path}")

    with tempfile.TemporaryDirectory(
        prefix=f".{pgn_path.stem}.repair_",
        dir=pgn_path.parent,
    ) as tmpdir:
        tmp_path = Path(tmpdir)
        repaired_path = tmp_path / "repaired.pgn"

        if mode == FAST_REPAIR_MODE:
            fast_stats = rewrite_pgn_fast(
                pgn_path,
                repaired_path,
                preserve_markup=preserve_markup,
            )
            sanitization = TextSanitizationStats(
                removed_bom=fast_stats.removed_bom,
                invalid_utf8_replaced=fast_stats.invalid_utf8_replaced,
                control_characters_removed=fast_stats.control_characters_removed,
            )
            normalization = _normalization_stats_from_fast(fast_stats)
        else:
            sanitized_path = tmp_path / "sanitized.pgn"
            sanitization = sanitize_pgn_to_path(pgn_path, sanitized_path)
            normalization = normalize_pgn_file(sanitized_path, repaired_path)

        if normalization.games_written == 0:
            raise RuntimeError("No PGN games could be repaired from the input.")

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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite PGN files in place so they are more likely to be readable by "
            "CQL. The default fast mode uses a single-pass lexical rewrite that "
            "strips parser-hostile comments and variations. Strict mode keeps the "
            "older python-chess normalization path."
        )
    )
    parser.add_argument(
        "--pgn",
        dest="pgn_location",
        required=True,
        help="Path to a .pgn file or a directory containing .pgn files.",
    )
    parser.add_argument(
        "--mode",
        dest="mode",
        choices=REPAIR_MODES,
        default=FAST_REPAIR_MODE,
        help=(
            "Repair mode. 'fast' is a CQL-safe lexical rewrite and is the "
            "default. 'strict' reparses through python-chess for canonical "
            "mainline-only normalization."
        ),
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
        help=(
            "Suffix for the one-time backup of the original PGN before replacing "
            "it. Use --no-backup to skip the backup."
        ),
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
        "--preserve-markup",
        dest="preserve_markup",
        action="store_true",
        help=(
            "Fast mode only: keep PGN comments ({...}, ;..., %...) and side "
            "variations ((...)) instead of stripping them. Still scrubs BOMs, "
            "invalid UTF-8, and control characters."
        ),
    )
    parser.add_argument(
        "--cql-lineincrement",
        dest="cql_lineincrement",
        type=int,
        default=1000,
        help=(
            "When --cql-bin is supplied, tell CQL to print progress every N "
            "games during the repaired-file smoke test."
        ),
    )
    return parser.parse_args(argv)


def _format_repair_summary(display_path: str, result: PgnRepairResult) -> str:
    summary = (
        f"Repaired {display_path}: "
        f"{result.normalization.games_written} game(s), "
        f"{result.sanitization.control_characters_removed} control char(s) removed, "
        f"{result.sanitization.invalid_utf8_replaced} invalid UTF-8 byte(s) replaced, "
        f"mode={result.normalization.mode}"
    )
    if result.sanitization.removed_bom:
        summary += ", BOM removed"
    if result.normalization.used_native_accelerator:
        summary += ", native fast path"
    if result.normalization.comments_removed:
        summary += f", {result.normalization.comments_removed} comment block(s) removed"
    if result.normalization.variations_removed:
        summary += (
            f", {result.normalization.variations_removed} variation(s) removed"
        )
    if result.normalization.line_comments_removed:
        summary += (
            f", {result.normalization.line_comments_removed} line comment(s) removed"
        )
    if result.normalization.parser_errors:
        summary += (
            f", {result.normalization.parser_errors} parser error note(s) across "
            f"{result.normalization.parser_error_games} game(s)"
        )
    if result.backup_path is not None:
        summary += f", backup: {result.backup_path.name}"
    if result.smoke_test_message is not None:
        summary += f", {result.smoke_test_message}"
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cql_lineincrement < 1:
        print("Error: --cql-lineincrement must be at least 1.")
        return 1
    if args.preserve_markup and args.mode != FAST_REPAIR_MODE:
        print("Error: --preserve-markup is only supported with --mode fast.")
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

    print(f"Repairing {len(pgn_files)} PGN file(s) in place with mode={args.mode}...")
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
                mode=args.mode,
                preserve_markup=args.preserve_markup,
            )
        except Exception as exc:
            failures += 1
            progress_write(f"FAILED repair: {pgn_path}: {exc}")
            continue

        results.append(result)
        progress_write(_format_repair_summary(display_path, result))

    overall_progress.close()

    print("\n--- Repair Summary ---")
    print(f"Files: {len(pgn_files)}")
    print(f"Repaired: {len(results)}")
    print(f"Failed: {failures}")
    print("----------------------")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
