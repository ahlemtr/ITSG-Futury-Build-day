"""Seed data (P7.2, plan/02 section 7): the test case catalogue and the 10 seed submissions.

`python -m store.seed` seeds the store selected by DATABASE_URL with the KG selected by KG_BACKEND.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from engine.checker import Checker
from engine.expected import get_case
from engine.intake import load_files, receive
from kg.interface import KnowledgeBase
from tools.make_submissions import build_submissions

# Made-up vendor names for the portal demo; `s-itsg-ref` carries ITSG's own reference file.
VENDORS = {
    "s-itsg-ref": "ITSG Referenz",
    "s-variant": "Payroll Nord Demo",
    "s-three-periods": "Lohnwerk Demo GmbH",
    "s-missing-july": "Gehalt 24 Demo",
    "s-wrong-order": "Lohnbüro West Demo",
    "s-stale-efz": "Gehalt 24 Demo",
    "s-insurer-field": "Lohnbüro West Demo",
    "s-no-contact": "Abrechnung Süd Demo",
    "s-legacy-1": "Altlohn Classic Demo",
    "s-legacy-hidden": "Altlohn Classic Demo",
}


def seed(kb: KnowledgeBase, repo, root: Path | None = None, check: bool = True, triage=None) -> dict[str, int]:
    """With `check`, every seed submission is checked once, so lists and counts show labels right away;
    `triage` (the AI services' triage) fills the AI proposal of unclear deviations."""
    for ref in kb.get_test_cases(include_hidden=True):
        repo.upsert_test_case(get_case(kb, ref.key))
    if os.environ.get("SPEC_BASELINE"):  # the starting point has no submissions; vendors upload live
        return {"test_cases": len(repo.list_test_cases()), "submissions": 0}
    subs = build_submissions(kb)
    for s in subs:
        valid_on = date.fromisoformat(max(s.expected_label))
        receive(kb, repo, {n: t.encode("utf-8") for n, t in s.files.items()}, s.test_case_id, valid_on=valid_on,
                vendor=VENDORS.get(s.id, "seed"), submission_id=s.id, content=s.content, root=root)
        if check:
            sub = repo.get_submission(s.id)
            res = Checker(kb).check(repo.get_test_case(s.test_case_id), list(load_files(sub).values()), valid_on,
                                    triage=triage)
            repo.save_check(s.id, res)
    return {"test_cases": len(repo.list_test_cases()), "submissions": len(repo.list_submissions())}


if __name__ == "__main__":
    from kg import get_kb
    from store.repo import get_repo

    print(seed(get_kb(), get_repo()))
