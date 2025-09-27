#!/usr/bin/env python3

from __future__ import annotations
from pathlib import Path
from tests_cql.helpers import assert_matches, expected_matches_from_pgn

def test_cql_file(cql_case, tmp_path: Path, cql_bin: str, utf8_env: dict):
    """
    Single parametrized test over all discovered (CQL, PGN) pairs.
    Collection happens in conftest.py::pytest_generate_tests.
    """
    cql_path, pgn_path, expected = cql_case
    assert_matches(cql_bin, cql_path, pgn_path, expected, tmpdir=tmp_path, env=utf8_env)
