# EEL Review Assistant: project report

State on 2026-10-31, branch `main` at `0f48295` ("final changes"). Written after reading every plan, handout and README in the repository, the challenge deck, the code layout, the API and the UI routes, and after running the checks. This file replaces the hackathon plans (`plan/`, `HANDOUT.md`, `INTEGRATION_PLAN.md`, `SPEC_UPDATE_WORKFLOW.md`, `BACKEND_IMPLEMENTATION_PLAN.md`, `ui/UI_PLAN.md`), which were deleted in the same cleanup. Everything worth keeping from them is summarised here. They remain readable in Git history (`git show 0f48295:plan/03_DOMAIN_RULES_VORERKRANKUNG.md`, etc.).

## 1. The challenge

Futury Build Days, ITSG challenge "AI review assistant for system review" (deck of 23.10.2026, `sources/Futury-Hackathon-2026-Englisch.pdf`).

- ITSG certifies payroll programs (SAP, DATEV, Lexware ...) before they may send data to the social insurers (§ 95b SGB IV): about 100 programs, 800 million messages a year, specifications spread over about 100 documents, an initial approval and then a yearly audit.
- Task: design an AI solution that supports and potentially replaces the testing processes, focused on income replacement benefits (Entgeltersatzleistungen, EEL), "e.g. maternity benefit and sickness benefit". It should check automatically whether a program meets all applicable specifications in that scope.
- Objectives named by ITSG: identify the relevant requirements in the specifications; translate them into testable criteria; generate test cases with expected results; create a traceable test record; test the payroll software and compare with the expected results; deliver comprehensible test reports.
- Suggested flow: AI generates test cases, humans run them in the payroll software, AI checks the resulting data sets. Optional: run locally at the vendor and produce a report for ITSG. A prototype is "the cherry on top".

The team won first place on Monday 2026-10-26/27. The final presentation is in December 2026.

## 2. Our answer in one paragraph

A test platform that takes over what ITSG's test system eVpT does for EEL and adds what eVpT cannot do: judge deviations instead of diffing against one model solution, and keep the tests current when the rules change. Vendors upload their output files (TEEL0); the platform returns a receipt, runs a format check, compares with expected files computed by a deterministic rules engine, labels every deviation (exact match / correct variant / bug / invalid / unclear), builds the insurer replies (TEEK0) from the vendor's own files so the test story can continue round by round, and issues a signed report. When a new specification is uploaded, it is chunked, embedded, diffed against the previous version, analysed by an LLM (which only proposes, with citations), and the knowledge graph and test catalogue grow; ITSG approves new tests before vendors see them.

Pitch lines used: "One platform for EEL testing: it receives the files, answers like the insurer, judges every difference and keeps the tests up to date." / "Today's comparison is a preliminary evaluation (fachliche Vorbewertung). Ours is a real one."

## 3. Domain facts the project rests on

