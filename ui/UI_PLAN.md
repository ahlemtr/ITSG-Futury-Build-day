# UI plan (draft, waiting for OK)

Owner: Slim. Status: **draft**. No code until this plan is approved.

Source of truth: the Miro mockups in `ui/mockups/`. This plan follows them screen by screen.

| File | Screen |
|---|---|
| `00_screen_map.png` | how the screens connect |
| `00_look_and_feel.png` | colors, labels, type, layout rules |
| `01_overview.png` | 1 Overview |
| `02_spec_changes.png` | 2 Spec changes |
| `03_test_catalogue.png` | 3 Test catalogue |
| `04_submission_result.png` | 4 Submission result |
| `05_advisor_queue.png` | 5 Advisor queue |
| `06_signed_report.png` | 6 Signed report |

## 1. What we build

**Changed (plan update by Ghassen, "change of plans"):** the platform now replaces eVpT for EEL. The portal has two views:

- **ITSG view:** the 6 mockup screens below
- **Vendor view:** story, upload, receipt, insurer replies, result, signed report. No mockups yet, see section 4b (draft)

The local vendor pre-check stays future work.

```
1 Overview ──open submission──> 4 Submission result ──unclear──> 5 Advisor queue
                                        │                              │ precedent
                                        └──────verdict──────> 6 Signed report
2 Spec changes ──draft tests──> 3 Test catalogue
```

## 2. Design rules (from `00_look_and_feel.png`)

Taken from ITSG's own deck. All values are defined once as named tokens, so they can be changed in one place.

### Colors

| Token | Hex | Used for |
|---|---|---|
| `--itsg-red` | `#D50032` | wordmark, the one primary button per screen. **Never for status** |
| `--red-dark` | `#A8002A` | active nav text |
| `--red-faint` | `#FBEAEE` | selected row, active nav background |
| `--ground` | `#EEF2F6` | app background |
| `--surface` | `#FFFFFF` | panels, top bar |
| `--ink` | `#1C2430` | text, headings |

### Result labels: always text plus color

**Changed (team feedback, coloured backgrounds looked unprofessional):** labels are neutral (ink text, grey border, white background). Only a small dot in front of the text carries a colour, and only two colours are used: **green** for Exact match (also Identical, Valid, Passed, Approved) and **red** for Bug (also Failed, Not passed). All other labels get a grey dot.

| Label | Also used for | Background / text (read from the image, fine-tune when building) |
|---|---|---|
| Exact match | Identical, Passed, Approved, Valid | `#E6F4EA` / `#1E7B45` |
| Correct variant | | `#E8F0FB` / `#1F5FAD` |
| Bug | Failed, Not passed | `#FDEBE9` / `#B42318` (a status red, not the brand red) |
| Invalid | | `#F0E9F9` / `#6B2FA3` |
| Unclear | Needs approval | `#FDF1E1` / `#9A5B00` |
| Ignored / neutral | Not run, Public, Rule field | `#EEF0F3` / `#4B5563` |

### Type

- headings: **Fira Sans Condensed 700**
- UI text: Fira Sans 400 / 500, 14 px base
- tabular figures (`font-variant-numeric: tabular-nums`) in tables and dates

### Layout rules

- flat panels: 1 px quiet border, 6 px radius
- square-ish buttons, 4 px radius
- no gradients, no shadows at rest, no icon tiles
- one primary red button per screen
- dense tables, generous outer margins
- labels never rely on color alone

## 3. App shell (on every screen)

- **Top bar:** ITSG wordmark, "EEL Review Assistant", a context line on the right (e.g. "Rule set in force V13.3 · next V13.4 from 01.01.2027", or the submission / report number), user avatar (IT = ITSG tester, SA = system advisor)
- **Left nav:** section label "Systemuntersuchung EEL", then Overview, Spec changes, Test catalogue, Submissions, Advisor queue, Reports. Open items have a count badge (Spec changes 1, Advisor queue 3). The active item is tinted

## 4. Screens

