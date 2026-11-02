"""One test per rule ID that had none before G2: each breaks one rule and shows that its check catches it."""

from datetime import date

import pytest

from engine.checker import check
from engine.expected import build_chain, get_case, load_scenario
from engine.families.vorerkrankung import chain as vk_chain
from engine.families.vorerkrankung import checks as vk
from engine.rules import formats
from engine.writer_messages import write_file

D = date.fromisoformat


def _peter(kb):
    return build_chain(load_scenario(kb, "peter"), "13.4", kb)


def _parsed(kb, msgs):
    from engine.records import parse_file

    return parse_file(write_file(msgs, kb), kb, "13.4").messages


def _fails(results, rule):
    return [r for r in results if r.rule == rule and not r.ok]


def _41(kb, **dbvo):
    m = _peter(kb).messages[0].model_copy(deep=True)
    m.blocks["DBVO"].update(dbvo)
    return m


# ---------------------------------------------------------------- F41: format of the employer's 41


@pytest.mark.rules("F41-1", "F41-2")
def test_f41_1_and_2_abgabegrund_and_korr(kb):
    m01 = _parsed(kb, [_peter(kb).messages[2]])[0]
    assert _fails(vk.check_41_format(m01), "F41-1")
    m = _41(kb)
    m.head["KORR-ABGABEGRUND"] = 1
    [rec] = _parsed(kb, [m])
    assert _fails(vk.check_41_format(rec), "F41-2") and not _fails(vk.check_41_format(rec), "F41-1")


@pytest.mark.rules("F41-3")
def test_f41_3_mm_flags_match_blocks(kb):
    [rec] = _parsed(kb, [_peter(kb).messages[0]])
    rec.head["MM-ANSPRECH"].value = "N"  # flag says no DBAP, block is there
    assert _fails(formats.check_mm_flags(rec), "F41-3")
    del rec.blocks["DBVO"]
    assert _fails(vk.check_41_format(rec), "F41-3")


@pytest.mark.rules("F41-4", "F41-5")
def test_f41_4_and_5_grundav_and_start(kb):
    res = check(kb, "peter", [write_file([_41(kb, GRUNDAV=2)], kb)], D("2027-01-01"))
    assert {(d.rule, d.label) for d in res.deviations if d.field == "GRUNDAV"} == {("F41-4", "invalid")}
    res = check(kb, "peter", [write_file([_41(kb, **{"AU-AB-AG": D("2026-03-12")})], kb)], D("2027-01-01"))
    assert {(d.rule, d.label) for d in res.deviations if d.field == "AU-AB-AG"} == {("F41-5", "invalid")}


@pytest.mark.rules("F41-7")
def test_f41_7_count_of_groups(kb):
    [rec] = _parsed(kb, [_peter(kb).messages[0]])
    rec.blocks["DBVO"].fields["ANZAHL-AU"].value = 3  # four groups follow
    assert _fails(vk.check_41_format(rec, D("2026-03-11")), "F41-7")


@pytest.mark.rules("F41-9")
def test_f41_9_insurer_only_group_fields(kb):
    m = _41(kb)
    m.blocks["DBVO"]["groups"][0]["KZ-AU"] = 1
    [rec] = _parsed(kb, [m])
    assert _fails(vk.check_41_format(rec, D("2026-03-11")), "F41-9")
    res = check(kb, "peter", [write_file([m], kb)], D("2027-01-01"))
    assert "F41-9" in {d.rule for d in res.deviations if d.label == "invalid"}


@pytest.mark.rules("F41-10")
def test_f41_10_datensatz_id_format(kb):
    m = _41(kb)
    m.head["DATENSATZ-ID"] = "not-a-uuid"
    [rec] = _parsed(kb, [m])
    assert not formats.check_uuid(rec).ok
    assert formats.check_uuid(_parsed(kb, [_41(kb)])[0]).ok  # ITSG's own style of ID is accepted


# ---------------------------------------------------------------- K61: what the insurer's 61 carries


