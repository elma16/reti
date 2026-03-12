from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn as chess_pgn


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


def discover_pgn_files(location: str) -> tuple[list[Path], Path | None] | None:
    path = Path(location).expanduser()

    if path.is_file():
        if path.suffix.lower() != ".pgn":
            print(f"Error: '{location}' is not a .pgn file.")
            return None
        return [path], None

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
        return files, path

    print(f"Error: '{location}' is not a valid file or directory.")
    return None


def format_pgn_display_path(pgn_path: Path, root: Path | None) -> str:
    if root is None:
        return pgn_path.name

    try:
        return str(pgn_path.relative_to(root))
    except ValueError:
        return pgn_path.name


def side_name(turn: bool) -> str:
    return "white" if turn == chess.WHITE else "black"


def comment_matches_marker(comment: str, marker_text: str) -> bool:
    return comment.strip() == marker_text


def parse_annotated_pgn(
    pgn_path: Path,
    *,
    marker_text: str,
) -> list[ParsedAnnotatedGame]:
    parsed_games: list[ParsedAnnotatedGame] = []

    with pgn_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        game_index = 0
        while True:
            game = chess_pgn.read_game(handle)
            if game is None:
                break

            game_index += 1
            move_uci_sequence = tuple(move.uci() for move in game.mainline_moves())
            positions: list[AnnotatedPosition] = []
            for node in game.mainline():
                if not comment_matches_marker(node.comment, marker_text):
                    continue

                board = node.board()
                positions.append(
                    AnnotatedPosition(
                        ply_index=board.ply(),
                        fullmove_number=board.fullmove_number,
                        move_san=node.san(),
                        move_uci=node.uci(),
                        fen=board.fen(),
                        side_to_move=side_name(board.turn),
                        piece_count=len(board.piece_map()),
                    )
                )

            parsed_games.append(
                ParsedAnnotatedGame(
                    game_index=game_index,
                    headers=dict(game.headers),
                    parse_errors=tuple(
                        str(error) for error in (getattr(game, "errors", None) or [])
                    ),
                    move_uci_sequence=move_uci_sequence,
                    positions=tuple(positions),
                )
            )

    return parsed_games
