"""Prior-illness rules: when a 41 must be sent, which periods it lists, EFZ end.

Every function returns a `Trace`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta

from engine.model import AuPeriod, Decision41, TestInputs, Trace
from engine.rules.params import Params

NO_41_PERSON_GROUPS = {109, 110}  # marginal employment (Pflichtenheft item bcec54ad)
INTERIM_KZ_AU = 3  # "further check": an interim answer of the insurer (K61-5, E-3)
INTERIM_KZ_AK_AU = 4  # current sick note missing (K61-7, E-3)


def days(start: date, end: date) -> int:
    """Calendar days, both ends inclusive."""
    return (end - start).days + 1


def add_months(d: date, n: int) -> date:
    """Calendar months (relativedelta clamps month ends: 31.08 + 6 = 28.02)."""
    return d + relativedelta(months=n)


def days_in_window(a: AuPeriod, window_start: date, window_end_excl: date) -> int:
    s, e = max(a.start, window_start), min(a.end, window_end_excl - timedelta(days=1))
    return days(s, e) if e >= s else 0


def gap_limit(prior_end: date, p: Params) -> date:
    return add_months(prior_end, p.gap_months)


def too_far(next_start: date, prior_end: date, p: Params) -> bool:
    limit = gap_limit(prior_end, p)
    return next_start > limit if p.gap_inclusive else next_start >= limit


def select_chain(current: AuPeriod, certified: list[AuPeriod], p: Params, trace: Trace | None = None) -> list[AuPeriod]:
    """Newest first; stop at the first gap larger than gap_months (R41-2 for the first link, R41-3 after)."""
    chain: list[AuPeriod] = []
    next_start = current.start
    for a in sorted(certified, key=lambda a: a.end, reverse=True):
        rule = "R41-2" if not chain else "R41-3"
        limit = gap_limit(a.end, p)
        far = too_far(next_start, a.end, p)
        if trace:
            op = ">" if p.gap_inclusive else ">="
            trace.add(rule, f"prior {a.start}..{a.end}: next start {next_start} {op} {limit} is {far}"
                            f" -> {'stop' if far else 'chain'}", ok=not far or bool(chain))
        if far:
            break
        chain.append(a)
        next_start = a.start
    return chain


def current_end(current: AuPeriod, report_date: date | None, p: Params) -> date:
    """R41-6: an open-ended AU counts until report date + open_end_days - 1."""
    if current.end:
        return current.end
    if report_date is None:
        raise ValueError("open-ended current AU needs a report date")
    return report_date + timedelta(days=p.open_end_days - 1)


def must_send_41(current: AuPeriod, priors: list[AuPeriod], report_date: date | None, p: Params,
                 insurance: str = "statutory", person_group: int | None = None) -> Decision41:
    t = Trace(inputs={"current": current.model_dump(mode="json"), "priors": [a.model_dump(mode="json") for a in priors],
                      "report_date": str(report_date) if report_date else None, "params": p.__dict__,
                      "insurance": insurance, "person_group": person_group})
    if insurance != "statutory":
        t.add("R41-7", f"insurance {insurance}: a 41 only for people with statutory health insurance", ok=False)
        return Decision41(send=False, trace=t)
    t.add("R41-7", "statutory health insurance: the 41 goes to the person's health insurer")
    if person_group in NO_41_PERSON_GROUPS:
        t.add("R41-8", f"person group {person_group}: no 41 for marginal employment", ok=False)
        return Decision41(send=False, trace=t)
    certified = [a for a in priors if a.certified]
    dropped = [a for a in priors if not a.certified]
    t.add("R41-5", f"{len(dropped)} uncertified prior(s) dropped")
    if not current.certified or not certified:
        t.add("R41-1", f"current certified={current.certified}, certified priors={len(certified)}", ok=False)
        return Decision41(send=False, trace=t)
    t.add("R41-1", f"current certified, {len(certified)} certified prior(s)")
    chain = select_chain(current, certified, p, t)
    if not chain:
        t.values["chain"] = []
        return Decision41(send=False, trace=t)
    cur_end = current_end(current, report_date, p)
    if not current.end:
        t.add("R41-6", f"open end counted until {cur_end}")
    window_start = add_months(current.start, -p.sum_window_months)
    cur_days = days(current.start, cur_end)
    prior_days = sum(days_in_window(a, window_start, current.start) for a in chain)
    total = cur_days + prior_days
    t.values.update(chain=[[str(a.start), str(a.end)] for a in chain], window_start=str(window_start),
                    current_days=cur_days, prior_days=prior_days, total=total)
    ok = total >= p.min_total_days
    t.add("R41-4", f"total {total} = {cur_days} current + {prior_days} prior; minimum {p.min_total_days}", ok=ok)
    return Decision41(send=ok, chain=chain, total_days=total, trace=t)


def decide(i: TestInputs, p: Params) -> Decision41:
    """must_send_41 on a test case's inputs."""
    return must_send_41(i.current, i.priors, i.report_date, p, insurance=i.insurance, person_group=i.person_group)


