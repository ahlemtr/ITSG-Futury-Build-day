# EEL Review Assistant

Test platform for ITSG's system review of payroll software, scoped to income replacement benefits (Entgeltersatzleistungen, EEL). Won the Futury Hackathon 2026 × ITSG. Next milestone: live demo to the GKV and ITSG on **11 December 2026**, pilot likely after.

Read `PROJECT_REPORT.md` first: what exists, promised vs. delivered (section 5), decisions in force (6), decisions for December (9), open questions for ITSG.

## Layout

`engine/` parser, rules, checker, builder, runs, report + signing · `kg/` knowledge graph (seed, extraction, YAML + Neo4j backends, upload pipeline) · `llm/` OpenAI client and agents · `store/` Postgres / in-memory repo · `api/` FastAPI · `ui/` React + Vite · `layouts/` record layouts · `sources/` spec documents · `tools/` CLI tools · `tests/` pytest.

## Run and check

```
./dev.ps1 [-Reset]                     # Windows: Postgres + Neo4j (Docker), API :8000, UI :5173
uv run pytest -q                       # graph tests need NEO4J_TESTS=1 and a full graph
uv run ruff check .
cd ui && npm run build && npm run check:i18n
```

Without Docker: `DATABASE_URL= uv run uvicorn api.main:app --port 8000` (in-memory store, YAML knowledge base).
Known: `tests/test_annex_evidence.py::test_vb_annex_centered_chapters_work_with_linux_poppler_indentation` fails on Windows (`pdftotext` indentation); `uvicorn --reload` hangs on Windows.

## Rules of the codebase

- The AI never computes or writes: agents answer in a fixed schema with citations that must resolve to real passage keys; code validates and writes. Dates, day counts and expected results come from the deterministic engine.
- Every check picks its rule set by the case's validity date, never "latest".
- Parameters are versioned with the Verfahrensbeschreibung; a Rundschreiben only proposes values.
- UI is German only (legal terms stay German). OpenAI stays the provider. Only test data goes through the platform.
- Keep `kg/build/` (paid embeddings) and `data/llm_cache/`; changing prompt text invalidates cached answers.
- Git: fork of `ahlemtr/ITSG-Futury-Build-day`, one branch + PR per feature into her `main`.
