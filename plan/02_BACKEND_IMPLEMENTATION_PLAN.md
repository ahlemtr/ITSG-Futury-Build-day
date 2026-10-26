# Backend Implementation Plan

Read `00_PROJECT_OVERVIEW.md` first for context and `03_DOMAIN_RULES_VORERKRANKUNG.md` for the exact rules.

## 1. Principles

1. **The LLM never computes expected values or verdicts.** It extracts, drafts and explains. Rules are deterministic Python.
2. **Every verdict cites its source**: rule ID, ITSG criterion (if any), spec document, version, section.
3. **Rules and layouts are data.** Parameters and layouts live in YAML (later the knowledge graph). A version change is a data change.
4. **Only `kg/` knows where rules and layouts come from.** The rest of the code calls the interface in section 5.
5. **Files in, files out.** The vendor uploads TEEL0 files and gets receipts, TEEK0 replies and signed reports back. Transport (GKV communication server) is assumed; no eVpT connection.

## 2. Tech stack

| Purpose | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI + Uvicorn, Pydantic v2 |
| Data files | PyYAML |
| Dates | python-dateutil (`relativedelta`) |
| Database + file storage | Postgres 16 in Docker on the team VM (app data: test cases, submissions, verdicts, runs, reports), `psycopg`; files on the VM disk under `data/` |
| Knowledge graph | Neo4j 5 Community in Docker on the same VM (`07_KNOWLEDGE_GRAPH.md`), YAML backend as fallback |
| LLM | Anthropic SDK (Claude), JSON output validated with Pydantic |
| Signing | `cryptography` (Ed25519), `hashlib` (SHA-256) |
| Report HTML | Jinja2 |
| PDF text | `pdftotext` (poppler) for the spec diff, pdfplumber as fallback |
| Tests | pytest |
| Run | Docker Compose on the team VM (api + postgres + neo4j), `.env` for keys |

## 3. Repository structure

```
eel-review/
├── layouts/                   # DONE: DSLW.yaml, DBxx.yaml (V13.3 and V13.4 identical)
├── engine/
│   ├── records.py             # parser + writer (fixed width <-> dict)
│   ├── intake.py              # upload -> stored files + hash + receipt (format check)
│   ├── model.py               # Pydantic: AuPeriod, Scenario, Message, Verdict ...
│   ├── rules/
│   │   ├── params.py          # get_param(name, on_date | version)
│   │   ├── vorerkrankung.py   # must_send_41, select_chain, efz_end
│   │   └── formats.py         # F41-* field checks
│   ├── expected.py            # scenario -> expected message chain
│   ├── writer_messages.py     # expected chain -> TEEL0/TEEK0 files
│   ├── checker.py             # submission -> verdicts
│   ├── diff.py                # 3-level diff with compare modes
│   ├── variants.py            # known-variant catalogue + precedent lookup
│   ├── runs.py                # test rounds, reply generation, verdicts
│   ├── builder.py             # clones, boundary variants, change impact
│   ├── specdiff.py            # version diff -> changed sections -> rules
│   ├── report.py              # JSON + HTML report
│   └── signing.py
├── kg/
│   ├── interface.py           # the contract (section 5)
│   ├── yaml_backend.py        # reads layouts/ + kg/seed/ (reference backend)
│   ├── graph_backend.py       # teammate's Neo4j graph, same interface
│   ├── seed_graph.py, load.py # build and load the graph (07, K3 to K5)
│   └── seed/                  # ONE set of hand-written seed files, read by both backends:
│                              # documents, message_types, parameters, rules (with criteria),
│                              # compare_modes, variants, changes, test_cases, passages,
│                              # sections (spec text per passage, from pdftotext)
├── llm/
│   ├── client.py
│   ├── explain.py             # fail verdict -> plain explanation with citation
│   ├── story.py               # scenario -> readable test story (TA style)
│   └── extract.py             # spec passage -> draft rule (shown on 3.12)
├── store/
│   ├── schema.sql
│   ├── repo.py
│   └── seed.py
├── api/
│   ├── main.py
│   └── routes/                # parse, check, testcases, builder, specdiff, reports
├── fixtures/
│   ├── itsg/TEEL0-Test1-DBVO  # ITSG reference file
│   ├── scenarios/*.yaml       # peter + clones + Beispielpapier cases
│   └── generated/             # files produced by the writer
├── tools/
│   └── make_submissions.py    # seed submissions by mutation (M3.4)
└── tests/
```

