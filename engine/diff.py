"""Three-level diff (P4.1, plan/05 section 3): messages, matching, fields.

Matching is by person (VSNR) + Abgabegrund + position in the chain (n-th message of that type),
never by line order. Fields are compared on their fixed-width form, using the compare mode of
each field from the layout: `compare` fields only; `rule` fields are checked by rules, `ignore`
fields never.
"""

from __future__ import annotations

import hashlib
import itertools
from typing import Any

from engine import layouts
from engine.layouts import LayoutView
from engine.model import Deviation, ExpectedMessage, Record
from engine.records import format_value
from kg.interface import KnowledgeBase


def _dev_id(d: Deviation, n: int) -> str:
    h = hashlib.sha1(f"{d.step}|{d.signature}|{d.expected}|{d.actual}|{n}".encode()).hexdigest()[:10]
    return f"dev-{h}"


def _show(v: Any) -> Any:
    return str(v) if v is not None and not isinstance(v, (str, int)) else v


class Differ:
    def __init__(self, kb: KnowledgeBase, version: str):
        self.kb = kb
        self.version = version
        self.dslw = layouts.get(kb, "DSLW", version)

    def _flag_of(self, blk: str) -> str | None:
        return self.dslw.flags.get(blk)

    def match(self, expected: list[ExpectedMessage], actual: list[Record]):
        """-> (pairs, missing expected, extra actual)."""
        def key(person: Any, ag: str) -> tuple:
            return (str(person or "").strip(), ag)

        buckets: dict[tuple, list[Record]] = {}
        for r in actual:
            buckets.setdefault(key(r.get("DSLW.VSNR"), r.abgabegrund or ""), []).append(r)
        exp_buckets: dict[tuple, list[ExpectedMessage]] = {}
        for m in expected:
            exp_buckets.setdefault(key(m.head.get("VSNR"), m.abgabegrund), []).append(m)
        pairs, missing = [], []
        used: set[int] = set()
        for k, exps in exp_buckets.items():
            cands = self._order(exps, buckets.get(k, []))
            for n, m in enumerate(exps):
                if n < len(cands):
                    pairs.append((m, cands[n]))
                    used.add(id(cands[n]))
                else:
                    missing.append(m)
        pairs.sort(key=lambda p: p[0].step)
        missing.sort(key=lambda m: m.step)
        extra = [r for r in actual if id(r) not in used]
        return pairs, missing, extra

    def _order(self, exps: list[ExpectedMessage], cands: list[Record]) -> list[Record]:
        """Chain position among messages of the same type: keep the vendor's order unless another
        assignment gives fewer deviations (lines may come in any order, plan/02 M4.1)."""
        if len(exps) < 2 or len(cands) < 2 or len(cands) > 5:
            return cands
        best, best_cost = cands, None
        for perm in itertools.permutations(cands):
            cost = sum(len(self.diff_pair(m, r)) for m, r in zip(exps, perm))
            if best_cost is None or cost < best_cost:
                best, best_cost = list(perm), cost
        return best

    def _cmp_fields(self, lay: LayoutView, exp: dict[str, Any], act: dict, base: dict, suffix: str = "",
                    group_fields: bool = False) -> list[Deviation]:
        out = []
        fields = lay.repeating_group.fields if group_fields else lay.fields
        for f in fields:
            if f.compare_mode != "compare" or f.name == "KENNUNG":
                continue
            if lay.repeating_group and f.name == lay.repeating_group.count_field:
                continue  # group count differences are reported as missing / extra groups
            fv = act.get(f.name)
            exp_s = format_value(f, exp.get(f.name, f.constant))
            act_s = fv.raw if fv is not None else None
            if exp_s != act_s:
                out.append(Deviation(**base, record=lay.record, field=f.name + suffix, kind="value_differs",
                                     expected=_show(exp.get(f.name)), actual=_show(fv.value if fv else None)))
        return out

    def _cmp_groups(self, lay: LayoutView, exp_groups: list[dict], act_groups: list[dict], base: dict) -> list[Deviation]:
        out: list[Deviation] = []

        def pk(g: dict) -> tuple:
            v = [g.get(n) for n in ("BEGINN-AU", "ENDE-AU")]
            return tuple(getattr(x, "value", x) for x in v)

        ek, ak = [pk(g) for g in exp_groups], [pk(g) for g in act_groups]
        for i, k in enumerate(ek):
            if k not in ak:
                out.append(Deviation(**base, record=lay.record, field="BEGINN-AU", kind="missing_group",
                                     expected=f"{k[0]}..{k[1]}", actual=None))
        for k in ak:
            if k not in ek:
                out.append(Deviation(**base, record=lay.record, field="BEGINN-AU", kind="extra_group", expected=None,
                                     actual=f"{_show(k[0])}..{_show(k[1])}"))
        common_e = [k for k in ek if k in ak]
        common_a = [k for k in ak if k in ek]
        if common_e != common_a:
            out.append(Deviation(**base, record=lay.record, field="BEGINN-AU", kind="order_differs",
                                 expected=[f"{a}..{b}" for a, b in common_e],
                                 actual=[f"{a}..{b}" for a, b in common_a]))
        for i, k in enumerate(ek):
            if k in ak:
                j = ak.index(k)
                out += self._cmp_fields(lay, exp_groups[i], act_groups[j], base, suffix=f"-{j + 1}", group_fields=True)
        return out

    def diff_pair(self, m: ExpectedMessage, r: Record) -> list[Deviation]:
        base = {"step": m.step, "abgabegrund": m.abgabegrund}
        out = []
        skip_flags = set()
        for blk in self.dslw.block_order:
            flag = self._flag_of(blk)
            if blk in m.blocks and blk not in r.blocks:
                out.append(Deviation(**base, record="DSLW", field=flag, kind="missing_block", expected="J",
                                     actual=r.get(f"DSLW.{flag}")))
                skip_flags.add(flag)
            elif blk not in m.blocks and blk in r.blocks:
                out.append(Deviation(**base, record="DSLW", field=flag, kind="extra_block", expected="N",
                                     actual=r.get(f"DSLW.{flag}")))
                skip_flags.add(flag)
        head = dict(m.head)
        for blk in self.dslw.block_order:
            flag = self._flag_of(blk)
            if flag:
                head[flag] = "J" if blk in m.blocks else "N"
        devs = self._cmp_fields(self.dslw, head, r.head, base)
        out += [d for d in devs if d.field not in skip_flags]
        for blk, exp in m.blocks.items():
            if blk not in r.blocks:
                continue
            lay = layouts.get(self.kb, blk, self.version)
            act = r.blocks[blk]
            out += self._cmp_fields(lay, exp, act.fields, base)
            if lay.repeating_group:
                out += self._cmp_groups(lay, exp.get("groups", []), act.groups, base)
        return out

    def diff(self, expected: list[ExpectedMessage], actual: list[Record]) -> tuple[list[Deviation], list]:
        pairs, missing, extra = self.match(expected, actual)
        out: list[Deviation] = []
        for m in missing:
            out.append(Deviation(step=m.step, abgabegrund=m.abgabegrund, record="DSLW", field="ABGABEGRUND",
                                 kind="missing_message", expected=m.abgabegrund, actual=None))
        for r in extra:
            out.append(Deviation(step=None, abgabegrund=r.abgabegrund, record="DSLW", field="ABGABEGRUND",
                                 kind="extra_message", expected=None, actual=r.abgabegrund))
        for m, r in pairs:
            out += self.diff_pair(m, r)
        for n, d in enumerate(out):
            d.id = _dev_id(d, n)
        return out, pairs


def diff(expected: list[ExpectedMessage], actual: list[Record], kb: KnowledgeBase, version: str) -> list[Deviation]:
    return Differ(kb, version).diff(expected, actual)[0]
