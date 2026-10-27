# EEL Review Assistant: UI

React + TypeScript + Vite. Plan: `UI_PLAN.md`. Mockups: `mockups/`.

## Run it (Windows, VS Code terminal)

The UI needs the backend: Postgres and Neo4j in Docker, the API on port 8000. Vite forwards `/api/*` to it.

```
# once: Docker Desktop running, then from the repo root
docker compose up -d postgres neo4j
NEO4J_PASSWORD=changeme NEO4J_URI=bolt://localhost:7687 uv run python -m kg.build --skip-extract   # load + embed the graph

# terminal 1, repo root: the API on Postgres and Neo4j
DATABASE_URL=postgresql://eel:eel@localhost:5432/eel KG_BACKEND=graph NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=changeme uv run uvicorn api.main:app --port 8000

# terminal 2
cd ui
npm install        # first time only
npm run dev        # opens http://127.0.0.1:5173
```

Stop with `Ctrl + C`. Before a rehearsal, stop the API and run `python -m tools.demo_reset` with the same variables: Postgres goes back to the seed data, advisor precedents are removed from the graph. The LLM cache (`data/llm_cache/`) is kept, so the demo works offline after one run.

Without Docker: leave out `DATABASE_URL` and `KG_BACKEND` (in-memory store and the YAML knowledge base), e.g. `DATABASE_URL= uv run uvicorn api.main:app --port 8000`.

With `OPENAI_API_KEY` in `.env`, the AI proposals, the spec-update agent and the stories are real calls; the first spec diff takes about a minute.

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
| `src/data/` | `api.ts` (backend calls and mapping to the UI types), stores, `runTexts.ts` (hand-written vendor run texts) |
| `src/i18n/` | `de.json`, `en.json`, legal terms (`terms.ts`) and `glossary.md` |
