"""Deadlines per vendor company (HANDOUT agenda 1): what is due when, and how the catalogue evolved.

Stored deadlines come from events: starting a test run opens round 1, every accepted round closes its
deadline and opens the next one. Rule-set deadlines are derived on read from the knowledge base and the
companies' certificates, so they always match the versions the platform knows:

- update tests: a certified company does not run the whole catalogue again when a new Verfahrensbeschreibung
  comes. It passes the new and changed test cases of that version (the catalogue's cases on the rules the
  changes recompute, plus the tests the upload drafted) by the day before the version takes effect; done once
  it passed a run of each of them under the new version. Overdue after the switch until it has;
- first certification: a company without a certificate (new software) runs the full catalogue of the rule set
  in force, with no fixed date (plan/06 event D); `view` reports its progress per company;
- permanent test cases (PTA 8.4): certified companies send them every month, due on the last day;
  done once a submission of that company arrived in the month;
- ITSG: next year's catalogue approved CATALOGUE_LEAD_DAYS before the switch date; the switch date itself.

The day counts are assumptions until ITSG confirms them (HANDOUT agenda 1, "open").
"""

from __future__ import annotations

import calendar as cal
import re
import unicodedata
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from engine import specdiff

ROUND_DAYS = 14  # round N is due 14 days after the insurer reply of round N-1 (round 1: after the start)
CATALOGUE_LEAD_DAYS = 60  # vendors get two months with the approved catalogue before the switch
PERMANENT_MONTHS = 3  # this month and the next two
SOON_DAYS = 7  # due within a week: shown as a reminder

Kind = Literal["round", "update", "permanent", "catalogue", "switch"]


class Company(BaseModel):
    id: str
    name: str
    product: str | None = None
    certified_until: date | None = None
    certified_for: str | None = None  # rule set of the current certificate; None: new software, not certified yet


class Deadline(BaseModel):
    id: str
    company_id: str | None = None  # None = ITSG
    kind: Kind
    due: date
    opened: date | None = None  # start of the window (round: the day the reply it answers went out)
    ref: str | None = None  # run id or rule set version
    params: dict = {}  # round, rounds, test case, version: the UI writes the text
    done: bool = False
    done_on: date | None = None


