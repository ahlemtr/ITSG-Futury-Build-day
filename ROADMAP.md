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
| 1 Full EEL scope | G2–G8 (incl. G2b, G6b) |
| 2 Expert knowledge and AI rule derivation | G9, G9b, G10–G13 |
| 3 Hardening | G14–G17 |
| 4 Demo | G18 |

---

## Phase 0: Foundation

### G0. CI and a clean baseline

Why: every later goal relies on a green, reproducible check.

- [x] GitHub Actions workflow on Linux: `uv run pytest -q`, `uv run ruff check .`, `npm run build` (includes `tsc`), `npm run check:i18n`
- [x] Install `poppler-utils` in CI so the annex tests run as intended
- [x] Make `test_vb_annex_centered_chapters_work_with_linux_poppler_indentation` pass on Windows too, or mark it Linux-only with a clear reason (it was a splitter bug on every platform, not poppler: fixed in `kg/extract/generic.py`, test renamed `test_vb_annex_centered_chapters_are_headings`)
- [x] Commit the VB 13.4 PDF so a fresh checkout (and CI) has the full seed; 21 tests need its passages
- [x] Neo4j service container in a second CI job with `NEO4J_TESTS=1`
- [x] Fix or document `test_search_finds_chaining[graph]` (it was not German full-text ranking: the fusion in `kg/graph_backend.py` added up every chunk of a passage, so a long passage with many weak chunks beat one strong chunk; now each passage counts once per list, at its best chunk)

Done when: every push and every pull request into upstream `main` shows a green check.

### G1. ITSG questions and German-only UI

Why: answers from the ITSG contact unblock several scope goals; the English UI is extra work on every new screen.

- [x] Send the essential questions to the ITSG contact (5 questions, email scheduled for 2026-11-02 08:00; see `PROJECT_REPORT.md` section 9). The other questions run on the team's working assumptions and are asked later only if needed
- [x] Look for the published TA 167/168 solution proposals on the ITSG/GKV download page (the PTA says they are published) before waiting for ITSG (not needed: ITSG sent them directly on 2026-11-02, answer to question 1; the work they start is G2b)
- [ ] Record each answer in `PROJECT_REPORT.md` and in the affected rule or parameter (question 1 answered 2026-11-02, recorded in G2b; questions 10, 11, 12, 14 still open)
- [x] Remove the English locale, the language switch and the English part of `ui/src/i18n/glossary.md`; keep the i18n key structure so texts stay in one place (`en.json` deleted; the `{de, en}` text pairs in the UI code are plain German strings now; `glossary.md` is the German vocabulary)
- [x] Update the i18n check to German only (`ui/scripts/check-i18n.mjs`: only `de.json` allowed, no empty texts, every literal key the code uses exists)

Done when: questions sent, UI has one language, i18n check green.

Needs: nothing.

---

## Phase 1: Full EEL scope

Scope as decided: all 22 EEL codes (certificates 01–04, the other employer and insurer messages, the extra module 11–31) and error cases. G4 (02) and G5 (03) are built side by side. Test cases are written from the VB and Beispielpapier text, then replaced or validated with ITSG's cases when they arrive. Each certificate goal follows the same pattern: layouts, rules with spec citations, expected chains, test cases (boundary clones and hidden variants), checker labels, insurer replies.

### G2. Generalise the engine beyond prior illnesses

Why: today `engine/rules/vorerkrankung.py` and the Peter chain are the only scenario family. New families must plug in without special cases.

