# Roadmap to 11 December 2026

The goal: a near-finished EEL test platform for a live demo to the GKV and ITSG on 11 December 2026 and a likely pilot discussion after. Background and decisions are in [`PROJECT_REPORT.md`](PROJECT_REPORT.md) (gaps: section 5.2, decisions: section 9).

How to read this file:

- Work is split into **goals** (G0 to G18). Each goal can be picked up and finished alone. A goal lists what it needs first under "Needs".
- Phases follow the decided order: **scope → AI rule derivation → hardening**, then demo preparation. There is no schedule: each goal is worked until it is done properly.
- A task is done when its tests pass in CI. A goal is done when its "Done when" line holds.
- Tick the boxes on `main` as work lands, so everyone sees the current state.

| Phase | Goals |
|---|---|
| 0 Foundation | G0, G1 |
| 1 Full EEL scope | G2–G8 |
| 2 Expert knowledge and AI rule derivation | G9–G13 |
| 3 Hardening | G14–G17 |
| 4 Demo | G18 |

---

## Phase 0: Foundation

### G0. CI and a clean baseline

Why: every later goal relies on a green, reproducible check.

- [ ] GitHub Actions workflow on Linux: `uv run pytest -q`, `uv run ruff check .`, `npm run build` (includes `tsc`), `npm run check:i18n`
- [ ] Install `poppler-utils` in CI so the annex tests run as intended
- [ ] Make `test_vb_annex_centered_chapters_work_with_linux_poppler_indentation` pass on Windows too, or mark it Linux-only with a clear reason
- [ ] Neo4j service container in a second CI job with `NEO4J_TESTS=1`
- [ ] Fix or document `test_search_finds_chaining[graph]` (German full-text ranking)

Done when: every push to `main` and every PR shows a green check.

### G1. ITSG questions and German-only UI

Why: answers from the ITSG contact unblock several scope goals; the English UI is extra work on every new screen.

- [ ] Send the 10 questions of `PROJECT_REPORT.md` section 9 to the ITSG contact; add the request for VB Anlage 3 and example cases with solution files for 02, 03 and the other messages
- [ ] Record each answer in `PROJECT_REPORT.md` and in the affected rule or parameter
- [ ] Remove the English locale and the language switch; keep the i18n key structure so texts stay in one place
- [ ] Update the i18n check to German only

Done when: questions sent, UI has one language, i18n check green.

Needs: nothing.

---

## Phase 1: Full EEL scope

Scope as decided: certificates 01, 02, 03, the other messages and error cases. G4 (02) and G5 (03) are built side by side. Test cases are written from the VB and Beispielpapier text, then replaced or validated with ITSG's cases when they arrive. Each certificate goal follows the same pattern: layouts, rules with spec citations, expected chains, test cases (boundary clones and hidden variants), checker labels, insurer replies.

### G2. Generalise the engine beyond prior illnesses

Why: today `engine/rules/vorerkrankung.py` and the Peter chain are the only scenario family. New families must plug in without special cases.

- [ ] Define a scenario family interface (inputs, expected chain builder, rules, compare modes) and move the prior-illness logic behind it
- [ ] Map each Abgabegrund to its required and optional data blocks (VB Anlage 3, or the VB text until it arrives)
- [ ] Check every layout in `layouts/` against GG Anlage 1 (`tools/compare_anlage1`), fill gaps
- [ ] Test cases name their family; catalogue, runs and reports group by family
- [ ] Complete the existing rules (`PROJECT_REPORT.md` section 5.2, item 12):
  - [ ] Implement E-3 (an update only in interim flags 3 or 4 does not cancel the earlier 61); today it has a rule card and no code
  - [ ] Compute K61-4 (KZ-NACHWEIS) and K61-5 (KZ-AU) from the case facts; today they are typed into the test data
  - [ ] Call `check_61` and `check_62` (K61-1..3, K62-1) on every 61/62 the insurer simulator writes, as a self-check; today they are never called
  - [ ] Complete the DBAN layout (today only KENNUNG)
  - [ ] One test per rule ID, so every rule is shown to be covered

Done when: Peter still passes unchanged, all 37 existing rules have code and a test, and a second family can be added by adding files, not by editing the checker.

Needs: G0.

### G3. Certificate 01 Krankengeld, complete

Why: 01 appears in Peter's chain, but only the fields that touch the chain are checked.

- [ ] Rules for all 01 fields and blocks (salary data, working time, one-off payments, contact data) with VB citations
- [ ] Connect the Krankengeld calculator: expected salary values on the 01 are computed, not typed into the test data
- [ ] Extend the calculator to the cases it lacks (Entgeltumwandlung, flexible working time, Altersteilzeit, output-based pay, the special cases of RS Anl. 3 4.1.1.1.1.2)
- [ ] Test cases: monthly pay, hourly pay, part time, one-off payment, start of employment mid-month, plus hidden variants
- [ ] Insurer replies to a 01 (62 benefit end, error replies)

Done when: an 01 with every block is checked field by field, each deviation cites a passage.

