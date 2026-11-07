"""Scenarios and expected message chains.

A scenario = case facts from the knowledge base (`kb.get_test_case`, as `Case`) + chain-only extras from
`fixtures/scenarios/<id>.yaml`. `build_chain` hands it to the case's family (`engine/families/`), which
turns it into the expected messages under one rule set version.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine import families
from engine.families.base import ChainResult, Scenario
from engine.model import Case
from kg.interface import KnowledgeBase

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios"
DEFAULT_EXTRAS = "peter"

__all__ = ["ChainResult", "Scenario", "build_chain", "get_case", "load_extras", "load_scenario"]


def load_extras(kb: KnowledgeBase, tc: Case) -> dict[str, Any]:
    seen = set()
    key: str | None = tc.id
    while key and key not in seen:
        seen.add(key)
        path = SCENARIO_DIR / f"{key}.yaml"
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            key = kb.get_test_case(key).parent if key != tc.id else tc.parent
        except KeyError:
            key = None
    return yaml.safe_load((SCENARIO_DIR / f"{DEFAULT_EXTRAS}.yaml").read_text(encoding="utf-8"))


def get_case(kb: KnowledgeBase, key: str) -> Case:
    """The KG test case as the engine's typed `Case`."""
    return Case.from_kb(kb.get_test_case(key))


def load_scenario(kb: KnowledgeBase, test_case: str | Case) -> Scenario:
    tc = get_case(kb, test_case) if isinstance(test_case, str) else test_case
    return Scenario(test_case=tc, extras=load_extras(kb, tc))


def build_chain(sc: Scenario, version: str, kb: KnowledgeBase) -> ChainResult:
    return families.of_case(sc.test_case).build_chain(kb, sc, version)
