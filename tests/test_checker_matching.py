"""The checker names a rule for the message the rule failed on, not another message of the same type, and the
result does not depend on the order of the vendor's files or lines (code review of the rule review, 2026-11-07)."""

from datetime import date

import pytest

from engine.checker import check
from engine.expected import build_chain, load_scenario
from engine.writer_messages import write_file

D = date.fromisoformat
ON = D("2027-01-01")


def _employer(kb):
    return [m.model_copy(deep=True) for m in build_chain(load_scenario(kb, "peter"), "13.4", kb).employer()]


def _labels(res):
    return sorted((d.step, d.abgabegrund, d.field, d.rule, d.label) for d in res.deviations)


@pytest.mark.rules("C-3", "E-2")
def test_order_of_files_and_lines_does_not_matter(kb):
    msgs = _employer(kb)
    assert check(kb, "peter", [write_file(msgs, kb)], ON).label == "exact_match"
    assert check(kb, "peter", [write_file(list(reversed(msgs)), kb)], ON).label == "exact_match"
    assert check(kb, "peter", [write_file([m], kb) for m in reversed(msgs)], ON).label == "exact_match"


@pytest.mark.rules("S-2")
def test_each_message_gets_its_own_failure(kb):
    msgs = _employer(kb)
    for m in msgs:
        if m.abgabegrund == "01":
            m.head["KORR-ABGABEGRUND"] = 1
    res = check(kb, "peter", [write_file(msgs, kb)], ON)
    got = {(d.step, d.rule, d.label) for d in res.deviations if d.field == "KORR-ABGABEGRUND"}
    assert got == {(s, "S-2", "invalid") for s in (m.step for m in msgs if m.abgabegrund == "01")}


@pytest.mark.rules("S-1")
def test_a_failure_on_one_01_does_not_label_the_other(kb):
    """The first 01 sends MM-KUG 9 (no Schlüsselzahl, S-1); the second sends 1, a valid code that differs from
    the expected 0. Only the first is S-1: the second is a deviation of its own."""
    msgs = _employer(kb)
    first, second = [m for m in msgs if m.abgabegrund == "01"]
    first.blocks["DBAL"]["MM-KUG"], second.blocks["DBAL"]["MM-KUG"] = 9, 1
    res = check(kb, "peter", [write_file(msgs, kb)], ON)
    rules = {d.step: d.rule for d in res.deviations if d.field == "MM-KUG"}
    assert rules[first.step] == "S-1" and rules[second.step] != "S-1", _labels(res)


@pytest.mark.rules("F41-4")
def test_the_specific_rule_wins_over_the_code_table(kb):
    msgs = _employer(kb)
    msgs[0].blocks["DBVO"]["GRUNDAV"] = 7  # no Schlüsselzahl (S-1) and not 1 (F41-4)
    res = check(kb, "peter", [write_file(msgs, kb)], ON)
    assert {d.rule for d in res.deviations if d.field == "GRUNDAV"} == {"F41-4"}


@pytest.mark.rules("C-3")
def test_names_on_an_88_that_points_nowhere(kb):
    msgs = _employer(kb)
    m88 = next(m for m in msgs if m.abgabegrund == "88")
    m88.blocks["DBSD"]["DATENSATZ-ID-URSPRUNGSMELDUNG"] = "00000000-0000-0000-0000-000000000000"
    m88.blocks["DBSD"]["VORNAME"] = "Paul"
    res = check(kb, "peter", [write_file(msgs, kb)], ON)
    got = {(d.field, d.rule, d.label) for d in res.deviations if d.abgabegrund == "88"}
    assert ("VORNAME", "C-3", "bug") in got, _labels(res)