Needs: G2.

### G4. Certificate 02 Kinderkrankengeld

- [ ] Layouts and rules for 02 (child data, care days, limits per child and year)
- [ ] Expected chain and test cases, including limit boundaries and a hidden variant
- [ ] Insurer replies and checker labels

Done when: a vendor can run a 02 test case end to end and get a signed report.

Needs: G2.

### G5. Certificate 03 Mutterschaftsgeld

- [ ] Layouts and rules for 03 (protection periods before and after birth, expected and actual birth date, premature and multiple births)
- [ ] Expected chain and test cases at the period boundaries, plus a hidden variant
- [ ] Insurer replies and checker labels

Done when: a vendor can run a 03 test case end to end and get a signed report.

Needs: G2.

### G6. Other messages: 42, 51, 73, 99 and insurer 66, 67, 71, 72

- [ ] For each Abgabegrund: layout check, rules, when it is due, expected reply
- [ ] Insurer simulator sends 66/67 error replies when the vendor's file is wrong, so the vendor has to react
- [ ] Cancel (88) and correction paths for every certificate, not only Peter's

Done when: every in-scope Abgabegrund has at least one executable test case.

Needs: G2.

### G7. Error cases and robustness

Why: the demo should show complex situations, not only the happy path.

- [ ] Test cases built from wrong vendor files: invalid codes, missing mandatory blocks, wrong order, duplicates, wrong envelope, encoding errors
- [ ] Format check returns precise, cited errors for each; no crash on any malformed upload (fuzz the parser)
- [ ] Mixed chains: two certificates for one employee, overlapping periods, change of insurer
- [ ] Checker labels stay correct under these cases (invalid > bug > unclear > correct variant > exact match)

Done when: a corpus of broken files runs in CI and each gets the expected label.

Needs: G3 (works best after G4–G6).

### G8. Certification flow and automation

Why: the demo story includes a new vendor completing the yearly catalogue and earning the certified label.

- [ ] Vendor lifecycle: new, in certification, certified, under yearly audit
- [ ] Yearly catalogue per vendor; progress per test case and family
- [ ] Certified label when every required case passes; label unlocks the permanent test cases
- [ ] Deadlines in the calendar from ITSG's real rules (G1 answers), reminders in the vendor view
- [ ] Signed certification report in addition to per-run reports

Done when: a fresh vendor account goes from zero to certified in the UI, and the permanent cases appear.

Needs: G2; G14 for real accounts (works with the demo toggle before that).

---

## Phase 2: Expert knowledge and AI rule derivation

### G9. Expert knowledge capture

Why: the experts who retire take the reasons with them: why a deviation is acceptable, how they read an unclear passage. Today an advisor decision is stored as a precedent with a short optional reason, matched only by its exact signature, with no spec version and no review. Decided cases become the asset the system learns from and the tests every rule change must pass.

- [ ] A decided case stores: the deviation and the case facts, verdict, reason in the expert's words (required), the passages relied on (required), author, date, the spec version or validity date it holds for
- [ ] Scope per decision: exact signature by default; the expert can widen it to a named pattern (e.g. any missing DBAP on a 41)
- [ ] Conflicting decisions on the same situation are flagged and must be resolved; the resolution is recorded
- [ ] A random sample of confident verdicts (rules, catalogue, precedents) goes to an expert for review, not only the unclear ones; the share is set per category, higher while a category is new and lower as agreement grows
- [ ] Every confirmed case becomes a regression test that runs in CI
- [ ] Groups of similar decisions are proposed as a rule definition in the G10 format; an expert approves before it is used
- [ ] Agreement rate between AI proposal and expert verdict, per category, shown in the UI as the measure of readiness
- [ ] Ask the ITSG contact for real past eVpT deviations with the advisor's verdict as the starting set; until they arrive, use synthetic decided cases, marked as such

Done when: an advisor decision carries its reason, passages and validity, a conflicting decision is caught, and the decision runs as a test.

Needs: G0; G10 for promoting decisions to rules.

### G10. Rules as data

Why: today rules are hand-coded and the AI only adjusts existing parameters (gap 2 in section 5.2). G10 to G12 let the AI turn spec text into executable rules, while still never computing results itself.

- [ ] Own YAML rule types, readable by ITSG experts and stored next to `kg/seed/rules.yaml`, that cover the hand-coded rules: date window, day sum, period chaining, field format, code list, block presence, cross-field consistency
- [ ] The engine interprets these rule definitions; expected results stay deterministic
- [ ] Re-express the existing 37 rules as data; the old Python and the new definitions must give identical results on all test tables

Done when: the hand-coded rules are deleted or reduced to the interpreter, and all tests are unchanged.

Needs: G2.

### G11. Spec text to executable rule

