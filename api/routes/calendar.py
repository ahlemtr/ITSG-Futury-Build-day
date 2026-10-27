"""Deadlines per vendor company and the catalogue's history (engine/calendar.py)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from api.routes.common import kb, repo
from engine import calendar

router = APIRouter()


@router.get("/calendar")
def get_calendar(request: Request, company: str | None = None, today: date | None = None):
    """All companies for ITSG; `company` (id or name) for the vendor view."""
    return calendar.view(kb(request), repo(request), today or date.today(), company)
