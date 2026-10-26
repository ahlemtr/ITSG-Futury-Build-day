"""Test runs in rounds: story out, vendor files in, insurer reply back, verdict at the end."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from api.routes.common import ai, kb, repo, test_case
from engine import runs

router = APIRouter()


class RunBody(BaseModel):
    test_case_id: str
    valid_on: date = date(2027, 1, 1)
    vendor: str | None = None


def _load(request: Request, run_id: str) -> runs.RunState:
    doc = repo(request).get_run(run_id)
    if doc is None:
        raise HTTPException(404, "run not found")
    return runs.RunState.model_validate(doc)


@router.post("/runs")
def start(request: Request, body: RunBody):
    st, story = runs.start(kb(request), test_case(request, body.test_case_id), body.valid_on)
    if ai(request):
        story = ai(request).story(st.test_case) or story
    repo(request).save_run(st.id, st.model_dump(mode="json") | {"vendor": body.vendor})
    return {"run_id": st.id, "story": story, "rounds": st.last_round}


@router.post("/runs/{run_id}/submit")
async def submit(request: Request, run_id: str, files: list[UploadFile] = File(default=[])):
    st = _load(request, run_id)
    try:
        res = runs.submit(kb(request), st, [await f.read() for f in files])
    except ValueError as e:
        raise HTTPException(409, str(e))
    repo(request).save_run(st.id, st.model_dump(mode="json"))
    out = res.model_dump()
    if st.test_case.hidden:  # pass / fail only
        out["outcomes"] = [{"rule": o.rule, "outcome": o.outcome} for o in res.outcomes]
    return {"status": st.status, **out}


@router.get("/runs/{run_id}/verdict")
def verdict(request: Request, run_id: str):
    return runs.verdict(_load(request, run_id))
