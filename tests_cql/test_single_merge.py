"""Unit tests for the cross-script single-output merge."""

from __future__ import annotations

from pathlib import Path

import pytest

from reti.common.pgn_discovery import InputCollection
from reti.cql.runner import JobResult
import reti.cql.single_merge as single_merge_module
from reti.cql.single_merge import merge_single_output


SOURCE_PGN = """[Event "Test"]
[Site "?"]
[Date "2024.01.01"]
[Round "1"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 1-0


[Event "Test"]
[Site "?"]
[Date "2024.01.02"]
[Round "2"]
[White "Carol"]
[Black "Dave"]
[Result "0-1"]

1. d4 d5 2. c4 e6 3. Nc3 Nf6 0-1


[Event "Test"]
[Site "?"]
[Date "2024.01.03"]
[Round "3"]
[White "Eve"]
[Black "Frank"]
[Result "1/2-1/2"]

1. Nf3 Nf6 2. g3 g6 1/2-1/2
"""


class RecordingProgress:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.updates: list[int] = []
        self.postfixes: list[str] = []
        self.closed = False

    def update(self, amount: int) -> None:
        self.updates.append(amount)

    def set_postfix_str(self, text: str) -> None:
        self.postfixes.append(text)

    def close(self) -> None:
        self.closed = True


def _hedgehog_annotated() -> str:
    """First game annotated by a hypothetical hedgehog script at move 4."""
    return """[Event "Test"]
[Site "?"]
[Date "2024.01.01"]
[Round "1"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 {hedgehog} Nf6 1-0
"""


def _maroczy_annotated() -> str:
    """First game annotated by a hypothetical maroczy script at move 2."""
    return """[Event "Test"]
[Site "?"]
[Date "2024.01.01"]
[Round "1"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 c5 2. Nf3 {maroczy} d6 3. d4 cxd4 4. Nxd4 Nf6 1-0
"""


def _qgd_annotated() -> str:
    """Second game annotated by a hypothetical qgd script at move 2."""
    return """[Event "Test"]
[Site "?"]
[Date "2024.01.02"]
[Round "2"]
[White "Carol"]
[Black "Dave"]
[Result "0-1"]

1. d4 d5 2. c4 {qgd} e6 3. Nc3 Nf6 0-1
"""


def _make_setup(tmp_path: Path) -> tuple[Path, InputCollection, Path, Path, Path, Path]:
    pgn_root = tmp_path / "pgns"
    pgn_root.mkdir()
    source_pgn = pgn_root / "games.pgn"
    source_pgn.write_text(SOURCE_PGN, encoding="utf-8")

    cql_root = tmp_path / "cql"
    cql_root.mkdir()

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    pair_dir = output_dir / "games"
    pair_dir.mkdir()
    hedgehog_out = pair_dir / "hedgehog.pgn"
    maroczy_out = pair_dir / "maroczy.pgn"
    qgd_out = pair_dir / "qgd.pgn"

    hedgehog_out.write_text(_hedgehog_annotated(), encoding="utf-8")
    maroczy_out.write_text(_maroczy_annotated(), encoding="utf-8")
    qgd_out.write_text(_qgd_annotated(), encoding="utf-8")

    pgn_inputs = InputCollection(files=[source_pgn], root=pgn_root)
    return source_pgn, pgn_inputs, output_dir, hedgehog_out, maroczy_out, qgd_out


def _make_results(
    source_pgn: Path,
    cql_root: Path,
    outputs: dict[str, Path],
) -> list[JobResult]:
    return [
        JobResult(
            pgn_path=source_pgn,
            cql_path=cql_root / f"{stem}.cql",
            output_pgn=output_pgn,
            success=True,
            match_count=1,
            returncode=0,
            stdout="",
            stderr="",
        )
        for stem, output_pgn in outputs.items()
    ]


def test_merge_matched_only_stacks_comments_from_multiple_scripts(tmp_path: Path) -> None:
    source_pgn, pgn_inputs, output_dir, hedgehog_out, maroczy_out, qgd_out = _make_setup(tmp_path)
    cql_root = tmp_path / "cql"

    results = _make_results(
        source_pgn,
        cql_root,
        {"hedgehog": hedgehog_out, "maroczy": maroczy_out, "qgd": qgd_out},
    )

    merged = merge_single_output(
        results,
        pgn_inputs,
        output_dir,
        include_unmatched=False,
    )

    assert len(merged) == 1
    text = merged[0].read_text(encoding="utf-8")

    # Both annotations on the first game appear at the right positions
    assert "maroczy" in text
    assert "hedgehog" in text
    # Second game's annotation appears
    assert "qgd" in text
    # Third game (no match) is excluded
    assert 'White "Eve"' not in text

    # First game should appear exactly once (deduplicated across the 2 scripts that matched it)
    assert text.count('White "Alice"') == 1

    # The per-pair output files have been removed after folding into the merged PGN
    assert not hedgehog_out.exists()
    assert not maroczy_out.exists()
    assert not qgd_out.exists()


