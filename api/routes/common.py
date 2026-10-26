"""Shared helpers for the routes."""

from __future__ import annotations

from fastapi import HTTPException, Request

from engine.model import TestCase


def kb(request: Request):
    return request.app.state.kb


def repo(request: Request):
    return request.app.state.repo


def ai(request: Request):
    return request.app.state.ai


def test_case(request: Request, id_: str) -> TestCase:
    """Store first (builder drafts, approvals), then the knowledge base."""
    tc = repo(request).get_test_case(id_)
    if tc is not None:
        return tc
    try:
        return kb(request).get_test_case(id_)
    except KeyError:
        raise HTTPException(404, f"test case {id_} not found")


def real_versions(request: Request) -> list[str]:
    return [v.version for v in kb(request).get_versions("VB") if not v.simulated]
