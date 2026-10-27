"""Krankengeld from Arbeitsentgelt, step by step (Gemeinsames Rundschreiben Krankengeld, Anlage 3 = RS-ANL3,
Fassung 11.12.2024, sections 4 and 5). The calculator ITSG advisors use by hand, as code: every step returns its
value, the formula in words and the section it comes from.

Steps:
1. Bemessungszeitraum: the last Entgeltabrechnungszeitraum that ended and was billed before the AU began
   (4.1.2.1.1; payroll on the same day as the AU start does not count). Monthly pay only in this version.
2. Zwölf-Monats-Zeitraum for one-off payments: the 12 calendar months ending with that month (5.1.3.1).
3. Regelentgelt laufend: monthly gross / 30 (Formel 5, 4.1.2.1), or for hourly pay
   gross x weekly hours / (paid hours x 7) (Formel 2, 4.1.1.1).
4. Brutto-Hinzurechnungsbetrag: contributory one-off payments of the 12 months / 360 (5.1.3).
5. Regelentgelt kumuliert = laufend + Hinzurechnung (Formel 7), limited to the Höchstregelentgelt, the
   calendar-daily KV contribution ceiling of the year of the last day of the Bemessungszeitraum (4.3).
6. Nettoarbeitsentgelt laufend: monthly net / 30 (hourly: as step 3); Netto-Hinzurechnungsbetrag =
   Brutto-Hinzurechnung x net laufend / Regelentgelt laufend, with the uncapped Regelentgelt (Formel 8).
7. Krankengeld = the lowest of 70 % of the capped kumuliertes Regelentgelt (5.1.1), 90 % of the kumuliertes
   Nettoarbeitsentgelt (5.1.2) and 100 % of the laufendes Nettoarbeitsentgelt (§ 47 Abs. 1 Satz 4 SGB V).

Rounding (4.1.2.1): computed to 3 decimals, rounded commercially to 2.

Not covered yet: Entgeltumwandlung (Abzugsbetrag, Formel 6), flexible working time, Altersteilzeit,
pay by output over 3 periods, the special cases of 4.1.1.1.1.2 (start of employment, Elternzeit, ...).
"""

from __future__ import annotations

import calendar as cal
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel

RS = "RS-ANL3@2024-12-11"
# Where each section's text sits in the knowledge graph. The extraction merged 4.1.1 into 4.1.2 and 5.1 into 5.3
# (headings with wide spacing were not split); the section numbers below are the document's own.
PASSAGE = {"4.1.1.1": f"{RS}#4.1.2", "4.1.2.1": f"{RS}#4.1.2.1", "4.1.2.1.1": f"{RS}#4.1.2.1.1", "4.3": f"{RS}#4.3",
           "5.1.1": f"{RS}#5.3", "5.1.2": f"{RS}#5.3", "5.1.3": f"{RS}#5.3", "5.1.3.1": f"{RS}#5.3"}

# Annual KV contribution ceiling (§ 223 Abs. 3 SGB V) / 360. 2016, 2018 and 2019 are quoted in RS-ANL3; the others
# come from the Sozialversicherungs-Rechengrößen and are not in our documents: to be confirmed by ITSG.
HOECHSTREGELENTGELT: dict[int, tuple[Decimal, bool]] = {
    2016: (Decimal("141.25"), True), 2018: (Decimal("147.50"), True), 2019: (Decimal("151.25"), True),
    2024: (Decimal("172.50"), False), 2025: (Decimal("183.75"), False), 2026: (Decimal("193.75"), False),
}

CENT = Decimal("0.01")


def money(x: Decimal) -> Decimal:
    """3 decimals first, then commercially to 2 (4.1.2.1)."""
    return x.quantize(Decimal("0.001"), ROUND_HALF_UP).quantize(CENT, ROUND_HALF_UP)


class Input(BaseModel):
    au_start: date
    pay: Literal["monthly", "hourly"] = "monthly"
    billing_day: int = 31  # payroll run: day of the month (31 = last day)
    billing_month: Literal["same", "next"] = "same"  # payroll for month M runs in M or in M+1
    gross: Decimal  # SV-Bruttoarbeitsentgelt of the Bemessungszeitraum, without one-off payments
    net: Decimal  # Nettoarbeitsentgelt of the same period
    one_off: Decimal = Decimal(0)  # contributory one-off payments of the 12 months (EZKV)
    weekly_hours: Decimal | None = None  # hourly pay: regelmäßige wöchentliche Arbeitszeit
    paid_hours: Decimal | None = None  # hourly pay: tatsächliche Arbeitsstunden + bezahlte Fehlstunden


class Step(BaseModel):
    key: str
    value: str
    formula: str
    section: str
    passage: str | None = None
    confirmed: bool = True  # False: a value from outside our documents, to be confirmed


class Result(BaseModel):
    bemessungszeitraum: tuple[date, date]
    zwoelf_monate: tuple[date, date]
    regelentgelt: Decimal
    krankengeld: Decimal
    steps: list[Step]


