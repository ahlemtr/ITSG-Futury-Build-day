# Knowledge graph: how to build it

Owner: Teammate A (see `00_PROJECT_OVERVIEW.md` section 7). Read `02_BACKEND_IMPLEMENTATION_PLAN.md` section 5 (interface) and `03_DOMAIN_RULES_VORERKRANKUNG.md` first.

## 1. What the graph is for

The graph is only worth building if it answers the queries of the engine better than the YAML backend. It serves exactly these:

| Query | Used by | Why a graph helps |
|---|---|---|
| `get_layout`, `get_rules`, `get_param`, `get_passage`, `get_versions` | parser, rules engine, report | single lookups, a graph is not better than YAML here, but it keeps one source of truth |
| `get_affected_rules(changes)` | spec diff, test builder (M5.2, M5.3), demo step 6 | multi-hop: change -> passage or parameter -> rule -> test case |
| `get_deviation_context(record, field, abgabegrund, version)` | AI triage (M8.5), advisor view | multi-hop: field -> rules -> passages + precedents + flagged blocks |
| `add_precedent`, `find_precedent` | advisor decision (M8.6), catalogue step a | precedents attach to the field they are about |
| `subgraph(node, depth)` | UI, pitch | shows the impact path visually |

Everything else (LLM extraction of rules from all PDFs, Rundschreiben law as entities, salary fields of the 01) stays out.

## 2. Decisions

| Decision | Reason |
|---|---|
| **Curated, not extracted.** The graph is loaded from YAML written by hand from the plan docs and from `starter/layouts/`. The LLM only drafts (M8.3, shown on section 3.12, status `draft`) | an LLM-extracted graph from German legal PDFs is noisy and cannot be validated in hackathon time |
| **Every node points back to a passage** (document, version, section, page) | every verdict and AI proposal must cite its source (principle 2 in `02`) |
| **Version by validity, not by copying.** One `Rule`, one `Parameter` node; values and passages carry `valid_from` | `get_param(name, on_date)` is one lookup, a version change is a data change (principle 3 in `02`) |
| **Join versions by `valid_from`, never by version number** | Beispielpapier "Version 13.3, gültig ab 01.01.2027" belongs to VB **13.4**, not VB 13.3 |
| **Neo4j 5 Community on our VM**, app data (submissions, runs, reports) in a plain Postgres container next to it | readable path queries, Neo4j Browser gives the graph visual for free, no Supabase dependency |
| **YAML backend stays the reference.** `kg/yaml_backend.py` and `kg/graph_backend.py` implement the same interface | if the graph is late or breaks, the engine still runs (`KG_BACKEND=yaml`) |

## 3. Schema

### Nodes

Every node has a unique `key`.

| Label | Key example | Properties | Loaded from |
|---|---|---|---|
| Document | `VB` | title | `kg/seed/documents.yaml` |
| DocVersion | `VB@13.4` | doc, version, published, valid_from | `kg/seed/documents.yaml` |
| Passage | `VB@13.4#3.12` | doc, version, section, heading, text, page | keys from all seed files, text from `kg/seed/passages.yaml` (step 2) |
| MessageType | `41` | name, sender (employer / insurer / both), in_scope | `kg/seed/message_types.yaml` |
| Record | `DBVO` | title, section, page, fixed_length | `starter/layouts/*.yaml` |
| Field | `DBVO.BEGINN-AU` | record, name, start, end, length, type, required, format, repeating, compare_mode | `starter/layouts/*.yaml` + `kg/seed/compare_modes.yaml` |
| Rule | `R41-2` | title, kind (domain / format / reply / chain) | `kg/seed/rules.yaml` |
| Criterion | `0cefe80e-...` | text | `kg/seed/rules.yaml` |
| Parameter | `gap_inclusive` | note | `kg/seed/parameters.yaml` |
| ParamValue | `gap_inclusive@13.4` | value, version, valid_from, simulated | `kg/seed/parameters.yaml` |
| Change | `VB-13.3-13.4-DBVO-chaining` | summary, label (editorial...), in_scope, block, field | `starter/data/spec_diff_13.3_13.4.json` + `kg/seed/changes.yaml` |
| TestCase | `peter-gap-exact` | kind (reference / clone / hidden), origin (itsg / beispielpapier / builder), status, hidden | `kg/seed/test_cases.yaml` |
| Precedent | `41\|DSLW.MM-ANSPRECH\|missing_block` | verdict, reason, advisor, decided | written at runtime by `add_precedent` |

