"""Known-variant catalogue + precedent lookup (P4.4, decision D4)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from engine.model import Deviation
from kg.interface import KnowledgeBase

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "variants.yaml"


class Variant(BaseModel):
    signature: str
    verdict: str
    reason: str
    source: str | None = None
    active: bool = True


class Catalogue:
    def __init__(self, path: Path = DEFAULT_PATH, entries: list[Variant] | None = None):
        if entries is None:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            entries = [Variant(**v) for v in raw.get("variants", [])]
        self.entries = {v.signature: v for v in entries if v.active}

    def resolve(self, d: Deviation, kb: KnowledgeBase) -> bool:
        """Label the deviation from the catalogue or an approved precedent. Returns True if resolved."""
        v = self.entries.get(d.signature)
        if v:
            d.label, d.resolved_by = v.verdict, "catalogue"
            d.explanation = f"known variant: {v.reason}"
            d.sources = [v.source] if v.source else []
            return True
        p = kb.find_precedent(d.signature)
        if p:
            d.label, d.resolved_by, d.precedent_key = p.verdict, "catalogue", p.key
            d.explanation = f"precedent ({p.advisor or 'advisor'}, {p.decided}): {p.reason}"
            d.sources = [j for j in p.justified_by if "#" in j]
            return True
        return False
