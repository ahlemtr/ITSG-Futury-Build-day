import shutil
from datetime import date
from pathlib import Path

import pytest

from engine import builder, runs, specdiff
from engine.expected import build_chain, load_scenario
from engine.records import parse_file
from engine.writer_messages import chain_files

ROOT = Path(__file__).resolve().parents[1]
VB133 = ROOT / "sources/2025_11_24_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.3.pdf"
VB134 = ROOT / "sources/2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf"
D = date.fromisoformat


@pytest.fixture(scope="module")
def vb_changes():
    if not shutil.which("pdftotext") or not VB134.exists():
        pytest.skip("pdftotext or VB PDFs not available")
    return specdiff.diff_pdfs(VB133, VB134, "VB-13.3-13.4")


def test_specdiff(vb_changes):
    by = lambda blk, words: [c for c in vb_changes if c.block == blk and words in c.old + c.new]
    dbvo = by("DBVO", "nicht mindestens 6 Monate")
    assert dbvo and "nicht mehr als 6 Monate" in dbvo[0].new
    assert any(c.field == "VORNAME" for c in by("DBSD", "Vorname"))
    assert by("DBEE", "Beschäftigungsverhältnis") or by("DBEE", "Ende eines Be")
    assert any(c.field == "BBNR-VU" for c in vb_changes if c.block == "DSLW")
    assert specdiff.layout_rows_changed(vb_changes) == []
    assert not any("...." in c.old + c.new for c in vb_changes)  # TOC ignored


def test_impact(kb):
    imp = specdiff.impact(["VB-13.3-13.4-DBVO-chaining"], kb)
    assert {r.id for r in imp.recompute} == {"R41-2", "R41-3"} and len(imp.tests) == 8


def test_recompute(kb):
    ids = [t.id for t in kb.get_test_cases(include_hidden=True)]
    diff = [r.id for r in builder.recompute(kb, ids, "13.3", "13.4") if r.differs]
    assert sorted(diff) == ["peter-gap-exact", "peter-gap-exact-hidden"]


def test_boundaries(kb):
    b = builder.boundaries(kb, "R41-4", "peter")
    assert [t.id for t in b] == ["peter-b27", "peter-b28", "peter-b29", "peter-b30"]
    for t in b:
        ref = kb.get_test_case(t.id)
        assert t.inputs.current == ref.inputs.current and t.status == "draft"
        assert {v: e.send_41 for v, e in t.expected.items()} == {v: e.send_41 for v, e in ref.expected.items()}
    g = {t.id: t for t in builder.boundaries(kb, "R41-2", "peter")}
    assert set(g) == {"peter-gap-in", "peter-gap-exact", "peter-gap-out"}
    for k, t in g.items():
        ref = kb.get_test_case(k)
        assert t.inputs.priors == ref.inputs.priors and t.parent == "peter"
        assert {v: e.send_41 for v, e in t.expected.items()} == {v: e.send_41 for v, e in ref.expected.items()}
    assert len(builder.boundaries(kb, "R41-3", "peter")) == 3


def test_package(kb):
    files = builder.package(kb, kb.get_test_case("peter-gap-exact"), "13.4")
    assert sorted(files) == ["TEEK0-peter-gap-exact-s2-61", "TEEL0-peter-gap-exact-r1", "scenario.yaml", "story.txt"]
    assert builder.package_zip(files)[:2] == b"PK"
    with pytest.raises(PermissionError):
        builder.package(kb, kb.get_test_case("peter-gap-exact-hidden"), "13.4")


def test_hidden(kb):
    h = builder.hidden(kb, "peter-gap-exact", seed=0)
    assert h.id == "peter-gap-exact-hidden" and h.hidden
    assert (h.inputs.priors[0].start, h.inputs.priors[0].end) == (D("2025-07-27"), D("2025-08-31"))
    assert (h.inputs.current.start, h.inputs.current.end) == (D("2026-02-28"), D("2026-03-09"))
    assert not h.expected["13.3"].send_41 and h.expected["13.4"].send_41
    p = builder.hidden(kb, "peter", seed=1)
    assert p.expected["13.4"].send_41 and p.inputs.current.start != D("2026-03-11")


def _vendor_files(kb, tc="peter"):
    ch = build_chain(load_scenario(kb, tc), "13.4", kb)
    return {k: v for k, v in chain_files(ch, tc, kb).items() if k.startswith("TEEL0")}


def test_peter_four_rounds(kb):
    st, story = runs.start(kb, "peter", D("2027-01-01"))
    assert "11.03.2026" in story and st.last_round == 4
    f = _vendor_files(kb)
    r1 = runs.submit(kb, st, [f["TEEL0-peter-r1"]])
    k61 = parse_file(r1.reply, kb).messages[0]
    assert k61.abgabegrund == "61" and k61.get("DBID.REFERENZ-ID") == "11111111-2222-AAAA-EEEE-111111111111"
    r2 = runs.submit(kb, st, [f["TEEL0-peter-r2"]])
    assert parse_file(r2.reply, kb).messages[0].abgabegrund == "61"
    r3 = runs.submit(kb, st, [f["TEEL0-peter-r3"]])
    k62 = parse_file(r3.reply, kb).messages[0]
    assert k62.get("DBID.REFERENZ-ID") == "11112222-FFFF-3333-5555-CCCCCCCCCCCC"
    runs.submit(kb, st, [])
    v = runs.verdict(st)
    assert v["status"] == "passed" and v["rounds"] == 4, v


def test_reply_uses_vendor_dsid(kb):
    st, _ = runs.start(kb, "peter", D("2027-01-01"))
    r1 = _vendor_files(kb)["TEEL0-peter-r1"].replace("11111111-2222-AAAA-EEEE-111111111111",
                                                     "ABCDEF01-2222-AAAA-EEEE-111111111111")
    rep = runs.submit(kb, st, [r1])
    assert parse_file(rep.reply, kb).messages[0].get("DBID.REFERENZ-ID") == "ABCDEF01-2222-AAAA-EEEE-111111111111"


def test_missing_41_ends_run(kb):
    st, _ = runs.start(kb, "peter", D("2027-01-01"))
    res = runs.submit(kb, st, [])
    assert res.ended and st.status == "failed" and res.reply is None


def test_hidden_verdict_has_no_values(kb):
    st, _ = runs.start(kb, "peter-gap-exact-hidden", D("2027-01-01"))
    runs.submit(kb, st, [])
    v = runs.verdict(st)
    assert v["status"] == "failed"
    assert all(set(r) == {"rule", "outcome"} for r in v["rules"])
    assert {"rule": "R41-2", "outcome": "fail"} in v["rules"]
