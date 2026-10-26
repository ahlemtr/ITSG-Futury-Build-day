"""Knowledge graph: seed files, build scripts and the two backends behind kg.interface.KnowledgeBase."""

from __future__ import annotations


def get_kb(backend: str | None = None):
    """The backend selected by KG_BACKEND (`yaml` or `graph`), default yaml."""
    from kg.common import env

    backend = (backend or env("KG_BACKEND", "yaml")).lower()
    if backend == "graph":
        from kg.graph_backend import GraphBackend

        return GraphBackend()
    if backend == "yaml":
        from kg.yaml_backend import YamlBackend

        return YamlBackend()
    raise ValueError(f"unknown KG_BACKEND {backend!r}, expected 'yaml' or 'graph'")
