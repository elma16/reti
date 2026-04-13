from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FastPgnRewriteStats:
    removed_bom: bool
    invalid_utf8_replaced: int
    control_characters_removed: int
    games_written: int
    comments_removed: int
    variations_removed: int
    line_comments_removed: int
    used_native_accelerator: bool


class _FastPgnLexicalWriter:
    def __init__(
        self,
        output_handle: io.TextIOBase,
        *,
        preserve_markup: bool = False,
        inspect_only: bool = False,
    ) -> None:
        self.output_handle = output_handle
        self.preserve_markup = preserve_markup
        self.inspect_only = inspect_only

        self.removed_bom = False
        self.invalid_utf8_replaced = 0
        self.control_characters_removed = 0
        self.games_written = 0
        self.comments_removed = 0
        self.variations_removed = 0
        self.line_comments_removed = 0

        self._at_file_start = True
        self._in_comment = False
        self._variation_depth = 0
        self._skip_line_comment = False
        self._header_line = False
        self._line_start = True
        self._recovery_armed = False
        self._pending_space = False
        self._saw_nonwhitespace_output = False
        self._source_line_has_nonspace = False
        self._current_game_has_moves = False
        self._current_game_has_result = False
        self._leading_whitespace: list[str] = []
        self._line_output: list[str] = []
        self._token_chars: list[str] = []

    def feed(self, text: str) -> None:
        for char in text:
            self._feed_char(char)

    def finish(self) -> FastPgnRewriteStats:
        if self._line_output or self._header_line:
            self._finish_line(had_newline=False)

        self._write_missing_result(before_new_game=False)
        if (
            not self.inspect_only
            and self.games_written == 0
            and self._saw_nonwhitespace_output
        ):
            self.games_written = 1

        return FastPgnRewriteStats(
            removed_bom=self.removed_bom,
            invalid_utf8_replaced=self.invalid_utf8_replaced,
            control_characters_removed=self.control_characters_removed,
            games_written=self.games_written,
            comments_removed=self.comments_removed,
            variations_removed=self.variations_removed,
            line_comments_removed=self.line_comments_removed,
            used_native_accelerator=False,
        )

    def _feed_char(self, char: str) -> None:
        if self._at_file_start:
            self._at_file_start = False
            if char == "\ufeff":
                self.removed_bom = True
                return

        if char == "\ufffd":
            self.invalid_utf8_replaced += 1
            char = "?"

        codepoint = ord(char)
        if codepoint < 32 and char not in "\n\t":
            self.control_characters_removed += 1
            return

        if char == "\n":
            self._finish_line(had_newline=True)
            return

        if char not in " \t":
            self._source_line_has_nonspace = True

        if self._line_start:
            if char in " \t":
                self._leading_whitespace.append(char)
                return
            if not self.preserve_markup and self._recovery_armed and char == "[":
                self._in_comment = False
                self._variation_depth = 0
                self._recovery_armed = False

        if not self.preserve_markup and self._skip_line_comment:
            return

        if self._header_line:
            self._line_output.append(char)
            return

        if not self.preserve_markup:
            if self._in_comment:
                if char == "}":
                    self._in_comment = False
                    if self._variation_depth == 0:
                        self._recovery_armed = False
                return

            if self._variation_depth:
                if char == "{":
                    self._finish_token()
                    self.comments_removed += 1
                    self._in_comment = True
                elif char == "(":
                    self._finish_token()
                    self.variations_removed += 1
                    self._variation_depth += 1
                elif char == ")":
                    self._variation_depth -= 1
                    if self._variation_depth == 0:
                        self._recovery_armed = False
                return

        if self._line_start:
            if char == "[":
                self._header_line = True
                self._line_output.extend(self._leading_whitespace)
                self._leading_whitespace.clear()
                self._line_output.append(char)
                self._line_start = False
                return

            if not self.preserve_markup and char in "%;":
                self.line_comments_removed += 1
                self._skip_line_comment = True
                self._leading_whitespace.clear()
                self._line_start = False
                return

            self._leading_whitespace.clear()
            self._line_start = False

        if not self.preserve_markup:
            if char == "{":
                self._finish_token()
                self.comments_removed += 1
                self._in_comment = True
                return

            if char == "(":
                self._finish_token()
                self.variations_removed += 1
                self._variation_depth = 1
                return

            if char == ";":
                self._finish_token()
                self.line_comments_removed += 1
                self._skip_line_comment = True
                return

        if char in " \t":
            if self._line_output:
                self._finish_token()
                self._pending_space = True
            return

        if self._pending_space and self._line_output:
            self._line_output.append(" ")
        self._pending_space = False
        self._line_output.append(char)
        self._token_chars.append(char)
        self._current_game_has_moves = True
        self._saw_nonwhitespace_output = True

    def _finish_line(self, *, had_newline: bool) -> None:
        self._finish_token()
        line_text = "".join(self._line_output)
        if not self._header_line:
            line_text = line_text.rstrip(" \t")

        is_event_header = self._header_line and line_text.lstrip(" \t").startswith("[Event ")
        if is_event_header:
            self._write_missing_result(before_new_game=True)
            self.games_written += 1
            self._saw_nonwhitespace_output = True
            self._current_game_has_moves = False
            self._current_game_has_result = False

        if not self.inspect_only:
            if line_text:
                self.output_handle.write(line_text)
            if had_newline:
                self.output_handle.write("\n")

        if (self._in_comment or self._variation_depth) and not self._source_line_has_nonspace:
            self._recovery_armed = True

        self._skip_line_comment = False
        self._header_line = False
        self._line_start = True
        self._pending_space = False
        self._source_line_has_nonspace = False
        self._leading_whitespace.clear()
        self._line_output.clear()

    def _finish_token(self) -> None:
        if not self._token_chars:
            return
        token = "".join(self._token_chars)
        if token in {"1-0", "0-1", "1/2-1/2", "*"}:
            self._current_game_has_result = True
        self._token_chars.clear()

    def _write_missing_result(self, *, before_new_game: bool) -> None:
        if not self._current_game_has_moves or self._current_game_has_result:
            return

        if not self.inspect_only:
            if before_new_game:
                self.output_handle.write("*\n\n")
            else:
                self.output_handle.write("*\n")
        self._current_game_has_result = True
        self._saw_nonwhitespace_output = True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _native_binary_name() -> str:
    if os.name == "nt":
        return "reti-fast-pgn-repair.exe"
    return "reti-fast-pgn-repair"


