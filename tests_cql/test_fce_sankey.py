from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reti.annotated_pgn import parse_annotated_pgn
from reti.fce_sankey import (
    build_game_key,
    build_sankey_data,
    build_game_sequences,
    collect_hits_from_pgn_dir,
    render_fce_sankey,
    render_sankey_html,
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _game_headers(event: str, white: str = "White", black: str = "Black") -> str:
    return (
        f'[Event "{event}"]\n'
        '[Site "Test"]\n'
        '[Date "2026.03.12"]\n'
        '[Round "1"]\n'
        f'[White "{white}"]\n'
        f'[Black "{black}"]\n'
        '[Result "*"]\n'
        "\n"
    )


class TestFceSankey(unittest.TestCase):
    def test_build_game_key_matches_same_game_and_separates_different_games(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "2-0Pp.pgn"
            second = root / "2-1P.pgn"
            third = root / "other.pgn"

            shared_game = _game_headers("Shared") + "1. e4 {CQL} e5 2. Nf3 Nc6 *\n"
            _write_text(first, shared_game)
            _write_text(second, shared_game)
            _write_text(
                third,
                _game_headers("Different") + "1. d4 {CQL} d5 2. c4 e6 *\n",
            )

            first_game = parse_annotated_pgn(first, marker_text="CQL")[0]
            second_game = parse_annotated_pgn(second, marker_text="CQL")[0]
            third_game = parse_annotated_pgn(third, marker_text="CQL")[0]

        self.assertEqual(build_game_key(first_game), build_game_key(second_game))
        self.assertNotEqual(build_game_key(first_game), build_game_key(third_game))

    def test_build_game_sequences_resolves_same_ply_overlap_and_collapses_repeats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_root = root / "annotated"

            parent_game_one = _game_headers("Game One") + (
                "1. e4 {CQL} e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *\n"
            )
            child_game_one = _game_headers("Game One") + (
                "1. e4 {CQL} e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *\n"
            )
            rook_game_one = _game_headers("Game One") + (
                "1. e4 e5 2. Nf3 {CQL} Nc6 3. Bb5 {CQL} a6 4. Ba4 Nf6 *\n"
            )
            knight_game_one = _game_headers("Game One") + (
                "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 {CQL} Nf6 *\n"
            )

            child_game_two = _game_headers("Game Two", white="A", black="B") + (
                "1. d4 {CQL} d5 2. c4 e6 3. Nc3 {CQL} Nf6 *\n"
            )
            rook_game_two = _game_headers("Game Two", white="A", black="B") + (
                "1. d4 d5 2. c4 {CQL} e6 3. Nc3 Nf6 *\n"
            )

            _write_text(
                pgn_root / "2-0Pp.pgn",
                parent_game_one,
            )
            _write_text(
                pgn_root / "2-1P.pgn",
                child_game_one + "\n" + child_game_two,
            )
            _write_text(
                pgn_root / "6-2-0Rr.pgn",
                rook_game_one + "\n" + rook_game_two,
            )
            _write_text(
                pgn_root / "nested" / "3-1Np.pgn",
                knight_game_one,
            )

            hits_by_game, warnings, skipped_files, parsed_files = collect_hits_from_pgn_dir(
                str(pgn_root),
                marker_text="CQL",
            )

        assert hits_by_game is not None
        sequences = build_game_sequences(hits_by_game)
        self.assertEqual(parsed_files, 4)
        self.assertEqual(skipped_files, 0)
        self.assertEqual(warnings, ())
        self.assertEqual(len(sequences), 2)

        ordered_sequences = sorted(sequences.values(), key=len, reverse=True)
        self.assertEqual(
            ordered_sequences[0],
            ["2-1P", "6-2-0Rr", "3-1Np"],
        )
        self.assertEqual(
            ordered_sequences[1],
            ["2-1P", "6-2-0Rr", "2-1P"],
        )

    def test_build_sankey_data_counts_start_end_and_return_transitions(self):
        game_sequences = {
            "g1": ["2-1P", "6-2-0Rr", "3-1Np"],
            "g2": ["2-1P", "6-2-0Rr", "2-1P"],
        }

        data = build_sankey_data(game_sequences)

        self.assertEqual(data.total_games, 2)
        self.assertEqual(data.total_transitions, 8)
        self.assertEqual(data.unique_endings, 3)

        link_map = {
            (data.node_labels[source], data.node_labels[target]): value
            for source, target, value in zip(
                data.link_sources,
                data.link_targets,
                data.link_values,
            )
        }
        self.assertEqual(link_map[("Start", "King + Pawn vs King")], 2)
        self.assertEqual(link_map[("King + Pawn vs King", "6.2 Rook vs Rook")], 2)
        self.assertEqual(link_map[("6.2 Rook vs Rook", "3.1 Knight vs Pawns")], 1)
        self.assertEqual(link_map[("6.2 Rook vs Rook", "King + Pawn vs King")], 1)
        self.assertEqual(link_map[("3.1 Knight vs Pawns", "End")], 1)
        self.assertEqual(link_map[("King + Pawn vs King", "End")], 1)

    def test_render_sankey_html_includes_plotly_payload(self):
        data = build_sankey_data({"g1": ["2-1P", "6-2-0Rr"]})
        html = render_sankey_html(
            data,
            title="Demo Sankey",
            warnings=("warning one",),
        )

        self.assertIn("Plotly.newPlot", html)
        self.assertIn("Demo Sankey", html)
        self.assertIn("King + Pawn vs King", html)
        self.assertIn("warning one", html)
        self.assertIn("https://cdn.plot.ly/plotly-2.35.2.min.js", html)

    def test_main_renders_html_from_recursive_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pgn_root = root / "annotated"
            output_html = root / "docs" / "fce_sankey.html"

            _write_text(
                pgn_root / "2-1P.pgn",
                _game_headers("One") + "1. e4 {CQL} e5 2. Nf3 Nc6 *\n",
            )
            _write_text(
                pgn_root / "nested" / "6-2-0Rr.pgn",
                _game_headers("One") + "1. e4 e5 2. Nf3 {CQL} Nc6 *\n",
            )

            exit_code = render_fce_sankey(
                pgn_dir=str(pgn_root),
                output_html=str(output_html),
                marker_text="CQL",
                title="Recursive Sankey",
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_html.exists())
            html = output_html.read_text(encoding="utf-8")
            self.assertIn("Recursive Sankey", html)
            self.assertIn("Rook vs Rook", html)
            self.assertIn("King + Pawn vs King", html)


if __name__ == "__main__":
    unittest.main()
