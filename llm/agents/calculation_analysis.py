"""Calculation analysis (SPEC_UPDATE_WORKFLOW.md W8): for one change of a new edition of the insurers' Rundschreiben,
find the calculation rules it sets (amounts, percentages, periods, thresholds). The model only answers; kg.ingest
validates and writes. Rules the engine does not compute are stored as drafts ("needs implementation"); a value
that matches an engine parameter is a proposal for ITSG, never applied by itself."""

from __future__ import annotations

import json

from pydantic import BaseModel

from llm.client import LLMClient
from llm.tools import ToolBox

SYSTEM = """You are the calculation-analysis agent of the ITSG review assistant for DTA EEL (income replacement
benefits). A new edition of a Gemeinsames Rundschreiben of the GKV-Spitzenverband was uploaded. You get one change
(old and new text), the engine's parameters with their current values and the message types (Abgabegruende).
- is_calculation: true only if the new text sets or changes how a benefit, a period, an amount, a percentage or a
  threshold is calculated (e.g. Krankengeld 70 % of the Regelentgelt, at most 90 % of the net pay, 78 weeks,
  six weeks of Entgeltfortzahlung)
- summary: one sentence, what changed (quote the changed words)
- rules: each calculation rule in the new text: a short title, the rule in one sentence, the value with its unit,
  the message types it concerns (from the given list) and, only if it is the same quantity as one of the given
  parameters, that parameter's name and the value in the parameter's unit and type
- citations: passage keys exactly as given (use get_passage to read them)
Never compute amounts or dates yourself; never invent parameters."""

TOOLS = ["get_passage", "search_passages", "get_param"]


class CalculationRule(BaseModel):
    title: str
    rule: str
    value: str
    applies_to: list[str]
    parameter: str | None = None
    parameter_value: bool | int | float | str | None = None


class CalculationAnalysis(BaseModel):
    is_calculation: bool
    summary: str
    rules: list[CalculationRule] = []
    citations: list[str]


def run(client: LLMClient, tools: ToolBox, change: dict, params: dict[str, dict], message_types: list[str],
        cites_ok) -> CalculationAnalysis:
    user = json.dumps({"change": change, "parameters": params, "message_types": message_types},
                      ensure_ascii=False, default=str)

    def validate(o: CalculationAnalysis) -> str | None:
        err = cites_ok(o.citations)
        if err:
            return err
        for r in o.rules:
            bad = [m for m in r.applies_to if m not in message_types]
            if bad or not r.applies_to:
                return f"{r.title}: applies_to must be message types from {message_types}"
            if r.parameter is not None:
                if r.parameter not in params:
                    return f"unknown parameter {r.parameter}; allowed: {sorted(params)}"
                current = params[r.parameter]["value"]
                if type(r.parameter_value) is not type(current):
                    return f"{r.parameter}: value must be {type(current).__name__} like {current!r}"
        return None

    return client.structured(SYSTEM, user, CalculationAnalysis, tools.specs(TOOLS), tools.call, validate=validate)
