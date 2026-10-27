# Integration plan: UI on the real backend

Goal: every screen of the portal (ITSG view and vendor view) runs on the FastAPI backend instead of mock data, so the demo storyline of `plan/00` section 6 works end to end. State on 2026-10-27.

## 1. Principles

1. **The vendor view stays.** It replaces the eVpT portal for EEL: story, upload (stand-in for the GKV communication server), receipt, insurer reply download (TEEK0 to import into the payroll software), verdict, signed report. The vendor still works in their own payroll software; the portal only receives files and hands out replies and results.
2. **One adapter, screens unchanged.** The UI keeps its types (`ui/src/data/types.ts`). A new `ui/src/data/api.ts` calls the backend and maps its JSON to those types. `dataSource.ts` picks mock or api by `VITE_DATA_MODE`. Mock mode keeps working for offline demos.
3. **No CORS.** Vite proxies `/api/*` to `http://127.0.0.1:8000/*` in dev.
4. **The backend judges, the UI shows.** Labels, rule outcomes, replies and signatures come from the backend. The in-browser parser stays only for showing the uploaded file field by field.
5. **Texts:** backend explanations are English only. The adapter shows them in both languages; UI chrome stays translated through `de.json` / `en.json`.
6. **Rule ids** are the KG ids (`kg/seed/rules.yaml`: R41-x, F41-x, K61-x, K62-x, E-x, C-x). The mockup ids R01-EFZ, R88-1, R62-1 are dropped (UI_PLAN Q5).

## 2. Steps

Each step ends with a check that is run before the next step starts.

| Step | What | Backend | UI | Done when |
|---|---|---|---|---|
| I1 plumbing | proxy, api client, mode switch, seed with results | seed runs the check for every seed submission and gives them demo vendor names; `GET /overview` (figures for screen 1) | `vite.config.ts` proxy, `npm run dev:api`, `data/api.ts` with `getJson` / `postJson` / `postForm` | `/api/health` answers through Vite; backend tests green |
| I2 ITSG read screens | Overview, Submissions, Submission result | `GET /submissions` returns label, version, received date | adapters: overview, submission list, `/submissions/{id}/diff` + check deviations into `SubmissionResult` (all messages of the chain, one block group per message) | the 10 seed submissions show their labels; `s-missing-july` shows the R41-3 bug with its passage |
| I3 advisor queue | queue and decisions | `GET /advisor/queue` (exists), `POST /deviations/{id}/decide` (exists) | `advisorStore` in api mode: load the queue, decide, show the stored precedent | deciding `s-no-contact` empties the queue and the re-check is resolved by precedent |
| I4 vendor test run | the round-based run on the real checker | `POST /runs/{id}/submit` also stores the files as a submission (receipt, visible in the ITSG view); rejected files do not use up the round; `GET /runs/{id}` | `runStore` in api mode: start a run, upload per round, show the backend receipt and rule outcomes, show and **download the real TEEK0 reply** | Peter: upload ITSG's TEEL0, get the 61 built from it, download it; a broken file fails the named rule |
| I5 signed report | screen 6 + report lists | `GET /reports` (list of signed reports) | Signed report screen (verdict, SHA-256, Ed25519 check via `/reports/verify`, rule table, JSON / HTML download), Reports list for ITSG and vendor | report of `s-missing-july` shows "Not passed", R41-3, signature valid |
| I6 spec changes | screen 2 | `POST /specdiff` (exists) | change list, old / new passage side by side, impact table (rules to recompute, tests whose result flips) | 13.3 vs 13.4 shows the DBVO 3.12 change and `peter-gap-exact` |
| I7 test catalogue | screen 3 | `GET /test-cases`, `GET /test-cases/{id}`, `POST /builder/hidden`, `POST /test-cases/{id}/approve` (exist) | table with status and visibility, detail with chain per rule set, approve and generate hidden variant | approving a draft changes its status in the table |
| I8 docs | how to run both together | | `ui/README.md`, `HANDOUT.md`, UI_PLAN open questions answered | a teammate can start backend + UI with the README only |

## 3. Out of scope for this plan

- Real OpenAI calls (needs a key; without one the advisor queue shows "no AI proposal" and the deterministic result stands).
- Postgres and Neo4j (the backend runs on `MemoryRepo` and `KG_BACKEND=yaml`; a backend restart resets runs and decisions).
- Login. The ITSG / vendor switch in the top bar stays a demo switch.

## 4. How to run (after I1)

```
uv run uvicorn api.main:app --port 8000      # terminal 1, repo root
cd ui && npm run dev:api                      # terminal 2, opens http://127.0.0.1:5173
```
