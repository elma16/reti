from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from reti.common.pgn_discovery import (
    discover_pgn_files,
    format_pgn_display_path,
)
from reti.pgn_utils import find_pgn_utils_binary

__all__ = [
    "AnnotatedPosition",
    "ParsedAnnotatedGame",
    "comment_matches_marker",
    "discover_pgn_files",
    "fast_iter_annotated_pgn",
    "format_pgn_display_path",
    "iter_annotated_pgn",
    "parse_annotated_pgn",
    "side_name",
]


@dataclass(frozen=True)
class AnnotatedPosition:
    ply_index: int
    fullmove_number: int
    move_san: str
    move_uci: str
    fen: str
    side_to_move: str
    piece_count: int


@dataclass(frozen=True)
class ParsedAnnotatedGame:
    game_index: int
    headers: dict[str, str]
    parse_errors: tuple[str, ...]
    move_uci_sequence: tuple[str, ...]
    positions: tuple[AnnotatedPosition, ...]


def side_name(turn: bool) -> str:
    return "white" if turn else "black"


def comment_matches_marker(comment: str, marker_text: str) -> bool:
    return comment.strip() == marker_text


def _position_from_native(raw: dict[str, object]) -> AnnotatedPosition:
    return AnnotatedPosition(
        ply_index=int(raw.get("ply_index", 0)),
        fullmove_number=int(raw.get("fullmove_number", 0)),
        move_san=str(raw.get("move_san", "")),
        move_uci=str(raw.get("move_uci", "")),
        fen=str(raw.get("fen", "")),
        side_to_move=str(raw.get("side_to_move", "")),
        piece_count=int(raw.get("piece_count", 0)),
    )


def _game_from_native(raw: dict[str, object]) -> ParsedAnnotatedGame:
    headers_raw = raw.get("headers", {})
    headers = {
        str(key): str(value)
        for key, value in (headers_raw.items() if isinstance(headers_raw, dict) else ())
    }
    parse_errors_raw = raw.get("parse_errors", [])
    parse_errors = tuple(str(error) for error in parse_errors_raw) if isinstance(parse_errors_raw, list) else ()
    moves_raw = raw.get("move_uci_sequence", [])
    move_uci_sequence = tuple(str(move) for move in moves_raw) if isinstance(moves_raw, list) else ()
    positions_raw = raw.get("positions", [])
    positions = (
        tuple(_position_from_native(position) for position in positions_raw if isinstance(position, dict))
        if isinstance(positions_raw, list)
        else ()
    )
    return ParsedAnnotatedGame(
        game_index=int(raw.get("game_index", 0)),
        headers=headers,
        parse_errors=parse_errors,
        move_uci_sequence=move_uci_sequence,
        positions=positions,
    )