Key formats:
- Passage: `DOC@VERSION#SECTION`, e.g. `VB@13.4#3.12`, `BP@13.3#13.2`, `BVORERK@1#0cefe80e`
- Field: `RECORD.NAME`. Repeating group fields drop the occurrence suffix: layout name `BEGINN-AU-{nn}` becomes `DBVO.BEGINN-AU`. In files and in the Beispielpapier the suffix is written without padding (`BEGINN-AU-1`), so normalize with the regex `-(\{nn\}|\d+)$`
- ParamValue: `PARAM@VERSION`, simulated versions as `sim-13.5`

### Edges

| Edge | From -> To | Properties | Used by |
|---|---|---|---|
| HAS_VERSION | Document -> DocVersion | | `get_versions` |
| SUCCEEDS | DocVersion -> DocVersion (newer -> older) | | `get_versions` |
| CONTAINS | DocVersion -> Passage | | `get_passage` |
| USES_BLOCK | MessageType -> Record | mandatory, flag (e.g. `MM-ANSPRECH`) | format checks F41-3, triage |
| HAS_FIELD | Record -> Field | | `get_layout` |
| DESCRIBED_IN | Field, Record, Parameter, TestCase -> Passage | | triage, report |
| APPLIES_TO | Rule -> MessageType | | `get_rules` |
| CONSTRAINS | Rule -> Field | | triage |
| SOURCED_FROM | Rule -> Passage | | citations, impact (review tier) |
| IMPLEMENTS | Rule -> Criterion | | report shows the ITSG criterion |
| USES_PARAM | Rule -> Parameter | | impact (recompute tier) |
| HAS_VALUE | Parameter -> ParamValue | | `get_param` |
| MODIFIES_OLD, MODIFIES_NEW | Change -> Passage | | impact (review tier) |
| CHANGES_PARAM | Change -> Parameter | | impact (recompute tier) |
| TARGETS | TestCase -> Rule | | impact -> tests to recompute |
| CLONE_OF, HIDDEN_OF | TestCase -> TestCase | | builder lineage |
| ABOUT | Precedent -> Field | | catalogue step a, triage |
| JUSTIFIED_BY | Precedent -> Rule or Passage | | advisor view |

## 4. Build process

Code lives in `kg/` as planned in `02` section 3. Seed files in `kg/seed/`.

| Step | Implement | Test / how |
|---|---|---|
| K0 | VM: `docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<password> -v neo4j_data:/data neo4j:5-community`. Env: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `KG_BACKEND` | Neo4j Browser opens on port 7474 |
| K1 | **seed files by hand** (section 5) | every rule of `03` sections 3 to 7 is in `rules.yaml` |
| K2 | **passage text**: `pdftotext -layout` on each PDF in `sources/`, split at section headings (regex `^\s*\d+(\.\d+)+\s+\S`), skip table of contents lines (dot leaders + page number), write `kg/seed/passages.yaml` as `key -> {heading, text, page}`. Split 3.12 further into sub-passages (section 7) | `VB@13.3#3.12` contains "nicht mindestens 6 Monate", `VB@13.4#3.12` contains "nicht mehr als 6 Monate" |
| K3 | **build in memory** (`kg/seed_graph.py`): read seed + layouts + spec diff into node and edge lists, normalize keys | node counts printed per label |
| K4 | **validate before loading** (section 6). Exit code 1 on errors | break a rule's source key: build fails with the rule id |
| K5 | **load** (`kg/load.py`): unique constraint per label, `UNWIND $rows MERGE` for nodes and edges, full-text index on passages | load twice: identical node and edge counts |
| K6 | **backend** (`kg/graph_backend.py`): one query per interface method (section 8) | all engine tests pass with `KG_BACKEND=graph` (M9.2) |
| K7 | **tests** (section 9) | `pytest tests/test_kg.py` green against the VM |
| K8 | **demo queries** saved as favorites in Neo4j Browser (section 10) | impact path renders in one click |

