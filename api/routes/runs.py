"""Test runs in rounds: story out, vendor files in, insurer reply back, verdict at the end.

Every accepted upload is also stored as a submission (`run-<id>-r<round>`, all files of the run so far),
so the ITSG view sees the vendor's progress in Submissions, the advisor queue and the reports.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from api.routes.common import ai, kb, repo, test_case
from engine import calendar, intake, runs
from engine.expected import build_chain, load_scenario

router = APIRouter()


class RunBody(BaseModel):
    test_case_id: str
    valid_on: date = date(2027, 1, 1)
    vendor: str | None = None


def _load(request: Request, run_id: str) -> tuple[runs.RunState, dict]:
    doc = repo(request).get_run(run_id)
    if doc is None:
        raise HTTPException(404, "run not found")
    return runs.RunState.model_validate(doc), doc


def _save(request: Request, st: runs.RunState, doc: dict) -> None:
    extras = {k: doc.get(k) for k in ("vendor", "story", "file_names", "plan")}
    repo(request).save_run(st.id, st.model_dump(mode="json") | extras)


def _plan(request: Request, st: runs.RunState) -> list[dict]:
    """Per round: the messages the software must produce and the insurer replies it gets.
    Hidden tests: only the number of rounds."""
    if st.test_case.hidden:
        return [{"round": r} for r in range(1, st.last_round + 1)]
    msgs = build_chain(load_scenario(kb(request), st.test_case), st.version, kb(request)).messages
    return [{"round": r,
             "expects": [m.abgabegrund for m in msgs if m.actor == "employer" and m.round == r],
             "replies": [m.abgabegrund for m in msgs if m.actor == "insurer" and m.round == r]}
            for r in range(1, st.last_round + 1)]


def _public(st: runs.RunState, doc: dict) -> dict:
    hidden = st.test_case.hidden
    rounds = []
    for rr in st.rounds:
        r = rr.model_dump()
        if hidden:  # pass / fail only, never expected values or replies
            r = {"round": rr.round, "ended": rr.ended,
                 "outcomes": [{"rule": o.rule, "outcome": o.outcome} for o in rr.outcomes]}
        rounds.append(r)
    return {"run_id": st.id, "test_case_id": st.test_case.id, "hidden": hidden, "version": st.version,
            "valid_on": st.valid_on.isoformat(), "vendor": doc.get("vendor"), "story": doc.get("story"),
            "round": st.round, "last_round": st.last_round, "status": st.status, "plan": doc.get("plan"),
            "results": rounds}


@router.post("/runs")
def start(request: Request, body: RunBody):
    st, story = runs.start(kb(request), test_case(request, body.test_case_id), body.valid_on)
    if ai(request):
        story = ai(request).story(st.test_case) or story
    doc = {"vendor": body.vendor, "story": story, "file_names": [], "plan": _plan(request, st)}
    _save(request, st, doc)
    calendar.run_started(repo(request), st, body.vendor, date.today())
    return {"rounds": st.last_round, **_public(st, doc)}


@router.get("/runs/{run_id}")
def get_run(request: Request, run_id: str):
    st, doc = _load(request, run_id)
    return _public(st, doc)


@router.post("/runs/{run_id}/submit")
async def submit(request: Request, run_id: str, files: list[UploadFile] = File(default=[]),
                 vendor: str | None = Form(None)):
    st, doc = _load(request, run_id)
    if st.status != "open":
        raise HTTPException(409, f"run is {st.status}")
    doc["vendor"] = doc.get("vendor") or vendor
    new = {(f.filename or f"file{n}"): await f.read() for n, f in enumerate(files)}
    receipt = None
    if new:
        names = (doc.get("file_names") or []) + list(new)
        so_far = dict(zip(doc.get("file_names") or [], (t.encode("utf-8") for t in st.files))) | new
        rec = intake.receive(kb(request), repo(request), so_far, st.test_case.id, valid_on=st.valid_on,
                             vendor=doc.get("vendor"), submission_id=f"run-{st.id[:8]}-r{st.round + 1}",
                             content=f"test run {st.id}, round {st.round + 1}", root=request.app.state.data_root)
        receipt = rec.model_dump()
        receipt["files"] = [f for f in receipt["files"] if f["name"] in new]
        if rec.status == "rejected":  # a rejected file is not judged and does not use up the round
            return {"status": st.status, "receipt": receipt, "round": st.round + 1, "rejected": True}
        doc["file_names"] = names
    try:
        res = runs.submit(kb(request), st, list(new.values()))
    except ValueError as e:
        raise HTTPException(409, str(e))
    if receipt:
        triage = ai(request).triage if ai(request) else None
        repo(request).save_check(receipt["submission_id"], runs.check_so_far(kb(request), st, triage=triage))
    _save(request, st, doc)
    calendar.round_accepted(repo(request), st, doc.get("vendor"), date.today())
    out = res.model_dump()
    if st.test_case.hidden:  # pass / fail only
        out = {"round": res.round, "ended": res.ended,
               "outcomes": [{"rule": o.rule, "outcome": o.outcome} for o in res.outcomes]}
    return {"status": st.status, "receipt": receipt, **out}


@router.get("/runs/{run_id}/verdict")
def verdict(request: Request, run_id: str):
    return runs.verdict(_load(request, run_id)[0])
