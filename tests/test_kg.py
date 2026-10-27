"""Step K11 (08 section 14): every test runs against both backends."""

from __future__ import annotations

import datetime as dt
import shutil

import pytest

from engine.model import Precedent
from kg import seed_graph, validate
from kg.common import BUILD_DIR, LAYOUT_DIR, SEED_DIR

BACKENDS = ["yaml", "graph"]
CHAINING = "VB-13.3-13.4-DBVO-chaining"


@pytest.fixture(scope="session")
def yaml_kb(passages_built, tmp_path_factory):
    from kg.yaml_backend import YamlBackend

    # precedents go to a temp file, so tests never touch kg/seed/precedents.yaml
    return YamlBackend(precedents_path=tmp_path_factory.mktemp("kg") / "precedents.yaml")


@pytest.fixture(scope="session")
def graph_kb(neo4j_driver):
    from kg.graph_backend import GraphBackend

    return GraphBackend(neo4j_driver)


@pytest.fixture(params=BACKENDS)
def kb(request):
    return request.getfixturevalue(f"{request.param}_kb")


# ---------------------------------------------------------------- section 14 table

def test_param_by_date(kb):
    assert kb.get_param("gap_inclusive", on_date=dt.date(2026, 11, 1)) is False
    assert kb.get_param("gap_inclusive", on_date=dt.date(2027, 1, 1)) is True


def test_param_simulated_only_by_version(kb):
    assert kb.get_param("min_total_days", version="sim-13.5") == 28
    assert kb.get_param("min_total_days", on_date=dt.date(2028, 6, 1)) == 30


def test_layout_dbvo(kb):
    layout = kb.get_layout("DBVO", "13.4")
    assert len(layout.fields) == 15
    by_name = {f.name: f for f in layout.fields}
    assert by_name["BEGINN-AU"].repeating and by_name["BEGINN-AU"].key == "DBVO.BEGINN-AU"
    assert sum(f.repeating for f in layout.fields) == 8
    starts = [f.start for f in layout.fields]
    assert starts == sorted(starts)


def test_rules_41_under_13_3(kb):
    rules = kb.get_rules("41", "13.3")
    expected = [f"R41-{i}" for i in range(1, 7)] + [f"F41-{i}" for i in range(1, 11)] + ["C-1", "C-2", "S-1"]
    assert [r.id for r in rules] == expected
    sources = [s for r in rules for s in r.sources]
    assert not [s for s in sources if s.startswith("VB@13.4")]
    assert any(s.startswith("VB@13.3") for s in sources)
    assert next(r for r in rules if r.id == "R41-2").criterion == "0cefe80e-4fd9-41e1-be4f-3ae1ecbde646"


def test_affected_rules_chaining(kb):
    impact = kb.get_affected_rules([CHAINING])
    assert {r.id for r in impact.recompute} == {"R41-2", "R41-3"}
    assert {t.key for t in impact.tests} == {
        "peter", "peter-gap-exact", "peter-gap-in", "peter-gap-out", "peter-hidden", "peter-gap-exact-hidden",
        "bp-13-2", "bp-13-3",
    }
    review = {r.id for r in impact.review}
    assert not review & {"R41-2", "R41-3"}


def test_test_case_expected(kb):
    tc = kb.get_test_case("peter-gap-exact")
    assert tc.expected["13.3"]["send_41"] is False
    assert tc.expected["13.4"]["send_41"] is True
    assert tc.expected["13.4"]["periods"] == [["2025-08-07", "2025-09-11"]]
    assert tc.parent == "peter" and tc.kind == "clone"


def test_passage_chaining_13_4(kb):
    assert "nicht mehr als 6 Monate" in kb.get_passage("VB@13.4#3.12/chaining").text


def test_passage_insurer_13_4_keeps_old_wording(kb):
    assert "nicht mindestens 6 Monate" in kb.get_passage("VB@13.4#3.12/insurer").text