def deciding_rule(current: AuPeriod, priors: list[AuPeriod], report_date: date | None, p: Params,
                  insurance: str = "statutory", person_group: int | None = None) -> str:
    """For a 41 that must be sent: the condition closest to its boundary (smallest margin).
    Used to name the rule a vendor broke when it sent no 41. Ties go to R41-2."""
    d = must_send_41(current, priors, report_date, p, insurance=insurance, person_group=person_group)
    if not d.send:
        return d.trace.failed[-1] if d.trace.failed else "R41-1"
    gap_margin = (gap_limit(d.chain[0].end, p) - current.start).days
    total_margin = (d.total_days or 0) - p.min_total_days
    return "R41-2" if gap_margin <= total_margin else "R41-4"


# ---------------------------------------------------------------- insurer flags on the 61 (K61-4, K61-5)


def note_kind(a: AuPeriod) -> str:
    return a.sick_note or ("eau" if a.certified else "none")


def insurer_has_note(a: AuPeriod, reply: str) -> bool:
    """Does the insurer have the sick note when it writes this reply ("first" or "corrected" 61)?
    An eAU reaches it at once; a paper note when the case says (default: never)."""
    kind = note_kind(a)
    if kind == "eau":
        return True
    if kind == "paper":
        gets = a.insurer_gets_note or "never"
        return gets == "first" or (gets == "corrected" and reply == "corrected")
    return False


def insurer_flags(a: AuPeriod, reply: str) -> dict[str, Any]:
    """The DBVO group flags the insurer sets for one prior period in its first or corrected 61.

    K61-4 KZ-NACHWEIS: 1 sick note present, 4 missing. K61-5 KZ-AU: 1 counts, 2 does not count, 5 partly counts
    (TEIL-ANR-AU range), 3 further check (interim). A missing note is an interim answer in the first 61 (4 / 3);
    in the corrected 61 the insurer has decided: still missing = does not count (4 / 2). A period the insurer
    rechecks is set back to 3 in the corrected 61 (E-3)."""
    out: dict[str, Any] = {"KZ-NACHWEIS": 1, "KZ-AU": 1, "TEIL-ANR-AU-BEGINN": None, "TEIL-ANR-AU-ENDE": None}
    if not insurer_has_note(a, reply):
        out.update({"KZ-NACHWEIS": 4, "KZ-AU": INTERIM_KZ_AU if reply == "first" else 2})
        return out
    if reply == "corrected" and a.insurer_rechecks:
        out["KZ-AU"] = INTERIM_KZ_AU
    elif a.counts == "no":
        out["KZ-AU"] = 2
    elif a.counts == "partly":
        out.update({"KZ-AU": 5, "TEIL-ANR-AU-BEGINN": a.counts_from, "TEIL-ANR-AU-ENDE": a.counts_to})
    return out


def supersedes(old: Mapping[str, Any], new: Mapping[str, Any]) -> bool:
    """E-3: does an updated 61 replace the earlier one? Not if every change only sets an interim flag
    (KZ-AU 3 or KZ-AK-AU 4): the earlier answer stands. `old` / `new`: the DBVO blocks of both 61s."""
    if _g(old, "KZ-AK-AU") != _g(new, "KZ-AK-AU") and _g(new, "KZ-AK-AU") != INTERIM_KZ_AK_AU:
        return True
    og, ng = old.get("groups", []), new.get("groups", [])
    if [(_g(g, "BEGINN-AU"), _g(g, "ENDE-AU")) for g in og] != [(_g(g, "BEGINN-AU"), _g(g, "ENDE-AU")) for g in ng]:
        return True
    for a, b in zip(og, ng):
        changed = {k for k in set(a) | set(b) if _g(a, k) != _g(b, k)}
        if changed - {"KZ-AU", "KZ-NACHWEIS"} or ("KZ-AU" in changed and _g(b, "KZ-AU") != INTERIM_KZ_AU):
            return True
        if "KZ-NACHWEIS" in changed and _g(b, "KZ-AU") != INTERIM_KZ_AU:
            return True
    return False


# ---------------------------------------------------------------- EFZ end


def _g(g: Mapping[str, Any], name: str) -> Any:
    v = g.get(name)
    return getattr(v, "value", v)


def efz_end(current_start: date, groups_61: list[Mapping[str, Any]], p: Params) -> tuple[date, Trace]:
    t = Trace(inputs={"current_start": str(current_start), "efz_days": p.efz_days})
    used = 0
    for g in groups_61:
        s, e = _g(g, "BEGINN-AU"), _g(g, "ENDE-AU")
        kz_au, kz_nw = int(_g(g, "KZ-AU") or 0), int(_g(g, "KZ-NACHWEIS") or 0)
        n = 0
        if kz_au == 1 and kz_nw == 1:
            n = days(s, e)
        elif kz_au == 1 and kz_nw == 2 and _g(g, "TEIL-NACHWEIS-AU-BEGINN"):
            n = days(_g(g, "TEIL-NACHWEIS-AU-BEGINN"), _g(g, "TEIL-NACHWEIS-AU-ENDE"))
        elif kz_au == 5 and _g(g, "TEIL-ANR-AU-BEGINN"):
            n = days(_g(g, "TEIL-ANR-AU-BEGINN"), _g(g, "TEIL-ANR-AU-ENDE"))
        used += n
        t.steps.append(f"E-1: {s}..{e} KZ-AU {kz_au} KZ-NACHWEIS {kz_nw} -> {n} days")
    remaining = p.efz_days - used
    end = current_start + timedelta(days=remaining - 1) if remaining > 0 else current_start - timedelta(days=1)
    t.rules.append("E-1")
    t.values.update(used=used, remaining=remaining, efz_end=str(end))
    return end, t
