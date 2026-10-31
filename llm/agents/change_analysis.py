"""Change analysis (spec upload): for one change of a newly uploaded spec version
that touches rules, say what changed in the rules. The model only answers; kg.ingest validates the answer and
writes it into the knowledge graph. Dates and expected results always come from the rules engine."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from llm.client import LLMClient
from llm.tools import ToolBox

SYSTEM = """You are the change-analysis agent of the ITSG review assistant for DTA EEL.
A new version of a specification was uploaded. You get one change (old and new text of the same place), the rules
built on that passage with the parameters they use and the parameters' current values. Decide:
- summary: one sentence, what changed (quote the changed words)
- label: editorial (wording only, same meaning), clarification (meaning made explicit, same result), law_change
  (the rule's result can change)
- in_scope: true if the change affects one of the given rules
- param_changes: only when the new text changes the value of a given parameter; name it and give the new value in
  the type of the current value. Example: "nicht mindestens 6 Monate" -> "nicht mehr als 6 Monate" makes a gap of
  exactly 6 months chain, so gap_inclusive false -> true. Never invent parameters.
- citations: passage keys exactly as given (old and new passage), use get_passage to read them.
Never compute dates or results yourself."""

TOOLS = ["get_passage", "search_passages", "get_rules", "get_param"]


class ParamChange(BaseModel):
    name: str
    new_value: bool | int | float | str
    reason: str


class ChangeAnalysis(BaseModel):
    summary: str
    label: Literal["editorial", "clarification", "law_change"]
    in_scope: bool
    param_changes: list[ParamChange] = []
    citations: list[str]


def run(client: LLMClient, tools: ToolBox, change: dict, rules: list[dict], params: dict[str, dict],
        cites_ok) -> ChangeAnalysis:
    """`params`: name -> {"value": current value, "note": what it means}. Answers naming another parameter or a
    value of another type are rejected (retried once, then dropped)."""
    user = json.dumps({"change": change, "rules": rules, "parameters": params}, ensure_ascii=False, default=str)

    def validate(o: ChangeAnalysis) -> str | None:
        err = cites_ok(o.citations)
        if err:
            return err
        for pc in o.param_changes:
            if pc.name not in params:
                return f"unknown parameter {pc.name}; allowed: {sorted(params)}"
            current = params[pc.name]["value"]
            if type(pc.new_value) is not type(current):
                return f"{pc.name}: new value must be {type(current).__name__} like the current value {current!r}"
            if pc.new_value == current:
                return f"{pc.name}: new value equals the current value"
        return None

    return client.structured(SYSTEM, user, ChangeAnalysis, tools.specs(TOOLS), tools.call, validate=validate)
