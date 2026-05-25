from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reti.annotated_pgn import iter_annotated_pgn, parse_annotated_pgn
from reti.pgn_utils import find_pgn_utils_binary


pytestmark = pytest.mark.skipif(
    find_pgn_utils_binary() is None,
    reason="native reti-pgn-utils binary is not built",
)


def test_parse_annotated_pgn_uses_rust_playthrough_for_fen_and_uci(tmp_path: Path) -> None:
    pgn = tmp_path / "fen.pgn"
    pgn.write_text(
        '[Event "Fen"]\n'
        '[Result "*"]\n'
        '[SetUp "1"]\n'
        '[FEN "8/8/8/8/8/8/4K3/6k1 w - - 0 1"]\n'
        "\n"
        "1. Kd2 {CQL} Kh1 { SPECIAL } *\n",
        encoding="utf-8",
    )

    games = parse_annotated_pgn(pgn, marker_text="SPECIAL")

    assert len(games) == 1
    assert games[0].headers["Event"] == "Fen"
    assert games[0].move_uci_sequence == ("e2d2", "g1h1")
    assert len(games[0].positions) == 1
    position = games[0].positions[0]
    assert position.move_san == "Kh1"
    assert position.move_uci == "g1h1"
    assert position.side_to_move == "white"
    assert position.piece_count == 2
    assert position.fen.startswith("8/8/8/8/8/8/3K4/7k w")


def test_parse_annotated_pgn_reports_replay_errors_without_python_chess(tmp_path: Path) -> None:
    pgn = tmp_path / "bad.pgn"
    pgn.write_text(
        '[Event "Bad"]\n[Result "*"]\n\n1. Ke2 {CQL} *\n',
        encoding="utf-8",
    )

    games = parse_annotated_pgn(pgn, marker_text="CQL")

    assert len(games) == 1
    assert games[0].parse_errors == ("illegal SAN at ply 1: Ke2",)
    assert games[0].positions == ()


def test_iter_annotated_pgn_keeps_progress_contract(tmp_path: Path) -> None:
    pgn = tmp_path / "two.pgn"
    pgn.write_text(
        '[Event "One"]\n[Result "*"]\n\n1. e4 {CQL} *\n\n'
        '[Event "Two"]\n[Result "*"]\n\n1. d4 {CQL} *\n',
        encoding="utf-8",
    )

    rows = list(iter_annotated_pgn(pgn, marker_text="CQL"))

    assert [game.game_index for game, _ in rows] == [1, 2]
    assert sum(bytes_seen for _, bytes_seen in rows) == pgn.stat().st_size
