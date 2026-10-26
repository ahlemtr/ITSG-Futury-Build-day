"""Step K9.3: load the validated graph into Neo4j (08 section 12.3). Idempotent: MERGE by key, never deletes.

To rebuild from zero: run `MATCH (n) DETACH DELETE n` by hand in Neo4j Browser, then load again.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from kg.common import env, to_date

# Labels and relationship types come from this whitelist (07 section 3), never from input data.
LABELS = ["Document", "DocVersion", "Passage", "MessageType", "Record", "Field", "Rule", "Criterion",
          "Parameter", "ParamValue", "Change", "TestCase", "Precedent"]
REL_TYPES = ["HAS_VERSION", "SUCCEEDS", "CONTAINS", "USES_BLOCK", "HAS_FIELD", "CARRIES", "DESCRIBED_IN",
             "APPLIES_TO", "CONSTRAINS", "SOURCED_FROM", "IMPLEMENTS", "USES_PARAM", "HAS_VALUE", "MODIFIES_OLD",
             "MODIFIES_NEW", "DERIVED_FROM", "CHANGES_PARAM", "TARGETS", "CLONE_OF", "HIDDEN_OF", "ABOUT",
             "JUSTIFIED_BY"]
DATE_PROPS = {"published", "valid_from", "decided"}  # stored as Neo4j date() (08 section 1.5)
BATCH = 500


def connect():
    from neo4j import GraphDatabase

    uri = env("NEO4J_URI", "bolt://localhost:7687")
    user = env("NEO4J_USER", "neo4j")
    password = env("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD not set (see .env.example)")
    # notifications off: queries on optional parts (no Precedent yet) would log "type does not exist"
    driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")
    driver.verify_connectivity()
    return driver


def check_label(label: str) -> str:
    if label not in LABELS:
        raise ValueError(f"label {label!r} not in the schema whitelist")
    return label


def check_rel(rel: str) -> str:
    if rel not in REL_TYPES:
        raise ValueError(f"relationship type {rel!r} not in the schema whitelist")
    return rel


def db_props(props: dict) -> dict:
    return {k: (to_date(v) if k in DATE_PROPS and v is not None else v) for k, v in props.items()}


def _batches(rows: list, size: int = BATCH):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def load(graph: dict, driver) -> None:
    nodes: dict[str, list] = defaultdict(list)
    for n in graph["nodes"]:
        nodes[check_label(n["label"])].append({"key": n["key"], "props": db_props(n["props"])})
    edges: dict[tuple[str, str, str], list] = defaultdict(list)
    for e in graph["edges"]:
        group = (check_rel(e["type"]), check_label(e["from_label"]), check_label(e["to_label"]))
        edges[group].append({"from": e["from_key"], "to": e["to_key"], "props": db_props(e["props"])})

    with driver.session() as s:
        for label in LABELS:
            s.run(f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS FOR (n:{label}) REQUIRE n.key IS UNIQUE")
        for label, rows in nodes.items():
            for chunk in _batches(rows):
                s.run(f"UNWIND $rows AS row MERGE (n:{label} {{key: row.key}}) SET n += row.props", rows=chunk)
        for (rel, from_label, to_label), rows in edges.items():
            for chunk in _batches(rows):
                s.run(
                    f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.from}}) MATCH (b:{to_label} {{key: r.to}}) "
                    f"MERGE (a)-[e:{rel}]->(b) SET e += r.props",
                    rows=chunk,
                )
        s.run(
            "CREATE FULLTEXT INDEX passage_text IF NOT EXISTS FOR (p:Passage) ON EACH [p.text, p.heading] "
            "OPTIONS {indexConfig: {`fulltext.analyzer`: 'german'}}"
        )
        s.run("CALL db.awaitIndexes(300)")


def db_counts(driver) -> tuple[Counter, Counter]:
    with driver.session() as s:
        nodes = Counter({r["label"]: r["n"] for r in s.run(
            "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n")})
        edges = Counter({r["type"]: r["n"] for r in s.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n")})
    return nodes, edges
