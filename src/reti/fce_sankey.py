from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

from reti.annotated_pgn import (
    ParsedAnnotatedGame,
    discover_pgn_files,
    fast_iter_annotated_pgn,
    format_pgn_display_path,
    iter_annotated_pgn,
    parse_annotated_pgn,
)
from reti.ending_catalog import Ending, EndingCatalog

START_NODE = "__start__"
END_NODE = "__end__"
START_LABEL = "Start"
END_LABEL = "End"
START_END_COLOR = "#9AA1A9"

CATALOGS: dict[str, str] = {
    "fce": "reti.fce_metadata:FCE_CATALOG",
    "100endings": "reti.endings100_metadata:ENDINGS_100_CATALOG",
}


def load_catalog(name: str) -> EndingCatalog:
    spec = CATALOGS[name]
    module_path, attr = spec.rsplit(":", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, attr)


@dataclass(frozen=True)
class EndingHit:
    ending_stem: str
    ply_index: int


@dataclass(frozen=True)
class SankeyData:
    node_ids: list[str]
    node_labels: list[str]
    node_colors: list[str]
    node_hover: list[str]
    link_sources: list[int]
    link_targets: list[int]
    link_values: list[int]
    link_colors: list[str]
    link_hover: list[str]
    total_games: int
    total_transitions: int
    unique_endings: int
    top_transitions: list[tuple[str, str, int]]


@dataclass(frozen=True)
class SankeyBuildResult:
    data: SankeyData
    warnings: tuple[str, ...]
    skipped_files: int
    parsed_files: int


def normalize_header_value(value: str) -> str:
    return " ".join(value.split())


