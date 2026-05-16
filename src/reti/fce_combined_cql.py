from __future__ import annotations

import argparse
import csv
import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from reti.fce_metadata import FCE_CATALOG


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CQL_TABLE_DIR = REPO_ROOT / "cql-files" / "FCE" / "table"
DEFAULT_OUTPUT_CQL = REPO_ROOT / "cql-files" / "FCE" / "combined" / "fce-table-markers.cql"

_CQL_PREAMBLE_RE = re.compile(r"^\s*cql\s*\(", re.IGNORECASE)
OVERLAP_PARENT_STEMS = {
    "2-1P": ("2-0Pp",),
    "6-2-2RPPr": ("6-2-0Rr",),
    "6-2-2RPPrConnected": ("6-2-2RPPr", "6-2-0Rr"),
    "8-1RNrNoPawns": ("8-1RNr",),
    "8-2RBrNoPawns": ("8-2RBr",),
    "9-3QPq": ("9-2Qq",),
    "10-2QrNoPawns": ("10-2Qr",),
    "10-7-1QbrrNoPawns": ("10-7-1Qbrr",),
}


@dataclass(frozen=True)
class CombinedCqlEntry:
    stem: str
    label: str
    cql_path: Path
    auxiliary: bool = False
    duplicate_of: str | None = None
    parent_stems: tuple[str, ...] = ()

    @property
    def marker_texts(self) -> tuple[str, ...]:
        return (self.stem, *self.parent_stems)


@dataclass(frozen=True)
class CombinedCqlBuildResult:
    output_cql: Path
    entries: tuple[CombinedCqlEntry, ...]
    skipped_duplicates: tuple[CombinedCqlEntry, ...]


