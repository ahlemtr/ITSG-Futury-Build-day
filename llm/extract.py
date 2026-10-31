"""Requirements to criteria, LLM part.

1. find: requirement sentences of a spec section, each with passage key and a verified quote
2. translate: one testable `CriterionDraft` per requirement, with parameters and rule mapping
3b. review: for drafts the code could not match, propose equivalent / new_valid / wrong / unclear
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from engine.model import CriterionDraft, CriterionReview, RequirementSentence, Rule
from llm.client import LLMClient
from llm.tools import ToolBox

FIND = """You read a section of a German spec for payroll messages (DTA EEL) and list every requirement
sentence: a sentence that obliges the employer's software to do or not do something. Use search_passages and
get_passage to read the section (passage keys like VB@13.4#3.12/conditions). For each requirement give the
passage key and an exact quote (copied verbatim, German). Do not paraphrase in the quote."""

TRANSLATE = """Translate each requirement sentence into one testable criterion in the style of the ITSG
criteria (English or German, one sentence, starting like "The system ensures that ..."). Give:
applies_to (Abgabegrund, e.g. "41"), condition (in words), params as {name, value} using these names when they
match: min_total_days, gap_months, gap_inclusive, sum_window_months, open_end_days, efz_days (else a new
snake_case name), maps_to_rule (one approved rule id from get_rules if it describes exactly that rule, else
null) and citations (passage keys). Never compute dates; use add_months / count_days if needed."""

REVIEW = """Some criterion drafts could not be matched to an approved rule by code, and some ITSG criteria were
not found. For each unmatched draft propose: equivalent (same requirement as an approved rule or ITSG criterion,
other wording, split or merged; list the rule ids in `rules`), new_valid (a real requirement of the cited passage
that no ITSG criterion covers), wrong (contradicts its cited passage) or unclear. Parameter values are compared
by code, never by you: do not accept a different value as equivalent. Cite passage keys. This is a proposal for
a human, never final."""


class Found(BaseModel):
    sentences: list[RequirementSentence]


class Translated(BaseModel):
    drafts: list[CriterionDraft]


class Reviewed(BaseModel):
    reviews: list[CriterionReview]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("­", "")).strip().lower()


class LLMExtractor:
    def __init__(self, client: LLMClient, tools: ToolBox, cites_ok):
        self.client, self.tools, self.cites_ok = client, tools, cites_ok

    def find(self, document: str, version: str, section: str) -> list[RequirementSentence]:
        kb = self.tools.kb

        def validate(o: Found) -> str | None:
            if not o.sentences:
                return "no requirement sentences"
            for s in o.sentences:
                try:
                    text = kb.get_passage(s.passage_key).text
                except KeyError:
                    return f"unknown passage key {s.passage_key}"
                if _norm(s.quote)[:60] not in _norm(text):
                    return f"quote not found verbatim in {s.passage_key}: {s.quote[:60]}"
            return None

        user = json.dumps({"document": document, "version": version, "section": section})
        return self.client.structured(FIND, user, Found, self.tools.specs(["search_passages", "get_passage"]),
                                      self.tools.call, validate=validate).sentences

    def translate(self, sentences: list[RequirementSentence], version: str) -> list[CriterionDraft]:
        def validate(o: Translated) -> str | None:
            if not o.drafts:
                return "no drafts"
            for d in o.drafts:
                err = self.cites_ok(d.citations)
                if err:
                    return f"draft '{d.text[:50]}': {err}"
            return None

        user = json.dumps({"version": version, "sentences": [s.model_dump() for s in sentences]}, ensure_ascii=False)
        tools = self.tools.specs(["get_rules", "get_param", "add_months", "count_days"])
        return self.client.structured(TRANSLATE, user, Translated, tools, self.tools.call, validate=validate).drafts

    def review(self, drafts: list[CriterionDraft], unfound: list[Rule], version: str) -> list[CriterionReview]:
        kb = self.tools.kb
        crit = [{"rule": r.id, "criterion": r.criterion, "title": r.title} for ag in ("41",)
                for r in kb.get_rules(ag, version)]
        user = json.dumps({"version": version, "drafts": [d.model_dump() for d in drafts],
                           "unfound_itsg_criteria": [r.id for r in unfound], "approved_rules": crit,
                           "passages": {k: kb.get_passage(k).text[:1500] for d in drafts for k in d.citations
                                        if _exists(kb, k)}}, ensure_ascii=False)

        def validate(o: Reviewed) -> str | None:
            for r in o.reviews:
                err = self.cites_ok(r.citations)
                if err:
                    return f"review {r.draft_id}: {err}"
            return None

        tools = self.tools.specs(["get_passage", "get_rules", "add_months", "count_days"])
        return self.client.structured(REVIEW, user, Reviewed, tools, self.tools.call, validate=validate).reviews


def _exists(kb, key: str) -> bool:
    try:
        kb.get_passage(key)
        return True
    except KeyError:
        return False
