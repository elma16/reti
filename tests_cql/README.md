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
- Test resolution prefers `bins/cql6-2/cql` before `bins/cql6-1/cql` so
  Unicode-form CQL files (for example in `cql-files/mates/`) parse reliably.

Existing behaviour
------------------

If `cases.json` is absent, collection falls back to the original convention of
looking for a sibling `.pgn` for every `.cql`. That means you can opt into the
manifest gradually without breaking current tests.

Coverage requirement
--------------------
Manifest mode supports an opt-in strict check:

- Set `"enforce_full_cql_coverage": true` in `cases.json` to fail collection if
  any `.cql` under `cql-files/` has no test case.
- Leave it unset/false for focused suites (for example, testing only one
  directory like FCE table scripts).

FCE suite
---------

The current manifest includes a focused FCE suite for `cql-files/FCE/**/*.cql`:

- Each CQL file has a dedicated FEN fixture in `tests_cql/fixtures/FCE/`.
- Each fixture contains two positions:
  - One positive FEN expected to match.
  - One near-miss negative FEN expected not to match.
- Every FCE case is configured with `expected: 1`.

Use this pattern for other directories: add per-script FEN pairs, point datasets
at those files, and set explicit expected counts.

Mates suite
-----------

The manifest also includes `cql-files/mates/*.cql`:

- Most mate scripts use paired FEN fixtures in `tests_cql/fixtures/mates/*.txt`.
- `castlingmate.cql` is move-dependent, so it uses
  `tests_cql/fixtures/mates/castlingmate.pgn` with two one-move games from FEN
  start positions (positive and near-miss negative).
