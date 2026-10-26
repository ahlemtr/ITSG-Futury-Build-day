# Data model (Postgres on the team VM)

App data only. Spec versions, passages, rules, parameters, criteria and precedents live behind `kg/` (`07_KNOWLEDGE_GRAPH.md`); tables below reference them by key (`rule_id`, `precedent_key`).

```mermaid
erDiagram
    TEST_CASE ||--o{ TEST_CASE : "cloned from"
    TEST_CASE ||--o{ TEST_STEP : has
    TEST_STEP ||--o{ EXPECTED_FIELD : expects
    TEST_CASE ||--o{ RUN : "run as"
    RUN ||--o{ RUN_STEP : has
    TEST_CASE ||--o{ SUBMISSION : "checked by"
    SUBMISSION ||--o{ SUBMISSION_FILE : contains
    SUBMISSION ||--o{ VERDICT : produces
    SUBMISSION ||--o| REPORT : "signed as"
    TEST_CASE ||--o{ APPROVAL : "approved by"

    TEST_CASE {
        text id PK
        text parent_id FK
        date branch_point
        text kind
        text origin
        text status
        bool hidden
        text catalogue_version
        text_array target_rules
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
        text rule_id
        int step_seq
        text record
        text field
        text outcome
        text expected
        text actual
        text explanation
        text resolved_by
        text precedent_key
        jsonb ai_proposal
    }
    RUN {
        uuid id PK
        text test_case_id FK
        text vendor
        date valid_on
        text status
    }
    RUN_STEP {
        uuid run_id FK
        int round
        text submitted_path
        text reply_path
        text verdict
    }
    REPORT {
        uuid submission_id FK
        text json_sha256
        text signature
    }
    APPROVAL {
        text test_case_id FK
        text approver
        text decision
        timestamptz at
    }
```

`compare_mode`: compare, rule, ignore. `outcome` (per deviation): exact_match, correct_variant, bug, invalid, unclear. `kind`: reference, clone, hidden. `origin`: itsg, beispielpapier, builder. `status`: draft, approved, rejected. `resolved_by`: diff, catalogue, rules, ai_proposal, advisor. `precedent_key`: record + field + kind of deviation, the key of the precedent in `kg/`.
