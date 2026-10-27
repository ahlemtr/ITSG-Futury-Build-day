"""The contract between the knowledge graph and the rest of the backend (02 section 5, 08 section 13).

Both backends implement it: kg.yaml_backend (reference, no Neo4j or OpenAI needed) and kg.graph_backend.
Every method except add_precedent and subgraph is also an OpenAI agent tool with the same name and arguments.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol

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

__all__ = [
    "Change",
    "DeviationContext",
    "Graph",
    "Impact",
    "KnowledgeBase",
    "Layout",
    "Passage",
    "Precedent",
    "Rule",
    "SpecRef",
    "TestCase",
    "TestCaseRef",
    "Version",
]


class KnowledgeBase(Protocol):
    def get_layout(self, record: str, version: str) -> Layout: ...

    def get_field_definitions(self, record: str, field: str | None = None,
                              version: str | None = None, on_date=None) -> list[dict]: ...

    def get_rules(self, abgabegrund: str, version: str) -> list[Rule]:
        """Rules for a message type; sources limited to VB passages of that version (other docs always)."""
        ...

    def get_param(self, name: str, version: str | None = None, on_date: dt.date | None = None) -> Any:
        """By date: real versions only; simulated values (sim-13.5) only by version."""
        ...

    def get_passage(self, ref: str | SpecRef) -> Passage: ...

    def search_passages(self, text: str, k: int = 5, version: str | None = None, on_date=None) -> list[Passage]:
        """Vector search, full-text fallback (YAML backend: plain substring search)."""
        ...

    def get_versions(self, document: str) -> list[Version]: ...

    def get_changes(self, document: str, old_version: str, new_version: str,
                    in_scope_only: bool = True) -> list[Change]: ...

    def get_affected_rules(self, change_keys: list[str]) -> Impact:
        """{recompute, review, tests}; the builder uses recompute only (07 section 7)."""
        ...

    def get_test_cases(self, rule_id: str | None = None, include_hidden: bool = False) -> list[TestCaseRef]: ...

    def get_test_case(self, key: str) -> TestCase: ...

    def get_deviation_context(self, record: str, field: str, abgabegrund: str, version: str) -> DeviationContext: ...

    def add_precedent(self, p: Precedent) -> None: ...

    def find_precedent(self, signature: str) -> Precedent | None: ...

    def subgraph(self, label: str, key: str, depth: int = 1) -> Graph:
        """UI only, not an agent tool."""
        ...
