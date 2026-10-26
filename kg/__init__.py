"""Knowledge graph package. Only `get_kb()` and `interface.KnowledgeBase` are used by the backend."""

from __future__ import annotations

import os
from functools import lru_cache

from kg.interface import KnowledgeBase


@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    """Return the backend selected by KG_BACKEND (`yaml` default, `graph`)."""
    backend = os.environ.get("KG_BACKEND", "yaml")
    if backend == "yaml":
        from kg.yaml_backend import YamlBackend  # built by the KG teammate (plan/08)

        return YamlBackend()
    if backend == "graph":
        from kg.graph_backend import GraphBackend

        return GraphBackend()
    raise ValueError(f"unknown KG_BACKEND: {backend}")