## 4. Order of work (milestones)

Each task lists what to implement, what to test and how to test it. A milestone is done when its tests pass.

### M0 Setup

| Task | Implement | Test / how |
|---|---|---|
| M0.1 | repo, `pyproject.toml`, ruff, pytest, `.env.example` (ANTHROPIC_API_KEY, DATABASE_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, KG_BACKEND=yaml, SIGNING_KEY_PATH). No default rule set: every check passes `valid_on` (M4.7) | `pytest` runs (0 tests), `uvicorn api.main:app` serves `/health` |
| M0.2 | copy `layouts/` and `fixtures/itsg/TEEL0-Test1-DBVO` | file present, YAML loads |

### M1 Records: parser and writer

| Task | Implement | Test / how |
|---|---|---|
| M1.1 | `records.parse_file(text) -> [Record]`: split lines, dispatch by first 4 chars. DSLW: fixed part, then blocks in `block_order` whose MM flag is `J`. DBVO repeating group via `ANZAHL-AU`. VOSZ/DSKO/NCSZ kept as raw lines | parse the ITSG file: ABGABEGRUND = 41, AU-AB-AG = 20260311, 4 groups with the expected dates, AZVU = 1234-5678-007, consumed length = line length |
| M1.2 | typed values: `n` -> int or date (`date_yyyymmdd`) or Decimal (`amount_2dp`, value / 100); `an` -> stripped str. Keep raw string too | `00135384` with amount_2dp -> `Decimal("1353.84")`; `00000000` date -> `None` |
| M1.3 | `records.write_dslw(head: dict, blocks: dict) -> str`: pad `an` right with spaces, `n` left with zeros, set MM flags from blocks present | **round trip**: parse ITSG file, write it back, byte-identical |
| M1.4 | errors as data: unknown block, length mismatch, non-numeric in `n` -> `ParseIssue(record, field, pos, message)` | corrupt one digit to a letter: parser returns 1 issue, does not crash |

### M2 Rules engine

| Task | Implement | Test / how |
|---|---|---|
| M2.1 | `kg/seed/rules.yaml` + `kg/seed/parameters.yaml` (format in `07_KNOWLEDGE_GRAPH.md` section 5): rules R41-1..6, F41-1..10, K61-1..7, K62-1..2, E-1..3, C-1..8 with `id, title, criterion, sources[], params[], fields[]`. Parameter values per version (13.3, 13.4, sim-13.5) with `valid_from` | YAML loads into Pydantic models |
| M2.2 | `params.get(name, version)` and `params.get(name, on_date)` | `gap_inclusive` is False for 13.3, True for 13.4; by date: False on 2026-11-01, True on 2027-01-01 |
| M2.3 | `select_chain`, `must_send_41` exactly as in rules doc section 3 | **all rows** of rules doc section 9 (Beispielpapier 13.1 to 13.5, Peter and clones) under 13.3, 13.4 and sim-13.5 as a parametrized pytest. BP 13.5 trace counts the open AU until 08.09 (23 days) |
| M2.4 | `efz_end(current_start, groups_61, params)` | first 61 -> 2026-03-30, corrected 61 -> 2026-03-27 |
| M2.5 | each function returns a `Trace`: rule ids evaluated, inputs, intermediate values (e.g. total = 35) | trace for Peter contains R41-1..4 and total 35 |

### M3 Scenarios and expected chains

| Task | Implement | Test / how |
|---|---|---|
| M3.1 | scenario format `fixtures/scenarios/<id>.yaml`: person, employer ids, AU periods (start, end, certified, source), employment end, report date, insurer behavior per step (which flags) | Peter and all clones from rules doc section 9 written as YAML |
| M3.2 | `expected.build_chain(scenario, version) -> [ExpectedMessage]`: step, actor, abgabegrund, expected fields with `compare_mode` (compare / rule / ignore, per `05_CHECKING_AND_DEVIATIONS.md` section 4) | Peter -> 7 messages (41, 61, 01, 61, 88, 01, 62) with EFZ ends 30.03 and 27.03. Clones are **single-step** tests (only the 41 decision and its content, rules doc section 9): `peter-gap-exact` -> no 41 under 13.3, 41 with 1 period under 13.4 |
| M3.3 | `writer_messages`: expected chain -> files. Employer files TEEL0 (the "solution"), insurer files TEEK0 (61 with REF-ID, BBNR-VU, AZVU echoed, flags; 62 with DBEE) | generated Peter 41 equals the ITSG file on every `compare` field |
| M3.4 | `tools/make_submissions.py`: build seed submissions (section 7) by copying the expected files and applying mutations | each mutation produces a file the parser still reads |