### 1 Overview: first screen of the day (built)
| Widget | Content |
|---|---|
| Header | "Overview", subtitle: one catalogue, two rule sets in parallel. No upload button: uploading happens in the vendor view |
| "Checks now" card | V13.3 valid until 31.12.2026: submissions this month, passed all rules, with open deviations (was "Track 1 · Monthly checks") |
| "Preparing next year" card | V13.4 valid from 01.01.2027: spec changes in scope, test cases to re-approve, hidden variants ready (was "Track 2 · Catalogue 2027") |
| Resolution bar | stacked bar + legend: catalogue and rules / AI proposal + advisor / waiting for advisor (the pitch metric) |
| Latest submissions | vendor, test case, rule set, result badge, received date. Clicking a row opens screen 4 |

### 2 Spec changes: a new Verfahrensbeschreibung is published
| Widget | Content |
|---|---|
| Header | "Verfahrensbeschreibung V13.3 → V13.4", "36 changes found, 5 inside the EEL prototype scope. Field layouts unchanged.", buttons **Show all 36** and primary **Draft affected tests** |
| Change list | the 5 in-scope changes (DBVO 3.12, DSLW BBNR-VU 3.1.10, DBID 3.19, DBSD 3.20, DBEE 3.7.3). "Rule change" badge on the ones that move a rule |
| Side-by-side passage | old text (V13.3) and new text (V13.4), changed words marked red (removed) and green (added) |
| Impact table | rules from this passage (R41-2, R41-3), changed parameter (gap_inclusive false → true), test cases on these rules, test whose result flips (peter-gap-exact: no 41 → 41 required, Needs approval) |

### 3 Test catalogue: test builder output, human approval
| Widget | Content |
|---|---|
| Header | "Test catalogue 2027", buttons **Generate hidden variants** and primary **Approve N test(s)** |
| Catalogue table | test case + short description, rules, visibility (Public / Hidden), status (Approved / Needs approval). Selected row tinted |
| Detail: scenario facts | 3 tiles, e.g. prior illness ends 11.09.2025, new AU starts 11.03.2026, gap 6 months |
| Detail: round table | per round: what we send, what the software must produce (4 rounds for Peter) |
| Footnote | "Expected files computed by the rules engine. Source: VB V13.4, 3.12." |

### 4 Submission result: rule checker output for one test case
| Widget | Content |
|---|---|
| Result header | test case · vendor, round, receive date, rule set. Verdict badge (worst label) + primary **Open report** |
| Filter chips | counts: all fields, identical, correct variant, ignored, rule field... + toggle "Show only deviations" |
| Field diff table | block, field, model solution, vendor file, mode (compare / ignore / rule), label. Identical rows grey. Clicking a row fills the panel |
| Explanation panel | "Why this label": title, decided by (catalogue / rules / AI / advisor), rule, spec passage, ITSG criterion |

### 5 Advisor queue: only unclear deviations reach a human
| Widget | Content |
|---|---|
| Queue list | open deviations: title, vendor · test case, Unclear badge. Selected item tinted |
| Expected vs actual | two tiles: model solution, vendor file |
| AI proposal card | proposal, confidence, reasoning, cited spec passage, similar precedents. A proposal without a citation is not shown |
| Decision bar | primary **Confirm as ...**, Mark as bug, Mark invalid. A reason is required and is saved as a precedent (e.g. P-014) |

### 6 Signed report: what ITSG and the vendor receive
| Widget | Content |
|---|---|
| Header | "Test report · vendor", catalogue, rule set, number of public and hidden tests. **Download JSON**, primary **Download PDF** |
| Verdict card | Passed / Not passed, large type, one-line reason |
| Signature card | SHA-256 hash, Ed25519 signature status (Valid) |
| Rule table | rule, what it checks, public test result, hidden variant result (pass/fail only, never expected values), spec passage |

## 4b. Vendor view (built, decisions taken by Claude on Slim's request)

Decisions: switch in the top bar; vendor sees the field-by-field result for public tests, never for hidden ones; built from this text without Miro mockups. Upload really reads the file in the browser (layouts from `plan/starter/layouts`, SHA-256, DATENSATZ-ID, format issues). The verdict per round is a stand-in until the backend checker exists: it only checks that the expected messages arrived.

Why: demo steps 2 and 3 (`plan/00_PROJECT_OVERVIEW.md` section 6) and the done-criterion "a vendor uploads a file, gets a receipt, receives the next insurer reply and downloads the signed report" (`plan/02` section 8).

Same look as the ITSG view (section 2). No mockups exist; this section replaces them until the team draws them.

