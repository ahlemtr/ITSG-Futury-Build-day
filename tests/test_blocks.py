"""VB Anlage 3 chapter 2: data blocks per Abgabegrund (rule A3-1, every family)."""

from datetime import date

import pytest

from engine.checker import check
from engine.expected import build_chain, load_scenario
from engine.rules import blocks
from engine.writer_messages import write_file

D = date.fromisoformat


def test_table_covers_all_22_codes():
    t = blocks.block_table()
    assert len(t) == 22 and all(len(row) == 19 for row in t.values())
    assert t["41"]["DBVO"] == "J" and t["41"]["DBAP"] == "J" and t["41"]["DBID"] == "m" and t["41"]["DBUN"] == "N"
    assert t["88"] == {b: ("J" if b == "DBSD" else "N") for b in t["88"]}
    assert t["03"]["DBMU"] == "J" and t["02"]["DBFR"] == "J" and t["51"]["DBBE"] == "J"
    assert {code for code, row in t.items() if row["DBID"] == "J"} == {"51", "61", "62", "66", "67", "71", "72", "73"}


def test_graph_has_no_unknown_blocks(kb):
    ctx = kb.get_deviation_context("DSLW", "MM-ANSPRECH", "41", "13.4")
    assert ctx.flagged_blocks and all(b.presence in ("J", "m") for b in ctx.flagged_blocks)


@pytest.mark.rules("A3-1")
def test_missing_mandatory_block_is_invalid(kb, seeds):
    res = check(kb, "peter", list(seeds["s-no-contact"].files.values()), D("2027-01-01"))
    [d] = res.deviations
    assert d.label == "invalid" and d.rule == "A3-1" and d.signature == "41|DSLW.MM-ANSPRECH|missing_block"
    assert "VB-ANL3@13.3#2" in d.sources


@pytest.mark.rules("A3-1")
def test_forbidden_block_is_invalid(kb):
    ch = build_chain(load_scenario(kb, "peter"), "13.4", kb)
    m41 = ch.messages[0].model_copy(deep=True)
    m41.blocks["DBEE"] = {"EEL-ABAG": D("2026-03-11")}  # DBEE is N on a 41
    res = check(kb, "peter", [write_file([m41], kb)], D("2027-01-01"))
    d = next(d for d in res.deviations if d.field == "MM-EELENDE")
    assert d.label == "invalid" and d.rule == "A3-1"