### M4 Rule checker (exact match first, then deviation analysis)

See `05_CHECKING_AND_DEVIATIONS.md` for the flow, compare modes and labels.

| Task | Implement | Test / how |
|---|---|---|
| M4.0 | `kg/seed/compare_modes.yaml`: per record/field `compare`, `rule` or `ignore`, with source (VB section) | ignore list as in doc 05 section 4 (DATUM-ERSTELLUNG, DATUM-VERARBEITUNG, AKTENZEICHEN-SV, DBAL/DBAE amounts, DBNA unknown positions). Rule list as in doc 05 |
| M4.1 | **diff engine** on three levels: messages (expected vs present), matching (person + Abgabegrund + chain position, not line order), fields (`compare` fields only). Output `Deviation(step, record, field, expected, actual, kind)` | ITSG reference vs generated solution: 0 deviations. Same file with lines in another order: still 0. Missing 88: 1 message-level deviation |
| M4.2 | rule-field checks: UUID format and uniqueness, product id, test sender number, AZVU constant, REFERENZ-ID links | reused DSID: C-1 bug. AZVU changed in step 6: C-2 bug |
| M4.3 | format checks (F41-*, MM flags vs blocks, insurer-only fields zero, types) -> label **invalid** | AU-AB-SV filled: F41-6 invalid. Letter in a numeric field: invalid |
| M4.4 | **known-variant catalogue** `kg/seed/variants.yaml`: deviation signature -> correct variant + reason; approved precedents come from `kg.find_precedent` | a seeded precedent resolves its deviation without AI |
| M4.5 | **rule re-check** per deviation: evaluate the vendor's version against R41, E, C rules -> correct variant or bug | 3 of 4 periods: correct variant (note "as many as possible"). July missing: bug R41-3. Pay end 30.03 after corrected 61: bug E-1 |
| M4.6 | label aggregation: worst label per test case (invalid > bug > unclear > correct variant > exact match), counts per `resolved_by` | Peter reference: exact match |
| M4.7 | `check(submission, valid_on=date)` picks the rule set by validity date, never "latest" | `s-legacy-1` with valid_on 2026-11-01 (13.3): exact match. With valid_on 2027-01-01 (13.4): bug R41-2 |

### M5 Spec diff and test builder

| Task | Implement | Test / how |
|---|---|---|
| M5.1 | `specdiff.diff(v_old_txt, v_new_txt) -> [Change]` with block + field attribution, TOC and page headers ignored (port of `tools/specdiff.py`) | 13.3 vs 13.4: change list contains the DBVO chaining sentence, DBSD names, DBEE end, BBNR-VU. No layout row changed |
| M5.2 | `impact(changes)` via `kg.get_affected_rules` (tiers `recompute` and `review`, `07_KNOWLEDGE_GRAPH.md` section 7) | DBVO change -> recompute R41-2, R41-3 -> peter, peter-gap-*, peter-hidden, peter-gap-exact-hidden, BP 13.2, BP 13.3; F41/K61 only in review |
| M5.3 | `builder.recompute(test_cases, old_version, new_version)`: expected chains under both, list the ones that differ | only `peter-gap-exact` and its hidden variant `peter-gap-exact-hidden` differ between 13.3 and 13.4 |
| M5.4 | `builder.clone(base, branch_point, change) -> Scenario` with `parent_id`, and `builder.boundaries(rule, base)`: generate threshold -1 / = / +1 variants | boundaries(R41-4, peter) -> b27, b28, b29, b30. boundaries(R41-2, peter) -> gap-in, gap-exact, gap-out |
| M5.5 | test package: scenario YAML + expected TEEL0 + TEEK0 + story text, status `draft` until approved | package for `peter-gap-exact` contains 3 files + story |
| M5.6 | **hidden variants**: `builder.hidden(test_case, seed)` shifts dates, targets month ends and leap years, keeps the rule boundary; stored with `hidden=true`, never exported with expected files | `peter-gap-exact-hidden` (prior 27.07 to 31.08.2025, current 28.02 to 09.03.2026, 46 days) expects no 41 under 13.3 and a 41 under 13.4 |
| M5.7 | **test runs in rounds**: `run.start(test_case)` returns the story only; `run.submit(files)` checks the step and returns the next insurer reply built from the vendor's file (REF-ID = their DSID); `run.verdict()` returns pass/fail per rule without expected values for hidden tests | Peter: 4 rounds (41 / 01 / 88 + 01 / 62 import). If no 41 arrives where one is required: rule fails, run ends |

