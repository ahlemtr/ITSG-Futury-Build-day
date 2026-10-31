"""Reference backend: reads kg/seed, layouts/ and kg/build/passages.yaml, no Neo4j or OpenAI needed.

It answers from the same in-memory graph seed_graph builds for Neo4j, so both backends give the
same answers. Precedents are appended to kg/seed/precedents.yaml.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import re
from collections import defaultdict
from pathlib import Path
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
from kg.common import (
    BUILD_DIR,
    LAYOUT_DIR,
    MAX_SUBGRAPH_DEPTH,
    SEED_DIR,
    dump_yaml,
    keep_source,
    load_yaml,
    norm_field,
    passage_doc_version,
    resolve_passage_key,
    resolve_vb,
    to_date,
)
from kg.seed_graph import GraphBuilder, Seed, add_precedent_nodes, build_from, jsonable

_TOKEN = re.compile(r"\w+", re.UNICODE)
NARROW_BOOST = 1.25  # a 3.12 part or a field passage beats the section that contains it


def search_patterns(tokens: list[str]) -> list[re.Pattern]:
    """Substring search anchored at word starts ("vorerkrankung" matches "Vorerkrankungen", "6" not "2026"),
    plus one pattern per pair of adjacent query words ("6 Monate" as a phrase). Numbers must match whole
    ("6" not "60" or "6.1.2"), words may continue (German inflection and compounds)."""

    def pat(t: str) -> str:
        return r"(?<!\w)" + re.escape(t) + (r"(?![\w.]*\d)" if t.isdigit() else "")

    pats = [re.compile(pat(t)) for t in tokens]
    pats += [re.compile(pat(a) + r"\W+" + pat(b)) for a, b in itertools.pairwise(tokens)]
    return pats


def search_score(patterns: list[re.Pattern], text: str, df: list[int], n_docs: int, avg_len: float) -> float:
    """BM25 over the patterns (text already lower case)."""
    length = max(len(text), 1)
    score = 0.0
    for pat, d in zip(patterns, df):
        tf = len(pat.findall(text))
        if not tf:
            continue
        idf = math.log(1 + (n_docs - d + 0.5) / (d + 0.5))
        score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg_len))
    return score


class YamlBackend:
    def __init__(self, seed_dir: Path = SEED_DIR, layout_dir: Path = LAYOUT_DIR,
                 passages_path: Path = BUILD_DIR / "passages.yaml", precedents_path: Path | None = None):
        seed = Seed(seed_dir, layout_dir, passages_path)
        self.precedents_path = precedents_path or seed_dir / "precedents.yaml"
        if precedents_path is not None:
            seed.precedents = (load_yaml(precedents_path) or []) if precedents_path.exists() else []
        self._load(build_from(seed))

    # ---------------------------------------------------------------- index
    def _load(self, graph: dict) -> None:
        self.nodes: dict[tuple[str, str], dict] = {}
        self._search_docs: list[tuple[str, dict, str, str]] | None = None
        self.out: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.inn: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for n in graph["nodes"]:
            self.nodes[(n["label"], n["key"])] = n["props"]
        for e in graph["edges"]:
            self._add_edge(e)
        self.vb_versions = [k for _, k in sorted(
            ((p["valid_from"] or "", p["version"]) for (lb, _), p in self.nodes.items()
             if lb == "DocVersion" and p["doc"] == "VB"))]

    def _add_edge(self, e: dict) -> None:
        src, dst = (e["from_label"], e["from_key"]), (e["to_label"], e["to_key"])
        self.out[src] = [x for x in self.out[src] if not (x["type"] == e["type"] and
                                                          (x["to_label"], x["to_key"]) == dst)] + [e]
        self.inn[dst] = [x for x in self.inn[dst] if not (x["type"] == e["type"] and
                                                         (x["from_label"], x["from_key"]) == src)] + [e]

    def _props(self, label: str, key: str) -> dict:
        try:
            return self.nodes[(label, key)]
        except KeyError:
            raise KeyError(f"{label} {key!r} not found") from None

    def _targets(self, label: str, key: str, type_: str) -> list[str]:
        return [e["to_key"] for e in self.out[(label, key)] if e["type"] == type_]

    def _sources(self, label: str, key: str, type_: str, from_label: str | None = None) -> list[str]:
        return [e["from_key"] for e in self.inn[(label, key)]
                if e["type"] == type_ and (from_label is None or e["from_label"] == from_label)]

    def _labelled(self, label: str) -> list[tuple[str, dict]]:
        return [(k, p) for (lb, k), p in self.nodes.items() if lb == label]

    def _rule_order(self, key: str) -> int:
        return self.nodes[("Rule", key)]["order"]

    # ---------------------------------------------------------------- builders
    def _rule(self, key: str, vb: str | None = None) -> Rule:
        p = self._props("Rule", key)
        criteria = self._targets("Rule", key, "IMPLEMENTS")
        return Rule(
            id=key, title=p["title"], description=p.get("description") or "", kind=p["kind"], status=p["status"],
            criterion=criteria[0] if criteria else None,
            applies_to=sorted(self._targets("Rule", key, "APPLIES_TO")),
            fields=sorted(self._targets("Rule", key, "CONSTRAINS")),
            params=sorted(self._targets("Rule", key, "USES_PARAM")),
            sources=sorted(s for s in self._targets("Rule", key, "SOURCED_FROM") if keep_source(s, vb)),
        )

    def _passage(self, key: str) -> Passage:
        return Passage(key=key, **{k: v for k, v in self._props("Passage", key).items() if k != "embedding"})

    def _test_ref(self, key: str, cls=TestCaseRef, **extra) -> TestCaseRef:
        p = self._props("TestCase", key)
        targets = sorted(self._targets("TestCase", key, "TARGETS"), key=self._rule_order)
        return cls(key=key, kind=p["kind"], origin=p["origin"], status=p["status"], hidden=p["hidden"],
                   steps=p["steps"], parent=p.get("parent"), targets=targets, **extra)

    def _precedent(self, key: str) -> Precedent:
        p = self._props("Precedent", key)
        return Precedent(key=key, abgabegrund=p["abgabegrund"], field=p["field"], kind=p["kind"],
                         verdict=p["verdict"], reason=p.get("reason") or "", advisor=p.get("advisor"),
                         decided=p.get("decided"), justified_by=sorted(self._targets("Precedent", key, "JUSTIFIED_BY")))

    def _field_key(self, record: str, field: str) -> str:
        key = field if "." in field else f"{record}.{field}"
        if ("Field", key) not in self.nodes:
            rec, name = key.split(".", 1)
            key = f"{rec}.{norm_field(name)}"
        self._props("Field", key)
        return key

    # ---------------------------------------------------------------- interface
    def _document_versions(self) -> list[dict]:
        return [dict(p) for _, p in self._labelled("DocVersion")]

    def get_field_definitions(self, record: str, field: str | None = None,
                              version: str | None = None, on_date=None) -> list[dict]:
        from kg.field_evidence import applicable_documents

        if version is not None:
            version = resolve_vb(version, self.vb_versions)
        active = applicable_documents(self._document_versions(), version, on_date)
        fkey = self._field_key(record, field) if field else None
        return [dict(p, key=k, applicable=p["document_version"] in active)
                for k, p in self._labelled("FieldDefinition")
                if p["record"] == record and (fkey is None or p["field"] == fkey)]

    def get_layout(self, record: str, version: str) -> Layout:
        from kg.field_evidence import resolve_fields

        vb = resolve_vb(version, self.vb_versions)
        p = self._props("Record", record)
        edges = sorted((e for e in self.out[("Record", record)] if e["type"] == "HAS_FIELD"),
                       key=lambda e: e["props"]["order"])
        raw_fields = []
        for e in edges:
            f = dict(self.nodes[("Field", e["to_key"])])
            f["values"] = json.loads(f["values"]) if f.get("values") else None
            raw_fields.append(dict(f, key=e["to_key"]))
        fields = [FieldDef(**f) for f in resolve_fields(raw_fields, self.get_field_definitions(record, version=vb),
                                                       self._document_versions(), vb)]
        return Layout(record=record, title=p["title"], section=p["section"], page=p.get("page"),
                      fixed_length=p["fixed_length"], status=p["status"], version=vb, fields=fields)

    def get_rules(self, abgabegrund: str, version: str) -> list[Rule]:
        vb = resolve_vb(version, self.vb_versions)
        keys = sorted(self._sources("MessageType", str(abgabegrund), "APPLIES_TO", "Rule"), key=self._rule_order)
        return [self._rule(k, vb) for k in keys]

    def get_param(self, name: str, version: str | None = None, on_date: dt.date | str | None = None) -> Any:
        self._props("Parameter", name)
        values = [self.nodes[("ParamValue", k)] for k in self._targets("Parameter", name, "HAS_VALUE")]
        if version is not None:
            for v in values:
                if v["version"] == version:
                    return v["value"]
            raise KeyError(f"parameter {name!r} has no value for version {version!r}")
        if on_date is None:
            raise ValueError("get_param needs version or on_date")
        day = to_date(on_date)
        valid = [v for v in values if not v["simulated"] and v["valid_from"] and to_date(v["valid_from"]) <= day]
        if not valid:
            raise KeyError(f"parameter {name!r} has no value valid on {day}")
        return max(valid, key=lambda v: v["valid_from"])["value"]

    def get_passage(self, ref: str | SpecRef) -> Passage:
        key = ref.key if isinstance(ref, SpecRef) else ref
        return self._passage(resolve_passage_key(key, self.vb_versions))

    def search_passages(self, text: str, k: int = 5, version: str | None = None, on_date=None) -> list[Passage]:
        from kg.chunks import snippet
        from kg.field_evidence import applicable_documents

        tokens = list(dict.fromkeys(t.lower() for t in _TOKEN.findall(text)))
        if self._search_docs is None:  # one search document per chunk, scored per passage by its best chunk
            self._search_docs = [(c["passage"], self.nodes[("Passage", c["passage"])],
                                  f"{c.get('heading') or ''}\n{c.get('text') or ''}".lower(), c.get("text") or "")
                                 for _key, c in self._labelled("Chunk")]
        docs = self._search_docs
        if version is not None or on_date is not None:
            vb = resolve_vb(version, self.vb_versions) if version else None
            active = applicable_documents(self._document_versions(), vb, on_date)
            docs = [d for d in docs if d[0].split("#", 1)[0] in active]
        if not tokens or not docs:
            return []
        patterns = search_patterns(tokens)
        df = [sum(1 for _, _, body, _ in docs if pat.search(body)) for pat in patterns]
        avg_len = sum(len(body) for _, _, body, _ in docs) / len(docs)
        best: dict[str, tuple[float, str]] = {}
        for key, p, body, raw in docs:
            s = search_score(patterns, body, df, len(docs), avg_len)
            if s > 0:
                s *= NARROW_BOOST if p.get("part") or p.get("field") else 1.0
                if s > best.get(key, (0.0, ""))[0]:
                    best[key] = (s, raw)
        ranked = sorted(best, key=lambda key: (-best[key][0], key))[:k]
        return [self._passage(key).model_copy(update={"snippet": snippet(best[key][1], text)}) for key in ranked]

    def get_versions(self, document: str) -> list[Version]:
        out = []
        for key, p in self._labelled("DocVersion"):
            if p["doc"] != document:
                continue
            succeeds = self._targets("DocVersion", key, "SUCCEEDS")
            out.append(Version(document=document, version=p["version"], published=p.get("published"),
                               valid_from=p.get("valid_from"), file=p.get("file"),
                               succeeds=passage_doc_version(succeeds[0] + "#")[1] if succeeds else None))
        return sorted(out, key=lambda v: (v.valid_from or dt.date.min, v.published or dt.date.min, v.version))

    def _change(self, key: str) -> Change:
        p = self._props("Change", key)
        return Change(
            key=key, **{k: v for k, v in p.items()},
            derived_from=sorted(self._targets("Change", key, "DERIVED_FROM")),
            changes_param=sorted(self._targets("Change", key, "CHANGES_PARAM")),
            modifies_old=sorted(self._targets("Change", key, "MODIFIES_OLD")),
            modifies_new=sorted(self._targets("Change", key, "MODIFIES_NEW")),
        )

    def get_changes(self, document: str, old_version: str, new_version: str,
                    in_scope_only: bool = True) -> list[Change]:
        keys = sorted(k for k, p in self._labelled("Change")
                      if p["document"] == document and p["old_version"] == old_version
                      and p["new_version"] == new_version and (p["in_scope"] or not in_scope_only))
        return [self._change(k) for k in keys]

    def get_affected_rules(self, change_keys: list[str]) -> Impact:
        params, passages = set(), set()
        for c in change_keys:
            self._props("Change", c)
            params.update(self._targets("Change", c, "CHANGES_PARAM"))
            passages.update(self._targets("Change", c, "MODIFIES_OLD") + self._targets("Change", c, "MODIFIES_NEW"))
        recompute = {r for prm in params for r in self._sources("Parameter", prm, "USES_PARAM", "Rule")}
        review = {r for pk in passages for r in self._sources("Passage", pk, "SOURCED_FROM", "Rule")} - recompute
        tests = {t for r in recompute for t in self._sources("Rule", r, "TARGETS", "TestCase")}
        return Impact(
            recompute=[self._rule(r) for r in sorted(recompute, key=self._rule_order)],
            review=[self._rule(r) for r in sorted(review, key=self._rule_order)],
            tests=[self._test_ref(t) for t in sorted(tests, key=lambda t: self.nodes[("TestCase", t)]["order"])],
        )

    def get_test_cases(self, rule_id: str | None = None, include_hidden: bool = False) -> list[TestCaseRef]:
        if rule_id is None:
            keys = [k for k, _ in self._labelled("TestCase")]
        else:
            self._props("Rule", rule_id)
            keys = self._sources("Rule", rule_id, "TARGETS", "TestCase")
        keys = [k for k in keys if include_hidden or not self.nodes[("TestCase", k)]["hidden"]]
        return [self._test_ref(k) for k in sorted(keys, key=lambda k: self.nodes[("TestCase", k)]["order"])]

    def get_test_case(self, key: str) -> TestCase:
        p = self._props("TestCase", key)
        return self._test_ref(key, TestCase, inputs=json.loads(p["inputs"]), expected=json.loads(p["expected"]),
                              sources=sorted(self._targets("TestCase", key, "DESCRIBED_IN")))

    def get_deviation_context(self, record: str, field: str, abgabegrund: str, version: str) -> DeviationContext:
        from kg.field_evidence import applicable_documents

        vb = resolve_vb(version, self.vb_versions)
        active = applicable_documents(self._document_versions(), vb)
        fkey = self._field_key(record, field)
        ag = str(abgabegrund)
        rule_keys = [r for r in self._sources("Field", fkey, "CONSTRAINS", "Rule")
                     if ag in self._targets("Rule", r, "APPLIES_TO")]
        rules = [self._rule(r, vb) for r in sorted(rule_keys, key=self._rule_order)]
        passage_keys = {s for r in rules for s in r.sources}
        passage_keys |= {pk for pk in self._targets("Field", fkey, "DESCRIBED_IN") if keep_source(pk, vb)}
        passage_keys = {pk for pk in passage_keys if pk.split("#", 1)[0] in active}
        flag = fkey.split(".", 1)[1]
        blocks = [FlaggedBlock(record=e["to_key"], flag=flag, mandatory=e["props"]["mandatory"])
                  for e in self.out[("MessageType", ag)]
                  if e["type"] == "USES_BLOCK" and e["props"].get("flag") == flag]
        return DeviationContext(
            record=record, field=fkey, abgabegrund=ag, version=version, rules=rules,
            passages=[self._passage(k) for k in sorted(passage_keys)],
            precedents=[self._precedent(k) for k in sorted(self._sources("Field", fkey, "ABOUT", "Precedent"))],
            flagged_blocks=sorted(blocks, key=lambda b: b.record),
        )

    def _normalize_precedent(self, p: Precedent) -> Precedent:
        """The precedent as stored: field = the real Field key (BEGINN-AU-1 -> BEGINN-AU), key rebuilt from it,
        every justification an existing Rule or Passage."""
        fkey = self._field_key(p.field.split(".", 1)[0], p.field)
        for j in p.justified_by:
            label = "Passage" if "#" in j else "Rule"
            if (label, j) not in self.nodes:
                raise KeyError(f"precedent justification {label} {j!r} not found")
        return Precedent(**{**p.model_dump(), "field": fkey, "key": ""})

    def _signature(self, signature: str) -> str:
        ag, field, kind = signature.split("|")
        try:
            field = self._field_key(field.split(".", 1)[0], field)
        except KeyError:
            pass
        return f"{ag}|{field}|{kind}"

    def _drop_precedent_index(self, signature: str) -> None:
        self.nodes.pop(("Precedent", signature), None)
        for e in self.out.pop(("Precedent", signature), []):
            dst = (e["to_label"], e["to_key"])
            self.inn[dst] = [x for x in self.inn[dst] if x["from_key"] != signature]

    def add_precedent(self, p: Precedent) -> None:
        p = self._normalize_precedent(p)
        row = jsonable(p.model_dump())
        stored = (load_yaml(self.precedents_path) or []) if self.precedents_path.exists() else []
        stored = [x for x in stored if x.get("key") != p.key] + [row]
        dump_yaml(stored, self.precedents_path)
        self._drop_precedent_index(p.key)  # a re-save replaces the old JUSTIFIED_BY edges
        g = GraphBuilder()
        add_precedent_nodes(g, row)
        result = g.result()
        for n in result["nodes"]:
            self.nodes[(n["label"], n["key"])] = n["props"]
        for e in result["edges"]:
            self._add_edge(e)

    def find_precedent(self, signature: str) -> Precedent | None:
        signature = self._signature(signature)
        return self._precedent(signature) if ("Precedent", signature) in self.nodes else None

    def remove_precedent(self, signature: str) -> None:
        """Test helper: drop a precedent from the file and the index."""
        signature = self._signature(signature)
        stored = (load_yaml(self.precedents_path) or []) if self.precedents_path.exists() else []
        dump_yaml([x for x in stored if x.get("key") != signature], self.precedents_path)
        self._drop_precedent_index(signature)

    def subgraph(self, label: str, key: str, depth: int = 1) -> Graph:
        depth = max(1, min(int(depth), MAX_SUBGRAPH_DEPTH))
        self._props(label, key)
        seen = {(label, key)}
        frontier = [(label, key)]
        edges: dict[tuple, dict] = {}
        for _ in range(depth):
            nxt = []
            for node in frontier:
                for e in self.out[node] + self.inn[node]:
                    edges[(e["type"], e["from_label"], e["from_key"], e["to_label"], e["to_key"])] = e
                    other = (e["to_label"], e["to_key"]) if (e["from_label"], e["from_key"]) == node \
                        else (e["from_label"], e["from_key"])
                    if other not in seen and other in self.nodes:
                        seen.add(other)
                        nxt.append(other)
            frontier = nxt
        nodes = [GraphNode(label=lb, key=k, props={pk: pv for pk, pv in self.nodes[(lb, k)].items()
                                                   if pk != "embedding"})
                 for lb, k in sorted(seen)]
        return Graph(nodes=nodes, edges=[GraphEdge(**e) for _, e in sorted(edges.items())])
