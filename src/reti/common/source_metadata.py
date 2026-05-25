"""Shared source PGN classification and display helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar


LUMBRAS_OTB_PREFIX = "LumbrasGigaBase_OTB_"
LUMBRAS_ONLINE_PREFIX = "LumbrasGigaBase_Online_"

TError = TypeVar("TError", bound=Exception)


def source_stem(source_pgn: str) -> str:
    return Path(source_pgn).stem


def source_sort_key(source_pgn: str) -> tuple[int, str]:
    stem = source_stem(source_pgn)
    if stem.endswith("_noDate") or stem == "noDate":
        return 999999, stem
    for token in stem.replace("-", "_").split("_"):
        if len(token) >= 4 and token[:4].isdigit():
            return int(token[:4]), stem
        if token.isdigit():
            return int(token), stem
    return 999998, stem


def source_bucket_key(source_pgn: str) -> str:
    """Bucket key used by the original one-script-per-ending FCE snapshot."""
    stem = source_stem(source_pgn)
    if stem.startswith(LUMBRAS_OTB_PREFIX):
        return stem[len(LUMBRAS_OTB_PREFIX) :]
    return stem


def source_bucket_label(source_pgn: str) -> str:
    return source_bucket_key(source_pgn).replace("_partial_release", " partial").replace(
        "_", " "
    )


def classify_source_group(
    source_pgn: str,
    *,
    error_type: type[TError] = ValueError,
) -> str:
    stem = source_stem(source_pgn)
    if stem.startswith(LUMBRAS_OTB_PREFIX):
        return "otb"
    if stem.startswith(LUMBRAS_ONLINE_PREFIX):
        return "online"
    raise error_type(
        f"Could not classify source PGN {source_pgn!r}; expected "
        "LumbrasGigaBase_OTB_* or LumbrasGigaBase_Online_*"
    )


def combined_source_bucket_key(source_pgn: str) -> str:
    stem = source_stem(source_pgn)
    if stem.startswith(LUMBRAS_OTB_PREFIX):
        return f"otb:{stem[len(LUMBRAS_OTB_PREFIX):]}"
    if stem.startswith(LUMBRAS_ONLINE_PREFIX):
        return f"online:{stem[len(LUMBRAS_ONLINE_PREFIX):]}"
    return stem


def combined_source_bucket_label(source_pgn: str) -> str:
    stem = source_stem(source_pgn)
    if stem.startswith(LUMBRAS_OTB_PREFIX):
        bucket = stem[len(LUMBRAS_OTB_PREFIX) :].replace("_partial_release", " partial")
        return f"OTB {bucket.replace('_', ' ')}"
    if stem.startswith(LUMBRAS_ONLINE_PREFIX):
        bucket = stem[len(LUMBRAS_ONLINE_PREFIX) :].replace(
            "_partial_release", " partial"
        )
        return f"Online {bucket.replace('_', ' ')}"
    return stem.replace("_partial_release", " partial").replace("_", " ")