### M6 Report and signing

| Task | Implement | Test / how |
|---|---|---|
| M6.1 | report JSON: submission meta, rule set version, per step per check: outcome, expected, actual, rule, criterion, source, explanation | JSON validates against Pydantic model |
| M6.2 | HTML report (Jinja2): summary, chain timeline, table of fails/reviews with spec passage | open in browser, fail rows show the passage text |
| M6.3 | signing: SHA-256 of each input file and of the report JSON, Ed25519 signature, `verify(report)` | change one byte in the report -> verify fails |

### M7 Store, seed, API

| Task | Implement | Test / how |
|---|---|---|
| M7.1 | `store/schema.sql` per `diagrams/07_data_model.md` (app data only, rules and spec stay behind `kg/`) | applies cleanly on the Postgres container |
| M7.2 | `store/seed.py`: section 7 seed data | after seed: 14 test cases, 10 submissions; `kg` returns 2 spec versions and the rule set |
| M7.3 | API endpoints (section 6) | `httpx` tests for each endpoint against seeded data |
| M7.4 | **intake**: `POST /submissions` stores the files with SHA-256, parses them and returns a receipt `{accepted / rejected, issues[]}`, like eVpT's processing confirmation | corrupt file -> rejected with the parse issue; valid file -> accepted and checkable |

### M8 LLM services

| Task | Implement | Test / how |
|---|---|---|
| M8.1 | `explain(verdict, passage)`: 2 to 4 sentences, German or English, must quote the rule id and section; reject output without them | for the July-period fail, text mentions R41-3 and 3.12 |
| M8.2 | `story(scenario)`: TA-style month-by-month description for the test package | Peter story lists the 4 prior periods and 11.03.2026 |
| M8.3 | `extract(passage)`: draft a rule (condition + parameters) from the 3.12 text, shown next to the approved rule | draft for the chaining sentence contains a 6-month parameter |
| M8.4 | cache LLM outputs by input hash, so the demo works offline after one run | second run makes no API call |
| M8.5 | **AI deviation triage**: input = deviation + context from `kg.get_deviation_context` (rules, passages, precedents, flagged blocks); output JSON `{proposal: likely_variant / likely_bug / unclear, reasoning, citations[], confidence}`; rejected if no citation; never sets a final label | `s-no-contact` (41 without DBAP): proposal "likely bug", cites Beispielpapier 13.1 where every 41 carries MM-ANSPRECH = J |
| M8.6 | **advisor decision -> precedent**: `POST /deviations/{id}/decide` stores label + reason, adds the signature to the catalogue | re-check `s-no-contact`: resolved by precedent, no AI call |

### M9 Knowledge graph integration

| Task | Implement | Test / how |
|---|---|---|
| M9.1 | `kg/interface.py` (section 5) + `yaml_backend` | all engine tests pass using yaml_backend |
| M9.2 | `graph_backend` (teammate) behind the same interface, switch via `KG_BACKEND=graph` | same tests pass with graph_backend |

## 5. Knowledge graph interface (contract with the teammate)

```python
class KnowledgeBase(Protocol):
    def get_layout(self, record: str, version: str) -> Layout: ...
    def get_rules(self, abgabegrund: str, version: str) -> list[Rule]: ...
    def get_param(self, name: str, version: str | None = None, on_date: date | None = None) -> Any: ...
        # by date: real versions only; simulated values (sim-13.5) only by version
    def get_passage(self, ref: SpecRef) -> Passage: ...          # doc, version, section, text, page
    def search_passages(self, text: str) -> list[Passage]: ...
    def get_affected_rules(self, changes: list[str]) -> Impact: ...
        # Impact = {recompute: [Rule], review: [Rule], tests: [TestCaseRef]}; builder uses recompute only
    def get_deviation_context(self, record: str, field: str, abgabegrund: str, version: str) -> DeviationContext: ...
    def add_precedent(self, p: Precedent) -> None: ...
    def find_precedent(self, signature: str) -> Precedent | None: ...
    def get_versions(self, document: str) -> list[Version]: ...  # with valid_from
    def subgraph(self, label: str, key: str, depth: int = 1) -> Graph: ...   # UI only
```

