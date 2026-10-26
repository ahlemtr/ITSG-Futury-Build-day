# Knowledge graph: seeding guide (step by step)

This is the build guide for the knowledge graph. Follow it top to bottom. It is written so that a coding agent (Claude Code) can execute it without asking questions. Where a value is not known, the guide says so and gives the fallback.

`07_KNOWLEDGE_GRAPH.md` explains **why** the graph looks like this. This file says **exactly how** to build it. Where the two differ in a detail, this file wins.

Read first: `07_KNOWLEDGE_GRAPH.md` sections 1 to 3, `03_DOMAIN_RULES_VORERKRANKUNG.md`, `09_TECH_STACK.md`.

## 0. Result and done criteria

At the end there is:
- a folder `kg/` with seed files, build scripts and the graph backend (section 2)
- a running Neo4j with all nodes, edges, a full-text index and a vector index on passages
- `pytest tests/test_kg.py` green (section 14)

Done when:
- [ ] `python -m kg.build` runs end to end with exit code 0 and prints node and edge counts per label
- [ ] running it twice gives identical counts
- [ ] every query in section 13 returns the expected answer
- [ ] `KG_BACKEND=yaml` and `KG_BACKEND=graph` give the same answers for the tests in section 14

## 1. Fixed terminology and conventions

These names are a contract with the rest of the backend and the LLM tools. Use them exactly. Do not invent synonyms.

### 1.1 Document codes

| Code | Document | File in `sources/` |
|---|---|---|
| `VB` | Verfahrensbeschreibung DTA EEL | `2025_11_24_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.3.pdf`, `2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf` |
| `GG` | Gemeinsame Grundsätze EEL | `GG_EEL_V13.1_06.05.2025.pdf` |
| `PTA` | Pool-Testaufgaben 2025/2026 | `PTA_Gemeinsame-Testaufgaben-2025-2026_Version-3.pdf` |
| `BP` | Beispielpapier DTA EEL | `2026_03_10_Endfassung_Beispielpapier_DTA_EEL_Version_13.3_gueltig_ab_01.01.2027.pdf` |
| `HINWEISE` | Hinweise DTA-EEL-Beispiel Vorerkrankung Testkonstellation | `Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx` |
| `BVORERK` | DTA-EEL-Beispiel_Vorerkrankung (ITSG criteria) | `DTA-EEL-Beispiel_Vorerkrankung.docx` |
| `RS-ANL1` | Rundschreiben Entgeltersatzleistungen, Anlage 1 | `2025_12_10_NS_FLB_TOP_01_24c24i45SGBV45SGBVII47SGBXIV_Aktualisierung_der_GR_zu_EEL_Anl1.pdf` |
| `RS-ANL2` | Rundschreiben Entgeltersatzleistungen, Anlage 2 | `2025_12_10_NS_FLB_TOP_01_24c24i45SGBV45SGBVII47SGBXIV_Aktualisierung_der_GR_zu_EEL_Anl2.pdf` |
| `RS-ANL3` | Rundschreiben Entgeltersatzleistungen, Anlage 3 | `2024_12_11_NS_FLB_TOP_02_24c24i4444b45SGBV45SGBVII47SGBXIV_Aktualisierung_der_GR_zu_Entgeltersatzleistungen_Anl3.pdf` |

Not loaded: `Futury-Hackathon-2026-Englisch.pdf`, the Translation Assistance PDF, `TEEL0-Test1-DBVO` (a record file, used by the parser, not text), `workflow.png`.

If a listed file is missing, skip it, print a warning, and continue. Sources in brackets in section 9 are optional for that reason.

### 1.2 Version strings

| Document | Version string | published | valid_from |
|---|---|---|---|
| VB | `13.3` | 2025-11-24 | 2026-01-01 |
| VB | `13.4` | 2026-03-10 | 2027-01-01 |
| GG | `13.1` | 2025-05-06 | 2026-01-01 |
| PTA | `2025-2026-v3` | 2026-09-22 | 2026-01-01 |
| BP | `13.3` | 2026-03-10 | 2027-01-01 |
| HINWEISE | `1` | null | 2027-01-01 |
| BVORERK | `1` | null | 2027-01-01 |
| RS-ANL1, RS-ANL2 | `2025-12-10` | 2025-12-10 | 2025-12-10 |
| RS-ANL3 | `2024-12-11` | 2024-12-11 | 2024-12-11 |
| simulated | `sim-13.5` | none | none |

Join versions by `valid_from`, never by number: BP `13.3` belongs with VB `13.4` (both valid from 2027-01-01).

### 1.3 Key formats

| Thing | Format | Examples |
|---|---|---|
| DocVersion | `DOC@VERSION` | `VB@13.4`, `GG@13.1` |
| Passage | `DOC@VERSION#SECTION` or `DOC@VERSION#SECTION/PART` | `VB@13.4#3.12`, `VB@13.4#3.12/chaining`, `VB@13.4#3.12.7`, `BP@13.3#13.2`, `BVORERK@1#0cefe80e` |
| Record | block code | `DSLW`, `DBVO` |
| Field | `RECORD.NAME`, repeating suffix removed | `DSLW.ABGABEGRUND`, `DBVO.BEGINN-AU` |
| MessageType | Abgabegrund, 2 digits, string | `"01"`, `"41"`, `"88"` |
| Rule | rule id from `03` | `R41-2`, `F41-8`, `K61-1`, `E-1`, `C-3` |
| Criterion | full ITSG UUID, lower case | `0cefe80e-4fd9-41e1-be4f-3ae1ecbde646` |
| Parameter | snake_case name from `03` section 2 | `gap_inclusive` |
| ParamValue | `PARAM@VERSION` | `gap_inclusive@13.4`, `min_total_days@sim-13.5` |
| Change | `VB-13.3-13.4-NNN` for raw diff entries (NNN = index in the JSON, 3 digits), curated names for in-scope ones (section 10) | `VB-13.3-13.4-017`, `VB-13.3-13.4-DBVO-chaining` |
| TestCase | lower case, hyphens | `peter`, `peter-gap-exact`, `bp-13-2` |
| Precedent | `ABGABEGRUND\|FIELD\|KIND` | `41\|DSLW.MM-ANSPRECH\|missing_block` |

