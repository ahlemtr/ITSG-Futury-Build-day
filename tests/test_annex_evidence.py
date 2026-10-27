"""Cross-document evidence, applicability and fixed-width round trips."""

from collections import Counter

from engine.records import format_value, parse_file, to_value, write_file
from kg.field_evidence import classify


def test_vb_annex_centered_chapters_work_with_linux_poppler_indentation():
    from kg.extract import generic
    from kg.extract.pdf_text import Line

    lines = [Line(0, 3, "                    1 Änderungsprotokoll zur Anlage 1"),
             Line(1, 3, "Historie"), Line(2, 4, "                    2 Datensatz VOSZ - Vorlaufsatz"),
             Line(3, 4, "Einleitung"), Line(4, 6, "                    3 Datensatz DSKO - Kommunikation"),
             Line(5, 6, "Bedingungen")]
    sections = generic.split("VB-ANL1", "13.1.3", lines, 2, lambda msg: None)
    assert {p["section"] for p in sections} == {"1", "2", "3"}


def test_requirement_scope_is_not_a_structural_conflict():
    assert classify("required", "m", "M") == "requirement_scope"
    assert classify("required", "M", "m") == "requirement_scope"
    assert classify("type", "an", "n") == "representation_scope"
    assert classify("length", 20, 61) == "structure_difference"


def test_all_annex_rows_keep_source_cells_and_conditions(kb):
    rows = [p for (label, _), p in kb.nodes.items() if label == "FieldDefinition"]
    counts = Counter(d["document_version"] for d in rows)
    assert counts["GG-ANL1@13.1.1"] == 289
    assert counts["VB-ANL1@13.1.3"] == 289
    assert counts["VB-ANL1@13.1.4"] == 289
    for d in rows:
        assert d["extraction"] == "pdf_table_cells"
        assert d["length"] == d["end"] - d["start"] + 1
        assert d["source_name"]
        if d["required"] == "m":
            assert d["condition_status"] == "source_prose"
            assert d["condition_text"] == d["explanation"]


def test_complementary_markers_both_survive(kb):
    definitions = kb.get_field_definitions("DBAE", "BRUTTO-1", version="13.3")
    by_doc = {d["doc"]: d for d in definitions if d["applicable"]}
    assert by_doc["VB"]["required"] == "M"
    assert by_doc["GG-ANL1"]["required"] == "m"
    layout = kb.get_layout("DBAE", "13.3")
    gross = next(f for f in layout.fields if f.name == "BRUTTO-1")
    assert gross.required == "m"
    assert gross.definition_source.startswith("VB-ANL1@13.1.3#")
    links = kb.subgraph("FieldDefinition", by_doc["VB"]["key"], 1).edges
    assert any(e.type == "COMPLEMENTS" and not e.props["automatic_conflict"] for e in links)


def test_annex_revision_selected_by_effective_date(kb):
    current = kb.get_field_definitions("DBAE", "BRUTTO-1", version="13.4")
    assert any(d["document_version"] == "VB-ANL1@13.1.3" and d["applicable"] for d in current)
    assert not any(d["document_version"] == "VB-ANL1@13.1.4" and d["applicable"] for d in current)
    later = kb.get_field_definitions("DBAE", "BRUTTO-1", on_date="2027-07-01")
    assert any(d["document_version"] == "VB-ANL1@13.1.4" and d["applicable"] for d in later)
    assert not any(d["document_version"] == "VB-ANL1@13.1.3" and d["applicable"] for d in later)


def test_version_filtered_search_keeps_future_annex_out(kb):
    hits = kb.search_passages("BRUTTO-1", k=20, version="13.3")
    assert hits
    assert all(not p.key.startswith(("VB@13.4#", "VB-ANL1@13.1.4#")) for p in hits)
    assert any(p.key.startswith("VB-ANL1@13.1.3#") for p in hits)


def test_technical_alphanumeric_fields_preserve_content(kb):
    layout = kb.get_layout("DBUN", "13.3")
    ikuv = next(f for f in layout.fields if f.name == "IKUV")
    assert ikuv.type == "an"
    raw = format_value(ikuv, "00123AB")
    assert to_value(ikuv, raw) == ("00123AB", None)
    assert len(raw) == 15


def test_name_fields_have_independent_round_trip_and_block_context(kb, itsg_bytes):
    parsed = parse_file(itsg_bytes, kb)
    assert not parsed.issues
    assert write_file(parsed, kb).encode(parsed.encoding) == itsg_bytes
    layout = kb.get_layout("DBNA", "13.3")
    fields = {f.name: f for f in layout.fields}
    assert "UNKLAR" not in fields
    assert [(fields[n].start, fields[n].length) for n in
            ("VORSATZWORT", "NAMENSZUSATZ", "TITEL", "KENNZ-AEND-BER")] == [(65, 20), (85, 20), (105, 20), (125, 1)]
    for name, value in (("VORSATZWORT", "von"), ("NAMENSZUSATZ", "der"), ("TITEL", "Dr.")):
        assert to_value(fields[name], format_value(fields[name], value)) == (value, None)
    definition = next(d for d in kb.get_field_definitions("DBNA", "KENNZ-AEND-BER")
                      if d["doc"] == "GG-ANL1")
    sub = kb.subgraph("FieldDefinition", definition["key"], 1)
    assert any(e.type == "IN_CONTEXT" and e.to_key == "GG-ANL1@13.1.1#5" for e in sub.edges)
    assert "nur Grundstellung" in kb.get_passage("GG-ANL1@13.1.1#5").text
