"""Continuity of benefits (VB Anlage 3 chapter 3, § 69 SGB IX): when a second benefit follows a first one, does the
employer send a new certificate? Rule A3-2: a gap of one day always needs one; directly following benefits
follow the table in kg/seed/continuity.yaml. The same for every family."""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache
from typing import Literal

from pydantic import BaseModel

Verdict = Literal["none", "required", "same_child", "impossible"]


class ContinuityDecision(BaseModel):
    new_certificate: bool | None  # None = the combination cannot occur
    verdict: Verdict | Literal["gap"]
    reason: str


@cache
def table() -> dict:
    from kg.common import SEED_DIR, load_yaml

    return load_yaml(SEED_DIR / "continuity.yaml")


def benefit_of(abgabegrund: str) -> str:
    for benefit, codes in table()["benefits"].items():
        if abgabegrund in codes:
            return benefit
    raise ValueError(f"Abgabegrund {abgabegrund} is not a certificate of a benefit (VB Anlage 3 chapter 3)")


def verdict(first: str, following: str) -> Verdict:
    t = table()
    return t["rows"][benefit_of(first)][t["columns"].index(benefit_of(following))]


def new_certificate(first: str, first_end: date, following: str, following_start: date,
                    same_child: bool | None = None, organ_donation: bool = False) -> ContinuityDecision:
    """`first` / `following`: the Abgabegrund of each certificate (01, 02, 03, 04, 11, 12, 21, 22, 23, 31).
    `organ_donation`: the first benefit is Krankengeld nach § 44a SGB V (no data exchange for it)."""
    gap = (following_start - first_end - timedelta(days=1)).days
    if gap < 0:
        raise ValueError("the following benefit starts before the first one ends")
    if gap >= 1:
        return ContinuityDecision(new_certificate=True, verdict="gap",
                                  reason=f"{gap} Kalendertag(e) zwischen den beiden Leistungen: immer eine neue Entgeltbescheinigung")
    if organ_donation:
        return ContinuityDecision(new_certificate=True, verdict="required",
                                  reason="für Krankengeld nach § 44a SGB V gibt es keinen Datenaustausch: die folgende "
                                         "Leistung braucht eine eigene Entgeltbescheinigung")
    v = verdict(first, following)
    if v == "same_child":
        if same_child is None:
            raise ValueError("whether it is the same child decides here: pass same_child")
        new: bool | None = not same_child
        why = "dasselbe Kind: ein durchgängiger Fall" if same_child else "ein anderes Kind: ein neuer Fall"
    else:
        new = {"none": False, "required": True, "impossible": None}[v]
        why = {"none": "§ 69 SGB IX: die erste Entgeltbescheinigung gilt weiter",
               "required": "eine neue Entgeltbescheinigung mit dem Abgabegrund der folgenden Leistung",
               "impossible": "diese Kombination kommt nicht vor (keine Fallgestaltung)"}[v]
    return ContinuityDecision(new_certificate=new, verdict=v,
                              reason=f"{benefit_of(first)}, direkt gefolgt von {benefit_of(following)}: {why}")
