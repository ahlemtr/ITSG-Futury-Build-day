"""Step K9.1: seed + layouts + passages + diff -> nodes and edges in memory (08 section 12.1)."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

import yaml

from kg.chunks import passage_chunks
from kg.common import (
    BUILD_DIR,
    LAYOUT_DIR,
    OPTIONAL_DOCS,
    ROOT,
    SEED_DIR,
    env,
    field_key,
    layout_fields,
    load_documents,
    load_layouts,
    load_yaml,
    passage_doc_version,
)
from kg.extract.pdf_text import join_strings

DIFF_FILE = "spec_diff_13.3_13.4.json"
# 08 section 10: a raw change line is matched by its first 40 characters; shorter needles
# (page numbers like "50") match everywhere and fall back to the block passage instead
MATCH_CHARS = 40
MIN_NEEDLE = 15


def jsonable(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def to_json(value) -> str:
    return json.dumps(jsonable(value), ensure_ascii=False)


def load_passages(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `python -m kg.build --skip-load --skip-embed` first")
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=loader) or []


class GraphBuilder:
    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str], dict] = {}
        self.edges: dict[tuple[str, str, str, str, str], dict] = {}
        self.warnings: list[str] = []

    # positional-only: Change nodes have a `label` property, edges may have a `type`
    def node(self, label: str, key: str, /, **props) -> None:
        self.nodes[(label, key)] = {k: jsonable(v) for k, v in props.items()}

    def edge(self, type_: str, from_label: str, from_key: str, to_label: str, to_key: str, /, **props) -> None:
        self.edges[(type_, from_label, from_key, to_label, to_key)] = {k: jsonable(v) for k, v in props.items()}

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def has(self, label: str, key: str) -> bool:
        return (label, key) in self.nodes

    def result(self) -> dict:
        return {
            "nodes": [{"label": lb, "key": k, "props": p} for (lb, k), p in self.nodes.items()],
            "edges": [
                {"type": t, "from_label": fl, "from_key": fk, "to_label": tl, "to_key": tk, "props": p}
                for (t, fl, fk, tl, tk), p in self.edges.items()
            ],
            "warnings": self.warnings,
        }


def _expand(sources: list[str], vb_versions: list[str]) -> list[str]:
    """'VB@V#3.12' -> both VB versions (08 section 9.2 shorthand)."""
    out = []
    for s in sources:
        if s.startswith("VB@V#"):
            out += [s.replace("VB@V#", f"VB@{v}#", 1) for v in vb_versions]
        else:
            out.append(s)
    return out


class Seed:
    """Everything the build reads, so the YAML backend can reuse it."""

    def __init__(self, seed_dir: Path, layout_dir: Path, passages_path: Path):
        self.seed_dir = seed_dir
        self.documents = load_documents(seed_dir)
        self.layouts = load_layouts(layout_dir)
        self.passages = load_passages(passages_path)
        self.message_types = load_yaml(seed_dir / "message_types.yaml")
        self.compare_modes = load_yaml(seed_dir / "compare_modes.yaml")
        self.parameters = load_yaml(seed_dir / "parameters.yaml")["parameters"]
        self.rules = load_yaml(seed_dir / "rules.yaml")["rules"]
        self.changes = load_yaml(seed_dir / "changes.yaml")
        self.test_cases = load_yaml(seed_dir / "test_cases.yaml")["test_cases"]
        self.precedents = load_yaml(seed_dir / "precedents.yaml") or []
        with open(seed_dir / DIFF_FILE, encoding="utf-8") as f:
            self.diff = json.load(f)
        self.extra_changes: list[tuple[dict, list]] = []  # change sets of uploaded versions
        baseline = env("SPEC_BASELINE", "")
        if baseline:
            start_from_baseline(self, baseline, (env("BASELINE_TEST_CASES", "peter") or "peter").split(","))
            load_overlays(self, ingested_dir())


def ingested_dir() -> Path:
    """Where the spec upload writes what it learned (one folder per uploaded document version)."""
    data = Path(env("DATA_DIR", "data") or "data")
    return (data if data.is_absolute() else ROOT / data) / "ingested"


def load_overlays(seed: Seed, folder: Path) -> None:
    """Add every uploaded version (in valid-from order): document, passages, raw diff and curated changes,
    parameter values, expected results of test cases. Written by kg.ingest."""
    if not folder.exists():
        return
    found = []
    for d in folder.iterdir():
        if (d / "document.yaml").exists():
            found.append((load_yaml(d / "document.yaml"), d))
    for doc, d in sorted(found, key=lambda x: str(x[0]["valid_from"])):
        seed.documents.append({**doc, "present": True})
        seed.passages += load_yaml(d / "passages.yaml") or []
        values = (load_yaml(d / "parameters.yaml") or []) if (d / "parameters.yaml").exists() else []
        for v in values:
            prm = next((p for p in seed.parameters if p["name"] == v["name"]), None)
            if prm is not None:
                prm["values"] = [x for x in prm["values"] if str(x["version"]) != str(v["version"])] + [
                    {k: v[k] for k in ("version", "valid_from", "value")}]
        if (d / "changes.yaml").exists():
            with open(d / "diff.json", encoding="utf-8") as f:
                seed.extra_changes.append((load_yaml(d / "changes.yaml"), json.load(f)))
        if (d / "expected.yaml").exists():
            expected = load_yaml(d / "expected.yaml") or {}
            for tc in seed.test_cases:
                if tc["id"] in expected:
                    tc.setdefault("expected", {})[str(doc["version"])] = expected[tc["id"]]


def start_from_baseline(seed: Seed, baseline: str, test_cases: list[str]) -> None:
    """The platform's starting point: the document up to the baseline version (SPEC_BASELINE=VB@13.3), newer
    versions arrive through the spec upload. Newer versions leave with their passages, curated changes,
    parameter values and expectations; references to them fall back to the same section of the baseline.
    Only the given test cases are kept (Peter from the Hinweise document)."""
    doc, version = baseline.split("@")
    base = next(d for d in seed.documents if d["doc"] == doc and d["version"] == version)
    newer = {d["version"] for d in seed.documents
             if d["doc"] == doc and d["version"] != version and str(d["valid_from"]) > str(base["valid_from"])}
    seed.documents = [d for d in seed.documents if not (d["doc"] == doc and d["version"] in newer)]
    hidden = tuple(f"{doc}@{v}#" for v in newer)
    seed.passages = [p for p in seed.passages if not p["key"].startswith(hidden)] if hidden else seed.passages
    present = {p["key"] for p in seed.passages}

    def sources(keys: list[str] | None) -> list[str]:
        out = []
        for k in keys or []:
            if k and hidden and k.startswith(hidden):
                k = f"{baseline}#{k.split('#', 1)[1]}"
                if k not in present:
                    continue
            if k not in out:
                out.append(k)
        return out

    for prm in seed.parameters:
        prm["values"] = [v for v in prm["values"] if str(v["version"]) not in newer]
        prm["sources"] = sources(prm.get("sources"))
    for r in seed.rules:
        r["sources"] = sources(r.get("sources"))
    for mode in ("ignore", "rule"):
        for entry in seed.compare_modes.get(mode) or []:
            if entry.get("source"):
                entry["source"] = (sources([entry["source"]]) or [None])[0]
    seed.test_cases = [tc for tc in seed.test_cases if tc["id"] in test_cases]
    for tc in seed.test_cases:
        tc["expected"] = {v: e for v, e in (tc.get("expected") or {}).items() if str(v) not in newer}
        tc["sources"] = sources(tc.get("sources"))
    if str(seed.changes.get("new_version")) in newer:
        seed.changes = {}
        seed.diff = []
    seed.precedents = []


def build(seed_dir: Path = SEED_DIR, layout_dir: Path = LAYOUT_DIR,
          passages_path: Path = BUILD_DIR / "passages.yaml") -> dict:
    return build_from(Seed(seed_dir, layout_dir, passages_path))


def build_from(seed: Seed) -> dict:
    g = GraphBuilder()
    vb_versions = [d["version"] for d in seed.documents if d["doc"] == "VB"]
    present_docs = {f"{d['doc']}@{d['version']}" for d in seed.documents if d["present"]}

    def passage_edge(type_: str, from_label: str, from_key: str, key: str, **props) -> None:
        """Edge to a passage; optional sources whose file is missing are dropped with a warning."""
        doc, version = passage_doc_version(key)
        if not g.has("Passage", key) and doc in OPTIONAL_DOCS and f"{doc}@{version}" not in present_docs:
            g.warn(f"{from_label} {from_key}: optional source {key} missing (file not present), skipped")
            return
        g.edge(type_, from_label, from_key, "Passage", key, **props)

    # --- K1: documents and versions
    for d in seed.documents:
        if not d["present"] and d["doc"] not in ("VB", "GG", "PTA"):
            g.warn(f"{d['doc']}@{d['version']}: file missing, not loaded")
            continue
        g.node("Document", d["doc"], title=d["title"])
        dv = f"{d['doc']}@{d['version']}"
        g.node("DocVersion", dv, doc=d["doc"], version=d["version"], published=d["published"],
               valid_from=d["valid_from"], file=d["file"])
        g.edge("HAS_VERSION", "Document", d["doc"], "DocVersion", dv)
        if d["succeeds"]:
            g.edge("SUCCEEDS", "DocVersion", dv, "DocVersion", f"{d['doc']}@{d['succeeds']}")

    # --- K2: passages
    for p in seed.passages:
        g.node("Passage", p["key"], doc=p["doc"], version=str(p["version"]), section=str(p["section"]),
               part=p.get("part"), field=p.get("field"), heading=p.get("heading") or "", text=p.get("text") or "",
               page=p.get("page"))
        g.edge("CONTAINS", "DocVersion", f"{p['doc']}@{p['version']}", "Passage", p["key"])
        for c in passage_chunks(p):  # W7: retrieval runs on chunks, results are grouped per passage
            g.node("Chunk", c["key"], passage=p["key"], n=c["n"], heading=c["heading"], text=c["text"])
            g.edge("HAS_CHUNK", "Passage", p["key"], "Chunk", c["key"])

    # --- K3: records and fields
    field_passages: dict[str, list[str]] = {}
    for p in seed.passages:
        if p.get("field"):
            field_passages.setdefault(p["field"], []).append(p["key"])
    modes = _compare_modes(seed, g)
    for name, lay in seed.layouts.items():
        spec = lay["spec"]
        g.node("Record", name, title=lay["title"], section=str(spec["section"]), page=spec.get("page"),
               fixed_length=lay["fixed_length"], status=lay["status"])
        for v in vb_versions:
            passage_edge("DESCRIBED_IN", "Record", name, f"VB@{v}#{spec['section']}")
        for order, f in enumerate(layout_fields(lay), start=1):
            key = field_key(name, f)
            status = lay["status"]
            if name == "DSLW" and f["name"].startswith("MM-"):
                status = "inferred"  # names from the Beispielpapier
            mode = modes.get(key, {"mode": "compare"})
            g.node("Field", key, record=name, name=key.split(".", 1)[1], layout_name=f["name"],
                   start=f["start"], end=f["end"], length=f["length"], type=f["type"], required=f["required"],
                   format=f.get("format"), constant=f.get("constant"),
                   values=to_json(f["values"]) if f.get("values") else None,
                   repeating=f["repeating"], offset_in_group=f.get("offset_in_group"), status=status,
                   compare_mode=mode["mode"], compare_rule=mode.get("rule"), compare_source=mode.get("source"),
                   order=order)
            g.edge("HAS_FIELD", "Record", name, "Field", key, order=order)
            for pk in field_passages.get(key, []):
                g.edge("DESCRIBED_IN", "Field", key, "Passage", pk)
    dslw = seed.layouts.get("DSLW")
    if dslw:
        for order, block in enumerate(dslw.get("block_order", []), start=1):
            flag = seed.layouts.get(block, {}).get("announced_by", {}).get("field")
            g.edge("CARRIES", "Record", "DSLW", "Record", block, order=order, flag=flag)

    # --- K4: message types
    for mt in seed.message_types["message_types"]:
        g.node("MessageType", mt["code"], name=mt["name"], sender=mt["sender"], in_scope=mt["in_scope"])
    for b in seed.message_types["blocks"]:
        g.edge("USES_BLOCK", "MessageType", b["type"], "Record", b["record"], flag=b["flag"], mandatory=b["mandatory"])
    for code, keys in (seed.message_types.get("described_in") or {}).items():
        for k in keys:
            passage_edge("DESCRIBED_IN", "MessageType", code, k)

    # --- K6: parameters
    for prm in seed.parameters:
        g.node("Parameter", prm["name"], note=prm.get("note"))
        for v in prm["values"]:
            vk = f"{prm['name']}@{v['version']}"
            g.node("ParamValue", vk, value=v["value"], version=str(v["version"]), valid_from=v.get("valid_from"),
                   simulated=bool(v.get("simulated", False)))
            g.edge("HAS_VALUE", "Parameter", prm["name"], "ParamValue", vk)
        for s in _expand(prm.get("sources", []), vb_versions):
            passage_edge("DESCRIBED_IN", "Parameter", prm["name"], s)

    # --- K6: rules and criteria
    for order, r in enumerate(seed.rules, start=1):
        g.node("Rule", r["id"], title=r["title"], description=r.get("description", ""), kind=r["kind"],
               status=r["status"], order=order)
        for code in r.get("applies_to", []):
            g.edge("APPLIES_TO", "Rule", r["id"], "MessageType", str(code))
        for fk in r.get("fields", []):
            g.edge("CONSTRAINS", "Rule", r["id"], "Field", fk)
        for prm in r.get("params", []):
            g.edge("USES_PARAM", "Rule", r["id"], "Parameter", prm)
        for s in _expand(r.get("sources", []), vb_versions):
            passage_edge("SOURCED_FROM", "Rule", r["id"], s)
        if r.get("criterion"):
            uuid = r["criterion"].lower()
            text_key = f"BVORERK@1#{uuid[:8]}"
            text = g.nodes[("Passage", text_key)]["text"] if g.has("Passage", text_key) else r["title"]
            g.node("Criterion", uuid, text=text)
            g.edge("IMPLEMENTS", "Rule", r["id"], "Criterion", uuid)

    # --- K7: spec changes
    _changes(seed.changes, seed.diff, seed, g)
    for cur, diff in seed.extra_changes:
        _changes(cur, diff, seed, g)

    # --- K8: test cases
    for order, tc in enumerate(seed.test_cases, start=1):
        g.node("TestCase", tc["id"], kind=tc["kind"], origin=tc["origin"], status=tc["status"],
               hidden=bool(tc.get("hidden", False)), steps=tc["steps"], parent=tc.get("parent"), order=order,
               inputs=to_json(tc.get("inputs") or {}), expected=to_json(tc.get("expected") or {}))
        for rid in tc.get("targets", []):
            g.edge("TARGETS", "TestCase", tc["id"], "Rule", rid)
        if tc.get("parent"):
            if tc["kind"] == "clone":
                g.edge("CLONE_OF", "TestCase", tc["id"], "TestCase", tc["parent"])
            elif tc["kind"] == "hidden":
                g.edge("HIDDEN_OF", "TestCase", tc["id"], "TestCase", tc["parent"])
        for s in tc.get("sources", []):
            passage_edge("DESCRIBED_IN", "TestCase", tc["id"], s)

    # --- precedents (written at runtime by add_precedent)
    for p in seed.precedents:
        add_precedent_nodes(g, p)
    return g.result()


def add_precedent_nodes(g: GraphBuilder, p: dict) -> None:
    g.node("Precedent", p["key"], abgabegrund=str(p["abgabegrund"]), field=p["field"], kind=p["kind"],
           verdict=p["verdict"], reason=p.get("reason", ""), advisor=p.get("advisor"), decided=p.get("decided"))
    g.edge("ABOUT", "Precedent", p["key"], "Field", p["field"])
    for j in p.get("justified_by", []):
        g.edge("JUSTIFIED_BY", "Precedent", p["key"], "Passage" if "#" in j else "Rule", j)


def _is_date_or_flag(f: dict) -> bool:
    name = f["name"]
    return f.get("format") == "date_yyyymmdd" or name.startswith(("MM-", "KZ-")) or name.endswith("GRUND")


def _compare_modes(seed: Seed, g: GraphBuilder) -> dict[str, dict]:
    """Field key -> {mode, rule, source} (08 section 8). Unlisted fields are `compare`."""
    known = {field_key(r, f) for r, lay in seed.layouts.items() for f in layout_fields(lay)}
    out: dict[str, dict] = {}
    for mode in ("ignore", "rule"):
        for entry in seed.compare_modes.get(mode) or []:
            info = {"mode": mode, "rule": entry.get("rule"), "source": entry.get("source")}
            if "field" in entry:
                if entry["field"] not in known:
                    g.warn(f"compare_modes: unknown field {entry['field']}")
                out[entry["field"]] = info
                continue
            record = entry["record"]
            for f in layout_fields(seed.layouts[record]):
                if entry.get("all_fields_except_dates_and_flags") and _is_date_or_flag(f):
                    continue
                out[field_key(record, f)] = info
    return out


def _rank(p: dict, block_sections: set[str]) -> int:
    """Narrowest first: part > field > block > section (08 section 10 step 2)."""
    if p.get("part"):
        return 3
    if p.get("field"):
        return 2
    if str(p["section"]) in block_sections:
        return 1
    return 0


def _in_block(p: dict, section: str | None) -> bool:
    s = str(p["section"])
    return section is not None and (s == section or s.startswith(section + "."))


def _narrowest(candidates: list[dict], text: str, block_sections: set[str], block_section: str | None) -> str | None:
    """Narrowest passage holding the changed text, preferring passages of the change's own block.

    The full text is tried first, then 120 and 40 characters: 40 alone is ambiguous for the DBVO change
    ("ginn der nachgehenden Erkrankung nicht m" is in both 3.12/chaining and 3.12/insurer).
    """
    for size in (None, 120, MATCH_CHARS):
        needle = text if size is None else text[:size]
        if len(needle) < MIN_NEEDLE:
            return None
        hits = [p for p in candidates if needle in (p.get("text") or "")]
        if hits:
            hits.sort(key=lambda p: (not _in_block(p, block_section), -_rank(p, block_sections),
                                     len(p.get("text") or ""), p["key"]))
            return hits[0]["key"]
    return None


def _changes(cur: dict, diff: list, seed: Seed, g: GraphBuilder) -> None:
    """One change set: raw changes of a diff plus the curated changes on top (seed or uploaded version)."""
    if not cur:  # at the baseline: no newer version yet
        return
    doc, old_v, new_v = cur.get("document", "VB"), str(cur["old_version"]), str(cur["new_version"])
    by_version = {v: [p for p in seed.passages if p["doc"] == doc and str(p["version"]) == v] for v in (old_v, new_v)}
    block_sections = {str(lay["spec"]["section"]) for lay in seed.layouts.values()}
    raws = []
    for i, c in enumerate(diff):
        key = f"{doc}-{old_v}-{new_v}-{i:03d}"
        raw = {"key": key, "tag": c["tag"], "block": c.get("block"), "field": c.get("field"),
               "old": "\n".join(c.get("old") or []), "new": "\n".join(c.get("new") or [])}
        raws.append(raw)
        g.node("Change", key, document=doc, old_version=old_v, new_version=new_v, tag=raw["tag"],
               block=raw["block"], field=raw["field"], old=raw["old"], new=raw["new"], in_scope=False,
               label="unknown", summary=None, curated=False)
        block_section = str(seed.layouts[raw["block"]]["spec"]["section"]) if raw["block"] in seed.layouts else None
        for lines, version, rel in ((c.get("old"), old_v, "MODIFIES_OLD"), (c.get("new"), new_v, "MODIFIES_NEW")):
            if not lines:
                continue
            target = _narrowest(by_version[version], join_strings(lines), block_sections, block_section)
            if target is None and block_section:
                fallback = f"{doc}@{version}#{block_section}"
                target = fallback if g.has("Passage", fallback) else None
            if target:
                g.edge(rel, "Change", key, "Passage", target)
            else:
                g.warn(f"{key}: no passage found for the {'old' if rel == 'MODIFIES_OLD' else 'new'} text")

    for c in cur.get("changes", []):
        match = c.get("raw_match") or {}
        if c.get("raw_keys"):  # written by the spec upload: the raw changes the AI analysed
            derived = [r for r in raws if r["key"] in c["raw_keys"]]
        else:
            derived = [r for r in raws if _raw_matches(r, match)]
        if not derived:
            g.warn(f"{c['key']}: raw_match {match} found no raw change")
        first = derived[0] if derived else {}
        g.node("Change", c["key"], document=doc, old_version=old_v, new_version=new_v,
               tag=first.get("tag", "replace"), block=first.get("block"), field=first.get("field"),
               old="\n".join(r["old"] for r in derived), new="\n".join(r["new"] for r in derived),
               in_scope=bool(c.get("in_scope", False)), label=c.get("label", "unknown"), summary=c.get("summary"),
               curated=True)
        for r in derived:
            g.edge("DERIVED_FROM", "Change", c["key"], "Change", r["key"])
        for prm in c.get("changes_param") or []:
            g.edge("CHANGES_PARAM", "Change", c["key"], "Parameter", prm)
        for rel, field in (("MODIFIES_OLD", "modifies_old"), ("MODIFIES_NEW", "modifies_new")):
            for pk in c.get(field) or []:
                g.edge(rel, "Change", c["key"], "Passage", pk)


def _raw_matches(raw: dict, match: dict) -> bool:
    if "block" in match and raw["block"] != match["block"]:
        return False
    if "field_prefix" in match and not (raw["field"] or "").startswith(match["field_prefix"]):
        return False
    if "old_contains" in match and match["old_contains"] not in join_strings(raw["old"].split("\n")):
        return False
    return not ("new_contains" in match and match["new_contains"] not in join_strings(raw["new"].split("\n")))


def counts(graph: dict) -> tuple[Counter, Counter]:
    return Counter(n["label"] for n in graph["nodes"]), Counter(e["type"] for e in graph["edges"])


def print_counts(nodes: Counter, edges: Counter, title: str) -> None:
    print(f"{title}:")
    print("  nodes: " + ", ".join(f"{k} {v}" for k, v in sorted(nodes.items())) + f" (total {sum(nodes.values())})")
    print("  edges: " + ", ".join(f"{k} {v}" for k, v in sorted(edges.items())) + f" (total {sum(edges.values())})")


def write(graph: dict, build_dir: Path = BUILD_DIR) -> Path:
    path = build_dir / "graph.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=1)
    return path
