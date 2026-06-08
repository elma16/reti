"""Pluggable wrapper around a CQL executable.

The whole point of the abstraction is so swapping ``cql6`` for ``cqli`` (or a
future engine that speaks the same shape of CLI) is a one-line change at the
top of the runner instead of a grep-and-replace.

A backend is a small object with two responsibilities:

1. Know where its binary lives and how to invoke it.
2. Build the argv list for ``-i <pgn> -o <output> [<flags>] <script>``.

Anything else (subprocess management, capturing stdout/stderr, post-run game
counting) belongs in :mod:`reti.cql.runner`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from reti.common.subprocess_helpers import resolve_executable


def resolve_cql_binary(cql_binary: str) -> Path | None:
    """Resolve an explicit path or a name on PATH; print and return None if missing."""
    resolved = resolve_executable(cql_binary)
    if resolved is None:
        print(f"Error: CQL binary not found: '{cql_binary}'")
    return resolved


def infer_backend_name(binary_path: Path) -> str:
    """Infer a backend from the executable name when the user does not choose."""
    name = binary_path.name.lower()
    if "cqli" in name:
        return "cqli"
    return "cql6"


def create_cql_backend(binary_path: Path, backend_name: str = "auto") -> "CqlBackend":
    """Build a backend wrapper for a resolved CQL executable."""
    selected = infer_backend_name(binary_path) if backend_name == "auto" else backend_name
    if selected == "cql6":
        return Cql6Backend(binary_path)
    if selected == "cqli":
        return CqliBackend(binary_path)
    raise ValueError(f"unsupported CQL backend: {backend_name}")


class CqlBackend(ABC):
    """A CQL-like engine that takes a PGN + script and writes matched games."""

    def __init__(self, binary_path: Path) -> None:
        self.binary_path = binary_path

    @abstractmethod
    def build_run_command(
        self,
        pgn_path: Path,
        script_path: Path,
        output_path: Path,
        *,
        threads: str | int = "auto",
    ) -> list[str]:
        """Return argv for a normal cross-product run."""

    @abstractmethod
    def build_smoke_command(
        self,
        pgn_path: Path,
        script_path: Path,
        output_path: Path,
        *,
        lineincrement: int | None = None,
    ) -> list[str]:
        """Return argv for the cheap "does this PGN parse" smoke test."""


class Cql6Backend(CqlBackend):
    """The cql6 binary that ships in ``cql-bin/``.

    Uses ``-i / -o`` for input/output and ``-threads N`` for thread count. The
    smoke-test variant uses the longer ``-input / -output`` spellings (matches
    the historical pgn_cli.py path) and accepts ``-lineincrement``.
    """

    def build_run_command(
        self,
        pgn_path: Path,
        script_path: Path,
        output_path: Path,
        *,
        threads: str | int = "auto",
    ) -> list[str]:
        command = [
            str(self.binary_path),
            "-i",
            str(pgn_path),
            "-o",
            str(output_path),
            "-matchstring",
            script_path.stem,
        ]
        if threads != "auto":
            command.extend(["-threads", str(threads)])
        command.append(str(script_path))
        return command

    def build_smoke_command(
        self,
        pgn_path: Path,
        script_path: Path,
        output_path: Path,
        *,
        lineincrement: int | None = None,
    ) -> list[str]:
        command = [str(self.binary_path)]
        if lineincrement is not None:
            command.extend(["-lineincrement", str(lineincrement)])
        command.extend(
            [
                "-input",
                str(pgn_path),
                "-output",
                str(output_path),
                str(script_path),
            ]
        )
        return command


class CqliBackend(Cql6Backend):
    """CQLi currently accepts the same conservative argv shape as CQL 6.x."""
