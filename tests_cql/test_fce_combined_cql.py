from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from reti.fce_combined_cql import (
    build_combined_marker_cql,
    render_combined_cql,
    select_entries,
)


class TestFceCombinedCql(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.cql_table_dir = self.repo_root / "cql-files" / "FCE" / "table"

    def test_select_entries_uses_specificity_order_and_skips_alias_duplicates(self) -> None:
        entries, skipped = select_entries(self.cql_table_dir)
        stems = [entry.stem for entry in entries]

        self.assertEqual(stems[0], "1-4BN")
        self.assertEqual(stems[1], "1-5NNp")
        self.assertLess(stems.index("1-5NNp"), stems.index("2-1P"))
        self.assertIn("6-2-2RPPrConnected", stems)
        self.assertIn("8-1RNrNoPawns", stems)
        self.assertIn("8-2RBrNoPawns", stems)
        self.assertIn("10-2QrNoPawns", stems)
        self.assertIn("10-7-1QbrrNoPawns", stems)
        self.assertNotIn("8-1RNrPp", stems)
        self.assertNotIn("8-2RBrPp", stems)
        self.assertNotIn("10-2QrPp", stems)
        self.assertLess(stems.index("6-2-2RPPrConnected"), stems.index("6-2-2RPPr"))
        self.assertLess(stems.index("6-2-2RPPr"), stems.index("6-2-0Rr"))
        self.assertLess(stems.index("8-1RNrNoPawns"), stems.index("8-1RNr"))
        self.assertLess(stems.index("8-2RBrNoPawns"), stems.index("8-2RBr"))
        self.assertLess(stems.index("9-3QPq"), stems.index("9-2Qq"))
        self.assertLess(stems.index("10-2QrNoPawns"), stems.index("10-2Qr"))
        self.assertLess(
            stems.index("10-7-1QbrrNoPawns"),
            stems.index("10-7-1Qbrr"),
        )

        skipped_pairs = {entry.stem: entry.duplicate_of for entry in skipped}
        self.assertEqual(skipped_pairs["8-1RNrPp"], "8-1RNr")
        self.assertEqual(skipped_pairs["8-2RBrPp"], "8-2RBr")
        self.assertEqual(skipped_pairs["10-2QrPp"], "10-2Qr")
        self.assertEqual(skipped_pairs["10-7-1QbrrPp"], "10-7-1Qbrr")

    def test_render_combined_cql_uses_one_preamble_and_marker_comments(self) -> None:
        entries, _ = select_entries(self.cql_table_dir, include_auxiliary=False)
        text = render_combined_cql(entries[:3])

        self.assertEqual(text.count("cql("), 1)
        self.assertIn("cql(quiet)", text)
        self.assertIn('comment("1-4BN")', text)
        self.assertIn('comment("1-5NNp")', text)
        self.assertIn('comment("2-1P")', text)
        self.assertLess(
            text.index('"1-4BN"'),
            text.index('"1-5NNp"'),
        )
        self.assertLess(
            text.index('"1-5NNp"'),
            text.index('"2-1P"'),
        )
        self.assertIn("\n    or\n", text)

    def test_build_combined_marker_cql_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_cql = Path(tmpdir) / "fce-table-markers.cql"
            result = build_combined_marker_cql(
                cql_table_dir=self.cql_table_dir,
                output_cql=output_cql,
                force=False,
            )

            self.assertEqual(result.output_cql, output_cql.resolve())
            self.assertTrue(output_cql.exists())
            text = output_cql.read_text(encoding="utf-8")
            self.assertIn('comment("1-4BN")', text)
            self.assertIn('comment("6-2-2RPPrConnected")', text)
            self.assertIn('comment("10-2QrNoPawns")', text)
            self.assertIn('comment("10-7-1QbrrNoPawns")', text)
            self.assertIn(
                'comment("2-1P")\n        comment("2-0Pp")',
                text,
            )
            self.assertIn(
                'comment("6-2-2RPPr")\n        comment("6-2-0Rr")',
                text,
            )
            self.assertIn(
                'comment("9-3QPq")\n        comment("9-2Qq")',
                text,
            )
            self.assertLess(
                text.index("// 6-2-2RPPr:"),
                text.index("// 6-2-0Rr:"),
            )
            self.assertLess(
                text.index("// 9-3QPq:"),
                text.index("// 9-2Qq:"),
            )
            self.assertLess(
                text.index('comment("10-2QrNoPawns")'),
                text.index("// 10-2Qr:"),
            )
            self.assertIn(
                'comment("10-2QrNoPawns")\n        comment("10-2Qr")',
                text,
            )


if __name__ == "__main__":
    unittest.main()
