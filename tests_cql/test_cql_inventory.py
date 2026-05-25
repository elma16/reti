from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CQL_ROOT = REPO_ROOT / "cql-files"
SOURCE_DIRS = ("100endings", "FCE", "lila", "mates", "silly")


def _cql_files() -> list[Path]:
    files: list[Path] = []
    for dirname in SOURCE_DIRS:
        files.extend(sorted((CQL_ROOT / dirname).rglob("*.cql")))
    return files


def _has_doc_comment(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").lstrip()
    return text.startswith(("//", ";;", "/*"))


def _blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _non_comment_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", ";;", "#")):
            continue
        lines.append(line)
    return lines


class CqlInventoryTests(unittest.TestCase):
    def test_all_source_cql_files_have_intent_comments(self) -> None:
        missing = [str(path.relative_to(REPO_ROOT)) for path in _cql_files() if not _has_doc_comment(path)]
        self.assertEqual([], missing)

    def test_source_cql_files_are_not_empty_or_exact_duplicates(self) -> None:
        empty = [str(path.relative_to(REPO_ROOT)) for path in _cql_files() if not path.read_text(encoding="utf-8", errors="replace").strip()]
        self.assertEqual([], empty)

        by_hash: dict[str, list[str]] = {}
        for path in _cql_files():
            by_hash.setdefault(_blob_sha(path), []).append(str(path.relative_to(REPO_ROOT)))
        duplicates = [paths for paths in by_hash.values() if len(paths) > 1]
        self.assertEqual([], duplicates)

    def test_mates2_and_tosort_have_been_refiled(self) -> None:
        leftovers: list[str] = []
        for dirname in ("mates2", "tosort"):
            root = CQL_ROOT / dirname
            if root.exists():
                leftovers.extend(str(path.relative_to(REPO_ROOT)) for path in root.rglob("*.cql"))
        self.assertEqual([], leftovers)

    def test_manifest_cases_point_to_real_cql_and_two_example_datasets(self) -> None:
        manifest_path = REPO_ROOT / "tests_cql" / "fixtures" / "cases.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fixtures_root = manifest_path.parent
        datasets = manifest.get("datasets", {})

        problems: list[str] = []
        for case in manifest.get("cases", []):
            cql = case.get("cql")
            dataset_name = case.get("dataset")
            if cql and not (REPO_ROOT / cql).exists():
                problems.append(f"missing cql: {cql}")
            if not dataset_name or dataset_name not in datasets:
                problems.append(f"missing dataset for case: {case}")
                continue

            dataset = datasets[dataset_name]
            if "fen" in dataset:
                fen_path = fixtures_root / dataset["fen"]
                if not fen_path.exists():
                    problems.append(f"missing fen dataset: {dataset['fen']}")
                    continue
                if len(_non_comment_lines(fen_path)) < 2:
                    problems.append(f"fen dataset needs positive and negative examples: {dataset['fen']}")
            elif "pgn" in dataset:
                pgn_path = fixtures_root / dataset["pgn"]
                if not pgn_path.exists():
                    problems.append(f"missing pgn dataset: {dataset['pgn']}")
                    continue
                event_count = sum(
                    1
                    for line in pgn_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    if line.startswith("[Event ")
                )
                if event_count < 2:
                    problems.append(f"pgn dataset needs positive and negative examples: {dataset['pgn']}")
            else:
                problems.append(f"dataset must declare fen or pgn: {dataset_name}")

        self.assertEqual([], problems)


if __name__ == "__main__":
    unittest.main()
