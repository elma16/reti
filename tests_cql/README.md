Testing CQL scripts
===================

The default test collection walks `cql-files/**/*.cql` and looks for a
`tests_cql/fixtures/<same-path>.pgn`. That quickly explodes into a mountain of
tiny PGN fixtures. To keep things manageable you can drive collection with a
single manifest instead.

Manifest mode
-------------

Create `tests_cql/fixtures/cases.json` (copy `cases.example.json` as a start).
Define a couple of reusable datasets and then point any number of CQL files at
them:

```json
{
  "datasets": {
    "fce-sample": { "pgn": "FCE/1-4BN.pgn" },
    "mate-nets": { "fen": "100YMK/6.txt" }
  },
  "cases": [
    {
      "cql": "cql-files/FCE/table/3-2NN.cql",
      "dataset": "fce-sample",
      "expected": 0
    },
    {
      "cql_glob": "cql-files/FCE/table/*.cql",
      "dataset": "mate-nets",
      "expected": 1
    }
  ]
}
```

Notes:
- Paths inside `datasets` are relative to `tests_cql/fixtures`.
- A dataset can be a `pgn` you already have, or a `fen` file with one position
  per line. FEN datasets are converted to temporary PGNs under
  `tests_cql/.generated` automatically.
- `expected` defaults to `expected_matches_from_pgn()` when omitted, so set it
  explicitly for FEN datasets.

Existing behaviour
------------------

If `cases.json` is absent, collection falls back to the original convention of
looking for a sibling `.pgn` for every `.cql`. That means you can opt into the
manifest gradually without breaking current tests.

Coverage requirement
--------------------
Test collection now fails if any `.cql` under `cql-files/` has no corresponding
test case. Add entries to `tests_cql/fixtures/cases.json` (preferred), or supply
a fixture PGN alongside the `.cql`, until the missing list is empty.

Common test dataset
-------------------

We include a small shared PGN fixture `tests_cql/fixtures/db.pgn` and a manifest
`tests_cql/fixtures/cases.json` to drive a couple of smoke tests:

- `common-db` dataset points to `db.pgn`.
- `most_visited_square.cql` is expected to match both games (expected 2).
- `rook_homerun.cql` is expected to find none (expected 0).

Use this as a pattern for adding more CQL scripts: drop minimal positions into
`db.pgn` or another dataset, add a case entry with an explicit expected count,
and run `pytest tests_cql --cql-bin /path/to/cql`.
