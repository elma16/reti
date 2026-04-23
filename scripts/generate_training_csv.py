#!/usr/bin/env python3
"""Generate a training CSV from CQL-annotated PGN endgame files.

Fast-scans PGNs for {CQL} markers, randomly samples games, analyses
positions with Stockfish, and writes a CSV with columns:

    fen, expected_result, sharp, material
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine
import chess.pgn as chess_pgn
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reti.annotated_pgn import discover_pgn_files

# ---------------------------------------------------------------------------
# Fast PGN scanning (regex-based, no move validation)
# ---------------------------------------------------------------------------

_GAME_BOUNDARY_RE = re.compile(r"\r?\n\s*\r?\n(?=\[)")
_HEADER_LINE_RE = re.compile(r'\[(\w+)\s+"([^"]*)"\]')


@dataclass
class GameRef:
    """Lightweight reference to a game found during the fast scan."""

    file_path: Path
    chunk_start: int
    chunk_end: int
    num_markers: int


def _count_markers(chunk: str, marker_text: str) -> int:
    count = 0
    pos = 0
    target = f"{{{marker_text}}}"
    while True:
        idx = chunk.find("{", pos)
        if idx == -1:
            break
        end = chunk.find("}", idx + 1)
        if end == -1:
            break
        if chunk[idx + 1 : end].strip() == marker_text:
            count += 1
        pos = end + 1
    return count


def fast_scan_for_refs(
    pgn_paths: list[Path],
    *,
    marker_text: str,
    min_matches: int,
) -> list[GameRef]:
    """Scan PGN files and return refs for games with enough CQL markers."""
    refs: list[GameRef] = []
    for pgn_path in tqdm(pgn_paths, desc="Scanning PGNs", unit="file"):
        text = pgn_path.read_text(encoding="utf-8", errors="replace")
        starts = [0] + [m.end() for m in _GAME_BOUNDARY_RE.finditer(text)]

        for idx in range(len(starts)):
            start = starts[idx]
            end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
            chunk = text[start:end]

            # Quick reject: not enough braces to possibly have min_matches markers.
            if chunk.count("{") < min_matches:
                continue

            n_markers = _count_markers(chunk, marker_text)
            if n_markers >= min_matches:
                refs.append(
                    GameRef(
                        file_path=pgn_path,
                        chunk_start=start,
                        chunk_end=end,
                        num_markers=n_markers,
                    )
                )
    return refs


# ---------------------------------------------------------------------------
# Selective python-chess parsing (only for sampled games)
# ---------------------------------------------------------------------------

_file_text_cache: dict[Path, str] = {}
_FILE_CACHE_MAX = 4


def _get_file_text(path: Path) -> str:
    if path not in _file_text_cache:
        if len(_file_text_cache) >= _FILE_CACHE_MAX:
            _file_text_cache.pop(next(iter(_file_text_cache)))
        _file_text_cache[path] = path.read_text(
            encoding="utf-8", errors="replace"
        )
    return _file_text_cache[path]


@dataclass
class GameMetadata:
    white: str
    black: str
    event: str
    year: str


@dataclass
class ExtractedPosition:
    board: chess.Board
    metadata: GameMetadata


def extract_positions(
    ref: GameRef,
    *,
    marker_text: str,
    positions_per_game: int,
) -> list[ExtractedPosition]:
    """Parse one game with python-chess and return boards at CQL markers."""
    text = _get_file_text(ref.file_path)
    chunk = text[ref.chunk_start : ref.chunk_end]

    game = chess_pgn.read_game(io.StringIO(chunk))
    if game is None:
        return []

    headers = game.headers
    meta = GameMetadata(
        white=headers.get("White", "?"),
        black=headers.get("Black", "?"),
        event=headers.get("Event", "?"),
        year=headers.get("Date", "????.??.??").split(".")[0],
    )

    results: list[ExtractedPosition] = []
    for node in game.mainline():
        if node.comment.strip() == marker_text:
            results.append(ExtractedPosition(board=node.board().copy(), metadata=meta))
            if len(results) >= positions_per_game:
                break
    return results


# ---------------------------------------------------------------------------
# Stockfish analysis helpers
# ---------------------------------------------------------------------------


def winning_chances_from_cp(cp: int) -> float:
    """Logistic sigmoid mapping centipawns to winning chances in [-1, 1].

    Coefficient taken from Lichess / Anki-Chess-2.0.
    """
    clamped = min(1000, max(-1000, cp))
    return 2.0 / (1.0 + math.exp(-0.00368208 * clamped)) - 1.0


def score_to_cp(score: chess.engine.Score) -> int:
    """Convert engine score to centipawns (mate mapped to +/-10000)."""
    cp = score.score(mate_score=10000)
    return cp if cp is not None else 0


def material_string(board: chess.Board) -> str:
    """Material balance like ``KRPkrp``."""
    parts: list[str] = []
    for color in (chess.WHITE, chess.BLACK):
        for pt in (
            chess.KING,
            chess.QUEEN,
            chess.ROOK,
            chess.BISHOP,
            chess.KNIGHT,
            chess.PAWN,
        ):
            char = chess.piece_symbol(pt)
            if color == chess.WHITE:
                char = char.upper()
            parts.append(char * len(board.pieces(pt, color)))
    return "".join(parts)


@dataclass
class PositionClassification:
    fen: str
    expected_result: str  # "white", "black", "draw"
    sharp: bool
    material: str
    metadata: GameMetadata | None = None


def classify_position(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    *,
    limit: chess.engine.Limit,
    winning_threshold_cp: int,
    sharp_threshold_wc: float,
) -> PositionClassification:
    """Analyse a position and classify it."""
    results = engine.analyse(board, limit, multipv=2)

    best_cp = score_to_cp(results[0]["score"].white())

    if best_cp > winning_threshold_cp:
        expected = "white"
    elif best_cp < -winning_threshold_cp:
        expected = "black"
    else:
        expected = "draw"

    if len(results) < 2:
        is_sharp = True  # only one legal move
    else:
        second_cp = score_to_cp(results[1]["score"].white())
        gap = abs(
            winning_chances_from_cp(best_cp)
            - winning_chances_from_cp(second_cp)
        )
        is_sharp = gap >= sharp_threshold_wc

    return PositionClassification(
        fen=board.fen(),
        expected_result=expected,
        sharp=is_sharp,
        material=material_string(board),
    )


# ---------------------------------------------------------------------------
# Quota-driven collection
# ---------------------------------------------------------------------------


def collect_positions(
    refs: list[GameRef],
    *,
    engine: chess.engine.SimpleEngine,
    limit: chess.engine.Limit,
    n: int,
    sharp_quota: int,
    winning_quota: int,
    positions_per_game: int,
    marker_text: str,
    winning_threshold_cp: int,
    sharp_threshold_wc: float,
) -> list[tuple[PositionClassification, str]]:
    """Return list of ``(classification, source_stem)`` tuples."""
    collected: list[tuple[PositionClassification, str]] = []
    sharp_count = 0
    winning_count = 0
    analysed = 0

    non_sharp_quota = n - sharp_quota
    draw_quota = n - winning_quota

    pbar = tqdm(total=n if n < 2**63 else None, desc="Collecting positions", unit="pos")

    for ref in refs:
        if len(collected) >= n:
            break

        extracted = extract_positions(
            ref, marker_text=marker_text, positions_per_game=positions_per_game
        )
        source = ref.file_path.stem

        for ep in extracted:
            if len(collected) >= n:
                break

            pc = classify_position(
                engine,
                ep.board,
                limit=limit,
                winning_threshold_cp=winning_threshold_cp,
                sharp_threshold_wc=sharp_threshold_wc,
            )
            pc.metadata = ep.metadata
            analysed += 1
            is_winning = pc.expected_result != "draw"

            # Enforce independent quotas — skip if any axis is full.
            if pc.sharp and sharp_count >= sharp_quota:
                continue
            if not pc.sharp and (len(collected) - sharp_count) >= non_sharp_quota:
                continue
            if is_winning and winning_count >= winning_quota:
                continue
            if not is_winning and (len(collected) - winning_count) >= draw_quota:
                continue

            collected.append((pc, source))
            if pc.sharp:
                sharp_count += 1
            if is_winning:
                winning_count += 1
            pbar.update(1)
            pbar.set_postfix_str(
                f"sharp={sharp_count} win={winning_count} analysed={analysed}",
                refresh=False,
            )

    pbar.close()
    return collected


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

BASE_CSV_FIELDS = ["fen", "expected_result", "sharp", "material", "source"]
METADATA_CSV_FIELDS = ["white", "black", "event", "year"]


def write_csv(
    positions: list[tuple[PositionClassification, str]],
    output: Path,
    *,
    include_metadata: bool = False,
) -> None:
    fields = BASE_CSV_FIELDS + (METADATA_CSV_FIELDS if include_metadata else [])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for pc, source in positions:
            row: dict[str, object] = {
                "fen": pc.fen,
                "expected_result": pc.expected_result,
                "sharp": pc.sharp,
                "material": pc.material,
                "source": source,
            }
            if include_metadata and pc.metadata:
                row["white"] = pc.metadata.white
                row["black"] = pc.metadata.black
                row["event"] = pc.metadata.event
                row["year"] = pc.metadata.year
            writer.writerow(row)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a training CSV from CQL-annotated PGN endgame files.",
    )

    # I/O
    p.add_argument(
        "--pgn",
        required=True,
        help="PGN file or directory of PGN files (scanned recursively).",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Path to the output CSV file.",
    )
    p.add_argument(
        "--marker-text",
        default="CQL",
        help="Comment marker text. Default: CQL.",
    )
    p.add_argument(
        "--metadata",
        action="store_true",
        default=False,
        help="Include white, black, event, year columns in the CSV.",
    )

    # Quotas
    p.add_argument(
        "--n",
        type=int,
        required=True,
        help="Maximum number of positions (-1 for unlimited).",
    )
    p.add_argument(
        "--sharp",
        type=int,
        default=None,
        help="Maximum sharp positions (-1 for unlimited). Default: N.",
    )
    p.add_argument(
        "--winning",
        type=int,
        default=None,
        help="Maximum winning positions (-1 for unlimited). Default: N.",
    )
    p.add_argument(
        "--per-pgn",
        action="store_true",
        default=False,
        help="Apply quotas (N, sharp, winning) per PGN file instead of globally.",
    )

    # Sampling
    p.add_argument(
        "--min-matches",
        type=int,
        default=1,
        help="Minimum CQL markers per game to be considered. Default: 1.",
    )
    p.add_argument(
        "--positions-per-game",
        type=int,
        default=1,
        help="Number of CQL positions to extract per game. Default: 1.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility.",
    )

    # Engine
    p.add_argument(
        "--engine",
        default="stockfish",
        help="Path to UCI engine binary. Default: stockfish.",
    )
    engine_group = p.add_mutually_exclusive_group()
    engine_group.add_argument(
        "--time",
        type=float,
        default=0.1,
        help="Seconds per position for Stockfish. Default: 0.1.",
    )
    engine_group.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Search depth per position (alternative to --time).",
    )

    # Thresholds
    p.add_argument(
        "--winning-threshold",
        type=int,
        default=150,
        metavar="CP",
        help="Centipawn threshold for winning vs drawn. Default: 150.",
    )
    p.add_argument(
        "--sharp-threshold",
        type=float,
        default=0.2,
        metavar="WC",
        help=(
            "Winning-chance gap between best and second-best move to classify "
            "a position as sharp. Range 0.0-2.0. Default: 0.2."
        ),
    )

    args = p.parse_args(argv)
    _NO_LIMIT = 2**63
    if args.n == -1:
        args.n = _NO_LIMIT
    if args.sharp is None:
        args.sharp = args.n
    elif args.sharp == -1:
        args.sharp = _NO_LIMIT
    if args.winning is None:
        args.winning = args.n
    elif args.winning == -1:
        args.winning = _NO_LIMIT
    return args


def _group_refs_by_file(
    refs: list[GameRef],
) -> dict[Path, list[GameRef]]:
    groups: dict[Path, list[GameRef]] = {}
    for ref in refs:
        groups.setdefault(ref.file_path, []).append(ref)
    return groups


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.seed is not None:
        random.seed(args.seed)

    # Discover PGN files.
    discovery = discover_pgn_files(args.pgn)
    if discovery is None:
        return 1
    pgn_files, _ = discovery

    # Phase 1: fast scan.
    refs = fast_scan_for_refs(
        pgn_files,
        marker_text=args.marker_text.strip(),
        min_matches=args.min_matches,
    )
    print(
        f"Found {len(refs)} games with >= {args.min_matches} CQL marker(s) "
        f"across {len(pgn_files)} file(s)."
    )
    if not refs:
        print("Nothing to do.")
        return 0

    limit = (
        chess.engine.Limit(depth=args.depth)
        if args.depth is not None
        else chess.engine.Limit(time=args.time)
    )
    marker = args.marker_text.strip()
    engine = chess.engine.SimpleEngine.popen_uci(args.engine)
    all_positions: list[tuple[PositionClassification, str]] = []

    try:
        if args.per_pgn:
            # Quotas apply independently per PGN file.
            by_file = _group_refs_by_file(refs)
            for pgn_path in sorted(by_file):
                file_refs = by_file[pgn_path]
                random.shuffle(file_refs)
                print(f"\n--- {pgn_path.stem} ({len(file_refs)} games) ---")
                batch = collect_positions(
                    file_refs,
                    engine=engine,
                    limit=limit,
                    n=args.n,
                    sharp_quota=args.sharp,
                    winning_quota=args.winning,
                    positions_per_game=args.positions_per_game,
                    marker_text=marker,
                    winning_threshold_cp=args.winning_threshold,
                    sharp_threshold_wc=args.sharp_threshold,
                )
                all_positions.extend(batch)
        else:
            # Global quotas across all files.
            random.shuffle(refs)
            all_positions.extend(
                collect_positions(
                    refs,
                    engine=engine,
                    limit=limit,
                    n=args.n,
                    sharp_quota=args.sharp,
                    winning_quota=args.winning,
                    positions_per_game=args.positions_per_game,
                    marker_text=marker,
                    winning_threshold_cp=args.winning_threshold,
                    sharp_threshold_wc=args.sharp_threshold,
                )
            )
    finally:
        engine.quit()

    # Phase 3: write CSV.
    output_path = Path(args.output).expanduser()
    write_csv(all_positions, output_path, include_metadata=args.metadata)

    sharp_count = sum(1 for pc, _ in all_positions if pc.sharp)
    winning_count = sum(
        1 for pc, _ in all_positions if pc.expected_result != "draw"
    )
    print(f"\nWrote {len(all_positions)} positions to {output_path}")
    print(f"  Sharp: {sharp_count}, Non-sharp: {len(all_positions) - sharp_count}")
    print(f"  Winning: {winning_count}, Drawn: {len(all_positions) - winning_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
