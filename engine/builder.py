"""Test builder (P5.3 to P5.6): recompute expectations, clones, boundary variants, test packages,
hidden variants. Everything the builder produces is a `draft` until a human approves it.
"""

from __future__ import annotations

import io
import random
import zipfile
from datetime import date, timedelta

import yaml
from pydantic import BaseModel

from engine.expected import build_chain, get_case, insurer_flags, load_scenario, msg_61
from engine.model import AuPeriod, Case, ExpectedOutcome
from engine.rules import params as params_mod
from engine.rules.vorerkrankung import add_months, days, days_in_window, must_send_41
from engine.writer_messages import chain_files, write_file
from kg.interface import KnowledgeBase

VERSIONS = ("13.3", "13.4", "sim-13.5")


# ---------------------------------------------------------------- expectations


def outcome(kb: KnowledgeBase, tc: Case, version: str) -> ExpectedOutcome:
    i = tc.inputs
    d = must_send_41(i.current, i.priors, i.report_date, params_mod.load(kb, version=version))
    return ExpectedOutcome(send_41=d.send, periods=[(a.start, a.end) for a in d.chain] if d.send else [],
                           total_days=d.total_days if d.send else None)


def with_expected(kb: KnowledgeBase, tc: Case, versions=VERSIONS) -> Case:
    tc.expected = {v: outcome(kb, tc, v) for v in versions}
    return tc


class Recomputed(BaseModel):
    id: str
    old: ExpectedOutcome
    new: ExpectedOutcome
    differs: bool


def recompute(kb: KnowledgeBase, test_cases: list[str | Case], old: str, new: str) -> list[Recomputed]:
    """P5.3: expected results under both versions; `differs` marks the ones a spec change touches."""
    out = []
    for t in test_cases:
        tc = get_case(kb, t) if isinstance(t, str) else t
        o, n = outcome(kb, tc, old), outcome(kb, tc, new)
        out.append(Recomputed(id=tc.id, old=o, new=n, differs=o != n))
    return out


# ---------------------------------------------------------------- clones and boundaries


def clone(kb: KnowledgeBase, base: str | Case, branch_point: date | None, change: dict, new_id: str | None = None,
          targets: list[str] | None = None) -> Case:
    """P5.4: copy a test case, apply `change` to its inputs (`current`, `priors`, `report_date`,
    `employment_end`), keep `parent`. Status draft, origin builder."""
    b = get_case(kb, base) if isinstance(base, str) else base
    tc = b.model_copy(deep=True)
    inputs = tc.inputs.model_dump()
    inputs.update(change)
    tc.inputs = type(tc.inputs).model_validate(inputs)
    tc.id = new_id or f"{b.id}-clone"
    tc.parent, tc.kind, tc.origin, tc.status, tc.hidden = b.id, "clone", "builder", "draft", False
    tc.steps = "single"
    tc.branch_point = branch_point
    tc.targets = targets or b.targets
    return with_expected(kb, tc)


def boundaries(kb: KnowledgeBase, rule: str, base: str | Case) -> list[Case]:
    """Threshold -1 / = / +1 variants of one rule (P5.4).

    R41-4: totals from (smallest min_total_days - 1) to the largest one, by moving the current end.
    R41-2: one prior of 36 days ending 6 months + 1 day / exactly / - 1 day before the current start.
    R41-3: the oldest link of the chain at gap - 1 day / exact / + 1 day.
    """
    b = get_case(kb, base) if isinstance(base, str) else base
    cur = b.inputs.current
    pv = [params_mod.load(kb, version=v) for v in VERSIONS]
    out: list[Case] = []
    if rule == "R41-4":
        p = pv[0]
        window = add_months(cur.start, -p.sum_window_months)
        certified = [a for a in b.inputs.priors if a.certified]
        prior_days = sum(days_in_window(a, window, cur.start) for a in certified)
        lo, hi = min(x.min_total_days for x in pv) - 1, max(x.min_total_days for x in pv)
        for total in range(lo, hi + 1):
            end = cur.start + timedelta(days=total - prior_days - 1)
            out.append(clone(kb, b, cur.start, {"current": {**cur.model_dump(), "end": end}},
                             f"{b.id}-b{total}", ["R41-4"]))
        return out
    gap = pv[0].gap_months
    if rule == "R41-2":
        exact_end = add_months(cur.start, -gap)
        for name, shift in (("gap-in", 1), ("gap-exact", 0), ("gap-out", -1)):
            end = exact_end + timedelta(days=shift)
            prior = AuPeriod(start=end - timedelta(days=35), end=end, certified=True)
            out.append(clone(kb, b, cur.start, {"priors": [prior.model_dump()]}, f"{b.id}-{name}",
                             ["R41-2", "R41-3"]))
        return out
    if rule == "R41-3":
        priors = sorted([a for a in b.inputs.priors if a.certified], key=lambda a: a.end, reverse=True)
        if len(priors) < 2:
            raise ValueError("R41-3 boundaries need at least two certified priors")
        nxt = priors[-2]
        exact_end = add_months(nxt.start, -gap)
        for name, shift in (("link-in", 1), ("link-exact", 0), ("link-out", -1)):
            end = exact_end + timedelta(days=shift)
            dur = days(priors[-1].start, priors[-1].end)
            moved = AuPeriod(start=end - timedelta(days=dur - 1), end=end, certified=True)
            new = [a.model_dump() for a in priors[:-1]] + [moved.model_dump()]
            out.append(clone(kb, b, cur.start, {"priors": new}, f"{b.id}-{name}", ["R41-3"]))
        return out
    raise ValueError(f"no boundary generator for {rule}")