## 5. Seed files and where each fact comes from

| File | Content | Source |
|---|---|---|
| `documents.yaml` | VB 13.3 (published 24.11.2025, valid 01.01.2026), VB 13.4 (10.03.2026, valid 01.01.2027), GG 13.1, BP 13.3 (valid 01.01.2027), HINWEISE, BVORERK, RS Anl. 1 to 3. Optional list of named passages with headings | `06` section 1, file names in `sources/`. BP, HINWEISE, BVORERK and RS are in the claude.ai project only: copy them into `sources/` before K2 |
| `message_types.yaml` | 01, 41, 61, 62, 88 with `in_scope: true`, the others with `false`. Blocks per message type with `mandatory` and `flag` | `06` section 1; flags from `announced_by` in the layouts (e.g. DBVO by `MM-VOER`); DBAP optional on a 41 via `MM-ANSPRECH` (Beispielpapier 13.1) |
| `parameters.yaml` | `min_total_days`, `gap_months`, `gap_inclusive`, `sum_window_months`, `open_end_days`, `efz_days`, one value per version, `sim-13.5` marked `simulated: true` | `03` section 2 |
| `rules.yaml` | criteria (4 UUIDs) and rules R41-1..6, F41-1..10, K61-1..7, K62-1..2, E-1..3, C-1..8, each with `applies_to`, `fields`, `params`, `sources`, `criterion` | `03` sections 3 to 7 |
| `compare_modes.yaml` | ignore list and rule list with VB section | `05` section 4 |
| `changes.yaml` | curated layer on top of the raw diff: which change touches which parameter (`CHANGES_PARAM`), `in_scope`, summary | `04` sections 1 and 2 |
| `test_cases.yaml` | id, kind, parent, targets | `02` section 7, `03` section 9 |
| from `starter/layouts/*.yaml` | Record (section, page from `spec`), Field (start, end, length, type, required, format), repeating group, `announced_by` flag | already extracted |
| from `starter/data/spec_diff_13.3_13.4.json` | 67 raw changes (`tag, block, field, old, new`), linked by `block` to the record's section passage | already computed |

Rules for writing the seed:
- Field names exactly as in the layouts. Never type a field that is not in a layout; validation catches it (section 6)
- A rule sourced from the VB lists the passage in **both** versions when the text exists in both (e.g. `VB@13.3#3.12` and `VB@13.4#3.12`), so the impact query sees the change
- Cite the narrowest passage that holds the rule (section 7)

Real DBVO field names (from `starter/layouts/DBVO.yaml`): `GRUNDAV`, `AU-AB-AG`, `AU-AB-SV`, `KZ-AK-AU`, `12-MONATSFRIST-AB`, `ANZAHL-AU`, repeating: `BEGINN-AU`, `ENDE-AU`, `KZ-NACHWEIS`, `TEIL-NACHWEIS-AU-BEGINN`, `TEIL-NACHWEIS-AU-ENDE`, `KZ-AU`, `TEIL-ANR-AU-BEGINN`, `TEIL-ANR-AU-ENDE`.

## 6. Validation (step K4)

| Check | Error or warning |
|---|---|
| every rule has at least one SOURCED_FROM and one APPLIES_TO | error |
| every edge points to an existing node | error |
| every passage key resolves to a known DocVersion | error |
| every parameter has a value for 13.3 and 13.4 | error |
| every field a rule constrains exists in a layout | error (catches typos and invented names) |
| every test case targets at least one rule | error |
| every in-scope change reaches at least one rule | warning |
| passages without text | warning until K2 is done |

## 7. Granularity: the lesson from the first build

A first build with 3.12 as one passage returned **17 rules** as affected by the DBVO chaining change, because every format rule (F41) and reply rule (K61) also cites 3.12. Useless for the demo. Two fixes, both required:

1. **Tiered impact.**
   - `recompute`: rules whose **parameter** changed (Change -> CHANGES_PARAM -> Parameter <- USES_PARAM <- Rule). For the chaining change: R41-2, R41-3. Their test cases are recomputed under the new version, and only `peter-gap-exact` flips.
   - `review`: rules that only cite a changed **passage**. Listed for a human to reread, nothing is recomputed.
