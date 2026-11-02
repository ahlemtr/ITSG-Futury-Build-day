"""Locked test cases: values typed in from their source document (ITSG Hinweise, Beispielpapier, TA solutions), each
compared field with its source. For every locked case and every rule set version it has values for, the engine's
chain must give exactly those values; a field listed under `xfail` must still differ (strict: when the engine
starts to agree, the entry has to go). A rule change is accepted only when this whole file passes."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from engine import builder
from engine.expected import build_chain, get_case, load_scenario

ROOT = Path(__file__).resolve().parents[1]
CASES = [c for c in yaml.safe_load((ROOT / "kg/seed/test_cases.yaml").read_text(encoding="utf-8"))["test_cases"]
         if c.get("locked")]
COMPARED = ("send_41", "periods", "chain", "efz_end", "egzbis", "frist_12m")
PARAMS = [(c["id"], v, f) for c in CASES for v, exp in (c.get("expected") or {}).items()
          for f in COMPARED if f in exp]


def _s(v):
    return None if v is None else str(v)


def actual_value(ch, field: str):
    if field == "send_41":
        return ch.decision.send
    if field == "periods":
        return [[str(a.start), str(a.end)] for a in ch.decision.chain] if ch.decision.send else []
    if field == "chain":
        return [m.abgabegrund for m in ch.messages]
    if field == "efz_end":
        return {k: str(v) for k, v in ch.efz.items()}
    if field == "egzbis":
        m01 = [m for m in ch.messages if m.abgabegrund == "01"]
        return _s(m01[-1].blocks["DBAL"]["DATUM-EGZBIS"]) if m01 else None
    if field == "frist_12m":
        m61 = next((m for m in ch.messages if m.abgabegrund == "61"), None)
        return _s(m61.blocks["DBVO"]["12-MONATSFRIST-AB"]) if m61 else None
    raise KeyError(field)


def norm(v):
    """YAML dates and lists of dates -> strings, so typed-in values compare with the engine's."""
    if isinstance(v, date):
        return str(v)
    if isinstance(v, list | tuple):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    return v


def test_locked_cases_exist():
    ids = {c["id"] for c in CASES}
    assert {"peter", "bp-13-1", "bp-13-5", "ta-167-r1", "ta-167-r2", "ta-167-r3"} <= ids


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_every_compared_value_has_a_source(case):
    fields = {f for exp in (case.get("expected") or {}).values() for f in exp if f in COMPARED}
    missing = fields - set(case.get("expected_sources") or {})
    assert not missing, f"{case['id']}: no source for {sorted(missing)}"


@pytest.mark.parametrize(("case_id", "version", "field"), PARAMS, ids=lambda x: str(x))
def test_locked_value(kb, case_id, version, field):
    case = next(c for c in CASES if c["id"] == case_id)
    exp = case["expected"][version]
    if field not in (case.get("expected_sources") or {}):
        pytest.skip("value without a source is not a locked value")
    ch = build_chain(load_scenario(kb, case_id), version, kb)
    actual, expected = actual_value(ch, field), norm(exp[field])
    reason = (exp.get("xfail") or {}).get(field)
    if reason:
        assert actual != expected, f"{case_id} {version} {field} now matches ITSG: remove the xfail entry ({reason})"
        pytest.xfail(reason)
    assert actual == expected


def test_locked_cases_are_never_recomputed(kb):
    tc = get_case(kb, "ta-167-r2")
    before = tc.model_dump(mode="json")["expected"]
    assert builder.with_expected(kb, tc).model_dump(mode="json")["expected"] == before
    assert builder.recompute(kb, ["peter", "ta-167-r2", "peter-gap-exact"], "13.3", "13.4")[0].id == "peter-gap-exact"
    clone = builder.clone(kb, "peter", None, {}, "peter-copy")
    assert not clone.locked and clone.allowed_variants == []
