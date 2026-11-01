"""Scenario families. Each sub-package of `engine/families/` with a `FAMILY` object is one family; it is
found at first use, so adding a family means adding a folder. `load_from` registers a family from
another folder (the test-only family under tests/ uses it)."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path

from engine.families.base import ChainResult, CheckContext, Family, Scenario

DEFAULT = "vorerkrankung"
_REGISTRY: dict[str, Family] = {}
_DISCOVERED = False

__all__ = [
    "DEFAULT",
    "ChainResult",
    "CheckContext",
    "Family",
    "Scenario",
    "all_families",
    "get",
    "load_from",
    "of_case",
    "register",
]


def register(family: Family) -> Family:
    if not isinstance(family, Family):
        raise TypeError(f"{family!r} is not a Family")
    _REGISTRY[family.id] = family
    return family


def _discover() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    for mod in pkgutil.iter_modules(__path__):
        if mod.ispkg:
            fam = getattr(importlib.import_module(f"{__name__}.{mod.name}"), "FAMILY", None)
            if fam is not None:
                register(fam)


def load_from(path: str | Path) -> Family:
    """Import the package at `path` (a folder with __init__.py defining FAMILY) and register its family."""
    path = Path(path).resolve()
    name = f"_eel_family_{path.name}"
    spec = importlib.util.spec_from_file_location(name, path / "__init__.py", submodule_search_locations=[str(path)])
    if spec is None or spec.loader is None:
        raise ImportError(f"no family package at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return register(module.FAMILY)


def get(family_id: str | None) -> Family:
    _discover()
    key = family_id or DEFAULT
    if key not in _REGISTRY:
        raise KeyError(f"unknown scenario family {key!r} (known: {', '.join(sorted(_REGISTRY))})")
    return _REGISTRY[key]


def all_families() -> list[Family]:
    _discover()
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def of_case(case) -> Family:
    """The family of a test case (`Case` or KG `TestCase`); cases without one are prior illness."""
    return get(getattr(case, "family", None))