def build_game_key(parsed_game: ParsedAnnotatedGame) -> str:
    normalized_headers = {
        key: normalize_header_value(value)
        for key, value in sorted(parsed_game.headers.items())
    }
    payload = json.dumps(
        {
            "headers": normalized_headers,
            "moves": list(parsed_game.move_uci_sequence),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def resolve_same_ply_overlap(endings: set[str], catalog: EndingCatalog) -> str:
    return min(
        endings,
        key=lambda stem: (
            catalog.endings_by_stem[stem].specificity_rank,
            catalog.endings_by_stem[stem].display_label,
        ),
    )


def build_game_sequences(
    hits_by_game: dict[str, list[EndingHit]],
    catalog: EndingCatalog,
) -> dict[str, list[str]]:
    sequences: dict[str, list[str]] = {}
    for game_key, hits in hits_by_game.items():
        by_ply: dict[int, set[str]] = defaultdict(set)
        for hit in hits:
            by_ply[hit.ply_index].add(hit.ending_stem)

        ordered_stems: list[str] = []
        for ply_index in sorted(by_ply):
            ordered_stems.append(resolve_same_ply_overlap(by_ply[ply_index], catalog))

        collapsed: list[str] = []
        for stem in ordered_stems:
            if not collapsed or collapsed[-1] != stem:
                collapsed.append(stem)

        if collapsed:
            sequences[game_key] = collapsed

    return sequences


def count_transitions(game_sequences: dict[str, list[str]]) -> Counter[tuple[str, str]]:
    transitions: Counter[tuple[str, str]] = Counter()
    for sequence in game_sequences.values():
        path = [START_NODE, *sequence, END_NODE]
        for source, target in zip(path, path[1:]):
            transitions[(source, target)] += 1
    return transitions


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    stripped = hex_color.lstrip("#")
    if len(stripped) != 6:
        raise ValueError(f"Expected a 6-digit hex color, got: {hex_color}")
    red = int(stripped[0:2], 16)
    green = int(stripped[2:4], 16)
    blue = int(stripped[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _node_label(
    stem: str,
    catalog: EndingCatalog,
    *,
    show_numbers: bool,
) -> str:
    if stem == START_NODE:
        return START_LABEL
    if stem == END_NODE:
        return END_LABEL
    ending = catalog.endings_by_stem[stem]
    return ending.display_label if show_numbers else ending.label


def _node_color(stem: str, catalog: EndingCatalog) -> str:
    if stem in (START_NODE, END_NODE):
        return START_END_COLOR
    return catalog.endings_by_stem[stem].color


def _node_hover(
    stem: str,
    catalog: EndingCatalog,
    *,
    show_numbers: bool,
    outgoing: dict[str, int],
    incoming: dict[str, int],
) -> str:
    if stem == START_NODE:
        return f"{START_LABEL}<br>Games entering Sankey: {outgoing.get(stem, 0)}"
    if stem == END_NODE:
        return f"{END_LABEL}<br>Games leaving Sankey: {incoming.get(stem, 0)}"

    ending = catalog.endings_by_stem[stem]
    label = ending.display_label if show_numbers else ending.label
    return (
        f"{label}<br>"
        f"Chapter: {ending.chapter_label}<br>"
        f"Incoming transitions: {incoming.get(stem, 0)}<br>"
        f"Outgoing transitions: {outgoing.get(stem, 0)}"
    )


def build_sankey_data(
    game_sequences: dict[str, list[str]],
    catalog: EndingCatalog,
    *,
    show_numbers: bool = True,
) -> SankeyData:
    transitions = count_transitions(game_sequences)
    total_transitions = sum(transitions.values())

    encountered_stems = {
        stem for sequence in game_sequences.values() for stem in sequence
    }
    node_ids = [
        START_NODE,
        *[ending.stem for ending in catalog.endings if ending.stem in encountered_stems],
        END_NODE,
    ]
    node_labels = [
        _node_label(stem, catalog, show_numbers=show_numbers) for stem in node_ids
    ]
    node_colors = [_node_color(stem, catalog) for stem in node_ids]
    node_index = {stem: index for index, stem in enumerate(node_ids)}

    outgoing: dict[str, int] = defaultdict(int)
    incoming: dict[str, int] = defaultdict(int)
    for (source, target), value in transitions.items():
        outgoing[source] += value
        incoming[target] += value

    link_sources: list[int] = []
    link_targets: list[int] = []
    link_values: list[int] = []
    link_colors: list[str] = []
    link_hover: list[str] = []

    ordered_links = sorted(
        transitions.items(),
        key=lambda item: (
            -item[1],
            _node_label(item[0][0], catalog, show_numbers=show_numbers),
            _node_label(item[0][1], catalog, show_numbers=show_numbers),
        ),
    )
    for (source, target), value in ordered_links:
        source_label = _node_label(source, catalog, show_numbers=show_numbers)
        target_label = _node_label(target, catalog, show_numbers=show_numbers)
        share = (value / total_transitions * 100.0) if total_transitions else 0.0

        link_sources.append(node_index[source])
        link_targets.append(node_index[target])
        link_values.append(value)
        link_colors.append(hex_to_rgba(_node_color(source, catalog), 0.42))
        link_hover.append(
            f"{source_label} -> {target_label}<br>"
            f"Count: {value}<br>"
            f"Share of all counted transitions: {share:.2f}%"
        )

    node_hover = [
        _node_hover(
            stem,
            catalog,
            show_numbers=show_numbers,
            outgoing=outgoing,
            incoming=incoming,
        )
        for stem in node_ids
    ]

    top_transitions = [
        (
            _node_label(source, catalog, show_numbers=show_numbers),
            _node_label(target, catalog, show_numbers=show_numbers),
            value,
        )
        for (source, target), value in ordered_links[:10]
    ]

    return SankeyData(
        node_ids=node_ids,
        node_labels=node_labels,
        node_colors=node_colors,
        node_hover=node_hover,
        link_sources=link_sources,
        link_targets=link_targets,
        link_values=link_values,
        link_colors=link_colors,
        link_hover=link_hover,
        total_games=len(game_sequences),
        total_transitions=total_transitions,
        unique_endings=len(encountered_stems),
        top_transitions=top_transitions,
    )


def collect_hits_from_pgn_dir(
    pgn_dir: str,
    *,
    marker_text: str,
    catalog: EndingCatalog,
) -> tuple[dict[str, list[EndingHit]] | None, tuple[str, ...], int, int]:
    discovery = discover_pgn_files(pgn_dir)
    if discovery is None:
        return None, (), 0, 0

    pgn_files, pgn_root = discovery
    hits_by_game: dict[str, list[EndingHit]] = defaultdict(list)
    warnings: list[str] = []
    skipped_files = 0
    parsed_files = 0

    # Build list of (path, ending, size) so we can weight the progress bar by bytes.
    work_items: list[tuple[Path, Ending, int]] = []
    for pgn_path in pgn_files:
        stem = pgn_path.stem
        display_path = format_pgn_display_path(pgn_path, pgn_root)
        ending_entry: Ending | None = catalog.endings_by_stem.get(stem)
        if ending_entry is None:
            warnings.append(
                f"Skipping {display_path}: file stem '{stem}' is not a curated {catalog.name} ending."
            )
            skipped_files += 1
            continue
        work_items.append((pgn_path, ending_entry, pgn_path.stat().st_size))

    total_bytes = sum(size for _, _, size in work_items)
    pbar = tqdm(
        total=total_bytes,
        unit="B",
        unit_scale=True,
        desc=f"Parsing {catalog.name} PGNs",
    )

    for pgn_path, ending, file_size in work_items:
        display_path = format_pgn_display_path(pgn_path, pgn_root)
        pbar.set_postfix_str(pgn_path.stem, refresh=False)

        try:
            game_stream = fast_iter_annotated_pgn(pgn_path, marker_text=marker_text)
            bytes_accounted = 0
            for parsed_game, bytes_consumed in game_stream:
                bytes_accounted += bytes_consumed
                pbar.update(bytes_consumed)

                if parsed_game.parse_errors:
                    warnings.append(
                        f"{display_path} game {parsed_game.game_index}: "
                        + " | ".join(parsed_game.parse_errors)
                    )

                if not parsed_game.positions:
                    continue

                game_key = build_game_key(parsed_game)
                for position in parsed_game.positions:
                    hits_by_game[game_key].append(
                        EndingHit(ending_stem=ending.stem, ply_index=position.ply_index)
                    )

            # Account for any trailing bytes after the last game.
            if bytes_accounted < file_size:
                pbar.update(file_size - bytes_accounted)

        except Exception as exc:
            warnings.append(f"Skipping {display_path}: failed to parse PGN ({exc}).")
            skipped_files += 1
            pbar.update(file_size)
            continue

        parsed_files += 1

    pbar.close()
    return hits_by_game, tuple(warnings), skipped_files, parsed_files


def render_sankey_html(
    sankey_data: SankeyData,
    *,
    title: str,
    description: str = (
        "This Sankey tracks how games move between curated ending categories. "
        "Each edge counts a consecutive change in the ending label, after "
        "collapsing immediate repeats and resolving same-ply overlaps to the "
        "most specific ending."
    ),
    warnings: tuple[str, ...] = (),
) -> str:
    plot_payload = {
        "node": {
            "label": sankey_data.node_labels,
            "color": sankey_data.node_colors,
            "customdata": sankey_data.node_hover,
            "hovertemplate": "%{customdata}<extra></extra>",
            "pad": 18,
            "thickness": 18,
            "line": {"color": "rgba(255,255,255,0.35)", "width": 0.6},
        },
        "link": {
            "source": sankey_data.link_sources,
            "target": sankey_data.link_targets,
            "value": sankey_data.link_values,
            "color": sankey_data.link_colors,
            "customdata": sankey_data.link_hover,
            "hovertemplate": "%{customdata}<extra></extra>",
        },
    }
    top_transitions = [
        {
            "source": source,
            "target": target,
            "count": count,
        }
        for source, target, count in sankey_data.top_transitions
    ]
    warning_items = "\n".join(f"<li>{warning}</li>" for warning in warnings[:20])
    marker_example = "{CQL}"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --bg: #f5efe4;
      --panel: rgba(255, 252, 246, 0.9);
      --ink: #211f1b;
      --muted: #6d665a;
      --accent: #8f4f2d;
      --border: rgba(33, 31, 27, 0.12);
      --shadow: 0 18px 60px rgba(47, 34, 19, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(143, 79, 45, 0.18), transparent 34%),
        radial-gradient(circle at top right, rgba(78, 121, 167, 0.16), transparent 26%),
        linear-gradient(180deg, #f8f4eb 0%, var(--bg) 100%);
    }}
    main {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .hero {{
      display: grid;
      gap: 12px;
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 3vw, 3.2rem);
      line-height: 1.02;
      letter-spacing: -0.03em;
    }}
    .lede {{
      max-width: 72ch;
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.6;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin: 22px 0 28px;
    }}
    .stat {{
      padding: 16px 18px;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .stat-label {{
      display: block;
      font-size: 0.82rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .stat-value {{
      font-size: 1.9rem;
      line-height: 1;
    }}
    .layout {{
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
      align-items: start;
    }}
    .panel {{
      border: 1px solid var(--border);
      border-radius: 20px;
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    #chart {{
      min-height: 760px;
    }}
    .sidebar {{
      padding: 20px;
      display: grid;
      gap: 18px;
    }}
    .sidebar h2 {{
      margin: 0 0 10px;
      font-size: 1.05rem;
    }}
    .sidebar p, .sidebar li {{
      color: var(--muted);
      line-height: 1.55;
      margin: 0;
    }}
    .sidebar ul {{
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
    }}
    .empty {{
      padding: 20px;
      border-radius: 16px;
      background: rgba(255,255,255,0.6);
      border: 1px dashed var(--border);
    }}
    @media (max-width: 980px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      #chart {{
        min-height: 560px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>{title}</h1>
      <p class="lede">{description}</p>
    </section>

    <section class="stats">
      <article class="stat">
        <span class="stat-label">Games With Transitions</span>
        <span class="stat-value">{sankey_data.total_games:,}</span>
      </article>
      <article class="stat">
        <span class="stat-label">Counted Transitions</span>
        <span class="stat-value">{sankey_data.total_transitions:,}</span>
      </article>
      <article class="stat">
        <span class="stat-label">Unique Ending Nodes</span>
        <span class="stat-value">{sankey_data.unique_endings:,}</span>
      </article>
    </section>

    <section class="layout">
      <div class="panel">
        <div id="chart"></div>
      </div>
      <aside class="panel sidebar">
        <section>
          <h2>Reading the Diagram</h2>
          <p>Start and End are synthetic nodes. Hover over links to inspect counts and shares of all counted transitions. Hover over nodes to inspect incoming and outgoing transition totals.</p>
        </section>
        <section>
          <h2>Top Transitions</h2>
          <ul id="top-transitions"></ul>
        </section>
        <section>
          <h2>Warnings</h2>
          <div class="empty" id="warnings-panel">{'<ul>' + warning_items + '</ul>' if warning_items else 'No warnings.'}</div>
        </section>
      </aside>
    </section>
  </main>

  <script>
    const sankeyPayload = {json.dumps(plot_payload, ensure_ascii=True)};
    const topTransitions = {json.dumps(top_transitions, ensure_ascii=True)};
    const hasLinks = sankeyPayload.link.value.length > 0;
    const chart = document.getElementById("chart");

    const layout = {{
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      margin: {{l: 24, r: 24, t: 24, b: 24}},
      font: {{
        family: 'Georgia, "Iowan Old Style", "Palatino Linotype", serif',
        color: "#211f1b",
        size: 13,
      }},
    }};

    if (hasLinks) {{
      Plotly.newPlot(chart, [{{
        type: "sankey",
        arrangement: "snap",
        node: sankeyPayload.node,
        link: sankeyPayload.link,
      }}], layout, {{
        responsive: true,
        displaylogo: false,
      }});
    }} else {{
      chart.innerHTML = '<div class="empty">No transitions were found in the annotated PGNs. Check that the input directory contains ending-named PGNs with {marker_example} comments.</div>';
    }}

    const list = document.getElementById("top-transitions");
    if (topTransitions.length === 0) {{
      list.innerHTML = '<li>No transitions found.</li>';
    }} else {{
      list.innerHTML = topTransitions.map((item) =>
        `<li><strong>${{item.source}}</strong> → <strong>${{item.target}}</strong> (${{item.count.toLocaleString()}})</li>`
      ).join("");
    }}
  </script>
</body>
</html>
"""


def build_sankey_from_pgn_dir(
    pgn_dir: str,
    *,
    marker_text: str,
    catalog: EndingCatalog,
    show_numbers: bool = True,
) -> SankeyBuildResult | None:
    collection = collect_hits_from_pgn_dir(
        pgn_dir, marker_text=marker_text, catalog=catalog
    )
    hits_by_game, warnings, skipped_files, parsed_files = collection
    if hits_by_game is None:
        return None

    game_sequences = build_game_sequences(hits_by_game, catalog)
    return SankeyBuildResult(
        data=build_sankey_data(game_sequences, catalog, show_numbers=show_numbers),
        warnings=warnings,
        skipped_files=skipped_files,
        parsed_files=parsed_files,
    )


def render_fce_sankey(
    *,
    pgn_dir: str,
    output_html: str,
    marker_text: str,
    title: str,
    catalog: EndingCatalog,
    show_numbers: bool = True,
) -> int:
    result = build_sankey_from_pgn_dir(
        pgn_dir,
        marker_text=marker_text,
        catalog=catalog,
        show_numbers=show_numbers,
    )
    if result is None:
        return 1

    output_path = Path(output_html).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_sankey_html(result.data, title=title, warnings=result.warnings),
        encoding="utf-8",
    )

    print(f"\n--- {catalog.name} Sankey Summary ---")
    print(f"Parsed PGN files: {result.parsed_files}")
    print(f"Skipped files: {result.skipped_files}")
    print(f"Games with transitions: {result.data.total_games}")
    print(f"Counted transitions: {result.data.total_transitions}")
    print(f"Unique ending nodes: {result.data.unique_endings}")
    print(f"HTML: {output_path}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings[:10]:
            print(f"- {warning}")
        if len(result.warnings) > 10:
            print(f"- ... and {len(result.warnings) - 10} more")
    print("--------------------------")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render an interactive static Sankey diagram from annotated ending PGN output."
        )
    )
    parser.add_argument(
        "--pgn-dir",
        dest="pgn_dir",
        required=True,
        help="Directory containing annotated PGN output, scanned recursively.",
    )
    parser.add_argument(
        "--output-html",
        dest="output_html",
        required=True,
        help="Path to the standalone HTML file to generate.",
    )
    parser.add_argument(
        "--marker-text",
        dest="marker_text",
        default="CQL",
        help="Comment text to match exactly after stripping whitespace. Defaults to CQL.",
    )
    parser.add_argument(
        "--title",
        dest="title",
        default=None,
        help="Page and chart title. Defaults to a title derived from the catalog name.",
    )
    parser.add_argument(
        "--catalog",
        dest="catalog",
        choices=sorted(CATALOGS),
        default="fce",
        help="Ending catalog to use. Choices: %(choices)s. Default: fce.",
    )
    parser.add_argument(
        "--show-numbers",
        dest="show_numbers",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include ending numbers in node labels. Default: --show-numbers.",
    )
    return parser.parse_args(argv)


DEFAULT_TITLES: dict[str, str] = {
    "fce": "Fundamental Chess Endings Transition Sankey",
    "100endings": "100 Endgames You Must Know Transition Sankey",
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.marker_text.strip():
        print("Error: --marker-text must contain at least one non-whitespace character.")
        return 1
    catalog = load_catalog(args.catalog)
    title = args.title or DEFAULT_TITLES.get(args.catalog, f"{args.catalog} Transition Sankey")
    return render_fce_sankey(
        pgn_dir=args.pgn_dir,
        output_html=args.output_html,
        marker_text=args.marker_text.strip(),
        title=title,
        catalog=catalog,
        show_numbers=args.show_numbers,
    )


if __name__ == "__main__":
    raise SystemExit(main())
