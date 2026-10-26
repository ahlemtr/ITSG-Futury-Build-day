from datetime import date

from engine.expected import build_chain, load_scenario
from engine.records import parse_file
from engine.writer_messages import chain_files, write_file

D = date.fromisoformat


def test_scenarios_load(kb):
    for t in kb.get_test_cases(include_hidden=True):
        sc = load_scenario(kb, t.id)
        assert sc.extras["person"]["familienname"] == "Mustermann"


def test_peter_chain(kb):
    ch = build_chain(load_scenario(kb, "peter"), "13.4", kb)
    assert [m.abgabegrund for m in ch.messages] == ["41", "61", "01", "61", "88", "01", "62"]
    assert ch.efz == {"after_first_61": D("2026-03-30"), "after_corrected_61": D("2026-03-27")}
    assert [m.round for m in ch.messages] == [1, 1, 2, 2, 3, 3, 3]
    assert ch.messages[-1].blocks["DBEE"]["EEL-ENDE"] == D("2026-03-31")


def test_gap_exact_flips(kb):
    sc = load_scenario(kb, "peter-gap-exact")
    assert build_chain(sc, "13.3", kb).messages == []
    m = build_chain(sc, "13.4", kb).messages
    assert len(m) == 1 and len(m[0].blocks["DBVO"]["groups"]) == 1


def test_generated_41_equals_itsg_file(kb, itsg_bytes):
    ch = build_chain(load_scenario(kb, "peter"), "13.4", kb)
    gen = parse_file(write_file([ch.messages[0]], kb), kb).messages[0]
    ref = parse_file(itsg_bytes, kb).messages[0]
    assert gen.raw == ref.raw  # identical, so equal on every compare field too


def test_files_parse(kb):
    files = chain_files(build_chain(load_scenario(kb, "peter"), "13.4", kb), "peter", kb)
    assert len(files) == 6  # 3 TEEL0 rounds, 3 TEEK0 replies
    for text in files.values():
        pf = parse_file(text, kb)
        assert pf.issues == [] and pf.messages
    r3 = parse_file(files["TEEL0-peter-r3"], kb).messages
    assert [m.abgabegrund for m in r3] == ["88", "01"]
    k61 = parse_file(files["TEEK0-peter-s2-61"], kb).messages[0]
    assert k61.get("DBID.REFERENZ-ID") == "11111111-2222-AAAA-EEEE-111111111111"
    assert k61.get("DBVO.12-MONATSFRIST-AB") == D("2025-07-14")
