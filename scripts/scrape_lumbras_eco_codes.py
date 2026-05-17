#!/usr/bin/env python3
"""Scrape Lumbra's extended ECO-code table into a local CSV.

The page uses extended Scid-style ECO codes such as A00q, which match the
`ECO` tags found in Lumbra's PGNs more closely than a plain A00-E99 catalog.
This script intentionally writes a generated artifact; keep the CSV out of
source control unless the publication/licensing decision is explicit.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen


DEFAULT_URL = "https://lumbrasgigabase.com/en/eco-codes-en/"
DEFAULT_OUTPUT = Path("data/openings/lumbras_eco_codes.csv")
ECO_RE = re.compile(r"^[A-E][0-9]{2}[a-z]*$")
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class EcoRow:
    row_number: int
    eco: str
    eco_base: str
    eco_group: str
    name: str
    moves: str
    source_url: str


class TableTextParser(HTMLParser):
    """Extract table rows as plain text cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_cell = False
        self._in_row = False
        self._cell_chunks: list[str] = []
        self._row_cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._in_row = True
            self._row_cells = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._cell_chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            text = normalize_text("".join(self._cell_chunks))
            self._row_cells.append(text)
            self._cell_chunks = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row_cells:
                self.rows.append(self._row_cells)
            self._row_cells = []
            self._in_row = False


def normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def normalize_moves(value: str) -> str:
    value = normalize_text(value)
    if value == "*":
        return ""
    if value.endswith(" *"):
        return value[:-2].strip()
    return value


def parse_eco_rows(html: str, source_url: str) -> list[EcoRow]:
    parser = TableTextParser()
    parser.feed(html)

    rows: list[EcoRow] = []
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        eco = cells[0].strip()
        if not ECO_RE.fullmatch(eco):
            continue
        rows.append(
            EcoRow(
                row_number=len(rows) + 1,
                eco=eco,
                eco_base=eco[:3],
                eco_group=eco[0],
                name=normalize_text(cells[1]),
                moves=normalize_moves(cells[2]),
                source_url=source_url,
            )
        )
    return rows


def read_html(args: argparse.Namespace) -> str:
    if args.input_html:
        return Path(args.input_html).read_text(encoding="utf-8")

    request = Request(
        args.url,
        headers={"User-Agent": "reti-fce-opening-scraper/1.0"},
    )
    with urlopen(request, timeout=args.timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def write_csv(rows: Iterable[EcoRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_number",
                "eco",
                "eco_base",
                "eco_group",
                "name",
                "moves",
                "source_url",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "row_number": row.row_number,
                    "eco": row.eco,
                    "eco_base": row.eco_base,
                    "eco_group": row.eco_group,
                    "name": row.name,
                    "moves": row.moves,
                    "source_url": row.source_url,
                }
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Lumbra's extended ECO-code table to CSV."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--input-html",
        help="Parse a previously downloaded HTML file instead of fetching --url.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    html = read_html(args)
    rows = parse_eco_rows(html, args.url)
    if not rows:
        raise SystemExit("No ECO rows found; page structure may have changed.")
    write_csv(rows, args.output)
    print(f"Wrote {len(rows):,} ECO rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
