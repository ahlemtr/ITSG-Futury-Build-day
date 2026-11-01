"""Test builder parts of the prior-illness family: the 41 decision as expected outcome, boundary
variants of R41-2 / R41-3 / R41-4, hidden variants and the task story."""

from __future__ import annotations

import random
from datetime import date, timedelta

from engine import builder as core
from engine.families.vorerkrankung.rules import add_months, days, days_in_window, decide
from engine.model import AuPeriod, Case, ExpectedOutcome
from engine.rules import params as params_mod
from kg.interface import KnowledgeBase


def outcome(kb: KnowledgeBase, tc: Case, version: str) -> ExpectedOutcome:
    d = decide(tc.inputs, params_mod.load(kb, version=version))
    return ExpectedOutcome(send_41=d.send, periods=[(a.start, a.end) for a in d.chain] if d.send else [],
                           total_days=d.total_days if d.send else None)


# ---------------------------------------------------------------- boundaries


def boundaries_r41_4(kb: KnowledgeBase, b: Case) -> list[Case]:
    """Totals from (smallest min_total_days - 1) to the largest one, by moving the current end."""
    cur = b.inputs.current
    pv = [params_mod.load(kb, version=v) for v in params_mod.all_versions(kb)]
    p = pv[0]
    window = add_months(cur.start, -p.sum_window_months)
    certified = [a for a in b.inputs.priors if a.certified]
    prior_days = sum(days_in_window(a, window, cur.start) for a in certified)
    lo, hi = min(x.min_total_days for x in pv) - 1, max(x.min_total_days for x in pv)
    out = []
    for total in range(lo, hi + 1):
        end = cur.start + timedelta(days=total - prior_days - 1)
        out.append(core.clone(kb, b, cur.start, {"current": {**cur.model_dump(), "end": end}},
                              f"{b.id}-b{total}", ["R41-4"]))
    return out


def _gap(kb: KnowledgeBase) -> int:
    return params_mod.load(kb, version=params_mod.all_versions(kb)[0]).gap_months


def boundaries_r41_2(kb: KnowledgeBase, b: Case) -> list[Case]:
    """One prior of 36 days ending 6 months + 1 day / exactly / - 1 day before the current start."""
    cur = b.inputs.current
    exact_end = add_months(cur.start, -_gap(kb))
    out = []
    for name, shift in (("gap-in", 1), ("gap-exact", 0), ("gap-out", -1)):
        end = exact_end + timedelta(days=shift)
        prior = AuPeriod(start=end - timedelta(days=35), end=end, certified=True)
        out.append(core.clone(kb, b, cur.start, {"priors": [prior.model_dump()]}, f"{b.id}-{name}",
                              ["R41-2", "R41-3"]))
    return out


def boundaries_r41_3(kb: KnowledgeBase, b: Case) -> list[Case]:
    """The oldest link of the chain at gap - 1 day / exact / + 1 day."""
    cur = b.inputs.current
    priors = sorted([a for a in b.inputs.priors if a.certified], key=lambda a: a.end, reverse=True)
    if len(priors) < 2:
        raise ValueError("R41-3 boundaries need at least two certified priors")
    nxt = priors[-2]
    exact_end = add_months(nxt.start, -_gap(kb))
    out = []
    for name, shift in (("link-in", 1), ("link-exact", 0), ("link-out", -1)):
        end = exact_end + timedelta(days=shift)
        dur = days(priors[-1].start, priors[-1].end)
        moved = AuPeriod(start=end - timedelta(days=dur - 1), end=end, certified=True)
        new = [a.model_dump() for a in priors[:-1]] + [moved.model_dump()]
        out.append(core.clone(kb, b, cur.start, {"priors": new}, f"{b.id}-{name}", ["R41-3"]))
    return out


GENERATORS = {"R41-2": boundaries_r41_2, "R41-3": boundaries_r41_3, "R41-4": boundaries_r41_4}


# ---------------------------------------------------------------- hidden variants


