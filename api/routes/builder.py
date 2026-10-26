"""Test builder routes: spec diff, boundaries, clones, hidden variants, approvals, packages."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from api.routes.common import ai, kb, real_versions, repo, test_case
from engine import builder, specdiff

router = APIRouter()


class SpecdiffBody(BaseModel):
    document: str = "VB"
    old_version: str
    new_version: str


class BoundariesBody(BaseModel):
    rule_id: str
    base_test_case_id: str
    version: str | None = None


class CloneBody(BaseModel):
    base_id: str
    branch_point: date | None = None
    change: dict[str, Any]
    new_id: str | None = None


class HiddenBody(BaseModel):
    test_case_id: str
    seed: int = 0


class ApproveBody(BaseModel):
    approver: str
    decision: str  # approved / rejected


def _store(request: Request, tcs):
    for t in tcs:
        repo(request).upsert_test_case(t)
    return [t.model_dump(mode="json") for t in tcs]


@router.post("/specdiff")
def spec_diff(request: Request, body: SpecdiffBody):
    k = kb(request)
    changes = k.get_changes(body.document, body.old_version, body.new_version, in_scope_only=True)
    imp = specdiff.impact(changes, k)
    rec = builder.recompute(k, [k.get_test_case(t.id) for t in imp.tests], body.old_version, body.new_version)
    out = {"changes": [c.model_dump() for c in changes],
           "recompute": [r.id for r in imp.recompute], "review": [r.id for r in imp.review],
           "tests": [t.model_dump() for t in imp.tests],
           "recomputed": [r.model_dump(mode="json") for r in rec],
           "changed_tests": [r.id for r in rec if r.differs]}
    if ai(request):
        out["agent"] = ai(request).spec_update(body.document, body.old_version, body.new_version)
    return out


@router.post("/builder/boundaries")
def boundaries(request: Request, body: BoundariesBody):
    try:
        tcs = builder.boundaries(kb(request), body.rule_id, test_case(request, body.base_test_case_id))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _store(request, tcs)


@router.post("/builder/clone")
def clone(request: Request, body: CloneBody):
    tc = builder.clone(kb(request), test_case(request, body.base_id), body.branch_point, body.change, body.new_id)
    return _store(request, [tc])[0]


@router.post("/builder/hidden")
def hidden(request: Request, body: HiddenBody):
    tc = builder.hidden(kb(request), test_case(request, body.test_case_id), body.seed)
    _store(request, [tc])
    return {"id": tc.id, "hidden": True, "parent": tc.parent, "status": tc.status}  # never the expected values


@router.post("/test-cases/{id_}/approve")
def approve(request: Request, id_: str, body: ApproveBody):
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(422, "decision must be approved or rejected")
    tc = test_case(request, id_)
    repo(request).upsert_test_case(tc)
    tc = repo(request).approve(id_, body.approver, body.decision)
    return {"id": tc.id, "status": tc.status}


@router.get("/test-cases/{id_}/package")
def package(request: Request, id_: str, version: str | None = None):
    tc = test_case(request, id_)
    if tc.hidden:
        raise HTTPException(403, "hidden test cases are never exported")
    version = version or real_versions(request)[-1]
    story = ai(request).story(tc) if ai(request) else None
    files = builder.package(kb(request), tc, version, story)
    return Response(builder.package_zip(files), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{id_}-{version}.zip"'})
