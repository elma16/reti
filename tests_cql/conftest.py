from __future__ import annotations
import os
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from tests_cql.helpers import expected_matches_from_pgn, fens_to_pgn_text

MANIFEST_FILENAME = "cases.json"
GENERATED_DIR = ".generated"


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
        raise RuntimeError(
            "Could not locate repo root containing 'cql-files' and 'tests_cql'."
        )
    return root


@pytest.fixture(scope="session")
def fixtures_dir(repo_root: Path) -> Path:
    d = repo_root / "tests_cql" / "fixtures"
    if not d.is_dir():
        pytest.skip(f"Missing fixtures directory: {d}")
    return d


@pytest.fixture(scope="session")
def cql_bin(request, repo_root: Path) -> str:
    import os
    from pathlib import Path

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
            subprocess.run(
                [str(p), "-h"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
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


def _manifest_path(repo_root: Path) -> Path:
    return repo_root / "tests_cql" / "fixtures" / MANIFEST_FILENAME


def _load_manifest(repo_root: Path) -> dict | None:
    manifest_path = _manifest_path(repo_root)
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse {manifest_path}: {exc}") from exc


def _generate_pgn_from_fens(fen_file: Path, repo_root: Path) -> Path:
    dest_dir = repo_root / "tests_cql" / GENERATED_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{fen_file.stem}.pgn"
    lines = [
        line.split("#", 1)[0].strip()
        for line in fen_file.read_text(encoding="utf-8").splitlines()
    ]
    fens = [line for line in lines if line]
    if not fens:
        raise RuntimeError(f"No FENs found in {fen_file}")
    dest.write_text(fens_to_pgn_text(fens), encoding="utf-8")
    return dest


def _cases_from_manifest(repo_root: Path):
    manifest = _load_manifest(repo_root)
    if manifest is None:
        return None

    fixtures_root = repo_root / "tests_cql" / "fixtures"
    datasets = {}
    for name, cfg in manifest.get("datasets", {}).items():
        if "pgn" in cfg:
            pgn_path = fixtures_root / cfg["pgn"]
            if not pgn_path.exists():
                raise RuntimeError(
                    f"Dataset '{name}' points to missing PGN: {pgn_path}"
                )
            datasets[name] = pgn_path
        elif "fen" in cfg:
            fen_path = fixtures_root / cfg["fen"]
            if not fen_path.exists():
                raise RuntimeError(
                    f"Dataset '{name}' points to missing FEN file: {fen_path}"
                )
            datasets[name] = _generate_pgn_from_fens(fen_path, repo_root)
        else:
            raise RuntimeError(
                f"Dataset '{name}' must declare 'pgn' or 'fen'. Got: {cfg}"
            )

    cases = []
    ids = []
    for entry in manifest.get("cases", []):
        dataset_name = entry.get("dataset")
        if not dataset_name or dataset_name not in datasets:
            raise RuntimeError(f"Case is missing a valid dataset: {entry}")

        expected = entry.get("expected")
        use_glob = entry.get("cql_glob")
        cql_path = entry.get("cql")
        if not use_glob and not cql_path:
            raise RuntimeError(f"Case must provide 'cql' or 'cql_glob': {entry}")

        if use_glob:
            cql_paths = sorted(repo_root.glob(use_glob))
        else:
            cql_paths = [repo_root / cql_path]

        for cql_file in cql_paths:
            if not cql_file.exists():
                raise RuntimeError(f"Case CQL path not found: {cql_file}")
            expected_val = expected
            if expected_val is None:
                expected_val = expected_matches_from_pgn(datasets[dataset_name])
            cases.append((str(cql_file), str(datasets[dataset_name]), expected_val))
            case_id = entry.get("id") or str(cql_file.relative_to(repo_root)).replace(
                "\\", "/"
            )
            ids.append(case_id)

    return cases, ids


def _cases_from_fixture_pairs(cql_root: Path, fx_root: Path):
    cases = []
    ids = []
    for cql in cql_root.rglob("*.cql"):
        rel = cql.relative_to(cql_root)
        pgn = fx_root / rel.with_suffix(".pgn")
        if not pgn.exists():
            continue
        expected = expected_matches_from_pgn(pgn)
        cases.append((str(cql), str(pgn), expected))
        ids.append(str(rel).replace("\\", "/"))
    return cases, ids


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
    collected = _cases_from_manifest(root)
    if collected is None:
        cases, ids = _cases_from_fixture_pairs(cql_root, fx_root)
    else:
        cases, ids = collected

    # Enforce that every .cql under cql-files has a test case. Fail fast if any are missing.
    all_cql = {p.resolve() for p in cql_root.rglob("*.cql")}
    tested_cql = {Path(c[0]).resolve() for c in cases}
    missing = sorted(all_cql - tested_cql)
    if missing:
        missing_rel = [str(m.relative_to(root)) for m in missing]
        raise RuntimeError(
            "Missing CQL tests for the following files:\n  - "
            + "\n  - ".join(missing_rel)
            + "\nAdd entries to tests_cql/fixtures/cases.json (preferred) or provide fixture PGNs."
        )

    metafunc.parametrize("cql_case", cases, ids=ids)
