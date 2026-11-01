"""VB Anlage 3 chapter 3: continuity of benefits (rules A3-2, A3-3)."""

from datetime import date

import pytest

from engine.rules.continuity import new_certificate, verdict

D = date.fromisoformat


def test_table_rows_as_printed():
    assert verdict("01", "04") == "none" and verdict("01", "11") == "none" and verdict("01", "21") == "none"
    assert verdict("01", "02") == "required" and verdict("04", "03") == "required"
    assert verdict("31", "21") == "required" and verdict("22", "01") == "none"
    assert verdict("21", "12") == "none" and verdict("21", "21") == "none"
    assert verdict("02", "02") == "same_child" and verdict("23", "23") == "same_child"
    assert verdict("02", "01") == "required" and verdict("23", "21") == "required"
    assert all(verdict("03", c) == "required" for c in ("01", "11", "21", "02", "23"))
    assert verdict("03", "03") == "impossible"


@pytest.mark.rules("A3-2")
def test_one_gap_day_always_needs_a_new_certificate():
    seamless = new_certificate("01", D("2026-03-31"), "01", D("2026-04-01"))
    assert seamless.new_certificate is False and seamless.rule == "A3-3"
    gap = new_certificate("01", D("2026-03-31"), "01", D("2026-04-02"))  # 01.04 in between
    assert gap.new_certificate is True and gap.rule == "A3-2"
    with pytest.raises(ValueError):
        new_certificate("01", D("2026-03-31"), "01", D("2026-03-31"))


@pytest.mark.rules("A3-3")
def test_directly_following_benefits():
    assert new_certificate("01", D("2026-03-31"), "21", D("2026-04-01")).new_certificate is False
    assert new_certificate("21", D("2026-03-31"), "01", D("2026-04-01")).new_certificate is False
    assert new_certificate("11", D("2026-03-31"), "21", D("2026-04-01")).new_certificate is True
    assert new_certificate("01", D("2026-03-31"), "03", D("2026-04-01")).new_certificate is True
    assert new_certificate("02", D("2026-03-31"), "02", D("2026-04-01"), same_child=True).new_certificate is False
    assert new_certificate("02", D("2026-03-31"), "02", D("2026-04-01"), same_child=False).new_certificate is True
    with pytest.raises(ValueError):
        new_certificate("02", D("2026-03-31"), "02", D("2026-04-01"))
    assert new_certificate("01", D("2026-03-31"), "01", D("2026-04-01"), organ_donation=True).new_certificate is True
    assert new_certificate("03", D("2026-03-31"), "03", D("2026-04-01")).new_certificate is None
    with pytest.raises(ValueError):
        new_certificate("41", D("2026-03-31"), "01", D("2026-04-01"))
