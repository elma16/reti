#!/usr/bin/env python3

from __future__ import annotations
import subprocess
from pathlib import Path

try:
    import chess.pgn
except Exception:
    chess = None

def run_cql(cql_bin: str, cql_file: str | Path, in_pgn: str | Path, out_pgn: str | Path,
            extra: list[str] | None = None, env: dict | None = None) -> tuple[int, str, str]:
    extra = extra or []
    cmd = [cql_bin, "-s", "-i", str(in_pgn), "-o", str(out_pgn), str(cql_file)] + extra
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout, r.stderr

def count_games(pgn_path: str | Path) -> int:
    if chess is not None:
        n = 0
        with open(pgn_path, "r", encoding="utf-8") as f:
            while chess.pgn.read_game(f) is not None:
                n += 1
        return n
    # Fallback: crude count by [Event] tags.
    n = 0
    with open(pgn_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("[Event "):
                n += 1
    return n

def expected_matches_from_pgn(pgn_path: str | Path, default: int = 1) -> int:
    if chess is None:
        return default
    with open(pgn_path, "r", encoding="utf-8") as f:
        game = chess.pgn.read_game(f)
    if game is None:
        return default
    for key in ("X-ExpectedCQLMatches", "ExpectedCQLMatches", "X-ExpectedMatches"):
        if key in game.headers:
            try:
                return int(game.headers[key])
            except Exception:
                pass
    return default

def assert_matches(cql_bin: str, cql_file: str | Path, in_pgn: str | Path,
                   expected_games: int, tmpdir: Path, env: dict | None = None):
    out_pgn = tmpdir / "out.pgn"
    code, out, err = run_cql(cql_bin, cql_file, in_pgn, out_pgn, env=env)
    if code != 0:
        raise AssertionError(f"CQL failed ({code})\nSTDERR:\n{err}\nSTDOUT:\n{out}")
    got = count_games(out_pgn)
    assert got == expected_games, (
        f"{cql_file}: expected {expected_games} matched game(s), got {got}\n"
        f"STDERR:\n{err}\nSTDOUT:\n{out}"
    )
