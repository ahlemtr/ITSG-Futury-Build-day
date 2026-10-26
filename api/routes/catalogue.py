"""Read-only catalogue routes: parse, versions, rules, test cases, passages, graph."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from api.routes.common import kb, real_versions, repo, test_case
from engine.expected import build_chain, get_case, load_scenario
from engine.records import parse_file

router = APIRouter()


@router.post("/parse")
async def parse(request: Request, file: UploadFile = File(...)):
    pf = parse_file(await file.read(), kb(request))
    return {"encoding": pf.encoding,
            "records": [{"kind": r.kind, "line": r.line_no, "abgabegrund": r.abgabegrund,
                         "fields": {k: (None if v is None else str(v)) for k, v in r.values().items()}}
                        for r in pf.records if r.kind],
            "issues": [i.model_dump() for i in pf.issues]}


@router.get("/versions")
def versions(request: Request, document: str = "VB"):
    return [v.model_dump(mode="json") for v in kb(request).get_versions(document)]


@router.get("/rules")
def rules(request: Request, version: str):
    out: dict[str, dict] = {}
    for ag in ("41", "61", "62", "01", "88"):
        for r in kb(request).get_rules(ag, version):
            out.setdefault(r.id, r.model_dump())
    params = {}
    for r in out.values():
        for p in r["params"]:
            params[p] = kb(request).get_param(p, version=version)
    return {"version": version, "rules": list(out.values()), "params": params}


@router.get("/test-cases")
def list_test_cases(request: Request, kind: str | None = None, hidden: bool | None = None):
    items = repo(request).list_test_cases(kind=kind, hidden=hidden)
    if not items:
        items = [get_case(kb(request), t.key) for t in kb(request).get_test_cases(include_hidden=hidden is not False)
                 if (kind is None or t.kind == kind) and (hidden is None or t.hidden == hidden)]
    return [{"id": t.id, "kind": t.kind, "origin": t.origin, "status": t.status, "hidden": t.hidden,
             "parent": t.parent, "targets": t.targets, "steps": t.steps} for t in items]


@router.get("/test-cases/{id_}")
def get_test_case(request: Request, id_: str):
    tc = test_case(request, id_)
    sc = load_scenario(kb(request), tc)
    chains = {}
    for v in real_versions(request):
        ch = build_chain(sc, v, kb(request))
        chains[v] = [{"step": m.step, "round": m.round, "actor": m.actor, "abgabegrund": m.abgabegrund, "note": m.note}
                     for m in ch.messages]
    files = [s.id for s in repo(request).list_submissions(id_)]
    return {"test_case": tc.model_dump(mode="json"), "parent": tc.parent, "chains": chains, "submissions": files}


@router.get("/test-cases/{id_}/expected")
def expected(request: Request, id_: str, version: str):
    tc = test_case(request, id_)
    if tc.hidden:
        raise HTTPException(403, "expected results of hidden tests are not shown")
    ch = build_chain(load_scenario(kb(request), tc), version, kb(request))
    return ch.model_dump(mode="json")


@router.get("/passages/search")
def search(request: Request, q: str, k: int = 5):
    return [p.model_dump() for p in kb(request).search_passages(q, k)]


@router.get("/passages/{doc}/{version}/{section:path}")
def passage(request: Request, doc: str, version: str, section: str):
    try:
        return kb(request).get_passage(f"{doc}@{version}#{section}").model_dump()
    except KeyError:
        raise HTTPException(404, "passage not found")


@router.get("/graph/subgraph")
def subgraph(request: Request, label: str, key: str, depth: int = 1):
    return kb(request).subgraph(label, key, depth).model_dump()
