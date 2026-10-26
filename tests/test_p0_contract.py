from datetime import date
from pathlib import Path

import yaml

from kg.interface import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]


def test_layouts_load():
    files = list((ROOT / "layouts").glob("*.yaml"))
    assert len(files) == 20
    for f in files:
        assert yaml.safe_load(f.read_text(encoding="utf-8"))["record"] == f.stem


def test_itsg_file_present():
    assert (ROOT / "fixtures/itsg/TEEL0-Test1-DBVO").exists()


def test_fake_implements_protocol(kb):
    assert isinstance(kb, KnowledgeBase)
    assert kb.get_param("gap_inclusive", on_date=date(2027, 1, 1)) is True
    assert kb.get_param("gap_inclusive", on_date=date(2026, 11, 1)) is False
    assert kb.get_param("min_total_days", version="sim-13.5") == 28
    assert kb.get_param("min_total_days", on_date=date(2028, 6, 1)) == 30


def test_fake_kg_answers(kb):
    rules = kb.get_rules("41", "13.3")
    assert len(rules) == 18 and not any(s.startswith("VB@13.4") for r in rules for s in r.sources)
    imp = kb.get_affected_rules(["VB-13.3-13.4-DBVO-chaining"])
    assert {r.id for r in imp.recompute} == {"R41-2", "R41-3"}
    assert {t.id for t in imp.tests} == {"peter", "peter-gap-exact", "peter-gap-in", "peter-gap-out", "peter-hidden",
                                         "peter-gap-exact-hidden", "bp-13-2", "bp-13-3"}
    assert "nicht mehr als 6 Monate" in kb.get_passage("VB@13.4#3.12/chaining").text
    assert "nicht mindestens 6 Monate" in kb.get_passage("VB@13.4#3.12/insurer").text
    lay = kb.get_layout("DBVO", "13.4")
    assert len(lay.fields) + len(lay.repeating_group.fields) == 15
