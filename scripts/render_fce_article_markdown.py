#!/usr/bin/env python3
"""Render editable FCE article prose from Markdown into the static page.

This intentionally handles only the small Markdown subset used by
reti-site/content/index.md.  The interactive table, Sankey controls, scripts,
and styles remain in reti-site/static/index.html.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOURCE = Path("reti-site/content/index.md")
DEFAULT_TARGET = Path("reti-site/static/index.html")


@dataclass
class Article:
    title: str
    date: str
    author: str
    sections: dict[str, list[str]]
    references: list[tuple[str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-md", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target-html", type=Path, default=DEFAULT_TARGET)
    return parser.parse_args()


def parse_article(text: str) -> Article:
    metadata: dict[str, str] = {}
    if text.startswith("---\n"):
        _, meta_text, text = text.split("---\n", 2)
        for line in meta_text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

    references: list[tuple[str, str]] = []
    body_lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\[\^([A-Za-z0-9_-]+)\]:\s*(.+)$", line)
        if match:
            references.append((match.group(1), match.group(2).strip()))
        else:
            body_lines.append(line)

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body_lines:
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1)
            sections[current] = []
            continue
        if current:
            sections[current].append(line)

    return Article(
        title=metadata.get("title", "FCE article"),
        date=metadata.get("date", ""),
        author=metadata.get("author", ""),
        sections=sections,
        references=references,
    )


def render_inline(text: str, ref_numbers: dict[str, int]) -> str:
    text = re.sub(
        r"\[\^([A-Za-z0-9_-]+)\]",
        lambda m: (
            f'<sup><a href="#ref-{m.group(1)}">{ref_numbers[m.group(1)]}</a></sup>'
            if m.group(1) in ref_numbers
            else m.group(0)
        ),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: (
            f'<a href="{m.group(2).replace("&", "&amp;")}" '
            f'target="_blank" rel="noopener noreferrer">{m.group(1)}</a>'
        ),
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<cite>\1</cite>", text)
    return text


def blocks(lines: list[str]) -> list[list[str]]:
    out: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        elif current:
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def render_paragraphs(lines: list[str], ref_numbers: dict[str, int]) -> str:
    rendered: list[str] = []
    for block in blocks(lines):
        if block[0].startswith("- "):
            items = [
                f"<li>{render_inline(line[2:].strip(), ref_numbers)}</li>"
                for line in block
                if line.startswith("- ")
            ]
            rendered.append('<ul class="section-summary">\n      ' + "\n      ".join(items) + "\n    </ul>")
        else:
            paragraph = " ".join(line.strip() for line in block)
            rendered.append(f"    <p>{render_inline(paragraph, ref_numbers)}</p>")
    return "\n".join(rendered)


def section_lines(article: Article, *names: str) -> tuple[str, list[str]]:
    for name in names:
        lines = article.sections.get(name)
        if lines is not None:
            return name, lines
    return names[0], []


def render_section(
    title: str,
    lines: list[str],
    ref_numbers: dict[str, int],
    *,
    section_class: str,
    title_id: str,
) -> str:
    body = render_paragraphs(lines, ref_numbers)
    return f'''  <section class="{section_class}" aria-labelledby="{title_id}">
    <h2 id="{title_id}">{title}</h2>
{body}
  </section>'''


def render_intro(article: Article, ref_numbers: dict[str, int]) -> str:
    intro_title, intro_lines = section_lines(article, "Introduction", "Methodology", "Methodology and Scope")
    motivation_title, motivation_lines = section_lines(article, "Motivation")
    methodology_title, methodology_lines = section_lines(article, "Methodology")
    sections = [
        render_section(
            intro_title,
            intro_lines,
            ref_numbers,
            section_class="article-intro",
            title_id="intro-title",
        )
    ]
    if motivation_lines:
        sections.append(
            render_section(
                motivation_title,
                motivation_lines,
                ref_numbers,
                section_class="article-section prose-section",
                title_id="motivation-title",
            )
        )
    if methodology_lines:
        sections.append(
            render_section(
                methodology_title,
                methodology_lines,
                ref_numbers,
                section_class="article-section prose-section",
                title_id="methodology-title",
            )
        )
    return "\n".join(sections)


def render_table_summary(article: Article, ref_numbers: dict[str, int]) -> str:
    _, lines = section_lines(article, "Table", "Ending Incidence and Outcomes")
    return render_paragraphs(lines, ref_numbers)


def render_article_section(
    article: Article,
    ref_numbers: dict[str, int],
    title_id: str,
    *names: str,
) -> str:
    title, lines = section_lines(article, *names)
    return render_section(
        title,
        lines,
        ref_numbers,
        section_class="article-section prose-section",
        title_id=title_id,
    )


def render_transition_copy(article: Article, ref_numbers: dict[str, int]) -> str:
    _, lines = section_lines(article, "Transitions", "Consecutive Ending Transitions")
    return render_paragraphs(lines, ref_numbers)


def render_references(article: Article, ref_numbers: dict[str, int]) -> str:
    items = "\n".join(
        f'      <li id="ref-{key}">{render_inline(body, ref_numbers)}</li>'
        for key, body in article.references
    )
    return f'''  <section class="references-section" aria-labelledby="references-title">
    <h2 id="references-title">References</h2>
    <ol class="references" aria-label="References">
{items}
    </ol>
  </section>'''


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    before, sep, rest = text.partition(start)
    if not sep:
        raise SystemExit(f"missing marker {start!r}")
    _, sep, after = rest.partition(end)
    if not sep:
        raise SystemExit(f"missing marker {end!r}")
    return f"{before}{start}\n{replacement}\n  {end}{after}"


def render(article: Article, target_text: str) -> str:
    ref_numbers = {key: index for index, (key, _) in enumerate(article.references, start=1)}
    title_html = render_inline(article.title, ref_numbers)
    target_text = re.sub(r"<h1>.*?</h1>", f"<h1>{title_html}</h1>", target_text, count=1)
    table_title, _ = section_lines(article, "Table", "Ending Incidence and Outcomes")
    transition_title, _ = section_lines(article, "Transitions", "Consecutive Ending Transitions")
    target_text = re.sub(
        r'<h2 id="table-title">.*?</h2>',
        f'<h2 id="table-title">{table_title}</h2>',
        target_text,
        count=1,
    )
    target_text = re.sub(
        r'<h2 id="transition-title">.*?</h2>',
        f'<h2 id="transition-title">{transition_title}</h2>',
        target_text,
        count=1,
    )
    target_text = re.sub(
        r'<p class="byline">.*?</p>',
        f'<p class="byline">Date: {article.date} | Author: {article.author}</p>',
        target_text,
        count=1,
    )
    target_text = replace_between(
        target_text,
        "  <!-- FCE_INTRO_START -->",
        "  <!-- FCE_INTRO_END -->",
        render_intro(article, ref_numbers),
    )
    target_text = replace_between(
        target_text,
        "    <!-- FCE_TABLE_SUMMARY_START -->",
        "    <!-- FCE_TABLE_SUMMARY_END -->",
        "    " + render_table_summary(article, ref_numbers).replace("\n", "\n    "),
    )
    target_text = replace_between(
        target_text,
        "  <!-- FCE_RESULTS_START -->",
        "  <!-- FCE_RESULTS_END -->",
        render_article_section(
            article,
            ref_numbers,
            "results-title",
            "Results and Discussion",
            "Results",
            "Discussion",
        ),
    )
    target_text = replace_between(
        target_text,
        "    <!-- FCE_TRANSITION_COPY_START -->",
        "    <!-- FCE_TRANSITION_COPY_END -->",
        "    " + render_transition_copy(article, ref_numbers).replace("\n", "\n    "),
    )
    target_text = replace_between(
        target_text,
        "  <!-- FCE_CONCLUSION_START -->",
        "  <!-- FCE_CONCLUSION_END -->",
        render_article_section(article, ref_numbers, "conclusion-title", "Conclusion"),
    )
    target_text = replace_between(
        target_text,
        "  <!-- FCE_REFERENCES_START -->",
        "  <!-- FCE_REFERENCES_END -->",
        render_references(article, ref_numbers),
    )
    return target_text


def main() -> None:
    args = parse_args()
    article = parse_article(args.source_md.read_text(encoding="utf-8"))
    target_text = args.target_html.read_text(encoding="utf-8")
    args.target_html.write_text(render(article, target_text), encoding="utf-8")
    print(f"Rendered {args.source_md} -> {args.target_html}")


if __name__ == "__main__":
    main()