def test_precedent_round_trip(kb):
    signature = "41|DBVO.KZ-AU|order_differs"
    if kb.find_precedent(signature) is not None:
        pytest.skip(f"a real precedent {signature} exists, not overwriting it")
    p = Precedent(abgabegrund="41", field="DBVO.KZ-AU", kind="order_differs", verdict="correct_variant",
                  reason="test precedent", advisor="pytest", decided=dt.date(2026, 10, 26),
                  justified_by=["F41-9", "VB@13.4#3.12.12"])
    try:
        kb.add_precedent(p)
        found = kb.find_precedent(signature)
        assert found is not None and found.model_dump() == p.model_dump()
        ctx = kb.get_deviation_context("DBVO", "KZ-AU", "41", "13.4")
        assert signature in [x.key for x in ctx.precedents]
    finally:
        kb.remove_precedent(signature)
    assert kb.find_precedent(signature) is None


def test_build_twice_identical_counts(passages_built):
    first = seed_graph.counts(seed_graph.build())
    second = seed_graph.counts(seed_graph.build())
    assert first == second


def test_load_twice_identical_counts(passages_built, neo4j_driver):
    from kg import load

    graph = seed_graph.build()
    load.load(graph, neo4j_driver)
    first = load.db_counts(neo4j_driver)
    load.load(graph, neo4j_driver)
    second = load.db_counts(neo4j_driver)
    assert first == second
    nodes, _edges = seed_graph.counts(graph)
    assert all(first[0][label] >= n for label, n in nodes.items())


def test_validation_names_rule_and_field_typo(passages_built, tmp_path):
    seed = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed)
    rules = (seed / "rules.yaml").read_text(encoding="utf-8")
    typo = rules.replace("fields: [DBVO.BEGINN-AU, DBVO.ENDE-AU, DBVO.AU-AB-AG]",
                         "fields: [DBVO.BEGIN-AU, DBVO.ENDE-AU, DBVO.AU-AB-AG]", 1)
    assert typo != rules
    (seed / "rules.yaml").write_text(typo, encoding="utf-8")
    errors, _ = validate.validate(seed_graph.build(seed, LAYOUT_DIR, BUILD_DIR / "passages.yaml"))
    assert any("R41-2" in e and "DBVO.BEGIN-AU" in e for e in errors), errors


def test_clean_seed_validates(passages_built):
    errors, _ = validate.validate(seed_graph.build())
    assert errors == []


# ---------------------------------------------------------------- section 13 "must answer"

def test_versions_vb(kb):
    versions = kb.get_versions("VB")
    assert [(v.version, v.valid_from) for v in versions] == [("13.3", dt.date(2026, 1, 1)),
                                                             ("13.4", dt.date(2027, 1, 1))]
    assert versions[1].succeeds == "13.3"


def test_changes_in_scope(kb):
    changes = kb.get_changes("VB", "13.3", "13.4")
    assert {c.key for c in changes} == {
        CHAINING, "VB-13.3-13.4-BBNR-VU", "VB-13.3-13.4-DBID-AZVU", "VB-13.3-13.4-DBSD-names",
        "VB-13.3-13.4-DBEE-end",
    }
    chaining = next(c for c in changes if c.key == CHAINING)
    assert chaining.changes_param == ["gap_inclusive"] and chaining.label == "editorial"
    assert chaining.derived_from == ["VB-13.3-13.4-059"]
    assert len(kb.get_changes("VB", "13.3", "13.4", in_scope_only=False)) == 67 + 5


def test_raw_change_links_to_narrowest_passage(kb):
    raw = next(c for c in kb.get_changes("VB", "13.3", "13.4", in_scope_only=False) if c.key == "VB-13.3-13.4-059")
    assert raw.modifies_old == ["VB@13.3#3.12/chaining"]
    assert raw.modifies_new == ["VB@13.4#3.12/chaining"]