- Today the official exam (Pool-Testaufgaben 2025/2026) has only 2 fake employees for EEL (TA 167, TA 168). eVpT compares the vendor's files with one fixed solution, only for selected tasks; correct alternatives show up as deviations and a system advisor sorts each one out by hand.
- Message types (Abgabegrund): employer 01–04 certificates, 41 prior-illness request, 42, 51, 73, 88 cancel, 99; insurer 61 prior-illness answer, 62 benefit end, 66, 67, 71, 72.
- Spec versions: VB (Verfahrensbeschreibung) 13.3 published 24.11.2025, valid 01.01.2026; VB 13.4 published 10.03.2026, valid 01.01.2027. Field layouts are identical; all changes are in the explanatory text (67 raw changes, 36 after removing page shifts).
- The one real rule change that hits the scope: VB 3.12 (DBVO, chaining prior illnesses) changed from "nicht **mindestens** 6 Monate" to "nicht **mehr als** 6 Monate". A gap of exactly 6 months now chains. The change log calls it editorial. VB 13.4 is internally inconsistent: the insurer paragraph of 3.12 and field text 3.12.7 still use the old wording. That inconsistency was a pitch point.
- Other 13.4 clarifications modelled: BBNR-VU echoed on replies (VB 3.1.10, K61-2), AKTENZEICHEN-VERURSACHER blank if none sent (3.19, C-7), names on the 88 (3.20, C-4), 62 end not after end of employment (3.7.3, C-6).
- Rules implemented (`kg/seed/rules.yaml`, 37 rules): R41-1..6 (when a 41 is due, chaining, 30-day sum, Kurz-AU, open end), F41-1..10 (41 format), K61-1..7 and K62-1..2 (insurer replies), E-1..3 (EFZ end date), C-1..8 (chain consistency), S-1 (code values from GG Anlage 2).
- Versioned parameters: `min_total_days` 30, `gap_months` 6, `gap_inclusive` false (13.3) / true (13.4), `sum_window_months` 12, `open_end_days` 7, `efz_days` 42. A simulated 13.5 (28 days) exists for the demo.
- Test catalogue (full seed, 18 cases): `peter` (the Hinweise scenario, 7-message chain 41, 61, 01, 61, 88, 01, 62; ITSG's real TEEL0 file is step 1), boundary clones `peter-gap-exact/-in/-out`, `peter-b27..b30`, `peter-noteless`, hidden variants `peter-hidden`, `peter-gap-exact-hidden` (31.08 + 6 months = 28.02), Beispielpapier rows `bp-13-1..5`, and `ta-167`, `ta-168` as drafts. `peter-gap-exact` and its hidden variant are the only cases whose result flips between 13.3 and 13.4.
- Seed submissions (`tools/make_submissions.py`, full seed only): `s-itsg-ref`, `s-variant`, `s-three-periods`, `s-missing-july`, `s-wrong-order`, `s-stale-efz`, `s-insurer-field`, `s-no-contact`, `s-legacy-*`, `s-legacy-hidden`.
- Label order per test case: invalid > bug > unclear > correct variant > exact match.

## 4. What exists in the repository

| Layer | Where | What it does |
|---|---|---|
| Record layouts | `layouts/*.yaml` (20 blocks) | DSLW + DBxx fixed-width layouts. DBAP inferred from the sample, DBNA now from GG Anlage 1, DBAN missing |
| Engine | `engine/` | parser/writer (`records.py`, byte-identical round trip), rules (`rules/vorerkrankung.py`, `formats.py`, `params.py`), expected chains (`expected.py`), TEEL0/TEEK0 writer (`writer_messages.py`), 3-level diff (`diff.py`), checker (`checker.py`), known variants (`variants.py`, `data/variants.yaml`), spec diff (`specdiff.py`), test builder with clones, boundaries and hidden variants (`builder.py`), test rounds (`runs.py`), report + SHA-256/Ed25519 signing (`report.py`, `signing.py`), criteria pipeline (`criteria.py`), deadlines (`calendar.py`), Krankengeld calculator (`calc/krankengeld.py`) |
| Knowledge graph | `kg/` | seed files `kg/seed/*`, PDF/DOCX extraction (`kg/extract/*`, incl. annex table cells), graph build/validate/load/embed, YAML backend and Neo4j backend behind one interface (`interface.py`, `get_kb()`), chunks + hybrid search, field evidence from the annexes, upload pipeline (`ingest.py`) |
| LLM | `llm/` | OpenAI Structured Outputs client with a disk cache (`client.py`), read-only tools (`tools.py`), agents: `change_analysis`, `spec_update`, `calculation_analysis`, `check` (triage), `chat` (RAG), `document_metadata`; plus `explain`, `story`, `extract` (criteria) |
| Store | `store/` | `PgRepo` (Postgres) and `MemoryRepo` with the same methods; `schema.sql`; seed |
| API | `api/main.py`, `api/routes/*` | FastAPI, 46 endpoints (health, parse, submissions/check/diff/report, advisor queue + decide, runs, test cases + approve, builder, specdiff, spec upload + jobs, criteria, rules/versions/passages, kg stats/events/ask/subgraph/field definitions, calendar, chat, calc, admin reset) |
| UI | `ui/` | React 18 + Vite + TypeScript, German default and English on a button. ITSG view: Overview, Fristen (calendar), Prüfrechner (calculator), Spec-Änderungen, Testkatalog, Wissensgraph, Einreichungen, Klärungsfälle, Prüfberichte. Vendor view ("Hersteller"): my tests, test run per round, calendar, results, reports. AI activity overlay, chat drawer |
| Tools | `tools/` | `reset_baseline` (demo reset), `make_submissions`, `make_vendor_uploads`, `extract_key_values` (GG Anlage 2 code tables), `compare_anlage1`, `kg_bundle` (export/import passages, embeddings, AI cache) |
| Deployment | `Dockerfile` (API image), `docker-compose.yml` (local Postgres + Neo4j + API), `dev.ps1` (one-command local start on Windows). The TU VM setup was removed on 2026-10-31; Google Cloud deployment is still to be written |
| Sources | `sources/` | VB 13.3, GG 13.1 + Anlagen 1–3, VB Anlage 1 13.1.3 and 13.1.4, Beispielpapier, Pool-Testaufgaben, Rundschreiben Anl. 1–3, the two ITSG DOCX files, the challenge deck. VB 13.4 is kept local only (gitignored) because it is uploaded live in the demo |

Hackathon team (from the commit history): Ahlem Trabelsi (backend engine), Mohamed Hizem (knowledge graph), Slim Frikha (UI shell, vendor view, advisor queue, README showcase), Ghassen Zaara (plans, integration, spec update workflow, calendar, reset, chat, deployment). 56 commits, 26–27.10.2026. From here on Ghassen carries the project, with occasional help.

## 5. Promised vs. delivered

### Delivered and verified

| Promise | Status |
|---|---|
| Parse ITSG's TEEL0 file and write it back byte-identical | done, tested |
| Rules engine for prior illnesses (41/61) and EFZ end, all rows of the domain test tables under 13.3, 13.4, sim-13.5 | done, tested |
| Peter's full 7-message chain generated (TEEL0 + TEEK0) and checked all green | done |
| Checker with labels, compare modes (compare / rule / ignore), precedents that resolve the same deviation next time | done; advisor decision is stored as a precedent |
| Round-based vendor test run with insurer replies built from the vendor's own file, TEEK0 download | done (UI + API) |
| Hidden variants: vendor only sees pass/fail | done; `/test-cases/{id}/expected` returns 403 for hidden tests |
| Signed report (SHA-256 + Ed25519) with verification, HTML with ITSG logo and fonts | done; PDF only inside the Docker image (WeasyPrint) |
| Spec upload pipeline (store, chunk, embed, diff, map, AI analysis, apply, catalogue) | done; verified with the real VB 13.4 PDF and a real model: 4 changes touching rules, `gap_inclusive` false → true derived by the AI, R41-2/R41-3 to recompute, 8 draft tests including `peter-gap-exact` and its hidden variant, graph grew to 1,032 passages |
| This-year / next-year logic (rule set chosen by validity date, never "latest") | done |
| Knowledge graph tab (counts, growth log, Cytoscape view, "ask the graph") and chunk-level hybrid search | done |
| RAG chat with inline citations that must resolve to real passages | done |
| GG annexes as cited evidence; S-1 checks every code field against Anlage 2 | done |
| Deadline calendar per vendor company, demo reset from the user menu, "less text" UI pass | done (deadline rules are assumptions, see 5.3) |

Checks run on 2026-10-31 on this machine: `pytest` 207 passed, **1 failed**, 27 skipped (graph tests need `NEO4J_TESTS=1`); `ruff check .` clean; `tsc -b` clean; i18n check: 564 keys, both languages complete.

The failure: `tests/test_annex_evidence.py::test_vb_annex_centered_chapters_work_with_linux_poppler_indentation` expects sections `{"1","2","3"}`, gets `{"intro","2","3"}`. The heading detection for centred annex chapters depends on the indentation `pdftotext` produces; the test encodes Linux poppler indentation and fails on this Windows setup.

### 5.2 Where the pitch is bigger than the product

These are the honest gaps. They matter for December because a jury that read the deck will ask exactly these questions.

1. **Scope is one scenario family, not "EEL".** The engine computes one topic: prior illnesses (41/61), the EFZ end date and the 01/88/62 chain around them. All 16 executable test cases are Peter variants or Beispielpapier rows; `ta-167` and `ta-168` are drafts. Maternity (03), child sick benefit (02), rehab and accident benefits are out of scope, though ITSG's deck names maternity benefit as an example.
2. **Rules are hand-coded, not derived.** `vorerkrankung.py` and `formats.py` are Python written from the plans. The "AI keeps tests up to date" story works when a change maps onto an existing parameter (`gap_inclusive`). A change that needs new logic produces a draft rule (`CALC-*`, status draft, never used in checks) and needs a developer. ITSG's objective "translate requirements into testable criteria" is shown on one section (VB 3.12, criteria pipeline, `/criteria/extract`), which the UI does not call.
3. **"AI generates test cases"** is partly true: test cases are produced by the deterministic builder (clones, boundaries, hidden variants) after the AI has interpreted the change. That design is right (the AI never computes dates or results), but it should be stated plainly.
4. **The upload pipeline is proven on one real document pair.** VB 13.3 → 13.4 works with the real model. The Rundschreiben path (W8) is tested only with a scripted change; no newer edition exists. LLM answers are cached by prompt hash in `data/llm_cache/`, so a repeated demo upload replays the cached answer.
5. **Missing source knowledge.** Anlage 3 of the VB (data blocks per Abgabegrund) is not available, so a missing DBAP on a 41 stays "unclear". DBAN has no layout. The 12 open questions to ITSG (6-month counting from end date or day after, month ends 31.08 + 6 months = 28.02, Kurz-AU listing, which 6-month wording is authoritative, eVpT's ignore list, etc.) are unanswered.
6. **Krankengeld calculator** (`/calculator`, RS Anl. 3 sections 4 and 5) covers monthly and hourly pay only; Entgeltumwandlung, flexible working time, Altersteilzeit, output-based pay and the special cases of 4.1.1.1.1.2 are not covered. It is not in the handout and was added in the last commit.
7. **Calendar rules are invented** until ITSG confirms them: round N due 14 days after round N-1, update tests due the day before the new version takes effect, permanent test cases due each month end, catalogue approval 60 days before the switch.
8. **No login.** The ITSG/vendor switch is a demo toggle, all endpoints are open. Hidden tests are protected only by the UI not calling `GET /test-cases/{id}`. The reset endpoint is allowed from loopback or with `ALLOW_RESET=1`.
9. **Not a vendor-side tool.** The optional "run locally at the vendor" idea from the deck is not built (same engine, packaging only).
10. **Search quality** has a known miss: "Ansprechpartner DBAP" ranks VB 2.2.3.1 above 3.18; `test_search_finds_chaining[graph]` fails on Neo4j's German full-text ranking.
11. **Data protection.** ITSG documents and vendor files go to OpenAI. Decided for December: only test data goes through the platform, so OpenAI stays; expect the question from the GKV audience anyway.

### 5.3 Operational weight

Running it needs Docker (Postgres + Neo4j), Python 3.12 with `uv`, Node, `pdftotext`, and an OpenAI key for new AI answers and embeddings. On Windows `uvicorn --reload` hangs and the machine runs short of memory with Docker + API + Vite. The knowledge graph build cache (`kg/build/`, 156 MB, including 142 MB of paid embeddings) is the expensive asset; `tools/kg_bundle` exports it for teammates.

## 6. Decisions taken during the build (still in force)

1. The engine keeps its own typed `Case`; the KG's `TestCase` has dict inputs (`Case.from_kb` / `to_kb`).
2. Only repeating-group field names drop their `-nn` suffix; fixed names like `DBAP.FIRMA-1` keep it. `an` values are right-stripped only; date fields longer than 8 characters stay strings.
3. `DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG` (C-3) and `DBSD.AKTENZEICHEN-VERURSACHER` (C-2) are `rule` fields.
4. A missing oldest chained period is bug R41-3; any other missing period is a correct variant. A missing 41 is a bug of the rule closest to its boundary.
5. Diff matching of messages of the same type follows the vendor's order unless another pairing gives fewer deviations.
6. Generated files copy the envelope (VOSZ, DSKO, NCSZ) of ITSG's file; the envelope is not graded. Single-step test packages also carry the insurer's 61.
7. Every accepted round upload is also a submission `run-<id>-r<n>`; rejected files do not use up a round.
8. The AI never writes: agents answer in a fixed schema, code validates (citations must be real passage keys, parameter names and types are checked) and writes. Without key and cache every AI call degrades to "no answer". An AI proposal leaves a deviation `unclear` until the advisor decides.
9. Parameters are versioned with the VB; a Rundschreiben only proposes parameter values.
10. Advisor decisions are stored as precedents in `DATA_DIR/precedents.yaml` (YAML backend) or Neo4j, never in `kg/seed/precedents.yaml`.
11. Neo4j holds the knowledge (documents, passages, chunks, rules, parameters, layouts, test definitions, precedents); Postgres holds operations (submissions, checks, runs, reports, catalogue status, upload jobs, growth log, companies, deadlines). Files under `DATA_DIR`.
12. The starting point (`SPEC_BASELINE=VB@13.3`) has Peter only and no submissions; the full seed (13.3 + 13.4, 18 test cases, 10 submissions) is what the tests use.

## 7. How to run

```
docker compose up -d postgres neo4j
SPEC_BASELINE=VB@13.3 uv run python -m tools.reset_baseline              # Postgres back to the starting point
SPEC_BASELINE=VB@13.3 uv run python -m kg.build --skip-extract --fresh   # Neo4j baseline graph
SPEC_BASELINE=VB@13.3 SEED_ON_START=0 uv run uvicorn api.main:app --port 8000
cd ui && npm run dev                                                       # http://127.0.0.1:5173
```

Or `./dev.ps1` (add `-Reset` to reset first). Without Docker: leave `DATABASE_URL` and `KG_BACKEND` empty (in-memory store, YAML knowledge base). Sample vendor files: `python -m tools.make_vendor_uploads` (writes `samples/vendor_uploads/`). The old demo state was deleted from `data/`; run `./dev.ps1 -Reset` once so Postgres and Neo4j match it again.

## 8. Cleanup done on 2026-10-31

The repo was reduced to what is needed to continue (commits `fbf69c7` and the one after it):

- **Removed:** all hackathon plans and handouts (`plan/`, `HANDOUT.md`, `INTEGRATION_PLAN.md`, `SPEC_UPDATE_WORKFLOW.md`, `BACKEND_IMPLEMENTATION_PLAN.md`, `ui/UI_PLAN.md`, `ui/mockups/`; their content is summarised in this report and stays in Git history), duplicate sources (`sources/TEEL0-Test1-DBVO`, the translation glossary PDF, the archived VB 13.4 upload), the TU VM deployment (`compose.vm.yaml`, `deploy/`, `docs/VM_DEPLOYMENT.md`, `.gitattributes`), all caches and generated output (`__pycache__`, `.pytest_cache`, `.ruff_cache`, `ui/dist`, `bundles/`, `samples/`, `data/report-preview/`) and the old demo runtime state (`data/ingested/`, `data/submissions/`).
- **Comments:** dead references to the deleted plans (`plan/02`, `(08 section 5.2)`, `Step K9.1`, `HANDOUT agenda`, milestone tags like `P8.5`) were removed from comments and docstrings only; no code or prompt text changed.
- **README:** Slim's showcase README (from `origin/main`) is kept; only its links to deleted files were fixed.
- **Kept on purpose:** `kg/build/` (156 MB, includes 142 MB of paid embeddings), `data/llm_cache/` (AI answers, offline demo), `data/keys/` (report signing key), `.venv/`, `ui/node_modules/`, `.env`, the challenge deck.
- **Checked:** every tracked file is referenced by the code or read by convention (config files, entry points, CLI tools). After the cleanup: `pytest` 207 passed, 1 failed (the Windows/Linux `pdftotext` annex test), 27 skipped; `ruff` and `tsc` clean.

## 9. Decisions for December (2026-10-31)

| Topic | Decision |
|---|---|
| Event | **11 December 2026**: pitch with live demo to the GKV and other key stakeholders; a pilot discussion with ITSG is likely afterwards. The product must be close to finished, not a scoped demo |
| People | Ghassen alone, working with Claude Code; teammates help occasionally. The roadmap is a list of independent goals and tasks, no role assignment |
| Phases | 1) widen EEL scope, 2) real AI rule derivation from the spec text, 3) harden for real use (login, security). Planned in advance, worked in that order |
| Scope | All of EEL: certificates 01 (Krankengeld), 02 (Kinderkrankengeld), 03 (Mutterschaftsgeld), the other messages (42, 51, 73, 62/71/72, 66/67 errors, 99), including error cases, to show robust and complex situations |
| Demo story | The same arc with full EEL coverage (vendor run, deviations judged, VB 13.4 upload, tests update, signed report), plus automations, e.g. a newly signed vendor completes the whole yearly catalogue, gets the certified label, and that unlocks the permanent test cases |
| Kept features | Krankengeld calculator, deadline calendar, RAG chat, knowledge graph tab |
| Language | German only: the English UI will be dropped |
| Login | Two roles, ITSG staff and vendor accounts, email + password in our own user table; ITSG creates the vendor accounts (no self sign-up) |
| Data | Only test data goes through the platform (test employees like Peter); OpenAI stays the AI provider |
| Architecture | Keep Neo4j + Postgres |
| Hosting | Google Cloud ($300 free credits), Google's default HTTPS URL, no own domain |
| ITSG | There is a contact who can answer domain questions and provide data |
| Git | Fork `ahlemtr/ITSG-Futury-Build-day`, one branch + pull request per feature into her `main`; GitHub Actions (Linux) runs pytest, ruff, tsc and the i18n check on every PR |