Repeating field names: the layouts write `BEGINN-AU-{nn}`, files and examples write `BEGINN-AU-1`. Normalize both with the regex `-(\{nn\}|\d+)$` → remove.

### 1.4 Enumerations (exact values)

| Property | Allowed values |
|---|---|
| `Rule.kind` | `domain`, `format`, `reply`, `chain`, `efz` |
| `Rule.status` | `approved`, `draft` |
| `MessageType.sender` | `employer`, `insurer`, `both` |
| `Field.type` | `an`, `n` |
| `Field.required` | `M`, `m` |
| `Field.compare_mode` | `compare`, `rule`, `ignore` |
| `Record.status` / `Field.status` | `extracted`, `inferred`, `partial`, `missing` |
| `USES_BLOCK.mandatory` | `true`, `false`, `unknown` |
| `TestCase.kind` | `reference`, `clone`, `hidden` |
| `TestCase.origin` | `itsg`, `beispielpapier`, `builder`, `pta` |
| `TestCase.status` | `draft`, `approved`, `rejected` |
| `Change.tag` | `replace`, `insert`, `delete` (from the diff JSON) |
| `Change.label` | `editorial`, `clarification`, `law_change`, `unknown` |
| `Precedent.verdict` | `correct_variant`, `bug`, `invalid` |
| deviation kind (in precedent keys) | `value_differs`, `missing_block`, `extra_block`, `missing_message`, `extra_message`, `missing_group`, `extra_group`, `order_differs` |

### 1.5 Data conventions

- Dates: ISO strings `YYYY-MM-DD` in YAML and in Neo4j (`date()` type in Neo4j).
- All YAML files: UTF-8, 2-space indent, keys in snake_case.
- Booleans: `true` / `false`, never `J` / `N` (those stay only inside record files).
- Text from documents: keep German as is, no translation.

## 2. Folder layout

```
kg/
├── __init__.py
├── interface.py          # KnowledgeBase Protocol (02 section 5), Pydantic models imported from engine/model.py
├── yaml_backend.py       # reference backend, reads kg/seed + layouts/
├── graph_backend.py      # Neo4j backend, same interface
├── build.py              # entry point: python -m kg.build [--skip-embed] [--skip-load]
├── extract/
│   ├── pdf_text.py       # pdftotext + cleanup (section 5.1)
│   ├── vb.py             # VB splitter (section 5.2)
│   ├── generic.py        # GG, PTA, BP, RS splitter (section 5.3)
│   └── docx.py           # HINWEISE, BVORERK (section 5.4)
├── seed_graph.py         # seed + layouts + diff -> nodes and edges in memory (section 12.1)
├── validate.py           # section 12.2
├── load.py               # Neo4j load (section 12.3)
├── embed.py              # OpenAI embeddings with cache (section 12.4)
├── seed/                 # hand-written, committed
│   ├── documents.yaml
│   ├── message_types.yaml
│   ├── parameters.yaml
│   ├── rules.yaml
│   ├── compare_modes.yaml
│   ├── changes.yaml
│   ├── test_cases.yaml
│   └── precedents.yaml   # starts as an empty list: []
└── build/                # generated, NOT committed (add to .gitignore)
    ├── text/             # pdftotext output per DocVersion
    ├── passages.yaml
    ├── embeddings.jsonl  # cache: {sha256, model, vector}
    └── graph.json        # nodes + edges after seed_graph, for debugging
```

`layouts/` is the copy of `plan/starter/layouts/*.yaml` at repo root (task M0.2). The diff JSON is copied to `kg/seed/spec_diff_13.3_13.4.json`.

## 3. Step K0: environment

1. Neo4j (needs 5.13 or newer for vector indexes):
   ```
   docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \
     -e NEO4J_AUTH=neo4j/<password> -e NEO4J_PLUGINS='["apoc"]' \
     -v neo4j_data:/data neo4j:5.26-community
   ```
2. Python deps: `neo4j`, `pyyaml`, `pydantic>=2`, `python-docx`, `openai`, `python-dateutil`, `pytest`.
3. System tool: `pdftotext` (poppler). Check with `pdftotext -v`.
4. `.env`: `NEO4J_URI=bolt://localhost:7687`, `NEO4J_USER=neo4j`, `NEO4J_PASSWORD=...`, `OPENAI_API_KEY=...`, `OPENAI_EMBED_MODEL=text-embedding-3-small`, `KG_BACKEND=yaml`.

Check: Neo4j Browser opens on `http://<vm>:7474`, `pdftotext -v` prints a version.

## 4. Step K1: `documents.yaml`

Write exactly this structure, one entry per row of section 1.2 (only for files present, plus all VB, GG, PTA):

```yaml
documents:
  - code: VB
    title: Verfahrensbeschreibung DTA EEL
    versions:
      - version: "13.3"
        published: 2025-11-24
        valid_from: 2026-01-01
        file: sources/2025_11_24_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.3.pdf
      - version: "13.4"
        published: 2026-03-10
        valid_from: 2027-01-01
        file: sources/2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf
        succeeds: "13.3"
  - code: GG
    ...
```

Nodes: `Document {key: code, title}`, `DocVersion {key: "CODE@VERSION", doc, version, published, valid_from, file}`. Edges: `HAS_VERSION`, `SUCCEEDS` (newer to older).

## 5. Step K2: passages (spec text)

Output: `kg/build/passages.yaml` as a list of `{key, doc, version, section, part, heading, text, page, field}`. `part` and `field` are null unless set below.

### 5.1 PDF to clean text (all PDFs)

