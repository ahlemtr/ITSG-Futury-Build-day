# Backend implementation plan (everything except the knowledge graph)

Owner: Ahlem. Status: **decisions D1 to D6 taken (section 6), waiting for final validation**. Nothing is implemented before this plan is approved.

This file turns `plan/02_BACKEND_IMPLEMENTATION_PLAN.md` (milestones M0 to M8) into a concrete build order for one person. The `plan/` files stay the source of truth: this file only decides order, boundaries and what is built when. Where a detail is missing here, `plan/02`, `03`, `05`, `06` and `09` apply.

## 1. Scope

### Mine (this plan)

| Area | Folders | Milestones in `plan/02` |
|---|---|---|
| Setup, repo, Docker Compose | root, `docker-compose.yml`, `pyproject.toml` | M0 |
| Shared Pydantic models | `engine/model.py` | part of M9.1 (contract) |
| Parser and writer | `engine/records.py` | M1 |
| Rules engine | `engine/rules/` | M2.2 to M2.5 |
| Scenarios, expected chains, TEEL0/TEEK0 writer, seed submissions | `engine/expected.py`, `engine/writer_messages.py`, `fixtures/`, `tools/` | M3 |
| Rule checker | `engine/diff.py`, `engine/checker.py`, `engine/variants.py` | M4.1 to M4.7 (not M4.0) |
| Spec diff, test builder, hidden variants, test rounds | `engine/specdiff.py`, `engine/builder.py`, `engine/runs.py` | M5 |
| Report and signing | `engine/report.py`, `engine/signing.py`, `templates/` | M6 |
| Store, seed, API, intake | `store/`, `api/`, `engine/intake.py` | M7 |
| LLM services and agents (OpenAI) | `llm/` | M8 |

### Not mine

| Area | Owner | Reference |
|---|---|---|
| Everything under `kg/`: interface implementation, YAML backend, graph backend, seed files (`documents`, `message_types`, `parameters`, `rules`, `compare_modes`, `changes`, `test_cases`, `precedents`), extraction, build, load, embed | friend (KG) | `plan/08_KG_SEEDING_GUIDE.md` K0 to K11, `plan/02` M2.1, M4.0, M9 |
| Frontend | not in this plan | `plan/09` section 5 |

## 2. Boundary with the knowledge graph

The backend talks to the knowledge graph **only** through `kg/interface.py` (`plan/02` section 5). No backend file reads `kg/seed/` or Neo4j directly.

### 2.1 What we must agree on first (day 1, half a day, together)

1. `engine/model.py`: the shared Pydantic models `Layout`, `Field`, `Rule`, `Parameter`, `Passage`, `SpecRef`, `Version`, `Change`, `Impact`, `TestCase`, `TestCaseRef`, `DeviationContext`, `Precedent`, `Graph`. Field names follow `plan/08` sections 1.3 to 1.5 exactly (keys, enums, ISO dates).
2. `kg/interface.py`: the `KnowledgeBase` Protocol, exactly as in `plan/02` section 5.
3. A factory `kg.get_kb()` that returns the backend selected by `KG_BACKEND`.

After this, both sides build in parallel behind the contract.

### 2.2 What the backend needs from the KG, and when

| My phase | KG methods used | KG seed data needed |
|---|---|---|
| P1 parser | `get_layout` | `layouts/` (already done in `plan/starter/layouts/`) |
| P2 rules engine | `get_param`, `get_rules`, `get_versions` | `parameters.yaml`, `rules.yaml`, `documents.yaml` |
| P3 scenarios | `get_test_case`, `get_test_cases` | `test_cases.yaml` |
| P4 checker | `get_rules`, `find_precedent`, `add_precedent`, `get_passage` | `compare_modes.yaml`, `precedents.yaml` |
| P5 spec diff, builder | `get_changes`, `get_affected_rules`, `get_test_cases` | `changes.yaml`, spec diff JSON |
| P8 LLM | all tool methods, `search_passages`, `get_deviation_context` | passages (`kg/build/passages.yaml`) |

