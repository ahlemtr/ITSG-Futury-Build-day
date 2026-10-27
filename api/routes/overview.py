"""Figures for the portal's first screen: the rule set in force, next year's rule set, who settled the deviations."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request

from api.routes.common import kb, repo
from engine import builder, specdiff
from engine.expected import get_case
from engine.rules import params as params_mod

router = APIRouter()

PASSED = ("exact_match", "correct_variant")


@router.get("/overview")
def overview(request: Request, today: date | None = None):
    today = today or date.today()
    k, r = kb(request), repo(request)
    versions = sorted((v for v in k.get_versions("VB") if not v.version.startswith("sim") and v.valid_from),
                      key=lambda v: v.valid_from)
    now = params_mod.version_on(k, today)
    nxt = next((v for v in versions if v.valid_from > today), None)

    subs = r.list_submissions()
    checks = [c for c in (r.get_check(s.id) for s in subs) if c is not None]
    open_subs = sum(1 for c in checks if any(d.label == "unclear" and d.resolved_by != "advisor" for d in c.deviations))
    resolution = {"catalogueAndRules": 0, "aiConfirmedByAdvisor": 0, "waitingForAdvisor": 0}
    for c in checks:
        for d in c.deviations:
            if d.resolved_by == "advisor":
                resolution["aiConfirmedByAdvisor"] += 1
            elif d.label == "unclear":
                resolution["waitingForAdvisor"] += 1
            else:
                resolution["catalogueAndRules"] += 1

    next_year = None
    if nxt is not None:
        changes = k.get_changes("VB", now, nxt.version, in_scope_only=True)
        tests = specdiff.impact(changes, k).tests
        flips = [x for x in builder.recompute(k, [get_case(k, t.key) for t in tests], now, nxt.version) if x.differs]
        cases = r.list_test_cases()
        next_year = {"ruleSet": nxt.version, "validFrom": nxt.valid_from.isoformat(),
                     "specChangesInScope": len(changes),
                     "testsToReapprove": len(flips),
                     "hiddenVariantsReady": sum(1 for t in cases if t.hidden and t.status == "approved")}
    return {
        "checksNow": {"ruleSet": now,
                      "validUntil": (nxt.valid_from - timedelta(days=1)).isoformat() if nxt else None,
                      "month": today.isoformat()[:7],
                      "submissions": len(subs),
                      "passedAllRules": sum(1 for c in checks if c.label in PASSED),
                      "withOpenDeviations": open_subs},
        "nextYear": next_year,
        "resolution": resolution,
    }
