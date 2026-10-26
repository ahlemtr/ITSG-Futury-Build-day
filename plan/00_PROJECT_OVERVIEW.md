# EEL Review Assistant: Project Overview

Futury Build Days, ITSG challenge: an AI review assistant for the system review (Systemuntersuchung) of German payroll software, scoped to income replacement benefits (Entgeltersatzleistungen, EEL).

## 1. The problem in one paragraph

Payroll software (SAP, DATEV, Lexware...) must be certified by ITSG before it may send data to the social insurers. For EEL, the rules fill hundreds of pages (Verfahrensbeschreibung, Beispielpapier, Rundschreiben) and change every year. Today the official certification exam (Pool-Testaufgaben) contains only **2 fake employees** for EEL (TA 167 and TA 168), written by hand. Vendors run them through **eVpT**, ITSG's test system, which compares their output files against **one fixed solution**. Correct alternatives show up as deviations, and every deviation has to be sorted out by a human system advisor.

## 2. How the ecosystem works today

| Step | Who | What happens |
|---|---|---|
| 1 | Umbrella organizations + ITSG | write test tasks (fake employee, month by month), solutions and insurer reply files (TEEK0) |
| 2 | Vendor | enters each month into their payroll software, which produces output files (TEEL0) on its own |
| 3 | eVpT | receives the files at test address 99300001 (via the GKV communication server), confirms receipt, runs the core check (format, plausibility), and for selected tasks a preliminary evaluation ("fachliche Vorbewertung") against the model solution |
| 4 | eVpT | provides the insurer replies the following month, the vendor imports them and continues |
| 5 | ITSG system advisor | discusses every deviation with the vendor, decides bug or allowed alternative |
| 6 | Vendor | after certification, keeps processing the permanent test cases (the same test employees) from the month after approval, for ongoing quality control (PTA 8.4) |

Key facts we confirmed:
- ITSG does not talk to vendor software live. Vendors run everything locally and submit output files as proof.
- eVpT plays the insurer with reply files prepared in advance by ITSG, available for the next month of the test story (PTA 2.3, 8.3).
- Open: how often certified vendors actually upload their permanent test cases (monthly or only for the yearly audit). Our platform works either way.
- Test cases, solutions and replies are very likely created manually (test tasks by the umbrella organizations, insurer replies by ITSG per decisions of the KoSKP committee).
- The eVpT portal is where vendors see results and download replies. Its own description calls the comparison a "fachliche Vorbewertung", a preliminary evaluation. Final judgement is manual.
- Details and sources: `05_CHECKING_AND_DEVIATIONS.md`, section 1.

## 3. What we build: one platform that replaces eVpT for EEL

A complete test platform for EEL. It takes over everything eVpT does for this area and adds what eVpT cannot do: keep the tests up to date and actually judge the results.

| Part | Does | Replaces today |
|---|---|---|
| **Test catalogue** | test employees (stories), expected results per rule version, hidden variants | Pool-Testaufgaben and solution sheets, maintained by hand |
| **Test builder** | turns rules and spec changes into new or updated test cases: story, expected TEEL0 files, TEEK0 replies, hidden variants. Human approves before use | writing tests and solutions by hand |
| **Intake** | receives the vendor's TEEL0 files, stores them with a hash, returns a receipt, runs the format check | eVpT receipt and core check |
| **Checker** | exact match against the expected files first, then labels every deviation: correct variant, bug, invalid, unclear (AI proposal, advisor decides) | eVpT preliminary evaluation and most of the advisor's manual sorting |
| **Insurer simulator** | builds the insurer replies (61, 62) from the vendor's own files, so the story can continue | eVpT's prepared reply files |
| **Portal** | vendor view: story, upload, replies, verdict, signed report. ITSG view: catalogue, spec diff, approvals, advisor queue | eVpT portal and deviation meetings |

Shared foundation: **knowledge graph** (rules, field layouts, spec passages, versions) and **record layouts** (YAML, already extracted for all blocks).

**Assumed, not built:** the transmission network (GKV communication server, encryption), test company numbers and vendor accounts. In the prototype the vendor uploads files in the browser; in production the same files arrive over the existing network.

Pitch lines: "One platform for EEL testing: it receives the files, answers like the insurer, judges every difference and keeps the tests up to date." and "Today's comparison is a preliminary evaluation. Ours is a real one."

Vision: the engine is procedure-agnostic (layouts and rules are data), so other procedures (DEÜV, contributions, ...) can move over one by one until eVpT can be switched off. How to say it to ITSG, who built eVpT: "everything eVpT does for EEL, plus judgement and tests that stay up to date", not "your system is old".

## 4. Prototype scope