def _month_end(d: date) -> date:
    return d.replace(day=cal.monthrange(d.year, d.month)[1])


def _billing_date(month_start: date, inp: Input) -> date:
    m = month_start if inp.billing_month == "same" else (month_start + timedelta(days=32)).replace(day=1)
    return m.replace(day=min(inp.billing_day, cal.monthrange(m.year, m.month)[1]))


def bemessungszeitraum(inp: Input) -> tuple[date, date]:
    """The last calendar month that ended and was billed before the AU began (4.1.2.1.1, Beispiel 71)."""
    m = (inp.au_start.replace(day=1) - timedelta(days=1)).replace(day=1)  # the month before: ended
    for _ in range(3):
        if _billing_date(m, inp) < inp.au_start:  # billing on the AU start day does not count
            return m, _month_end(m)
        m = (m - timedelta(days=1)).replace(day=1)
    raise ValueError("no billed month in the 3 months before the AU start")


def zwoelf_monate(bz_end: date) -> tuple[date, date]:
    """12 calendar months ending with the Bemessungszeitraum (5.1.3.1, Beispiel 104: April -> 01.05. Vorjahr - 30.04.)."""
    start = bz_end.replace(day=1)
    for _ in range(11):
        start = (start - timedelta(days=1)).replace(day=1)
    return start, bz_end


def calculate(inp: Input) -> Result:
    steps: list[Step] = []

    def step(key: str, value, formula: str, section: str, confirmed: bool = True):
        steps.append(Step(key=key, value=str(value), formula=formula, section=section, passage=PASSAGE.get(section),
                          confirmed=confirmed))

    bz = bemessungszeitraum(inp)
    step("bemessungszeitraum", f"{bz[0]:%d.%m.%Y} - {bz[1]:%d.%m.%Y}",
         "last calendar month ended and billed before the AU start", "4.1.2.1.1")
    zm = zwoelf_monate(bz[1])
    step("zwoelf_monate", f"{zm[0]:%d.%m.%Y} - {zm[1]:%d.%m.%Y}", "12 calendar months ending with the Bemessungszeitraum",
         "5.1.3.1")

    if inp.pay == "monthly":
        re_lfd = money(inp.gross / 30)
        step("regelentgelt_laufend", re_lfd, f"{inp.gross} / 30", "4.1.2.1")
        net_lfd = money(inp.net / 30)
        step("netto_laufend", net_lfd, f"{inp.net} / 30", "4.1.2.1")
    else:
        if not inp.weekly_hours or not inp.paid_hours:
            raise ValueError("hourly pay needs weekly_hours and paid_hours")
        re_lfd = money(inp.gross * inp.weekly_hours / (inp.paid_hours * 7))
        step("regelentgelt_laufend", re_lfd, f"{inp.gross} x {inp.weekly_hours} / ({inp.paid_hours} x 7)", "4.1.1.1")
        net_lfd = money(inp.net * inp.weekly_hours / (inp.paid_hours * 7))
        step("netto_laufend", net_lfd, f"{inp.net} x {inp.weekly_hours} / ({inp.paid_hours} x 7)", "4.1.1.1")

    hz = money(inp.one_off / 360)
    step("hinzurechnung_brutto", hz, f"{inp.one_off} / 360", "5.1.3")
    re_kum = re_lfd + hz
    step("regelentgelt_kumuliert", re_kum, f"{re_lfd} + {hz}", "5.1.3")

    year = bz[1].year
    if year not in HOECHSTREGELENTGELT:
        raise ValueError(f"Höchstregelentgelt {year} is not known")
    hoechst, confirmed = HOECHSTREGELENTGELT[year]
    step("hoechstregelentgelt", hoechst, f"KV contribution ceiling {year} / 360", "4.3", confirmed)
    re_capped = min(re_kum, hoechst)
    step("regelentgelt_massgeblich", re_capped, f"min({re_kum}, {hoechst})", "4.3")

    net_hz = money(hz * net_lfd / re_lfd) if re_lfd else Decimal(0)
    step("hinzurechnung_netto", net_hz, f"{hz} x {net_lfd} / {re_lfd}", "5.1.3")
    net_kum = net_lfd + net_hz
    step("netto_kumuliert", net_kum, f"{net_lfd} + {net_hz}", "5.1.3")

    k70 = money(re_capped * Decimal("0.7"))
    step("kg_70_regelentgelt", k70, f"70 % x {re_capped}", "5.1.1")
    k90 = money(net_kum * Decimal("0.9"))
    step("kg_90_netto", k90, f"90 % x {net_kum}", "5.1.2")
    step("kg_100_netto_laufend", net_lfd, "100 % of the laufendes Nettoarbeitsentgelt", "5.1.3")
    kg = min(k70, k90, net_lfd)
    step("krankengeld", kg, f"min({k70}, {k90}, {net_lfd})", "5.1.2")
    return Result(bemessungszeitraum=bz, zwoelf_monate=zm, regelentgelt=re_capped, krankengeld=kg, steps=steps)