def _strip_cql_preamble(text: str, *, path: Path) -> list[str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _CQL_PREAMBLE_RE.match(line):
            body = lines[index + 1 :]
            while body and not body[0].strip():
                body.pop(0)
            while body and not body[-1].strip():
                body.pop()
            if not body:
                raise ValueError(f"{path} has no CQL body after cql()")
            return body
    raise ValueError(f"{path} does not contain a cql(...) preamble")


def _normalized_body_hash(path: Path) -> str:
    body = _strip_cql_preamble(path.read_text(encoding="utf-8"), path=path)
    normalized_lines = []
    for line in body:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        normalized_lines.append(re.sub(r"\s+", "", stripped))
    payload = "\n".join(normalized_lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _auxiliary_label(stem: str) -> str:
    if stem.endswith("NoPawns"):
        base = stem.removesuffix("NoPawns")
        if base in FCE_CATALOG.endings_by_stem:
            return f"{FCE_CATALOG.endings_by_stem[base].label} (without pawns)"
    if stem.endswith("Connected"):
        base = stem.removesuffix("Connected")
        if base in FCE_CATALOG.endings_by_stem:
            return f"{FCE_CATALOG.endings_by_stem[base].label} (connected pawns)"
    if stem in FCE_CATALOG.endings_by_stem:
        return FCE_CATALOG.endings_by_stem[stem].label
    return stem


def canonical_entries(cql_table_dir: Path) -> list[CombinedCqlEntry]:
    entries: list[CombinedCqlEntry] = []
    for ending in FCE_CATALOG.endings:
        cql_path = cql_table_dir / f"{ending.stem}.cql"
        if not cql_path.exists():
            raise FileNotFoundError(f"missing canonical FCE CQL script: {cql_path}")
        entries.append(
            CombinedCqlEntry(
                stem=ending.stem,
                label=ending.label,
                cql_path=cql_path,
                auxiliary=False,
                parent_stems=OVERLAP_PARENT_STEMS.get(ending.stem, ()),
            )
        )
    return entries


def auxiliary_entries(cql_table_dir: Path) -> list[CombinedCqlEntry]:
    manifest_path = cql_table_dir / "auxiliary_manifest.csv"
    if not manifest_path.exists():
        return []

    entries: list[CombinedCqlEntry] = []
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "target" not in (reader.fieldnames or ()):
            raise ValueError(f"{manifest_path} must contain a target column")
        for row in reader:
            stem = (row.get("target") or "").strip()
            if not stem:
                continue
            cql_path = cql_table_dir / f"{stem}.cql"
            if not cql_path.exists():
                raise FileNotFoundError(f"missing auxiliary FCE CQL script: {cql_path}")
            entries.append(
                CombinedCqlEntry(
                    stem=stem,
                    label=_auxiliary_label(stem),
                    cql_path=cql_path,
                    auxiliary=True,
                    parent_stems=OVERLAP_PARENT_STEMS.get(stem, ()),
                )
            )
    return entries


def select_entries(
    cql_table_dir: Path,
    *,
    include_auxiliary: bool = True,
    include_duplicate_aliases: bool = False,
) -> tuple[list[CombinedCqlEntry], list[CombinedCqlEntry]]:
    canonical = canonical_entries(cql_table_dir)
    skipped_duplicates: list[CombinedCqlEntry] = []
    canonical_for_matching = sorted(
        canonical,
        key=lambda entry: FCE_CATALOG.endings_by_stem[entry.stem].specificity_rank,
    )

    if not include_auxiliary:
        return canonical_for_matching, skipped_duplicates

    body_owner_by_hash = {
        _normalized_body_hash(entry.cql_path): entry.stem for entry in canonical
    }
    auxiliary: list[CombinedCqlEntry] = []
    for entry in auxiliary_entries(cql_table_dir):
        body_hash = _normalized_body_hash(entry.cql_path)
        duplicate_of = body_owner_by_hash.get(body_hash)
        if duplicate_of and not include_duplicate_aliases:
            skipped_duplicates.append(
                CombinedCqlEntry(
                    stem=entry.stem,
                    label=entry.label,
                    cql_path=entry.cql_path,
                    auxiliary=True,
                    duplicate_of=duplicate_of,
                    parent_stems=entry.parent_stems,
                )
            )
            continue
        body_owner_by_hash.setdefault(body_hash, entry.stem)
        auxiliary.append(entry)

    auxiliary_by_parent: dict[str, list[CombinedCqlEntry]] = {}
    append_later: list[CombinedCqlEntry] = []
    for entry in auxiliary:
        if not entry.parent_stems:
            append_later.append(entry)
        else:
            auxiliary_by_parent.setdefault(entry.parent_stems[0], []).append(entry)

    entries: list[CombinedCqlEntry] = []
    for entry in canonical_for_matching:
        entries.extend(auxiliary_by_parent.pop(entry.stem, []))
        entries.append(entry)
    for remaining in auxiliary_by_parent.values():
        entries.extend(remaining)
    entries.extend(append_later)
    return entries, skipped_duplicates


def _quote_cql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_combined_cql(entries: list[CombinedCqlEntry]) -> str:
    if not entries:
        raise ValueError("cannot render a combined CQL script with no entries")

    lines = [
        "// Generated by scripts/build_fce_combined_marker_cql.py.",
        "// Run this single script against a PGN directory to get one annotated PGN per input PGN.",
        "// Marker comments are written as {<stem>}.",
        "",
        "cql(quiet)",
        "",
        "{",
    ]

    for index, entry in enumerate(entries):
        if index:
            lines.append("    or")
        row_note = "auxiliary" if entry.auxiliary else "canonical"
        if entry.parent_stems:
            row_note += f"; also marks {', '.join(entry.parent_stems)}"
        lines.append("    {")
        lines.append(f"        // {entry.stem}: {entry.label} ({row_note})")
        body = _strip_cql_preamble(
            entry.cql_path.read_text(encoding="utf-8"),
            path=entry.cql_path,
        )
        for body_line in body:
            lines.append(f"        {body_line}" if body_line else "")
        for marker_text in entry.marker_texts:
            lines.append(f'        comment("{_quote_cql_string(marker_text)}")')
        lines.append("    }")

    lines.extend(["}", ""])
    return "\n".join(lines)


def write_text_atomically(path: Path, text: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists: {path} (pass --force)")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(text)
    temp_path.replace(path)


def build_combined_marker_cql(
    *,
    cql_table_dir: Path = DEFAULT_CQL_TABLE_DIR,
    output_cql: Path = DEFAULT_OUTPUT_CQL,
    include_auxiliary: bool = True,
    include_duplicate_aliases: bool = False,
    force: bool = False,
) -> CombinedCqlBuildResult:
    cql_table_dir = cql_table_dir.expanduser().resolve()
    output_cql = output_cql.expanduser().resolve()
    entries, skipped_duplicates = select_entries(
        cql_table_dir,
        include_auxiliary=include_auxiliary,
        include_duplicate_aliases=include_duplicate_aliases,
    )
    write_text_atomically(output_cql, render_combined_cql(entries), force=force)
    return CombinedCqlBuildResult(
        output_cql=output_cql,
        entries=tuple(entries),
        skipped_duplicates=tuple(skipped_duplicates),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build one combined FCE CQL script whose match comments are "
            "{<stem>} markers."
        )
    )
    parser.add_argument(
        "--cql-table-dir",
        type=Path,
        default=DEFAULT_CQL_TABLE_DIR,
        help="Directory containing the curated FCE table CQL scripts.",
    )
    parser.add_argument(
        "--output-cql",
        type=Path,
        default=DEFAULT_OUTPUT_CQL,
        help="Path for the generated combined CQL script.",
    )
    parser.add_argument(
        "--canonical-only",
        action="store_true",
        help="Include only the 30 canonical FCE table rows.",
    )
    parser.add_argument(
        "--include-duplicate-aliases",
        action="store_true",
        help=(
            "Include auxiliary scripts whose CQL body is identical to a "
            "canonical branch. This is usually not wanted for counting."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_combined_marker_cql(
        cql_table_dir=args.cql_table_dir,
        output_cql=args.output_cql,
        include_auxiliary=not args.canonical_only,
        include_duplicate_aliases=args.include_duplicate_aliases,
        force=args.force,
    )
    print(f"Wrote combined FCE marker CQL: {result.output_cql}")
    print(f"Branches: {len(result.entries)}")
    if result.skipped_duplicates:
        skipped = ", ".join(
            f"{entry.stem}={entry.duplicate_of}"
            for entry in result.skipped_duplicates
        )
        print(f"Skipped canonical-equivalent aliases already covered by parent rows: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
