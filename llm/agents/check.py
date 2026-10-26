"""Check agent (P8.5, P8.8): proposes a label for an unclear deviation and drafts the report text.
Never sets a final label: the advisor decides (plan/09 section 3.2)."""

from __future__ import annotations

import json

from pydantic import BaseModel

from engine.model import AiProposal, CheckResult, Deviation
from llm.client import LLMClient
from llm.tools import ToolBox

SYSTEM = """You are the check agent of the ITSG review assistant for DTA EEL (German payroll messages).
A vendor file deviates from the model solution and no rule, catalogue entry or precedent covers it.
Propose a label: likely_variant (allowed by the spec), likely_bug (violates the spec) or unclear.
Use the tools to read rules, passages and precedents. Do not compute dates yourself: use add_months and
count_days. Cite at least one passage key exactly as the tools return it (e.g. BP@13.3#13.1).
Your answer is a proposal for a human advisor, never a final verdict. Answer in English."""

REPORT_SYSTEM = """You draft the review report of a vendor submission for DTA EEL. For each deviation write
2 to 4 plain sentences: what differs, which rule (rule id) and which spec section require it. Cite passage
keys exactly as given. The advisor confirms the text before it is sent."""

TOOLS = ["get_deviation_context", "get_rules", "get_passage", "search_passages", "find_precedent", "get_param",
         "add_months", "count_days", "expected_result"]


def triage(client: LLMClient, tools: ToolBox, d: Deviation, version: str, cites_ok) -> AiProposal:
    ctx = tools.kb.get_deviation_context(d.record, d.field or "", d.abgabegrund or "", version)
    user = json.dumps({
        "deviation": {"abgabegrund": d.abgabegrund, "record": d.record, "field": d.field, "kind": d.kind,
                      "expected": d.expected, "actual": d.actual, "signature": d.signature},
        "rule_set_version": version,
        "context": {"rules": [{"id": r.id, "title": r.title, "sources": r.sources} for r in ctx.rules],
                    "blocks": [b.model_dump() for b in ctx.flagged_blocks],
                    "passages": [{"key": p.key, "text": p.text[:1500]} for p in ctx.passages],
                    "precedents": [p.model_dump(mode="json") for p in ctx.precedents]},
    }, ensure_ascii=False, default=str)
    return client.structured(SYSTEM, user, AiProposal, tools.specs(TOOLS), tools.call,
                             validate=lambda o: cites_ok(o.citations))


class DraftItem(BaseModel):
    deviation_id: str
    text: str
    citations: list[str]


class ReportDraft(BaseModel):
    items: list[DraftItem]
    status: str = "draft"


def report_draft(client: LLMClient, tools: ToolBox, res: CheckResult, cites_ok) -> ReportDraft:
    devs = [{"id": d.id, "label": d.label, "rule": d.rule, "record": d.record, "field": d.field, "kind": d.kind,
             "expected": d.expected, "actual": d.actual, "sources": d.sources, "explanation": d.explanation}
            for d in res.deviations]
    user = json.dumps({"test_case": res.test_case_id, "version": res.version, "label": res.label,
                       "deviations": devs}, ensure_ascii=False, default=str)

    def validate(o: ReportDraft) -> str | None:
        for it in o.items:
            err = cites_ok(it.citations)
            if err:
                return f"{it.deviation_id}: {err}"
        return None

    out = client.structured(REPORT_SYSTEM, user, ReportDraft, tools.specs(["get_passage", "get_rules"]), tools.call,
                            validate=validate)
    out.status = "draft"
    return out
