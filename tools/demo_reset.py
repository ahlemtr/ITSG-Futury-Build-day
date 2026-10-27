"""Put the demo back to its start: seed data only, no test runs, no advisor decisions.

python -m tools.demo_reset    (stop the API first; uses DATABASE_URL, KG_BACKEND, NEO4J_*, DATA_DIR)

- Postgres: every app table emptied, then the test case catalogue and the 10 seed submissions are seeded again
  (checked, with the AI triage when OpenAI is available).
- Knowledge graph: advisor precedents removed (Neo4j nodes, or DATA_DIR/precedents.yaml for the YAML backend).
- DATA_DIR: uploaded submission files and the signing key stay out of git; uploads are removed. The LLM cache
  (data/llm_cache/) is kept, so the demo runs offline after one rehearsal.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

TABLES = ["criterion_draft", "approval", "report", "run_step", "run", "check_result", "verdict", "submission_file",
          "submission", "expected_field", "test_step", "test_case"]


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    data = Path(os.environ.get("DATA_DIR", "data"))
    os.environ.setdefault("PRECEDENTS_PATH", str(data / "precedents.yaml"))

    from kg import get_kb
    from llm.services import get_ai
    from store.repo import PgRepo, get_repo
    from store.seed import seed

    shutil.rmtree(data / "submissions", ignore_errors=True)
    (data / "precedents.yaml").unlink(missing_ok=True)

    kb = get_kb()
    if hasattr(kb, "_q"):  # graph backend
        kb._q("MATCH (p:Precedent) DETACH DELETE p")
        print("graph: precedents removed")

    repo = get_repo()
    if isinstance(repo, PgRepo):
        repo.conn.execute(f"TRUNCATE {', '.join(TABLES)} CASCADE")
        print("postgres: tables emptied")
    ai = get_ai(kb)
    print("seeded:", seed(kb, repo, root=data, triage=ai.triage if ai else None))


if __name__ == "__main__":
    main()
