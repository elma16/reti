# reti

A collection of Chess Query Language (CQL)-driven analysis tools for chess PGN files.

## Overview

This repo contains:

- CLI scripts for running `.cql` files over PGN databases
- Two Flask web apps for exploring match results visually
- Test fixtures for historical CQL endgame behavior

## Repository layout

- `src/reti/analyse_cql.py`: generic CLI wrapper around any CQL script or directory of scripts
- `src/reti/fce_table_analyzer.py`: table-oriented script parser for Fundamental Chess Endings workflows
- `src/reti/fce_table_app.py`: existing Flask app for FCE-style output
- `src/reti/templates/fce_table.html`: shared UI for the FCE app
- `cql-files/`: included `.cql` script collections
- `tests_cql/`: fixtures and tests
- `reti-web/`: standalone PGN web uploader/analyzer (moved into its own directory)

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # use .venv\Scripts\Activate.ps1 on Windows
pip install -e .
pip install -r reti-web/requirements.txt
```

## CLI usage

```bash
# Run one script or a directory of scripts against a PGN file
python src/reti/analyse_cql.py path/to/games.pgn path/to/cql path/to/script_or_directory
```

For FCE-table workflows, use `src/reti/fce_table_analyzer.py` and `src/reti/fce_table_app.py` directly.

## Web app

The web interface is now in `reti-web/`.

```bash
cd reti-web
python cql_analyzer_app.py
```

Open `http://127.0.0.1:5000` and upload a `.pgn` file.
