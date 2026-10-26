import json
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
