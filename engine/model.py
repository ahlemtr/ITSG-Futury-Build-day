"""Shared Pydantic models (02 section 5). This part covers what the knowledge graph interface returns."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

RuleKind = Literal["domain", "format", "reply", "chain", "efz"]
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
