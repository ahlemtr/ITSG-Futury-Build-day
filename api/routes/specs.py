"""Spec upload: a new document version starts the pipeline of kg.ingest as a background job."""

from __future__ import annotations

import tempfile
import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from api.routes.common import ai, kb, repo
from engine.signing import sha256
from kg import ingest

router = APIRouter()


@router.post("/spec-versions", status_code=202)
async def upload(request: Request, file: UploadFile = File(...), document: str = Form("VB"),
                 version: str | None = Form(None), valid_from: date | None = Form(None),
                 published: date | None = Form(None)):
    """Version and valid-from date are read from the file name or the first page when not given."""
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "the upload must be a PDF")
    tmp = Path(tempfile.mkdtemp()) / (Path(file.filename or "upload.pdf").name or "upload.pdf")
    tmp.write_bytes(data)
    if version is None or valid_from is None:
        from engine.specdiff import extract_text

        text = extract_text(tmp)
        found = ingest.guess(file.filename or "", text, document=document)
        if (not found.get("version") or not found.get("valid_from")) and ai(request) and text.strip():
            metadata = ai(request).read_document_metadata(file.filename or "", text)
            if metadata:
                for key in ("version", "valid_from"):
                    if getattr(metadata, key):
                        found.setdefault(key, getattr(metadata, key))
        version = version or found.get("version")
        valid_from = valid_from or (date.fromisoformat(found["valid_from"]) if "valid_from" in found else None)
    if not version or not valid_from:
        raise HTTPException(422, "version and valid_from could not be read from the file: please enter them")
    if any(v.version == version for v in kb(request).get_versions(document)):
        raise HTTPException(409, f"{document} {version} is already known")
    job = ingest.new_job(repo(request), document, version, valid_from, file.filename or tmp.name, sha256(data))
    if published:
        job["published"] = published.isoformat()

    app = request.app

    def set_kb(new_kb) -> None:
        app.state.kb = new_kb
        if app.state.ai:
            from llm.services import get_ai

            app.state.ai = get_ai(new_kb)

    def ai_factory(staged_kb):
        if not app.state.ai:
            return None
        from llm.services import AIServices

        return AIServices(staged_kb)

    pipeline = ingest.Pipeline(job, tmp, kb(request), repo(request), ai_factory, set_kb)
    threading.Thread(target=pipeline.run, name=job["id"], daemon=True).start()
    return job


@router.get("/jobs")
def list_jobs(request: Request):
    return repo(request).list_jobs()


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str):
    job = repo(request).get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.get("/kg/events")
def events(request: Request):
    return repo(request).list_events()
