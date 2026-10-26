# Tech stack

Everything we use, in one place. Other plan files refer here. If a library is not on this list, ask the team before adding it.

## 1. Overview

```
Browser (React)  ──HTTP/JSON──>  FastAPI (Python)
                                   ├── engine/   parser, writer, rules, diff, checker, runs, report
                                   ├── llm/      OpenAI agents + tools
                                   ├── kg/       knowledge graph interface ── Neo4j (or YAML fallback)
                                   └── store/    app data ── Postgres
                                 files on disk: data/ (uploads, generated files, reports)
```

All of it runs with Docker Compose on the team VM.

## 2. Backend

| Purpose | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | |
| Package manager | `uv` with `pyproject.toml` | `uv sync`, `uv run pytest` |
| API | FastAPI + Uvicorn | |
| Models and validation | Pydantic v2 | shared models in `engine/model.py` |
| YAML | PyYAML | layouts, seed files, scenarios |
| Dates | python-dateutil (`relativedelta`) | calendar months, `03` section 1 |
| App database | Postgres 16, driver `psycopg` (v3) | tables in `diagrams/07_data_model.md` |
| File storage | VM disk under `data/` | SHA-256 per file |
| PDF text | poppler `pdftotext` (system tool), `pdfplumber` as fallback | spec diff and passages |
| Word files | `python-docx` | HINWEISE, BVORERK (`08` section 5.4) |
| HTML report | Jinja2 | |
| PDF report | WeasyPrint | renders the HTML report |
| Signing | `cryptography` (Ed25519), `hashlib` (SHA-256) | |
| HTTP client (tests) | `httpx` | API tests |
| Tests | pytest | |
| Lint and format | ruff | |

## 3. LLM (OpenAI)

| Purpose | Choice |
|---|---|
| SDK | official `openai` Python SDK |
| Chat model | set by `OPENAI_MODEL` in `.env` (a current GPT model that supports Structured Outputs and function calling) |
| Output format | Structured Outputs: every LLM answer is JSON validated against a Pydantic model; invalid answer = retry once, then fail |
| Tool use | function calling: the agent calls our Python functions to read data and do exact calculations |
| Embeddings | `text-embedding-3-small` (1536 dimensions), set by `OPENAI_EMBED_MODEL` |
| Cache | every LLM and embedding call cached by sha256 of its input in `data/llm_cache/`, so the demo runs offline after one run |

### 3.1 What the LLM does

| Agent | Input | Does | Output | Who confirms |
|---|---|---|---|---|
| **Spec-update agent** | a new spec version | reads the diff, the affected rules and the existing test cases through tools; decides per change: no change / update test / new test; drafts the test case and the curated change | draft test cases + draft changes | ITSG approves before use |
| **Check agent** | a vendor submission | reads the parsed files and the diff against the solution through tools; for each deviation proposes correct variant / bug / invalid / unclear with a citation; drafts the report | draft labels + draft report | advisor confirms and sends |
| **Explain** | one verdict | plain-language explanation with rule id and section | text | none (display only) |
| **Story** | a scenario | TA-style test story | text | part of the test approval |

### 3.2 Rules for every agent

1. Dates, day counts and rule results come from tool calls into the deterministic engine, never from the model's own arithmetic.
2. Every proposal cites at least one passage key (`VB@13.4#3.12/chaining`); answers without a citation are rejected.
3. Agent output is always a draft. A human approves test cases; an advisor confirms labels and reports.

### 3.3 Tools the agents can call

The knowledge graph tools are the methods of `kg/interface.py` (`08` section 13): `get_layout`, `get_rules`, `get_param`, `get_passage`, `search_passages`, `get_versions`, `get_changes`, `get_affected_rules`, `get_test_cases`, `get_test_case`, `get_deviation_context`, `find_precedent`.

Engine tools (deterministic code in `engine/`):

| Tool | Does |
|---|---|
| `parse_file(file_id)` | parsed records and parse issues |
| `expected_result(test_case_id, version)` | the rules engine's expected 41 decision, periods, EFZ end, chain |
| `evaluate_rule(rule_id, test_case_id, version, vendor_values)` | pass or fail with a trace |
| `diff_submission(submission_id)` | 3-level diff with compare modes |
| `add_months(date, n)`, `count_days(start, end)` | exact date math |

`add_precedent` is not a tool: only the advisor's decision in the API writes precedents.

## 4. Knowledge graph

| Purpose | Choice |
|---|---|
| Graph database | Neo4j 5 Community (`neo4j:5.26-community`), APOC plugin |
| Driver | official `neo4j` Python driver |
| Search | full-text index (German analyzer) + vector index on `Passage.embedding` |
| Fallback | `kg/yaml_backend.py` reading `kg/seed/` and `layouts/`, selected by `KG_BACKEND=yaml` |

How to seed it: `08_KG_SEEDING_GUIDE.md`.

## 5. Frontend

| Purpose | Choice |
|---|---|
| Framework | React 18 + TypeScript |
| Build | Vite |
| Styling | Tailwind CSS |
| Data fetching | TanStack Query |
| Routing | React Router |
| Diagrams in the UI | Mermaid (chain timeline), Cytoscape.js (graph subgraph view) |

Views: vendor (story, upload, receipt, replies, verdict, signed report) and ITSG (catalogue, spec diff, test approvals, advisor queue, side-by-side diff).

## 6. Infrastructure

| Purpose | Choice |
|---|---|
| Run | Docker Compose on the team VM: `api`, `web`, `postgres`, `neo4j` |
| Secrets | `.env` (never committed), `.env.example` committed |
| Version control | GitHub repo, one branch per milestone, PR into `main` |

## 7. Environment variables

| Name | Example | Used by |
|---|---|---|
| `OPENAI_API_KEY` | | llm, kg/embed |
| `OPENAI_MODEL` | | llm |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | kg/embed, search |
| `DATABASE_URL` | `postgresql://eel:eel@postgres:5432/eel` | store |
| `NEO4J_URI` | `bolt://neo4j:7687` | kg |
| `NEO4J_USER` | `neo4j` | kg |
| `NEO4J_PASSWORD` | | kg |
| `KG_BACKEND` | `yaml` or `graph` | kg |
| `SIGNING_KEY_PATH` | `data/keys/ed25519.pem` | engine/signing |
| `DATA_DIR` | `data` | intake, reports |

## 8. Python packages (pyproject)

Runtime: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pyyaml`, `python-dateutil`, `psycopg[binary]`, `neo4j`, `openai`, `python-docx`, `pdfplumber`, `jinja2`, `weasyprint`, `cryptography`, `python-multipart`, `python-dotenv`.

Dev: `pytest`, `httpx`, `ruff`.

System: `poppler-utils` (for `pdftotext`) and the WeasyPrint system libraries (Pango) in the API Docker image.
