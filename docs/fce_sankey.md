# FCE Sankey Workflow

`scripts/render_fce_sankey.py` turns the annotated PGN output from the curated
FCE workflow into a standalone interactive Sankey diagram.

Unlike `scripts/render_fce_table_from_summary.py`, this does **not** read
`summary.csv`. It reads the output PGNs themselves and reconstructs how the same
underlying games move between ending labels over time.

## Inputs

The Sankey builder expects the output directory from:

```bash
python src/reti/analyse_cql.py \
  --pgn path/to/pgn_dir \
  --cql-bin path/to/cql \
  --scripts cql-files/FCE/table \
  -o output/fce-table
```

That directory should contain one annotated PGN per `(input PGN, ending script)`
pair. Each PGN filename stem is treated as the ending label, and `{CQL}`
comments mark the positions used for transition extraction.

## Render the HTML

```bash
python scripts/render_fce_sankey.py \
  --pgn-dir output/fce-table \
  --output-html docs/fce_sankey.html
```

Optional flags:

- `--marker-text TEXT`: comment text to match exactly after stripping
  whitespace; defaults to `CQL`
- `--title TEXT`: page and chart title

## Transition rules

For each underlying game:

1. collect all marked ending hits across the annotated PGN directory
2. sort them by move order
3. if multiple endings hit at the same ply, keep only the most specific FCE
   ending
4. collapse immediate repeats
5. count one transition for each consecutive distinct change

Synthetic `Start` and `End` nodes are added so each game contributes a complete
path through the Sankey.

## Output

The generated HTML file:

- is standalone apart from the Plotly CDN dependency
- is suitable for GitHub Pages or any other static hosting
- includes hover text for counts and transition shares
- colors ending nodes by major FCE chapter

Writing to `docs/fce_sankey.html` is a sensible default if you want the diagram
to be easy to publish alongside the repository documentation.
