# reti-web

A Flask web interface for uploading a PGN file and running 100 classical endgame CQL patterns.

## Run locally

```bash
cd reti-web
python -m venv .venv
source .venv/bin/activate  # use .venv\\Scripts\\Activate.ps1 on Windows
pip install -r requirements.txt
python cql_analyzer_app.py
```

Open `http://127.0.0.1:5000`.

## Notes

- `cql_analyzer_app.py` defaults to CQL paths relative to the repo root.
- Environment overrides:
  - `CQL_BINARY` (default: `../bins/cql6-2/cql`)
  - `CQL_SCRIPTS_DIR` (default: `../cql-files/mates`)
  - `MAX_WORKERS` (default: `min(8, CPU cores)`)

### Files

- `cql_analyzer_app.py`: Flask app entrypoint
- `templates/index.html`: browser UI
- `requirements.txt`: runtime dependencies
