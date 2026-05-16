from __future__ import annotations

import csv
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

    def _canonical_table_targets(self) -> list[str]:
        manifest_path = self.repo_root / "cql-files" / "FCE" / "table" / "manifest.csv"
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            return [row["target"] for row in csv.DictReader(handle)]

    def test_readme_row_count_matches_curated_fce_table(self) -> None:
        readme_rows = self._readme_table_rows()
        curated_table_dir = self.repo_root / "cql-files" / "FCE" / "table"
        canonical_targets = self._canonical_table_targets()

        self.assertGreater(
            len(readme_rows), 0, "README FCE markdown table has no data rows."
        )
        self.assertGreater(
            len(canonical_targets), 0, "cql-files/FCE/table manifest has no rows."
        )
        self.assertEqual(
            len(readme_rows),
            len(canonical_targets),
            "README FCE markdown row count must match the canonical FCE table manifest.",
        )
        missing = [
            target
            for target in canonical_targets
            if not (curated_table_dir / f"{target}.cql").exists()
        ]
        self.assertEqual(missing, [], "Canonical FCE table scripts are missing.")


if __name__ == "__main__":
    unittest.main()
