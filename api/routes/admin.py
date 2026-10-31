"""Demo reset from the user menu: the same as `python -m tools.reset_baseline`, as a background
job with stages for the AI overlay. Only from the machine itself (loopback) or with ALLOW_RESET=1."""

from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from api.routes.common import repo

router = APIRouter()

STAGES = ["files", "graph", "store"]
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_lock = threading.Lock()


def allowed(request: Request) -> bool:
    return os.environ.get("ALLOW_RESET") == "1" or (request.client is not None and request.client.host in LOOPBACK)


@router.get("/admin/reset")
def status(request: Request):
    """The last reset job (null when none ran since the API started) and whether a reset is allowed here."""
    return {"allowed": allowed(request), "job": getattr(request.app.state, "reset_job", None)}


@router.post("/admin/reset", status_code=202)
def start(request: Request):
    if not allowed(request):
        raise HTTPException(403, "reset is only allowed on a local setup (or with ALLOW_RESET=1)")
    app = request.app
    with _lock:
        job = getattr(app.state, "reset_job", None)
        if job and job["status"] == "running":
            raise HTTPException(409, "a reset is already running")
        # kept in memory: the reset empties the job tables of the store
        job = {"id": f"reset-{uuid.uuid4().hex[:8]}", "status": "running", "created": datetime.now(UTC).isoformat(),
               "stages": [{"name": n, "status": "waiting", "counts": {}} for n in STAGES], "error": None}
        app.state.reset_job = job

    def stage(name: str, status_: str, **counts) -> None:
        st = next(s for s in job["stages"] if s["name"] == name)
        st["status"], st["counts"] = status_, counts

    def run() -> None:
        from tools.reset_baseline import reset

        try:
            kb, counts = reset(repo(request), stage)
            app.state.kb = kb
            if app.state.ai:
                from llm.services import get_ai

                app.state.ai = get_ai(kb)
            job["result"], job["status"] = counts, "done"
        except Exception as e:  # noqa: BLE001 - reported to the UI
            for s in job["stages"]:
                if s["status"] == "running":
                    s["status"] = "failed"
            job["status"], job["error"] = "failed", f"{type(e).__name__}: {e}"

    threading.Thread(target=run, name=job["id"], daemon=True).start()
    return job
