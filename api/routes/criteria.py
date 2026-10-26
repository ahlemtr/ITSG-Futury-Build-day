"""Requirements to criteria (P8.2): extract, score against the ITSG criteria, draft test cases."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.routes.common import ai, repo
from engine.model import CriterionReview
from llm.client import LLMInvalid, LLMUnavailable

router = APIRouter()


class ExtractBody(BaseModel):
    document: str = "VB"
    version: str
    section: str


class ApproveBody(BaseModel):
    approver: str
    decision: str  # approved / rejected
    review: CriterionReview | None = None  # human decision on a 3b proposal, stored with the draft


@router.post("/criteria/extract")
def extract(request: Request, body: ExtractBody):
    if not ai(request):
        raise HTTPException(503, "LLM services disabled")
    decided = {c.id: c.review for c in repo(request).list_criteria() if c.review is not None}
    try:
        res = ai(request).criteria(body.document, body.version, body.section, decided)
    except (LLMUnavailable, LLMInvalid) as e:
        raise HTTPException(503, f"LLM unavailable: {e}")
    for d in res.drafts:
        if repo(request).get_criterion(d.id) is None:
            repo(request).save_criterion(d)
    for t in res.test_cases:
        repo(request).upsert_test_case(t)
    return res.model_dump(mode="json")


@router.post("/criteria/{cid}/approve")
def approve(request: Request, cid: str, body: ApproveBody):
    c = repo(request).get_criterion(cid)
    if c is None:
        raise HTTPException(404, "criterion draft not found")
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(422, "decision must be approved or rejected")
    c.status = body.decision
    if body.review is not None:
        c.review = body.review.model_copy(update={"draft_id": c.id})
    repo(request).save_criterion(c)
    return {"id": c.id, "status": c.status}
