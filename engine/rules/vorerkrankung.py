"""Prior-illness rules (P2.2 to P2.4): when a 41 must be sent, which periods it lists, EFZ end.

Exactly the algorithms of plan/03 sections 3 and 6. Every function returns a `Trace`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta

from engine.model import AuPeriod, Decision41, Trace
from engine.rules.params import Params


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


def must_send_41(current: AuPeriod, priors: list[AuPeriod], report_date: date | None, p: Params) -> Decision41:
    t = Trace(inputs={"current": current.model_dump(mode="json"), "priors": [a.model_dump(mode="json") for a in priors],
                      "report_date": str(report_date) if report_date else None, "params": p.__dict__})
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


def deciding_rule(current: AuPeriod, priors: list[AuPeriod], report_date: date | None, p: Params) -> str:
    """For a 41 that must be sent: the condition closest to its boundary (smallest margin).
    Used to name the rule a vendor broke when it sent no 41. Ties go to R41-2."""
    d = must_send_41(current, priors, report_date, p)
    if not d.send:
        return d.trace.failed[-1] if d.trace.failed else "R41-1"
    gap_margin = (gap_limit(d.chain[0].end, p) - current.start).days
    total_margin = (d.total_days or 0) - p.min_total_days
    return "R41-2" if gap_margin <= total_margin else "R41-4"


# ---------------------------------------------------------------- EFZ end (plan/03 section 6)


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
