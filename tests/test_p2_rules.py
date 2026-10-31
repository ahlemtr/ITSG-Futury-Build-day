from datetime import date
from pathlib import Path

import pytest
import yaml

from engine.expected import get_case
from engine.records import parse_file
from engine.rules import formats, params
from engine.rules.vorerkrankung import add_months, deciding_rule, efz_end, must_send_41

VERSIONS = ["13.3", "13.4", "sim-13.5"]
ROOT = Path(__file__).resolve().parents[1]
CASES = [t["id"] for t in yaml.safe_load((ROOT / "kg/seed/test_cases.yaml").read_text(encoding="utf-8"))["test_cases"]
         if t["origin"] != "pta"]
D = date.fromisoformat


def test_params_by_date_and_version(kb):
    assert params.load(kb, on_date=D("2026-11-01")).gap_inclusive is False
    assert params.load(kb, on_date=D("2027-01-01")).gap_inclusive is True
    assert params.load(kb, version="sim-13.5").min_total_days == 28
    assert params.load(kb, on_date=D("2028-06-01")).min_total_days == 30
    assert params.version_on(kb, D("2026-11-01")) == "13.3"


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("case", CASES)
def test_rules_table(kb, case, version):
    """Every Beispielpapier and Peter row under 13.3, 13.4 and sim-13.5."""
    tc = get_case(kb, case)
    exp = tc.expected[version]
    d = must_send_41(tc.inputs.current, tc.inputs.priors, tc.inputs.report_date, params.load(kb, version=version))
    assert d.send == exp.send_41
    if exp.send_41:
        assert [(a.start, a.end) for a in d.chain] == exp.periods
        assert d.total_days == exp.total_days


def test_bp_13_5_counts_until_0809(kb):
    tc = get_case(kb, "bp-13-5")
    d = must_send_41(tc.inputs.current, tc.inputs.priors, tc.inputs.report_date, params.load(kb, version="13.4"))
    assert d.total_days == 23 and "R41-6" in d.trace.rules


def test_peter_trace(kb):
    tc = get_case(kb, "peter")
    d = must_send_41(tc.inputs.current, tc.inputs.priors, tc.inputs.report_date, params.load(kb, version="13.4"))
    assert {"R41-1", "R41-2", "R41-3", "R41-4"} <= set(d.trace.rules)
    assert d.trace.values["total"] == 35


def test_month_end():
    assert add_months(D("2025-08-31"), 6) == D("2026-02-28")


def test_deciding_rule(kb):
    p = params.load(kb, version="13.4")
    for case, rule in [("peter-gap-exact", "R41-2"), ("peter-b30", "R41-4")]:
        tc = get_case(kb, case)
        assert deciding_rule(tc.inputs.current, tc.inputs.priors, tc.inputs.report_date, p) == rule


def _g(s, e, nw, au):
    return {"BEGINN-AU": D(s), "ENDE-AU": D(e), "KZ-NACHWEIS": nw, "KZ-AU": au}


def test_efz_end(kb):
    p = params.load(kb, version="13.4")
    first = [_g("2026-03-01", "2026-03-03", 4, 3), _g("2025-12-01", "2025-12-03", 1, 1),
             _g("2025-10-01", "2025-10-17", 1, 1), _g("2025-07-14", "2025-07-15", 1, 1)]
    assert efz_end(D("2026-03-11"), first, p)[0] == D("2026-03-30")
    corrected = [_g("2026-03-01", "2026-03-03", 1, 1)] + first[1:]
    assert efz_end(D("2026-03-11"), corrected, p)[0] == D("2026-03-27")


def test_format_checks(kb, itsg_bytes):
    m = parse_file(itsg_bytes, kb).messages[0]
    res = formats.check_41_format(m, D("2026-03-11"))
    assert all(r.ok for r in res), [r for r in res if not r.ok]
    assert formats.check_uuid(m).ok and formats.check_mm_flags(m) == []
    text = itsg_bytes.decode()
    i = text.index("DBVO1") + 13  # AU-AB-SV
    bad = parse_file(text[:i] + "20260311" + text[i + 8:], kb).messages[0]
    assert any(r.rule == "F41-6" and not r.ok for r in formats.check_41_format(bad))
    assert not formats.check_chain([m, m])[0].ok  # reused DSID -> C-1
