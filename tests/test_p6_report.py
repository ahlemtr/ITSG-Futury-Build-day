import json
from copy import deepcopy
from datetime import date

from engine import report, signing
from engine.checker import check


def _signed(kb, sid, tmp_path, seeds):
    s = seeds[sid]
    res = check(kb, s.test_case_id, list(s.files.values()), date(2027, 1, 1))
    rep = report.build(res, sid, s.files, kb, vendor="Test GmbH")
    key = signing.load_key(tmp_path / "k.pem")
    return signing.sign(rep.model_dump(mode="json"), key)


def test_report_validates_and_signs(kb, tmp_path, seeds):
    signed = _signed(kb, "s-missing-july", tmp_path, seeds)
    report.Report.model_validate(signed["report"])
    assert signing.verify(signed)
    blob = json.dumps(signed).replace("R41-3", "R41-4", 1).encode()
    assert not signing.verify_bytes(blob)


def test_html_fail_row_shows_passage(kb, tmp_path, seeds):
    html = report.render_html(_signed(kb, "s-missing-july", tmp_path, seeds))
    assert "R41-3" in html and "nicht mehr als 6 Monate" in html
    ok = report.render_html(_signed(kb, "s-itsg-ref", tmp_path, seeds))
    assert "exact_match" in ok


def test_key_created_once(tmp_path):
    k1 = signing.load_key(tmp_path / "x.pem")
    k2 = signing.load_key(tmp_path / "x.pem")
    assert signing.sign({"a": 1}, k1)["signature"]["value"] == signing.sign({"a": 1}, k2)["signature"]["value"]


def test_branded_export_is_self_contained_and_does_not_mutate_signature(kb, tmp_path, seeds):
    signed = _signed(kb, "s-missing-july", tmp_path, seeds)
    original = deepcopy(signed)
    html = report.render_html(signed)
    assert signed == original and signing.verify(signed)
    assert 'alt="ITSG"' in html and 'src="data:image/png;base64,' in html
    assert html.count("data:font/woff;base64,") == 3
    assert "Fehler festgestellt" in html and "Feststellungen &amp; Begründungen" in html
    assert "@page" in html and "counter(pages)" in html
    assert signed["signature"]["json_sha256"] in html
    assert signed["signature"]["value"] in html
    assert signed["signature"]["public_key"] in html
    assert '<script' not in html and 'src="http' not in html and 'url("http' not in html


def test_report_escapes_content_and_preserves_zero(kb, tmp_path, seeds):
    signed = _signed(kb, "s-missing-july", tmp_path, seeds)
    signed["report"]["vendor"] = '<script>alert("vendor")</script>'
    signed["report"]["checks"][0]["expected"] = "0"
    signed["report"]["checks"][0]["actual"] = "<unsafe>"
    html = report.render_html(signed)
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert '<div class="value">0</div>' in html
    assert '&lt;unsafe&gt;' in html and '<unsafe>' not in html


def test_report_date_uses_utc():
    assert report._display_date("2026-10-27T12:34:00+02:00", True) == "27.10.2026 · 10:34 UTC"
    assert report._display_date("2027-01-01") == "01.01.2027"
