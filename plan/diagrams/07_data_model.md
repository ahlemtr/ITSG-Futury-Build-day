# Data model (Supabase Postgres)

```mermaid
erDiagram
    SPEC_VERSION ||--o{ SPEC_SECTION : contains
    SPEC_SECTION ||--o{ RULE : "source of"
    RULE ||--o{ RULE_PARAM : has
    RULE }o--o{ ITSG_CRITERION : implements
    TEST_CASE ||--o{ TEST_CASE : "cloned from"
    TEST_CASE ||--o{ TEST_STEP : has
    TEST_STEP ||--o{ EXPECTED_FIELD : expects
    TEST_CASE }o--o{ RULE : targets
    TEST_CASE ||--o{ SUBMISSION : "checked by"
    SUBMISSION ||--o{ SUBMISSION_FILE : contains
    SUBMISSION ||--o{ VERDICT : produces
    VERDICT }o--|| RULE : "about"
    SUBMISSION ||--o| REPORT : "signed as"
    TEST_CASE ||--o{ APPROVAL : "approved by"
    VERDICT }o--o| PRECEDENT : "resolved by"

    SPEC_VERSION {
        text id PK
        text document
        text version
        date valid_from
    }
    SPEC_SECTION {
        text id PK
        text version_id FK
        text section_no
        int page
        text body
        text body_hash
    }
    RULE {
        text id PK
        text section_id FK
        text abgabegrund
        text title
        text status
        date valid_from
        date valid_to
    }
    RULE_PARAM {
        text rule_id FK
        text name
        text value
        date valid_from
    }
    ITSG_CRITERION {
        uuid id PK
        text text
    }
    TEST_CASE {
        text id PK
        text parent_id FK
        date branch_point
        text kind
        bool hidden
        text catalogue_version
        jsonb scenario
    }
    TEST_STEP {
        text id PK
        text test_case_id FK
        int seq
        text actor
        text abgabegrund
        text file_ref
    }
    EXPECTED_FIELD {
        text step_id FK
        text record
        text field
        text expected
        text compare_mode
    }
    SUBMISSION {
        uuid id PK
        text test_case_id FK
        text vendor
        text product_id
        text rule_set_version
    }
    SUBMISSION_FILE {
        uuid id PK
        uuid submission_id FK
        int seq
        text path
        text sha256
    }
    VERDICT {
        uuid id PK
        uuid submission_id FK
        text rule_id FK
        int step_seq
        text outcome
        text expected
        text actual
        text explanation
    }
    REPORT {
        uuid submission_id FK
        text json_sha256
        text signature
    }
    PRECEDENT {
        uuid id PK
        text signature
        text label
        text reason
        text advisor
        timestamptz at
    }
    APPROVAL {
        text test_case_id FK
        text approver
        text decision
        timestamptz at
    }
```

`compare_mode`: compare, rule, ignore. `outcome` (per deviation): exact_match, correct_variant, bug, invalid, unclear. `kind`: reference, boundary, clone, hidden. `PRECEDENT.signature`: record + field + kind of deviation, used by the known-variant catalogue.
VERDICT also stores `resolved_by` (diff, catalogue, rules, ai_proposal, advisor) and `ai_proposal` (JSON).