def test_merge_include_unmatched_emits_unmatched_games_unannotated(tmp_path: Path) -> None:
    source_pgn, pgn_inputs, output_dir, hedgehog_out, maroczy_out, qgd_out = _make_setup(tmp_path)
    cql_root = tmp_path / "cql"

    results = _make_results(
        source_pgn,
        cql_root,
        {"hedgehog": hedgehog_out, "maroczy": maroczy_out, "qgd": qgd_out},
    )

    merged = merge_single_output(
        results,
        pgn_inputs,
        output_dir,
        include_unmatched=True,
    )

    assert len(merged) == 1
    text = merged[0].read_text(encoding="utf-8")

    # All three games present
    assert 'White "Alice"' in text
    assert 'White "Carol"' in text
    assert 'White "Eve"' in text

    # The third game has no annotation comments
    eve_section = text.split('White "Eve"')[1]
    assert "{" not in eve_section.split("1/2-1/2")[0]


def test_merge_skips_unmatched_when_flag_off(tmp_path: Path) -> None:
    source_pgn, pgn_inputs, output_dir, hedgehog_out, _, _ = _make_setup(tmp_path)
    cql_root = tmp_path / "cql"

    # Only the hedgehog script matched (game 1). Games 2 and 3 unmatched.
    results = _make_results(
        source_pgn,
        cql_root,
        {"hedgehog": hedgehog_out},
    )

    merged = merge_single_output(
        results,
        pgn_inputs,
        output_dir,
        include_unmatched=False,
    )
    text = merged[0].read_text(encoding="utf-8")

    assert 'White "Alice"' in text
    assert 'White "Carol"' not in text
    assert 'White "Eve"' not in text
    assert "hedgehog" in text


def test_single_script_merge_uses_per_pair_output_without_source_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_pgn, pgn_inputs, output_dir, hedgehog_out, _, _ = _make_setup(tmp_path)
    cql_root = tmp_path / "cql"
    results = _make_results(source_pgn, cql_root, {"hedgehog": hedgehog_out})
    expected_text = hedgehog_out.read_text(encoding="utf-8")
    original_iter = single_merge_module._iter_pgn_chunks

    def fail_if_source_is_read(pgn_path: Path, *, progress=None):
        if pgn_path == source_pgn:
            raise AssertionError("single-script fast path should not scan source PGN")
        yield from original_iter(pgn_path, progress=progress)

    monkeypatch.setattr(single_merge_module, "_iter_pgn_chunks", fail_if_source_is_read)

    merged = merge_single_output(
        results,
        pgn_inputs,
        output_dir,
        include_unmatched=False,
    )

    assert merged[0].read_text(encoding="utf-8") == expected_text
    assert not hedgehog_out.exists()


