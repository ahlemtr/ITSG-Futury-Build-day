"""Explain (P8.3): a fail verdict in 2 to 4 plain sentences, quoting rule id and section."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from engine.model import Deviation, Passage
from llm.client import LLMClient

SYSTEM = """Explain a failed check of a DTA EEL vendor file to a payroll software developer in 2 to 4 plain
sentences (English). You must name the rule id and the spec section number given to you. Use only the facts
given; do not compute dates."""


class Explanation(BaseModel):
    text: str


def sections(sources: list[str]) -> list[str]:
    """`VB@13.4#3.12/chaining` -> `3.12`."""
    out = []
    for s in sources:
        m = re.match(r"^[A-Z0-9-]+@[^#]+#([^/]+)", s)
        if m:
            out.append(m.group(1))
    return out


def explain(client: LLMClient, d: Deviation, passage: Passage | None) -> str:
    secs = sections(d.sources)
    user = json.dumps({"rule": d.rule, "label": d.label, "record": d.record, "field": d.field, "kind": d.kind,
                       "expected": d.expected, "actual": d.actual, "engine_explanation": d.explanation,
                       "sections": secs, "passage": passage.text[:1500] if passage else None},
                      ensure_ascii=False, default=str)

    def validate(o: Explanation) -> str | None:
        n = len(re.findall(r"[.!?](\s|$)", o.text.strip()))
        if d.rule and d.rule not in o.text:
            return f"the text must name rule {d.rule}"
        if secs and not any(s in o.text for s in secs):
            return f"the text must name section {secs[0]}"
        if not 2 <= n <= 4:
            return "2 to 4 sentences"
        return None

    return client.structured(SYSTEM, user, Explanation, validate=validate).text
