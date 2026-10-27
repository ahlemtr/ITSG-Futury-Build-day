"""The Krankengeld calculator against the worked examples of Rundschreiben Anlage 3 (RS-ANL3, 11.12.2024)."""

from datetime import date
from decimal import Decimal as D

from engine.calc.krankengeld import Input, bemessungszeitraum, calculate, zwoelf_monate


def test_beispiel_71_bemessungszeitraum():
    # AU 22.01., payroll on the 15th for the current month: January billed but not ended -> December
    inp = Input(au_start=date(2026, 1, 22), billing_day=15, billing_month="same", gross=D(1), net=D(1))
    assert bemessungszeitraum(inp) == (date(2025, 12, 1), date(2025, 12, 31))


def test_billing_on_au_start_day_does_not_count():
    # payroll for May on 03.06.; AU from 03.06. -> May not yet billed -> April (4.1.1.1.1)
    inp = Input(au_start=date(2026, 6, 3), billing_day=3, billing_month="next", gross=D(1), net=D(1))
    assert bemessungszeitraum(inp) == (date(2026, 4, 1), date(2026, 4, 30))


def test_beispiele_104_105_zwoelf_monate():
    assert zwoelf_monate(date(2026, 4, 30)) == (date(2025, 5, 1), date(2026, 4, 30))
    assert zwoelf_monate(date(2026, 3, 31)) == (date(2025, 4, 1), date(2026, 3, 31))


def test_beispiel_102_kumuliertes_regelentgelt():
    r = calculate(Input(au_start=date(2026, 5, 16), gross=D(2400), net=D(1800), one_off=D(4500)))
    steps = {s.key: s.value for s in r.steps}
    assert steps["regelentgelt_laufend"] == "80.00" and steps["hinzurechnung_brutto"] == "12.50"
    assert steps["regelentgelt_kumuliert"] == "92.50"


def test_beispiel_103_krankengeld_mit_einmalzahlung():
    r = calculate(Input(au_start=date(2026, 5, 16), gross=D(2250), net=D(1650), one_off=D(4500)))
    steps = {s.key: s.value for s in r.steps}
    assert steps["regelentgelt_laufend"] == "75.00" and steps["regelentgelt_kumuliert"] == "87.50"
    assert steps["netto_laufend"] == "55.00" and steps["hinzurechnung_netto"] == "9.17"
    assert steps["netto_kumuliert"] == "64.17"
    assert steps["kg_70_regelentgelt"] == "61.25" and steps["kg_90_netto"] == "57.75"
    assert r.krankengeld == D("55.00")  # capped by 100 % of the laufendes Nettoarbeitsentgelt


def test_hoechstregelentgelt_caps():
    r = calculate(Input(au_start=date(2026, 5, 16), gross=D(9000), net=D(5500)))
    assert r.regelentgelt == D("193.75")
    assert next(s for s in r.steps if s.key == "hoechstregelentgelt").confirmed is False  # not from our documents


def test_api(fresh_kb, tmp_path):
    from fastapi.testclient import TestClient

    from api.main import create_app
    from store.repo import MemoryRepo

    client = TestClient(create_app(kb=fresh_kb, repo=MemoryRepo(), ai=False, data_root=tmp_path))
    r = client.post("/calc/krankengeld", json={"au_start": "2026-05-16", "gross": "2250", "net": "1650", "one_off": "4500"})
    assert r.status_code == 200 and r.json()["krankengeld"] == "55.00"
    assert client.post("/calc/krankengeld", json={"au_start": "2026-05-16", "pay": "hourly", "gross": "1",
                                                   "net": "1"}).status_code == 422
