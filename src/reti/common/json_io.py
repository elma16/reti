"""Small JSON file helpers used by snapshot builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reti.common.hashing import canonical_json


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
