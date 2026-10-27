"""Put the platform back to its starting point: seed data only, no test runs, no advisor decisions.

python -m tools.reset_baseline    (stop the API first; uses DATABASE_URL, KG_BACKEND, NEO4J_*, DATA_DIR)
The API runs the same `reset` from the user menu ("Alles zurücksetzen", POST /admin/reset).

- Files: uploaded submission files, uploaded spec versions (DATA_DIR/ingested) and advisor precedents are removed.
  The LLM cache (DATA_DIR/llm_cache/) and the embeddings (kg/build/embeddings.jsonl) are kept, so the demo runs
  offline after one rehearsal.
- Knowledge graph: Neo4j emptied and loaded again at the baseline (`kg.build --skip-extract --fresh`); the YAML
  backend is simply read again without the overlays.
- Store: every app table emptied, then the test case catalogue, the companies and (without SPEC_BASELINE) the
  10 seed submissions are seeded again (checked, with the AI triage when OpenAI is available).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# stage(name, status, **counts): progress for the API job; the command line prints it
Stage = Callable[..., None]


def data_dir() -> Path:
    data = Path(os.environ.get("DATA_DIR", "data") or "data")
    return data if data.is_absolute() else ROOT / data


def reset(repo, stage: Stage = lambda *a, **k: None):
    """Returns the knowledge base at the baseline and the seed counts."""
    from kg import get_kb
    from llm.services import get_ai
    from store.seed import seed

    data = data_dir()
    os.environ.setdefault("PRECEDENTS_PATH", str(data / "precedents.yaml"))

    stage("files", "running")
    shutil.rmtree(data / "submissions", ignore_errors=True)
    shutil.rmtree(data / "ingested", ignore_errors=True)  # uploaded spec versions: back to the baseline only
    (data / "precedents.yaml").unlink(missing_ok=True)
    stage("files", "done")

    stage("graph", "running")
    if os.environ.get("KG_BACKEND", "yaml") == "graph":
        from kg import build

        if build.main(["--skip-extract", "--fresh"]) != 0:
            raise RuntimeError("kg.build failed (validation errors)")
    kb = get_kb()
    stage("graph", "done", versions=len([v for v in kb.get_versions("VB") if not v.version.startswith("sim")]))

    stage("store", "running")
    repo.clear()
    ai = get_ai(kb)
    counts = seed(kb, repo, root=data, triage=ai.triage if ai else None)
    baseline = os.environ.get("SPEC_BASELINE", "")
    if baseline:
        doc, version = baseline.split("@")
        repo.add_event("baseline", {"document": doc, "version": version, "test_cases": counts["test_cases"]})
    stage("store", "done", **counts)
    return kb, counts


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    from store.repo import get_repo

    _, counts = reset(get_repo(), stage=lambda name, status, **c: print(f"{name}: {status}", c or ""))
    print("seeded:", counts)


if __name__ == "__main__":
    main()
