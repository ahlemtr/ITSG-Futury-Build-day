"""Record layouts follow the case's validity date: VB Anlage 1 13.1.4 applies from 01.07.2027, mid-year (G2)."""

from datetime import date

from engine import layouts
from engine.checker import check


def test_anlage_1_version_by_date(kb):
    assert kb.get_layout("DSLW", "13.3").layout_version == "VB-ANL1@13.1.3"
    assert kb.get_layout("DSLW", "13.4").layout_version == "VB-ANL1@13.1.3"  # VB 13.4 starts 01.01.2027
    assert kb.get_layout("DSLW", "13.4", on_date=date(2027, 6, 30)).layout_version == "VB-ANL1@13.1.3"
    late = kb.get_layout("DSLW", "13.4", on_date=date(2027, 7, 1))
    assert late.layout_version == "VB-ANL1@13.1.4"
    assert all("13.1.4" in f.definition_source for f in late.fields if f.definition_source and
               f.definition_source.startswith("VB-ANL1"))


def test_engine_reads_the_layout_of_the_day(kb, itsg_bytes):
    assert layouts.get(kb, "DBVO", "13.4", date(2027, 7, 1)).layout_version == "VB-ANL1@13.1.4"
    assert layouts.get(kb, "DBVO", "13.4", date(2027, 1, 1)).layout_version == "VB-ANL1@13.1.3"
    # same structure in both: ITSG's file parses the same way on both sides of the switch
    assert check(kb, "peter", [itsg_bytes], date(2027, 7, 1)).parse_issues == []
