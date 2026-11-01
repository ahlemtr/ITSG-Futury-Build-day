"""Every rule card must be proved by a test and named by a test case.

A test proves a rule when it carries `@pytest.mark.rules("<id>", ...)` and fails if the rule's code is wrong.
Every rule is proved by a test (roadmap G2: one test per rule ID). A rule may be untargeted by test cases only
while no family uses it yet (listed below).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MARK = re.compile(r"mark\.rules\(([^)]*)\)")
ID = re.compile(r"[\"']([^\"']+)[\"']")

# rules no test proves yet: none since G2; a new rule card needs its test in the same change
UNTESTED: set[str] = set()
# rules no test case names in its targets
UNTARGETED = {"A3-2", "A3-3"}  # continuity of benefits: no family chains two benefits yet (G3-G6)


def _rule_ids() -> set[str]:
    data = yaml.safe_load((ROOT / "kg/seed/rules.yaml").read_text(encoding="utf-8"))
    return {r["id"] for r in data["rules"]}


def _marked() -> set[str]:
    found: set[str] = set()
    for f in (ROOT / "tests").glob("test_*.py"):
        if f.name == Path(__file__).name:
            continue
        for args in MARK.findall(f.read_text(encoding="utf-8")):
            found |= set(ID.findall(args))
    return found


def _targeted() -> set[str]:
    data = yaml.safe_load((ROOT / "kg/seed/test_cases.yaml").read_text(encoding="utf-8"))
    return {r for t in data["test_cases"] for r in t.get("targets") or []}


def test_markers_name_real_rules():
    unknown = _marked() - _rule_ids()
    assert not unknown, f"tests mark rules that have no rule card: {sorted(unknown)}"


def test_every_rule_is_proved_by_a_test():
    missing = _rule_ids() - _marked()
    assert missing == UNTESTED, (f"newly untested: {sorted(missing - UNTESTED)}; "
                                 f"now tested, remove from UNTESTED: {sorted(UNTESTED - missing)}")


def test_every_rule_is_named_by_a_test_case():
    missing = _rule_ids() - _targeted()
    assert missing == UNTARGETED, (f"newly untargeted: {sorted(missing - UNTARGETED)}; "
                                   f"now targeted, remove from UNTARGETED: {sorted(UNTARGETED - missing)}")
