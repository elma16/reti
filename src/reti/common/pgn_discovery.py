"""File discovery helpers for PGN/CQL inputs.

Three previous flavours of "find the .pgn files under this path" are now one
function. ``discover_input_files`` is the general form (any suffix, returns an
``InputCollection`` with a stable root); ``discover_pgn_files`` is the
narrower variant that several scripts already export by that name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InputCollection:
    """A set of input files with the directory we should treat as their root.

    ``root`` is the directory the user pointed us at (or the file's parent if
    they pointed at one file). Using it as the relative-path origin keeps
    output layouts deterministic across single-file and directory runs.
    """

    root: Path
    files: list[Path]


def discover_input_files(location: str, suffix: str) -> InputCollection | None:
    """Resolve a single file or recursively discover matching files in a directory.

    ``suffix`` should include the leading dot (``".pgn"``).
    """
    path = Path(location).expanduser()
    expected_suffix = suffix.lower()

    if path.is_file():
        if path.suffix.lower() != expected_suffix:
            print(f"Error: '{location}' is not a {suffix} file.")
            return None
        return InputCollection(root=path.parent, files=[path])

    if path.is_dir():
        files = sorted(
            (
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() == expected_suffix
            ),
            key=lambda item: str(item.relative_to(path)),
        )
        if not files:
            print(f"Error: No {suffix} files found under '{location}'.")
            return None
        return InputCollection(root=path, files=files)

    print(f"Error: '{location}' is not a valid file or directory.")
    return None


def discover_pgn_files(location: str) -> tuple[list[Path], Path | None] | None:
    """Discover .pgn files; legacy signature returning ``(files, root_or_none)``.

    Kept for callers that don't need an InputCollection. Returns ``None`` for
    invalid input. ``root`` is ``None`` when the user pointed at a single
    file (matching the old ``annotated_pgn`` behaviour).
    """
    collection = discover_input_files(location, ".pgn")
    if collection is None:
        return None
    if len(collection.files) == 1 and collection.files[0].parent == collection.root:
        # Distinguish "single file" from "directory with one file" by checking
        # whether the user pointed at a file vs. a directory.
        if Path(location).expanduser().is_file():
            return collection.files, None
    return collection.files, collection.root


def relative_stem(path: Path, root: Path) -> Path:
    """Path relative to ``root`` with the final suffix removed."""
    return path.relative_to(root).with_suffix("")


def format_relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def format_pgn_display_path(pgn_path: Path, root: Path | None) -> str:
    if root is None:
        return pgn_path.name

    try:
        return str(pgn_path.relative_to(root))
    except ValueError:
        return pgn_path.name