def slug(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def company_for(repo, name: str | None) -> Company | None:
    """The company of a vendor name; a name seen for the first time becomes a new, uncertified company."""
    if not name:
        return None
    c = repo.get_company(slug(name))
    if c is None:
        c = Company(id=slug(name), name=name)
        repo.save_company(c)
    return c


def _round_id(run_id: str, n: int) -> str:
    return f"round-{run_id[:8]}-{n}"


def _open_round(repo, st, company: Company, n: int, opened: date) -> None:
    repo.save_deadline(Deadline(id=_round_id(st.id, n), company_id=company.id, kind="round", opened=opened,
                                due=opened + timedelta(days=ROUND_DAYS), ref=st.id,
                                params={"round": n, "rounds": st.last_round, "test_case": st.test_case.id,
                                        "hidden": st.test_case.hidden, "version": st.version}))


def run_started(repo, st, vendor: str | None, today: date) -> None:
    if c := company_for(repo, vendor):
        _open_round(repo, st, c, 1, today)


def round_accepted(repo, st, vendor: str | None, today: date) -> None:
    """Called after `runs.submit`: closes the round just played, opens the next while the run is open."""
    c = company_for(repo, vendor)
    if c is None:
        return
    d = repo.get_deadline(_round_id(st.id, st.round))
    if d is not None:
        repo.save_deadline(d.model_copy(update={"done": True, "done_on": today}))
    if st.status == "open" and st.round < st.last_round:
        _open_round(repo, st, c, st.round + 1, today)


def _month_end(d: date) -> date:
    return d.replace(day=cal.monthrange(d.year, d.month)[1])


def _add_month(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1)


def _versions(kb) -> list:
    return sorted((v for v in kb.get_versions("VB") if not v.version.startswith("sim") and v.valid_from),
                  key=lambda v: v.valid_from)


def update_tests(kb, repo, old: str, new: str) -> list[str]:
    """The new and changed test cases of a rule set update: the catalogue's cases on the rules the changes
    recompute, plus the tests the upload of the new version drafted."""
    rules = {r.id for r in specdiff.impact(kb.get_changes("VB", old, new, in_scope_only=True), kb).recompute}
    ids = {t.id for t in repo.list_test_cases() if rules & set(t.targets)}
    for job in repo.list_jobs():
        if job.get("document") == "VB" and job.get("version") == new and job.get("status") == "done":
            ids |= set((job.get("result") or {}).get("drafts") or [])
    return sorted(ids)


def passed_tests(runs: list[dict], company_id: str, version: str | None = None) -> set[str]:
    return {r["test_case"]["id"] for r in runs if r.get("status") == "passed" and slug(r.get("vendor") or "") == company_id
            and (version is None or r.get("version") == version)}


def derived(kb, repo, today: date) -> list[Deadline]:
    out: list[Deadline] = []
    runs = repo.list_runs()
    subs = repo.list_submissions()
    versions = _versions(kb)
    for c in repo.list_companies():
        if c.certified_for is None:
            continue
        since = next((v.valid_from for v in versions if v.version == c.certified_for), None)
        for v in versions:
            if since is None or v.valid_from <= since:
                continue
            tests = update_tests(kb, repo, c.certified_for, v.version)
            passed = passed_tests(runs, c.id, v.version) & set(tests)
            out.append(Deadline(id=f"update-{c.id}-{v.version}", company_id=c.id, kind="update", ref=v.version,
                                due=v.valid_from - timedelta(days=1),
                                params={"version": v.version, "tests": len(tests), "passed": len(passed)},
                                done=bool(tests) and len(passed) == len(tests)))
        month = today.replace(day=1)
        for _ in range(PERMANENT_MONTHS):
            sent = [s.created.date() for s in subs if slug(s.vendor or "") == c.id
                    and (s.created.year, s.created.month) == (month.year, month.month)]
            out.append(Deadline(id=f"permanent-{c.id}-{month:%Y-%m}", company_id=c.id, kind="permanent",
                                opened=month, due=_month_end(month), params={"month": f"{month:%Y-%m}"},
                                done=bool(sent), done_on=min(sent) if sent else None))
            month = _add_month(month)
    drafts = sum(1 for t in repo.list_test_cases() if t.status == "draft")
    for v in versions:
        if v.valid_from <= today:
            continue
        out.append(Deadline(id=f"catalogue-{v.version}", kind="catalogue", ref=v.version,
                            due=v.valid_from - timedelta(days=CATALOGUE_LEAD_DAYS),
                            params={"version": v.version, "drafts": drafts}, done=drafts == 0))
        out.append(Deadline(id=f"switch-{v.version}", kind="switch", ref=v.version, due=v.valid_from,
                            params={"version": v.version}))
    return out


def status(d: Deadline, today: date) -> str:
    if d.done:
        return "done"
    if d.due < today:
        return "overdue"
    return "soon" if (d.due - today).days <= SOON_DAYS else "open"


def history(repo) -> list[dict]:
    """How the catalogue evolved: the baseline, every spec upload and every approval, oldest first."""
    out = []
    for e in repo.list_events():
        if e["kind"] == "baseline":
            out.append({"at": e["at"], "kind": "baseline", "version": e.get("version"), "tests": e.get("test_cases")})
        elif e["kind"] == "spec_upload":
            out.append({"at": e["at"], "kind": "spec_upload", "document": e.get("document"),
                        "version": e.get("version"), "valid_from": e.get("valid_from"),
                        "changes": e.get("in_scope"), "drafts": len(e.get("drafts") or []),
                        "flipped": len(e.get("tests_flipped") or [])})
    for a in repo.list_approvals():
        out.append({"at": a["at"], "kind": "approval", "test_case": a["test_case_id"], "decision": a["decision"]})
    return sorted(out, key=lambda x: x["at"])


def view(kb, repo, today: date, company: str | None = None) -> dict:
    """The calendar of all companies, or of one (id or name) for the vendor view."""
    companies = repo.list_companies()
    if company is not None:
        companies = [c for c in companies if company in (c.id, c.name)]
    ids = {c.id for c in companies}
    deadlines = [d for d in repo.list_deadlines() + derived(kb, repo, today)
                 if d.company_id in ids or (company is None and d.company_id is None)]
    rows = [d.model_dump(mode="json") | {"status": status(d, today), "days": (d.due - today).days}
            for d in sorted(deadlines, key=lambda d: (d.due, d.id))]
    runs = repo.list_runs()
    catalogue = [t.id for t in repo.list_test_cases() if t.status == "approved"]

    def first(c: Company) -> dict | None:  # progress of a first certification over the approved catalogue
        if c.certified_for is not None:
            return None
        return {"tests": len(catalogue), "passed": len(passed_tests(runs, c.id) & set(catalogue))}

    return {"today": today.isoformat(),
            "companies": [c.model_dump(mode="json") | {"first_certification": first(c)} for c in companies],
            "deadlines": rows,
            "history": history(repo) if company is None else []}
