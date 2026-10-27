from __future__ import annotations

import os
from pathlib import Path

import pytest

from kg.common import BUILD_DIR

ROOT = Path(__file__).resolve().parents[1]
ITSG_FILE = ROOT / "fixtures/itsg/TEEL0-Test1-DBVO"


@pytest.fixture(scope="session")
def passages_built():
    """The YAML backend and the build read kg/build/passages.yaml; extract it once if missing."""
    if not (BUILD_DIR / "passages.yaml").exists():
        from kg import extract

        extract.run()
    return BUILD_DIR / "passages.yaml"


@pytest.fixture(scope="session")
def neo4j_driver():
    """A driver to the Neo4j of .env with the full graph loaded, or skip. The tests load the full seed into
    that database, so they run only with NEO4J_TESTS=1 (never against the demo graph of DEMO_START=1)."""
    if os.environ.get("NEO4J_TESTS") != "1":
        pytest.skip("graph tests need NEO4J_TESTS=1 and a Neo4j with the full graph (they write to it)")
    try:
        from kg import load

        driver = load.connect()
    except Exception as exc:  # noqa: BLE001 - any connection problem means: no graph tests
        pytest.skip(f"Neo4j not reachable ({exc.__class__.__name__}: {exc})")
    with driver.session() as s:
        rules = s.run("MATCH (r:Rule) RETURN count(r) AS n").single()["n"]
    if not rules:
        driver.close()
        pytest.skip("Neo4j is empty: run `python -m kg.build` first")
    yield driver
    driver.close()


# ---------------------------------------------------------------- backend (engine, API, LLM) tests


def make_kb(precedents: Path):
    """The KG reference backend (yaml); precedents go to a temp file, never into kg/seed."""
    from kg.yaml_backend import YamlBackend

    return YamlBackend(precedents_path=precedents)


@pytest.fixture(scope="session")
def kb(passages_built, tmp_path_factory):
    """Shared, read-only use. Tests that add precedents take `fresh_kb`."""
    return make_kb(tmp_path_factory.mktemp("kb") / "precedents.yaml")


@pytest.fixture
def fresh_kb(passages_built, tmp_path):
    return make_kb(tmp_path / "precedents.yaml")


@pytest.fixture(scope="session")
def seeds(kb):
    from tools.make_submissions import build_submissions

    return {s.id: s for s in build_submissions(kb)}


@pytest.fixture
def itsg_bytes():
    return ITSG_FILE.read_bytes()