def find_fast_repair_binary() -> Path | None:
    if os.environ.get("RETI_FAST_PGN_REPAIR_NO_NATIVE") == "1":
        return None

    explicit = os.environ.get("RETI_FAST_PGN_REPAIR_BIN")
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return candidate

    repo_root = _repo_root()
    binary_name = _native_binary_name()
    for candidate in (
        repo_root / "native" / "repair-pgn-fast" / "target" / "release" / binary_name,
        repo_root / "native" / "repair-pgn-fast" / "target" / "debug" / binary_name,
    ):
        if candidate.is_file():
            return candidate

    for name in (binary_name, "repair-pgn-fast"):
        on_path = shutil.which(name)
        if on_path:
            return Path(on_path)

    return None


def _parse_native_stats(output: str) -> FastPgnRewriteStats:
    data = json.loads(output)
    return FastPgnRewriteStats(
        removed_bom=bool(data["removed_bom"]),
        invalid_utf8_replaced=int(data["invalid_utf8_replaced"]),
        control_characters_removed=int(data["control_characters_removed"]),
        games_written=int(data["games_written"]),
        comments_removed=int(data["comments_removed"]),
        variations_removed=int(data["variations_removed"]),
        line_comments_removed=int(data["line_comments_removed"]),
        used_native_accelerator=True,
    )


def _rewrite_pgn_fast_native(
    source_path: Path,
    destination_path: Path,
    binary_path: Path,
    *,
    preserve_markup: bool = False,
) -> FastPgnRewriteStats:
    command = [str(binary_path), str(source_path), str(destination_path)]
    if preserve_markup:
        command.insert(1, "--preserve-markup")
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "fast repair native helper failed")
    return _parse_native_stats(process.stdout)


def rewrite_pgn_fast_python(
    source_path: Path,
    destination_path: Path,
    *,
    preserve_markup: bool = False,
) -> FastPgnRewriteStats:
    writer: _FastPgnLexicalWriter
    stats: FastPgnRewriteStats
    with source_path.open("rb") as raw_handle, destination_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as output_handle:
        text_handle = io.TextIOWrapper(
            raw_handle,
            encoding="utf-8",
            errors="replace",
            newline=None,
        )
        writer = _FastPgnLexicalWriter(output_handle, preserve_markup=preserve_markup)
        for chunk in iter(lambda: text_handle.read(1024 * 1024), ""):
            writer.feed(chunk)
        stats = writer.finish()

    return stats


def _inspect_pgn_fast_native(
    source_path: Path,
    binary_path: Path,
) -> FastPgnRewriteStats:
    process = subprocess.run(
        [str(binary_path), "--inspect", str(source_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "fast repair native helper failed")
    return _parse_native_stats(process.stdout)


def inspect_pgn_fast(source_path: Path) -> FastPgnRewriteStats:
    """
    Scan a PGN and return the same stats rewrite_pgn_fast would produce, without
    writing an output file. Uses the Rust helper when available.
    """
    binary_path = find_fast_repair_binary()
    if binary_path is not None:
        try:
            return _inspect_pgn_fast_native(source_path, binary_path)
        except Exception:
            pass

    with source_path.open("rb") as raw_handle:
        text_handle = io.TextIOWrapper(
            raw_handle,
            encoding="utf-8",
            errors="replace",
            newline=None,
        )
        sink = io.StringIO()
        writer = _FastPgnLexicalWriter(
            sink, preserve_markup=True, inspect_only=True
        )
        for chunk in iter(lambda: text_handle.read(1024 * 1024), ""):
            writer.feed(chunk)
        return writer.finish()


def rewrite_pgn_fast(
    source_path: Path,
    destination_path: Path,
    *,
    preserve_markup: bool = False,
) -> FastPgnRewriteStats:
    binary_path = find_fast_repair_binary()
    if binary_path is not None:
        try:
            return _rewrite_pgn_fast_native(
                source_path,
                destination_path,
                binary_path,
                preserve_markup=preserve_markup,
            )
        except Exception:
            pass

    return rewrite_pgn_fast_python(
        source_path,
        destination_path,
        preserve_markup=preserve_markup,
    )
