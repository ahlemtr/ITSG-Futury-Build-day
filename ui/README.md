# EEL Review Assistant: UI

React + TypeScript + Vite. Plan: `UI_PLAN.md`. Mockups: `mockups/`.

## Run it (Windows, VS Code terminal)

```
cd ui
npm install        # first time only
npm run dev        # opens http://127.0.0.1:5173
```

Stop with `Ctrl + C`.

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
| `src/data/` | `dataSource.ts` (mock or api) and the mock JSON |
| `src/i18n/` | `de.json`, `en.json`, legal terms (`terms.ts`) and `glossary.md` |
