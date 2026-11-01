"""Continuity of benefits (VB Anlage 3 chapter 3, § 69 SGB IX): when a second benefit follows a first one, does the
employer send a new certificate? Rules A3-2 (a gap of one day always needs one) and A3-3 (directly following
benefits, table in kg/seed/continuity.yaml). The same for every family."""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache
from typing import Literal

from pydantic import BaseModel

Verdict = Literal["none", "required", "same_child", "impossible"]


class ContinuityDecision(BaseModel):
    new_certificate: bool | None  # None = the combination cannot occur
    rule: str  # A3-2 or A3-3
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
        return ContinuityDecision(new_certificate=True, rule="A3-2", verdict="gap",
                                  reason=f"{gap} calendar day(s) between the two benefits: always a new certificate")
    if organ_donation:
        return ContinuityDecision(new_certificate=True, rule="A3-3", verdict="required",
                                  reason="Krankengeld nach § 44a SGB V has no data exchange: the following benefit "
                                         "needs its own certificate")
    v = verdict(first, following)
    if v == "same_child":
        if same_child is None:
            raise ValueError("whether it is the same child decides here: pass same_child")
        new: bool | None = not same_child
        why = "same child: one continuous case" if same_child else "another child: a new case"
    else:
        new = {"none": False, "required": True, "impossible": None}[v]
        why = {"none": "§ 69 SGB IX: the first certificate carries on",
               "required": "a new certificate with the code of the following benefit",
               "impossible": "this combination cannot occur"}[v]
    return ContinuityDecision(new_certificate=new, rule="A3-3", verdict=v,
                              reason=f"{benefit_of(first)} followed directly by {benefit_of(following)}: {why}")
