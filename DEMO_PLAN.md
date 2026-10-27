# Demo plan: a new Verfahrensbeschreibung arrives

Goal: the demo starts with a platform that knows only **V13.3**. On stage, ITSG uploads the **V13.4** PDF. The platform chunks it into passages, embeds them, diffs them against V13.3, maps the changes to the rules, lets the AI work out what changed in the rules (e.g. `gap_inclusive` false → true), stores everything in the knowledge graph (Neo4j) and Postgres, and recomputes the test cases. The screen shows a progress animation while this runs, then the diff and its impact. State on 2026-10-27.

## 1. Principles

1. **The pipeline is real.** Every stage runs on the uploaded file: extraction (`kg/extract/pdf_text.py`), embeddings (`kg/embed.py`, OpenAI), diff (`engine/specdiff.py`), rule mapping (rule sources by section), AI analysis (spec-update agent), recompute (`engine/builder.py`). Nothing is replayed from the seed.
2. **The hand-curated 13.4 knowledge stays as the reference.** `kg/seed/changes.yaml` and the 13.4 parameter values are no longer loaded at the start of the demo; a test compares the pipeline's result with them (e.g. it must find `gap_inclusive` false → true on 3.12).
3. **No approval step on the analysis.** The AI result describes next year's rule set (13.4, valid from 01.01.2027), not the one in force. The human gate stays where it is: new and changed tests are drafts in the Test catalogue until ITSG approves them.
4. **Real storage.** Docker Compose runs Postgres and Neo4j. Uploaded files, the ingestion job and its stages, passages and changes go to Postgres; versions, passages (with embeddings), changes and their links to rules go to Neo4j.
5. **Resettable.** One command puts the platform back to "13.3 only" before each rehearsal.

## 2. Steps

| Step | What | Done when |
|---|---|---|
| D0 field table | Submission result: one tab per message (41, 01, 88, 01), only deviations by default, identical empty fields hidden | `s-missing-july` opens on the 41 with its 1 deviation; the 99 fields of the 41 are one click away |
| D1 start state | The KG can start without a version (`KG_HIDE_VERSIONS=VB@13.4`): no 13.4 document, passages, parameter values, changes, rule sources or expected results. Everything is checked under 13.3 | the Overview shows only V13.3; `s-legacy-1` is an exact match; `/specdiff` says there is no newer version |
| D2 ingestion pipeline | `POST /spec-versions` (PDF, document, version, valid from) starts a job; stages: stored → chunked → embedded → diffed → mapped → AI analysis → recomputed. `GET /spec-versions/jobs/{id}` reports progress. The result is added to the running KB | uploading the 13.4 PDF yields the DBVO 3.12 change with `gap_inclusive` false → true, R41-2 / R41-3 to recompute, and `peter-gap-exact` flips |
| D3 Docker | `docker compose up postgres neo4j`, schema applied, 13.3 graph loaded, `PgRepo` fixed until the API runs on Postgres, the pipeline writes to both stores | after an upload, the 13.4 nodes are in Neo4j and the job, file and passages are in Postgres |
| D4 upload screen | Spec changes: empty state "V13.3 in force, no newer version" with an upload card; while the job runs, an animated stage list (chunking, embedding, diffing, AI analysis …); then the existing diff view | the whole flow runs in the browser |
| D5 rehearsal | `python -m tools.demo_reset`; demo script in `DEMO.md` (storyline of `plan/00` section 6 adapted) | two clean runs in a row |

## 3. Open points

- The AI analysis takes about a minute the first time; answers are cached in `data/llm_cache/`, so rehearsals and the live demo are fast and work offline.
- Which passages count as "in scope" is decided by the sections the rules cite (3.12, 3.1.10, 3.7.3, 3.19, 3.20), not by hand.