### Questions for the ITSG contact

1. TA 167 and TA 168: solutions and TEEK0 reply files, and a sample eVpT deviation report.
2. Anlage 3 of the Verfahrensbeschreibung (data blocks per Abgabegrund): is DBAP mandatory on a 41? Beispielpapier 13.1 sets MM-ANSCHRIFT = J (DBAN), ITSG's reference file sends N; layout of DBAN.
3. "6 months" in VB 3.12: counted from the end date or from the day after? Month ends: is 31.08 + 6 months = 28.02?
4. Which 6-month wording is authoritative for 2027: VB 13.4 changed only the employer sentence; the insurer paragraph and 3.12.7 still use the old wording.
5. Kurz-AU directly followed by a certified AU: one merged period or the certified part only?
6. Which fields eVpT's Vorbewertung ignores (our list: DATUM-ERSTELLUNG, DATUM-VERARBEITUNG, AKTENZEICHEN-SV, salary amounts of the 01).
7. Deadline rules: when each test round is due, how often certified vendors submit permanent test cases (monthly per PTA 8.4?), when the catalogue must be approved before a new version takes effect.
8. Certification rules: what a new vendor must pass to be certified, and what the certified label unlocks.
9. Can payroll software clone an employee to start a test branch? What share of eVpT deviations turn out to be allowed variants?
