"""Tqdm-friendly terminal output helpers."""

from __future__ import annotations

from tqdm import tqdm as tqdm_progress


def make_terminal_safe(text: str) -> str:
    """Escape control characters before sending text to the terminal."""
    safe_parts: list[str] = []
    for char in text:
        codepoint = ord(char)
        if char in "\n\r\t":
            safe_parts.append(char)
        elif codepoint < 32 or codepoint == 127:
            safe_parts.append(f"\\x{codepoint:02x}")
        else:
            safe_parts.append(char)
    return "".join(safe_parts)


def format_progress_label(text: str, *, max_length: int = 80) -> str:
    safe = (
        make_terminal_safe(text)
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
    )
    if len(safe) <= max_length:
        return safe
    head = max(10, max_length // 2 - 2)
    tail = max(10, max_length - head - 3)
    return f"{safe[:head]}...{safe[-tail:]}"


def progress_write(message: str) -> None:
    tqdm_progress.write(make_terminal_safe(message))
