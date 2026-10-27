"""Step K9.2: validate the in-memory graph before loading (08 section 12.2). Errors stop the build."""

from __future__ import annotations

import re
from collections import defaultdict

from kg.extract import check_3_12

KEY_FORMATS = {
    "Document": r"[A-Z][A-Z0-9]*(-[A-Z0-9]+)*",
    "DocVersion": r"[A-Z][A-Z0-9-]*@[A-Za-z0-9.-]+",
    "Passage": r"[A-Z][A-Z0-9-]*@[A-Za-z0-9.-]+#[A-Za-z0-9.-]+(/[a-z_]+)?",
    "Record": r"D[A-Z]{3}",
    "Field": r"D[A-Z]{3}\.[A-Z0-9][A-Z0-9-]*",
    "MessageType": r"\d{2}",
    "Rule": r"(R41|F41|K61|K62)-\d+|[EC]-\d+",
    "Criterion": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "Parameter": r"[a-z][a-z0-9_]*",
    "ParamValue": r"[a-z][a-z0-9_]*@(\d+\.\d+|sim-\d+\.\d+)",
    "Change": r"[A-Z]+-\d+\.\d+-\d+\.\d+-(\d{3}|[A-Za-z0-9-]+)",
    "TestCase": r"[a-z0-9]+(-[a-z0-9]+)*",
    "Precedent": r"\d{2}\|D[A-Z]{3}\.[A-Z0-9][A-Z0-9-]*\|[a-z_]+",
}

DEVIATION_KINDS = {"value_differs", "missing_block", "extra_block", "missing_message", "extra_message",
                   "missing_group", "extra_group", "order_differs"}

# (label, property) -> allowed values (08 section 1.4)
ENUMS = {
    ("Rule", "kind"): {"domain", "format", "reply", "chain", "efz"},
    ("Rule", "status"): {"approved", "draft"},
    ("MessageType", "sender"): {"employer", "insurer", "both"},
    ("Field", "type"): {"an", "n"},
    ("Field", "required"): {"M", "m"},
    ("Field", "compare_mode"): {"compare", "rule", "ignore"},
    ("Field", "status"): {"extracted", "inferred", "partial", "missing"},
    ("Record", "status"): {"extracted", "inferred", "partial", "missing"},
    ("TestCase", "kind"): {"reference", "clone", "hidden"},
    ("TestCase", "origin"): {"itsg", "beispielpapier", "builder", "pta"},
    ("TestCase", "status"): {"draft", "approved", "rejected"},
    ("Change", "tag"): {"replace", "insert", "delete"},
    ("Change", "label"): {"editorial", "clarification", "law_change", "unknown"},
    ("Precedent", "verdict"): {"correct_variant", "bug", "invalid"},
    ("Precedent", "kind"): DEVIATION_KINDS,
}
EDGE_ENUMS = {("USES_BLOCK", "mandatory"): {True, False, "unknown"}}


