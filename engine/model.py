"""Shared Pydantic models.

The first part (layouts to Graph) is the contract with the knowledge graph (`kg/interface.py`,
plan/02 section 5). Field names, keys and enum values follow plan/08 sections 1.3 to 1.5 exactly.
The second part holds the engine's own models (parsed records, traces, deviations, check results).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

# ---------------------------------------------------------------- enums (plan/08 section 1.4)

RuleKind = Literal["domain", "format", "reply", "chain", "efz"]
RuleStatus = Literal["approved", "draft"]
FieldType = Literal["an", "n"]
Required = Literal["M", "m"]
CompareMode = Literal["compare", "rule", "ignore"]
LayoutStatus = Literal["extracted", "inferred", "partial", "missing"]
TestKind = Literal["reference", "clone", "hidden"]
TestOrigin = Literal["itsg", "beispielpapier", "builder", "pta"]
TestStatus = Literal["draft", "approved", "rejected"]
ChangeTag = Literal["replace", "insert", "delete"]
ChangeLabel = Literal["editorial", "clarification", "law_change", "unknown"]
PrecedentVerdict = Literal["correct_variant", "bug", "invalid"]
DeviationKind = Literal[
    "value_differs",
    "missing_block",
    "extra_block",
    "missing_message",
    "extra_message",
    "missing_group",
    "extra_group",
    "order_differs",
]
Label = Literal["exact_match", "correct_variant", "bug", "invalid", "unclear"]
ResolvedBy = Literal["diff", "catalogue", "rules", "ai_proposal", "advisor", "precedent", "format"]

# worst first (plan/05 section 5)
LABEL_ORDER: list[str] = ["invalid", "bug", "unclear", "correct_variant", "exact_match"]

REPEAT_SUFFIX = re.compile(r"-(\{nn\}|\d+)$")


def base_field_name(name: str) -> str:
    """`BEGINN-AU-{nn}` and `BEGINN-AU-1` -> `BEGINN-AU` (plan/08 section 1.3)."""
    return REPEAT_SUFFIX.sub("", name)


# ---------------------------------------------------------------- knowledge graph contract


class Field(BaseModel):
    name: str  # as in the layout; repeating fields without the {nn} suffix
    start: int
    end: int
    length: int
    type: FieldType
    required: Required = "M"
    format: str | None = None
    constant: str | None = None
    values: dict[str, str] | None = None
    source: str | None = None
    repeating: bool = False
    offset_in_group: int | None = None
    compare_mode: CompareMode = "compare"
    status: LayoutStatus = "extracted"


class RepeatingGroup(BaseModel):
    count_field: str
    starts_at: int
    group_length: int
    fields: list[Field]


class Layout(BaseModel):
    record: str
    title: str = ""
    section: str | None = None
    page: int | None = None
    status: LayoutStatus = "extracted"
    fixed_length: int
    fields: list[Field]
    repeating_group: RepeatingGroup | None = None
    block_order: list[str] = []  # DSLW only
    announced_by: str | None = None  # MM flag in DSLW that announces this block

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        for f in self.repeating_group.fields if self.repeating_group else []:
            if f.name == base_field_name(name):
                return f
        raise KeyError(f"{self.record}.{name}")


class SpecRef(BaseModel):
    doc: str
    version: str
    section: str
    part: str | None = None

    @property
    def key(self) -> str:
        return f"{self.doc}@{self.version}#{self.section}" + (f"/{self.part}" if self.part else "")

    @classmethod
    def parse(cls, key: str) -> SpecRef:
        m = re.match(r"^([A-Z0-9-]+)@([^#]+)#([^/]+)(?:/(.+))?$", key)
        if not m:
            raise ValueError(f"not a passage key: {key}")
        return cls(doc=m[1], version=m[2], section=m[3], part=m[4])


class Passage(BaseModel):
    key: str
    doc: str
    version: str
    section: str
    part: str | None = None
    heading: str | None = None
    text: str
    page: int | None = None
    field: str | None = None


class ParamValue(BaseModel):
    version: str
    valid_from: date | None = None
    value: Any
    simulated: bool = False


class Parameter(BaseModel):
    name: str
    note: str | None = None
    values: list[ParamValue]
    sources: list[str] = []


class Rule(BaseModel):
    id: str
    title: str
    description: str | None = None
    kind: RuleKind
    status: RuleStatus = "approved"
    criterion: str | None = None
    applies_to: list[str]
    fields: list[str] = []
    params: list[str] = []
    sources: list[str] = []


class Version(BaseModel):
    document: str
    version: str
    published: date | None = None
    valid_from: date | None = None
    file: str | None = None
    succeeds: str | None = None
    simulated: bool = False


class Change(BaseModel):
    key: str
    tag: ChangeTag | None = None
    block: str | None = None
    field: str | None = None
    old: str = ""
    new: str = ""
    in_scope: bool = False
    label: ChangeLabel = "unknown"
    summary: str | None = None
    changes_param: list[str] = []
    modifies_old: list[str] = []
    modifies_new: list[str] = []


class TestCaseRef(BaseModel):
    id: str
    kind: TestKind
    origin: TestOrigin
    status: TestStatus = "approved"
    hidden: bool = False
    parent: str | None = None
    targets: list[str] = []
    steps: Literal["single", "chain"] = "single"


class Impact(BaseModel):
    recompute: list[Rule] = []
    review: list[Rule] = []
    tests: list[TestCaseRef] = []


class AuPeriod(BaseModel):
    start: date
    end: date | None = None  # None = open end (current AU only)
    certified: bool = True


class TestInputs(BaseModel):
    report_date: date | None = None
    employment_end: date | None = None
    current: AuPeriod | None = None
    priors: list[AuPeriod] = []
    summary: str | None = None


class ExpectedOutcome(BaseModel):
    send_41: bool
    periods: list[tuple[date, date]] = []
    total_days: int | None = None


class TestCase(TestCaseRef):
    inputs: TestInputs
    expected: dict[str, ExpectedOutcome] = {}
    sources: list[str] = []
    efz_ends: dict[str, date] = {}
    chain: list[str] = []
    branch_point: date | None = None


class Precedent(BaseModel):
    key: str  # signature ABGABEGRUND|RECORD.FIELD|KIND
    verdict: PrecedentVerdict
    reason: str
    advisor: str | None = None
    decided_on: date | None = None
    citations: list[str] = []


class BlockUse(BaseModel):
    type: str  # Abgabegrund
    record: str
    flag: str
    mandatory: bool | Literal["unknown"]


class DeviationContext(BaseModel):
    rules: list[Rule] = []
    passages: list[Passage] = []
    precedents: list[Precedent] = []
    blocks: list[BlockUse] = []


class GraphNode(BaseModel):
    label: str
    key: str
    props: dict[str, Any] = {}


class GraphEdge(BaseModel):
    type: str
    from_key: str
    to_key: str
    props: dict[str, Any] = {}


class Graph(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


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
    fields: dict[str, FieldValue] = {}
    groups: list[dict[str, FieldValue]] = []
    pos: int = 1
    length: int = 0


class Record(BaseModel):
    """One line of a file. DSLW lines are parsed; envelope lines (VOSZ, DSKO, NCSZ) kept raw."""

    kind: str
    line_no: int
    raw: str
    newline: str = ""
    head: dict[str, FieldValue] = {}
    blocks: dict[str, Block] = {}
    tail: str = ""  # unparsed remainder after an issue

    def get(self, key: str) -> Any:
        """`DSLW.ABGABEGRUND`, `DBVO.AU-AB-AG` -> typed value (None if absent)."""
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
    def periods(self) -> list[tuple[date | None, date | None]]:
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
    records: list[Record] = []
    issues: list[ParseIssue] = []
    encoding: str = "utf-8"

    @property
    def messages(self) -> list[Record]:
        return [r for r in self.records if r.kind == "DSLW"]


# ---------------------------------------------------------------- rules engine


class Trace(BaseModel):
    rules: list[str] = []
    inputs: dict[str, Any] = {}
    values: dict[str, Any] = {}
    steps: list[str] = []
    failed: list[str] = []  # rule ids whose condition does not hold

    def add(self, rule: str, step: str, ok: bool = True) -> None:
        if rule not in self.rules:
            self.rules.append(rule)
        self.steps.append(f"{rule}: {step}")
        if not ok and rule not in self.failed:
            self.failed.append(rule)


class Decision41(BaseModel):
    send: bool
    chain: list[AuPeriod] = []
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


# ---------------------------------------------------------------- scenarios and expected chains


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
    sources: list[str] = []
    explanation: str = ""
    resolved_by: ResolvedBy | None = None
    precedent_key: str | None = None
    ai_proposal: AiProposal | None = None

    @property
    def signature(self) -> str:
        fld = f"{self.record}.{self.field}" if self.field else self.record
        return f"{self.abgabegrund or ''}|{fld}|{self.kind}"


class CheckResult(BaseModel):
    test_case_id: str
    valid_on: date
    version: str
    label: Label
    deviations: list[Deviation] = []
    parse_issues: list[ParseIssue] = []
    counts: dict[str, int] = {}
    resolved_by: dict[str, int] = {}
    expected_messages: int = 0
    actual_messages: int = 0


# ---------------------------------------------------------------- criteria pipeline (P8.2)


class RequirementSentence(BaseModel):
    passage_key: str
    quote: str


class ParamDraft(BaseModel):
    name: str
    value: Any


class CriterionDraft(BaseModel):
    id: str = ""
    text: str
    applies_to: str = "41"
    condition: str = ""
    params: list[ParamDraft] = []
    maps_to_rule: str | None = None
    citations: list[str] = []
    status: TestStatus = "draft"
    review: CriterionReview | None = None  # human decision on a 3b proposal (rule 4)


class CriterionReview(BaseModel):
    draft_id: str
    proposal: Literal["equivalent", "new_valid", "wrong", "unclear"]
    rules: list[str] = []
    reasoning: str
    citations: list[str]
    confidence: float


class CriterionMatch(BaseModel):
    criterion: str
    rule: str
    found: bool
    params_ok: bool | None = None
    draft_ids: list[str] = []
    via: Literal["exact", "ai", "missing"] = "missing"


class CriteriaScore(BaseModel):
    exact: int
    ai_proposed: int
    missing: int
    params_correct: int
    new_requirements: int
    matches: list[CriterionMatch] = []
    summary: str = ""


CriterionDraft.model_rebuild()


def to_decimal(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))
