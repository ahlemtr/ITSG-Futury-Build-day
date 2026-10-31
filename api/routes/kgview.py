"""Knowledge graph tab: what the graph holds, how it grew, and "ask the graph"."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Request

from api.routes.common import catalogue_on_rules, kb

router = APIRouter()

SHOWN = ["DocVersion", "Passage", "Chunk", "Rule", "Parameter", "ParamValue", "Change", "TestCase", "Precedent",
         "Field", "FieldDefinition"]


@router.get("/kg/stats")
def stats(request: Request):
    """Nodes per label, links, embedded chunks and the document versions the graph knows."""
    k = kb(request)
    if hasattr(k, "_q"):  # Neo4j
        labels = {r["label"]: r["n"] for r in k._q("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n")}
        edges = k._q("MATCH ()-[e]->() RETURN count(e) AS n")[0]["n"]
        embedded = k._q("MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) AS n")[0]["n"]
        versions = [r["v"] for r in k._q("MATCH (v:DocVersion) RETURN v.key AS v ORDER BY v")]
        backend = "neo4j"
    else:
        labels = dict(Counter(label for (label, _key) in k.nodes))
        edges = sum(len(v) for v in k.out.values()) if hasattr(k, "out") else None
        embedded = 0
        versions = sorted(key for (label, key) in k.nodes if label == "DocVersion")
        backend = "yaml"
    return {"backend": backend, "nodes": {label: labels.get(label, 0) for label in SHOWN},
            "total_nodes": sum(labels.values()), "edges": edges, "embedded_chunks": embedded, "versions": versions}


@router.get("/kg/ask")
def ask(request: Request, q: str, k: int = 6, version: str | None = None, on_date: str | None = None):
    """Question or change text in: the passages that match (with the sentence), the rules built on them, the
    changes that modified them and the test cases on those rules."""
    graph = kb(request)
    out = []
    for p in graph.search_passages(q, k, version=version, on_date=on_date):
        sub = graph.subgraph("Passage", p.key, 1)
        rules = sorted({e.from_key for e in sub.edges if e.type == "SOURCED_FROM" and e.from_label == "Rule"})
        changes = sorted({e.from_key for e in sub.edges if e.type in ("MODIFIES_OLD", "MODIFIES_NEW")})
        tests = sorted({t.id for t in catalogue_on_rules(request, rules)}) if rules else []
        out.append({"passage": p.model_dump(), "rules": rules, "changes": changes, "tests": tests})
    return {"query": q, "results": out}


@router.get("/kg/fields/{record}/definitions")
def field_definitions(request: Request, record: str, field: str | None = None,
                      version: str | None = None, on_date: str | None = None):
    return {"record": record, "definitions": kb(request).get_field_definitions(record, field, version, on_date)}
