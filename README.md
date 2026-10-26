# EEL Review Assistant: complete package

| Folder | Content |
|---|---|
| `plan/` | project overview, diagrams, backend plan, rules, spec diff, checking, lifecycle, knowledge graph, plus `starter/` (layouts, parser sketch, diff script and output) |
| `sources/` | original source files: challenge deck, glossary, workflow, GG V13.1, Verfahrensbeschreibung V13.3 and V13.4, Beispielpapier V13.3, Rundschreiben Anl. 1 to 3, DTA-EEL-Beispiel_Vorerkrankung.docx, Hinweise_Testkonstellation.docx, Pool-Testaufgaben 2025/2026, TEEL0 reference file |

Still missing everywhere: Anlage 3 of the Verfahrensbeschreibung (data blocks per Abgabegrund). Not to be confused with `Anl3` of the Rundschreiben, which is in `sources/`.

Start with `plan/00_PROJECT_OVERVIEW.md`. Tech stack: `plan/09_TECH_STACK.md`. Knowledge graph build guide: `plan/08_KG_SEEDING_GUIDE.md`.

## Knowledge graph (`kg/`)

Built per `plan/08_KG_SEEDING_GUIDE.md`. Needs `uv`, poppler (`pdftotext`) and, for the graph backend, Neo4j 5.13+.

```
uv sync
cp .env.example .env                      # set NEO4J_PASSWORD (and OPENAI_API_KEY for embeddings)
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<password> \
  -e NEO4J_PLUGINS='["apoc"]' -v neo4j_data:/data neo4j:5.26-community
uv run python -m kg.build                 # extract -> build -> validate -> load -> embed
uv run python -m kg.build --skip-load     # offline: passages + graph.json + validation only
uv run pytest tests/test_kg.py            # both backends; graph tests skip without Neo4j
```

`KG_BACKEND=yaml` (default) answers from `kg/seed/`, `layouts/` and `kg/build/passages.yaml` without Neo4j or OpenAI;
`KG_BACKEND=graph` uses Neo4j. `kg.get_kb()` returns the selected backend. Without `OPENAI_API_KEY` the embed step is
skipped and search uses the full-text index.