def _month_ends(around: date) -> list[date]:
    out = []
    for y in range(around.year - 1, around.year + 3):
        for m in range(1, 13):
            first_next = date(y + (m == 12), m % 12 + 1, 1)
            out.append(first_next - timedelta(days=1))
    return out


def hidden(kb: KnowledgeBase, b: Case, seed: int = 0) -> Case:
    """Same rule, other dates; expected results computed by the engine, never exported.

    Gap boundary cases (one prior, targets R41-2): the prior moves to a month end whose `+ gap`
    is clamped (31.08 + 6 months = 28.02, leap years give 29.02); the gap offset (in / exact /
    out) and both durations are kept. Other cases: the whole story is shifted by a seeded number
    of days, keeping every decision unchanged."""
    i = b.inputs
    gap = params_mod.load(kb, version=params_mod.latest(kb)).gap_months
    hid = f"{b.id}-hidden" + (f"-{seed}" if seed else "")
    if "R41-2" in b.targets and len(i.priors) == 1 and i.current.end:
        prior = i.priors[0]
        offset = (i.current.start - add_months(prior.end, gap)).days
        cands = [e for e in _month_ends(prior.end) if add_months(e, gap).day != e.day and e <= prior.end]
        cands.sort(key=lambda e: (prior.end - e).days)
        end = cands[seed % min(len(cands), 6)]
        start_cur = add_months(end, gap) + timedelta(days=offset)
        shift = start_cur - i.current.start
        new_prior = AuPeriod(start=end - timedelta(days=days(prior.start, prior.end) - 1), end=end,
                             certified=prior.certified)
        change = {"priors": [new_prior.model_dump()],
                  "current": {"start": start_cur, "end": i.current.end + shift, "certified": i.current.certified},
                  "report_date": (i.report_date + shift) if i.report_date else None,
                  "employment_end": (i.employment_end + shift) if i.employment_end else None}
    else:
        rng = random.Random(seed)
        base_exp = {v: outcome(kb, b, v).send_41 for v in params_mod.all_versions(kb)}
        for _ in range(50):
            sh = timedelta(days=rng.randint(20, 90))
            mv = lambda d, sh=sh: d + sh if d else None
            change = {"priors": [{"start": mv(a.start), "end": mv(a.end), "certified": a.certified} for a in i.priors],
                      "current": {"start": mv(i.current.start), "end": mv(i.current.end),
                                  "certified": i.current.certified},
                      "report_date": mv(i.report_date), "employment_end": mv(i.employment_end)}
            probe = core.clone(kb, b, None, change)
            if {v: probe.expected[v].send_41 for v in params_mod.all_versions(kb)} == base_exp:
                break
    tc = core.clone(kb, b, None, change, hid, b.targets)
    tc.kind, tc.hidden = "hidden", True
    tc.parent = b.id
    return tc


# ---------------------------------------------------------------- story


def story_text(tc: Case) -> str:
    """Deterministic TA-style story (inputs only). llm/story.py can replace it with an LLM story."""
    f = lambda d: d.strftime("%d.%m.%Y")
    i = tc.inputs
    lines = [f"Testfall {tc.id}", "", "Im System hinterlegte AU-Zeiten:"]
    for a in sorted(i.priors, key=lambda a: a.start):
        note = "" if a.certified else " (ohne AU-Bescheinigung)"
        lines.append(f"- {f(a.start)} bis {f(a.end)}{note}")
    cur = i.current
    end = f"bis {f(cur.end)}" if cur.end else "mit offenem Ende"
    lines += ["", f"Die aktuelle AU beginnt am {f(cur.start)}, {end}."]
    if i.report_date:
        lines.append(f"Tagesdatum der Meldung: {f(i.report_date)}.")
    if i.employment_end:
        lines.append(f"Ende der Beschäftigung: {f(i.employment_end)}.")
    lines += ["", "Erstellen Sie die nach Verfahrensbeschreibung 3.12 erforderlichen Meldungen."]
    return "\n".join(lines) + "\n"
