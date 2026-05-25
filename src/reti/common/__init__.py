"""Shared helpers used across reti modules.

These were duplicated verbatim in three or four places before the refactor;
they now live here.
"""

from reti.common.pgn_discovery import (
    InputCollection,
    discover_input_files,
    discover_pgn_files,
    format_pgn_display_path,
    format_relative,
    relative_stem,
)
from reti.common.hashing import (
    canonical_json,
    manifest_fingerprint,
    sha256_file,
    sha256_text,
)
from reti.common.json_io import load_json, write_json
from reti.common.progress import (
    format_progress_label,
    make_terminal_safe,
    progress_write,
)
from reti.common.source_metadata import (
    classify_source_group,
    combined_source_bucket_key,
    combined_source_bucket_label,
    source_bucket_key,
    source_bucket_label,
    source_sort_key,
    source_stem,
)
from reti.common.subprocess_helpers import (
    describe_returncode,
    resolve_executable,
)

__all__ = [
    "InputCollection",
    "canonical_json",
    "describe_returncode",
    "discover_input_files",
    "discover_pgn_files",
    "format_pgn_display_path",
    "format_progress_label",
    "format_relative",
    "load_json",
    "make_terminal_safe",
    "manifest_fingerprint",
    "progress_write",
    "relative_stem",
    "resolve_executable",
    "sha256_file",
    "sha256_text",
    "classify_source_group",
    "combined_source_bucket_key",
    "combined_source_bucket_label",
    "source_bucket_key",
    "source_bucket_label",
    "source_sort_key",
    "source_stem",
    "write_json",
]
