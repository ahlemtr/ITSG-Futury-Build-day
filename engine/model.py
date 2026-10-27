"""Shared Pydantic models (02 section 5). The first part is what the knowledge graph interface returns;
the second part holds the engine models (parsed records, traces, deviations, criteria)."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

RuleKind = Literal["domain", "format", "reply", "chain", "efz", "calculation"]
DeviationKind = Literal[
    "value_differs", "missing_block", "extra_block", "missing_message", "extra_message",
    "missing_group", "extra_group", "order_differs",
]


class FieldDef(BaseModel):
    key: str  # RECORD.NAME, repeating suffix removed
    record: str
    name: str
    layout_name: str  # as in the layout, e.g. BEGINN-AU-{nn}
    start: int
    end: int
    length: int
    type: Literal["an", "n"]
    required: Literal["M", "m"]
    format: str | None = None
    constant: str | None = None
    values: dict[str, str] | None = None
    repeating: bool = False
    offset_in_group: int | None = None
    status: Literal["extracted", "inferred", "partial", "missing"]
    compare_mode: Literal["compare", "rule", "ignore"] = "compare"
    compare_rule: str | None = None
    order: int
    definition_source: str | None = None


class Layout(BaseModel):
    record: str
    title: str
    section: str
    page: int | None = None
    fixed_length: int
    status: Literal["extracted", "inferred", "partial", "missing"]
    version: str
    fields: list[FieldDef]


class SpecRef(BaseModel):
    doc: str
    version: str
    section: str
    part: str | None = None

    @property
    def key(self) -> str:
        return f"{self.doc}@{self.version}#{self.section}" + (f"/{self.part}" if self.part else "")


class Passage(BaseModel):
    key: str
    doc: str
    version: str
    section: str
    part: str | None = None
    heading: str = ""
    text: str = ""
    page: int | None = None
    field: str | None = None
    snippet: str | None = None  # search results only: the sentence that matched (W7)


class Rule(BaseModel):
    id: str
    title: str
    description: str = ""
    kind: RuleKind
    status: Literal["approved", "draft"]
    criterion: str | None = None
    applies_to: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    params: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class Version(BaseModel):
    document: str
    version: str
    published: dt.date | None = None
    valid_from: dt.date | None = None
    file: str | None = None
    succeeds: str | None = None


class Change(BaseModel):
    key: str
    document: str
    old_version: str
    new_version: str
    tag: Literal["replace", "insert", "delete"]
    block: str | None = None
    field: str | None = None
    old: str = ""
    new: str = ""
    in_scope: bool = False
    label: Literal["editorial", "clarification", "law_change", "unknown"] = "unknown"
    summary: str | None = None
    curated: bool = False
    derived_from: list[str] = Field(default_factory=list)
    changes_param: list[str] = Field(default_factory=list)
    modifies_old: list[str] = Field(default_factory=list)
    modifies_new: list[str] = Field(default_factory=list)


class TestCaseRef(BaseModel):
    __test__ = False  # not a pytest class

    key: str
    kind: Literal["reference", "clone", "hidden"]
    origin: Literal["itsg", "beispielpapier", "builder", "pta"]
    status: Literal["draft", "approved", "rejected"]
    hidden: bool = False
    steps: Literal["single", "chain"]
    parent: str | None = None
    targets: list[str] = Field(default_factory=list)


class TestCase(TestCaseRef):
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)  # per version: "13.3", "13.4", "sim-13.5"
    sources: list[str] = Field(default_factory=list)


class Impact(BaseModel):
    recompute: list[Rule] = Field(default_factory=list)  # rules whose parameter changed
    review: list[Rule] = Field(default_factory=list)  # rules that only cite a changed passage
    tests: list[TestCaseRef] = Field(default_factory=list)  # test cases targeting the recompute rules


class Precedent(BaseModel):
    key: str = ""  # signature ABGABEGRUND|FIELD|KIND, e.g. 41|DSLW.MM-ANSPRECH|missing_block
    abgabegrund: str
    field: str
    kind: DeviationKind
    verdict: Literal["correct_variant", "bug", "invalid"]
    reason: str = ""
    advisor: str | None = None
    decided: dt.date | None = None
    justified_by: list[str] = Field(default_factory=list)  # rule ids or passage keys

    @model_validator(mode="after")
    def _key(self) -> Precedent:
        signature = f"{self.abgabegrund}|{self.field}|{self.kind}"
        if not self.key:
            self.key = signature
        elif self.key != signature:
            raise ValueError(f"precedent key {self.key!r} does not match its signature {signature!r}")
        return self


class FlaggedBlock(BaseModel):
    record: str
    flag: str
    mandatory: bool | Literal["unknown"]


class DeviationContext(BaseModel):
    record: str
    field: str  # field key
    abgabegrund: str
    version: str
    rules: list[Rule] = Field(default_factory=list)
    passages: list[Passage] = Field(default_factory=list)
    precedents: list[Precedent] = Field(default_factory=list)
    flagged_blocks: list[FlaggedBlock] = Field(default_factory=list)


class GraphNode(BaseModel):
    label: str
    key: str
    props: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    type: str
    from_label: str
    from_key: str
    to_label: str
    to_key: str
    props: dict[str, Any] = Field(default_factory=dict)


class Graph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# =====================================================================================================
# Engine models (parser, rules engine, checker, builder, criteria). Not part of the KG interface.
# =====================================================================================================

Label = Literal["exact_match", "correct_variant", "bug", "invalid", "unclear"]
ResolvedBy = Literal["diff", "catalogue", "rules", "ai_proposal", "advisor"]
TestStatus = Literal["draft", "approved", "rejected"]

# worst first (05 section 5)
LABEL_ORDER: list[str] = ["invalid", "bug", "unclear", "correct_variant", "exact_match"]

REPEAT_SUFFIX = re.compile(r"-(\{nn\}|\d+)$")


def base_field_name(name: str) -> str:
    """BEGINN-AU-{nn} and BEGINN-AU-1 -> BEGINN-AU (08 section 1.3)."""
    return REPEAT_SUFFIX.sub("", name)


# ---------------------------------------------------------------- typed test case


class AuPeriod(BaseModel):
    start: dt.date
    end: dt.date | None = None  # None = open end (current AU only)
    certified: bool = True


class TestInputs(BaseModel):
    __test__ = False

    report_date: dt.date | None = None
    employment_end: dt.date | None = None
    current: AuPeriod | None = None
    priors: list[AuPeriod] = Field(default_factory=list)
    summary: str | None = None


class ExpectedOutcome(BaseModel):
    send_41: bool
    periods: list[tuple[dt.date, dt.date]] = Field(default_factory=list)
    total_days: int | None = None


class Case(BaseModel):
    """A test case as the engine uses it: typed inputs and expectations. Built from the KG's
    TestCase (Case.from_kb) or by the builder (drafts), stored in the app store."""

    id: str
    kind: Literal["reference", "clone", "hidden"]
    origin: Literal["itsg", "beispielpapier", "builder", "pta"]
    status: TestStatus = "approved"
    hidden: bool = False
    parent: str | None = None
    targets: list[str] = Field(default_factory=list)
    steps: Literal["single", "chain"] = "single"
    inputs: TestInputs
    expected: dict[str, ExpectedOutcome] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    branch_point: dt.date | None = None

    @classmethod
    def from_kb(cls, tc: TestCase) -> Case:
        return cls(id=tc.key, kind=tc.kind, origin=tc.origin, status=tc.status, hidden=tc.hidden, parent=tc.parent,
                   targets=tc.targets, steps=tc.steps, inputs=TestInputs.model_validate(tc.inputs),
                   expected={v: ExpectedOutcome.model_validate(e) for v, e in tc.expected.items()},
                   sources=tc.sources)

    def to_kb(self) -> TestCase:
        return TestCase(key=self.id, kind=self.kind, origin=self.origin, status=self.status, hidden=self.hidden,
                        steps=self.steps, parent=self.parent, targets=self.targets,
                        inputs=self.inputs.model_dump(mode="json"),
                        expected={v: e.model_dump(mode="json") for v, e in self.expected.items()},
                        sources=self.sources)


# ---------------------------------------------------------------- records (parser output)


class ParseIssue(BaseModel):
    record: str
    field: str | None = None
    pos: int | None = None  # 1-based character position in the line
    message: str
    line: int | None = None  # 1-based line number in the file


class FieldValue(BaseModel):
    name: str
    raw: str
    value: Any = None
    pos: int  # 1-based position in the line


class Block(BaseModel):
    record: str
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    groups: list[dict[str, FieldValue]] = Field(default_factory=list)
    pos: int = 1
    length: int = 0


class Record(BaseModel):
    """One line of a file. DSLW lines are parsed; envelope lines (VOSZ, DSKO, NCSZ) kept raw."""

    kind: str
    line_no: int
    raw: str
    newline: str = ""
    head: dict[str, FieldValue] = Field(default_factory=dict)
    blocks: dict[str, Block] = Field(default_factory=dict)
    tail: str = ""  # unparsed remainder after an issue

    def get(self, key: str) -> Any:
        """DSLW.ABGABEGRUND, DBVO.AU-AB-AG -> typed value (None if absent)."""
        rec, name = key.split(".", 1)
        fv = self.head.get(name) if rec == "DSLW" else (self.blocks[rec].fields.get(name) if rec in self.blocks else None)
        return fv.value if fv else None

    @property
    def abgabegrund(self) -> str | None:
        fv = self.head.get("ABGABEGRUND")
        return fv.raw if fv else None

    @property
    def dsid(self) -> str | None:
        return self.get("DSLW.DATENSATZ-ID")

    @property
    def periods(self) -> list[tuple[dt.date | None, dt.date | None]]:
        if "DBVO" not in self.blocks:
            return []
        return [(g["BEGINN-AU"].value, g["ENDE-AU"].value) for g in self.blocks["DBVO"].groups]

    def values(self) -> dict[str, Any]:
        """Flat typed view: DSLW fields, then BLOCK.FIELD, groups as BLOCK.FIELD-n."""
        out: dict[str, Any] = {f"DSLW.{k}": v.value for k, v in self.head.items()}
        for b in self.blocks.values():
            out.update({f"{b.record}.{k}": v.value for k, v in b.fields.items()})
            for n, g in enumerate(b.groups, 1):
                out.update({f"{b.record}.{k}-{n}": v.value for k, v in g.items()})
        return out


class ParsedFile(BaseModel):
    records: list[Record] = Field(default_factory=list)
    issues: list[ParseIssue] = Field(default_factory=list)
    encoding: str = "utf-8"

    @property
    def messages(self) -> list[Record]:
        return [r for r in self.records if r.kind == "DSLW"]


# ---------------------------------------------------------------- rules engine


class Trace(BaseModel):
    rules: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)  # rule ids whose condition does not hold

    def add(self, rule: str, step: str, ok: bool = True) -> None:
        if rule not in self.rules:
            self.rules.append(rule)
        self.steps.append(f"{rule}: {step}")
        if not ok and rule not in self.failed:
            self.failed.append(rule)


class Decision41(BaseModel):
    send: bool
    chain: list[AuPeriod] = Field(default_factory=list)
    total_days: int | None = None
    trace: Trace


class RuleResult(BaseModel):
    rule: str
    ok: bool
    field: str | None = None  # RECORD.FIELD the result is about
    message: str
    expected: Any = None
    actual: Any = None
    trace: Trace | None = None


# ---------------------------------------------------------------- expected chains


class ExpectedMessage(BaseModel):
    step: int  # 1-based position in the chain
    round: int
    actor: Literal["employer", "insurer"]
    abgabegrund: str
    head: dict[str, Any]  # DSLW field -> value (writer form)
    blocks: dict[str, dict[str, Any]]  # block -> field -> value, DBVO has "groups": [ {...} ]
    note: str | None = None


# ---------------------------------------------------------------- checker


class AiProposal(BaseModel):
    proposal: Literal["likely_variant", "likely_bug", "unclear"]
    reasoning: str
    citations: list[str]
    confidence: float


class Deviation(BaseModel):
    id: str = ""
    step: int | None = None
    abgabegrund: str | None = None
    record: str
    field: str | None = None
    expected: Any = None
    actual: Any = None
    kind: DeviationKind
    label: Label = "unclear"
    rule: str | None = None
    criterion: str | None = None
    sources: list[str] = Field(default_factory=list)
    explanation: str = ""
    resolved_by: ResolvedBy | None = None
    precedent_key: str | None = None
    ai_proposal: AiProposal | None = None

    @property
    def field_key(self) -> str:
        return f"{self.record}.{self.field}" if self.field else self.record

    @property
    def signature(self) -> str:
        return f"{self.abgabegrund or ''}|{self.field_key}|{self.kind}"


class CheckResult(BaseModel):
    test_case_id: str
    valid_on: dt.date
    version: str
    label: Label
    deviations: list[Deviation] = Field(default_factory=list)
    parse_issues: list[ParseIssue] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    resolved_by: dict[str, int] = Field(default_factory=dict)
    expected_messages: int = 0
    actual_messages: int = 0


# ---------------------------------------------------------------- criteria pipeline (P8.2)


class RequirementSentence(BaseModel):
    passage_key: str
    quote: str


class ParamDraft(BaseModel):
    name: str
    value: Any


class CriterionReview(BaseModel):
    draft_id: str
    proposal: Literal["equivalent", "new_valid", "wrong", "unclear"]
    rules: list[str] = Field(default_factory=list)
    reasoning: str
    citations: list[str]
    confidence: float


class CriterionDraft(BaseModel):
    id: str = ""
    text: str
    applies_to: str = "41"
    condition: str = ""
    params: list[ParamDraft] = Field(default_factory=list)
    maps_to_rule: str | None = None
    citations: list[str] = Field(default_factory=list)
    status: TestStatus = "draft"
    review: CriterionReview | None = None  # human decision on a 3b proposal (rule 4)


class CriterionMatch(BaseModel):
    criterion: str
    rule: str
    found: bool
    params_ok: bool | None = None
    draft_ids: list[str] = Field(default_factory=list)
    via: Literal["exact", "ai", "missing"] = "missing"


class CriteriaScore(BaseModel):
    exact: int
    ai_proposed: int
    missing: int
    params_correct: int
    new_requirements: int
    matches: list[CriterionMatch] = Field(default_factory=list)
    summary: str = ""
