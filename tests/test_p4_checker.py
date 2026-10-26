from datetime import date

import pytest

from engine.checker import check
from engine.diff import diff
from engine.expected import build_chain, load_scenario
from engine.model import Precedent
from engine.records import parse_file
from engine.writer_messages import chain_files
from tools.make_submissions import SEEDS as SEED_TABLE

D = date.fromisoformat


def _peter(kb):
    ch = build_chain(load_scenario(kb, "peter"), "13.4", kb)
    files = chain_files(ch, "peter", kb)
    return ch, files


def test_diff_reference_vs_generated(kb, itsg_bytes):
    ch, files = _peter(kb)
    actual = parse_file(itsg_bytes, kb).messages + [m for k, t in files.items() if k.startswith("TEEL0") and
                                                    not k.endswith("r1") for m in parse_file(t, kb).messages]
    assert diff(ch.employer(), actual, kb, "13.4") == []
    assert diff(ch.employer(), list(reversed(actual)), kb, "13.4") == []  # matching is not by line order
    no88 = [m for m in actual if m.abgabegrund != "88"]
    d = diff(ch.employer(), no88, kb, "13.4")
    assert [x.kind for x in d] == ["missing_message"]


@pytest.mark.parametrize("sid", [x[0] for x in SEED_TABLE])
def test_seed_labels(kb, sid, seeds):
    s = seeds[sid]
    for valid_on, label in s.expected_label.items():
        res = check(kb, s.test_case_id, list(s.files.values()), D(valid_on))
        assert res.label == label, [(d.label, d.rule, d.signature, d.explanation) for d in res.deviations]
        if label == "bug" and valid_on == max(s.expected_label):
            assert {d.rule for d in res.deviations if d.label == "bug"} == set(s.expected_rules)


def test_invalid_rule(kb, seeds):
    res = check(kb, "peter", list(seeds["s-insurer-field"].files.values()), D("2027-01-01"))
    assert {d.rule for d in res.deviations} == {"F41-6"}


def test_legacy_rule_set_by_date(kb, seeds):
    files = list(seeds["s-legacy-1"].files.values())
    assert check(kb, "peter-gap-exact", files, D("2026-11-01")).version == "13.3"
    res = check(kb, "peter-gap-exact", files, D("2027-01-01"))
    assert res.version == "13.4" and res.deviations[0].rule == "R41-2"
    assert "BVORERK@1#0cefe80e" in res.deviations[0].sources


def test_reused_dsid_and_azvu(kb):
    _, files = _peter(kb)
    r2 = files["TEEL0-peter-r2"].replace("AAAAAAAA-EEEE-2222-4444-BBBBBBBBBBBB", "11111111-2222-AAAA-EEEE-111111111111")
    res = check(kb, "peter", [files["TEEL0-peter-r1"], r2], D("2027-01-01"))
    assert "C-1" in {d.rule for d in res.deviations if d.label == "bug"}
    r3 = files["TEEL0-peter-r3"].replace("1234-5678-007", "1234-5678-999")
    res = check(kb, "peter", [files["TEEL0-peter-r1"], files["TEEL0-peter-r2"], r3], D("2027-01-01"))
    assert "C-2" in {d.rule for d in res.deviations}


def test_letter_in_numeric_is_invalid(kb, itsg_bytes):
    text = itsg_bytes.decode()
    i = text.index("DBVO1") + 6
    res = check(kb, "peter", [text[:i] + "X" + text[i + 1:]], D("2027-01-01"))
    assert res.label == "invalid"


def test_precedent_resolves_without_ai(fresh_kb, seeds):
    kb = fresh_kb
    kb.add_precedent(Precedent(abgabegrund="41", field="DSLW.MM-ANSPRECH", kind="missing_block", verdict="bug",
                               reason="BP 13.1 sends DBAP", justified_by=["BP@13.3#13.1"]))
    calls = []
    res = check(kb, "peter", list(seeds["s-no-contact"].files.values()), D("2027-01-01"),
                triage=lambda d, v: calls.append(d))
    assert res.label == "bug" and calls == []
    assert res.deviations[0].resolved_by == "catalogue" and res.deviations[0].precedent_key


def test_unclear_has_ai_slot(kb, seeds):
    res = check(kb, "peter", list(seeds["s-no-contact"].files.values()), D("2027-01-01"))
    [d] = res.deviations
    assert d.label == "unclear" and d.ai_proposal is None and d.signature == "41|DSLW.MM-ANSPRECH|missing_block"