- [ ] Agent reads a spec section and proposes rule definitions in the G10 schema, with citations that must resolve to real passages
- [ ] Code validates each proposal (schema, parameter types, referenced fields exist in the layouts) and runs it against the existing test tables
- [ ] ITSG reviews proposals in the UI (diff against the current rule, affected tests, approve or reject); only approved rules become active
- [ ] Wire the existing criteria pipeline (`/criteria/extract`) into the UI
- [ ] A new rule from a spec change creates new test cases through the builder
- [ ] Switch the agents to the strongest available OpenAI model; re-run the VB 13.4 analysis once so the cache holds the new answers

Done when: uploading a spec change that needs new logic (not just a parameter) ends with an approved, executable rule and new test cases, without a developer.

Needs: G10.

### G12. Measure the AI

- [ ] Golden set: spec sections paired with the known correct rule definitions (from G10)
- [ ] Evaluation script reports match rate, wrong citations, rejected proposals; run it on every prompt change
- [ ] Report the agreement rate with expert decisions (G9) next to the match rate
- [ ] Prompt versions recorded with cached answers so cache invalidation is deliberate
- [ ] Second real document path: a Rundschreiben or GG update end to end

Quality bar: a derived rule is accepted only if it gives the same results as the known rule on every test table, and an expert approves it.

Done when: the match rate is known and shown in the report, and a prompt change cannot silently lower it.

Needs: G11.

### G13. Gated code agent

Why: some new rules (e.g. a calculation the rule types cannot express) still need code. An agent may write it, but only behind the same guardrails a human change has.

- [ ] Agent works on its own branch and may only change rule and calculator modules, never the checker, the signing or the tests
- [ ] Its change must pass every existing test, every expert decided case (G9) and the G12 quality bar
- [ ] It opens a pull request with the diff, the spec passages and the test results; a human merges
- [ ] Every change is versioned and can be rolled back

Done when: a spec change that needs new code ends in a pull request that passes CI and a human can merge.

Needs: G11, G12.

---

## Phase 3: Hardening

### G14. Login and roles

- [ ] Login with Clerk: its React components in the UI, its session token verified in FastAPI on every request
- [ ] Role (ITSG staff, vendor) and company stored on the Clerk user or organisation, mirrored in Postgres for joins
- [ ] Sign-up restricted: ITSG staff invite vendor accounts; no self sign-up
- [ ] Check where Clerk stores account data and record it in `PROJECT_REPORT.md` (the GKV audience will ask)
- [ ] Every endpoint checks role and company; vendors see only their own runs and reports
- [ ] Hidden test expectations and the reset endpoint protected on the server, not only in the UI
- [ ] Replace the ITSG/vendor demo toggle with real accounts; seed demo accounts for the pitch

Done when: tests prove a vendor cannot read another vendor's data or any hidden expectation through the API.

Needs: G0.

### G15. Security measures

- [ ] Upload limits (size, type, count), safe file names, no path traversal under `DATA_DIR`
- [ ] Rate limits on login and AI endpoints; AI cost cap per day
- [ ] CORS limited to the UI origin; security headers; HTTPS only
- [ ] Audit log of logins, uploads, approvals and advisor decisions
- [ ] Secrets (OpenAI key, Clerk keys, DB passwords, signing key) in Google Secret Manager, never in the image
- [ ] Dependency and container scanning in CI

Done when: a checklist review passes and is recorded in `PROJECT_REPORT.md`.

Needs: G14.

### G16. Google Cloud deployment

Budget: $300 free credits; keep a budget alert. Region: Frankfurt (`europe-west3`), so data stays in Germany.

- [ ] API and UI on Cloud Run (UI as static files behind the API or its own service)
- [ ] Postgres on Cloud SQL (smallest instance), Neo4j Community in Docker on a small Compute Engine VM in the same region
- [ ] `DATA_DIR` files, `kg/build/` and `data/llm_cache/` on Cloud Storage
- [ ] Deploy from `main` with GitHub Actions after CI passes
- [ ] Budget alert and a cost estimate in `PROJECT_REPORT.md`

Done when: the platform runs on Google's default HTTPS URL and a push to `main` updates it.

Needs: G0; G15 for the secrets part.

### G17. Reliability

- [ ] PDF reports work in the deployed image (WeasyPrint)
- [ ] Health checks, structured logs, error pages that do not leak internals
- [ ] Database backups and a tested restore
- [ ] Demo reset that works in the cloud, admin only
- [ ] Load check: several vendors uploading at once

Done when: a restore from backup and a full demo run work on the deployed instance.

Needs: G16.

---

## Phase 4: Demo

### G18. Demo for 11 December

- [ ] Demo script: vendor run with full EEL coverage, deviations judged, VB 13.4 upload, rules and tests update, signed report, new vendor reaching the certified label
- [ ] Demo data and accounts, seeded by one command
- [ ] AI calls run live during the demo; cached answers take over automatically if the network or OpenAI fails; a local run as last resort
- [ ] Answers ready for expected questions (data protection, AI errors, cost, how ITSG would run it)
- [ ] Update `README.md` and `PROJECT_REPORT.md` to the delivered state; slides
- [ ] Two full rehearsals on the deployed instance

Done when: two rehearsals in a row run without a fix in between.

Needs: all goals that are part of the script.
