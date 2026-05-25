"""Single-output merge: combine per-(PGN, CQL) outputs into one PGN per source PGN.

For each source PGN, walk its games in order and overlay the comments emitted by
every CQL script whose output contained that game. The result is one merged PGN
per source where each input game appears at most once and carries the union of
all matching scripts' comments at the plies they were inserted.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import shutil

from tqdm import tqdm as tqdm_progress

from reti.common.progress import format_progress_label
from reti.common.pgn_discovery import InputCollection, relative_stem
from reti.cql.runner import JobResult


_GAME_ID_TAGS = ("Event", "Site", "Date", "Round", "White", "Black", "Result")
_HEADER_LINE_RE = re.compile(r'^\[(\w+)\s+"([^"]*)"\]\s*$', re.MULTILINE)
_MOVETEXT_TOKEN_RE = re.compile(
    r"\{[^}]*\}|;[^\n]*|\(|\)|\$\d+|\d+\.(?:\.\.)?|[^\s{}()$;]+"
)
_SAN_START = set("abcdefghKQRBNO")
_RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}


@dataclass(frozen=True)
class _PgnChunk:
    raw: str
    headers: dict[str, str]
    movetext_start: int


def _game_key(headers: dict[str, str]) -> tuple[str, ...]:
    """Stable identity for matching the same game across CQL outputs."""
    return tuple(headers.get(tag, "?") for tag in _GAME_ID_TAGS)


def _chunk_from_text(text: str) -> _PgnChunk | None:
    raw = text.strip()
    if not raw:
        return None
    headers: dict[str, str] = {}
    last_header_end = 0
    for match in _HEADER_LINE_RE.finditer(raw):
        headers[match.group(1)] = match.group(2)
        last_header_end = match.end()
    movetext_start = last_header_end
    while movetext_start < len(raw) and raw[movetext_start] in " \t\r\n":
        movetext_start += 1
    return _PgnChunk(
        raw=raw,
        headers=headers,
        movetext_start=movetext_start,
    )


def _iter_pgn_chunks(pgn_path: Path, *, progress: object | None = None):
    current: list[str] = []
    with pgn_path.open("rb") as handle:
        for raw_line in handle:
            if progress is not None:
                progress.update(len(raw_line))
            if raw_line.startswith(b'[Event "') and current:
                chunk = _chunk_from_text("".join(current))
                if chunk is not None:
                    yield chunk
                current = [raw_line.decode("utf-8", errors="replace")]
                continue
            if current or raw_line.startswith(b'[Event "'):
                current.append(raw_line.decode("utf-8", errors="replace"))
    if current:
        chunk = _chunk_from_text("".join(current))
        if chunk is not None:
            yield chunk


def _split_pgn_chunks(pgn_path: Path) -> list[_PgnChunk]:
    return list(_iter_pgn_chunks(pgn_path))


def _append_comment(by_ply: dict[int, str], ply: int, text: str) -> None:
    text = text.strip()
    if not text:
        return
    if ply in by_ply and by_ply[ply]:
        by_ply[ply] = f"{by_ply[ply]} {text}"
    else:
        by_ply[ply] = text


def _scan_comments_and_insertions(movetext: str) -> tuple[dict[int, str], dict[int, int]]:
    """Return mainline comments and insertion offsets relative to ``movetext``.

    This is intentionally lexical. It skips variations and comments without
    validating SAN, so broken side lines cannot derail the merge.
    """
    comments: dict[int, str] = {}
    insertions: dict[int, int] = {0: 0}
    ply = 0
    variation_depth = 0

    for match in _MOVETEXT_TOKEN_RE.finditer(movetext):
        token = match.group(0)
        char = token[0]

        if char == "{":
            if variation_depth == 0 and token.endswith("}"):
                _append_comment(comments, ply, token[1:-1])
            continue

        if char == "(":
            variation_depth += 1
            continue

        if char == ")" and variation_depth:
            variation_depth -= 1
            continue

        if variation_depth:
            continue

        if char in ";$":
            continue

        if char.isdigit():
            continue

        if char in _SAN_START:
            if token not in _RESULT_TOKENS:
                ply += 1
                insertions[ply] = match.end()

    return comments, insertions


def _comments_by_ply(chunk: _PgnChunk) -> dict[int, str]:
    comments, _ = _scan_comments_and_insertions(chunk.raw[chunk.movetext_start :])
    return comments


def _new_part(source: str, annotated: str) -> str:
    """Return the text added by an annotated version relative to the source comment.

    CQL inserts ``comment(...)`` output at the matching position; existing PGN
    comments at that ply are preserved. We try to extract just the addition so we
    don't duplicate the source comment in the merged output.
    """
    source = source.strip()
    annotated = annotated.strip()
    if not source:
        return annotated
    if annotated == source:
        return ""
    if annotated.startswith(source):
        return annotated[len(source):].strip()
    if annotated.endswith(source):
        return annotated[: -len(source)].strip()
    return annotated


def _join_comments(parts: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if part in seen:
            continue
        seen.add(part)
        out.append(part)
    return " ".join(out)


def _comment_literal(text: str) -> str:
    return "{" + text.replace("}", ")").strip() + "}"


def _apply_annotations_to_chunk(
    chunk: _PgnChunk,
    additions: dict[int, list[str]],
) -> str:
    movetext = chunk.raw[chunk.movetext_start :]
    _, insertion_offsets = _scan_comments_and_insertions(movetext)
    edits: list[tuple[int, str]] = []
    for ply, parts in additions.items():
        merged = _join_comments(parts)
        if not merged:
            continue
        relative_offset = insertion_offsets.get(ply)
        if relative_offset is None:
            relative_offset = len(movetext)
        absolute_offset = chunk.movetext_start + relative_offset
        edits.append((absolute_offset, " " + _comment_literal(merged)))

    text = chunk.raw
    for offset, insertion in sorted(edits, key=lambda item: item[0], reverse=True):
        text = text[:offset] + insertion + text[offset:]
    return text


def merge_single_output(
    results: list[JobResult],
    pgn_inputs: InputCollection,
    output_dir: Path,
    *,
    include_unmatched: bool,
    show_progress: bool = True,
) -> list[Path]:
    """Emit one merged PGN per source PGN with all matching scripts' comments overlaid.

    Per-pair output files are removed once they've been folded into a merged PGN.
    """
    annotated_comments: dict[
        Path, dict[tuple[str, ...], list[dict[int, str]]]
    ] = defaultdict(lambda: defaultdict(list))

    successful_results = [
        result
        for result in results
        if result.success and result.output_pgn.exists()
    ]
    source_pgns = {result.pgn_path for result in successful_results}
    results_by_source: dict[Path, list[JobResult]] = defaultdict(list)
    for result in successful_results:
        results_by_source[result.pgn_path].append(result)
    total_bytes = sum(result.output_pgn.stat().st_size for result in successful_results)
    sources_requiring_overlay = {
        source
        for source, source_results in results_by_source.items()
        if include_unmatched
        or len(
            [
                result
                for result in source_results
                if result.match_count is not None and result.match_count > 0
            ]
        )
        > 1
    }
    total_bytes += sum(path.stat().st_size for path in sources_requiring_overlay)

    progress = tqdm_progress(
        total=total_bytes,
        unit="B",
        unit_scale=True,
        desc="Merging single-output PGNs",
        dynamic_ncols=True,
        disable=not show_progress,
    )
    try:
        for result in successful_results:
            progress.set_postfix_str(
                format_progress_label(
                    f"scan {result.pgn_path.name} x {result.cql_path.name}"
                )
            )
            if result.pgn_path not in sources_requiring_overlay:
                progress.update(result.output_pgn.stat().st_size)
                continue
            if result.match_count is None or result.match_count == 0:
                progress.update(result.output_pgn.stat().st_size)
                continue
            for annotated_game in _iter_pgn_chunks(result.output_pgn, progress=progress):
                key = _game_key(annotated_game.headers)
                annotated_comments[result.pgn_path][key].append(
                    _comments_by_ply(annotated_game)
                )

        merged_paths: list[Path] = []
        for source_pgn in sorted(source_pgns):
            merged_name = relative_stem(source_pgn, pgn_inputs.root)
            merged_path = output_dir / f"{merged_name}.merged.pgn"
            merged_path.parent.mkdir(parents=True, exist_ok=True)

            source_results = results_by_source[source_pgn]
            matched_results = [
                result
                for result in source_results
                if result.match_count is not None and result.match_count > 0
            ]
            if not include_unmatched and not matched_results:
                progress.set_postfix_str(
                    format_progress_label(f"empty {source_pgn.name}")
                )
                merged_path.write_text("", encoding="utf-8")
                print(
                    f"Merged single-output PGN (matched): {merged_path} "
                    "(0 game(s))"
                )
                merged_paths.append(merged_path)
                continue
            if not include_unmatched and len(matched_results) == 1:
                only_result = matched_results[0]
                progress.set_postfix_str(
                    format_progress_label(f"move {source_pgn.name}")
                )
                if merged_path.exists():
                    merged_path.unlink()
                if only_result.output_pgn.exists():
                    shutil.move(str(only_result.output_pgn), merged_path)
                written_games = only_result.match_count or 0
                print(
                    f"Merged single-output PGN (matched): {merged_path} "
                    f"({written_games} game(s))"
                )
                merged_paths.append(merged_path)
                continue

            source_matches = annotated_comments.get(source_pgn, {})
            written_games = 0
            progress.set_postfix_str(
                format_progress_label(f"write {source_pgn.name}")
            )
            with merged_path.open("w", encoding="utf-8") as out:
                for chunk in _iter_pgn_chunks(source_pgn, progress=progress):
                    key = _game_key(chunk.headers)
                    per_script_comments = source_matches.get(key)
                    if per_script_comments is None and not include_unmatched:
                        continue

                    additions: dict[int, list[str]] = defaultdict(list)
                    if per_script_comments:
                        source_comments = _comments_by_ply(chunk)
                        for comments_by_ply in per_script_comments:
                            for ply, ann_text in comments_by_ply.items():
                                added = _new_part(source_comments.get(ply, ""), ann_text)
                                if added:
                                    additions[ply].append(added)

                    if additions:
                        out.write(_apply_annotations_to_chunk(chunk, additions))
                    else:
                        out.write(chunk.raw)
                    out.write("\n\n")
                    written_games += 1

            kind = "all" if include_unmatched else "matched"
            print(
                f"Merged single-output PGN ({kind}): {merged_path} "
                f"({written_games} game(s))"
            )
            merged_paths.append(merged_path)
    finally:
        progress.close()

    removed_dirs: set[Path] = set()
    for result in successful_results:
        per_pair = result.output_pgn
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
