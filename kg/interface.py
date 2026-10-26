"""The knowledge graph contract (plan/02 section 5). The backend talks to rules, layouts and
spec text only through this Protocol. Implementations: `kg/yaml_backend.py` (reference) and
`kg/graph_backend.py` (Neo4j), both owned by the KG teammate (plan/08)."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from engine.model import (
    Change,
    DeviationContext,
    Graph,
    Impact,
    Layout,
    Passage,
    Precedent,
    Rule,
    SpecRef,
    TestCase,
    TestCaseRef,
    Version,
)


@runtime_checkable
class KnowledgeBase(Protocol):
    def get_layout(self, record: str, version: str) -> Layout: ...

    def get_rules(self, abgabegrund: str, version: str) -> list[Rule]: ...

    def get_param(self, name: str, version: str | None = None, on_date: date | None = None) -> Any:
        """By date: real versions only; simulated values (sim-13.5) only by version."""
        ...

    def get_passage(self, ref: SpecRef | str) -> Passage: ...

    def search_passages(self, text: str, k: int = 5) -> list[Passage]: ...

    def get_changes(
        self, document: str, old_version: str, new_version: str, in_scope_only: bool = True
    ) -> list[Change]: ...

    def get_test_cases(self, rule_id: str | None = None, include_hidden: bool = False) -> list[TestCaseRef]: ...

    def get_test_case(self, key: str) -> TestCase: ...

    def get_affected_rules(self, changes: list[str]) -> Impact: ...

    def get_deviation_context(self, record: str, field: str, abgabegrund: str, version: str) -> DeviationContext: ...

    def add_precedent(self, p: Precedent) -> None: ...

    def find_precedent(self, signature: str) -> Precedent | None: ...

    def get_versions(self, document: str) -> list[Version]: ...

    def subgraph(self, label: str, key: str, depth: int = 1) -> Graph: ...