### 2.3 Working before the KG is ready

So that I am never blocked, the backend tests run against a **fake knowledge base**: a small in-memory class that implements the same Protocol and returns the values from `plan/03` (parameters, rule ids, Peter and clones) and `plan/05` (compare modes). It lives in `tests/fakes/fake_kb.py`, is used only by tests, and is deleted from the test setup once the friend's `yaml_backend` is ready. See open decision D1.

## 3. Build order

Each phase lists files, tasks (with the `plan/02` id), the tests that prove it and what it depends on. A phase is done when its tests pass. One branch per phase, PR into `main` (`plan/09` section 6).

### P0. Setup and shared contract

| Task | Implement | Test / how |
|---|---|---|
| P0.1 (M0.1) | repo layout of `plan/02` section 3, `pyproject.toml` with `uv`, ruff, pytest, `.env.example` with every variable of `plan/09` section 7, `api/main.py` with `/health` | `uv run pytest` runs, `uvicorn api.main:app` answers `/health` |
| P0.2 (M0.2) | copy `plan/starter/layouts/*.yaml` to `layouts/`, `sources/TEEL0-Test1-DBVO` to `fixtures/itsg/` | files present, every YAML loads |
| P0.3 | `docker-compose.yml`: `api`, `postgres` (and an empty `neo4j` service for the friend). API Dockerfile with poppler and the WeasyPrint system libraries | `docker compose up` starts, `/health` ok from the host |
| P0.4 | `engine/model.py` and `kg/interface.py` agreed with the friend (section 2.1), `tests/fakes/fake_kb.py` | models import, fake passes a small contract test (`get_param("gap_inclusive", on_date=2027-01-01)` is `True`) |

Depends on: nothing.

### P1. Records: parser and writer

| Task | Implement | Test / how |
|---|---|---|
| P1.1 (M1.1) | `records.parse_file(text, version) -> ParsedFile`: dispatch by first 4 chars, DSLW fixed part plus blocks in `block_order` where the MM flag is `J`, DBVO repeating group by `ANZAHL-AU`, VOSZ/DSKO/NCSZ kept as raw lines. Layouts come from `kb.get_layout` | ITSG file: ABGABEGRUND 41, AU-AB-AG 20260311, 4 groups, AZVU 1234-5678-007, consumed length = line length |
| P1.2 (M1.2) | typed values: `n` to int, date (`date_yyyymmdd`, `00000000` = None) or Decimal (`amount_2dp`); `an` stripped; raw kept | `00135384` -> `Decimal("1353.84")` |
| P1.3 (M1.3) | `records.write_dslw(head, blocks) -> str`, padding rules, MM flags from the blocks present | parse ITSG file, write back, byte-identical |
| P1.4 (M1.4) | `ParseIssue(record, field, pos, message)` for unknown block, length mismatch, non-numeric `n` | one digit replaced by a letter: 1 issue, no crash |
| P1.5 | encoding: UTF-8, fallback Latin-1, count characters (`plan/02` section 9) | file with umlauts parses in both encodings |

Depends on: P0. Base: `plan/starter/layouts/parse_check.py`.

### P2. Rules engine

| Task | Implement | Test / how |
|---|---|---|
| P2.1 (M2.2) | `engine/rules/params.py`: thin wrapper over `kb.get_param(name, version | on_date)`, returns a `Params` object for one rule set | `gap_inclusive` False on 2026-11-01, True on 2027-01-01, sim-13.5 only by version |
| P2.2 (M2.3) | `engine/rules/vorerkrankung.py`: `select_chain`, `must_send_41`, `days`, `add_months` exactly as `plan/03` section 3 | parametrized pytest over **all rows** of `plan/03` section 9 under 13.3, 13.4, sim-13.5 |
| P2.3 (M2.4) | `efz_end(current_start, groups_61, params)` as `plan/03` section 6 | first 61 -> 2026-03-30, corrected 61 -> 2026-03-27 |
| P2.4 (M2.5) | every function returns a `Trace` (rule ids, inputs, intermediate values) | Peter trace has R41-1..4 and total 35 |
| P2.5 | `engine/rules/formats.py`: F41-1..10 field checks on a parsed 41, plus K61, K62, C-1..8 checks as small functions with the same `Trace` | one passing and one failing example per rule |