1. `pdftotext -enc UTF-8 -layout <file> kg/build/text/<DOC>@<VERSION>.txt`
2. Track the page number by counting the form feed characters `\f` that pdftotext writes between pages (page = number of `\f` before the line + 1).
3. Remove: footer lines (`^\s*Stand:? \d`, `^\s*Seite \d+ von`), lines that hold only a page number (`^\s*\d{1,3}\s*$`, BP), the running header line directly after a VB footer (the line right after the footer, if it equals the current block title), GG footnote lines starting with `1 Das Bundesministerium`.
4. Remove table-of-contents lines: any line containing 4 or more dots in a row (`\.{4,}`).
5. When building passage text (not when finding headings): join lines, collapse whitespace to single spaces, and remove hyphenation: a line ending in `-` followed by a line starting with a lower-case letter is joined without the hyphen.

### 5.2 VB splitter

Three levels.

**Level 1: sections.** Start reading at the first column-0 line `2. Grundsätzliches` (everything before it is one passage `VB@V#1`, heading "Einführung"). A heading line matches:
```
^(\d+\.|\d+\.\d+(?:\.\d+)*)\s+([A-ZÄÖÜ].*)$
```
- must start in column 0
- the first character after the number must be an upper-case letter (this skips cross-references like `3.7 „Datenbaustein ...` at line start)
- the section number must be greater than the previous accepted one (compare as tuples of ints). Otherwise the line is body text. This removes false hits.
- strip a trailing `.` from the number (`2.` → `2`)

Each heading starts a passage `VB@V#<number>` that runs until the next accepted heading. Stop at `4. Anlagen`.

**Level 2: fields inside a block (3.1 to 3.20).** Inside a block section, each field's text becomes its own passage, numbered like the spec does:
- Field sub-section number = position of the field in the layout's `fields` list (then `repeating_group.fields`), counting only fields **without** a `source` key, starting at 1. Examples to verify: `3.1.10` = BBNR-VU, `3.1.11` = DATENSATZ-ID, `3.1.18` = ABGABEGRUND, `3.7.3` = EEL-ENDE, `3.12.5` = 12-MONATSFRIST-AB, `3.12.7` = BEGINN-AU, `3.12.9` = KZ-NACHWEIS, `3.12.12` = KZ-AU, `3.19.2` = AKTENZEICHEN-VERURSACHER, `3.19.3` = REFERENZ-ID.
- Find the field in the text by its layout row: `^\s*\d{3}\s*[-–]\s*\d{2,3}\s+(an|n|AN|N)\s+[MmKk]\s+(\S+)`; group 2 is the field name (normalize the `nn` suffix).
- The field passage starts at the last non-empty line before the row (the field heading) and ends right before the next field's heading or the end of the block.
- Key `VB@V#3.12.7`, `field: DBVO.BEGINN-AU`, heading = the heading line.
- The block passage `VB@V#3.12` keeps only the text before the first field heading.
- If a row is not found, print a warning; that field then has no own passage and rules fall back to the block passage.

**Level 3: parts of the 3.12 intro.** Split the block passage `VB@V#3.12` at these anchor sentences (they exist in both 13.3 and 13.4; search in the cleaned, joined text). Each part runs from its anchor to the next anchor:

| Part key | Starts at anchor | Content |
|---|---|---|
| `3.12/conditions` | `Die Vorerkrankungsanfrage (3.1.18` | when a 41 may be sent: sick note, 6 months, 30 days, open end + 1 week, eAU counts |
| `3.12/chaining` | `Bei der Anfrage sollen` | as many periods as possible, the 6-month chaining sentence, back to the first illness, Kurz-AU |
| `3.12/scope` | `Der Arbeitgeber stellt eine` | who asks whom, exclusions (private insurance, marginal jobs) |
| `3.12/insurer` | `Die Rückmeldung durch die Krankenkasse` | what the insurer returns, its own 6-month wording, 12-month limit |
| `3.12/uebergangsgeld` | `Erfolgt die Meldung durch den Arbeitgeber für GKV` | Abgabegrund 11/12 case |

`VB@V#3.12` itself stays as a passage with the full intro text (for search). Parts are extra passages with `part` set.

Checks (must pass):
- `VB@13.3#3.12/chaining` contains `nicht mindestens 6 Monate`
- `VB@13.4#3.12/chaining` contains `nicht mehr als 6 Monate` and not `nicht mindestens`
- `VB@13.4#3.12/insurer` contains `nicht mindestens 6 Monate` (the inconsistency inside 13.4)
- `VB@13.4#3.12.7` contains `mehr als 6 Monate`

### 5.3 GG, PTA, BP, RS splitter

Same as VB level 1 (heading regex, increasing numbers, upper-case first letter), with these differences:
- start at the first heading after the table of contents
- headings may be indented (GG indents sub-sections): allow leading spaces up to 12
- GG: section `2.1.2` (Abgabegrund 41) and `2.2.1` (61) must exist
- PTA: only keep chapters 1, 2, 5 and 8 (process, EEL, permanent test cases). Section `5.14` (EEL, TA 167 and 168) must exist
- BP: the examples are numbered like `13.1 Anfrage bei einer Vorerkrankung` and chapters like `23. Abgabegrund 88 – Stornierung eines Datensatzes`. Key `BP@13.3#13.1`, `BP@13.3#23`. Must exist: 13.1 to 13.5, 16.1, 16.5, 16.7, 17.1, 23
- RS-ANL1 to RS-ANL3: retrieval only, no rule cites them. Same heading rule; if no heading is found, one passage per page with key `RS-ANLn@VERSION#p<page>`

### 5.4 Word files (`.docx`)

Read with `python-docx`. Walk paragraphs and tables in document order.
Tables become text with one line per row, cells joined by ` | `.