def validate(graph: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = list(graph.get("warnings", []))
    nodes = {(n["label"], n["key"]): n["props"] for n in graph["nodes"]}
    out_edges: dict[tuple[str, str], list[dict]] = defaultdict(list)
    in_edges: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in graph["edges"]:
        out_edges[(e["from_label"], e["from_key"])].append(e)
        in_edges[(e["to_label"], e["to_key"])].append(e)

    # every field a rule constrains exists in a layout (named error, before the generic edge check)
    for e in graph["edges"]:
        if e["type"] == "CONSTRAINS" and ("Field", e["to_key"]) not in nodes:
            errors.append(f"rule {e['from_key']} constrains field {e['to_key']}, which is in no layout")

    # every edge's from and to node exists
    for e in graph["edges"]:
        for side in ("from", "to"):
            if (e[f"{side}_label"], e[f"{side}_key"]) not in nodes and not (e["type"] == "CONSTRAINS" and side == "to"):
                errors.append(f"edge {e['type']} {e['from_label']} {e['from_key']} -> {e['to_label']} {e['to_key']}: "
                              f"{side} node missing")

    # key formats and enums
    for (label, key), props in nodes.items():
        fmt = KEY_FORMATS.get(label)
        if fmt is None:
            errors.append(f"{label} {key}: label not in the schema")
        elif not re.fullmatch(fmt, key):
            errors.append(f"{label} {key!r}: key does not match format {fmt}")
        for (lb, prop), allowed in ENUMS.items():
            if lb == label and props.get(prop) not in allowed:
                errors.append(f"{label} {key}: {prop} = {props.get(prop)!r} not in {sorted(map(str, allowed))}")
    for e in graph["edges"]:
        for (t, prop), allowed in EDGE_ENUMS.items():
            if e["type"] == t and e["props"].get(prop) not in allowed:
                errors.append(f"edge {t} {e['from_key']} -> {e['to_key']}: {prop} = {e['props'].get(prop)!r}")

    # rules: at least one source and one message type
    for (label, key) in nodes:
        if label != "Rule":
            continue
        types = {e["type"] for e in out_edges[(label, key)]}
        if "SOURCED_FROM" not in types:
            errors.append(f"rule {key}: no SOURCED_FROM")
        if "APPLIES_TO" not in types:
            errors.append(f"rule {key}: no APPLIES_TO")

    # parameters: a value for every loaded VB version (13.3 and 13.4; 13.3 only at the demo start)
    vb_versions = sorted(props["version"] for (label, _key), props in nodes.items()
                         if label == "DocVersion" and props.get("doc") == "VB")
    for (label, key) in nodes:
        if label != "Parameter":
            continue
        versions = {nodes[("ParamValue", e["to_key"])]["version"] for e in out_edges[(label, key)]
                    if e["type"] == "HAS_VALUE" and ("ParamValue", e["to_key"]) in nodes}
        for v in vb_versions:
            if v not in versions:
                errors.append(f"parameter {key}: no value for {v}")

    # test cases target at least one rule, except official PTA tasks without a solution
    for (label, key), props in nodes.items():
        if (label == "TestCase" and props.get("origin") != "pta"
                and not any(e["type"] == "TARGETS" for e in out_edges[(label, key)])):
            errors.append(f"test case {key}: targets no rule")

    # passage keys resolve to a DocVersion
    for (label, key), props in nodes.items():
        if label == "Passage":
            head = key.split("#", 1)[0]
            if ("DocVersion", head) not in nodes:
                errors.append(f"passage {key}: DocVersion {head} not loaded")
            if not props.get("text"):
                warnings.append(f"passage {key}: empty text")

    # the 3.12 checks of section 5.2
    passages = {k: {"text": p.get("text", "")} for (lb, k), p in nodes.items() if lb == "Passage"}
    errors += [f"3.12 check: {m}" for m in check_3_12(passages)]

    # in-scope changes reach at least one rule
    rules_by_param = {e["to_key"] for e in graph["edges"] if e["type"] == "USES_PARAM"}
    cited = {e["to_key"] for e in graph["edges"] if e["type"] == "SOURCED_FROM"}
    for (label, key), props in nodes.items():
        if label == "Change" and props.get("in_scope"):
            reach = [e for e in out_edges[(label, key)]
                     if (e["type"] == "CHANGES_PARAM" and e["to_key"] in rules_by_param)
                     or (e["type"] in ("MODIFIES_OLD", "MODIFIES_NEW") and e["to_key"] in cited)]
            if not reach:
                warnings.append(f"in-scope change {key} reaches no rule")
    return errors, warnings


def report(errors: list[str], warnings: list[str], max_warnings: int = 40) -> None:
    empty = [w for w in warnings if w.endswith(": empty text")]
    other = [w for w in warnings if not w.endswith(": empty text")]
    for w in other[:max_warnings]:
        print(f"WARNING: {w}")
    if len(other) > max_warnings:
        print(f"WARNING: ... {len(other) - max_warnings} more")
    if empty:
        print(f"WARNING: {len(empty)} passages with empty text (chapter headings followed by a sub-section)")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"validation: {len(errors)} errors, {len(warnings)} warnings")
