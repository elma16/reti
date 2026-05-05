"""Tiny helpers for working with subprocesses and external binaries."""

from __future__ import annotations

import shutil
import signal
from pathlib import Path


def describe_returncode(returncode: int) -> str:
    """Negative subprocess return codes mean the process was killed by a signal."""
    if returncode >= 0:
        return f"return code {returncode}"

    signal_number = -returncode
    try:
        signal_name = signal.Signals(signal_number).name
    except ValueError:
        signal_name = f"SIG{signal_number}"
    return f"terminated by signal {signal_number} ({signal_name})"


def resolve_executable(binary: str) -> Path | None:
    """Resolve an explicit path or a name on PATH to a Path. None if not found."""
    candidate = Path(binary).expanduser()
    if candidate.is_file():
        return candidate

    on_path = shutil.which(binary)
    if on_path:
        return Path(on_path)

    return None