# ---------------------------------------------------------------- hidden variants (P5.6)


def _month_ends(around: date) -> list[date]:
    out = []
    for y in range(around.year - 1, around.year + 3):
        for m in range(1, 13):
            first_next = date(y + (m == 12), m % 12 + 1, 1)
            out.append(first_next - timedelta(days=1))
    return out


def hidden(kb: KnowledgeBase, test_case: str | Case, seed: int = 0) -> Case:
    """Same rule, other dates; expected results computed by the engine, never exported.

    Gap boundary cases (one prior, targets R41-2): the prior moves to a month end whose `+ gap`
    is clamped (31.08 + 6 months = 28.02, leap years give 29.02); the gap offset (in / exact /
    out) and both durations are kept. Other cases: the whole story is shifted by a seeded number
    of days, keeping every decision unchanged."""
    b = get_case(kb, test_case) if isinstance(test_case, str) else test_case
    i = b.inputs
    gap = params_mod.load(kb, version="13.4").gap_months
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
        base_exp = {v: outcome(kb, b, v).send_41 for v in VERSIONS}
        for _ in range(50):
            sh = timedelta(days=rng.randint(20, 90))
            mv = lambda d, sh=sh: d + sh if d else None
            change = {"priors": [{"start": mv(a.start), "end": mv(a.end), "certified": a.certified} for a in i.priors],
                      "current": {"start": mv(i.current.start), "end": mv(i.current.end),
                                  "certified": i.current.certified},
                      "report_date": mv(i.report_date), "employment_end": mv(i.employment_end)}
            probe = clone(kb, b, None, change)
            if {v: probe.expected[v].send_41 for v in VERSIONS} == base_exp:
                break
    tc = clone(kb, b, None, change, hid, b.targets)
    tc.kind, tc.hidden = "hidden", True
    tc.parent = b.id
    return tc


# ---------------------------------------------------------------- story and package (P5.5)


def story_text(tc: Case) -> str:
    """Deterministic TA-style story (inputs only). P8 can replace it with an LLM story."""
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


def single_step_reply(kb: KnowledgeBase, tc: Case, version: str):
    """The insurer's 61 for a single-step test (round 1 only), default flags."""
    sc = load_scenario(kb, tc)
    ch = build_chain(sc, version, kb)
    if not ch.messages:
        return None
    m41 = ch.messages[0]
    return msg_61(sc, ch.decision.chain, "corrected_61", 2, 1, m41.head["DATENSATZ-ID"])


def package(kb: KnowledgeBase, tc: Case, version: str, story: str | None = None) -> dict[str, str]:
    """Scenario YAML + expected TEEL0 + TEEK0 + story. Refused for hidden tests."""
    if tc.hidden:
        raise PermissionError("hidden test cases are never exported")
    sc = load_scenario(kb, tc)
    ch = build_chain(sc, version, kb)
    files = {"scenario.yaml": yaml.safe_dump(tc.model_dump(mode="json"), allow_unicode=True, sort_keys=False)}
    files.update(chain_files(ch, tc.id, kb))
    if tc.steps == "single":
        reply = single_step_reply(kb, tc, version)
        if reply:
            files[f"TEEK0-{tc.id}-s2-61"] = write_file([reply], kb)
    files["story.txt"] = story or story_text(tc)
    return files


def package_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text.encode("utf-8"))
    return buf.getvalue()


__all__ = [
    "boundaries",
    "clone",
    "hidden",
    "insurer_flags",
    "outcome",
    "package",
    "package_zip",
    "recompute",
    "story_text",
]
