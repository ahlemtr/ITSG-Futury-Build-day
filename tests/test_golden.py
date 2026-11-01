"""The engine's output for the full seed must not change unless on purpose (see tests/golden_snapshot.py)."""

from __future__ import annotations

import json

import pytest

from tests.golden_snapshot import GOLDEN, chains, checks, peter_run


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _assert_same(actual, expected, path=""):
    """Compare piece by piece so a failure names the first place that changed."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        assert sorted(actual) == sorted(expected), f"{path}: keys differ"
        for k in expected:
            _assert_same(actual[k], expected[k], f"{path}/{k}")
    elif isinstance(expected, list) and isinstance(actual, list):
        assert len(actual) == len(expected), f"{path}: length {len(actual)} != {len(expected)}"
        for n, (a, e) in enumerate(zip(actual, expected)):
            _assert_same(a, e, f"{path}[{n}]")
    else:
        assert actual == expected, f"{path} changed"


def test_expected_chains_unchanged(kb, golden):
    _assert_same(json.loads(json.dumps(chains(kb))), golden["chains"], "chains")


def test_check_results_unchanged(kb, golden):
    _assert_same(json.loads(json.dumps(checks(kb))), golden["checks"], "checks")


def test_peter_run_unchanged(kb, golden):
    _assert_same(json.loads(json.dumps(peter_run(kb))), golden["peter_run"], "peter_run")
