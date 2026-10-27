"""Versioned rule parameters (P2.1). A thin wrapper over `kb.get_param`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kg.interface import KnowledgeBase

NAMES = ("min_total_days", "gap_months", "gap_inclusive", "sum_window_months", "open_end_days", "efz_days")


@dataclass(frozen=True)
class Params:
    min_total_days: int
    gap_months: int
    gap_inclusive: bool
    sum_window_months: int
    open_end_days: int
    efz_days: int
    version: str | None = None


def load(kb: KnowledgeBase, version: str | None = None, on_date: date | None = None) -> Params:
    """Values of one rule set: by version (incl. sim-13.5) or by validity date (real versions only)."""
    vals = {n: kb.get_param(n, version=version, on_date=on_date) for n in NAMES}
    return Params(**vals, version=version or version_on(kb, on_date))


def version_on(kb: KnowledgeBase, on_date: date | None, document: str = "VB") -> str | None:
    """The real version valid on a date. Never 'latest' (plan/06 section 3)."""
    if on_date is None:
        return None
    valid = [v for v in kb.get_versions(document) if not v.version.startswith("sim") and v.valid_from and v.valid_from <= on_date]
    if not valid:
        raise LookupError(f"no {document} version valid on {on_date}")
    return max(valid, key=lambda v: v.valid_from).version


SIMULATED = ("sim-13.5",)  # simulated rule sets for the builder (only by version, never by date)


def real_versions(kb: KnowledgeBase, document: str = "VB") -> list[str]:
    """The real versions the knowledge base knows, oldest first (13.3 at the starting point, 13.4 after its upload)."""
    vs = [v for v in kb.get_versions(document) if not v.version.startswith("sim") and v.valid_from]
    return [v.version for v in sorted(vs, key=lambda v: v.valid_from)]


def latest(kb: KnowledgeBase, document: str = "VB") -> str:
    return real_versions(kb, document)[-1]


def all_versions(kb: KnowledgeBase) -> list[str]:
    """Real versions plus the simulated ones: the versions a test case gets expected results for."""
    return real_versions(kb) + list(SIMULATED)