def _native_annotated_pgn(
    pgn_path: Path,
    *,
    marker_text: str,
) -> list[ParsedAnnotatedGame]:
    binary_path = find_pgn_utils_binary()
    if binary_path is None:
        raise RuntimeError(
            "native PGN playthrough helper not found; build it with "
            "`cargo build --release --manifest-path native/pgn-utils/Cargo.toml`"
        )

    with tempfile.TemporaryDirectory(prefix="reti_annotated_pgn_") as tmpdir:
        output_path = Path(tmpdir) / "games.jsonl"
        process = subprocess.run(
            [
                str(binary_path),
                "annotated-pgn",
                "--marker",
                marker_text,
                "--allow-parse-errors",
                "--force",
                "--no-progress",
                "--output",
                str(output_path),
                str(pgn_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if process.returncode != 0:
            detail = process.stderr.strip() or process.stdout.strip()
            raise RuntimeError(detail or "native PGN playthrough helper failed")

        parsed: list[ParsedAnnotatedGame] = []
        with output_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"native PGN helper wrote invalid JSONL at line {line_number}: {exc}"
                    ) from exc
                if not isinstance(raw, dict):
                    raise RuntimeError(
                        f"native PGN helper wrote non-object JSONL at line {line_number}"
                    )
                parsed.append(_game_from_native(raw))
        return parsed


def parse_annotated_pgn(
    pgn_path: Path,
    *,
    marker_text: str,
) -> list[ParsedAnnotatedGame]:
    return _native_annotated_pgn(pgn_path, marker_text=marker_text)


def iter_annotated_pgn(
    pgn_path: Path,
    *,
    marker_text: str,
) -> Generator[tuple[ParsedAnnotatedGame, int], None, None]:
    """Yield ``(parsed_game, bytes_consumed)`` for each game in the PGN.

    ``bytes_consumed`` is the approximate number of bytes read since the
    previous yield, based on the file-handle position.  This is useful for
    driving a progress bar weighted by file size.
    """
    parsed_games = parse_annotated_pgn(pgn_path, marker_text=marker_text)
    if not parsed_games:
        return
    file_size = pgn_path.stat().st_size
    base = file_size // len(parsed_games)
    consumed = 0
    for index, parsed_game in enumerate(parsed_games, start=1):
        if index == len(parsed_games):
            bytes_consumed = file_size - consumed
        else:
            bytes_consumed = base
            consumed += bytes_consumed
        yield parsed_game, bytes_consumed


# ---------------------------------------------------------------------------
# Fast PGN scanner -- skips move validation for high-throughput aggregate views.
# Produces the same (ParsedAnnotatedGame, bytes_consumed) tuples so it is a
# drop-in replacement for iter_annotated_pgn in contexts that only need
# headers, move text (for game-key hashing), and {CQL} ply positions.
# ---------------------------------------------------------------------------

_GAME_BOUNDARY_RE = re.compile(r"\r?\n\s*\r?\n(?=\[)")
_HEADER_LINE_RE = re.compile(r'\[(\w+)\s+"([^"]*)"\]')


def _scan_movetext(
    movetext: str,
    marker_text: str,
) -> tuple[list[str], list[int]]:
    """Return ``(san_moves, marker_plies)`` from raw PGN movetext."""
    moves: list[str] = []
    marker_plies: list[int] = []
    ply = 0
    i = 0
    n = len(movetext)

    while i < n:
        c = movetext[i]

        if c == "{":
            end = movetext.find("}", i + 1)
            if end == -1:
                break
            if movetext[i + 1 : end].strip() == marker_text:
                marker_plies.append(ply)
            i = end + 1

        elif c == "(":
            depth = 1
            i += 1
            while i < n and depth > 0:
                ch = movetext[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif ch == "{":
                    close = movetext.find("}", i + 1)
                    i = close if close != -1 else n - 1
                i += 1

        elif c == ";":
            while i < n and movetext[i] != "\n":
                i += 1

        elif c == "$":
            i += 1
            while i < n and movetext[i].isdigit():
                i += 1

        elif c.isdigit():
            j = i + 1
            while j < n and (movetext[j].isdigit() or movetext[j] == "."):
                j += 1
            if "." in movetext[i:j]:
                i = j  # move number like "42." or "1..."
            else:
                # result token fragment (1-0, 0-1, 1/2-1/2) or stray digit
                while j < n and movetext[j] in "-/0123456789":
                    j += 1
                i = j

        elif c in "abcdefghKQRBNO":
            j = i + 1
            while j < n and movetext[j] not in " \t\r\n{}()$;":
                j += 1
            moves.append(movetext[i:j])
            ply += 1
            i = j

        elif c == "*":
            i += 1

        else:
            i += 1

    return moves, marker_plies


def fast_iter_annotated_pgn(
    pgn_path: Path,
    *,
    marker_text: str,
) -> Generator[tuple[ParsedAnnotatedGame, int], None, None]:
    """Fast drop-in replacement for :func:`iter_annotated_pgn`.

    Reads the file once, splits into games with a regex, and scans each
    game's movetext for SAN tokens and marker comments without validating
    moves against the board. This is for aggregate views that do not need FENs.

    ``move_uci_sequence`` on the yielded games contains **SAN** (not UCI)
    tokens.  This is fine for :func:`build_game_key` since it only hashes
    the sequence.
    """
    file_size = pgn_path.stat().st_size
    text = pgn_path.read_text(encoding="utf-8", errors="replace")
    text_len = len(text)
    if not text_len:
        return

    bytes_per_char = file_size / text_len

    # Split into per-game chunks.
    starts = [0] + [m.end() for m in _GAME_BOUNDARY_RE.finditer(text)]
    prev_byte_pos = 0

    for game_idx in range(len(starts)):
        start = starts[game_idx]
        end = starts[game_idx + 1] if game_idx + 1 < len(starts) else text_len
        chunk = text[start:end]

        # --- headers ---
        headers: dict[str, str] = {}
        last_header_end = 0
        for hm in _HEADER_LINE_RE.finditer(chunk):
            headers[hm.group(1)] = hm.group(2)
            last_header_end = hm.end()

        if not headers:
            continue

        # --- movetext (everything after the last header line) ---
        mt_start = last_header_end
        while mt_start < len(chunk) and chunk[mt_start] in " \t\r\n":
            mt_start += 1
        movetext = chunk[mt_start:]

        san_moves, marker_plies = _scan_movetext(movetext, marker_text)

        positions = tuple(
            AnnotatedPosition(
                ply_index=ply,
                fullmove_number=(ply + 1) // 2,
                move_san="",
                move_uci="",
                fen="",
                side_to_move="white" if ply % 2 == 1 else "black",
                piece_count=0,
            )
            for ply in marker_plies
        )

        parsed = ParsedAnnotatedGame(
            game_index=game_idx + 1,
            headers=headers,
            parse_errors=(),
            move_uci_sequence=tuple(san_moves),
            positions=positions,
        )

        byte_pos = int(end * bytes_per_char)
        bytes_consumed = byte_pos - prev_byte_pos
        prev_byte_pos = byte_pos
        yield parsed, bytes_consumed