### In scope
- Parser and writer for DTA EEL fixed-width records (DSLW + data blocks), driven by the YAML layouts
- Intake: upload, receipt, stored hash, format check (replaces eVpT's receipt and core check for EEL)
- Insurer simulator: 61 and 62 replies built from the vendor's own files
- Rules engine for **prior illnesses** (Abgabegrund 41/61) and the employer-paid sick period (EFZ end date)
- Chain checks for the full Vorerkrankung scenario: 41, 61, 01, 61, 88, 01, 62
- Rule checker: exact match first, then deviation analysis (catalogue, rule re-check, AI triage, advisor) with labels correct variant / bug / invalid / unclear, and a precedent store
- Spec diff between the real versions V13.3 and V13.4 of the Verfahrensbeschreibung, mapped to affected rules and test cases
- Test builder: clones of a reference person around rule boundaries, including the 6-month boundary that flips between 13.3 and 13.4 (optional second example: simulated 30 to 28 days)
- Explained report (JSON + HTML), signed with SHA-256 + Ed25519
- Hidden variants and the round-based test run (story, files, replies built from the vendor's files, verdict only)
- Rule set chosen by the date of the case (checks now under today's rules, next year's answers prepared in parallel)
- Minimal web portal: vendor view (story, upload, receipt, replies, verdict, signed report) and ITSG view (catalogue, spec diff, approval, advisor queue, side-by-side diff with labels)
- Knowledge graph behind a fixed interface (teammate), with a YAML fallback

### Out of scope (future)
- Vendor pre-check (same engine, packaged for vendors; the ITSG-side check stays necessary for hidden variants and the official verdict)
- Transmission network, encryption, test company numbers (assumed to exist)
- Maternity (03), child sick benefit (02), rehab and accident benefits
- Procedures other than EEL (DEÜV, contributions, ...): they stay on eVpT for now
- Full rule extraction from all documents by LLM (we show it on one section)

## 5. Source documents and what each one is for

| Document | Role in the build |
|---|---|
| Verfahrensbeschreibung DTA EEL V13.4 | field layouts (done) and procedural rules, section 3.12 for DBVO |
| Verfahrensbeschreibung DTA EEL V13.3 | previous version, source of the real spec diff |
| Gemeinsame Grundsätze EEL V13.1 | message types and cancellation rules |
| Beispielpapier V13.3 | gold examples to test the rules engine (sections 13, 16, 23) |
| DTA-EEL-Beispiel_Vorerkrankung.docx | ITSG's 4 criteria with UUIDs, our criteria format |
| Hinweise_Testkonstellation.docx | Peter Mustermann scenario and expected message chain |
| TEEL0-Test1-DBVO | real reference output file, parser fixture |
| Pool-Testaufgaben 2025/2026 | today's process (eVpT), TA 167 and 168 as baseline |
| Rundschreiben Anl. 1 to 3 | legal background, retrieval only |
| Futury deck | ITSG's objectives, our grading criteria |
| Translation Assistance (26.10.2026) | glossary German to English for the pitch |
| workflow.png | ITSG's picture of today's workflow |
| **missing:** Anlage 3 of the Verfahrensbeschreibung | which data blocks are mandatory or optional per Abgabegrund (VB 2.2.3.2 points to it). Decides whether DBAP or DBAN may be missing on a 41 |

## 6. Demo storyline

1. **Today:** 2 fake employees for EEL, eVpT diffs against one solution, humans sort the deviations.
2. **Upload** ITSG's TEEL0 reference file in the vendor view. The platform returns a receipt and shows every field by name.
3. **Run** Peter's case as the vendor: upload the 41, receive the insurer's 61 built from it, continue to the end. All green, every verdict linked to its spec passage.
4. **Break** a file (drop the July period, swap the order, wrong pay end date). The checker says exactly which rule failed and why.
5. **Deviation analysis:** a plain diff like today's shows the deviations of several submissions. Our checker labels them: a correct variant (3 of 4 periods), bugs, an invalid file, and one unclear case where the AI proposes a verdict with the spec passage. The advisor confirms, and the decision becomes a precedent that resolves the same case automatically next time.
6. **Real law change:** diff V13.3 against V13.4. Section 3.12 changed "not at least 6 months" to "not more than 6 months". The builder shows the affected rules, generates `peter-gap-exact` (gap of exactly 6 months), and a legacy vendor that still follows 13.3 fails exactly that case. Bonus finding for ITSG: the same section still uses the old wording in the insurer paragraph and in 3.12.7, so 13.4 is internally inconsistent. Our diff surfaces it, a human would likely miss it.
7. **Hidden variant:** the same rule with other dates (31.08 to 28.02, exactly 6 months). A vendor tuned to Peter's dates fails it.
8. **Approve** the new tests, show the signed report.

## 7. Team split

| Person | Owns |
|---|---|
| Teammate A | knowledge graph behind the interface in `02_BACKEND_IMPLEMENTATION_PLAN.md` section 5 |
| Ghassen | parser, rules engine, rule checker |
| Teammate B | test builder, fixtures generation, LLM services |
| Teammate C | API wiring, frontend, report rendering, pitch deck |

Milestones per owner (`02_BACKEND_IMPLEMENTATION_PLAN.md` section 4): Ghassen M1 to M4, M8.5, M8.6. Teammate B M5, M8.0 to M8.4, M8.7, M8.8. Teammate C M6, M7, frontend. Teammate A M9 and `08_KG_SEEDING_GUIDE.md` K0 to K11. M0 together on day 1.

## 8. Files in this plan

| File | Content |
|---|---|
| `00_PROJECT_OVERVIEW.md` | this file |
| `01_DIAGRAMS.md` | index of all diagrams |
| `diagrams/*.md` | Mermaid diagrams |
| `02_BACKEND_IMPLEMENTATION_PLAN.md` | modules, tasks, tests, API, data model, order of work |
| `03_DOMAIN_RULES_VORERKRANKUNG.md` | the rules we implement, formalized, with test cases |
| `04_SPEC_DIFF_13.3_TO_13.4.md` | the real changes between both versions and what they affect |
| `05_CHECKING_AND_DEVIATIONS.md` | eVpT's checking stages, our exact-match-first flow, compare modes and ignore list, labels, AI triage, precedents |
| `06_LIFECYCLE_AND_HIDDEN_TESTS.md` | spec versions and validity, the four events, one catalogue with today's and next year's answers, hidden variants, test rounds |
| `07_KNOWLEDGE_GRAPH.md` | why the knowledge graph exists, schema, impact tiers, queries |
| `08_KG_SEEDING_GUIDE.md` | step-by-step build guide for the knowledge graph: terminology, key formats, seed files, extraction, validation, load, tests |
| `09_TECH_STACK.md` | every library and service we use, the OpenAI agents and their tools, environment variables |
| `starter/layouts/` | done: YAML layouts for all blocks + a validated parser sketch |
| `starter/tools/specdiff.py`, `starter/data/` | done: the diff script and its output for 13.3 vs 13.4 |

## 9. Open questions for ITSG

1. Can we get the solutions and TEEK0 reply files for TA 167 and 168, and a sample eVpT deviation report?
2. Are the test tasks available as the original Excel files?
3. The 13.4 wording makes a gap of exactly 6 months chain. Is "6 months" counted from the end date or from the day after?
4. Can payroll software clone an employee to start a test branch?
5. What share of eVpT deviations turn out to be allowed alternatives?
6. Which fields does eVpT's Vorbewertung ignore? (our list: `05_CHECKING_AND_DEVIATIONS.md`, section 4)
7. Can we see the eVpT user manual (Benutzerhandbuch) chapter on the Vorbewertung and one real deviation report?
8. Record descriptions for DBNA, DBAN, DBAP (Anlage 1 of the GG, field check catalogue).
9. Which 6-month wording is authoritative for 2027? VB 13.4 changed only the employer sentence in 3.12 ("nicht mehr als"). The insurer paragraph of 3.12 still says "nicht mindestens 6 Monate", the field description 3.12.7 says "mehr als 6 Monate Arbeitsfähigkeit", and the criteria doc mixes both (`07_KNOWLEDGE_GRAPH.md` section 12).
10. Month ends: is 31.08 + 6 months = 28.02 (calendar months, § 188 BGB style)? Our hidden variant depends on it.
11. Anlage 3 of the Verfahrensbeschreibung (Abgabegrund / data block combinations): is DBAP mandatory on a 41? Beispielpapier 13.1 sets MM-ANSCHRIFT = J (DBAN), the ITSG reference file sends N. Which is expected?
12. Kurz-AU: an uncertified absence directly followed by a certified AU (VB 3.12) is listed how: merged into one period, or as the certified part only?

## 10. Glossary

| Term | Meaning |
|---|---|
| EEL | Entgeltersatzleistungen, income replacement benefits |
| EFZ | Entgeltfortzahlung, employer-paid sick period (6 weeks per illness) |
| AU | Arbeitsunfähigkeit, incapacity for work |
| Abgabegrund | message type code (01, 41, 61, 88...) |
| DSLW | the EEL record, carries the data blocks |
| DBxx | data block inside a DSLW (DBVO = prior illnesses) |
| TEEL0 / TEEK0 | EEL file from employer / from insurer, eVpT naming |
| eVpT | ITSG's electronic test system for permanent test cases; our platform replaces it for EEL |
| Permanent test cases | the test employees of the catalogue that a certified program keeps processing for ongoing quality control (PTA 8.4) |
| TA | Testaufgabe, one fake employee in the official exam |
| Systemberater | ITSG system advisor who reviews deviations |
| Agent | an OpenAI model that calls our tools (knowledge graph queries, engine functions) and returns a draft (`09_TECH_STACK.md` section 3) |
| Passage | one piece of spec text with a key like `VB@13.4#3.12/chaining` (`08_KG_SEEDING_GUIDE.md` section 1.3) |
| Kernprüfung | core check: format and plausibility, same as the real data acceptance points |
| Vorbewertung | eVpT's preliminary evaluation: comparison with the model solution |
| Musterlösung | model solution of a test task |
| Gültigkeitszeitraum | validity period of a spec version (from 1 January) |
| Hidden variant | same rule, different data, expected results never shown to the vendor |
| Kurz-AU | short absence without a sick note (allowed by EntgFG), never listed as a prior illness unless a certified AU follows seamlessly |
| Precedent | an advisor's decision on a deviation, reused automatically next time |