def test_test_cases_for_rule(kb):
    public = [t.key for t in kb.get_test_cases("R41-2")]
    assert public == ["peter", "peter-gap-exact", "peter-gap-in", "peter-gap-out", "bp-13-3"]
    with_hidden = {t.key for t in kb.get_test_cases("R41-2", include_hidden=True)}
    assert with_hidden == set(public) | {"peter-hidden", "peter-gap-exact-hidden"}


def test_deviation_context_mm_ansprech(kb):
    ctx = kb.get_deviation_context("DSLW", "MM-ANSPRECH", "41", "13.4")
    assert [r.id for r in ctx.rules] == ["F41-3"]
    assert [(b.record, b.mandatory) for b in ctx.flagged_blocks] == [("DBAP", "unknown")]
    assert "BP@13.3#13.1" in [p.key for p in ctx.passages]
    assert not [p for p in ctx.passages if p.key.startswith("VB@13.3")]


def test_search_finds_chaining(kb):
    keys = [p.key for p in kb.search_passages("Vorerkrankung 6 Monate", k=3)]
    assert any(k.endswith("#3.12/chaining") for k in keys), keys


def test_simulated_version_falls_back_to_newest_vb(kb):
    assert kb.get_passage("VB@sim-13.5#3.12/chaining").key == "VB@13.4#3.12/chaining"
    assert kb.get_layout("DBVO", "sim-13.5").version == "13.4"


def test_subgraph_rule(kb):
    g = kb.subgraph("Rule", "R41-2", depth=1)
    keys = {(n.label, n.key) for n in g.nodes}
    assert ("Parameter", "gap_inclusive") in keys and ("Criterion", "0cefe80e-4fd9-41e1-be4f-3ae1ecbde646") in keys
    assert ("Passage", "VB@13.4#3.12/chaining") in keys


# ---------------------------------------------------------------- review fixes

def _free_signature(kb, signature):
    if kb.find_precedent(signature) is not None:
        pytest.skip(f"a real precedent {signature} exists, not overwriting it")


def test_precedent_with_repeating_field_suffix(kb):
    """BEGINN-AU-1 is stored as the Field DBVO.BEGINN-AU, and found under both spellings."""
    signature = "41|DBVO.BEGINN-AU|missing_group"
    _free_signature(kb, signature)
    try:
        kb.add_precedent(Precedent(abgabegrund="41", field="DBVO.BEGINN-AU-1", kind="missing_group",
                                   verdict="bug", justified_by=["R41-3"]))
        found = kb.find_precedent(signature)
        assert found is not None and found.field == "DBVO.BEGINN-AU" and found.key == signature
        assert kb.find_precedent("41|DBVO.BEGINN-AU-1|missing_group").key == signature
        ctx = kb.get_deviation_context("DBVO", "BEGINN-AU-1", "41", "13.4")
        assert [p.key for p in ctx.precedents] == [signature]
    finally:
        kb.remove_precedent(signature)


def test_precedent_resave_replaces_justifications(kb):
    signature = "41|DBVO.KZ-NACHWEIS|value_differs"
    _free_signature(kb, signature)
    p = Precedent(abgabegrund="41", field="DBVO.KZ-NACHWEIS", kind="value_differs", verdict="invalid",
                  justified_by=["F41-9", "VB@13.4#3.12.9"])
    try:
        kb.add_precedent(p)
        kb.add_precedent(p.model_copy(update={"justified_by": ["F41-9"]}))
        assert kb.find_precedent(signature).justified_by == ["F41-9"]
    finally:
        kb.remove_precedent(signature)


def test_precedent_unknown_justification_rejected(kb):
    signature = "41|DBVO.ANZAHL-AU|value_differs"
    _free_signature(kb, signature)
    with pytest.raises(KeyError):
        kb.add_precedent(Precedent(abgabegrund="41", field="DBVO.ANZAHL-AU", kind="value_differs",
                                   verdict="bug", justified_by=["VB@13.4#3.12.99"]))
    assert kb.find_precedent(signature) is None