- [x] Define a scenario family interface (inputs, expected chain builder, rules, compare modes) and move the prior-illness logic behind it (`engine/families/base.py`; prior illness in `engine/families/vorerkrankung/`; a family is found by its folder)
- [x] Map each Abgabegrund to its required (J), optional (m) and forbidden (N) data blocks from VB Anlage 3 13.3 (`sources/vb/`, table in chapter 2); replace every `mandatory: unknown` in `kg/seed/message_types.yaml`; add VB Anlage 3 to `documents.yaml` (`block_table`, new common rule A3-1)
- [x] Rules from VB Anlage 3 chapter 3 (continuity of benefits, § 69 SGB IX): which change of benefit needs a new 01/02/03/11-31 and which does not; one gap day always needs a new one (`kg/seed/continuity.yaml`, `engine/rules/continuity.py`, rule A3-2)
- [x] Check every layout in `layouts/` against GG Anlage 1 (`tools/compare_anlage1`), fill gaps (247 fields, no structural difference; DBAP confirmed; 24 M/m-only findings documented)
- [x] Version the record layouts by validity date like the rules (VB Anlage 1 13.1.4 changes them on 01.07.2027, not at a year start) (`get_layout(..., on_date)`; same structure in 13.1.3 and 13.1.4, 15 check texts differ)
- [x] Fix the Beispielpapier versions: BP 13.2 (`sources/beispielpapier/`, valid 2026) belongs to VB 13.3, BP 13.3 to VB 13.4 (2027); add BP 13.2 to `documents.yaml` and correct the 13 `BP@13.3` citations in `rules.yaml` and `test_cases.yaml` (the five prior-illness examples are identical in both, so the expected results stay)
- [x] Test cases name their family; catalogue, runs and reports group by family ("Fallgruppe")
- [ ] Complete the existing rules (`PROJECT_REPORT.md` section 5.2, item 12): all done except the R41-5 wording, which waits for ITSG
  - [x] Implement E-3 (an update only in interim flags 3 or 4 does not cancel the earlier 61); today it has a rule card and no code
  - [x] Compute K61-4 (KZ-NACHWEIS) and K61-5 (KZ-AU) from the case facts; today they are typed into the test data (facts `sick_note`, `insurer_gets_note`, `counts`, `insurer_rechecks` per period)
  - [x] Call `check_61` and `check_62` (K61-1..3, K62-1) on every 61/62 the insurer simulator writes, as a self-check; today they are never called
  - [ ] Reword the R41-5 rule card once ITSG answers question 5 (the Pflichtenheft and ITSG's criteria file disagree)
  - [x] Link R41-5 to Pflichtenheft item a4770b2b and R41-6 to item ac3b56af (today only R41-1..4 carry their item ID)
  - [x] New rules for the two prior-illness items with no rule: a 41 only for people with statutory health insurance, addressed to their insurer; never for privately insured people or employee groups 109 and 110 (R41-7, R41-8; 109 and 110 are marginal employment)
  - [x] Complete the DBAN layout from Pflichtenheft Anlage 19 (KENNUNG, LAENDERKENNZ, PLZ, WOHNORT, STRASSE, HAUS-NR, ADR-ZUSATZ)
  - [x] One test per rule ID, so every rule is shown to be covered (`tests/test_rule_coverage.py` is strict)
  - [x] Review every rule against its sources: no rule twice, each card's scope where the documents say it holds, one place for its code (2026-11-03: 45 cards became 36; the 88 sends KORR-ABGABEGRUND 00, VB 3.1.19, BP 23; private insurance is R41-8. Code review 2026-11-07: a failed check labels only its own message, cross-message checks do not depend on file order, the names on an 88 are always checked, DATENSATZ-ID format split off as S-3, 37 cards; `tests/test_checker_matching.py`)
- [x] Backend texts the UI shows in German: rule titles (`kg/seed/rules.yaml`), check explanations and format messages are English today (found in G1); change them together with the rule cards, not the AI prompts

Done when: Peter still passes unchanged, all 37 existing rules have code and a test, and a second family can be added by adding files, not by editing the checker.

State 2026-11-07 (pull request #7 into upstream `main`, open; the rule review is #9): the done-when line holds. Peter's employer files and check results are byte-identical (golden snapshot `tests/golden/engine.json`); the insurer's 61 and 62 now carry a DBAP, as VB Anlage 3 requires. All rule cards have code and a test (37 after the rule review and its code review); a test-only family under `tests/fakes/families/demo/` runs through the core without any core change. Open: the R41-5 wording (ITSG question 5). The two paid steps are done (2026-11-02, G2b session): embeddings for the new chunks and one re-run of the VB 13.4 analysis, together about $0.27.

Needs: G0.

### G2b. Official test tasks TA 167 and TA 168 as locked tests

Why: on 2026-11-02 ITSG sent its solution proposals ("Musterlösungen") for TA 167 and TA 168: two Excel workbooks and four TEEK0 insurer replies (0521, 0523, 0524 for TA 167, three 61s; 0527 for TA 168, a 71). They are the first real insurer files we have and the first official exam tasks with a solution. ITSG calls them non-binding ("unverbindliche Vorschläge"), so they become locked tests that allow justified variants. Analysis of 2026-11-02 (all four TEEK0 files parse with no issue; periods, order, KZ-NACHWEIS and KZ-AU of our simulated 61s match ITSG's in all three rounds of TA 167; two fields and two EFZ end dates differ) is summarised in `PROJECT_REPORT.md` section 9.

Decisions of 2026-11-02:
- Nothing from the delivery is committed until publication is cleared with ITSG: the workbooks name ITSG staff and hold internal review notes, and upstream is public. The files stay local and are kept out of Git with `.gitignore`; tests that read them skip when they are missing (CI).
- 12-MONATSFRIST-AB follows TA 167: 12 months before the start of the earliest AU that counts, or 12 months before the current AU when none counts, always filled. This contradicts the Peter Hinweise and BP 16.1 (start of the earliest counting AU) and is recorded as a contradiction.
- ITSG's values are locked, including the EFZ ends of rounds 2 and 3.
- PTA 2025/2026 tasks are checked under VB 13.3 (validity date 01.01.2026 for parts dated 2025), because our knowledge base has no rule set valid in 2025.

Files and sources
- [x] Move the TEEK0 files to `fixtures/itsg/ta-167/` and `fixtures/itsg/ta-168/`, the workbooks to `sources/testaufgaben/loesungen/`; add both paths to `.gitignore`
- [x] `kg/seed/documents.yaml`: entry `PTA-LSG` (solutions to the Pool-Testaufgaben 2025/2026, ITSG, received 2026-11-02, not published, file local only) so test values can cite sheet and cell
- [ ] Ask ITSG whether the solutions may be published in our repository; commit them only after a yes

Engine fixes found by the TEEK0 files
- [x] AU-AB-SV on the insurer's 61 stays empty unless the insurer's start date differs from the employer's (VB 3.12.3); today the simulator always fills it. New rule K61-8
- [x] Rewrite K61-6 to TA 167's reading (code, rule card, sources); read BP 16.1 in full first and stop if it clearly shows the other reading. Peter's expected 61 moves from 14.07.2025 to 14.07.2024: review the golden snapshot diff (`tests/golden/`) before regenerating it. *Stopped (2026-11-02): BP 16.1 sets 12-MONATSFRIST-AB to the start of the counting AU (01.06.20XX) and VB 3.12.5 says the same; K61-6 keeps that reading, Peter stays at 14.07.2025, TA 167's three values are strict expected failures and the question goes to ITSG (contradiction 7)*
- [x] Rule E-4: the employer counts its own EFZ days of the same illness within 12 months from the first AU (§ 3 EFZG); when the employee states it is the same illness and the six weeks are used up, no EFZ (DATUM-EGZBIS = day before DATUM-AB), whatever the 61 says (TA 167 round 3: 11.06.2026). New input fact on the current AU
- [x] Rule E-5: EFZ never runs past the end of employment
- [x] Round 2 of TA 167 (DATUM-EGZBIS 20.02.2026): no rule reproduces it consistently with ITSG's own 61 (05.12.2025–23.01.2026 counts, 50 days, so EFZ is used up) and task text ("Korrektur ... in Krankengeldbezug"). Lock ITSG's value as a strict expected failure with the reason, ask ITSG, and turn it green only when the engine or ITSG's answer explains it
- [x] Rule texts change the agents' prompts: the cached answers for K61-6 go stale; re-run only with an explicit go (paid) (done with the go of 2026-11-02, budget cap $10, spent at most $0.27)

Test catalogue
- [x] Locked-test runner (`tests/test_locked.py`): for every locked case and every rule set version it has an expected value for, build the chain from its inputs and compare with the stored expected values; any difference fails, except an allowed variant of that case. Today no test does this for all cases: some have hand-written asserts, and the golden snapshot only freezes the engine's last output (it catches change, not correctness)
- [x] Expected values of a locked case are typed in from the source document, each with its source, and never recomputed by the engine (`engine/builder.py` `recompute`, `with_expected` and the spec-change pipeline skip locked cases; a test proves it). Applies to Peter, the Beispielpapier rows and TA 167
- [x] `ta-167` becomes the parent (approved, locked) with children `ta-167-r1`, `-r2`, `-r3`, one per prior-illness round (41 + the insurer's 61 + EFZ end): inputs from the TEEK0 files, validity 01.01.2026 / 02.02.2026 / 12.06.2026, expected values with a source per value (sheet and cell)
- [x] `fixtures/scenarios/ta-167.yaml`: person (Hoffmann, Marc), employer 99301347, insurer DAK-G 99300660, insurer DBAP from the TEEK0 files
- [x] Locked marker on test cases; a locked case can never be changed by an agent (G11b relies on it)
- [x] Allowed variants per case, read by the checker before the global catalogue: in a later 41, a period the insurer already rejected (KZ-AU 2) may be left out; BEGINN-AU 06.12.2025 with AE-ERSTTAG N instead of 05.12.2025 with J (both marked optional by ITSG)
- [x] `ta-168`: correct the family (it is 02 Kinderkrankengeld, 03 Mutterschaftsgeld and the insurer's 71, not prior illness) and write down its inputs; it stays a draft until G4, G5 and G6 exist

Tests (`tests/test_ta_167.py`)
- [x] Every TEEK0 file parses with no issue
- [x] Our simulated 61 in each round equals ITSG's TEEK0 except DATUM-ERSTELLUNG, DATENSATZ-ID, AKTENZEICHEN-SV and REFERENZ-ID (ITSG leaves it blank, its own note says so; K61-1 stays)
- [x] 41 decision and periods per round; the allowed variants are labelled as variants, not bugs
- [x] DATUM-EGZBIS per round (round 2 as the strict expected failure)
- [x] Checker run on a TEEL0 written from the workbook cells (the 41s; the 01s follow in G3) gives no bug

Records
- [x] `PROJECT_REPORT.md` section 9: question 1 answered (what came, what did not: no TEEL0 files, no eVpT deviation report); new contradictions (K61-6, the two date sets in TA 167, round 2 EFZ end, the Info sheet against the real TEEK0524, REFERENZ-ID blank); follow-up questions (round 2, publication, eVpT report). Section 6: VB 13.3 for PTA 2025/2026. Section 3: catalogue line for ta-167 and ta-168

Done when: one runner checks every locked case against its document values, `ta-167-r1` to `-r3` are locked and pass (round 2 as a documented expected failure), our simulated 61s equal ITSG's TEEK0 files except the listed fields, Peter passes with its reviewed new 12-month date, and nothing from the delivery is in Git.

State 2026-11-07 (pull request #8 into upstream `main`, stacked on #7, open): done except asking ITSG about publication (the follow-up questions are drafted in `PROJECT_REPORT.md` section 9, question 1). The done-when line holds with one change: Peter keeps its 12-month date, because K61-6 kept the reading of BP 16.1 (see the K61-6 box).

Needs: G2 (merged). The 01 content of TA 167 needs G3; TA 168 needs G4, G5 and G6.

### G3. Certificates 01 Krankengeld and 04 hospital companion, complete

Why: 01 appears in Peter's chain, but only the fields that touch the chain are checked.

- [ ] Rules for all 01 fields and blocks (salary data, working time, one-off payments, contact data) with VB citations
- [ ] Connect the Krankengeld calculator: expected salary values on the 01 are computed, not typed into the test data
- [ ] Extend the calculator to the cases it lacks (Entgeltumwandlung, flexible working time, Altersteilzeit, output-based pay, the special cases of RS Anl. 3 4.1.1.1.1.2)
- [ ] Test cases: monthly pay, hourly pay, part time, one-off payment, start of employment mid-month, plus hidden variants
- [ ] Locked tests from the Beispielpapier examples of this family (ITSG's own situation and result, for 2026 from BP 13.2 and for 2027 from BP 13.3) (chapters 3, 7, 12)
- [ ] Locked test from TA 167's three 01s (G2b workbook, sheet EEL): short-time work (MM-KUG, KUG dates, DBAE skips the KUG months), hourly pay (only the last month before the AU, DBZA), unpaid days (DBAW), one-off payment (EZKV, EZRV, EZALV), Übergangsbereich not in the DBAE, end of employment (ENDE-BV-AM, ENDE-BV-ZUM, GRUNDBEEND), AE-ERSTTAG
- [ ] Insurer replies to a 01 (62 benefit end, error replies)
- [ ] Certificate 04 (Krankengeld for a companion in hospital): same blocks as the 01 plus the hospital stay, with its own test cases

Done when: an 01 with every block is checked field by field, each deviation cites a passage.

Needs: G2.

### G4. Certificate 02 Kinderkrankengeld

- [ ] Layouts and rules for 02 (child data, care days, limits per child and year)
- [ ] Expected chain and test cases, including limit boundaries and a hidden variant
- [ ] Insurer replies and checker labels
- [ ] Locked tests from the Beispielpapier examples of this family (ITSG's own situation and result, for 2026 from BP 13.2 and for 2027 from BP 13.3)
- [ ] Locked test from TA 168's two 02s (G2b workbook): two child sick periods in one month (11.–12.09.2025 with one paid day of leave, 15.–19.09.2025), DBFR fields and the lost gross and net pay per day

Done when: a vendor can run a 02 test case end to end and get a signed report.

Needs: G2.

### G5. Certificate 03 Mutterschaftsgeld

- [ ] Layouts and rules for 03 (protection periods before and after birth, expected and actual birth date, premature and multiple births)
- [ ] Expected chain and test cases at the period boundaries, plus a hidden variant
- [ ] Insurer replies and checker labels
- [ ] Locked tests from the Beispielpapier examples of this family (ITSG's own situation and result, for 2026 from BP 13.2 and for 2027 from BP 13.3)
- [ ] Locked test from TA 168's 03 (G2b workbook): DBAE because the fixed-term employment ends, DBMU with salaries because of multiple employment, RÜCKMELDUNG-ENTGELTERSATZLEISTUNG J; the insurer's 71 reply is TEEK0527 (G6)

Done when: a vendor can run a 03 test case end to end and get a signed report.

Needs: G2.

### G6. Other messages: 42, 51, 73, 99 and insurer 66, 67, 71, 72

- [ ] For each Abgabegrund: layout check, rules, when it is due, expected reply
- [ ] Locked tests from the Beispielpapier examples of this family (ITSG's own situation and result, for 2026 from BP 13.2 and for 2027 from BP 13.3) (chapters 16, 17, 20 for the insurer replies)
- [ ] The insurer's 71 (amount of the benefit, DBHE) reproduced from TA 168's TEEK0527 (ZAHL-BEGINN 10.12.2025, EEL-NETTO 10.42), as a locked test of the insurer simulator
- [ ] Insurer simulator sends 66/67 error replies when the vendor's file is wrong, so the vendor has to react
- [ ] Expected vendor reactions from the Pflichtenheft (EEL, 01 Allgemeines): after a 66, cancel and resend with the corrected type; after a 67, no cancellation; a 72 is answered with a 73; a 99 only while a benefit is running; a 71 is read in
- [ ] Cancel (88) and correction paths for every certificate, not only Peter's

Done when: every in-scope Abgabegrund has at least one executable test case.

Needs: G2.

### G6b. Extra module: 11, 12, 21, 22, 23, 31

Why: scope for December is all 22 EEL codes. These six are the Pflichtenheft's extra module "EEL-Verfahren ... Verletztengeld, Kinderverletztengeld und Übergangsgeld" (44 items), for benefits paid by pension insurance (11, 12), accident insurance (21, 22, 23) and the employment agency (31).

- [ ] Layouts and rules for the blocks they use (DBLT, DBUN, DBSF ...), with the module's 44 Pflichtenheft items as baseline
- [ ] Routing: certificates go to the pension or accident insurer instead of the health insurer (Pflichtenheft Anlage 19 lists when, e.g. privately insured people or an occupational disease)
- [ ] Expected chains, test cases with hidden variants, insurer replies and checker labels for each code
- [ ] Locked tests from the Beispielpapier examples of this family (ITSG's own situation and result, for 2026 from BP 13.2 and for 2027 from BP 13.3) (chapters 7 to 11)
- [ ] The extra module is certified separately; the certification flow (G8) shows it as its own module

Done when: every one of the six codes has at least one executable test case and a signed report.

Needs: G2; works best after G3.

### G7. Error cases and robustness

Why: the demo should show complex situations, not only the happy path.

- [ ] Test cases built from wrong vendor files: invalid codes, missing mandatory blocks, wrong order, duplicates, wrong envelope, encoding errors
- [ ] Format check returns precise, cited errors for each; no crash on any malformed upload (fuzz the parser)
- [ ] Mixed chains: two certificates for one employee, overlapping periods, change of insurer
- [ ] Test cases with deliberate mistakes in the task itself that good software must catch (the Pflichtenheft says official test tasks may contain them)
- [ ] Checker labels stay correct under these cases (invalid > bug > unclear > correct variant > exact match)

- [ ] **Official core check as the first checking step** (`sources/EEL/`, Kernprüfung EEL 13.00.05 by AOK Systems, the same check the insurers run on every file): run it as a small Java sidecar (Java 11+) from the intake step; a form error becomes "invalid" with the official error number and text (657 texts, all data blocks of all 22 codes)
- [ ] Retire our own format rules (F41, S-1) where the core check covers them; keep only what it does not check
- [ ] Build the checks the core check does not run: the 42 letter-coded checks of VB Anlage 2 ("v"/"e"/"H": 11 VOSZ, 10 NCSZ, 10 DSKO, 10 DSLW, 1 DBUN, e.g. creation date not older than 6 months, file numbers without gaps, sender number admitted), which every receiver implements itself. All 639 numbered checks of Anlage 2 13.1.3 are in core check 13.00.05 (verified 2026-11-01)
- [ ] Error texts and severity from VB Anlage 2 (`sources/vb/`, 13.1.3 and 13.1.4, picked by validity date): a numeric 5th character is a core-check error, "v" a binding check, "e" only recommended (a warning, not "invalid"), "H" a hint, A/D/E/I/K/L a check of one insurer association; checking stops after more than 8 errors
- [ ] Turn the core check's 247 test files (broken records, each with the error number it must produce) into the broken-files corpus
- [ ] Store core-check releases with their dates and the Anlage 1 version they check (13.00.05 for 13.1.3); pick the release by the case's validity date
- [ ] The core check is internal code of AOK Systems: never in Git (`.gitignore`); each machine and the cloud image get it from outside the repo; written permission from ITSG (question 14)

Done when: a corpus of broken files runs in CI and each gets the expected label, and every upload passes through the official core check first.

Needs: G3 (works best after G4–G6).

### G8. Certification flow and automation

Why: the demo story includes a new vendor completing the yearly catalogue and earning the certified label.

- [ ] Vendor lifecycle: new, in certification, certified, under yearly audit
- [ ] Yearly catalogue per vendor; progress per test case and family
- [ ] Certified label when every required case passes; label unlocks the permanent test cases
- [ ] Real rules from the Pflichtenheft (Systemuntersuchung 0113) replace our assumptions: permanent test cases every month through eVpT; ITSG reviews at least once a year, a pass gives a new modification ID, a final fail stops data transmission after 3 months; Pflichtenheft changes must be implemented within 3 months; quality-management errors within 30 working days or the status is lost
- [ ] Certified when every base-module item is met, the test tasks are processed correctly and at least 2 pilot users approve; the label is the GKV certificate "systemuntersucht"
- [ ] Deadlines of single test rounds still from ITSG (question 7), reminders in the vendor view
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

### G9b. Knowledge graph as an asset

Why: today 95% of the graph is text (4,452 chunks, 1,935 passages, 1,025 field definitions); the typed knowledge is 37 rules, 6 parameters, 4 criteria, 1 test case and no decisions. Agents get "the top chunks" instead of a small, complete, correct context. The graph should hold the knowledge the agents need and hand it over per topic and version.

- [ ] Requirement nodes from the Pflichtenheft baseline (G11a import): ID, text, block, message type, sources, checkable yes/no; every rule linked to its item
- [ ] Decided cases (G9) and all test cases as nodes, with a locked flag
- [ ] Conflict nodes: two passages that disagree, with status (open, asked, answered by ITSG); expert interpretation nodes tied to a version; seeded with the 6 known contradictions (`PROJECT_REPORT.md` section 9)
- [ ] "Widersprüche" screen for ITSG staff: both passages side by side, topic, status; a deviation that falls on an open contradiction is labelled "unclear: sources contradict each other" instead of "bug"
- [ ] Link text to structure: each passage to the message types, blocks and fields it mentions; cross-references ("siehe Ziffer ...") as edges; Pflichtenheft sources to passages; passages linked across versions
- [ ] Context pack query: for one topic (e.g. 41 / DBVO.BEGINN-AU) and one validity date, return the requirements, rules, passages, decided cases and open conflicts; the change, reviewer, check and chat agents use it instead of plain top-k search
- [ ] Agent memory: change-agent and reviewer runs stored (what changed, outcomes locked, disagreements, who approved)
- [ ] Retrieval test set (~50 questions, each with the passages it must find), recall reported in CI; fixes the known "Ansprechpartner DBAP" miss
- [ ] Storage split (decided 2026-11-01): passage and chunk text, German full-text search and embeddings (pgvector, reused from `kg/build/embeddings.jsonl`) move to Postgres; the graph keeps only keys, metadata and links. Search narrows the area in the graph, then ranks text in Postgres

Done when: the agents' context comes from context packs, the retrieval test runs in CI, and the graph holds requirements, decisions, tests and conflicts.

Needs: G9; the requirement import of G11a.

### G10. Rules as data

Why: today rules are hand-coded and the AI only adjusts existing parameters (gap 2 in section 5.2). G10 to G12 let the AI turn spec text into executable rules, while still never computing results itself.

- [ ] Own YAML rule types, readable by ITSG experts and stored next to `kg/seed/rules.yaml`, that cover the hand-coded rules: date window, day sum, period chaining, field format, code list, block presence, cross-field consistency
- [ ] The engine interprets these rule definitions; expected results stay deterministic
- [ ] Re-express the existing 37 rules as data; the old Python and the new definitions must give identical results on all test tables

Done when: the hand-coded rules are deleted or reduced to the interpreter, and all tests are unchanged.

Needs: G2.

### G11a. Checklist baseline and change agent

Why: today ITSG's experts update the checklist of requirements (the Pflichtenheft) by hand, version by version (2026.1, 2026.2 ...). The platform should do it: start from the current Pflichtenheft, read a spec change, and hand out the next version in ITSG's own format, with a change list (Alt / Neu / Gelöscht).

- [ ] Import the EEL part of `sources/pflichtenheft/Pflichtenheft_EA_2026.2.pdf` as data: item ID, number, text, sources (Fundstellen), module / topic / block. 112 items in the base module, 44 in the UV/RV module. These become requirement nodes in the knowledge graph
- [ ] Hold out items for grading in G12 (decided 2026-11-01): about 20–25 of the 156 EEL items, picked at random by a script with a fixed seed from the 02, 03 and UV/RV extra-module items (the 41 items stay visible, our rules already use them). The list is stored outside the knowledge base and the agents never see those items. Pick them before any Pflichtenheft text is loaded
- [ ] Mark each item: checkable from the vendor's files (gets a rule) or only visible in the software (checked at the review appointment, no rule)
- [ ] Link every rule to its item ID (`criterion:` on the rule card)
- [ ] **Change agent:** reads a spec change and proposes item changes (new, changed, deleted; changed items keep their ID). It may answer "no item change needed" (example: VB 13.4, where the Pflichtenheft already said "nicht mehr als 6 Monate")
- [ ] **Reviewer agent**, separate from the change agent: reads the same spec change *without* seeing the change agent's draft and writes the expected outcomes in plain language (e.g. "a gap of exactly 6 months now chains"); a different OpenAI model than the change agent
- [ ] Where the two agents agree, the outcomes become the locked tests for the new version; where they disagree, an ITSG expert decides first
- [ ] Hand-off package: proposed Pflichtenheft version (EEL part, ITSG's structure, marked as a platform draft), change list against the previous version, updated rules and test cases, test results, full trace of both agents
- [ ] Expert approves the package; it becomes the new baseline

Done when: uploading VB 13.4 ends with a reviewed package (item changes or "no change needed" with reasons, locked outcomes, trace) that an expert can approve in the UI.

Needs: G0.

### G11b. Rules and tests in the loop

- [ ] For each changed checkable item, the change agent proposes rule definitions in the G10 schema, with citations that must resolve to real passages
- [ ] Code validates each proposal (schema, parameter types, referenced fields exist in the layouts)
- [ ] The engine runs the rules against the locked tests (Peter, Beispielpapier, ITSG solutions, expert decided cases, the outcomes locked in G11a); the agent reads failures and fixes its draft until all pass or its budget per change runs out ("unfinished, here is why")
- [ ] The agent may add test cases and update unlocked ones related to the change; it can never change or delete a locked test
- [ ] It only touches rules linked to the changed items; anything else is flagged in the package
- [ ] Wire the existing criteria pipeline (`/criteria/extract`) into the change agent
- [ ] Switch the agents to the strongest available OpenAI model; re-run the VB 13.4 analysis once so the cache holds the new answers

Done when: a spec change that needs new logic (not just a parameter) ends with approved items, rules that pass every locked test, and new test cases, without a developer.

Needs: G10, G11a, G9b.

### G12. Measure the AI

- [ ] Golden set: spec sections paired with the known correct rule definitions (from G10)
- [ ] Checklist grading on the held-out items: the change agent regenerates them from the spec text; how many of ITSG's items it found, invented and missed, and whether it named the same source
- [ ] Change grading against the Pflichtenheft's own change log (2026.1 to 2026.2: items added, changed, deleted)
- [ ] Agreement rate between change agent and reviewer agent, and how often the expert sided with each
- [ ] Items that do not come from the spec text (meeting decisions, laws, items marked "wird im Rahmen der QK 2026 erneut besprochen") are counted separately, since the agent cannot find them in the VB
- [ ] Evaluation script reports match rate, wrong citations, rejected proposals; run it on every prompt change
- [ ] Report the agreement rate with expert decisions (G9) next to the match rate
- [ ] Prompt versions recorded with cached answers so cache invalidation is deliberate
- [ ] Second real document path: a Rundschreiben or GG update end to end

Quality bar: a derived rule is accepted only if it gives the same results as the known rule on every test table, and an expert approves it.

Done when: the checklist score and the rule match rate are known and shown in the report, and a prompt change cannot silently lower them.

Needs: G11a, G11b.

### G13. Gated code agent

Why: some new rules (e.g. a calculation the rule types cannot express) still need code. An agent may write it, but only behind the same guardrails a human change has.

- [ ] Agent works on its own branch and may only change rule and calculator modules, never the checker, the signing or the tests
- [ ] Its change must pass every existing test, every expert decided case (G9) and the G12 quality bar
- [ ] It opens a pull request with the diff, the spec passages and the test results; a human merges
- [ ] Every change is versioned and can be rolled back

Done when: a spec change that needs new code ends in a pull request that passes CI and a human can merge.

Needs: G11b, G12.

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
- [ ] The core check (Java runtime + jar) in the deployed image, copied from outside the repo
- [ ] Health checks, structured logs, error pages that do not leak internals
- [ ] Database backups and a tested restore
- [ ] Demo reset that works in the cloud, admin only
- [ ] Load check: several vendors uploading at once

Done when: a restore from backup and a full demo run work on the deployed instance.

Needs: G16.

---

## Phase 4: Demo

### G18. Demo for 11 December

- [ ] Two spec stories (decided 2026-11-01): the maternity change (months that cannot be certified: 00000000 in BP 13.2 for 2026, 99999999 in BP 13.3 for 2027, matching the Pflichtenheft) as the real change between versions; the 6-month wording as "the platform found a contradiction in ITSG's documents" (the Pflichtenheft already said "nicht mehr als" while VB 13.3 said "nicht mindestens")
- [ ] A third story from G2b: ITSG's own solution to TA 167 marks periods as optional (justified variants exist even in the official exam) and contradicts itself (two date sets, one EFZ end that conflicts with its own 61); the platform shows each with its source
- [ ] Demo script: vendor run with full EEL coverage, deviations judged, VB 13.4 upload, rules and tests update, signed report, new vendor reaching the certified label
- [ ] Demo data and accounts, seeded by one command
- [ ] AI calls run live during the demo; cached answers take over automatically if the network or OpenAI fails; a local run as last resort
- [ ] Refill the cached AI triage answer of the seed (`s-no-id`, the 41 without DBID): rule titles are part of the triage prompt, so it has missed since G2's German titles (found in the code review of 2026-11-07; one paid call, only with a go)
- [ ] Answers ready for expected questions (data protection, AI errors, cost, how ITSG would run it)
- [ ] Update `README.md` and `PROJECT_REPORT.md` to the delivered state; slides
- [ ] Two full rehearsals on the deployed instance

Done when: two rehearsals in a row run without a fix in between.

Needs: all goals that are part of the script.