Depends on: P0 (fake KB for params). Not on P1 except P2.5.

### P3. Scenarios and expected chains

| Task | Implement | Test / how |
|---|---|---|
| P3.1 (M3.1) | scenario model and loader. Inputs come from `kb.get_test_case(id)`; chain-only extras (insurer behavior per step, names, employer ids) in `fixtures/scenarios/<id>.yaml`. See open decision D3 | Peter and every clone of `plan/03` section 9 load |
| P3.2 (M3.2) | `expected.build_chain(scenario, version) -> [ExpectedMessage]` with `compare_mode` per field | Peter -> 41, 61, 01, 61, 88, 01, 62, EFZ 30.03 and 27.03. `peter-gap-exact`: no 41 under 13.3, 41 with 1 period under 13.4 |
| P3.3 (M3.3) | `writer_messages.py`: expected chain -> TEEL0 (employer) and TEEK0 (insurer: 61 with REF-ID, BBNR-VU, AZVU echoed, flags; 62 with DBEE) | generated Peter 41 equals the ITSG file on every `compare` field |
| P3.4 (M3.4) | `tools/make_submissions.py`: the 10 seed submissions of `plan/02` section 7 by mutation | each output parses |

Depends on: P1, P2.

### P4. Rule checker

| Task | Implement | Test / how |
|---|---|---|
| P4.1 (M4.1) | `diff.py`: 3 levels (messages, matching by person + Abgabegrund + chain position, fields by compare mode) -> `Deviation(step, record, field, expected, actual, kind)`; `kind` uses the enum of `plan/08` section 1.4 | reference vs generated: 0. Lines reordered: 0. Missing 88: 1 message deviation |
| P4.2 (M4.2) | rule-field checks (UUID regex, uniqueness, product id, sender number, AZVU constant, REFERENZ-ID links) | reused DSID: C-1 bug. AZVU changed in step 6: C-2 bug |
| P4.3 (M4.3) | format checks -> **invalid** | AU-AB-SV filled: F41-6 invalid. Letter in numeric field: invalid |
| P4.4 (M4.4) | `variants.py`: known-variant catalogue + `kb.find_precedent(signature)`; signature = `ABGABEGRUND|FIELD|KIND`. See open decision D4 | a seeded precedent resolves its deviation without AI |
| P4.5 (M4.5) | rule re-check of the vendor's version against R41, E, C rules | 3 of 4 periods: correct variant. July missing: bug R41-3. Pay end 30.03 after corrected 61: bug E-1 |
| P4.6 (M4.6) | label aggregation (invalid > bug > unclear > correct variant > exact match), counts per `resolved_by` | Peter reference: exact match |
| P4.7 (M4.7) | `checker.check(submission, valid_on)`: rule set by validity date, never "latest"; unclear deviations get an empty slot for the AI proposal (filled in P8) | `s-legacy-1`: exact match on 2026-11-01, bug R41-2 on 2027-01-01. All 10 seed submissions get the label of `plan/02` section 7 (except `s-no-contact`: unclear until P8) |

Depends on: P3.

### P5. Spec diff, test builder, hidden variants, test rounds

