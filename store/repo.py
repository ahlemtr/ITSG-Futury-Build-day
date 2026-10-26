"""App data store (P7.1). `PgRepo` on Postgres (psycopg v3), `MemoryRepo` with the same methods
for tests and for running without a database. `get_repo()` picks Postgres when DATABASE_URL is set."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from engine.model import CheckResult, CriterionDraft, Deviation, TestCase

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


class SubmissionFile(BaseModel):
    name: str
    path: str
    sha256: str


class Submission(BaseModel):
    id: str
    test_case_id: str
    vendor: str | None = None
    product_id: str | None = None
    valid_on: date | None = None
    rule_set_version: str | None = None
    status: str = "accepted"
    files: list[SubmissionFile] = []
    issues: list[dict] = []
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str | None = None  # seed description


class MemoryRepo:
    def __init__(self) -> None:
        self.test_cases: dict[str, TestCase] = {}
        self.approvals: list[dict] = []
        self.submissions: dict[str, Submission] = {}
        self.checks: dict[str, CheckResult] = {}
        self.runs: dict[str, dict] = {}
        self.reports: dict[str, dict] = {}
        self.criteria: dict[str, CriterionDraft] = {}

    # test cases
    def upsert_test_case(self, tc: TestCase) -> None:
        self.test_cases[tc.id] = tc.model_copy(deep=True)

    def get_test_case(self, id_: str) -> TestCase | None:
        tc = self.test_cases.get(id_)
        return tc.model_copy(deep=True) if tc else None

    def list_test_cases(self, kind: str | None = None, hidden: bool | None = None) -> list[TestCase]:
        return [t for t in self.test_cases.values()
                if (kind is None or t.kind == kind) and (hidden is None or t.hidden == hidden)]

    def approve(self, id_: str, approver: str, decision: str) -> TestCase:
        tc = self.test_cases[id_]
        tc.status = "approved" if decision == "approved" else "rejected"
        self.approvals.append({"test_case_id": id_, "approver": approver, "decision": decision,
                               "at": datetime.now(UTC).isoformat()})
        return tc

    # submissions and checks
    def add_submission(self, s: Submission) -> None:
        self.submissions[s.id] = s

    def get_submission(self, id_: str) -> Submission | None:
        return self.submissions.get(id_)

    def list_submissions(self, test_case_id: str | None = None) -> list[Submission]:
        return [s for s in self.submissions.values() if test_case_id is None or s.test_case_id == test_case_id]

    def save_check(self, submission_id: str, res: CheckResult) -> None:
        self.checks[submission_id] = res
        s = self.submissions.get(submission_id)
        if s:
            s.rule_set_version = res.version

    def get_check(self, submission_id: str) -> CheckResult | None:
        return self.checks.get(submission_id)

    def find_deviation(self, dev_id: str) -> tuple[str, Deviation] | None:
        for sid, res in self.checks.items():
            for d in res.deviations:
                if d.id == dev_id:
                    return sid, d
        return None

    def update_deviation(self, submission_id: str, d: Deviation) -> None:
        res = self.checks[submission_id]
        res.deviations = [d if x.id == d.id else x for x in res.deviations]

    # runs, reports, criteria
    def save_run(self, run_id: str, doc: dict) -> None:
        self.runs[run_id] = doc

    def get_run(self, run_id: str) -> dict | None:
        return self.runs.get(run_id)

    def save_report(self, submission_id: str, signed: dict) -> None:
        self.reports[submission_id] = signed

    def get_report(self, submission_id: str) -> dict | None:
        return self.reports.get(submission_id)

    def save_criterion(self, c: CriterionDraft) -> None:
        self.criteria[c.id] = c

    def get_criterion(self, id_: str) -> CriterionDraft | None:
        return self.criteria.get(id_)

    def list_criteria(self) -> list[CriterionDraft]:
        return list(self.criteria.values())


def _j(model: BaseModel | dict) -> str:
    return json.dumps(model.model_dump(mode="json") if isinstance(model, BaseModel) else model, default=str)


class PgRepo:
    """Same methods as MemoryRepo on Postgres. Whole documents in jsonb, key columns alongside."""

    def __init__(self, url: str):
        import psycopg

        self.conn = psycopg.connect(url, autocommit=True)

    def apply_schema(self) -> None:
        self.conn.execute(SCHEMA.read_text(encoding="utf-8"))

    def _one(self, sql: str, *args: Any):
        return self.conn.execute(sql, args).fetchone()

    def _all(self, sql: str, *args: Any):
        return self.conn.execute(sql, args).fetchall()

    def upsert_test_case(self, tc: TestCase) -> None:
        self.conn.execute(
            """INSERT INTO test_case (id, parent_id, branch_point, kind, origin, status, hidden, target_rules, scenario)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET parent_id=EXCLUDED.parent_id, branch_point=EXCLUDED.branch_point,
               kind=EXCLUDED.kind, origin=EXCLUDED.origin, status=EXCLUDED.status, hidden=EXCLUDED.hidden,
               target_rules=EXCLUDED.target_rules, scenario=EXCLUDED.scenario""",
            (tc.id, tc.parent, tc.branch_point, tc.kind, tc.origin, tc.status, tc.hidden, tc.targets, _j(tc)))

    def get_test_case(self, id_: str) -> TestCase | None:
        row = self._one("SELECT scenario FROM test_case WHERE id=%s", id_)
        return TestCase.model_validate(row[0]) if row else None

    def list_test_cases(self, kind: str | None = None, hidden: bool | None = None) -> list[TestCase]:
        rows = self._all("""SELECT scenario FROM test_case WHERE (%s::text IS NULL OR kind=%s)
                            AND (%s::boolean IS NULL OR hidden=%s) ORDER BY id""", kind, kind, hidden, hidden)
        return [TestCase.model_validate(r[0]) for r in rows]

    def approve(self, id_: str, approver: str, decision: str) -> TestCase:
        tc = self.get_test_case(id_)
        if tc is None:
            raise KeyError(id_)
        tc.status = "approved" if decision == "approved" else "rejected"
        self.upsert_test_case(tc)
        self.conn.execute("INSERT INTO approval (test_case_id, approver, decision) VALUES (%s,%s,%s)",
                          (id_, approver, decision))
        return tc

    def add_submission(self, s: Submission) -> None:
        self.conn.execute(
            """INSERT INTO submission (id, test_case_id, vendor, product_id, rule_set_version, valid_on, status, doc)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET doc=EXCLUDED.doc, status=EXCLUDED.status""",
            (s.id, s.test_case_id, s.vendor, s.product_id, s.rule_set_version, s.valid_on, s.status, _j(s)))
        self.conn.execute("DELETE FROM submission_file WHERE submission_id=%s", (s.id,))
        for n, f in enumerate(s.files):
            self.conn.execute("INSERT INTO submission_file VALUES (%s,%s,%s,%s,%s,%s)",
                              (f"{s.id}-{n}", s.id, n, f.name, f.path, f.sha256))

    def get_submission(self, id_: str) -> Submission | None:
        row = self._one("SELECT doc FROM submission WHERE id=%s", id_)
        return Submission.model_validate(row[0]) if row else None

    def list_submissions(self, test_case_id: str | None = None) -> list[Submission]:
        rows = self._all("SELECT doc FROM submission WHERE (%s::text IS NULL OR test_case_id=%s) ORDER BY id",
                         test_case_id, test_case_id)
        return [Submission.model_validate(r[0]) for r in rows]

    def save_check(self, submission_id: str, res: CheckResult) -> None:
        self.conn.execute("""INSERT INTO check_result VALUES (%s,%s)
                             ON CONFLICT (submission_id) DO UPDATE SET doc=EXCLUDED.doc""", (submission_id, _j(res)))
        self.conn.execute("UPDATE submission SET rule_set_version=%s WHERE id=%s", (res.version, submission_id))
        self.conn.execute("DELETE FROM verdict WHERE submission_id=%s", (submission_id,))
        for d in res.deviations:
            self.conn.execute(
                "INSERT INTO verdict VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                (d.id, submission_id, d.rule, d.step, d.record, d.field, d.label,
                 None if d.expected is None else str(d.expected), None if d.actual is None else str(d.actual),
                 d.explanation, d.resolved_by, d.precedent_key,
                 _j(d.ai_proposal) if d.ai_proposal else None, _j(d)))

    def get_check(self, submission_id: str) -> CheckResult | None:
        row = self._one("SELECT doc FROM check_result WHERE submission_id=%s", submission_id)
        return CheckResult.model_validate(row[0]) if row else None

    def find_deviation(self, dev_id: str) -> tuple[str, Deviation] | None:
        row = self._one("SELECT submission_id, doc FROM verdict WHERE id=%s", dev_id)
        return (row[0], Deviation.model_validate(row[1])) if row else None

    def update_deviation(self, submission_id: str, d: Deviation) -> None:
        res = self.get_check(submission_id)
        res.deviations = [d if x.id == d.id else x for x in res.deviations]
        self.save_check(submission_id, res)

    def save_run(self, run_id: str, doc: dict) -> None:
        self.conn.execute("""INSERT INTO run VALUES (%s,%s,%s,%s,%s,%s)
                             ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, doc=EXCLUDED.doc""",
                          (run_id, doc["test_case"]["id"], doc.get("vendor"), doc["valid_on"], doc["status"], _j(doc)))

    def get_run(self, run_id: str) -> dict | None:
        row = self._one("SELECT doc FROM run WHERE id=%s", run_id)
        return row[0] if row else None

    def save_report(self, submission_id: str, signed: dict) -> None:
        sig = signed["signature"]
        self.conn.execute("""INSERT INTO report VALUES (%s,%s,%s,%s) ON CONFLICT (submission_id)
                             DO UPDATE SET json_sha256=EXCLUDED.json_sha256, signature=EXCLUDED.signature,
                             doc=EXCLUDED.doc""", (submission_id, sig["json_sha256"], sig["value"], _j(signed)))

    def get_report(self, submission_id: str) -> dict | None:
        row = self._one("SELECT doc FROM report WHERE submission_id=%s", submission_id)
        return row[0] if row else None

    def save_criterion(self, c: CriterionDraft) -> None:
        self.conn.execute("""INSERT INTO criterion_draft VALUES (%s,%s,%s)
                             ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, doc=EXCLUDED.doc""",
                          (c.id, c.status, _j(c)))

    def get_criterion(self, id_: str) -> CriterionDraft | None:
        row = self._one("SELECT doc FROM criterion_draft WHERE id=%s", id_)
        return CriterionDraft.model_validate(row[0]) if row else None

    def list_criteria(self) -> list[CriterionDraft]:
        return [CriterionDraft.model_validate(r[0]) for r in self._all("SELECT doc FROM criterion_draft ORDER BY id")]


def get_repo():
    url = os.environ.get("DATABASE_URL")
    if url:
        repo = PgRepo(url)
        repo.apply_schema()
        return repo
    return MemoryRepo()