### Switching views
- A **"ITSG | Hersteller"** switch in the top bar (demo only, no login). The avatar changes to IT or HS.
- Vendor pages live under `/vendor/...`, so both views can be open in two tabs during the demo.
- The vendor sees only its own data, and never expected values of hidden tests.

### Vendor nav
| Item | Content |
|---|---|
| Meine Testfälle | the catalogue as the vendor sees it: test case, story title, rule set, status (not started / round 2 of 4 / done) |
| Testlauf | the run of one test case, round by round (main page, below) |
| Ergebnisse | results per submission: screen 4 for public tests, pass/fail per rule only for hidden tests |
| Berichte | signed reports (screen 6) |

### Main page: test run (`/vendor/runs/:id`)
```
┌ Story (Aufgabe) ───────────────┐ ┌ Round 1 · 2 · 3 · 4 (stepper) ─────────────────┐
│ Peter Mustermann, 4 prior      │ │ What to enter now: "AU from 11.03.2026 ..."    │
│ periods, sick from 11.03.2026, │ │ [ Drop TEEL0 file(s) here ]  <- primary button │
│ job ends 31.03.2026            │ │ Receipt: accepted / rejected, issues, SHA-256  │
└────────────────────────────────┘ │ Parsed record: fields by name per block (open) │
                                   │ Result of this round: label + "details"        │
                                   │ Insurer reply: TEEK0 (61) ready -> download    │
                                   └────────────────────────────────────────────────┘
```
States of a round: **waiting for upload → checking → receipt → result → reply ready → next round unlocked**. Round 3 accepts two files (88 + new 01). Round 4 has no upload ("import only"). If a required message is missing, the run ends with the failed rule.

