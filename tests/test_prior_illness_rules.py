"""G2, completing the prior-illness rules: insurer flags from case facts (K61-4, K61-5), interim updates (E-3),
statutory insurance and marginal employment (R41-7, R41-8), the self-check of the insurer simulator."""

from datetime import date

import pytest

from engine import runs
from engine.checker import check
from engine.expected import build_chain, get_case, load_scenario
from engine.families.vorerkrankung.rules import insurer_flags, supersedes
from engine.model import AuPeriod
from engine.records import parse_file
from engine.writer_messages import chain_files, write_file

D = date.fromisoformat
P = {"start": D("2025-12-01"), "end": D("2025-12-03")}


def _flags(reply, **facts):
    f = insurer_flags(AuPeriod(**P, **facts), reply)
    return f["KZ-NACHWEIS"], f["KZ-AU"]


@pytest.mark.rules("K61-4", "K61-5")
def test_insurer_flags_from_facts():
    assert _flags("first") == (1, 1) and _flags("corrected") == (1, 1)  # eAU: known at once, counts
    # Peter's paper note: unknown in the first 61 (missing, further check), handed in for the corrected one
    assert _flags("first", sick_note="paper", insurer_gets_note="corrected") == (4, 3)
    assert _flags("corrected", sick_note="paper", insurer_gets_note="corrected") == (1, 1)
    assert _flags("first", sick_note="paper", insurer_gets_note="first") == (1, 1)
    assert _flags("corrected", sick_note="paper") == (4, 2)  # never handed in: decided, does not count
    assert _flags("first", counts="no") == (1, 2)
    part = insurer_flags(AuPeriod(**P, counts="partly", counts_from=D("2025-12-02"), counts_to=D("2025-12-03")),
                         "first")
    assert (part["KZ-AU"], part["TEIL-ANR-AU-BEGINN"], part["TEIL-ANR-AU-ENDE"]) == (5, D("2025-12-02"),
                                                                                      D("2025-12-03"))
    assert _flags("corrected", insurer_rechecks=True) == (1, 3) and _flags("first", insurer_rechecks=True) == (1, 1)


@pytest.mark.rules("K61-4", "K61-5")
def test_peter_61_flags_are_computed(kb):
    ch = build_chain(load_scenario(kb, "peter"), "13.4", kb)
    first, corrected = ch.messages[1], ch.messages[3]
    g = {str(x["BEGINN-AU"]): (x["KZ-NACHWEIS"], x["KZ-AU"]) for x in first.blocks["DBVO"]["groups"]}
    assert g["2026-03-01"] == (4, 3) and g["2025-12-01"] == (1, 1)
    assert {(x["KZ-NACHWEIS"], x["KZ-AU"]) for x in corrected.blocks["DBVO"]["groups"]} == {(1, 1)}


@pytest.mark.rules("E-3")
def test_interim_update_does_not_replace_the_first_61(kb):
    g = lambda au: {"BEGINN-AU": D("2025-12-01"), "ENDE-AU": D("2025-12-03"), "KZ-NACHWEIS": 1, "KZ-AU": au}
    dbvo = lambda au, ak=0: {"KZ-AK-AU": ak, "groups": [g(au)]}
    assert not supersedes(dbvo(1), dbvo(3)) and not supersedes(dbvo(1), dbvo(1, ak=4))
    assert supersedes(dbvo(3), dbvo(1)) and supersedes(dbvo(1), dbvo(2))
    ch = build_chain(load_scenario(kb, "peter-interim-update"), "13.4", kb)
    assert [m.abgabegrund for m in ch.messages] == ["41", "61", "01", "61", "62"]
    assert ch.values["corrected_61_replaces_first"] is False
    assert ch.messages[2].blocks["DBAL"]["DATUM-EGZBIS"] == ch.efz["after_first_61"] != ch.efz["after_corrected_61"]


@pytest.mark.rules("E-3")
def test_cancel_after_an_interim_update_is_a_bug(kb):
    """The vendor treats the interim update like a real correction and cancels its 01."""
    peter = build_chain(load_scenario(kb, "peter"), "13.4", kb)
    sc = load_scenario(kb, "peter-interim-update")
    own = build_chain(sc, "13.4", kb)
    msgs = own.employer() + [m.model_copy(deep=True) for m in peter.employer() if m.step in (5, 6)]
    res = check(kb, "peter-interim-update", [write_file(msgs, kb)], D("2027-01-01"))
    assert res.label == "bug" and "E-3" in {d.rule for d in res.deviations}


@pytest.mark.rules("R41-7", "R41-8")
def test_no_41_without_statutory_insurance(kb, itsg_bytes):
    for case, rule in (("peter-private", "R41-7"), ("peter-minijob", "R41-8")):
        ch = build_chain(load_scenario(kb, case), "13.4", kb)
        assert ch.messages == [] and ch.decision.trace.failed == [rule]
        res = check(kb, case, [itsg_bytes], D("2027-01-01"))  # the vendor sends a 41 anyway
        assert res.label == "bug" and {d.rule for d in res.deviations} == {rule}
    assert get_case(kb, "peter-private").inputs.insurance == "private"


@pytest.mark.rules("R41-7")
def test_41_goes_to_the_persons_insurer(kb):
    m41 = build_chain(load_scenario(kb, "peter"), "13.4", kb).messages[0].model_copy(deep=True)
    m41.head["EMPFAENGERNUMMER"] = "12345678"
    res = check(kb, "peter", [write_file([m41], kb)], D("2027-01-01"))
    d = next(d for d in res.deviations if d.field == "EMPFAENGERNUMMER")
    assert d.label == "bug" and d.rule == "R41-7"


@pytest.mark.rules("K61-1", "K61-2", "K61-3", "K62-1", "C-6", "C-7")
def test_simulator_self_check(kb):
    for case in ("peter", "peter-interim-update"):
        assert runs.self_check_chain(kb, case, "13.4") == []
    st, _ = runs.start(kb, "peter", D("2027-01-01"))
    files = {k: v for k, v in chain_files(build_chain(load_scenario(kb, "peter"), "13.4", kb), "peter", kb).items()
             if k.startswith("TEEL0")}
    for r in (1, 2, 3):
        assert runs.submit(kb, st, [files[f"TEEL0-peter-r{r}"]]).simulator_issues == []
    # a broken reply is caught: wrong reference, other BBNR-VU, periods not those of the 41
    sc = load_scenario(kb, "peter")
    ch = build_chain(sc, "13.4", kb)
    bad = ch.messages[1].model_copy(deep=True)
    bad.blocks["DBID"]["REFERENZ-ID"] = "00000000-0000-4000-8000-000000000000"
    bad.head["BBNR-VU"] = "11111111"
    bad.blocks["DBVO"]["groups"].reverse()
    replies = parse_file(write_file([bad], kb), kb, "13.4").messages
    employer = parse_file(write_file(ch.employer(), kb), kb, "13.4").messages
    from engine import families

    failed = {x.rule for x in families.of_case(sc.test_case).self_check(kb, sc, replies, employer)}
    assert {"K61-1", "K61-2", "K61-3"} <= failed
