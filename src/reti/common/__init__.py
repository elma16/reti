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
from reti.common.progress import (
    format_progress_label,
    make_terminal_safe,
    progress_write,
)
from reti.common.subprocess_helpers import (
    describe_returncode,
    resolve_executable,
)

__all__ = [
    "InputCollection",
    "describe_returncode",
    "discover_input_files",
    "discover_pgn_files",
    "format_pgn_display_path",
    "format_progress_label",
    "format_relative",
    "make_terminal_safe",
    "progress_write",
    "relative_stem",
    "resolve_executable",
]