| Task | Implement | Test / how |
|---|---|---|
| P5.1 (M5.1) | `specdiff.py`: port of `plan/starter/tools/specdiff.py` (TOC and headers ignored, block and field attribution) | 13.3 vs 13.4 contains the DBVO chaining sentence, DBSD names, DBEE end, BBNR-VU; no layout row changed |
| P5.2 (M5.2) | `impact(changes)` via `kb.get_affected_rules` (builder uses `recompute` only) | DBVO change -> recompute R41-2, R41-3 and the 8 test cases of `plan/08` section 14 |
| P5.3 (M5.3) | `builder.recompute(test_cases, old, new)` | only `peter-gap-exact` and `peter-gap-exact-hidden` differ |
| P5.4 (M5.4) | `builder.clone(base, branch_point, change)` with `parent_id`; `builder.boundaries(rule, base)` threshold -1 / = / +1 | R41-4 -> b27..b30. R41-2 -> gap-in, gap-exact, gap-out |
| P5.5 (M5.5) | test package: scenario + expected TEEL0 + TEEK0 + story (story text from P8, placeholder until then), status `draft` | `peter-gap-exact` package has 3 files + story |
| P5.6 (M5.6) | `builder.hidden(test_case, seed)`: shift dates, target month ends and leap years, keep the boundary; `hidden=true`, never exported | `peter-gap-exact-hidden`: no 41 under 13.3, 41 under 13.4 |
| P5.7 (M5.7) | `runs.py`: `start` returns the story only; `submit(files)` checks the step and builds the next insurer reply from the vendor's file (REF-ID = their DSID); `verdict` pass/fail per rule, no expected values for hidden tests | Peter: 4 rounds. No 41 where required: rule fails, run ends |

Depends on: P4. P5.1 can start any time (no other dependency).

### P6. Report and signing

| Task | Implement | Test / how |
|---|---|---|
| P6.1 (M6.1) | report JSON (Pydantic): meta, rule set version, per step per check: outcome, expected, actual, rule, criterion, source, explanation | validates against the model |
| P6.2 (M6.2) | HTML (Jinja2): summary, chain timeline, fail/review table with passage text; PDF via WeasyPrint | opens in a browser, fail rows show the passage |
| P6.3 (M6.3) | `signing.py`: SHA-256 of each input file and of the report JSON, Ed25519 (key at `SIGNING_KEY_PATH`, created if missing), `verify(report)` | one changed byte -> verify fails |

Depends on: P4.

### P7. Store, seed, API, intake

| Task | Implement | Test / how |
|---|---|---|
| P7.1 (M7.1) | `store/schema.sql` per `plan/diagrams/07_data_model.md` (app data only) and `store/repo.py` (psycopg v3) | applies cleanly on the Postgres container |
| P7.2 (M7.2) | `store/seed.py`: test cases, expected steps, the 10 seed submissions | 14 test cases, 10 submissions; `kb` returns 2 VB versions |
| P7.3 (M7.4) | `engine/intake.py` + `POST /submissions`: store files under `DATA_DIR` with SHA-256, parse, receipt `{accepted / rejected, issues[]}` | corrupt file rejected with the issue; valid file accepted and checkable |
| P7.4 (M7.3) | every endpoint of `plan/02` section 6, thin routes over the engine. Hidden tests: `/package` refused, `/verdict` without expected values | one `httpx` test per endpoint against seeded data |

Depends on: P4 for `/check`, P5 for builder and runs routes, P6 for reports. The schema, seed and read-only routes can start right after P3.

### P8. LLM services (OpenAI)