@pytest.mark.parametrize("query", ["Vorerkrankung OR", "NOT", "AND Monate", "a && b || (c)", "  "])
def test_search_free_text_never_crashes(kb, query):
    assert isinstance(kb.search_passages(query, k=3), list)


def test_search_numbers_match_whole():
    from kg.yaml_backend import search_patterns

    six = search_patterns(["6"])[0]
    assert six.search("nicht mehr als 6 monate") and six.search("6. monat")
    assert not six.search("seite 60") and not six.search("vgl. 6.1.2") and not six.search("2026")
    assert search_patterns(["vorerkrankung"])[0].search("vorerkrankungen")


def test_generic_splitter_keeps_toc_like_lines():
    from kg.extract import generic
    from kg.extract.pdf_text import Line

    lines = [Line(0, 2, "1. Allgemeines"), Line(1, 2, "Text vor der Tabelle"),
             Line(2, 2, "        2     Fr      Mo      6"), Line(3, 2, "2. Weiteres")]
    out = {p["section"]: p for p in generic.split("PTA", "v", lines, 1, lambda m: None)}
    assert "2     Fr" not in out["1"]["text"] and "Fr Mo 6" in out["1"]["text"]
    assert set(out) == {"1", "2"}


def test_bvorerk_repeated_uuid_is_no_new_passage(tmp_path):
    import docx

    from kg.extract.docx import split_bvorerk

    d = docx.Document()
    for text in ["Szenario DBVO", "f41c7278-b5a5-4ec3-b321-39bca5c3aeeb Kriterium eins",
                 "0cefe80e-4fd9-41e1-be4f-3ae1ecbde646 Kriterium zwei",
                 "siehe auch f41c7278-b5a5-4ec3-b321-39bca5c3aeeb"]:
        d.add_paragraph(text)
    path = tmp_path / "b.docx"
    d.save(path)
    out = split_bvorerk("BVORERK", "1", path, lambda m: None)
    assert [p["section"] for p in out] == ["intro", "f41c7278", "0cefe80e"]
    assert "siehe auch" in out[2]["text"]


# ---------------------------------------------------------------- both backends give the same answers

def test_backends_agree(yaml_kb, graph_kb):
    calls = [
        lambda kb: kb.get_layout("DBVO", "13.4"),
        lambda kb: kb.get_layout("DSLW", "13.3"),
        lambda kb: kb.get_rules("41", "13.3"),
        lambda kb: kb.get_rules("61", "13.4"),
        lambda kb: kb.get_rules("88", "sim-13.5"),
        lambda kb: [kb.get_param(n, version=v) for n in ("gap_inclusive", "min_total_days", "efz_days")
                    for v in ("13.3", "13.4", "sim-13.5")],
        lambda kb: kb.get_passage("VB@13.4#3.12/chaining"),
        lambda kb: kb.get_versions("VB"),
        lambda kb: kb.get_changes("VB", "13.3", "13.4", in_scope_only=False),
        lambda kb: kb.get_affected_rules([CHAINING, "VB-13.3-13.4-DBSD-names"]),
        lambda kb: kb.get_test_cases(include_hidden=True),
        lambda kb: [kb.get_test_case(t.key) for t in kb.get_test_cases(include_hidden=True)],
        lambda kb: kb.get_deviation_context("DSLW", "MM-ANSPRECH", "41", "13.4"),
        lambda kb: kb.get_deviation_context("DBVO", "BEGINN-AU-1", "41", "13.3"),
    ]

    def dump(x):
        return [i.model_dump() if hasattr(i, "model_dump") else i for i in x] if isinstance(x, list) else (
            x.model_dump() if hasattr(x, "model_dump") else x)

    for call in calls:
        assert dump(call(yaml_kb)) == dump(call(graph_kb))
