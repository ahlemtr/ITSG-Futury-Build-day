"""TA 167 against ITSG's solution (TEEK0521/0523/0524 and the workbook, local only: skipped when missing)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from engine.checker import check
from engine.expected import build_chain, load_scenario
from engine.records import parse_file
from engine.writer_messages import write_file

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "fixtures/itsg/ta-167"
ROUNDS = {"ta-167-r1": "TEEK0521_167_2026-01", "ta-167-r2": "TEEK0523_167_2026-03", "ta-167-r3": "TEEK0524_167_2026-06"}
VALID_ON = {"ta-167-r1": date(2026, 1, 1), "ta-167-r2": date(2026, 2, 2), "ta-167-r3": date(2026, 6, 12)}
# fields ITSG fills its own way: file creation, its record IDs, its file number; REFERENZ-ID it leaves blank
# (its own note); 12-MONATSFRIST-AB is the documented contradiction (tests/test_locked.py, xfail). DBAP is not graded
# (kg/seed/compare_modes.yaml) and ITSG's own replies spell the insurer two ways ("Test ITSG" / "Test-ITSG").
NOT_COMPARED = {"DSLW.DATUM-ERSTELLUNG", "DSLW.DATENSATZ-ID", "DBID.AKTENZEICHEN-SV", "DBID.REFERENZ-ID",
                "DBVO.12-MONATSFRIST-AB"}

pytestmark = pytest.mark.skipif(not DIR.exists(), reason="ITSG's TA 167 solution is local only (not published)")


def _itsg(kb, case):
    return parse_file((DIR / ROUNDS[case]).read_bytes(), kb, "13.3")


@pytest.mark.parametrize("case", ROUNDS)
def test_teek0_parses(kb, case):
    pf = _itsg(kb, case)
    assert pf.issues == [] and [m.abgabegrund for m in pf.messages] == ["61"]


@pytest.mark.parametrize("case", ROUNDS)
@pytest.mark.rules("K61-8")
def test_simulated_61_equals_itsg(kb, case):
    ch = build_chain(load_scenario(kb, case), "13.3", kb)
    m61 = next(m for m in ch.messages if m.abgabegrund == "61")
    ours = parse_file(write_file([m61], kb), kb, "13.3").messages[0].values()
    theirs = _itsg(kb, case).messages[0].values()
    diff = {k: (ours.get(k), theirs.get(k)) for k in set(ours) | set(theirs)
            if k not in NOT_COMPARED and not k.startswith("DBAP.") and ours.get(k) != theirs.get(k)}
    assert diff == {}
    assert ours["DBVO.AU-AB-SV"] is None  # K61-8: same start as the employer's, so Grundstellung


def _41(kb, case, periods):
    """A 41 as ITSG's workbook writes it (EEL sheet): the case's head, our layout, ITSG's periods."""
    m = build_chain(load_scenario(kb, case), "13.3", kb).messages[0].model_copy(deep=True)
    keep = {(g["BEGINN-AU"], g["ENDE-AU"]): g for g in m.blocks["DBVO"]["groups"]}
    groups = []
    for s, e in periods:
        g = dict(next(iter(keep.values())))
        g.update({"BEGINN-AU": date.fromisoformat(s), "ENDE-AU": date.fromisoformat(e)})
        groups.append(g)
    m.blocks["DBVO"]["groups"] = groups
    return write_file([m], kb)


WORKBOOK_41 = {  # EEL sheet, rows 72-76 (round 2) and 149-156 (round 3)
    "ta-167-r2": [("2025-12-05", "2026-01-23"), ("2025-08-13", "2025-09-12")],
    "ta-167-r3": [("2026-02-02", "2026-02-20"), ("2025-12-05", "2026-01-23"), ("2025-08-13", "2025-09-12")],
}


@pytest.mark.parametrize("case", WORKBOOK_41)
def test_workbook_41_has_no_bug(kb, case):
    res = check(kb, case, [_41(kb, case, WORKBOOK_41[case])], VALID_ON[case])
    assert not [d for d in res.deviations if d.step == 1 and d.label in ("bug", "invalid")], res.deviations


@pytest.mark.parametrize(("case", "periods"), [
    ("ta-167-r2", [("2025-12-05", "2026-01-23")]),  # rejected AU left out (ANZAHL-AU 01)
    ("ta-167-r2", [("2025-12-06", "2026-01-23"), ("2025-08-13", "2025-09-12")]),  # 06.12. instead of 05.12.
    ("ta-167-r3", [("2026-02-02", "2026-02-20")]),  # both optional periods left out
])
def test_allowed_variants_are_variants(kb, case, periods):
    res = check(kb, case, [_41(kb, case, periods)], VALID_ON[case])
    step1 = [d for d in res.deviations if d.step == 1]
    assert step1 and all(d.label == "correct_variant" for d in step1), [(d.label, d.signature) for d in step1]
    assert all(d.explanation.startswith("zulässige Variante dieses Testfalls") for d in step1)
