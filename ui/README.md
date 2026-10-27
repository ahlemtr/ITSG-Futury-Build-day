# EEL Review Assistant: UI

React + TypeScript + Vite. Plan: `UI_PLAN.md`. Mockups: `mockups/`.

## Run it (Windows, VS Code terminal)

```
cd ui
npm install        # first time only
npm run dev        # opens http://127.0.0.1:5173
```

Stop with `Ctrl + C`.

## Run it on the real backend (api mode)

Two terminals. The backend keeps its data in memory, so a restart resets runs and decisions.

```
# terminal 1, repo root (DATABASE_URL empty = in-memory store, no Postgres needed)
DATABASE_URL= uv run uvicorn api.main:app --port 8000

# terminal 2
cd ui
npm run dev:api    # same UI, data from the backend through the Vite proxy /api -> 127.0.0.1:8000
```

PowerShell: `$env:DATABASE_URL=""; uv run uvicorn api.main:app --port 8000`.

- `npm run dev` (mock mode) still works without a backend, with the hand-made demo data.
- With `OPENAI_API_KEY` in `.env`, the AI proposals, the spec-update agent and the stories are real calls, cached in `data/llm_cache/`; the first spec diff takes about a minute.
- Advisor decisions are stored in `data/precedents.yaml`. Delete `data/submissions/` and `data/precedents.yaml` to reset the demo; keep `data/llm_cache/` for the offline demo.
- Screens 2 (spec changes), 3 (test catalogue) and 6 (reports) exist in api mode only.

## Other commands

| Command | What it does |
|---|---|
| `npm run build` | type check + production build into `dist/` |
| `npm run check:i18n` | lists texts missing in `de.json` or `en.json` |
| `npm run build:layouts` | converts `plan/starter/layouts/*.yaml` into `src/records/layouts.generated.json` (run again when the layouts change) |

## Where things are

| Folder | Content |
|---|---|
| `src/styles/tokens.css` | all colors, fonts, sizes (from `mockups/00_look_and_feel.png`) |
| `src/components/` | top bar, left nav, shared pieces |
| `src/screens/` | one file per screen |
| `src/data/` | `dataSource.ts` (mock or api), `api.ts` (backend calls and mapping to the UI types), stores, mock data |
| `src/i18n/` | `de.json`, `en.json`, legal terms (`terms.ts`) and `glossary.md` |
