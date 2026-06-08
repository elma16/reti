#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import difflib
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = REPO_ROOT / "cql-files" / "FCE"
DEFAULT_OUTPUT_DIR = DEFAULT_SOURCE_DIR / "table"

# Canonical filenames used for the curated FCE table subset.
TABLE_TARGETS = [
    "1-4BN",
    "1-5NNp",
    "2-0Pp",
    "2-1P",
    "3-1Np",
    "3-2NN",
    "4-1Bp",
    "4-2scBB",
    "4-3ocBB",
    "5-0BN",
    "6-1-0RP",
    "6-2-0Rr",
    "6-2-1RPr",
    "6-2-2RPPr",
    "6-3RRrr",
    "7-1RN",
    "7-2RB",
    "8-1RNr",
    "8-2RBr",
    "8-3RAra",
    "9-1Qp",
    "9-2Qq",
    "9-3QPq",
    "10-1Qa",
    "10-2Qr",
    "10-3Qaa",
    "10-4Qra",
    "10-5Qrr",
    "10-6Qaaa",
    "10-7QAq",
    "10-7-1Qbrr",
]

# Auxiliary scripts are useful for FCE parenthetical sub-counts, but they are
# not part of the canonical table rows. Keep them reproducible without
# adding them to manifest.csv, which remains the canonical-row manifest.
TABLE_AUXILIARY_TARGETS = [
    "6-2-2RPPrConnected",
    "8-1RNrNoPawns",
    "8-1RNrPp",
    "8-2RBrNoPawns",
    "8-2RBrPp",
    "10-2QrNoPawns",
    "10-2QrPp",
    "10-7-1QbrrNoPawns",
    "10-7-1QbrrPp",
]

# Explicit source overrides for the curated table rows. Some rows map to
# differently named scripts, and some table rows intentionally use the broader
# inclusive script rather than the pawnless split.
SOURCE_OVERRIDES = {
    "2-1P": "2-AP",
    "5-0BN": "5-0Bn",
    "6-1-0RP": "6-1Rp",
    "6-2-0Rr": "6-2-0RPrp",
    "7-1RN": "7-1Rn",
    "7-2RB": "7-2Rb",
    "8-1RNr": "8-1RNrPp",
    "8-2RBr": "8-2RBrPp",
    "9-3QPq": "9-21QPq",
    "10-2Qr": "10-2QrPp",
    "10-7-1Qbrr": "10-7-1QbrrPp",
}

AUXILIARY_SOURCE_OVERRIDES = {
    "8-1RNrNoPawns": "8-1RNr",
    "8-2RBrNoPawns": "8-2RBr",
    "10-2QrNoPawns": "10-2Qr",
}


@dataclass(frozen=True)
class Resolution:
    target: str
    source: str
    mode: str
    score: float


def normalize_name(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def resolve_source(
    target: str,
    available: dict[str, Path],
    *,
    overrides: dict[str, str] | None = None,
) -> Resolution:
    override = (overrides or {}).get(target)
    if override and override in available:
        return Resolution(target=target, source=override, mode="override", score=1.0)

    if target in available:
        return Resolution(target=target, source=target, mode="exact", score=1.0)

    lower_map: dict[str, list[str]] = {}
    for stem in available:
        lower_map.setdefault(stem.lower(), []).append(stem)

    casefold_hits = lower_map.get(target.lower(), [])
    if len(casefold_hits) == 1:
        return Resolution(
            target=target,
            source=casefold_hits[0],
            mode="case-insensitive",
            score=1.0,
        )

    target_norm = normalize_name(target)
    scored = sorted(
        (
            (
                difflib.SequenceMatcher(
                    a=target_norm, b=normalize_name(candidate)
                ).ratio(),
                candidate,
            )
            for candidate in available
        ),
        reverse=True,
    )

    best_score, best_candidate = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < 0.72 or (best_score - second_score) < 0.08:
        raise ValueError(
            f"Could not resolve '{target}' confidently. Best candidates: {scored[:3]}"
        )

    return Resolution(
        target=target,
        source=best_candidate,
        mode="fuzzy",
        score=best_score,
    )


def build_subset(source_dir: Path, output_dir: Path, dry_run: bool) -> list[Resolution]:
    available = {path.stem: path for path in sorted(source_dir.glob("*.cql"))}
    if not available:
        raise SystemExit(f"No .cql files found in {source_dir}")

    canonical_resolutions = [
        resolve_source(target, available, overrides=SOURCE_OVERRIDES)
        for target in TABLE_TARGETS
    ]
    auxiliary_resolutions = [
        resolve_source(target, available, overrides=AUXILIARY_SOURCE_OVERRIDES)
        for target in TABLE_AUXILIARY_TARGETS
    ]
    resolutions = canonical_resolutions + auxiliary_resolutions

    if dry_run:
        return resolutions

    output_dir.mkdir(parents=True, exist_ok=True)
    target_names = set(TABLE_TARGETS) | set(TABLE_AUXILIARY_TARGETS)
    for stale_file in output_dir.glob("*.cql"):
        if stale_file.stem not in target_names:
            stale_file.unlink()

    for resolution in resolutions:
        src = available[resolution.source]
        dest = output_dir / f"{resolution.target}.cql"
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    manifest_path = output_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["target", "source", "mode", "score"],
        )
        writer.writeheader()
        for resolution in canonical_resolutions:
            writer.writerow(
                {
                    "target": resolution.target,
                    "source": resolution.source,
                    "mode": resolution.mode,
                    "score": f"{resolution.score:.3f}",
                }
            )

    auxiliary_manifest_path = output_dir / "auxiliary_manifest.csv"
    with auxiliary_manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["target", "source", "mode", "score"],
        )
        writer.writeheader()
        for resolution in auxiliary_resolutions:
            writer.writerow(
                {
                    "target": resolution.target,
                    "source": resolution.source,
                    "mode": resolution.mode,
                    "score": f"{resolution.score:.3f}",
                }
            )

    return resolutions


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the curated cql-files/FCE/table subset from the broader "
            "cql-files/FCE collection."
        )
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing the broader FCE corpus.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the curated table subset will be written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print the mapping without writing files.",
    )
    args = parser.parse_args()

    resolutions = build_subset(args.source_dir, args.output_dir, args.dry_run)
    for resolution in resolutions:
        print(
            f"{resolution.target}.cql <- {resolution.source}.cql "
            f"({resolution.mode}, score={resolution.score:.3f})"
        )

    if not args.dry_run:
        print(
            f"\nWrote {len(TABLE_TARGETS)} canonical and "
            f"{len(TABLE_AUXILIARY_TARGETS)} auxiliary table scripts to {args.output_dir}"
        )
        print(f"Canonical manifest: {args.output_dir / 'manifest.csv'}")
        print(f"Auxiliary manifest: {args.output_dir / 'auxiliary_manifest.csv'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
