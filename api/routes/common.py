"""Shared helpers for the routes."""

from __future__ import annotations

from fastapi import HTTPException, Request

from engine.expected import get_case
from engine.model import Case


def kb(request: Request):
    return request.app.state.kb


def repo(request: Request):
    return request.app.state.repo


def ai(request: Request):
    return request.app.state.ai


def test_case(request: Request, id_: str) -> Case:
    """Store first (builder drafts, approvals), then the knowledge base."""
    tc = repo(request).get_test_case(id_)
    if tc is not None:
        return tc
    try:
        return get_case(kb(request), id_)
    except KeyError:
        raise HTTPException(404, f"test case {id_} not found")


def real_versions(request: Request) -> list[str]:
    return [v.version for v in kb(request).get_versions("VB") if not v.version.startswith("sim")]


def catalogue_on_rules(request: Request, rules: list[str]) -> list[Case]:
    """The catalogue's test cases (store first, KB otherwise) that target one of the rules."""
    wanted = set(rules)
    cases = repo(request).list_test_cases() or [get_case(kb(request), t.key) for t in
                                                kb(request).get_test_cases(include_hidden=True)]
    return [t for t in cases if wanted & set(t.targets)]
