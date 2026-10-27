"""FastAPI app (P7.4, plan/02 section 6). Thin routes over the engine.

State: `kb` (knowledge base), `repo` (app data), `ai` (LLM services, None when no OpenAI key and no
cache), `data_root` (DATA_DIR). `create_app` takes them as arguments so tests inject the fake KB.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes import builder, catalogue, checking, criteria, overview, runs, specs


def create_app(kb=None, repo=None, ai=None, data_root: Path | None = None, seed: bool = False) -> FastAPI:
    load_dotenv()
    app = FastAPI(title="EEL review assistant", version="0.1.0")
    if kb is None:
        import os

        from kg import get_kb

        # advisor decisions go to DATA_DIR, not into the committed seed file; delete data/ to reset the demo
        os.environ.setdefault("PRECEDENTS_PATH", str(Path(os.environ.get("DATA_DIR", "data")) / "precedents.yaml"))

        kb = get_kb()
    if repo is None:
        from store.repo import get_repo

        repo = get_repo()
    if ai is None:
        from llm.services import get_ai

        ai = get_ai(kb)
    app.state.kb, app.state.repo, app.state.ai = kb, repo, ai
    app.state.data_root = data_root
    if seed:
        from store.seed import seed as do_seed

        do_seed(kb, repo, root=data_root, triage=ai.triage if ai else None)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    for r in (catalogue.router, checking.router, builder.router, runs.router, criteria.router, overview.router, specs.router):
        app.include_router(r)
    return app


def _lazy_app() -> FastAPI:
    import os

    return create_app(seed=os.environ.get("SEED_ON_START", "1") == "1")


_app: FastAPI | None = None


def __getattr__(name: str):  # `uvicorn api.main:app` builds the app on first access
    global _app
    if name == "app":
        if _app is None:
            _app = _lazy_app()
        return _app
    raise AttributeError(name)