2. **Finer passages.** Split 3.12 into sub-passages so a sentence-level change hits only the rules sourced from that sentence:

| Passage key | Content | Cited by |
|---|---|---|
| `VB@13.x#3.12/conditions` | when a 41 may be sent (certified AU, 30 days, open end + 1 week) | R41-1, R41-4, R41-6 |
| `VB@13.x#3.12/chaining` | "nicht mindestens" (13.3) / "nicht mehr als" (13.4) 6 Monate, back to the first illness | R41-2, R41-3 |
| `VB@13.x#3.12.7` | periods newest first, more than 6 months not requested | F41-8, R41-3 |
| `VB@13.x#3.12/fields` | field table, insurer-only fields | F41-4..7, F41-9, K61-* |

Pitch line: "We tell ITSG which tests must be regenerated, and which passages a human should reread."

## 8. Queries (step K6)

```cypher
// get_param by date (simulated values only when asked by version)
MATCH (:Parameter {key:$name})-[:HAS_VALUE]->(v)
WHERE NOT v.simulated AND date(v.valid_from) <= date($d)
RETURN v.value ORDER BY v.valid_from DESC LIMIT 1

// get_param by version
MATCH (:Parameter {key:$name})-[:HAS_VALUE]->(v {version:$version}) RETURN v.value

// get_rules(abgabegrund, version): VB passages of that version, other docs always
MATCH (r:Rule)-[:APPLIES_TO]->(:MessageType {key:$ag})
OPTIONAL MATCH (r)-[:SOURCED_FROM]->(p:Passage) WHERE p.doc <> 'VB' OR p.version = $vb
OPTIONAL MATCH (r)-[:IMPLEMENTS]->(c:Criterion)
RETURN r.key, r.title, c.key, collect(DISTINCT p.key)

// impact, tier recompute
MATCH (c:Change)-[:CHANGES_PARAM]->(:Parameter)<-[:USES_PARAM]-(r:Rule)
WHERE c.key IN $ids
OPTIONAL MATCH (t:TestCase)-[:TARGETS]->(r)
RETURN r.key, collect(DISTINCT t.key)

// impact, tier review (minus the recompute rules, done in Python)
MATCH (c:Change)-[:MODIFIES_OLD|MODIFIES_NEW]->(:Passage)<-[:SOURCED_FROM]-(r:Rule)
WHERE c.key IN $ids RETURN DISTINCT r.key

// deviation context for the AI triage
MATCH (r:Rule)-[:CONSTRAINS]->(f:Field {key:$field})
WHERE (r)-[:APPLIES_TO]->(:MessageType {key:$ag})
OPTIONAL MATCH (r)-[:SOURCED_FROM]->(p:Passage) WHERE p.doc <> 'VB' OR p.version = $vb
OPTIONAL MATCH (prec:Precedent)-[:ABOUT]->(f)
RETURN r.key, r.title, collect(DISTINCT p {.key, .text}), collect(DISTINCT prec {.*})

// blocks switched on by a flag field (e.g. MM-ANSPRECH -> DBAP)
MATCH (:MessageType {key:$ag})-[u:USES_BLOCK {flag:$flag}]->(b:Record)
RETURN b.key, u.mandatory
```

Load pattern (labels and relationship types from a whitelist in code, never from input):

```cypher
CREATE CONSTRAINT rule_key IF NOT EXISTS FOR (n:Rule) REQUIRE n.key IS UNIQUE;
UNWIND $rows AS row MERGE (n:Rule {key: row.key}) SET n += row;
UNWIND $rows AS r MATCH (a:Rule {key:r.s}) MATCH (b:Passage {key:r.d})
MERGE (a)-[e:SOURCED_FROM]->(b) SET e += r.p;
CREATE FULLTEXT INDEX passage_text IF NOT EXISTS FOR (p:Passage) ON EACH [p.text, p.heading]
OPTIONS {indexConfig: {`fulltext.analyzer`: 'german'}};
```

Simulated versions (`sim-13.5`) have no text of their own: passage lookups fall back to the newest real VB version.

## 9. Tests (step K7)

