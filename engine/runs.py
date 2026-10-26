"""Test runs in rounds (P5.7, plan/06 section 5).

`start` gives the vendor the story only. `submit` checks the round and builds the next insurer
reply from the vendor's own file (REF-ID = their DATENSATZ-ID). `verdict` returns pass / fail per
rule; for hidden tests without expected values. If a required message is missing, the rule fails
and the run ends.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel

from engine.builder import story_text
from engine.checker import Checker
from engine.expected import build_chain, load_scenario
from engine.model import ExpectedMessage, Record, TestCase
from engine.records import parse_file
from engine.rules import params as params_mod
from engine.writer_messages import write_file
from kg.interface import KnowledgeBase


class RuleOutcome(BaseModel):
    rule: str
    outcome: Literal["pass", "fail", "review"]
    message: str = ""
    expected: str | None = None
    actual: str | None = None


class RoundResult(BaseModel):
    round: int
    outcomes: list[RuleOutcome]
    reply_name: str | None = None
    reply: str | None = None  # TEEK0 text
    ended: bool = False


class RunState(BaseModel):
    id: str
    test_case: TestCase
    valid_on: date
    version: str
    round: int = 0
    last_round: int
    status: Literal["open", "passed", "failed"] = "open"
    files: list[str] = []
    rounds: list[RoundResult] = []


def _rounds(chain_msgs: list[ExpectedMessage], steps: str) -> int:
    emp = [m.round for m in chain_msgs if m.actor == "employer"]
    last = max(emp, default=1)
    ins_after = any(m.actor == "insurer" and m.round == last for m in chain_msgs)
    return last + 1 if steps == "chain" and ins_after else last


def start(kb: KnowledgeBase, test_case: str | TestCase, valid_on: date) -> tuple[RunState, str]:
    tc = kb.get_test_case(test_case) if isinstance(test_case, str) else test_case
    version = params_mod.version_on(kb, valid_on)
    ch = build_chain(load_scenario(kb, tc), version, kb)
    st = RunState(id=str(uuid.uuid4()), test_case=tc, valid_on=valid_on, version=version,
                  last_round=_rounds(ch.messages, tc.steps))
    return st, story_text(tc)


def _vendor_reply(kb: KnowledgeBase, st: RunState, m: ExpectedMessage, vendor: list[Record]) -> ExpectedMessage:
    """Adapt the expected insurer reply to the vendor's own messages."""
    m = m.model_copy(deep=True)
    v41 = next((r for r in vendor if r.abgabegrund == "41"), None)
    v01 = [r for r in vendor if r.abgabegrund == "01"]
    ref = v41 if m.abgabegrund == "61" else (v01[-1] if v01 else None)
    if ref is not None:
        m.blocks["DBID"]["REFERENZ-ID"] = ref.dsid or ""
        m.blocks["DBID"]["AKTENZEICHEN-VERURSACHER"] = ref.get("DBID.AKTENZEICHEN-VERURSACHER") or ""
        m.head["BBNR-VU"] = ref.get("DSLW.BBNR-VU") or m.head["BBNR-VU"]
    if m.abgabegrund == "61" and v41 is not None:
        exp_groups = {(g["BEGINN-AU"], g["ENDE-AU"]): g for g in m.blocks["DBVO"]["groups"]}
        ordered = []
        for s, e in v41.periods:  # K61-3: the vendor's periods in the vendor's order
            g = exp_groups.pop((s, e), None)
            ordered.append(g or {**next(iter(m.blocks["DBVO"]["groups"])), "BEGINN-AU": s, "ENDE-AU": e,
                                 "KZ-NACHWEIS": 4, "KZ-AU": 2})
        ordered += list(exp_groups.values())  # periods the insurer knows on top, appended
        m.blocks["DBVO"]["groups"] = ordered
    return m


def submit(kb: KnowledgeBase, st: RunState, files: list[str | bytes]) -> RoundResult:
    if st.status != "open":
        raise ValueError(f"run is {st.status}")
    st.round += 1
    r = st.round
    texts = [f.decode("utf-8") if isinstance(f, bytes) else f for f in files]
    st.files += texts
    new_msgs = [m for t in texts for m in parse_file(t, kb, st.version).messages]
    ch = build_chain(load_scenario(kb, st.test_case), st.version, kb)
    exp_round = [m for m in ch.messages if m.actor == "employer" and m.round == r]
    steps_done = {m.step for m in ch.messages if m.actor == "employer" and m.round <= r}

    res = Checker(kb).check(st.test_case, st.files, st.valid_on, version=st.version)
    outcomes: dict[str, RuleOutcome] = {}
    ended = False
    for d in res.deviations:
        if d.kind == "missing_message" and d.step not in steps_done:
            continue  # later rounds
        if d.step is not None and d.step not in steps_done:
            continue
        rule = d.rule or f"{d.record}.{d.field}"
        oc = "review" if d.label in ("unclear",) else ("pass" if d.label == "correct_variant" else "fail")
        if oc == "fail" or rule not in outcomes:
            outcomes[rule] = RuleOutcome(rule=rule, outcome=oc, message=d.explanation,
                                         expected=None if d.expected is None else str(d.expected),
                                         actual=None if d.actual is None else str(d.actual))
        if d.kind == "missing_message" and d.step in {m.step for m in exp_round}:
            ended = True
    if r > max((m.round for m in ch.messages if m.actor == "employer"), default=0) and new_msgs:
        outcomes["import-only"] = RuleOutcome(rule="import-only", outcome="fail",
                                              message="no new message may be sent in this round")
    for rule in st.test_case.targets:
        if rule.startswith("R41") and r == 1:
            outcomes.setdefault(rule, RuleOutcome(rule=rule, outcome="pass"))
    result = RoundResult(round=r, outcomes=list(outcomes.values()), ended=ended)
    vendor = [m for t in st.files for m in parse_file(t, kb, st.version).messages]
    replies = [m for m in ch.messages if m.actor == "insurer" and m.round == r]
    if replies and not ended:
        adapted = [_vendor_reply(kb, st, m, vendor) for m in replies]
        result.reply_name = f"TEEK0-{st.test_case.id}-r{r}"
        result.reply = write_file(adapted, kb)
    st.rounds.append(result)
    failed = any(o.outcome == "fail" for o in result.outcomes)
    if ended or failed and r >= st.last_round:
        st.status = "failed"
    elif r >= st.last_round:
        st.status = "failed" if any(o.outcome == "fail" for rr in st.rounds for o in rr.outcomes) else "passed"
    return result


def verdict(st: RunState) -> dict:
    """Pass / fail per rule. Hidden tests: no expected values, no messages with values."""
    per_rule: dict[str, RuleOutcome] = {}
    for rr in st.rounds:
        for o in rr.outcomes:
            if o.outcome == "fail" or o.rule not in per_rule:
                per_rule[o.rule] = o
    rules = []
    for o in per_rule.values():
        if st.test_case.hidden:
            rules.append({"rule": o.rule, "outcome": o.outcome})
        else:
            rules.append(o.model_dump())
    return {"run_id": st.id, "test_case_id": st.test_case.id, "status": st.status, "rounds": st.round,
            "version": st.version, "rules": rules}
