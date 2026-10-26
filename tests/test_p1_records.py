from datetime import date
from decimal import Decimal

from engine import layouts
from engine.records import parse_file, record_to_dicts, to_value, write_dslw, write_file


def test_parse_itsg_file(kb, itsg_bytes):
    pf = parse_file(itsg_bytes, kb)
    assert pf.issues == []
    [m] = pf.messages
    assert m.abgabegrund == "41"
    assert m.get("DBVO.AU-AB-AG") == date(2026, 3, 11)
    assert m.periods == [(date(2026, 3, 1), date(2026, 3, 3)), (date(2025, 12, 1), date(2025, 12, 3)),
                         (date(2025, 10, 1), date(2025, 10, 17)), (date(2025, 7, 14), date(2025, 7, 15))]
    assert m.get("DBID.AKTENZEICHEN-VERURSACHER") == "1234-5678-007"
    assert m.get("DBNA.FAMILIENNAME") == "Mustermann"
    assert set(m.blocks) == {"DBNA", "DBVO", "DBAP", "DBID"}
    assert m.tail == ""


def test_typed_values(kb):
    amt = layouts.get(kb, "DBAE", "13.4").field("BRUTTO-1")
    dt = layouts.get(kb, "DBVO", "13.4").field("AU-AB-AG")
    assert to_value(amt, "00135384")[0] == Decimal("1353.84")
    assert to_value(dt, "00000000")[0] is None


def test_round_trip_byte_identical(kb, itsg_bytes):
    pf = parse_file(itsg_bytes, kb)
    assert write_file(pf, kb).encode(pf.encoding) == itsg_bytes
    head, blocks = record_to_dicts(pf.messages[0])
    assert write_dslw(head, blocks, kb) == pf.messages[0].raw


def test_corrupt_digit_gives_one_issue(kb, itsg_bytes):
    text = itsg_bytes.decode("utf-8")
    i = text.index("DBVO1") + 6  # inside AU-AB-AG
    bad = text[:i] + "X" + text[i + 1:]
    pf = parse_file(bad, kb)
    assert len(pf.issues) == 1 and pf.issues[0].field == "AU-AB-AG"


def test_encodings(kb, itsg_bytes):
    text = itsg_bytes.decode("utf-8")
    latin = text.encode("latin-1")
    a, b = parse_file(itsg_bytes, kb), parse_file(latin, kb)
    assert b.encoding == "latin-1" and a.issues == b.issues == []
    assert a.messages[0].get("DBAP.FIRMA-2") == b.messages[0].get("DBAP.FIRMA-2")


def test_unknown_block_is_an_issue(kb, itsg_bytes):
    text = itsg_bytes.decode("utf-8")
    i = text.index("N41001J") + 7
    bad = text[:i] + "J" + text[i + 1:]  # MM-ANSCHRIFT = J, no DBAN layout
    pf = parse_file(bad, kb)
    assert any("DBAN" in x.message for x in pf.issues)