| Test | Expected |
|---|---|
| `get_param("gap_inclusive", on_date=2026-11-01)` | false |
| `get_param("gap_inclusive", on_date=2027-01-01)` | true |
| `get_param("min_total_days", version="sim-13.5")` | 28 |
| `get_param("min_total_days", on_date=2028-06-01)` | 30 (simulated values never returned by date) |
| `get_layout("DBVO", "13.4")` | fields in position order, `BEGINN-AU` marked repeating |
| `get_rules("41", "13.3")` | sources contain `VB@13.3#...`, never `VB@13.4#...` |
| impact of `VB-13.3-13.4-DBVO-chaining` | recompute = {R41-2, R41-3}; tests contain `peter`, `peter-gap-exact`, `peter-gap-in`, `peter-gap-out`, `peter-hidden`, `peter-gap-exact-hidden`, `bp-13-2`, `bp-13-3`; F41/K61 rules only in review |
| deviation context for 41, `DSLW.MM-ANSPRECH` | rule F41-3, flagged block DBAP (not mandatory), passage BP 13.1 |
| `add_precedent` then `find_precedent` for the same signature | precedent returned, no AI call needed |
| load the seed twice | identical node and edge counts |
| validation with a typo in a rule field | build fails naming the rule and field |

## 10. Demo views (Neo4j Browser favorites)

```cypher
// 1. The 13.4 change and its impact path
MATCH p = (c:Change {key:'VB-13.3-13.4-DBVO-chaining'})-[:CHANGES_PARAM]->(:Parameter)
          <-[:USES_PARAM]-(r:Rule)<-[:TARGETS]-(t:TestCase)
RETURN p

// 2. Why a deviation on a field matters
MATCH p = (f:Field {key:'DSLW.MM-ANSPRECH'})<-[:CONSTRAINS]-(r:Rule)-[:SOURCED_FROM]->(:Passage)
RETURN p

// 3. One rule end to end
MATCH p = (r:Rule {key:'R41-2'})-[*1]-() RETURN p
```

## 11. Interface changes compared to `02` section 5

| Method | Change |
|---|---|
| `get_affected_rules(changes)` | returns `{recompute: [rule], review: [rule], tests: [test_case]}` instead of `list[Rule]`; M5.2 and M5.3 use `recompute` only |
| `get_param(name, version=None, on_date=None)` | both lookup modes, simulated values only by version |
| `get_deviation_context(record, field, abgabegrund, version)` | new, used by M8.5 |
| `add_precedent(...)`, `find_precedent(...)` | new, used by M8.6 and catalogue step a |
| `search_passages(text)` | new, full-text search for the advisor |
| `subgraph(label, key, depth)` | new, for the UI |

`kg/yaml_backend.py` implements the same methods so both backends stay interchangeable.

## 12. Verified against the sources (26.10.2026)

| Point | Status | Evidence |
|---|---|---|
| 13.4 chaining wording "nicht mehr als 6 Monate" | confirmed | VB 13.4, DBVO 3.12, Stand 10.03.2026 |
| ITSG criterion 0cefe80e uses the 13.4 wording | confirmed | DTA-EEL-Beispiel_Vorerkrankung.docx |
| Format values of a 41 (KORR 00, MM-VOER J, GRUNDAV 1, insurer fields zero, MM-ANSPRECH J) | confirmed | Beispielpapier 13.1 |
| Repeating field names and suffix | `BEGINN-AU-{nn}` etc., suffix unpadded in examples | `starter/layouts/DBVO.yaml`, Beispielpapier 13.1 |
| Beispielpapier version | "Version 13.3, gültig ab 01.01.2027", pairs with VB 13.4 | file name and title page |
| ITSG criteria doc is internally inconsistent | requirement text says "nicht mindestens 6 Monate" (13.3), criterion 0cefe80e says "nicht mehr als" (13.4). Store one passage per criterion UUID, never the whole doc as one passage | DTA-EEL-Beispiel_Vorerkrankung.docx |

## 13. Open questions

1. Which wording in DTA-EEL-Beispiel_Vorerkrankung.docx is authoritative for 2027? (now `00` section 9, question 9, together with the unchanged insurer paragraph of VB 13.4 3.12)
2. DBAP, DBNA, DBAN layouts are inferred, partial or missing (`starter/layouts/README.md`): fields there are loaded with `status` from the layout and excluded from the strict field check.
