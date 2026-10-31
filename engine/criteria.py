"""Requirements to criteria to test cases, deterministic part.

3a measures criterion drafts against the approved rules and ITSG criteria by code (rule mapping and
parameter values), 3c scores, 4 generates draft boundary test cases. Steps 1, 2 and 3b (LLM) are in
`llm/extract.py`; `run_pipeline` wires them with an `extractor` that has `find`, `translate`, `review`.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from pydantic import BaseModel

from engine import builder
from engine.model import (
    Case,
    CriteriaScore,
    CriterionDraft,
    CriterionMatch,
    CriterionReview,
    RequirementSentence,
    Rule,
)
from kg.interface import KnowledgeBase

BASE_TEST_CASE = "peter"


class Extractor(Protocol):
    def find(self, document: str, version: str, section: str) -> list[RequirementSentence]: ...

    def translate(self, sentences: list[RequirementSentence], version: str) -> list[CriterionDraft]: ...

    def review(self, drafts: list[CriterionDraft], unfound: list[Rule], version: str) -> list[CriterionReview]: ...


def draft_id(d: CriterionDraft) -> str:
    return "crit-" + hashlib.sha1(f"{d.text}|{d.maps_to_rule}|{d.params}".encode()).hexdigest()[:10]


def itsg_rules(kb: KnowledgeBase, version: str, abgabegrund: str = "41") -> list[Rule]:
    return [r for r in kb.get_rules(abgabegrund, version) if r.criterion]


def params_ok(kb: KnowledgeBase, d: CriterionDraft, version: str) -> bool | None:
    """Every draft parameter whose name the KB knows equals the approved value (compared by code)."""
    checked = []
    for p in d.params:
        try:
            approved = kb.get_param(p.name, version=version)
        except (KeyError, LookupError):
            continue
        checked.append(_eq(approved, p.value))
    return all(checked) if checked else None


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return str(a).lower() == str(b).lower()
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


class Measured(BaseModel):
    matches: list[CriterionMatch]
    unmatched: list[CriterionDraft]
    unfound: list[str]  # rule ids of ITSG criteria no draft maps to
    params: dict[str, bool | None]  # draft id -> params_ok


def measure_exact(kb: KnowledgeBase, drafts: list[CriterionDraft], version: str) -> Measured:
    """Step 3a. A draft matches when it maps to an approved rule; parameters checked separately."""
    known = {r.id for ag in ("41", "61", "62", "01", "88") for r in kb.get_rules(ag, version)}
    crit = itsg_rules(kb, version)
    pok = {d.id: params_ok(kb, d, version) for d in drafts}
    matches, unmatched = [], []
    for r in crit:
        ds = [d for d in drafts if d.maps_to_rule == r.id]
        ok = [pok[d.id] for d in ds if pok[d.id] is not None]
        matches.append(CriterionMatch(criterion=r.criterion, rule=r.id, found=bool(ds),
                                      params_ok=all(ok) if ok else (True if ds else None),
                                      draft_ids=[d.id for d in ds], via="exact" if ds else "missing"))
    for d in drafts:
        if d.maps_to_rule is None or d.maps_to_rule not in known:
            unmatched.append(d)
    return Measured(matches=matches, unmatched=unmatched,
                    unfound=[m.rule for m in matches if not m.found], params=pok)


def score(measured: Measured, reviews: list[CriterionReview]) -> CriteriaScore:
    """Step 3c. AI `equivalent` proposals that name an unfound criterion's rule count as 'proposed by AI'."""
    matches = [m.model_copy() for m in measured.matches]
    for m in matches:
        if not m.found:
            hits = [r for r in reviews if r.proposal == "equivalent" and m.rule in r.rules]
            if hits:
                m.via, m.draft_ids = "ai", [r.draft_id for r in hits]
    exact = sum(m.via == "exact" for m in matches)
    ai = sum(m.via == "ai" for m in matches)
    missing = len(matches) - exact - ai
    pc = sum(1 for m in matches if m.via == "exact" and m.params_ok)
    new = sum(r.proposal == "new_valid" for r in reviews)
    summary = (f"ITSG criteria found: {exact} exact, {ai} proposed by AI, {missing} missing; parameters correct: "
               f"{pc}; new requirements proposed: {new}")
    return CriteriaScore(exact=exact, ai_proposed=ai, missing=missing, params_correct=pc, new_requirements=new,
                         matches=matches, summary=summary)


def generate(kb: KnowledgeBase, rules: list[str], base: str = BASE_TEST_CASE) -> list[Case]:
    """Step 4: draft boundary test cases for the rules of matched / confirmed drafts."""
    out: list[Case] = []
    for r in dict.fromkeys(rules):
        try:
            out += builder.boundaries(kb, r, base)
        except ValueError:
            continue  # no boundary generator for this rule (e.g. R41-1)
    return out


class PipelineResult(BaseModel):
    sentences: list[RequirementSentence]
    drafts: list[CriterionDraft]
    params_ok: dict[str, bool | None]
    reviews: list[CriterionReview]
    score: CriteriaScore
    test_cases: list[Case]


def run_pipeline(kb: KnowledgeBase, extractor: Extractor, document: str, version: str, section: str,
                 decided: dict[str, CriterionReview] | None = None) -> PipelineResult:
    """Steps 1 to 4. `decided`: human decisions on earlier 3b proposals by draft id (rule 4: not sent
    to the AI again)."""
    sentences = extractor.find(document, version, section)
    drafts = extractor.translate(sentences, version)
    for d in drafts:
        d.id = d.id or draft_id(d)
    m = measure_exact(kb, drafts, version)
    decided = decided or {}
    todo = [d for d in m.unmatched if d.id not in decided]
    unfound_rules = [r for r in itsg_rules(kb, version) if r.id in m.unfound]
    reviews = list(decided.values())
    if todo or unfound_rules:
        reviews += extractor.review(todo, unfound_rules, version) if todo else []
    sc = score(m, reviews)
    confirmed = [r for r in decided.values() if r.proposal in ("equivalent", "new_valid")]
    rules = [x.rule for x in sc.matches if x.via == "exact"] + [x for r in confirmed for x in r.rules]
    return PipelineResult(sentences=sentences, drafts=drafts, params_ok=m.params, reviews=reviews, score=sc,
                          test_cases=generate(kb, rules))