| Task | Implement | Test / how |
|---|---|---|
| P8.1 (M8.0, M8.4) | `llm/client.py`: Structured Outputs with Pydantic, retry once on invalid JSON, cache by sha256 of the input in `data/llm_cache/`. `llm/tools.py`: every interface method except `add_precedent` and `subgraph`, plus the engine tools of `plan/09` section 3.3 (`parse_file`, `expected_result`, `evaluate_rule`, `diff_submission`, `add_months`, `count_days`) | agent asking for `gap_inclusive` on 2027-01-01 gets `true` via the tool; second run makes no API call |
| P8.2 (M8.3, extended) | **requirements-to-criteria pipeline** (section 3.1 below): find the requirements in a spec section, translate them into testable criteria, measure them against ITSG's criteria (exact first, AI review for what does not match), generate test cases from them | from VB 13.4 section 3.12 it finds all 4 ITSG criteria (`BVORERK@1`) with the right parameters, and the generated boundary cases for R41-2 are gap-in, gap-exact, gap-out |
| P8.3 (M8.1) | `explain(verdict, passage)`: 2 to 4 sentences, must contain rule id and section, else rejected | July-period fail mentions R41-3 and 3.12 |
| P8.4 (M8.2) | `story(scenario)`: TA-style story, plugged into the P5.5 package | Peter story lists the 4 prior periods and 11.03.2026 |
| P8.5 (M8.5) | AI deviation triage via the check agent: input deviation + `kb.get_deviation_context`; output `{proposal, reasoning, citations[], confidence}`; rejected without citation; never sets a final label | `s-no-contact` -> likely bug, cites BP 13.1 |
| P8.6 (M8.6) | `POST /deviations/{id}/decide`: stores label + reason, calls `kb.add_precedent` | re-check `s-no-contact`: resolved by precedent, no AI call |
| P8.7 (M8.7) | spec-update agent: per change `{decision, test_case draft, reasoning, citations[]}`, stored as `draft` | 13.3 -> 13.4: `update_test` for `peter-gap-exact` and its hidden variant, `no_change` for `peter`, cites `VB@13.4#3.12/chaining` |
| P8.8 (M8.8) | check agent report draft per deviation, `draft` until the advisor confirms | `s-missing-july` draft names R41-3 and `VB@13.4#3.12/chaining` |

Depends on: P4, P5, P7. Needs real passages from the KG for useful citations (the fake KB only has the few passages the tests need; for P8.2 it also carries the text of the VB 13.4 section 3.12 passages and the 4 BVORERK criteria).

#### 3.1 P8.2 in detail: requirements to criteria to test cases

Covers the first three objectives of the challenge deck (page 11): identify the relevant requirements, translate them into testable criteria, generate test cases with expected results. Shown on one section (VB 13.4 section 3.12, prior illnesses), as `plan/00` section 4 says; the code takes any section.

| Step | Who | Input | Output |
|---|---|---|---|
| 1. Find | agent, tools `search_passages`, `get_passage` | document, version, section (`VB`, `13.4`, `3.12`) | list of requirement sentences, each with its passage key (`VB@13.4#3.12/chaining`) and a quote |
| 2. Translate | agent, Structured Outputs | the requirement sentences | one `CriterionDraft` per requirement: `text` (one testable sentence, ITSG style), `applies_to` (Abgabegrund), `condition` (in words), `params[]` (`{name, value}`, names from `plan/03` section 2 when they match, else a new name), `maps_to_rule` (rule id or null), `citations[]` |
| 3a. Measure (exact) | deterministic code, no LLM | the drafts + approved rules from `kb.get_rules("41", version)` + `kb.get_param` | per ITSG criterion: `found` (a draft maps to its rule), `params_ok` (every draft parameter equals the approved value). Drafts that match are done here, no LLM call |
| 3b. Measure (AI review) | criteria agent, only for what 3a did not match | each unmatched draft (no rule, or a rule other than the one it seems to describe) and each ITSG criterion no draft matched, with the cited passages, the approved rules and the ITSG criteria texts | per draft a proposal: `equivalent` (same requirement as a rule or ITSG criterion, other wording, or split / merged; names the rule), `new_valid` (a real requirement the ITSG criteria do not cover, e.g. the open-ended AU rule R41-6), `wrong` (contradicts its cited passage), `unclear`; plus `reasoning`, `citations[]`, `confidence`. Never final: a human confirms |
| 3c. Score | deterministic code | results of 3a and 3b | "ITSG criteria found: X exact, Y proposed by AI, Z missing; parameters correct: N; new requirements proposed: M", the same style as the checker metric (`plan/05` section 6) |
| 4. Generate | deterministic code (`builder.boundaries`, `expected.build_chain`) | the drafts matched in 3a, and drafts from 3b once a human confirmed them as `equivalent` or `new_valid` | draft boundary test cases with expected results under the given version, status `draft` |

