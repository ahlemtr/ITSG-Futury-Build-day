"""Neo4j backend: one Cypher query per interface method (08 section 13, base queries in 07 section 8)."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from engine.model import (
    Change,
    DeviationContext,
    FieldDef,
    FlaggedBlock,
    Graph,
    GraphEdge,
    GraphNode,
    Impact,
    Layout,
    Passage,
    Precedent,
    Rule,
    SpecRef,
    TestCase,
    TestCaseRef,
    Version,
)
from kg import load
from kg.common import MAX_SUBGRAPH_DEPTH, norm_field, resolve_passage_key, resolve_vb, to_date

PASSAGE_PROPS = "{.key, .doc, .version, .section, .part, .heading, .text, .page, .field}"
NARROW_BOOST = 1.25  # same re-ranking as the YAML backend: a part or field beats its section
RRF_K = 60  # reciprocal rank fusion constant (Cormack et al. 2009)
FULLTEXT_WEIGHT = 2.0  # spec queries quote the legal wording: exact terms count more than meaning
LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')
LUCENE_OPERATORS = {"AND", "OR", "NOT", "TO"}


def _lucene_term(term: str) -> str:
    """Free text as plain Lucene terms: special characters escaped, operator words lower-cased
    (the German analyzer lower-cases anyway, so "OR" still finds "or")."""
    if term in LUCENE_OPERATORS:
        term = term.lower()
    return LUCENE_SPECIAL.sub(r"\\\1", term)

RULES_QUERY = """
MATCH (r:Rule) WHERE r.key IN $keys
OPTIONAL MATCH (r)-[:APPLIES_TO]->(m:MessageType)
WITH r, collect(DISTINCT m.key) AS applies_to
OPTIONAL MATCH (r)-[:CONSTRAINS]->(f:Field)
WITH r, applies_to, collect(DISTINCT f.key) AS fields
OPTIONAL MATCH (r)-[:USES_PARAM]->(prm:Parameter)
WITH r, applies_to, fields, collect(DISTINCT prm.key) AS params
OPTIONAL MATCH (r)-[:SOURCED_FROM]->(p:Passage) WHERE $vb IS NULL OR p.doc <> 'VB' OR p.version = $vb
WITH r, applies_to, fields, params, collect(DISTINCT p.key) AS sources
OPTIONAL MATCH (r)-[:IMPLEMENTS]->(c:Criterion)
RETURN r {.*} AS r, applies_to, fields, params, sources, head(collect(c.key)) AS criterion
ORDER BY r.order
"""

TEST_REFS_QUERY = """
MATCH (t:TestCase) WHERE t.key IN $keys
OPTIONAL MATCH (t)-[:TARGETS]->(r:Rule)
WITH t, r ORDER BY r.order
WITH t, collect(r.key) AS targets
OPTIONAL MATCH (t)-[:DESCRIBED_IN]->(p:Passage)
RETURN t {.*} AS t, targets, collect(p.key) AS sources
ORDER BY t.order
"""


def native(value):
    """Neo4j temporal values to Python."""
    if hasattr(value, "to_native"):
        return value.to_native()
    if isinstance(value, dict):
        return {k: native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [native(v) for v in value]
    return value


class GraphBackend:
    def __init__(self, driver=None):
        self.driver = driver or load.connect()
        self._vb_versions: list[str] | None = None

    def close(self) -> None:
        self.driver.close()

    def _q(self, cypher: str, **params) -> list[dict]:
        with self.driver.session() as s:
            return [native(r.data()) for r in s.run(cypher, **params)]

    def _one(self, cypher: str, what: str, **params) -> dict:
        rows = self._q(cypher, **params)
        if not rows:
            raise KeyError(f"{what} not found")
        return rows[0]

    @property
    def vb_versions(self) -> list[str]:
        if self._vb_versions is None:
            rows = self._q("MATCH (d:DocVersion {doc: 'VB'}) RETURN d.version AS version ORDER BY d.valid_from, d.version")
            self._vb_versions = [r["version"] for r in rows]
        return self._vb_versions

    # ---------------------------------------------------------------- builders
    def _rules(self, keys: list[str], vb: str | None = None) -> list[Rule]:
        rows = self._q(RULES_QUERY, keys=list(keys), vb=vb)
        return [Rule(id=r["r"]["key"], title=r["r"]["title"], description=r["r"].get("description") or "",
                     kind=r["r"]["kind"], status=r["r"]["status"], criterion=r["criterion"],
                     applies_to=sorted(r["applies_to"]), fields=sorted(r["fields"]), params=sorted(r["params"]),
                     sources=sorted(r["sources"])) for r in rows]

    def _passages(self, keys: list[str]) -> list[Passage]:
        rows = self._q(f"MATCH (p:Passage) WHERE p.key IN $keys RETURN p {PASSAGE_PROPS} AS p ORDER BY p.key",
                       keys=list(keys))
        return [Passage(**r["p"]) for r in rows]

    def _test_refs(self, keys: list[str], full: bool = False) -> list[TestCaseRef]:
        out = []
        for r in self._q(TEST_REFS_QUERY, keys=list(keys)):
            t = r["t"]
            ref = {"key": t["key"], "kind": t["kind"], "origin": t["origin"], "status": t["status"], "hidden": t["hidden"],
                       "steps": t["steps"], "parent": t.get("parent"), "targets": r["targets"]}
            if full:
                out.append(TestCase(**ref, inputs=json.loads(t["inputs"]), expected=json.loads(t["expected"]),
                                    sources=sorted(r["sources"])))
            else:
                out.append(TestCaseRef(**ref))
        return out

    def _field_key(self, record: str, field: str) -> str:
        key = field if "." in field else f"{record}.{field}"
        rec, name = key.split(".", 1)
        rows = self._q("MATCH (f:Field) WHERE f.key IN $keys RETURN f.key AS k", keys=[key, f"{rec}.{norm_field(name)}"])
        found = {r["k"] for r in rows}
        if key in found:
            return key
        if f"{rec}.{norm_field(name)}" in found:
            return f"{rec}.{norm_field(name)}"
        raise KeyError(f"Field {key!r} not found")

    # ---------------------------------------------------------------- interface
    def _document_versions(self) -> list[dict]:
        return [r["d"] for r in self._q("MATCH (d:DocVersion) RETURN d {.*} AS d")]

    def get_field_definitions(self, record: str, field: str | None = None,
                              version: str | None = None, on_date=None) -> list[dict]:
        from kg.field_evidence import applicable_documents

        if version is not None:
            version = resolve_vb(version, self.vb_versions)
        active = applicable_documents(self._document_versions(), version, on_date)
        fkey = self._field_key(record, field) if field else None
        rows = self._q("MATCH (d:FieldDefinition {record: $record}) "
                       "WHERE $field IS NULL OR d.field = $field RETURN d {.*} AS d ORDER BY d.key",
                       record=record, field=fkey)
        return [dict(r["d"], applicable=r["d"]["document_version"] in active) for r in rows]

    def get_layout(self, record: str, version: str) -> Layout:
        from kg.field_evidence import resolve_fields

        vb = resolve_vb(version, self.vb_versions)
        row = self._one(
            "MATCH (rec:Record {key: $record}) "
            "OPTIONAL MATCH (rec)-[h:HAS_FIELD]->(f:Field) "
            "WITH rec, h, f ORDER BY h.order "
            "RETURN rec {.*} AS rec, collect(f {.*}) AS fields",
            f"Record {record!r}", record=record)
        rec = row["rec"]
        fields = []
        resolved = resolve_fields(row["fields"], self.get_field_definitions(record, version=vb),
                                  self._document_versions(), vb)
        for f in resolved:
            f["values"] = json.loads(f["values"]) if f.get("values") else None
            fields.append(FieldDef(**f))
        return Layout(record=record, title=rec["title"], section=rec["section"], page=rec.get("page"),
                      fixed_length=rec["fixed_length"], status=rec["status"], version=vb, fields=fields)

    def get_rules(self, abgabegrund: str, version: str) -> list[Rule]:
        vb = resolve_vb(version, self.vb_versions)
        rows = self._q("MATCH (r:Rule)-[:APPLIES_TO]->(:MessageType {key: $ag}) RETURN r.key AS k", ag=str(abgabegrund))
        return self._rules([r["k"] for r in rows], vb)

    def get_param(self, name: str, version: str | None = None, on_date: dt.date | str | None = None) -> Any:
        self._one("MATCH (p:Parameter {key: $name}) RETURN p.key AS k", f"Parameter {name!r}", name=name)
        if version is not None:
            rows = self._q("MATCH (:Parameter {key: $name})-[:HAS_VALUE]->(v:ParamValue {version: $version}) "
                           "RETURN v.value AS value", name=name, version=version)
            if not rows:
                raise KeyError(f"parameter {name!r} has no value for version {version!r}")
            return rows[0]["value"]
        if on_date is None:
            raise ValueError("get_param needs version or on_date")
        rows = self._q("MATCH (:Parameter {key: $name})-[:HAS_VALUE]->(v:ParamValue) "
                       "WHERE NOT v.simulated AND v.valid_from IS NOT NULL AND v.valid_from <= $d "
                       "RETURN v.value AS value ORDER BY v.valid_from DESC LIMIT 1", name=name, d=to_date(on_date))
        if not rows:
            raise KeyError(f"parameter {name!r} has no value valid on {on_date}")
        return rows[0]["value"]

    def get_passage(self, ref: str | SpecRef) -> Passage:
        key = resolve_passage_key(ref.key if isinstance(ref, SpecRef) else ref, self.vb_versions)
        found = self._passages([key])
        if not found:
            raise KeyError(f"Passage {key!r} not found")
        return found[0]

    def search_passages(self, text: str, k: int = 5, version: str | None = None, on_date=None) -> list[Passage]:
        """Hybrid search on chunks (W7): full-text and vector (needs embeddings and OPENAI_API_KEY) ranks merged by
        reciprocal rank fusion, full-text weighted higher; a passage scores with its best chunk and comes back with
        the sentence that matched."""
        from neo4j.exceptions import Neo4jError

        from kg import embed
        from kg.chunks import snippet
        from kg.field_evidence import applicable_documents

        pool = max(60, k * 12)
        heads = None
        if version is not None or on_date is not None:
            vb = resolve_vb(version, self.vb_versions) if version else None
            heads = sorted(applicable_documents(self._document_versions(), vb, on_date))
        query = " ".join(_lucene_term(t) for t in text.split())
        lists: list[tuple[float, list[dict]]] = []  # (weight, ranked chunks)
        if query:
            rows = self._q("CALL db.index.fulltext.queryNodes('chunk_text', $q, {limit: $limit}) YIELD node, score "
                           "WHERE $heads IS NULL OR split(node.passage, '#')[0] IN $heads "
                           "RETURN node.passage AS passage, node.text AS text, score", q=query, limit=pool, heads=heads)
            lists.append((FULLTEXT_WEIGHT, rows))
            # whole passages too: a section about the topic beats a list that only names it
            rows = self._q("CALL db.index.fulltext.queryNodes('passage_text', $q, {limit: $limit}) YIELD node, score "
                           "WHERE $heads IS NULL OR split(node.key, '#')[0] IN $heads "
                           "RETURN node.key AS passage, node.text AS text, score", q=query, limit=pool, heads=heads)
            lists.append((FULLTEXT_WEIGHT, rows))
        stored = self._q("MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN size(c.embedding) AS n LIMIT 1")
        if embed.available() and stored and text.strip():
            vector = embed.embed_query(text)
            if len(vector) == stored[0]["n"]:  # a different embedding model would not fit the index
                try:
                    lists.append((1.0, self._q(
                        "CALL db.index.vector.queryNodes('chunk_embedding', $k, $v) YIELD node, score "
                        "WHERE $heads IS NULL OR split(node.passage, '#')[0] IN $heads "
                        "RETURN node.passage AS passage, node.text AS text, score ORDER BY score DESC",
                        k=pool, v=vector, heads=heads)))
                except Neo4jError:
                    pass  # no usable vector index: full-text only
        fused: dict[str, float] = {}
        best_text: dict[str, tuple[float, str]] = {}
        for weight, ranked in lists:
            for rank, row in enumerate(ranked):
                score = weight / (RRF_K + rank + 1)
                fused[row["passage"]] = max(fused.get(row["passage"], 0.0), 0.0) + score
                if score > best_text.get(row["passage"], (0.0, ""))[0] and len(row["text"] or "") <= 4000:
                    best_text[row["passage"]] = (score, row["text"])
        if not fused:
            return []
        keys = sorted(fused, key=lambda key: (-fused[key], key))[: k * 3]
        rows = self._q(f"MATCH (p:Passage) WHERE p.key IN $keys RETURN p {PASSAGE_PROPS} AS p", keys=keys)
        props = {r["p"]["key"]: r["p"] for r in rows}
        boost = {key: NARROW_BOOST if props[key].get("part") or props[key].get("field") else 1.0 for key in props}
        best = sorted(props, key=lambda key: (-fused[key] * boost[key], key))[:k]
        return [Passage(**props[key], snippet=snippet(best_text.get(key, (0, props[key].get("text") or ""))[1], text))
                for key in best]

    def get_versions(self, document: str) -> list[Version]:
        rows = self._q("MATCH (:Document {key: $doc})-[:HAS_VERSION]->(v:DocVersion) "
                       "OPTIONAL MATCH (v)-[:SUCCEEDS]->(o:DocVersion) "
                       "RETURN v {.*} AS v, o.version AS succeeds", doc=document)
        out = [Version(document=document, version=r["v"]["version"], published=r["v"].get("published"),
                       valid_from=r["v"].get("valid_from"), file=r["v"].get("file"), succeeds=r["succeeds"])
               for r in rows]
        return sorted(out, key=lambda v: (v.valid_from or dt.date.min, v.published or dt.date.min, v.version))

    def get_changes(self, document: str, old_version: str, new_version: str,
                    in_scope_only: bool = True) -> list[Change]:
        rows = self._q(
            "MATCH (c:Change {document: $doc, old_version: $old, new_version: $new}) "
            "WHERE c.in_scope OR NOT $in_scope_only "
            "OPTIONAL MATCH (c)-[:DERIVED_FROM]->(d:Change) WITH c, collect(d.key) AS derived_from "
            "OPTIONAL MATCH (c)-[:CHANGES_PARAM]->(p:Parameter) WITH c, derived_from, collect(p.key) AS changes_param "
            "OPTIONAL MATCH (c)-[:MODIFIES_OLD]->(o:Passage) "
            "WITH c, derived_from, changes_param, collect(o.key) AS modifies_old "
            "OPTIONAL MATCH (c)-[:MODIFIES_NEW]->(n:Passage) "
            "RETURN c {.*} AS c, derived_from, changes_param, modifies_old, collect(n.key) AS modifies_new "
            "ORDER BY c.key",
            doc=document, old=old_version, new=new_version, in_scope_only=in_scope_only)
        return [Change(**r["c"], derived_from=sorted(r["derived_from"]), changes_param=sorted(r["changes_param"]),
                       modifies_old=sorted(r["modifies_old"]), modifies_new=sorted(r["modifies_new"])) for r in rows]

    def get_affected_rules(self, change_keys: list[str]) -> Impact:
        found = {r["k"] for r in self._q("MATCH (c:Change) WHERE c.key IN $ids RETURN c.key AS k", ids=change_keys)}
        for c in change_keys:
            if c not in found:
                raise KeyError(f"Change {c!r} not found")
        recompute = [r["k"] for r in self._q(
            "MATCH (c:Change)-[:CHANGES_PARAM]->(:Parameter)<-[:USES_PARAM]-(r:Rule) WHERE c.key IN $ids "
            "RETURN DISTINCT r.key AS k", ids=change_keys)]
        review = [r["k"] for r in self._q(
            "MATCH (c:Change)-[:MODIFIES_OLD|MODIFIES_NEW]->(:Passage)<-[:SOURCED_FROM]-(r:Rule) WHERE c.key IN $ids "
            "RETURN DISTINCT r.key AS k", ids=change_keys) if r["k"] not in recompute]
        tests = [r["k"] for r in self._q(
            "MATCH (t:TestCase)-[:TARGETS]->(r:Rule) WHERE r.key IN $rules RETURN DISTINCT t.key AS k",
            rules=recompute)]
        return Impact(recompute=self._rules(recompute), review=self._rules(review), tests=self._test_refs(tests))

    def get_test_cases(self, rule_id: str | None = None, include_hidden: bool = False) -> list[TestCaseRef]:
        if rule_id is not None:
            self._one("MATCH (r:Rule {key: $r}) RETURN r.key AS k", f"Rule {rule_id!r}", r=rule_id)
        rows = self._q("MATCH (t:TestCase) WHERE ($rule IS NULL OR (t)-[:TARGETS]->(:Rule {key: $rule})) "
                       "AND ($hidden OR NOT t.hidden) RETURN t.key AS k", rule=rule_id, hidden=include_hidden)
        return self._test_refs([r["k"] for r in rows])

    def get_test_case(self, key: str) -> TestCase:
        found = self._test_refs([key], full=True)
        if not found:
            raise KeyError(f"TestCase {key!r} not found")
        return found[0]

    def get_deviation_context(self, record: str, field: str, abgabegrund: str, version: str) -> DeviationContext:
        from kg.field_evidence import applicable_documents

        vb = resolve_vb(version, self.vb_versions)
        active = applicable_documents(self._document_versions(), vb)
        fkey = self._field_key(record, field)
        ag = str(abgabegrund)
        rule_keys = [r["k"] for r in self._q(
            "MATCH (r:Rule)-[:CONSTRAINS]->(:Field {key: $field}) WHERE (r)-[:APPLIES_TO]->(:MessageType {key: $ag}) "
            "RETURN r.key AS k", field=fkey, ag=ag)]
        rules = self._rules(rule_keys, vb)
        passage_keys = {s for r in rules for s in r.sources}
        passage_keys |= {r["k"] for r in self._q(
            "MATCH (:Field {key: $field})-[:DESCRIBED_IN]->(p:Passage) WHERE p.doc <> 'VB' OR p.version = $vb "
            "RETURN p.key AS k", field=fkey, vb=vb)}
        passage_keys = {pk for pk in passage_keys if pk.split("#", 1)[0] in active}
        precedents = [r["k"] for r in self._q(
            "MATCH (p:Precedent)-[:ABOUT]->(:Field {key: $field}) RETURN p.key AS k ORDER BY k", field=fkey)]
        flag = fkey.split(".", 1)[1]
        blocks = self._q("MATCH (:MessageType {key: $ag})-[u:USES_BLOCK {flag: $flag}]->(b:Record) "
                         "RETURN b.key AS record, u.mandatory AS mandatory ORDER BY record", ag=ag, flag=flag)
        return DeviationContext(
            record=record, field=fkey, abgabegrund=ag, version=version, rules=rules,
            passages=self._passages(sorted(passage_keys)),
            precedents=[self.find_precedent(k) for k in precedents],
            flagged_blocks=[FlaggedBlock(record=b["record"], flag=flag, mandatory=b["mandatory"]) for b in blocks],
        )

    def _normalize_precedent(self, p: Precedent) -> Precedent:
        """Same rule as the YAML backend: field = the real Field key, key rebuilt from it, every
        justification an existing Rule or Passage (unknown ones are an error, not silently dropped)."""
        fkey = self._field_key(p.field.split(".", 1)[0], p.field)
        for j in p.justified_by:
            label = "Passage" if "#" in j else "Rule"
            if not self._q(f"MATCH (x:{label} {{key: $j}}) RETURN 1 AS x", j=j):
                raise KeyError(f"precedent justification {label} {j!r} not found")
        return Precedent(**{**p.model_dump(), "field": fkey, "key": ""})

    def _signature(self, signature: str) -> str:
        ag, field, kind = signature.split("|")
        try:
            field = self._field_key(field.split(".", 1)[0], field)
        except KeyError:
            pass
        return f"{ag}|{field}|{kind}"

    def add_precedent(self, p: Precedent) -> None:
        p = self._normalize_precedent(p)
        props = {"abgabegrund": p.abgabegrund, "field": p.field, "kind": p.kind, "verdict": p.verdict,
                 "reason": p.reason, "advisor": p.advisor, "decided": p.decided}
        justified = [{"key": j, "passage": "#" in j} for j in p.justified_by]

        def write(tx):
            tx.run("MATCH (f:Field {key: $field}) MERGE (p:Precedent {key: $key}) SET p += $props "
                   "MERGE (p)-[:ABOUT]->(f) "
                   "WITH p OPTIONAL MATCH (p)-[old:JUSTIFIED_BY]->() DELETE old",
                   field=p.field, key=p.key, props=props).consume()
            for label, flag in (("Passage", True), ("Rule", False)):
                tx.run(f"UNWIND $rows AS j MATCH (p:Precedent {{key: $key}}) MATCH (x:{label} {{key: j.key}}) "
                       "MERGE (p)-[:JUSTIFIED_BY]->(x)",
                       key=p.key, rows=[j for j in justified if j["passage"] == flag]).consume()

        with self.driver.session() as s:
            s.execute_write(write)  # one transaction: no half-written precedent

    def find_precedent(self, signature: str) -> Precedent | None:
        rows = self._q("MATCH (p:Precedent {key: $key}) OPTIONAL MATCH (p)-[:JUSTIFIED_BY]->(x) "
                       "RETURN p {.*} AS p, collect(x.key) AS justified_by", key=self._signature(signature))
        if not rows:
            return None
        p = rows[0]["p"]
        return Precedent(key=p["key"], abgabegrund=p["abgabegrund"], field=p["field"], kind=p["kind"],
                         verdict=p["verdict"], reason=p.get("reason") or "", advisor=p.get("advisor"),
                         decided=p.get("decided"), justified_by=sorted(rows[0]["justified_by"]))

    def remove_precedent(self, signature: str) -> None:
        """Test helper."""
        self._q("MATCH (p:Precedent {key: $key}) DETACH DELETE p", key=self._signature(signature))

    def subgraph(self, label: str, key: str, depth: int = 1) -> Graph:
        depth = max(1, min(int(depth), MAX_SUBGRAPH_DEPTH))
        load.check_label(label)
        start = self._one(f"MATCH (n:{label} {{key: $key}}) RETURN n {{.*, embedding: null}} AS n",
                          f"{label} {key!r}", key=key)["n"]
        nodes = {(label, key): start}
        edges: dict[tuple, GraphEdge] = {}
        frontier = [(label, key)]
        for _ in range(depth):
            nxt = []
            by_label: dict[str, list[str]] = {}
            for lb, k in frontier:
                by_label.setdefault(lb, []).append(k)
            for lb, keys in by_label.items():
                rows = self._q(
                    f"MATCH (a:{load.check_label(lb)})-[r]-(b) WHERE a.key IN $keys "
                    "RETURN a.key AS a, type(r) AS type, startNode(r) = a AS outgoing, labels(b)[0] AS bl, "
                    "b.key AS b, properties(r) AS props, b {.*, embedding: null} AS bprops",
                    keys=keys)
                for r in rows:
                    a, b = (lb, r["a"]), (r["bl"], r["b"])
                    src, dst = (a, b) if r["outgoing"] else (b, a)
                    edges[(r["type"], *src, *dst)] = GraphEdge(type=r["type"], from_label=src[0], from_key=src[1],
                                                               to_label=dst[0], to_key=dst[1], props=r["props"])
                    if b not in nodes:
                        nodes[b] = r["bprops"]
                        nxt.append(b)
            frontier = nxt
        return Graph(
            nodes=[GraphNode(label=lb, key=k, props={pk: pv for pk, pv in p.items() if pk != "embedding"})
                   for (lb, k), p in sorted(nodes.items())],
            edges=[e for _, e in sorted(edges.items())],
        )
