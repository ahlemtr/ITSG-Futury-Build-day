"""Prüfrechner: the Krankengeld calculation of RS-ANL3 step by step (engine/calc/krankengeld.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.calc import krankengeld

router = APIRouter()


@router.post("/calc/krankengeld")
def krankengeld_calc(body: krankengeld.Input):
    try:
        return krankengeld.calculate(body).model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(422, str(e))
