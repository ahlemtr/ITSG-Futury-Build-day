"""Resolve source statements without conflating technical structure and commentary.

M is the unconditional case of m. Different markers describe requirement scope;
they do not, by themselves, prove contradictory rules. Conditions remain quoted
source evidence, not inferred executable predicates.
"""

from __future__ import annotations

from kg.common import to_date


def add_definitions(g, seed) -> None:
    """Source-qualified statements; logical Field identities are shared, evidence is never overwritten."""
    import json

    docs = {f"{d['doc']}@{d['version']}": d for d in seed.documents}
    statements = []
    for p in seed.passages:
        if not p.get("definition"):
            continue
        d = p["definition"]
        dv = f"{p['doc']}@{p['version']}"
        doc = docs[dv]
        record = d["record"]
        field = p.get("field") or f"{record}.POS-{d['start']:03d}"
        g.nodes[("Passage", p["key"])]["field"] = field
        if not g.has("Record", record):
            g.node("Record", record, title=record, section=p["section"].split(".f")[0],
                   fixed_length=0, status="extracted", knowledge_only=True)
        if not g.has("Field", field):
            g.node("Field", field, record=record, name=field.split(".", 1)[1],
                   layout_name=d["source_name"], start=d["start"], end=d["end"], length=d["length"],
                   type=d["type"], required=d["required"], status="extracted", compare_mode="ignore",
                   order=d["start"], repeating=False, knowledge_only=True)
        props = dict(d, field=field, document_version=dv, doc=p["doc"], version=p["version"],
                     role=doc.get("role", "reference"), published=doc.get("published"),
                     valid_from=doc.get("valid_from"), page=p["page"],
                     requirement_kind="unconditional" if d["required"] == "M" else "conditional",
                     condition_status="unconditional" if d["required"] == "M" else "source_prose",
                     condition_text=d["explanation"] if d["required"] == "m" else "")
        g.node("FieldDefinition", p["key"], **props)
        g.edge("HAS_DEFINITION", "DocVersion", dv, "FieldDefinition", p["key"])
        g.edge("DEFINES", "FieldDefinition", p["key"], "Field", field)
        g.edge("SOURCED_FROM", "FieldDefinition", p["key"], "Passage", p["key"])
        g.edge("DESCRIBED_IN", "Field", field, "Passage", p["key"])
        g.edge("DESCRIBED_IN", "Record", record, "Passage", p["key"])
        # Block introductions can narrow a row, e.g. DBNA change marker must be blank in EEL.
        context = p["key"].split(".f", 1)[0]
        if g.has("Passage", context):
            g.edge("IN_CONTEXT", "FieldDefinition", p["key"], "Passage", context)
        statements.append((p["key"], props))
    by_field = {}
    for key, d in statements:
        by_field.setdefault(d["field"], []).append((key, d))
    for rows in by_field.values():
        technical = [(k, d) for k, d in rows if d["role"] == "record_layout"]
        for key, d in rows:
            if d["role"] != "commentary":
                continue
            active = applicable_documents(seed.documents, d["version"]) if d["doc"] == "VB" else set()
            for tk, t in technical:
                if t["document_version"] not in active:
                    continue
                differences = {prop: {"technical": t[prop], "commentary": d[prop],
                                      "classification": classify(prop, t[prop], d[prop])}
                               for prop in ("type", "required", "length") if t[prop] != d[prop]}
                g.edge("COMPLEMENTS", "FieldDefinition", key, "FieldDefinition", tk,
                       differences=json.dumps(differences, ensure_ascii=False),
                       automatic_conflict=False, assessment="scope_comparison")


def classify(property_: str, technical, commentary) -> str:
    if technical == commentary:
        return "same"
    if property_ == "required" and {technical, commentary} == {"M", "m"}:
        return "requirement_scope"
    if property_ == "type" and {technical, commentary} == {"an", "n"}:
        return "representation_scope"
    return "structure_difference"


def applicable_documents(documents: list[dict], version: str | None = None, on_date=None) -> set[str]:
    """One revision per document family as of the requested rule set's effective date.

    A revision may be published after valid_from (retroactive corrections). Document
    families have independent version numbers; never compare them numerically.
    """
    if on_date is None and version is None:
        return {f"{d['doc']}@{d['version']}" for d in documents}
    if on_date is None:
        base = next(d for d in documents if d["doc"] == "VB" and d["version"] == version)
        on_date = base["valid_from"]
    day = to_date(on_date)
    best = {}
    ranks = {}
    for d in documents:
        if d["doc"] == "VB" and version is not None:
            if d["version"] == version:
                best["VB"] = d
            continue
        valid = to_date(d.get("valid_from"))
        if valid and valid > day:
            continue
        rank = (str(d.get("valid_from") or ""), str(d.get("published") or ""), d["version"])
        if d["doc"] not in ranks or rank > ranks[d["doc"]]:
            best[d["doc"]] = d
            ranks[d["doc"]] = rank
    return {f"{d['doc']}@{d['version']}" for d in best.values()}


def resolve_fields(fields: list[dict], definitions: list[dict], documents: list[dict], version: str,
                   on_date=None) -> list[dict]:
    """Executable metadata follows an applicable technical definition of the same field span.

    Commentary and older technical statements are still accessible in the graph.
    An unmatched span is never silently spliced into a parser layout.
    """
    active = applicable_documents(documents, version, on_date)
    selected = {}
    for d in definitions:
        if d["document_version"] not in active or d.get("role") != "record_layout":
            continue
        key = d.get("field")
        rank = (str(d.get("valid_from") or ""), str(d.get("published") or ""))
        if key and (key not in selected or rank > selected[key][0]):
            selected[key] = (rank, d)
    out = []
    for f in fields:
        f = dict(f)
        entry = selected.get(f["key"])
        if entry:
            d = entry[1]
            if (f["start"], f["end"], f["length"]) != (d["start"], d["end"], d["length"]):
                raise ValueError(f"{f['key']}: technical field span needs layout migration ({d['key']})")
            f.update(type=d["type"], required=d["required"], definition_source=d["key"])
        out.append(f)
    return out
