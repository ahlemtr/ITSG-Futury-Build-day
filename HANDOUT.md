# HANDOUT: backend implementation status (for the next teammate and their Claude)

Plan implemented: `BACKEND_IMPLEMENTATION_PLAN.md`, phases P0 to P8. Source of truth for details: `plan/02`, `03`, `05`, `06`, `08`, `09`. State on 2026-10-27. Nothing is committed yet (branch `backend`).

## How to run

```
UV_LINK_MODE=copy uv sync      # copy mode needed on OneDrive (hardlinks fail)
uv run pytest -q               # 130 tests, about 10 s, no network, no database
uv run ruff check .
```

The API needs a knowledge base. Until the KG teammate's `kg/yaml_backend.py` exists, `kg.get_kb()` fails, so start the app with the fake KB from Python:

```python
from api.main import create_app
from store.repo import MemoryRepo
from tests.fakes.fake_kb import FakeKB
app = create_app(kb=FakeKB(), repo=MemoryRepo(), ai=False, seed=True)   # serve with uvicorn.run(app)
```

With the real KG: `uvicorn api.main:app` (reads `KG_BACKEND`, `DATABASE_URL`, `SEED_ON_START=1` seeds on start). Docker: `docker compose up` (api, postgres, neo4j). Docker was not running on this machine, so the image and Postgres were never started.

## Status per phase

| Phase | Files | Status |
|---|---|---|
| P0 setup and contract | `pyproject.toml`, `.env.example`, `Dockerfile`, `docker-compose.yml`, `engine/model.py`, `kg/interface.py`, `kg/__init__.py`, `tests/fakes/fake_kb.py` | done (Docker not built) |
| P1 parser, writer | `engine/records.py` | done: ITSG file round-trips byte-identical, UTF-8 and Latin-1, issues as data |
| P2 rules engine | `engine/rules/params.py`, `vorerkrankung.py`, `formats.py` | done: all plan/03 section 9 rows under 13.3, 13.4, sim-13.5 |
| P3 scenarios, chains | `engine/expected.py`, `engine/writer_messages.py`, `fixtures/scenarios/peter.yaml`, `tools/make_submissions.py` | done: Peter 7-message chain, EFZ 30.03 / 27.03, generated 41 byte-identical to ITSG's |
| P4 rule checker | `engine/diff.py`, `engine/checker.py`, `engine/variants.py`, `engine/data/variants.yaml` | done: all 10 seed submissions get their plan/02 section 7 label and rule |
| P5 spec diff, builder, runs | `engine/specdiff.py`, `engine/builder.py`, `engine/runs.py` | done: spec diff on the real PDFs, recompute, boundaries, clone, package, hidden, 4 rounds for Peter |
| P6 report, signing | `engine/report.py`, `engine/signing.py`, `templates/report.html.j2` | done: JSON + HTML + Ed25519; PDF code present, untested (WeasyPrint needs Pango, only in the Docker image) |
| P7 store, seed, API, intake | `store/schema.sql`, `store/repo.py`, `store/seed.py`, `engine/intake.py`, `api/main.py`, `api/routes/*` | done with `MemoryRepo`; `PgRepo` written but never run against Postgres |
| P8 LLM | `llm/client.py`, `llm/tools.py`, `llm/services.py`, `llm/explain.py`, `llm/story.py`, `llm/extract.py`, `llm/agents/*`, `engine/criteria.py`, `api/routes/criteria.py` | done against a scripted fake transport; **never called the real OpenAI API** |
| P9 real KG | | not started: needs the KG teammate's K11 |
| P10 TA 167 | | not started (stretch) |

## Done criteria (BACKEND_IMPLEMENTATION_PLAN.md section 5)

- [x] ITSG's TEEL0 file parses and round-trips byte-identical
- [x] all rows of the plan/03 test tables pass under 13.3, 13.4 and sim-13.5
- [x] Peter's full chain is generated (TEEL0 + TEEK0) and checks all green
- [x] every seed submission gets its expected label
- [x] `s-no-contact` goes through AI proposal, advisor decision, and is resolved by precedent on re-check (with the fake LLM)
- [x] Peter runs as 4 rounds through `/runs`, a hidden variant returns only pass/fail
- [x] `/specdiff` 13.3 vs 13.4 returns the DBVO change and `peter-gap-exact` (recompute = R41-2, R41-3)
- [x] signed HTML report for one fail and one pass submission
- [~] `POST /criteria/extract` finds the 4 ITSG criteria: logic and scoring tested with scripted LLM answers; a real run with OpenAI is still to do
- [ ] at least one LLM explanation for a fail, cached for the offline demo: needs one real run with `OPENAI_API_KEY` (cache lands in `data/llm_cache/`)
- [x] every endpoint the demo storyline uses works and has an `httpx` test (`tests/test_p7_api.py`)
- [ ] all backend tests pass with `KG_BACKEND=yaml` and `graph`: waits for the KG teammate

## Next steps

