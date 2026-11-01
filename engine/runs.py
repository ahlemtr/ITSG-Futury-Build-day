"""Test runs in rounds.

`start` gives the vendor the story only. `submit` checks the round and builds the next insurer
reply from the vendor's own file (REF-ID = their DATENSATZ-ID). `verdict` returns pass / fail per
rule; for hidden tests without expected values. If a required message is missing, the rule fails
and the run ends.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date
from typing import Literal

from pydantic import BaseModel

from engine import families
from engine.builder import story_text
from engine.checker import Checker, worst
from engine.expected import build_chain, get_case, load_scenario
from engine.model import Case, CheckResult, ExpectedMessage
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
    simulator_issues: list[str] = []  # failed self-checks of our insurer reply (K61, K62, A3-1): our bug


class RunState(BaseModel):
    id: str
    test_case: Case
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


def start(kb: KnowledgeBase, test_case: str | Case, valid_on: date) -> tuple[RunState, str]:
    tc = get_case(kb, test_case) if isinstance(test_case, str) else test_case
    version = params_mod.version_on(kb, valid_on)
    ch = build_chain(load_scenario(kb, tc), version, kb)
    st = RunState(id=str(uuid.uuid4()), test_case=tc, valid_on=valid_on, version=version,
                  last_round=_rounds(ch.messages, tc.steps))
    return st, story_text(tc)


def submit(kb: KnowledgeBase, st: RunState, files: list[str | bytes]) -> RoundResult:
    if st.status != "open":
        raise ValueError(f"run is {st.status}")
    st.round += 1
    r = st.round
    texts = [f.decode("utf-8") if isinstance(f, bytes) else f for f in files]
    st.files += texts
    new_msgs = [m for t in texts for m in parse_file(t, kb, st.version, st.valid_on).messages]
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
    if r == 1:
        for rule in families.of_case(st.test_case).round_one_rules(st.test_case):
            outcomes.setdefault(rule, RuleOutcome(rule=rule, outcome="pass"))
    result = RoundResult(round=r, outcomes=list(outcomes.values()), ended=ended)
    vendor = [m for t in st.files for m in parse_file(t, kb, st.version, st.valid_on).messages]
    replies = [m for m in ch.messages if m.actor == "insurer" and m.round == r]
    if replies and not ended:
        fam = families.of_case(st.test_case)
        adapted = [fam.adapt_reply(m, vendor) for m in replies]
        result.reply_name = f"TEEK0-{st.test_case.id}-r{r}"
        result.reply = write_file(adapted, kb)
        written = parse_file(result.reply, kb, st.version, st.valid_on).messages
        scenario = load_scenario(kb, st.test_case)
        result.simulator_issues = [f"{x.rule}: {x.message}" for x in fam.self_check(kb, scenario, written, vendor)]
    st.rounds.append(result)
    failed = any(o.outcome == "fail" for o in result.outcomes)
    if ended or failed and r >= st.last_round:
        st.status = "failed"
    elif r >= st.last_round:
        st.status = "failed" if any(o.outcome == "fail" for rr in st.rounds for o in rr.outcomes) else "passed"
    return result


def self_check_chain(kb: KnowledgeBase, test_case: str | Case, version: str) -> list[str]:
    """The insurer replies of a case's expected chain checked against its expected employer messages."""
    sc = load_scenario(kb, test_case)
    ch = build_chain(sc, version, kb)
    parse = lambda msgs: parse_file(write_file(msgs, kb), kb, version).messages if msgs else []
    replies = parse([m for m in ch.messages if m.actor == "insurer"])
    employer = parse(ch.employer())
    return [f"{x.rule}: {x.message}" for x in families.of_case(sc.test_case).self_check(kb, sc, replies, employer)]


def check_so_far(kb: KnowledgeBase, st: RunState, triage=None) -> CheckResult:
    """The full check of the run's files, limited to the steps of the rounds played so far, so an open
    run does not show the messages of later rounds as missing. Stored as the run's submission check."""
    ch = build_chain(load_scenario(kb, st.test_case), st.version, kb)
    done = {m.step for m in ch.messages if m.actor == "employer" and m.round <= st.round}
    res = Checker(kb).check(st.test_case, st.files, st.valid_on, version=st.version, triage=triage)
    devs = [d for d in res.deviations if d.step is None or d.step in done]
    labels = [d.label for d in devs]
    return res.model_copy(update={
        "deviations": devs, "label": worst(labels), "counts": dict(Counter(labels)),
        "resolved_by": dict(Counter(d.resolved_by or "open" for d in devs)),
        "expected_messages": sum(1 for m in ch.messages if m.actor == "employer" and m.step in done)})


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
