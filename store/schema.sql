-- App data only (plan/diagrams/07_data_model.md). Spec versions, passages, rules, parameters,
-- criteria and precedents live behind kg/. Pydantic documents are kept whole in jsonb columns
-- next to the columns the diagram names, so the engine models round-trip without mapping code.

CREATE TABLE IF NOT EXISTS test_case (
    id                text PRIMARY KEY,
    parent_id         text,
    branch_point      date,
    kind              text NOT NULL CHECK (kind IN ('reference', 'clone', 'hidden')),
    origin            text NOT NULL CHECK (origin IN ('itsg', 'beispielpapier', 'builder', 'pta')),
    status            text NOT NULL CHECK (status IN ('draft', 'approved', 'rejected')),
    hidden            boolean NOT NULL DEFAULT false,
    catalogue_version text,
    target_rules      text[] NOT NULL DEFAULT '{}',
    scenario          jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS test_step (
    id           text PRIMARY KEY,
    test_case_id text NOT NULL REFERENCES test_case(id) ON DELETE CASCADE,
    seq          int NOT NULL,
    actor        text NOT NULL,
    abgabegrund  text NOT NULL,
    file_ref     text
);

CREATE TABLE IF NOT EXISTS expected_field (
    step_id      text NOT NULL REFERENCES test_step(id) ON DELETE CASCADE,
    record       text NOT NULL,
    field        text NOT NULL,
    expected     text,
    compare_mode text NOT NULL CHECK (compare_mode IN ('compare', 'rule', 'ignore'))
);

CREATE TABLE IF NOT EXISTS submission (
    id               text PRIMARY KEY,
    test_case_id     text NOT NULL,
    vendor           text,
    product_id       text,
    rule_set_version text,
    valid_on         date,
    status           text NOT NULL DEFAULT 'accepted',
    created          timestamptz NOT NULL DEFAULT now(),
    doc              jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS submission_file (
    id            text PRIMARY KEY,
    submission_id text NOT NULL REFERENCES submission(id) ON DELETE CASCADE,
    seq           int NOT NULL,
    name          text NOT NULL,
    path          text NOT NULL,
    sha256        text NOT NULL
);

-- one row per deviation of the latest check of a submission
CREATE TABLE IF NOT EXISTS verdict (
    id            text PRIMARY KEY,
    submission_id text NOT NULL REFERENCES submission(id) ON DELETE CASCADE,
    rule_id       text,
    step_seq      int,
    record        text,
    field         text,
    outcome       text NOT NULL CHECK (outcome IN ('exact_match', 'correct_variant', 'bug', 'invalid', 'unclear')),
    expected      text,
    actual        text,
    explanation   text,
    resolved_by   text,
    precedent_key text,
    ai_proposal   jsonb,
    doc           jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS check_result (
    submission_id text PRIMARY KEY REFERENCES submission(id) ON DELETE CASCADE,
    doc           jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS run (
    id           text PRIMARY KEY,
    test_case_id text NOT NULL,
    vendor       text,
    valid_on     date NOT NULL,
    status       text NOT NULL,
    doc          jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS run_step (
    run_id         text NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    round          int NOT NULL,
    submitted_path text,
    reply_path     text,
    verdict        text
);

CREATE TABLE IF NOT EXISTS report (
    submission_id text PRIMARY KEY REFERENCES submission(id) ON DELETE CASCADE,
    json_sha256   text NOT NULL,
    signature     text NOT NULL,
    doc           jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS approval (
    test_case_id text NOT NULL,
    approver     text NOT NULL,
    decision     text NOT NULL,
    at           timestamptz NOT NULL DEFAULT now()
);

-- criterion drafts of the requirements-to-criteria pipeline (P8.2)
CREATE TABLE IF NOT EXISTS criterion_draft (
    id     text PRIMARY KEY,
    status text NOT NULL DEFAULT 'draft',
    doc    jsonb NOT NULL
);

-- Spec upload (SPEC_UPDATE_WORKFLOW.md): one row per uploaded document version and its pipeline job
CREATE TABLE IF NOT EXISTS ingest_job (
    id         text PRIMARY KEY,
    document   text NOT NULL,
    version    text NOT NULL,
    status     text NOT NULL,          -- running / done / failed
    created    timestamptz NOT NULL DEFAULT now(),
    doc        jsonb NOT NULL          -- file, sha256, valid_from, stages with counts, result
);

-- What each upload or decision added to the knowledge graph (knowledge graph tab)
CREATE TABLE IF NOT EXISTS kg_event (
    id    serial PRIMARY KEY,
    at    timestamptz NOT NULL DEFAULT now(),
    kind  text NOT NULL,               -- baseline / spec_upload / precedent / tests
    doc   jsonb NOT NULL
);

-- Calendar (HANDOUT agenda 1): vendor companies and the deadlines that come from events (test run rounds).
-- Rule-set deadlines (recertification, permanent test cases, catalogue, switch date) are derived on read.
CREATE TABLE IF NOT EXISTS company (
    id   text PRIMARY KEY,
    name text NOT NULL,
    doc  jsonb NOT NULL                -- product, certified_until, certified_for
);

CREATE TABLE IF NOT EXISTS deadline (
    id         text PRIMARY KEY,
    company_id text,                   -- NULL = ITSG
    kind       text NOT NULL,          -- round
    due        date NOT NULL,
    done       boolean NOT NULL DEFAULT false,
    doc        jsonb NOT NULL
);