1. Run once with a real `OPENAI_API_KEY` (set `OPENAI_MODEL`): `/check` on `s-no-contact`, `/submissions/s-missing-july/report`, `/criteria/extract` on VB 13.4 section 3.12, `/specdiff`. Check the answers, then keep `data/llm_cache/` for the offline demo. Prompts are in `llm/agents/*.py`, `llm/extract.py`, `llm/explain.py`, `llm/story.py`.
2. Start Docker, `docker compose up postgres`, run `DATABASE_URL=postgresql://eel:eel@localhost:5432/eel uv run python -m store.seed` with a real KG, and fix whatever `PgRepo` gets wrong.
3. P9: when `kg/yaml_backend.py` exists, point `tests/conftest.py` fixture `kb` at it and fix contract mismatches together (see decisions 2, 3, 6 below).
4. Commit per phase, PR into `main` (plan/09 section 6). Do not commit `HANDOVER.md` (personal notes; it is in `.gitignore`).

## Decisions taken while building (check with the team)

1. `tests/fakes/fake_kb.py` is the fake KB of decision D1. Its passages come from `tests/fakes/passages.yaml`, extracted from the real VB 13.3 / 13.4 PDFs (3.12 parts, 3.12.7), BP 13.1 / 13.2 and the BVORERK docx.
2. `kg.get_kb()` imports `kg.yaml_backend.YamlBackend` and `kg.graph_backend.GraphBackend`. The KG teammate must use these class names (or change the factory). `get_passage` accepts a `SpecRef` or a key string.
3. Only repeating-group field names drop their `-nn` suffix (`BEGINN-AU-{nn}` -> `BEGINN-AU`). Fixed names such as `DBAP.FIRMA-1` or `DBAE.BRUTTO-1` keep it, otherwise they collide. plan/08 section 1.3 should say this.
4. `an` values are right-stripped only (`rstrip`), so the writer reproduces the file exactly.
5. Date fields longer than 8 characters (`DATUM-ERSTELLUNG`, 20 digits) stay strings.
6. `DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG` and `DBSD.AKTENZEICHEN-VERURSACHER` are compare mode `rule` (C-3, C-2) in the fake KB. plan/08 section 8 lists only the DBID versions: the KG teammate should add both to `compare_modes.yaml`, or `s-variant` stops being an exact match.
7. `s-three-periods` drops a middle period (01.12 to 03.12.2025), `s-missing-july` the oldest (14.07 to 15.07.2025). Rule re-check: a missing oldest chained period = bug R41-3 ("go back to the first illness"); any other missing period = correct variant ("as many as possible"). plan/02 does not say which period s-three-periods drops.
8. `s-wrong-order` is labeled bug F41-8 as plan/02 section 7 says, although F41 rules are format rules (plan/03 section 8 would say invalid). Order is checked by the re-check, not the format check.
9. A missing 41 is a bug of the rule closest to its boundary (`deciding_rule`: R41-2 for gap-exact, R41-4 for b30).
10. Peter's chain extras are in `fixtures/scenarios/peter.yaml`: ITSG file values, Hinweise IDs. Derived (not given by ITSG): insurer DSIDs, KZ-AU 3 for the missing note, 01 salary values, 62 EEL-ABAG/ABSV (day after the final EFZ end), KORR-ABGABEGRUND 01 on the 88. Clones and BP cases inherit Peter's extras.
11. Diff matching of messages of the same type: vendor order, unless another pairing gives fewer deviations.
12. The store has two implementations with the same methods: `PgRepo` (when `DATABASE_URL` is set) and `MemoryRepo` (tests, local runs without Docker). Pydantic documents are stored whole in `jsonb` next to the columns of the data model.
13. Generated files copy the envelope (VOSZ, DSKO, NCSZ) of the ITSG file; the envelope is not graded.
14. Single-step test packages also carry the insurer's 61 reply, so `peter-gap-exact` has scenario + TEEL0 + TEEK0 + story as plan/02 M5.5 says.
15. Test runs: round N grades the employer messages of round N with the full checker; the reply is the expected insurer message adapted to the vendor's file (REF-ID, AZVU, BBNR-VU, the vendor's periods in the vendor's order, extras appended).
16. LLM: `create_app(ai=False)` switches the LLM off. Every LLM call degrades to "no answer" when there is no key and no cache, so the deterministic result always stands. Citations must be passage keys the KB resolves; answers without are retried once, then dropped. An AI proposal sets `resolved_by = ai_proposal` but the label stays `unclear` until the advisor decides.
17. Criteria pipeline: a draft counts as matched in step 3a when `maps_to_rule` is an approved rule id; parameters are compared by code (`params_ok`). Only drafts without a known rule go to the AI review (3b). A human decision on a 3b proposal is stored on the draft (`CriterionDraft.review`, via `POST /criteria/{id}/approve` with a `review`) and is not sent to the AI again.
18. Seed: 16 test cases (14 public + 2 hidden), plan/02 M7.2 says 14; the difference is the 2 hidden ones.
