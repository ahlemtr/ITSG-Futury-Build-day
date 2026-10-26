from pathlib import Path

import yaml

from engine import layouts

ROOT = Path(__file__).resolve().parents[1]


def test_layouts_load():
    files = list((ROOT / "layouts").glob("*.yaml"))
    assert len(files) == 20
    for f in files:
        assert yaml.safe_load(f.read_text(encoding="utf-8"))["record"] == f.stem


def test_itsg_file_present():
    assert (ROOT / "fixtures/itsg/TEEL0-Test1-DBVO").exists()


def test_layout_view(kb):
    """Repeating group, block order and MM flags derived from the KG's flat layouts."""
    dbvo = layouts.get(kb, "DBVO", "13.4")
    g = dbvo.repeating_group
    assert (g.count_field, g.starts_at, g.group_length) == ("ANZAHL-AU", 33, 50)
    assert [f.name for f in g.fields][:2] == ["BEGINN-AU", "ENDE-AU"] and len(dbvo.fields) == 7
    dslw = layouts.get(kb, "DSLW", "13.4")
    assert dslw.block_order[:3] == ["DBNA", "DBAN", "DBAL"] and dslw.block_order[-1] == "DBSD"
    assert dslw.flags["DBVO"] == "MM-VOER" and dslw.flags["DBAP"] == "MM-ANSPRECH"
