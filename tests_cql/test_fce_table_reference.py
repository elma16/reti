from __future__ import annotations

import unittest
from pathlib import Path


README_HEADER = "## FCE table reference"
README_TABLE_HEADER = "| ID | Ending | Quantity | Percentage |"
README_TABLE_SEPARATOR = "|---|---|---|---|"


class TestFceTableReference(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]

    def _readme_table_rows(self) -> list[str]:
        lines = (self.repo_root / "README.md").read_text(encoding="utf-8").splitlines()
        in_section = False
        rows: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped == README_HEADER:
                in_section = True
                continue
            if in_section and stripped.startswith("## "):
                break
            if not in_section or not stripped.startswith("|"):
                continue
            if stripped in {README_TABLE_HEADER, README_TABLE_SEPARATOR}:
                continue
            rows.append(stripped)

        return rows

    def test_readme_row_count_matches_curated_fce_table(self) -> None:
        readme_rows = self._readme_table_rows()
        curated_table_dir = self.repo_root / "cql-files" / "FCE" / "table"
        curated_cql_files = sorted(curated_table_dir.glob("*.cql"))

        self.assertGreater(
            len(readme_rows), 0, "README FCE markdown table has no data rows."
        )
        self.assertGreater(
            len(curated_cql_files), 0, "cql-files/FCE/table has no curated .cql files."
        )
        self.assertEqual(
            len(readme_rows),
            len(curated_cql_files),
            "README FCE markdown row count must match the number of curated FCE table scripts.",
        )


if __name__ == "__main__":
    unittest.main()
