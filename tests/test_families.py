"""Scenario families plug in by adding files (roadmap G2)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from engine import builder, families
from engine.checker import check
from engine.expected import build_chain, get_case, load_scenario
from engine.model import Case
from engine.writer_messages import chain_files

DEMO = Path(__file__).resolve().parent / "fakes" / "families" / "demo"


@pytest.fixture(scope="module")
def demo():
    return families.load_from(DEMO)


def _case(send: bool) -> Case:
    return Case(id=f"demo-{send}", kind="reference", origin="builder", family="demo", inputs={"send_42": send})


def test_prior_illness_is_found_without_registration():
    assert families.get(None).id == "vorerkrankung"
    assert "vorerkrankung" in [f.id for f in families.all_families()]


def test_seed_cases_and_rules_name_their_family(kb):
    assert {t.family for t in kb.get_test_cases(include_hidden=True)} == {"vorerkrankung"}
    assert get_case(kb, "peter").family == "vorerkrankung"
    assert {r.id: r.family for r in kb.get_rules("41", "13.4")}["S-1"] == "common"
    assert {r.id: r.family for r in kb.get_rules("41", "13.4")}["R41-2"] == "vorerkrankung"


def test_unknown_family_is_refused():
    with pytest.raises(KeyError):
        families.get("no-such-family")


def test_demo_family_runs_through_the_core(kb, demo):
    tc = builder.with_expected(kb, _case(True))
    assert tc.inputs.__class__.__name__ == "DemoInputs" and tc.expected["13.4"].send_42
    assert Case.model_validate(tc.model_dump(mode="json")).inputs == tc.inputs  # store round trip
    ch = build_chain(load_scenario(kb, tc), "13.4", kb)
    files = chain_files(ch, tc.id, kb)
    assert list(files) == ["TEEL0-demo-True-r1"]
    assert check(kb, tc, list(files.values()), date(2027, 1, 1)).label == "exact_match"
    res = check(kb, tc, [], date(2027, 1, 1))
    assert res.label == "bug" and [d.rule for d in res.deviations] == ["DEMO-1"]
    assert builder.story_text(tc).startswith("Demo")
    assert check(kb, _case(False), [], date(2027, 1, 1)).label == "exact_match"
