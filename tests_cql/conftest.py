from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
import pytest
from tests_cql.helpers import expected_matches_from_pgn

def pytest_addoption(parser):
    grp = parser.getgroup("cql")
    grp.addoption(
        "--cql-bin",
        action="store",
        default=None,
        help="Path to CQL v6 executable. If unset, use $CQL_BIN or search PATH.",
    )

def _find_repo_root(start: Path) -> Path | None:
    # Walk up until we find a directory containing 'cql-files'
    for p in [start] + list(start.parents):
        if (p / "cql-files").is_dir() and (p / "tests_cql").is_dir():
            return p
        if (p.parent / "cql-files").is_dir() and (p.parent / "tests_cql").is_dir():
            return p.parent
    return None

@pytest.fixture(scope="session")
def repo_root() -> Path:
    here = Path(__file__).resolve()
    root = _find_repo_root(here)
    if root is None:
        raise RuntimeError("Could not locate repo root containing 'cql-files' and 'tests_cql'.")
    return root

@pytest.fixture(scope="session")
def fixtures_dir(repo_root: Path) -> Path:
    d = repo_root / "tests_cql" / "fixtures"
    if not d.is_dir():
        pytest.skip(f"Missing fixtures directory: {d}")
    return d

@pytest.fixture(scope="session")
def cql_bin(request, repo_root: Path) -> str:
    import os, shutil
    from pathlib import Path
    import subprocess
    # Resolution order:
    # 1) --cql-bin flag
    # 2) $CQL_BIN env
    # 3) repo-local bins/cql
    # 4) whatever "cql" on PATH
    candidates = []

    explicit = request.config.getoption("--cql-bin")
    if explicit:
        candidates.append(Path(explicit))

    env = os.environ.get("CQL_BIN")
    if env:
        candidates.append(Path(env))

    candidates.append(repo_root / "bins" / "cql6-1" / "cql")
    on_path = shutil.which("cql")
    if on_path:
        candidates.append(Path(on_path))

    for cand in candidates:
        try:
            p = Path(cand).expanduser().resolve()
        except Exception:
            continue
        if p.exists() and p.is_file() and os.access(p, os.X_OK):
            # sanity check: it runs
            subprocess.run([str(p), "-h"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return str(p)

    pytest.skip(
        "CQL binary not found. Tried: "
        + ", ".join(str(c) for c in candidates)
        + ". Set --cql-bin, $CQL_BIN, put cql on PATH, or place an executable at bins/cql."
    )


@pytest.fixture(scope="session")
def utf8_env() -> dict[str, str]:
    # Prevent Unicode havoc with scripts using symbols (⬓, etc.)
    env = os.environ.copy()
    env.setdefault("LC_ALL", "en_GB.UTF-8")
    env.setdefault("LANG", "en_GB.UTF-8")
    return env

def pytest_configure(config):
    config.addinivalue_line("markers", "cql: tests that require the CQL binary")

def pytest_generate_tests(metafunc):
    # Parametrize tests that accept 'cql_case' with discovered (cql_path, pgn_path, expected)
    if "cql_case" not in metafunc.fixturenames:
        return
    here = Path(__file__).resolve()
    root = _find_repo_root(here)
    if root is None:
        metafunc.parametrize("cql_case", [], ids=[])
        return

    cql_root = root / "cql-files"
    fx_root = root / "tests_cql" / "fixtures"
    cases = []
    ids = []
    for cql in cql_root.rglob("*.cql"):
        rel = cql.relative_to(cql_root)
        pgn = fx_root / rel.with_suffix(".pgn")
        if not pgn.exists():
            # You said 1 PGN per CQL; until it exists, we skip collecting it.
            continue
        expected = expected_matches_from_pgn(pgn)
        cases.append((str(cql), str(pgn), expected))
        ids.append(str(rel).replace("\\", "/"))
    metafunc.parametrize("cql_case", cases, ids=ids)