**Receipt** (replaces eVpT's processing confirmation): accepted or rejected, list of format issues (record, field, position, message), SHA-256 of each file, received at, DATENSATZ-IDs found.

**Parsed record** (demo step 2): every field of the uploaded file by name, grouped by block (DSLW, DBNA, DBVO, DBAP, DBID), DBVO periods as rows.

### Data
| Mode | Behaviour |
|---|---|
| mock | the upload is accepted and returns a prepared receipt, parsed record and reply for the demo files (no parsing in the browser) |
| api | `POST /runs`, `POST /runs/{id}/submit`, `GET /runs/{id}/verdict`, `POST /submissions` (receipt), `GET /test-cases/{id}/package` |

The ITSG reference file stays in `sources/` (never committed). It is uploaded live during the demo.

### Open questions for the vendor view
1. Switch in the top bar, or two separate start pages?
2. Does the vendor see the field-by-field diff (screen 4) for public tests, or only the label per rule? The plan says public tests come with expected results, so I propose: yes for public, never for hidden.
3. Should the team draw this in Miro first, or is this text enough to start?

## 5. Stack (decided: React)

| Part | Choice | Why |
|---|---|---|
| Framework | React 18 + TypeScript | matches the custom mockups 1:1 |
| Build tool | Vite | fast local start: `npm install`, then `npm run dev` |
| Pages / links | React Router | one URL per screen, e.g. `/submissions/:id` |
| Texts in two languages | react-i18next | see section 6 |
| Styling | plain CSS with the tokens from section 2, no UI kit | a UI kit would bring its own shadows and colors |
| Fonts | `@fontsource/fira-sans`, `@fontsource/fira-sans-condensed` | fonts are bundled, so the demo works offline |

Node 24 and npm 11 are already installed on Slim's machine.

### Folder layout

```
ui/
├── UI_PLAN.md
├── mockups/              Miro exports
├── package.json
├── index.html
└── src/
    ├── main.tsx          start
    ├── App.tsx           app shell + routes
    ├── styles/tokens.css colors, fonts, sizes (section 2)
    ├── components/       Badge, Card, Table, Chip, NavItem ...
    ├── screens/          Overview, SpecChanges, TestCatalogue, SubmissionResult, AdvisorQueue, SignedReport
    ├── data/             data_source.ts (mock or api) + mock/*.json
    └── i18n/             de.json, en.json, glossary.md
```

## 6. Language: German first, English on a button

German is the default, because the domain words are German. A **DE | EN** switch in the top bar changes the UI to English. The choice is remembered in the browser.

**Rules so the translation never changes the meaning of the law:**

| What | In English mode |
|---|---|
| Buttons, headings, table headers, hints | translated |
| Legal and procedure terms (Abgabegrund, Vorerkrankung, Entgeltfortzahlung, Arbeitsunfähigkeit, Verfahrensbeschreibung, Systemberater ...) | **kept in German**, with the English meaning as a tooltip, e.g. "Vorerkrankung (prior illness)" |
| Field and block names (DSLW, DBVO, ABGABEGRUND, AU-AB-AG ...) | **never translated**, they are names from the spec |
| Spec passages (quotes from the Verfahrensbeschreibung, GG, Beispielpapier) | **always the original German text.** An English help text may be shown below it, clearly marked "Unofficial translation, the German text is binding" |
| Rule IDs, codes, dates, numbers | unchanged. Dates stay `DD.MM.YYYY` in both languages |

- All terms and their fixed English meaning live in one list, `src/i18n/glossary.md`, built from the glossary in `plan/00_PROJECT_OVERVIEW.md`. Every English text uses these words, never a free translation.
- No text is written directly into a screen. Everything goes through `de.json` / `en.json`, so nothing stays half-translated.
- Check: a small script lists keys that are missing in one of the two files.
- The team (ideally someone who knows the procedure) reviews `en.json` once before the demo.

## 7. Where the data comes from

The backend is not built yet (Ghassen: checking, Ahlem: knowledge graph, Mohamed: infrastructure). The UI reads everything through one module, `data_source`:

| Mode | What it does |
|---|---|
| `mock` | hand-made demo data (JSON) matching the mockups: the demo vendors, peter + clones, the 5 spec changes, 3 advisor items, one report |
| `api` | calls the backend API (`plan/02_BACKEND_IMPLEMENTATION_PLAN.md` section 6) once it exists |

Switching is one setting. Mock data is made up from the plan documents, never copied from ITSG files.

Screen → API endpoint (for later):

| Screen | Endpoints |
|---|---|
| 1 Overview | `GET /test-cases`, submissions list (new endpoint needed), counts (new) |
| 2 Spec changes | `POST /specdiff`, `GET /passages/...` |
| 3 Test catalogue | `GET /test-cases`, `POST /builder/...`, `POST /test-cases/{id}/approve` |
| 4 Submission result | `GET /submissions/{id}/diff` |
| 5 Advisor queue | `GET /advisor/queue`, `POST /deviations/{id}/decide` |
| 6 Signed report | `GET /submissions/{id}/report` |

## 8. Order of work

| Step | Done when |
|---|---|
| 1. Setup | `npm run dev` in `ui/` opens an empty page in the browser |
| 2. App shell + design tokens + language | top bar with DE / EN switch, left nav with badges, colors and fonts as in the mockups |
| 3. Mock data | JSON for all 6 screens |
| 4. Screen 4 Submission result | the core of the demo: diff table, chips, explanation panel (**done**) |
| 5. Screen 1 Overview | cards, resolution bar, table opens screen 4 (**done**) |
| 5b. Vendor view (section 4b) | switch, my test cases, test run with upload, receipt, parsed record, reply (**done**, reply download waits for the backend) |
| 6. Screen 5 Advisor queue | decide button stores a precedent (in mock mode: in memory) |
| 7. Screen 6 Signed report | verdict, signature, rule table, JSON download |
| 8. Screen 2 Spec changes | change list, highlighted passages, impact table |
| 9. Screen 3 Test catalogue | table, facts, rounds, approve |
| 10. Switch to the API | same screens, real data |

Slim tests each step locally before anything is pushed.

## 9. Open questions

1. ~~Stack~~: React + Vite.
2. ~~Upload flow~~: later, by Slim. Button removed for now.
3. **Submissions and Reports nav items:** there is no list screen for them. Proposal: two simple list pages that reuse the Overview table.
4. **Red for status (mostly settled):** bad states use the Bug label tone `#B42318`, not the brand red. Remaining: the Overview mockup shows "3 with open deviations" and the "waiting" bar in brand red. Plan: use the Bug tone there too. OK?
5. **Rule IDs on screen 6:** R01-EFZ, R88-1, R62-1 don't exist in the rules doc. Use its IDs (E-1, C-3, C-6), or rename them in the rules doc?
6. **AI proposal for "DBAP missing":** screen 5 says "likely correct variant", the backend plan (M8.5) expects "likely bug". Which one is the demo?
7. ~~Language~~: German default, English on a button (section 6).
