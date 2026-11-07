"""Scenario family interface.

A family is one kind of test story: its own case facts, its own expected message chain and its own
rules. `vorerkrankung` (Peter: 41, 61, 01, 61, 88, 01, 62) is the first. Later: 02 Kinderkrankengeld,
03 Mutterschaftsgeld, ...

The core (parser, diff, labels, catalogue and precedents, the common rules of engine/rules/, reports)
works the same for every family. It asks the family only for what
differs. A new family = a new folder `engine/families/<id>/` with a `FAMILY` object; nothing in the core
changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel

from engine.model import Case, Deviation, ExpectedMessage, Record, Rule, RuleResult, Trace
from kg.interface import KnowledgeBase


class ChainResult(BaseModel):
    """Expected messages of one case under one rule set version (today in engine/expected.py)."""

    version: str
    messages: list[ExpectedMessage]
    decision: Any = None  # the family's own decision object (vorerkrankung: Decision41)
    values: dict[str, Any] = {}  # family values shown in the UI (vorerkrankung: efz dates)
    traces: dict[str, Trace] = {}

    def employer(self) -> list[ExpectedMessage]:
        return [m for m in self.messages if m.actor == "employer"]

    @property
    def efz(self) -> dict[str, Any]:
        """vorerkrankung: the EFZ end after each 61 (empty for other families)."""
        return self.values.get("efz", {})


class Scenario(BaseModel):
    """Case facts from the knowledge base + chain-only extras (person, employer, ids) from
    fixtures/scenarios/<id>.yaml. Same for every family."""

    test_case: Case
    extras: dict[str, Any]

    @property
    def id(self) -> str:
        return self.test_case.id


@dataclass
class CheckContext:
    """What the checker hands a family while checking one submission."""

    kb: KnowledgeBase
    version: str
    scenario: Scenario
    chain: ChainResult
    rules: dict[str, Rule]  # rule cards of this version
    actual: list[Record]  # the vendor's messages
    params: Any = None  # the family's parameters of this version
    step_of: dict[int, int] = field(default_factory=dict)  # id(record) -> chain step
    # set by the checker: label(deviation, label, rule, why); label None = the rule is broken, its card's kind decides
    label: Callable[[Deviation, str | None, str | None, str], bool] = lambda *a: True


class Family(ABC):
    id: ClassVar[str]  # "vorerkrankung"
    title: ClassVar[str]  # German, shown in the UI: "Vorerkrankung"
    codes: ClassVar[frozenset[str]]  # Abgabegründe of the chain: 41, 61, 01, 88, 62
    Inputs: ClassVar[type[BaseModel]]  # typed case facts (vorerkrankung: AU periods, report date ...)
    Outcome: ClassVar[type[BaseModel]]  # expected result per version (vorerkrankung: send 41?, periods, days)

    # ---- expected results (deterministic, never AI)
    @abstractmethod
    def params(self, kb: KnowledgeBase, version: str) -> Any:
        """The family's versioned parameters (vorerkrankung: gap_months, min_total_days ...)."""

    @abstractmethod
    def outcome(self, kb: KnowledgeBase, case: Case, version: str) -> BaseModel:
        """The decision only, for the catalogue and the builder (vorerkrankung: must a 41 be sent?)."""

    @abstractmethod
    def build_chain(self, kb: KnowledgeBase, scenario: Scenario, version: str) -> ChainResult:
        """All expected messages, employer and insurer, with step and round."""

    # ---- checking the vendor's files
    def check_records(self, ctx: CheckContext) -> list[tuple[Record | None, RuleResult]]:
        """Family rules on the vendor's messages (vorerkrankung: F41 on the 41, E-2 on the 88)."""
        return []

    def recheck(self, ctx: CheckContext, d: Deviation) -> bool:
        """Name the rule behind one diff deviation and label it via ctx.label; False = not covered."""
        return False

    # ---- test runs in rounds
    def adapt_reply(self, reply: ExpectedMessage, vendor: list[Record]) -> ExpectedMessage:
        """The insurer reply built on the vendor's own file (REFERENZ-ID = their DATENSATZ-ID)."""
        return reply

    def single_step_replies(self, kb: KnowledgeBase, scenario: Scenario, chain: ChainResult) -> list[ExpectedMessage]:
        """Insurer replies shipped with a single-step test package (vorerkrankung: the 61 to the 41)."""
        return []

    def round_one_rules(self, case: Case) -> list[str]:
        """Rules a clean first round already proves (vorerkrankung: the R41 targets)."""
        return []

    def self_check(self, kb: KnowledgeBase, scenario: Scenario, replies: list[Record],
                   employer: list[Record]) -> list[RuleResult]:
        """Checks on the replies our insurer simulator writes (vorerkrankung: K61, K62), against the employer
        messages they answer. Returns the failed checks; a failure is our bug, never the vendor's."""
        return []

    # ---- test builder
    def generators(self) -> dict[str, Callable[[KnowledgeBase, Case], list[Case]]]:
        """Boundary generators by rule ID (vorerkrankung: R41-2, R41-3, R41-4)."""
        return {}

    def hidden(self, kb: KnowledgeBase, case: Case, seed: int = 0) -> Case:
        """Same rule, other dates, expected results computed, never exported."""
        raise NotImplementedError(f"family {self.id} has no hidden variants")

    def story(self, case: Case) -> str:
        """The task text the vendor reads (German)."""
        raise NotImplementedError
