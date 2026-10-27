"""Vendor files in, verdicts out: intake, check, side-by-side diff, advisor queue, decisions, reports."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from api.routes.common import ai, kb, real_versions, repo, test_case
from engine import intake, layouts, report, signing
from engine.checker import Checker
from engine.diff import Differ
from engine.expected import build_chain, load_scenario
from engine.model import Precedent
from engine.records import format_value, parse_file
from engine.rules import params as params_mod

router = APIRouter()


class CheckBody(BaseModel):
    valid_on: date
    test_case_id: str | None = None
    files: list[str] = []
    submission_id: str | None = None


class DecideBody(BaseModel):
    label: str
    reason: str
    advisor: str
    citations: list[str] = []


def _submission(request: Request, sid: str):
    s = repo(request).get_submission(sid)
    if s is None:
        raise HTTPException(404, f"submission {sid} not found")
    return s


def run_check(request: Request, test_case_id: str, files: list, valid_on: date):
    tc = test_case(request, test_case_id)
    triage = ai(request).triage if ai(request) else None
    return Checker(kb(request)).check(tc, files, valid_on, triage=triage)


@router.post("/check")
def check(request: Request, body: CheckBody):
    if body.submission_id:
        s = _submission(request, body.submission_id)
        res = run_check(request, s.test_case_id, list(intake.load_files(s).values()), body.valid_on)
        repo(request).save_check(s.id, res)
        return {"submission_id": s.id, **res.model_dump(mode="json")}
    if not body.test_case_id:
        raise HTTPException(422, "test_case_id or submission_id required")
    return run_check(request, body.test_case_id, body.files, body.valid_on).model_dump(mode="json")


@router.post("/submissions")
async def submit(request: Request, test_case_id: str = Form(...), valid_on: date | None = Form(None),
                 vendor: str | None = Form(None), files: list[UploadFile] = File(default=[])):
    test_case(request, test_case_id)
    data = {f.filename or f"file{n}": await f.read() for n, f in enumerate(files)}
    rec = intake.receive(kb(request), repo(request), data, test_case_id, valid_on=valid_on, vendor=vendor,
                         root=request.app.state.data_root)
    return rec.model_dump()


def _rounds_total(request: Request, test_case_id: str, version: str | None) -> int:
    """Rounds of the test run: employer rounds plus an import-only round after the last insurer reply."""
    from engine.runs import _rounds

    tc = test_case(request, test_case_id)
    msgs = build_chain(load_scenario(kb(request), tc), version or real_versions(request)[-1], kb(request)).messages
    return _rounds(msgs, tc.steps)


@router.get("/submissions")
def list_submissions(request: Request, test_case_id: str | None = None):
    out, rounds = [], {}
    for s in sorted(repo(request).list_submissions(test_case_id), key=lambda x: x.created, reverse=True):
        res = repo(request).get_check(s.id)
        key = (s.test_case_id, s.rule_set_version)
        if key not in rounds:
            rounds[key] = _rounds_total(request, *key)
        out.append({**s.model_dump(mode="json", exclude={"files"}), "files": [f.name for f in s.files],
                    "label": res.label if res else None, "deviations": len(res.deviations) if res else None,
                    "rounds_total": rounds[key]})
    return out


@router.get("/submissions/{sid}/check")
def stored_check(request: Request, sid: str):
    """The stored check result (advisor decisions included); checks once when there is none yet."""
    s = _submission(request, sid)
    res = repo(request).get_check(sid)
    if res is None:
        res = run_check(request, s.test_case_id, list(intake.load_files(s).values()), s.valid_on or date.today())
        repo(request).save_check(sid, res)
    return {"submission_id": sid, **res.model_dump(mode="json")}


@router.get("/submissions/{sid}/diff")
def side_by_side(request: Request, sid: str, valid_on: date | None = None):
    """Model solution vs vendor file, field by field, with compare modes and labels. Also the plain
    all-field diff count (what a value comparison like today's would report)."""
    s = _submission(request, sid)
    valid_on = valid_on or s.valid_on
    res = repo(request).get_check(sid) or run_check(request, s.test_case_id, list(intake.load_files(s).values()),
                                                    valid_on)
    version = res.version
    k = kb(request)
    ch = build_chain(load_scenario(k, test_case(request, s.test_case_id)), version, k)
    actual = [m for f in intake.load_files(s).values() for m in parse_file(f, k, version).messages]
    differ = Differ(k, version)
    pairs, missing, extra = differ.match(ch.employer(), actual)
    labels = {(d.step, d.record, (d.field or "")): d.label for d in res.deviations}
    steps, plain = [], 0
    for m, r in pairs:
        rows = []
        for blk in ["DSLW"] + [b for b in layouts.get(k, "DSLW", version).block_order if b in m.blocks or b in r.blocks]:
            lay = layouts.get(k, blk, version)
            exp_vals = m.head if blk == "DSLW" else m.blocks.get(blk)
            act_vals = r.head if blk == "DSLW" else (r.blocks[blk].fields if blk in r.blocks else None)
            for f in lay.fields:
                ev = exp_vals.get(f.name, f.constant) if exp_vals is not None else None
                if lay.repeating_group and f.name == lay.repeating_group.count_field and exp_vals is not None:
                    ev = len(exp_vals.get("groups", []))  # the writer derives the count from the groups
                e = format_value(f, ev) if exp_vals is not None else None
                if blk == "DSLW" and f.name.startswith("MM-"):
                    e = None
                a = act_vals[f.name].raw if act_vals and f.name in act_vals else None
                same = e == a or e is None
                plain += 0 if same else 1
                rows.append({"record": blk, "field": f.name, "mode": f.compare_mode, "expected": e, "actual": a,
                             "same": same, "label": labels.get((m.step, blk, f.name))})
            if lay.repeating_group and blk in m.blocks and blk in r.blocks:
                eg, ag = m.blocks[blk].get("groups", []), r.blocks[blk].groups
                for n in range(max(len(eg), len(ag))):
                    for f in lay.repeating_group.fields:
                        e = format_value(f, eg[n].get(f.name)) if n < len(eg) else None
                        a = ag[n][f.name].raw if n < len(ag) else None
                        plain += 0 if e == a else 1
                        rows.append({"record": blk, "field": f"{f.name}-{n + 1}", "mode": f.compare_mode,
                                     "expected": e, "actual": a, "same": e == a,
                                     "label": labels.get((m.step, blk, "BEGINN-AU"))})
        steps.append({"step": m.step, "abgabegrund": m.abgabegrund, "fields": rows})
    plain += len(missing) + len(extra)
    return {"submission_id": sid, "version": version, "label": res.label, "steps": steps,
            "missing": [m.step for m in missing], "extra": [r.abgabegrund for r in extra],
            "plain_diff_count": plain, "labeled_deviations": len(res.deviations),
            "by_label": res.counts, "resolved_by": res.resolved_by}


@router.get("/advisor/queue")
def advisor_queue(request: Request):
    out = []
    for s in repo(request).list_submissions():
        res = repo(request).get_check(s.id)
        for d in res.deviations if res else []:
            if d.label == "unclear" and d.resolved_by != "advisor":
                out.append({"submission_id": s.id, "test_case_id": s.test_case_id, **d.model_dump(mode="json"),
                            "signature": d.signature})
    return out


def _justifications(k, refs: list[str]) -> list[str]:
    """Rule ids and passage keys the KB knows (it rejects a precedent justified by anything else)."""
    out = []
    for ref in dict.fromkeys(refs):
        try:
            if "#" in ref:
                k.get_passage(ref)
            elif not any(r.id == ref for ag in ("41", "61", "62", "01", "88") for r in k.get_rules(ag, params_mod.latest(k))):
                continue
            out.append(ref)
        except KeyError:
            continue
    return out


@router.post("/deviations/{dev_id}/decide")
def decide(request: Request, dev_id: str, body: DecideBody):
    found = repo(request).find_deviation(dev_id)
    if not found:
        raise HTTPException(404, "deviation not found")
    if body.label not in ("correct_variant", "bug", "invalid"):
        raise HTTPException(422, "label must be correct_variant, bug or invalid")
    sid, d = found
    cites = body.citations or (d.ai_proposal.citations if d.ai_proposal else []) or d.sources
    p = Precedent(abgabegrund=d.abgabegrund or "", field=d.field_key, kind=d.kind, verdict=body.label,
                  reason=body.reason, advisor=body.advisor, decided=datetime.now(UTC).date(),
                  justified_by=_justifications(kb(request), ([d.rule] if d.rule else []) + cites))
    kb(request).add_precedent(p)
    stored = kb(request).find_precedent(d.signature)  # the KB normalises the field key
    p = stored or p
    d.label, d.resolved_by, d.precedent_key = body.label, "advisor", p.key
    d.explanation = f"advisor {body.advisor}: {body.reason}"
    repo(request).update_deviation(sid, d)
    return {"deviation": d.model_dump(mode="json"), "precedent": p.model_dump(mode="json")}


@router.get("/submissions/{sid}/report")
def get_report(request: Request, sid: str, format: str = "json"):
    s = _submission(request, sid)
    res = repo(request).get_check(sid)
    if res is None:
        res = run_check(request, s.test_case_id, list(intake.load_files(s).values()),
                        s.valid_on or date.today())
        repo(request).save_check(sid, res)
    explanations = {}
    if ai(request):
        for d in res.deviations:
            if d.label in ("bug", "invalid"):
                explanations[d.id] = ai(request).explain(d) or d.explanation
    tc = test_case(request, s.test_case_id)
    chain = [m.abgabegrund for m in build_chain(load_scenario(kb(request), tc), res.version, kb(request)).messages]
    rep = report.build(res, sid, intake.load_files(s), kb(request), vendor=s.vendor, product_id=s.product_id,
                       chain=chain, explanations=explanations)
    signed = signing.sign(rep.model_dump(mode="json"))
    repo(request).save_report(sid, signed)
    if format == "html":
        return HTMLResponse(report.render_html(signed))
    if format == "pdf":
        try:
            return Response(report.render_pdf(report.render_html(signed)), media_type="application/pdf")
        except RuntimeError as e:
            raise HTTPException(501, str(e))
    return signed


@router.get("/reports")
def list_reports(request: Request, vendor: str | None = None):
    """Checked submissions with their report status; the report is signed when it is first opened."""
    out = []
    for s in sorted(repo(request).list_submissions(), key=lambda x: x.created, reverse=True):
        res = repo(request).get_check(s.id)
        if res is None or (vendor and s.vendor != vendor):
            continue
        signed = repo(request).get_report(s.id)
        out.append({"submission_id": s.id, "test_case_id": s.test_case_id, "vendor": s.vendor,
                    "rule_set_version": res.version, "label": res.label, "created": s.created.isoformat(),
                    "signed": signed["report"]["created"] if signed else None})
    return out


@router.post("/reports/verify")
async def verify(request: Request):
    return {"valid": signing.verify_bytes(await request.body())}


def version_for(request: Request, valid_on: date) -> str:
    return params_mod.version_on(kb(request), valid_on)
