"""Spec-update agent (P8.7): per curated change, decide no_change / update_test / new_test and draft
the test case. Output is stored as draft; ITSG approves before use."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from llm.client import LLMClient
from llm.tools import ToolBox

SYSTEM = """You are the spec-update agent of the ITSG review assistant for DTA EEL.
A new version of the Verfahrensbeschreibung was published. For each in-scope change, use the tools:
get_changes, get_affected_rules, get_test_cases, expected_result (compare the expected result of each
affected test case under the old and the new version). Decide per affected test case:
no_change (expected result identical), update_test (expected result differs) or new_test (the change needs a
test no existing case covers). Never compute dates yourself. Cite passage keys exactly (e.g.
VB@13.4#3.12/chaining). Your output is a draft for human approval."""

TOOLS = ["get_changes", "get_affected_rules", "get_test_cases", "get_test_case", "expected_result", "get_passage",
         "get_param", "add_months", "count_days"]


class TestDecision(BaseModel):
    change_key: str
    test_case_id: str | None = None
    decision: Literal["no_change", "update_test", "new_test"]
    test_case_draft: dict | None = None
    reasoning: str
    citations: list[str]


class SpecUpdate(BaseModel):
    decisions: list[TestDecision]
    status: str = "draft"


def run(client: LLMClient, tools: ToolBox, document: str, old: str, new: str, cites_ok) -> SpecUpdate:
    user = json.dumps({"document": document, "old_version": old, "new_version": new})

    def validate(o: SpecUpdate) -> str | None:
        if not o.decisions:
            return "no decisions"
        for d in o.decisions:
            err = cites_ok(d.citations)
            if err:
                return f"{d.change_key}/{d.test_case_id}: {err}"
        return None

    out = client.structured(SYSTEM, user, SpecUpdate, tools.specs(TOOLS), tools.call, validate=validate)
    out.status = "draft"
    return out