This is the final contract (agreed with `07_KNOWLEDGE_GRAPH.md` section 11). Precedents live behind this interface: the graph backend stores `Precedent` nodes, the YAML backend appends to `kg/seed/precedents.yaml`.

`Layout`, `Rule`, `Passage`, `SpecRef`, `Version` are Pydantic models in `engine/model.py`. The YAML backend is the reference implementation and must stay working.

## 6. API

| Method | Path | Body / params | Returns |
|---|---|---|---|
| GET | `/health` | | ok |
| POST | `/parse` | file | parsed records + issues |
| GET | `/versions` | | spec versions |
| GET | `/rules?version=13.4` | | rules with params and sources |
| GET | `/test-cases` | `?kind=&hidden=` | list |
| GET | `/test-cases/{id}` | | scenario, expected chain, parent, files |
| GET | `/test-cases/{id}/expected?version=` | | expected chain under a version |
| POST | `/check` | `{test_case_id, valid_on, files[]}` or `{submission_id, valid_on}` | CheckResult: deviations with labels, `resolved_by`, AI proposals |
| GET | `/submissions/{id}/diff` | | side-by-side diff (solution vs vendor), field modes, labels |
| GET | `/advisor/queue` | | unclear deviations with AI proposals |
| POST | `/deviations/{id}/decide` | `{label, reason, advisor}` | stores decision + precedent |
| POST | `/runs` | `{test_case_id}` | run id + story (inputs only) |
| POST | `/runs/{id}/submit` | files | step check + next insurer reply (TEEK0) or end |
| GET | `/runs/{id}/verdict` | | pass/fail per rule (no expected values for hidden tests) |
| GET | `/submissions/{id}/report` | `?format=json\|html` | signed report |
| POST | `/specdiff` | `{document, old_version, new_version}` | changes + affected rules + affected test cases + recomputed expectations |
| POST | `/builder/boundaries` | `{rule_id, base_test_case_id, version}` | draft clones |
| POST | `/builder/clone` | `{base_id, branch_point, change}` | draft clone |
| POST | `/test-cases/{id}/approve` | `{approver, decision}` | updated status |
| GET | `/passages/{doc}/{version}/{section}` | | passage text |
| GET | `/passages/search?q=` | | full-text search for the advisor |
| POST | `/submissions` | files, `test_case_id`, `valid_on` | receipt: accepted, or rejected with format issues |
| GET | `/submissions` | `?test_case_id=` | list for the results view |
| POST | `/builder/hidden` | `{test_case_id, seed}` | hidden variant (stored, never exported) |
| GET | `/test-cases/{id}/package` | | zip with scenario, expected TEEL0/TEEK0, story (refused for hidden tests) |
| GET | `/graph/subgraph` | `?label=&key=&depth=` | nodes and edges for the impact view |

## 7. Seed data: what the database contains and which diffs it shows

### Spec
| Item | Content |
|---|---|
| Spec versions | Verfahrensbeschreibung 13.3 (valid 2026-01-01), 13.4 (valid 2027-01-01), optional sim-13.5 |
| Sections | DBVO 3.12 chaining passage in both versions, DBSD 3.20, DBEE 3.7.3, DSLW 3.1.10, DBID 3.19 |
| Spec diff | the real 13.3 -> 13.4 change list (`04_SPEC_DIFF_13.3_TO_13.4.md`) |

### Rules
Vorerkrankung rule set (`03_DOMAIN_RULES_VORERKRANKUNG.md`) with parameters per version, ITSG criteria with UUIDs.

### Test cases
| ID | Kind | Purpose |
|---|---|---|
| peter | reference | full chain 41, 61, 01, 61, 88, 01, 62 |
| peter-gap-exact | clone | **flips between 13.3 and 13.4** |
| peter-gap-in, peter-gap-out | clone | boundary neighbors |
| peter-b27 .. peter-b30 | clone | 30-day threshold (and sim-13.5) |
| peter-noteless | clone | negative case: no 41 |
| peter-hidden | hidden | shifted dates |
| peter-gap-exact-hidden | hidden | month-end variant of the gap case, also flips |
| bp-13-1 .. bp-13-5 | reference | Beispielpapier examples |