Rules:
1. No draft without at least one citation (rejected, retry once, then fail, as in `plan/09` section 3.2).
2. The LLM never computes dates or sets a value the engine uses. Drafts are shown next to the approved rules; only a human can approve one.
3. Exact matching first (3a), AI only for what is left (3b), human for the final word: the same order as the checker (`plan/05` section 2). Parameter values are always compared by code; the AI judges only whether a draft describes the same requirement, never whether a different value is acceptable. If it argues a conversion (for example "180 days" against 6 months), it must use the engine tools (`add_months`, `count_days`).
4. A human decision on a 3b proposal is stored with the draft, so the same draft text is not sent to the AI again.
5. Cached by input hash like every LLM call (P8.1), so the demo runs offline.

Files: `llm/extract.py` (steps 1, 2, 3b), `engine/criteria.py` (steps 3a, 3c, 4), models `RequirementSentence`, `CriterionDraft`, `CriterionReview`, `CriteriaScore` in `engine/model.py`.

API (also in the `plan/02` section 6 list): `POST /criteria/extract` with `{document, version, section}` returns requirement sentences, drafts, score and draft test cases. `POST /criteria/{id}/approve` with `{approver, decision}`.

Tests:
- VB 13.4 section 3.12: 4 of 4 ITSG criteria found (f41c7278, 0cefe80e, aade0289, 9c8c9b58), parameters `gap_months = 6`, `min_total_days = 30`, `sum_window_months = 12` correct
- a draft with a wrong value (`gap_months = 5`) gets `params_ok = false`, and the AI review does not turn it into a match
- a draft without a citation is rejected
- drafts matched in 3a make no LLM call
- a draft that merges R41-2 and R41-3 into one sentence: 3b proposes `equivalent`, naming both rules
- a draft for the open-ended AU (R41-6, no ITSG criterion): 3b proposes `new_valid`, citing `VB@13.4#3.12/conditions`
- generate step for R41-2 returns gap-in, gap-exact, gap-out with the same expected results as P5.4
- second run makes no API call

### P9. Integration with the real knowledge graph

| Task | Implement | Test / how |
|---|---|---|
| P9.1 | switch tests from the fake KB to the friend's `yaml_backend`; fix any contract mismatch together | all backend tests green with `KG_BACKEND=yaml` |
| P9.2 | run the same suite with `KG_BACKEND=graph` | all backend tests green with `KG_BACKEND=graph` |
| P9.3 | end-to-end demo script: the storyline of `plan/00` section 6 through the API | every step returns what the storyline says |

Depends on: friend's K11 done.

### P10. Stretch goal: TA 167 (Marc Hoffmann)

Only after the critical path (section 4) is green. Shows that the platform can produce the model solution for a real exam task, for which we have no ITSG solution (`plan/00` question 1).

| Task | Implement | Test / how |
|---|---|---|
| P10.1 | the inputs of TA 167 from the PTA (`TA_167-EEL_2025-2026`): AU periods as first read from the PTA, to double-check against the PDF before use: 13.08 to 12.09.2025, 05.12.2025 to 23.01.2026 (the PTA prints "23.01.2025", a typo), 02.02 to 20.02.2026, 12.06 to 30.06.2026; employment end 30.06.2026; prior-illness requests in 12/2025, 02/2026 and 06/2026. Added to `test_cases.yaml` by the friend (inputs only today), chain extras in `fixtures/scenarios/ta-167.yaml` | the three AU cases load as scenarios |
| P10.2 | expected 41 decision and periods for each of the three requests with the existing rules engine, rule set by the request date (`valid_on`), expected TEEL0 with the writer. Status `draft` with the note "computed by us, no ITSG solution". The December 2025 request falls before VB 13.3 (valid from 2026-01-01) and we have no earlier version: compute it under 13.3 and flag it | each request gets a decision with a trace; the files parse and round-trip |
| P10.3 | list what TA 167 needs that the rules do not cover yet (KUG months, correction EFZ to sickness benefit in 03/2026, the June AU with no EFZ because of the same illness) as `unclear`, for the advisor and for ITSG | the list is in the test package, nothing is guessed |

