"""Engine view of a layout. The KG returns flat field lists (`Layout.fields`, repeating fields flagged);
the parser and the diff also need the repeating group, the DSLW block order and the MM flag of each
block. All three are derived from the layout data itself:

- repeating group: the fields with `repeating = true`; the count field is the numeric field ending right
  before the group (DBVO: ANZAHL-AU)
- block order and flags: the DSLW `MM-*` fields in layout order, their `values.J` names the block
  ("J: DBNA follows")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine.model import FieldDef, Layout
from kg.interface import KnowledgeBase

FOLLOWS = re.compile(r"\b(D[A-Z]{3})\b")


@dataclass(frozen=True)
class Group:
    count_field: str
    starts_at: int
    group_length: int
    fields: list[FieldDef]


@dataclass(frozen=True)
class LayoutView:
    record: str
    status: str
    fixed_length: int
    fields: list[FieldDef]  # fixed part, layout order
    repeating_group: Group | None = None
    block_order: list[str] = field(default_factory=list)  # DSLW only
    flags: dict[str, str] = field(default_factory=dict)  # DSLW only: block -> MM flag

    def field(self, name: str) -> FieldDef:
        for f in self.fields + (self.repeating_group.fields if self.repeating_group else []):
            if f.name == name:
                return f
        raise KeyError(f"{self.record}.{name}")


def view(layout: Layout) -> LayoutView:
    fixed = [f for f in layout.fields if not f.repeating]
    rep = sorted((f for f in layout.fields if f.repeating), key=lambda f: f.offset_in_group or 0)
    group = None
    if rep:
        starts_at = min(f.start for f in rep)
        length = max((f.offset_in_group or 1) + f.length - 1 for f in rep)
        count = next(f.name for f in fixed if f.end == starts_at - 1 and f.type == "n")
        group = Group(count_field=count, starts_at=starts_at, group_length=length, fields=rep)
    order, flags = [], {}
    for f in fixed:
        if f.name.startswith("MM-") and f.values and "J" in f.values:
            m = FOLLOWS.search(f.values["J"])
            if m:
                order.append(m.group(1))
                flags[m.group(1)] = f.name
    return LayoutView(record=layout.record, status=layout.status, fixed_length=layout.fixed_length, fields=fixed,
                      repeating_group=group, block_order=order, flags=flags)


_CACHE: dict[tuple[int, str, str], LayoutView] = {}


def get(kb: KnowledgeBase, record: str, version: str | None) -> LayoutView:
    """`version` None = the newest version the knowledge base knows."""
    if version is None:
        from engine.rules.params import latest

        version = latest(kb)
    key = (id(kb), record, version)
    if key not in _CACHE:
        _CACHE[key] = view(kb.get_layout(record, version))
    return _CACHE[key]


def flag_of(kb: KnowledgeBase, block: str, version: str) -> str | None:
    return get(kb, "DSLW", version).flags.get(block)
