"""GG Anlage 2 (Schlüsselzahlen) as allowed codes: read from the document, checked on every message (S-1)."""

from datetime import date

from engine.checker import Checker
from engine.records import parse_file
from engine.rules import formats
from tests.conftest import ITSG_FILE


def test_tables_read_from_anlage_2():
    t = formats.key_values()
    assert set(t) >= {"ABGABEGRUND", "GRUNDBEEND", "EEL-ENDE-GRUND", "ENTGART", "GRUNDAV", "KZ-NACHWEIS", "KZ-AU"}
    assert set(t["GRUNDAV"]["codes"]) == {"1", "2", "3"} and t["GRUNDAV"]["records"] == ["DBVO"]
    assert set(t["KZ-NACHWEIS"]["codes"]) == {"1", "2", "4"}  # 3 is not a code
    assert t["ABGABEGRUND"]["codes"]["88"] == "Stornierung eines Datensatzes"
    assert t["GRUNDAV"]["source"] == "GG-ANL2@13.0#10"


def _with_grundav(kb, code: str) -> str:
    text = ITSG_FILE.read_text(encoding="utf-8")
    rec = next(m for m in parse_file(text, kb, "13.3").messages if m.abgabegrund == "41")
    fv = rec.blocks["DBVO"].fields["GRUNDAV"]
    lines = text.splitlines(keepends=True)
    line = lines[rec.line_no - 1]
    lines[rec.line_no - 1] = line[: fv.pos - 1] + code + line[fv.pos - 1 + len(code):]
    return "".join(lines)


def test_itsg_file_passes(kb):
    msgs = parse_file(ITSG_FILE.read_text(encoding="utf-8"), kb, "13.3").messages
    assert all(formats.check_key_values(m) == [] for m in msgs)


def test_unknown_code_is_invalid(kb):
    rec = next(m for m in parse_file(_with_grundav(kb, "7"), kb, "13.3").messages if m.abgabegrund == "41")
    [r] = formats.check_key_values(rec)
    assert r.rule == "S-1" and r.field == "DBVO.GRUNDAV" and r.actual == "7"
    res = Checker(kb).check("peter", [_with_grundav(kb, "7")], date(2026, 11, 1))
    # on the 41 the stricter F41-4 (GRUNDAV must be 1) wins: one finding per field, invalid either way
    d = next(d for d in res.deviations if d.record == "DBVO" and d.field == "GRUNDAV")
    assert d.label == "invalid" and d.rule in ("F41-4", "S-1")
