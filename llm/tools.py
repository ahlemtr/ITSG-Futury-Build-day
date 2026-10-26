"""Tools the agents can call (P8.1, plan/09 section 3.3).

Knowledge graph tools = the methods of `kg/interface.py` except `add_precedent` and `subgraph`.
Engine tools = deterministic code: parse_file, expected_result, evaluate_rule, diff_submission,
add_months, count_days. The LLM never does date math itself.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from engine.builder import outcome
from engine.expected import build_chain, get_case, load_scenario
from engine.model import AuPeriod
from engine.rules import params as params_mod
from engine.rules.vorerkrankung import add_months, days, must_send_41
from kg.interface import KnowledgeBase

S, I, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
DATE = {"type": "string", "description": "ISO date YYYY-MM-DD"}


def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


SPECS = {
    "get_layout": _fn("get_layout", "Field layout of a record or data block", {"record": S, "version": S},
                      ["record", "version"]),
    "get_rules": _fn("get_rules", "Approved rules for an Abgabegrund under a spec version",
                     {"abgabegrund": S, "version": S}, ["abgabegrund", "version"]),
    "get_param": _fn("get_param", "Value of a rule parameter, by version or by validity date",
                     {"name": S, "version": S, "on_date": DATE}, ["name"]),
    "get_passage": _fn("get_passage", "Spec passage by key, e.g. VB@13.4#3.12/chaining", {"key": S}, ["key"]),
    "search_passages": _fn("search_passages", "Search spec passages", {"text": S, "k": I}, ["text"]),
    "get_versions": _fn("get_versions", "Versions of a document with valid_from", {"document": S}, ["document"]),
    "get_changes": _fn("get_changes", "Curated changes between two versions",
                       {"document": S, "old_version": S, "new_version": S, "in_scope_only": B},
                       ["document", "old_version", "new_version"]),
    "get_affected_rules": _fn("get_affected_rules", "Rules and test cases affected by changes",
                              {"changes": {"type": "array", "items": S}}, ["changes"]),
    "get_test_cases": _fn("get_test_cases", "Test cases, optionally targeting a rule",
                          {"rule_id": S, "include_hidden": B}, []),
    "get_test_case": _fn("get_test_case", "One test case with inputs and expected results per version", {"key": S},
                         ["key"]),
    "get_deviation_context": _fn("get_deviation_context", "Rules, passages, precedents and blocks for a deviation",
                                 {"record": S, "field": S, "abgabegrund": S, "version": S},
                                 ["record", "field", "abgabegrund", "version"]),
    "find_precedent": _fn("find_precedent", "Approved precedent for a deviation signature", {"signature": S},
                          ["signature"]),
    "expected_result": _fn("expected_result", "Rules engine: expected 41 decision, periods, EFZ end and chain",
                           {"test_case_id": S, "version": S}, ["test_case_id", "version"]),
    "evaluate_rule": _fn("evaluate_rule", "Evaluate a 41 rule for a test case, optionally on vendor values "
                         "{send_41, periods: [[start, end]]}",
                         {"rule_id": S, "test_case_id": S, "version": S, "vendor_values": {"type": "object"}},
                         ["rule_id", "test_case_id", "version"]),
    "parse_file": _fn("parse_file", "Parsed records and parse issues of a stored submission file",
                      {"file_id": S}, ["file_id"]),
    "diff_submission": _fn("diff_submission", "3-level diff with labels of a stored submission",
                           {"submission_id": S}, ["submission_id"]),
    "add_months": _fn("add_months", "Exact calendar month arithmetic", {"date": DATE, "n": I}, ["date", "n"]),
    "count_days": _fn("count_days", "Calendar days, both ends inclusive", {"start": DATE, "end": DATE},
                      ["start", "end"]),
}


def _d(x: str | None) -> date | None:
    return date.fromisoformat(x) if x else None


def _dump(v: Any) -> Any:
    if isinstance(v, BaseModel):
        return v.model_dump(mode="json")
    if isinstance(v, list):
        return [_dump(x) for x in v]
    return v


class ToolBox:
    def __init__(self, kb: KnowledgeBase, repo=None):
        self.kb = kb
        self.repo = repo
        self.log: list[tuple[str, dict]] = []

    def specs(self, names: list[str] | None = None) -> list[dict]:
        return [SPECS[n] for n in (names or SPECS)]

    def call(self, name: str, args: dict) -> Any:
        self.log.append((name, args))
        kb = self.kb
        if name == "get_param":
            return kb.get_param(args["name"], version=args.get("version"), on_date=_d(args.get("on_date")))
        if name == "get_passage":
            return _dump(kb.get_passage(args["key"]))
        if name == "search_passages":
            return [{"key": p.key, "heading": p.heading, "text": p.text[:1500]}
                    for p in kb.search_passages(args["text"], args.get("k", 5))]
        if name == "get_test_case":
            return _dump(kb.get_test_case(args["key"]))
        if name == "get_affected_rules":
            return _dump(kb.get_affected_rules(args["changes"]))
        if name == "get_deviation_context":
            return _dump(kb.get_deviation_context(args["record"], args["field"], args["abgabegrund"], args["version"]))
        if name == "find_precedent":
            return _dump(kb.find_precedent(args["signature"]))
        if name in ("get_layout", "get_rules", "get_versions", "get_changes", "get_test_cases"):
            return _dump(getattr(kb, name)(**args))
        if name == "add_months":
            return str(add_months(_d(args["date"]), int(args["n"])))
        if name == "count_days":
            return days(_d(args["start"]), _d(args["end"]))
        if name == "expected_result":
            sc = load_scenario(kb, args["test_case_id"])
            ch = build_chain(sc, args["version"], kb)
            return {"send_41": ch.decision.send, "periods": [[str(a.start), str(a.end)] for a in ch.decision.chain],
                    "total_days": ch.decision.total_days, "trace": ch.decision.trace.steps,
                    "efz": {k: str(v) for k, v in ch.efz.items()}, "chain": [m.abgabegrund for m in ch.messages]}
        if name == "evaluate_rule":
            return self.evaluate_rule(**args)
        if name == "parse_file":
            return self._parse_file(args["file_id"])
        if name == "diff_submission":
            res = self.repo.get_check(args["submission_id"]) if self.repo else None
            return _dump(res) if res else {"error": "no check result for this submission"}
        raise KeyError(f"unknown tool {name}")

    def evaluate_rule(self, rule_id: str, test_case_id: str, version: str, vendor_values: dict | None = None) -> dict:
        tc = get_case(self.kb, test_case_id)
        i = tc.inputs
        d = must_send_41(i.current, i.priors, i.report_date, params_mod.load(self.kb, version=version))
        steps = [s for s in d.trace.steps if s.startswith(rule_id)]
        ok = rule_id not in d.trace.failed
        if vendor_values is not None:
            sent = bool(vendor_values.get("send_41"))
            exp = outcome(self.kb, tc, version)
            if sent != exp.send_41:
                ok = False
                steps.append(f"vendor send_41={sent}, engine {exp.send_41}")
            periods = [tuple(_d(x) for x in p) for p in vendor_values.get("periods", [])]
            if rule_id == "R41-3" and exp.send_41 and periods and exp.periods[-1] not in periods:
                ok = False
                steps.append(f"oldest chained period {exp.periods[-1]} missing")
        return {"rule": rule_id, "ok": ok, "trace": steps, "values": d.trace.values}

    def _parse_file(self, file_id: str) -> dict:
        from pathlib import Path

        from engine.records import parse_file

        sid, _, name = file_id.partition("/")
        sub = self.repo.get_submission(sid) if self.repo else None
        f = next((f for f in sub.files if f.name == name), None) if sub else None
        if f is None:
            return {"error": "file not found; use <submission_id>/<file name>"}
        pf = parse_file(Path(f.path).read_bytes(), self.kb)
        return {"messages": [{"abgabegrund": m.abgabegrund, "values": {k: str(v) for k, v in m.values().items()
                                                                       if v not in (None, "")}}
                             for m in pf.messages], "issues": [i.model_dump() for i in pf.issues]}


def period(start: str, end: str) -> AuPeriod:
    return AuPeriod(start=_d(start), end=_d(end))
