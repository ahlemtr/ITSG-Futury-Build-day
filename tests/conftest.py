from __future__ import annotations

import pytest

from kg.common import BUILD_DIR


@pytest.fixture(scope="session")
def passages_built():
    """The YAML backend and the build read kg/build/passages.yaml; extract it once if missing."""
    if not (BUILD_DIR / "passages.yaml").exists():
        from kg import extract

        extract.run()
    return BUILD_DIR / "passages.yaml"


@pytest.fixture(scope="session")
def neo4j_driver():
    """A driver to the Neo4j of .env with the graph loaded, or skip."""
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