- **BVORERK** (no heading styles, 2 tables): one passage per ITSG criterion. A criterion is found by its UUID (regex `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`, case-insensitive). Passage key `BVORERK@1#<first 8 hex chars>`, text = the paragraph or table row holding the UUID plus the text up to the next UUID. All text before the first UUID is `BVORERK@1#intro`. Must exist: `f41c7278`, `0cefe80e`, `aade0289`, `9c8c9b58`.
- **HINWEISE** (no heading styles, list paragraphs and 1 table): exactly two passages. `HINWEISE@1#facts` = all paragraphs (Peter's AU periods, employment end, what the insurer knows). `HINWEISE@1#chain` = the table (the expected message chain with IDs and dates). The UUID-like values in this file (`11111111-...`, `AAAAAAAA-...`) are DATENSATZ-IDs, not criteria: do not apply the BVORERK rule here.
- Never store a whole document as one passage when it has structure (07 section 12: the criteria doc mixes 13.3 and 13.4 wording).

## 6. Step K3: records and fields (from layouts)

For every `layouts/*.yaml`:
- `Record {key: record, title, section: spec.section, page: spec.page, fixed_length, status}`
- `Record -[:DESCRIBED_IN]-> Passage VB@13.3#<section>` and `VB@13.4#<section>` (layouts are identical in both versions)
- for each entry of `fields` and `repeating_group.fields`: `Field {key: "RECORD.NAME", record, name, start, end, length, type, required, format, constant, values, repeating (true for group fields), offset_in_group, status (the record's status; DSLW `MM-*` flags get `inferred` because their names come from the Beispielpapier), compare_mode (section 8, default "compare")}`
- `Record -[:HAS_FIELD {order}]-> Field`
- `Field -[:DESCRIBED_IN]-> Passage VB@V#<field section>` when section 5.2 level 2 produced it
- DSLW `block_order` → `Record DSLW -[:CARRIES {order, flag}]-> Record DBxx`, flag from each block's `announced_by.field`

Check: DBVO has 7 fixed fields + 8 repeating ones; `DBVO.BEGINN-AU` has `repeating: true`.

## 7. Step K4: `message_types.yaml`

```yaml
message_types:
  - {code: "01", name: Entgeltbescheinigung Krankengeld, sender: employer, in_scope: true}
  - {code: "41", name: Anforderung anrechenbare Vorerkrankungen, sender: employer, in_scope: true}
  - {code: "61", name: Rückmeldung Vorerkrankungen, sender: insurer, in_scope: true}
  - {code: "62", name: Rückmeldung Ende Entgeltersatzleistung, sender: insurer, in_scope: true}
  - {code: "88", name: Stornierung, sender: both, in_scope: true}
  # plus with in_scope: false: 02, 03, 04, 11, 12, 21, 22, 23, 31, 42, 51, 66, 67, 71, 72, 73, 99 (names from 06 section 1)
blocks:
  - {type: "41", record: DBNA, flag: MM-NAME,      mandatory: true}
  - {type: "41", record: DBAN, flag: MM-ANSCHRIFT, mandatory: unknown}
  - {type: "41", record: DBVO, flag: MM-VOER,      mandatory: true}
  - {type: "41", record: DBAP, flag: MM-ANSPRECH,  mandatory: unknown}
  - {type: "41", record: DBID, flag: MM-ID,        mandatory: unknown}
  - {type: "61", record: DBNA, flag: MM-NAME,      mandatory: true}
  - {type: "61", record: DBVO, flag: MM-VOER,      mandatory: true}
  - {type: "61", record: DBAP, flag: MM-ANSPRECH,  mandatory: unknown}
  - {type: "61", record: DBID, flag: MM-ID,        mandatory: true}
  - {type: "01", record: DBNA, flag: MM-NAME,      mandatory: true}
  - {type: "01", record: DBAL, flag: MM-ALLGEMEIN, mandatory: true}
  - {type: "01", record: DBAE, flag: MM-ENTGELT,   mandatory: true}
  - {type: "01", record: DBAP, flag: MM-ANSPRECH,  mandatory: unknown}
  - {type: "01", record: DBID, flag: MM-ID,        mandatory: unknown}
  - {type: "88", record: DBSD, flag: MM-SD,        mandatory: true}
  - {type: "62", record: DBNA, flag: MM-NAME,      mandatory: true}
  - {type: "62", record: DBEE, flag: MM-EELENDE,   mandatory: true}
  - {type: "62", record: DBAP, flag: MM-ANSPRECH,  mandatory: unknown}
  - {type: "62", record: DBID, flag: MM-ID,        mandatory: true}
```

`unknown` because Anlage 3 of the VB is missing (`00` question 11). Do not guess `true` or `false`.

Nodes `MessageType {key: code, name, sender, in_scope}`, edges `MessageType -[:USES_BLOCK {flag, mandatory}]-> Record`, `MessageType -[:DESCRIBED_IN]-> Passage` for `GG@13.1#2.1.2` (41), `GG@13.1#2.2.1` (61), `GG@13.1#2.2.2` (62), `GG@13.1#2.5` (88), `GG@13.1#2.1.1` (01).

## 8. Step K5: `compare_modes.yaml`

Every field not listed is `compare`.

```yaml
ignore:
  - {field: DSLW.DATUM-ERSTELLUNG,   source: VB@13.4#3.1.5}
  - {field: DSLW.DATUM-VERARBEITUNG, source: VB@13.4#3.1.14}
  - {field: DBID.AKTENZEICHEN-SV,    source: VB@13.4#3.19.1}
  - {field: DBNA.UNKLAR,             source: null, note: positions 065-125 unknown}
  - {record: DBAE, all_fields_except_dates_and_flags: true, note: vendor payroll amounts}
  - {record: DBAL, all_fields_except_dates_and_flags: true, note: vendor payroll amounts}
rule:
  - {field: DSLW.DATENSATZ-ID,             rule: C-1,   source: VB@13.4#3.1.11}
  - {field: DSLW.PRODUKT-IDENTIFIER,       rule: null,  source: VB@13.4#3.1.12}
  - {field: DSLW.MODIFIKATIONS-IDENTIFIER, rule: null,  source: VB@13.4#3.1.13}
  - {field: DSLW.ABSENDERNUMMER,           rule: null,  source: VB@13.4#3.1.2}
  - {field: DSLW.ABRECHNUNGSPROGRAMM,      rule: null,  source: VB@13.4#3.1.20}
  - {field: DBID.AKTENZEICHEN-VERURSACHER, rule: C-2,   source: VB@13.4#3.19.2}
  - {field: DBID.REFERENZ-ID,              rule: K61-1, source: VB@13.4#3.19.3}
  - {record: DBAP, all_fields: true,       rule: null,  source: VB@13.4#3.18}
```

"Dates and flags" = fields with `format: date_yyyymmdd`, plus fields whose name starts with `MM-` or `KZ-` or ends with `GRUND`. `rule: null` means "checked by the intake against the vendor's registration", not by a domain rule.

## 9. Step K6: `parameters.yaml` and `rules.yaml`

### 9.1 `parameters.yaml`

```yaml
parameters:
  - name: min_total_days
    note: prior days in the window + current days must reach this
    values:
      - {version: "13.3",     valid_from: 2026-01-01, value: 30}
      - {version: "13.4",     valid_from: 2027-01-01, value: 30}
      - {version: "sim-13.5", valid_from: null,       value: 28, simulated: true}
    sources: [VB@13.3#3.12/conditions, VB@13.4#3.12/conditions]
```

Same shape for all six, values from `03` section 2:

| name | 13.3 | 13.4 | sim-13.5 | sources (both VB versions unless noted) |
|---|---|---|---|---|
| `min_total_days` | 30 | 30 | 28 | `3.12/conditions` |
| `gap_months` | 6 | 6 | 6 | `3.12/conditions`, `3.12/chaining` |
| `gap_inclusive` | false | true | true | `3.12/chaining` |
| `sum_window_months` | 12 | 12 | 12 | `3.12/conditions` |
| `open_end_days` | 7 | 7 | 7 | `3.12/conditions`, `BP@13.3#13.5` |
| `efz_days` | 42 | 42 | 42 | `VB@V#3.12.5` |

Nodes `Parameter {key: name, note}`, `ParamValue {key: "name@version", value, version, valid_from, simulated}`, edges `HAS_VALUE`, `Parameter -[:DESCRIBED_IN]-> Passage`.

### 9.2 `rules.yaml`

One entry per rule:

```yaml
rules:
  - id: R41-2
    title: gap between current AU start and last prior AU end at most gap_months
    kind: domain
    status: approved
    criterion: 0cefe80e-4fd9-41e1-be4f-3ae1ecbde646
    applies_to: ["41"]
    fields: [DBVO.BEGINN-AU, DBVO.ENDE-AU, DBVO.AU-AB-AG]
    params: [gap_months, gap_inclusive]
    sources: [VB@13.3#3.12/chaining, VB@13.4#3.12/chaining, BVORERK@1#0cefe80e]
```

`sources` written as `VB@V#x` in the table below means **both** `VB@13.3#x` and `VB@13.4#x`. Sources in brackets are only added if that file is present; every rule keeps at least one VB or GG source.

| id | kind | applies_to | fields | params | sources | criterion |
|---|---|---|---|---|---|---|
| R41-1 | domain | 41 | DBVO.AU-AB-AG | | VB@V#3.12/conditions, (BVORERK@1#f41c7278) | f41c7278-b5a5-4ec3-b321-39bca5c3aeeb |
| R41-2 | domain | 41 | DBVO.BEGINN-AU, DBVO.ENDE-AU, DBVO.AU-AB-AG | gap_months, gap_inclusive | VB@V#3.12/chaining, (BVORERK@1#0cefe80e) | 0cefe80e-4fd9-41e1-be4f-3ae1ecbde646 |
| R41-3 | domain | 41 | DBVO.BEGINN-AU, DBVO.ENDE-AU | gap_months, gap_inclusive | VB@V#3.12/chaining, VB@V#3.12.7, (BP@13.3#13.2), (BVORERK@1#aade0289) | aade0289-e8f9-4e12-9c49-464cf6cd0789 |
| R41-4 | domain | 41 | DBVO.BEGINN-AU, DBVO.ENDE-AU, DBVO.AU-AB-AG | min_total_days, sum_window_months | VB@V#3.12/conditions, (BP@13.3#13.4), (BVORERK@1#9c8c9b58) | 9c8c9b58-4d0f-4066-98ac-973095418d63 |
| R41-5 | domain | 41 | DBVO.BEGINN-AU, DBVO.ENDE-AU | | VB@V#3.12/chaining | |
| R41-6 | domain | 41 | DBVO.AU-AB-AG | open_end_days | VB@V#3.12/conditions, (BP@13.3#13.5) | |
| F41-1 | format | 41 | DSLW.ABGABEGRUND | | VB@V#3.1.18 | |
| F41-2 | format | 41 | DSLW.KORR-ABGABEGRUND | | VB@V#3.1.19 | |
| F41-3 | format | 41 | DSLW.MM-VOER, DSLW.MM-ANSPRECH, DSLW.MM-ID, DSLW.MM-NAME, DSLW.MM-ANSCHRIFT | | VB@V#3.1, (BP@13.3#13.1) | |
| F41-4 | format | 41 | DBVO.GRUNDAV | | VB@V#3.12.1 | |
| F41-5 | format | 41 | DBVO.AU-AB-AG | | VB@V#3.12.2 | |
| F41-6 | format | 41 | DBVO.AU-AB-SV, DBVO.KZ-AK-AU, DBVO.12-MONATSFRIST-AB | | VB@V#3.12.3, VB@V#3.12.4, VB@V#3.12.5 | |
| F41-7 | format | 41 | DBVO.ANZAHL-AU | | VB@V#3.12.6 | |
| F41-8 | format | 41 | DBVO.BEGINN-AU, DBVO.ENDE-AU | | VB@V#3.12.7 | |
| F41-9 | format | 41 | DBVO.KZ-NACHWEIS, DBVO.TEIL-NACHWEIS-AU-BEGINN, DBVO.TEIL-NACHWEIS-AU-ENDE, DBVO.KZ-AU, DBVO.TEIL-ANR-AU-BEGINN, DBVO.TEIL-ANR-AU-ENDE | | VB@V#3.12.9, VB@V#3.12.12 | |
| F41-10 | format | 41 | DSLW.DATENSATZ-ID | | VB@V#3.1.11 | |
| K61-1 | reply | 61 | DBID.REFERENZ-ID | | VB@V#3.19.3 | |
| K61-2 | reply | 61 | DSLW.BBNR-VU | | VB@V#3.1.10 | |
| K61-3 | reply | 61 | DBVO.BEGINN-AU, DBVO.ENDE-AU | | VB@V#3.12/insurer | |
| K61-4 | reply | 61 | DBVO.KZ-NACHWEIS | | VB@V#3.12.9 | |
| K61-5 | reply | 61 | DBVO.KZ-AU, DBVO.TEIL-ANR-AU-BEGINN, DBVO.TEIL-ANR-AU-ENDE | | VB@V#3.12.12, VB@V#3.12.13, VB@V#3.12.14, (BP@13.3#16.7) | |
| K61-6 | reply | 61 | DBVO.12-MONATSFRIST-AB | | VB@V#3.12.5, (BP@13.3#16.1), (HINWEISE@1#chain) | |
| K61-7 | reply | 61 | DBVO.KZ-AK-AU | | VB@V#3.12.4 | |
| K62-1 | reply | 62 | DBID.REFERENZ-ID | | VB@V#3.19.3, (HINWEISE@1#chain) | |
| K62-2 | reply | 62 | DBEE.EEL-ENDE, DBEE.EEL-ENDE-GRUND | | VB@V#3.7.3, VB@V#3.7.4 | |
| E-1 | efz | 01 | DBAL.DATUM-EGZBIS | efz_days | VB@V#3.4.3, (HINWEISE@1#chain) | |
| E-2 | efz | 01, 88 | DBAL.DATUM-EGZBIS, DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG | efz_days | GG@13.1#2.5, (BP@13.3#23) | |
| E-3 | efz | 61 | DBVO.KZ-AK-AU, DBVO.KZ-AU | | VB@V#3.12.4, VB@V#3.12.12 | |
| C-1 | chain | 01, 41, 88 | DSLW.DATENSATZ-ID | | VB@V#3.1.11 | |
| C-2 | chain | 01, 41, 88 | DBID.AKTENZEICHEN-VERURSACHER, DBSD.AKTENZEICHEN-VERURSACHER | | VB@V#3.19.2, VB@V#3.20 | |
| C-3 | chain | 88 | DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG | | VB@V#3.20, GG@13.1#2.5 | |
| C-4 | chain | 88 | DBSD.VORNAME, DBSD.FAMILIENNAME | | VB@V#3.20 | |
| C-5 | chain | 01, 88 | DSLW.ABGABEGRUND | | GG@13.1#2.5 | |
| C-6 | chain | 62 | DBEE.EEL-ENDE | | VB@V#3.7.3 | |
| C-7 | chain | 61 | DBID.AKTENZEICHEN-VERURSACHER | | VB@V#3.19.2 | |
| C-8 | chain | 88 | DSLW.MM-SD | | VB@V#3.20, (BP@13.3#23) | |

Titles: copy the rule text from `03` sections 3 to 7, shortened to one line. Store the full text from `03` in `description`.

Nodes and edges: `Rule {key: id, title, description, kind, status}`, `Criterion {key: uuid, text}` (text from the BVORERK passage if present, else the rule title), `Rule -[:APPLIES_TO]-> MessageType`, `-[:CONSTRAINS]-> Field`, `-[:USES_PARAM]-> Parameter`, `-[:SOURCED_FROM]-> Passage`, `-[:IMPLEMENTS]-> Criterion`.

## 10. Step K7: spec changes

1. Load `kg/seed/spec_diff_13.3_13.4.json` (67 entries). For entry i create `Change {key: "VB-13.3-13.4-%03d" % i, tag, block, field, old (joined with "\n"), new (joined with "\n"), in_scope: false, label: "unknown", summary: null}`.
2. Link each raw change to passages: find the old text in `VB@13.3` passages and the new text in `VB@13.4` passages (substring match on the first 40 characters of the joined, cleaned lines). Edges `MODIFIES_OLD` and `MODIFIES_NEW` to the **narrowest** passage that contains it (part > field > block > section). If not found, link to the block passage `VB@V#3.x` by `block` (via the Record's section). If still nothing, no edge, warning.
3. Apply the curated layer `kg/seed/changes.yaml`. It names the in-scope changes and adds what the diff cannot know:

```yaml
changes:
  - key: VB-13.3-13.4-DBVO-chaining
    raw: [find the raw entry whose old text contains "nicht mindestens 6 Monate" and block DBVO]
    summary: 6-month chaining wording, "nicht mindestens" became "nicht mehr als"; a gap of exactly 6 months now chains
    label: editorial
    in_scope: true
    changes_param: [gap_inclusive]
    modifies_old: [VB@13.3#3.12/chaining]
    modifies_new: [VB@13.4#3.12/chaining]
  - key: VB-13.3-13.4-BBNR-VU
    summary: insurer replies carry the employer's BBNR-VU
    label: clarification
    in_scope: true
    changes_param: []
    modifies_old: [VB@13.3#3.1.10]
    modifies_new: [VB@13.4#3.1.10]
  - key: VB-13.3-13.4-DBID-AZVU
    summary: AKTENZEICHEN-VERURSACHER returned unchanged, blank if the employer sent none
    label: clarification
    in_scope: true
    modifies_old: [VB@13.3#3.19.2]
    modifies_new: [VB@13.4#3.19.2]
  - key: VB-13.3-13.4-DBSD-names
    summary: VORNAME and FAMILIENNAME of the 88 are the names in the cancelled record
    label: clarification
    in_scope: true
    modifies_old: [VB@13.3#3.20]
    modifies_new: [VB@13.4#3.20]
  - key: VB-13.3-13.4-DBEE-end
    summary: if benefit continues after employment ends, confirm only up to the end of employment
    label: clarification
    in_scope: true
    modifies_old: [VB@13.3#3.7.3]
    modifies_new: [VB@13.4#3.7.3]
  # out of scope, in_scope: false: seafarers (DBAE, DBFR, DBSF), DBAE BRUTTO-1 hourly workers, DBFR home care, DSLW ABRECHNUNGSPROGRAMM wording (04 section 2)
```

The curated change node gets edges `DERIVED_FROM` to its raw changes, plus `CHANGES_PARAM` and `MODIFIES_OLD` / `MODIFIES_NEW`. `raw` is resolved by the build script by searching the raw changes, not typed by hand.

In production the spec-update agent (`02`, M5) writes this curated layer itself as `draft`, and a human approves it. For the seed we write it by hand.

## 11. Step K8: test cases (`test_cases.yaml`)

All facts from `03` section 9. Each entry:

```yaml
test_cases:
  - id: peter-gap-exact
    kind: clone
    origin: builder
    status: approved
    hidden: false
    parent: peter
    targets: [R41-2, R41-3]
    steps: single           # "single" = only the 41 decision is graded; "chain" = full 7-message chain
    inputs:
      report_date: 2026-03-11
      employment_end: 2026-03-31
      current: {start: 2026-03-11, end: 2026-03-20, certified: true}
      priors:
        - {start: 2025-08-07, end: 2025-09-11, certified: true}
    expected:
      "13.3":     {send_41: false}
      "13.4":     {send_41: true, periods: [[2025-08-07, 2025-09-11]], total_days: 46}
      "sim-13.5": {send_41: true, periods: [[2025-08-07, 2025-09-11]], total_days: 46}
    sources: [VB@13.4#3.12/chaining]
```

Write all of these:

| id | kind | origin | parent | hidden | targets | steps |
|---|---|---|---|---|---|---|
| peter | reference | itsg | | false | R41-1..R41-6, F41-*, K61-*, K62-*, E-*, C-* | chain |
| peter-gap-exact | clone | builder | peter | false | R41-2, R41-3 | single |
| peter-gap-in | clone | builder | peter | false | R41-2, R41-3 | single |
| peter-gap-out | clone | builder | peter | false | R41-2, R41-3 | single |
| peter-b27, peter-b28, peter-b29, peter-b30 | clone | builder | peter | false | R41-4 | single |
| peter-noteless | clone | builder | peter | false | R41-1, R41-5 | single |
| peter-hidden | hidden | builder | peter | true | R41-1..R41-4 | single |
| peter-gap-exact-hidden | hidden | builder | peter-gap-exact | true | R41-2, R41-3 | single |
| bp-13-1 .. bp-13-5 | reference | beispielpapier | | false | 13-1: R41-1, R41-6; 13-2: R41-3; 13-3: R41-2; 13-4: R41-4; 13-5: R41-6 | single |
| ta-167, ta-168 | reference | pta | | false | none yet (inputs only, no solution available) | chain |

`R41-1..R41-6` means each rule id in the range; `F41-*` means all F41 rules. Expected values: copy them from the tables in `03` section 9, for `13.3`, `13.4` and `sim-13.5`. For `peter` set `sources: [HINWEISE@1#facts, HINWEISE@1#chain]` and also store the EFZ ends `{after_first_61: 2026-03-30, after_corrected_61: 2026-03-27}` and the chain `[41, 61, 01, 61, 88, 01, 62]`. For `ta-167` and `ta-168` store only `inputs.summary` (one line from PTA 5.14) and `sources: [PTA@2025-2026-v3#5.14]`; validation (section 12.2) allows them to have no targets.

Peter's priors: 2025-07-14 to 2025-07-15, 2025-10-01 to 2025-10-17, 2025-12-01 to 2025-12-03, 2026-03-01 to 2026-03-03 (all certified; the last one only on paper at the employer). The other clones change only what `03` section 9 says.

Nodes `TestCase {key: id, kind, origin, status, hidden, steps, inputs (JSON string), expected (JSON string)}`, edges `TARGETS -> Rule`, `CLONE_OF -> TestCase` (kind clone), `HIDDEN_OF -> TestCase` (kind hidden), `DESCRIBED_IN -> Passage` for its sources.

Hidden test cases are in the graph like the others. The API decides what a vendor may see (`02` section 6), not the graph.

## 12. Step K9: build, validate, load, embed

### 12.1 Build (`seed_graph.py`)

Read all seed files, `kg/build/passages.yaml`, the layouts and the diff into two lists:
- `nodes: [{label, key, props}]`
- `edges: [{type, from_label, from_key, to_label, to_key, props}]`

Write them to `kg/build/graph.json`. Print counts per label and per edge type.

Expected order of magnitude: Document 7, DocVersion 8 to 10, Passage 300 to 900, Record 20, Field about 330, MessageType 22, Rule 38, Criterion 4, Parameter 6, ParamValue 18, Change 67 + 5, TestCase 20.

### 12.2 Validate (`validate.py`, exit code 1 on any error)

| Check | Level |
|---|---|
| every edge's `from` and `to` node exists | error |
| every key matches its format in section 1.3 | error |
| every enum value is in section 1.4 | error |
| every rule has at least one `SOURCED_FROM` and one `APPLIES_TO` | error |
| every field a rule constrains exists in a layout | error (prints rule id and field) |
| every parameter has values for `13.3` and `13.4` | error |
| every test case targets at least one rule, except `origin: pta` | error |
| every passage key resolves to a DocVersion | error |
| the 5.2 checks on 3.12 pass | error |
| every in-scope change reaches at least one rule (via param or passage) | warning |
| a rule source in brackets (optional file) is missing | warning |
| passage with empty text | warning |

### 12.3 Load (`load.py`)

1. For each label: `CREATE CONSTRAINT <label>_key IF NOT EXISTS FOR (n:<Label>) REQUIRE n.key IS UNIQUE`
2. Nodes per label in batches of 500: `UNWIND $rows AS row MERGE (n:<Label> {key: row.key}) SET n += row.props`
3. Edges per type: `UNWIND $rows AS r MATCH (a:<From> {key: r.from}) MATCH (b:<To> {key: r.to}) MERGE (a)-[e:<TYPE>]->(b) SET e += r.props`
4. Labels and relationship types come from a whitelist in code (the tables in `07` section 3 plus `CARRIES` and `DERIVED_FROM`), never from input data.
5. Full-text index:
   ```
   CREATE FULLTEXT INDEX passage_text IF NOT EXISTS FOR (p:Passage) ON EACH [p.text, p.heading]
   OPTIONS {indexConfig: {`fulltext.analyzer`: 'german'}}
   ```
6. Delete nothing automatically. To rebuild from zero: `MATCH (n) DETACH DELETE n` by hand, then load.

### 12.4 Embed (`embed.py`)

1. For every Passage: input = `heading + "\n" + text`, cut to 24,000 characters.
2. Cache key = sha256 of the input. Look it up in `kg/build/embeddings.jsonl`; call OpenAI only on a miss (batches of 100, model from `OPENAI_EMBED_MODEL`, default `text-embedding-3-small`, 1536 dimensions).
3. Write vectors to `Passage.embedding`.
4. Vector index:
   ```
   CREATE VECTOR INDEX passage_embedding IF NOT EXISTS FOR (p:Passage) ON p.embedding
   OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}
   ```

Run order in `kg/build.py`: extract → build → validate → load → embed. Flags `--skip-embed` and `--skip-load` for offline work.

## 13. Step K10: queries behind the interface and the LLM tools

`kg/graph_backend.py` implements the interface in `02` section 5 with one Cypher query per method (the queries in `07` section 8 are the base). Each method is also exposed to the OpenAI agents as a tool with the same name and arguments (`02`, task M8.0).

| Method / tool | Returns | Must answer |
|---|---|---|
| `get_layout(record, version)` | Layout | `DBVO` fields in position order, repeating ones flagged |
| `get_rules(abgabegrund, version)` | list[Rule] with sources of that VB version only | `"41", "13.3"` → no `VB@13.4#...` source |
| `get_param(name, version=None, on_date=None)` | value | see tests |
| `get_passage(key)` | Passage | `VB@13.4#3.12/chaining` text |
| `search_passages(text, k=5)` | list[Passage] | vector search first, full-text as fallback; "Vorerkrankung 6 Monate" finds `3.12/chaining` in the top 3 |
| `get_versions(document)` | list[Version] | VB → 13.3, 13.4 with valid_from |
| `get_changes(document, old_version, new_version, in_scope_only=True)` | list[Change] | 5 curated in-scope changes |
| `get_affected_rules(change_keys)` | `{recompute, review, tests}` | section 14 |
| `get_test_cases(rule_id=None, include_hidden=False)` | list[TestCaseRef] | `R41-2` → peter, peter-gap-*, bp-13-3 (hidden only when asked) |
| `get_test_case(key)` | TestCase with inputs and expected per version | `peter-gap-exact` |
| `get_deviation_context(record, field, abgabegrund, version)` | rules, passages, precedents, flagged blocks | `DSLW, MM-ANSPRECH, "41"` → F41-3, DBAP (mandatory unknown), BP 13.1 if present |
| `add_precedent(p)` / `find_precedent(signature)` | | round trip |
| `subgraph(label, key, depth=1)` | nodes + edges | UI only, not a tool |

`get_affected_rules` tiers (07 section 7):
- `recompute` = Change → `CHANGES_PARAM` → Parameter ← `USES_PARAM` ← Rule
- `review` = Change → `MODIFIES_OLD|MODIFIES_NEW` → Passage ← `SOURCED_FROM` ← Rule, minus the recompute rules
- `tests` = TestCase → `TARGETS` → recompute rules

## 14. Step K11: tests (`tests/test_kg.py`)

Run every test against both backends (pytest parametrize over `KG_BACKEND`).

| Test | Expected |
|---|---|
| `get_param("gap_inclusive", on_date=2026-11-01)` | `False` |
| `get_param("gap_inclusive", on_date=2027-01-01)` | `True` |
| `get_param("min_total_days", version="sim-13.5")` | `28` |
| `get_param("min_total_days", on_date=2028-06-01)` | `30` (simulated never by date) |
| `get_layout("DBVO", "13.4")` | 15 fields, `BEGINN-AU` repeating |
| `get_rules("41", "13.3")` | 18 rules (R41-1..6, F41-1..10, C-1, C-2), no source with `VB@13.4` |
| `get_affected_rules(["VB-13.3-13.4-DBVO-chaining"])` | recompute = {R41-2, R41-3}; tests = {peter, peter-gap-exact, peter-gap-in, peter-gap-out, peter-hidden, peter-gap-exact-hidden, bp-13-2, bp-13-3}; review contains no R41-2 / R41-3 |
| `get_test_case("peter-gap-exact").expected` | 13.3 no 41, 13.4 41 |
| `get_passage("VB@13.4#3.12/chaining")` | contains `nicht mehr als 6 Monate` |
| `get_passage("VB@13.4#3.12/insurer")` | contains `nicht mindestens 6 Monate` |
| `add_precedent` then `find_precedent` with the same signature | returns it |
| build + load twice | identical counts |
| seed with a typo in a rule field | validation fails naming the rule and the field |

## 15. Handover to the rest of the backend

- The interface (`kg/interface.py`) and the Pydantic models are shared with the engine. Agree on them first (half a day), then build behind them.
- The YAML backend is the reference and works without Neo4j and without OpenAI (search falls back to plain substring search).
- Never change a key format or enum value without updating this file and telling the team.