Depends on: P2, P3, P5.5. Out of scope: TA 168.

## 4. Order on one page

```
P0 setup + contract (with friend)
 ├─ P1 parser ──┐
 ├─ P2 rules ───┼─ P3 scenarios ── P4 checker ─┬─ P5 builder, runs ─┐
 └─ P5.1 specdiff (any time)                   ├─ P6 report ────────┼─ P7 API ── P8 LLM ── P9 real KG
                                               └─ P7.1, P7.2 store ─┘
```

Critical path for the demo: P0 -> P1 -> P2 -> P3 -> P4 -> P7 -> P8.1 -> P8.2 (requirements to criteria) and P8.5 / P8.6 (triage, advisor, precedent). Inside P8, build P8.2 right after P8.1. If time is short, cut in this order: P8.8, P8.7, P6.2 PDF, P5.6 leap-year targets, sim-13.5. P10 (TA 167) starts only when the critical path is green. P8.2 is not cut: it is the only place the deck objective "translate the requirements into testable criteria" is shown with AI.

## 5. Done when

From `plan/02` section 8, the items that are mine:

- [ ] ITSG's TEEL0 file parses and round-trips byte-identical
- [ ] all rows of the `plan/03` test tables pass under 13.3, 13.4 and sim-13.5
- [ ] Peter's full chain is generated (TEEL0 + TEEK0) and checks all green
- [ ] every seed submission gets its expected label
- [ ] `s-no-contact` goes through AI proposal, advisor decision, and is resolved by precedent on re-check
- [ ] Peter runs as 4 rounds through `/runs`, a hidden variant returns only pass/fail
- [ ] `/specdiff` 13.3 vs 13.4 returns the DBVO change and `peter-gap-exact` (recompute = R41-2, R41-3)
- [ ] signed HTML report for one fail and one pass submission
- [ ] `POST /criteria/extract` on VB 13.4 section 3.12 finds the 4 ITSG criteria with correct parameters and returns draft boundary test cases
- [ ] at least one LLM explanation for a fail, cached for the offline demo
- [ ] every endpoint the demo storyline uses works and has an `httpx` test
- [ ] all backend tests pass with `KG_BACKEND=yaml` and `KG_BACKEND=graph` (shared with the friend)

## 6. Decisions (all decided on 2026-10-26)

| # | Question | Decision |
|---|---|---|
| D1 | How do I work before the friend's KG exists? | A fake knowledge base in `tests/fakes/fake_kb.py`, used only by tests (section 2.3). Switch to the friend's `yaml_backend` as soon as it is ready (P9.1). Ask the friend to build `yaml_backend.py` right after K8 (seed files), not at the end: `plan/08` lists it in the folder layout and the K11 tests need it, but no step says when to build it |
| D2 | Who writes `engine/model.py` (shared models)? | Me, on day 1 (P0.4). The friend reviews it before building behind it |
| D3 | Scenario facts are in two places: `kg/seed/test_cases.yaml` (K8) and `fixtures/scenarios/*.yaml` (M3.1). Which is the source? | `test_cases.yaml`, read through `kb.get_test_case`. `fixtures/scenarios/<id>.yaml` holds only what the full chain needs on top: insurer behavior per step, names, employer ids (P3.1) |
| D4 | Who owns the known-variant catalogue (`kg/seed/variants.yaml` in M4.4, missing from `plan/08` and the interface)? | Me, as `engine/data/variants.yaml`, read by `engine/variants.py` (P4.4). Precedents stay behind the KG interface (`find_precedent`, `add_precedent`) |
| D5 | Are the API and report (P6, P7) mine? `plan/00` section 7 still gives them to "Teammate C" | Yes. Teammate A does the knowledge graph, I do everything else except the frontend |
| D6 | Which test people does the backend cover? | Peter Mustermann and his clones are the main case (the only one with ITSG's reference file and expected chain). TA 167 (Marc Hoffmann, prior-illness requests) is a stretch goal after the critical path (P10). TA 168 (child sickness benefit, maternity) stays out of scope |
