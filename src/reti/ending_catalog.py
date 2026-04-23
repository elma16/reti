from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ending:
    stem: str
    row_id: str
    label: str
    chapter_key: str
    chapter_label: str
    color: str
    specificity_rank: int

    @property
    def display_label(self) -> str:
        if self.row_id:
            return f"{self.row_id} {self.label}"
        return self.label


@dataclass(frozen=True)
class EndingCatalog:
    name: str
    endings: tuple[Ending, ...]
    endings_by_stem: dict[str, Ending]

    @classmethod
    def build(
        cls,
        *,
        name: str,
        ending_rows: list[tuple[str, str, str, str]],
        chapters: dict[str, tuple[str, str]],
        specificity_order: list[str],
    ) -> EndingCatalog:
        specificity_ranks = {stem: rank for rank, stem in enumerate(specificity_order)}
        endings = tuple(
            Ending(
                stem=stem,
                row_id=row_id,
                label=label,
                chapter_key=chapter_key,
                chapter_label=chapters[chapter_key][0],
                color=chapters[chapter_key][1],
                specificity_rank=specificity_ranks[stem],
            )
            for stem, row_id, label, chapter_key in ending_rows
        )
        endings_by_stem = {ending.stem: ending for ending in endings}
        return cls(name=name, endings=endings, endings_by_stem=endings_by_stem)