@pytest.mark.rules("K61-6")
def test_k61_6_twelve_month_period_starts_at_earliest_counted(kb):
    ch = _peter(kb)
    assert ch.messages[1].blocks["DBVO"]["12-MONATSFRIST-AB"] == D("2025-07-14")  # Hinweise
    tc = get_case(kb, "peter").model_copy(deep=True)
    tc.inputs.priors[0].counts = "no"  # 14.07-15.07.2025 does not count
    own = build_chain(load_scenario(kb, tc), "13.4", kb)
    assert own.messages[3].blocks["DBVO"]["12-MONATSFRIST-AB"] == D("2025-10-01")


@pytest.mark.rules("K61-7")
def test_k61_7_current_sick_note_missing(kb):
    ch = _peter(kb)
    assert ch.messages[1].blocks["DBVO"]["KZ-AK-AU"] == 0
    tc = get_case(kb, "peter").model_copy(deep=True)
    tc.inputs.current.certified = False
    m61 = vk_chain.msg_61(load_scenario(kb, tc), ch.decision.chain, "first_61", 2, 1, "x")
    assert m61.blocks["DBVO"]["KZ-AK-AU"] == 4


# ---------------------------------------------------------------- C: consistency of the chain


def _employer(kb):
    return [m.model_copy(deep=True) for m in _peter(kb).employer()]


@pytest.mark.rules("C-3")
def test_c3_cancel_points_to_the_01(kb):
    msgs = _employer(kb)
    m88 = next(m for m in msgs if m.abgabegrund == "88")
    m88.blocks["DBSD"]["DATENSATZ-ID-URSPRUNGSMELDUNG"] = msgs[0].head["DATENSATZ-ID"]  # the 41, not the 01
    assert _fails(vk.check_chain(_parsed(kb, msgs)), "C-3")
    res = check(kb, "peter", [write_file(msgs, kb)], D("2027-01-01"))
    assert "C-3" in {d.rule for d in res.deviations if d.label == "bug"}


@pytest.mark.rules("C-4")
def test_c4_cancel_names(kb):
    msgs = _employer(kb)
    next(m for m in msgs if m.abgabegrund == "88").blocks["DBSD"]["VORNAME"] = "Paul"
    assert _fails(vk.check_chain(_parsed(kb, msgs)), "C-4")


@pytest.mark.rules("C-5")
def test_c5_new_01_after_the_cancel(kb):
    msgs = [m for m in _employer(kb) if m.step != 6]  # 88 without the new 01
    assert _fails(vk.check_chain(_parsed(kb, msgs)), "C-5")


@pytest.mark.rules("C-8")
def test_c8_cancel_carries_only_dbsd(kb):
    msgs = _employer(kb)
    m88 = next(m for m in msgs if m.abgabegrund == "88")
    m88.blocks["DBNA"] = dict(msgs[0].blocks["DBNA"])
    assert _fails(vk.check_chain(_parsed(kb, msgs)), "C-8")


# ---------------------------------------------------------------- G2b: K61-8, E-4, E-5


@pytest.mark.rules("K61-8")
def test_k61_8_au_ab_sv_only_when_the_insurer_start_differs(kb):
    assert _peter(kb).messages[1].blocks["DBVO"]["AU-AB-SV"] is None
    tc = get_case(kb, "peter").model_copy(deep=True)
    tc.inputs.current.insurer_start = D("2026-03-10")
    ch = build_chain(load_scenario(kb, tc), "13.4", kb)
    assert ch.messages[1].blocks["DBVO"]["AU-AB-SV"] == D("2026-03-10")


@pytest.mark.rules("E-4", "E-5")
def test_e4_and_e5_employer_count_and_end_of_employment(kb):
    from engine.families.vorerkrankung.rules import efz_end
    from engine.rules import params

    p = params.load(kb, version="13.3")
    # E-4: no group counts in the 61, but the employer already paid 42 days for the same illness: no EFZ
    end, t = efz_end(D("2026-06-12"), [], p, own_used=42)
    assert end == D("2026-06-11") and "E-4" in t.rules
    # E-5: the EFZ would run to 23.07., the employment ends on 30.06.
    end, t = efz_end(D("2026-06-12"), [], p, employment_end=D("2026-06-30"))
    assert end == D("2026-06-30") and "E-5" in t.rules
    tc = get_case(kb, "ta-167-r3")
    assert build_chain(load_scenario(kb, tc), "13.3", kb).messages[-1].blocks["DBAL"]["DATUM-EGZBIS"] == D("2026-06-11")
