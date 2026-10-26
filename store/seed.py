"""Seed data (P7.2, plan/02 section 7): the test case catalogue and the 10 seed submissions.

`python -m store.seed` seeds the store selected by DATABASE_URL with the KG selected by KG_BACKEND.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from engine.expected import get_case
from engine.intake import receive
from kg.interface import KnowledgeBase
from tools.make_submissions import build_submissions


def seed(kb: KnowledgeBase, repo, root: Path | None = None) -> dict[str, int]:
    for ref in kb.get_test_cases(include_hidden=True):
        repo.upsert_test_case(get_case(kb, ref.key))
    subs = build_submissions(kb)
    for s in subs:
        valid_on = date.fromisoformat(max(s.expected_label))
        receive(kb, repo, {n: t.encode("utf-8") for n, t in s.files.items()}, s.test_case_id, valid_on=valid_on,
                vendor="seed", submission_id=s.id, content=s.content, root=root)
    return {"test_cases": len(repo.list_test_cases()), "submissions": len(repo.list_submissions())}


if __name__ == "__main__":
    from kg import get_kb
    from store.repo import get_repo

    print(seed(get_kb(), get_repo()))