def test_merge_preserves_existing_source_comments(tmp_path: Path) -> None:
    """If the source PGN has comments at a ply, the merged output keeps them
    once even when several scripts add new comments at the same ply."""
    pgn_root = tmp_path / "pgns"
    pgn_root.mkdir()
    source_pgn = pgn_root / "games.pgn"
    source_pgn.write_text(
        """[Event "T"]
[Site "?"]
[Date "?"]
[Round "?"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 c5 {good move} 2. Nf3 *
""",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    pair_dir = out_dir / "games"
    pair_dir.mkdir()

    a_out = pair_dir / "a.pgn"
    a_out.write_text(
        """[Event "T"]
[Site "?"]
[Date "?"]
[Round "?"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 c5 {good move} {a-marker} 2. Nf3 *
""",
        encoding="utf-8",
    )
    b_out = pair_dir / "b.pgn"
    b_out.write_text(
        """[Event "T"]
[Site "?"]
[Date "?"]
[Round "?"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 c5 {good move} {b-marker} 2. Nf3 *
""",
        encoding="utf-8",
    )

    pgn_inputs = InputCollection(files=[source_pgn], root=pgn_root)
    cql_root = tmp_path / "cql"
    results = _make_results(source_pgn, cql_root, {"a": a_out, "b": b_out})

    merged = merge_single_output(results, pgn_inputs, out_dir, include_unmatched=False)
    text = merged[0].read_text(encoding="utf-8")

    # Source comment kept exactly once
    assert text.count("good move") == 1
    # Both script markers present
    assert "a-marker" in text
    assert "b-marker" in text


def test_merge_handles_malformed_variation_without_swallowing_next_game(tmp_path: Path) -> None:
    pgn_root = tmp_path / "pgns"
    pgn_root.mkdir()
    source_pgn = pgn_root / "broken.pgn"
    source_pgn.write_text(
        """[Event "Broken"]
[Site "Match, Moscow  (5)"]
[Date "1963.04.01"]
[Round "5"]
[White "Petrosian, Aram"]
[Black "Botvinnik, Mikhail"]
[Result "1-0"]

1. c4 g6 2. d4 Nf6 3. Nc3 d5 4. Nf3 Bg7 5. e3 O-O 6. Be2 dxc4 7. Bxc4 c5 8. d5 e6 9. dxe6 Qxd1+ 10. Kxd1 Bxe6 11. Bxe6 fxe6 12. Ke2 Nc6 13. Rd1 Rad8 14. Rxd8 Rxd8 15. Ng5 Re8 16. Nge4 Nxe4 17. Nxe4 b6 18. Rb1 Nb4 19. Bd2 Nd5 ( 19... Nxa2 1-0

[Event "Next"]
[Site "?"]
[Date "2024.01.02"]
[Round "1"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 e5 *
""",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    pair_dir = out_dir / "broken"
    pair_dir.mkdir(parents=True)
    annotated = pair_dir / "marker.pgn"
    annotated.write_text(
        """[Event "Broken"]
[Site "Match, Moscow  (5)"]
[Date "1963.04.01"]
[Round "5"]
[White "Petrosian, Aram"]
[Black "Botvinnik, Mikhail"]
[Result "1-0"]

1. c4 g6 2. d4 {marker} Nf6 1-0
""",
        encoding="utf-8",
    )

    results = _make_results(source_pgn, tmp_path / "cql", {"marker": annotated})
    merged = merge_single_output(
        results,
        InputCollection(files=[source_pgn], root=pgn_root),
        out_dir,
        include_unmatched=False,
    )
    text = merged[0].read_text(encoding="utf-8")

    assert 'White "Petrosian, Aram"' in text
    assert "marker" in text
    assert 'Event "Next"' not in text


def test_movetext_scanner_handles_compact_move_numbers() -> None:
    comments, insertions = single_merge_module._scan_comments_and_insertions(
        "1.e4 {a} e5 2.Nf3 {b} Nc6 *"
    )
    assert comments == {1: "a", 3: "b"}
    assert sorted(insertions) == [0, 1, 2, 3, 4]


def test_merge_progress_is_weighted_by_input_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_pgn, pgn_inputs, output_dir, hedgehog_out, _, _ = _make_setup(tmp_path)
    cql_root = tmp_path / "cql"
    results = _make_results(source_pgn, cql_root, {"hedgehog": hedgehog_out})
    expected_total = hedgehog_out.stat().st_size

    progress_instances: list[RecordingProgress] = []

    def recording_tqdm(**kwargs):
        progress = RecordingProgress(**kwargs)
        progress_instances.append(progress)
        return progress

    monkeypatch.setattr(single_merge_module, "tqdm_progress", recording_tqdm)

    merge_single_output(
        results,
        pgn_inputs,
        output_dir,
        include_unmatched=False,
    )

    assert len(progress_instances) == 1
    progress = progress_instances[0]
    assert progress.kwargs["total"] == expected_total
    assert progress.kwargs["unit"] == "B"
    assert sum(progress.updates) == expected_total
    assert any("scan games.pgn x hedgehog.cql" in item for item in progress.postfixes)
    assert any("move games.pgn" in item for item in progress.postfixes)
    assert progress.closed


def test_include_unmatched_requires_single_output_via_cli() -> None:
    """The CLI surface refuses --include-unmatched without --single-output."""
    from reti.cql.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(
            [
                "--pgn",
                "/tmp/x.pgn",
                "--cql-bin",
                "/tmp/cql",
                "--scripts",
                "/tmp/scripts",
                "-o",
                "/tmp/out",
                "--include-unmatched",
            ]
        )


def test_single_output_and_merge_output_are_mutually_exclusive_via_cli() -> None:
    from reti.cql.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(
            [
                "--pgn",
                "/tmp/x.pgn",
                "--cql-bin",
                "/tmp/cql",
                "--scripts",
                "/tmp/scripts",
                "-o",
                "/tmp/out",
                "--single-output",
                "--merge-output",
            ]
        )