### Submissions (vendor files)
| ID | Test case | Content | Expected result |
|---|---|---|---|
| s-itsg-ref | peter | ITSG's real TEEL0 file for step 1 + generated rest of the chain | exact match |
| s-variant | peter | different DSIDs, timestamps, product id, sender data | exact match (these are rule/ignore fields; a naive all-field diff would flag each one) |
| s-three-periods | peter | 41 lists 3 of 4 periods | correct variant (rule re-check) |
| s-missing-july | peter | July period dropped | bug R41-3 |
| s-wrong-order | peter | periods oldest first | bug F41-8 |
| s-stale-efz | peter | second 01 still says 30.03, no 88 | bug E-1, E-2 |
| s-insurer-field | peter | AU-AB-SV filled by the employer | invalid F41-6 |
| s-no-contact | peter | 41 without DBAP (MM-ANSPRECH = N) | unclear -> AI proposal -> advisor -> precedent |
| s-legacy-1 | peter-gap-exact | vendor still on 13.3 logic: no 41 sent | exact match under 13.3, **bug under 13.4** |
| s-legacy-hidden | peter-gap-exact-hidden | same vendor, dates 31.08.2025 / 28.02.2026 | bug under 13.4 |

### The three diffs the demo shows
| Diff | Between | Endpoint |
|---|---|---|
| Spec diff | 13.3 vs 13.4 text | `POST /specdiff` |
| Result diff | `s-legacy-1` checked under 13.3 vs 13.4 | `POST /check` twice |
| Checking diff | all submissions: plain diff like today's (deviation count) vs our labels | `GET /submissions/{id}/diff`, `POST /check` |

## 8. Prototype done when

- [ ] ITSG's TEEL0 file parses and round-trips byte-identical
- [ ] all rows of the rules doc test tables pass under 13.3, 13.4 and sim-13.5
- [ ] Peter's full chain is generated (TEEL0 + TEEK0) and checks all green
- [ ] every seed submission gets its expected label
- [ ] `s-no-contact` goes through AI proposal, advisor decision, and is resolved by precedent on re-check
- [ ] Peter runs as 4 rounds through `/runs`, and a hidden variant returns only pass/fail
- [ ] `/specdiff` 13.3 vs 13.4 returns the DBVO change and identifies `peter-gap-exact` (recompute tier = R41-2, R41-3 only)
- [ ] all engine tests pass with `KG_BACKEND=yaml` and `KG_BACKEND=graph`
- [ ] signed HTML report for one fail and one pass submission
- [ ] at least one LLM explanation shown for a fail, cached for offline demo
- [ ] frontend can call every endpoint used in the demo storyline
- [ ] in the vendor view, a vendor uploads a file, gets a receipt, receives the next insurer reply and downloads the signed report

## 9. Assumptions and risks

| Item | Handling |
|---|---|
| 6-month counting (from end date or day after) | parameterized, ask ITSG, document in the report |
| DBNA positions 65-125, DBAP names, DBAN unknown | writer pads unknown parts with spaces, parser does not check them |
| Content of 01 salary fields (DBAL/DBAE) depends on vendor payroll | `compare_mode: ignore` except dates and flags |
| 62 field values (EEL-ABAG, EEL-ABSV) derived from Beispielpapier 17.1 | marked derived in the scenario |
| File character set (sample is UTF-8 with umlauts) | parse as UTF-8, fall back to Latin-1, count characters not bytes |
| LLM unavailable during demo | cached outputs (M8.4) |
| VB 13.4 is internally inconsistent on the 6-month rule (employer sentence changed, insurer paragraph and 3.12.7 not) | follow the employer sentence for R41-2/R41-3, show the inconsistency in the spec diff, ask ITSG (`00` question 9) |
| Anlage 3 (data blocks per Abgabegrund) not available | DBAP and DBAN on a 41 stay `unclear` (s-no-contact), never `invalid` |
| DBAN layout missing, but Beispielpapier 13.1 sets MM-ANSCHRIFT = J on a 41 | parser reports `ParseIssue(unknown block)` instead of crashing; deviation goes to the advisor |
| ITSG DATENSATZ-IDs are not RFC 4122 (`11111111-2222-AAAA-...`) | UUID check = regex `^[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}$` (case-insensitive), no version check |
