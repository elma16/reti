from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from reti.common.hashing import canonical_json, manifest_fingerprint, sha256_file, sha256_text
from reti.common.json_io import load_json, write_json
from reti.common.source_metadata import (
    classify_source_group,
    combined_source_bucket_key,
    combined_source_bucket_label,
    source_bucket_key,
    source_bucket_label,
    source_sort_key,
    source_stem,
)
from reti.fce_combined_snapshot import (
    SnapshotError,
    classify_source_group as combined_classify_source_group,
)
from reti.fce_snapshot import (
    source_bucket_label as snapshot_source_bucket_label,
    source_sort_key as snapshot_source_sort_key,
)

CHESS_AVAILABLE = importlib.util.find_spec("chess") is not None
if CHESS_AVAILABLE:
    from reti.fce_eval_snapshot import source_bucket_from_source_pgn
else:
    source_bucket_from_source_pgn = None


class SourceMetadataTests(unittest.TestCase):
    def test_source_stem_and_date_sort_key_match_snapshot_ordering(self) -> None:
        self.assertEqual(source_stem("LumbrasGigaBase_OTB_2020-2024.pgn"), "LumbrasGigaBase_OTB_2020-2024")
        sources = [
            "LumbrasGigaBase_OTB_noDate.pgn",
            "CustomSource.pgn",
            "LumbrasGigaBase_OTB_1900-1949.pgn",
            "LumbrasGigaBase_OTB_2020-2024.pgn",
        ]
        self.assertEqual(
            sorted(sources, key=source_sort_key),
            [
                "LumbrasGigaBase_OTB_1900-1949.pgn",
                "LumbrasGigaBase_OTB_2020-2024.pgn",
                "CustomSource.pgn",
                "LumbrasGigaBase_OTB_noDate.pgn",
            ],
        )
        self.assertIs(source_sort_key, snapshot_source_sort_key)

    def test_original_snapshot_bucket_labels_are_preserved(self) -> None:
        self.assertEqual(source_bucket_key("LumbrasGigaBase_OTB_2025.pgn"), "2025")
        self.assertEqual(
            source_bucket_label("LumbrasGigaBase_OTB_2025_partial_release.pgn"),
            "2025 partial",
        )
        self.assertEqual(
            source_bucket_label("LumbrasGigaBase_Online_2025.pgn"),
            "LumbrasGigaBase Online 2025",
        )
        self.assertIs(source_bucket_label, snapshot_source_bucket_label)

    def test_combined_bucket_labels_include_source_group(self) -> None:
        self.assertEqual(
            combined_source_bucket_key("LumbrasGigaBase_OTB_2025.pgn"),
            "otb:2025",
        )
        self.assertEqual(
            combined_source_bucket_label("LumbrasGigaBase_OTB_2025_partial_release.pgn"),
            "OTB 2025 partial",
        )
        self.assertEqual(
            combined_source_bucket_key("LumbrasGigaBase_Online_2025.pgn"),
            "online:2025",
        )
        self.assertEqual(
            combined_source_bucket_label("LumbrasGigaBase_Online_2025.pgn"),
            "Online 2025",
        )
        self.assertEqual(combined_source_bucket_label("Custom_partial_release.pgn"), "Custom partial")

    def test_source_group_errors_keep_calling_module_exception_type(self) -> None:
        self.assertEqual(classify_source_group("LumbrasGigaBase_OTB_2025.pgn"), "otb")
        self.assertEqual(classify_source_group("LumbrasGigaBase_Online_2025.pgn"), "online")
        with self.assertRaises(ValueError):
            classify_source_group("Custom.pgn")
        with self.assertRaises(SnapshotError):
            combined_classify_source_group("Custom.pgn")

    @unittest.skipIf(not CHESS_AVAILABLE, "python-chess is not installed in this environment")
    def test_legacy_eval_source_bucket_uses_shared_source_stem(self) -> None:
        assert source_bucket_from_source_pgn is not None
        self.assertEqual(
            source_bucket_from_source_pgn("LumbrasGigaBase_OTB_2025.pgn"),
            "LumbrasGigaBase_OTB_2025",
        )
        self.assertEqual(source_bucket_from_source_pgn(""), "")


class HashingTests(unittest.TestCase):
    def test_canonical_json_and_hash_helpers_are_stable(self) -> None:
        payload = {"b": [2, 1], "a": {"z": True}}
        text = canonical_json(payload)
        self.assertEqual(text, '{"a":{"z":true},"b":[2,1]}')
        self.assertEqual(sha256_text(text), sha256_text(canonical_json(json.loads(text))))

    def test_file_and_manifest_hashes_are_content_based(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "payload.txt"
            path.write_text("payload\n", encoding="utf-8")
            self.assertEqual(sha256_file(path), sha256_text("payload\n"))

        base = {"schemaVersion": 1, "value": {"b": 2, "a": 1}}
        with_fingerprint = {**base, "fingerprint": "old"}
        self.assertEqual(manifest_fingerprint(base), manifest_fingerprint(with_fingerprint))

    def test_json_io_uses_canonical_trailing_newline_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "payload.json"
            write_json(path, {"b": 2, "a": 1})
            self.assertEqual(path.read_text(encoding="utf-8"), '{"a":1,"b":2}\n')
            self.assertEqual(load_json(path), {"a": 1, "b": 2})


if __name__ == "__main__":
    unittest.main()
