"""VB Anlage 3 chapter 2: which data blocks each Abgabegrund must (J), may (m) or must not (N) carry.
Rule A3-1, the same for every family. The table is kg/seed/message_types.yaml `block_table`."""

from __future__ import annotations

from functools import cache

from engine.model import Deviation, Record, RuleResult

RULE = "A3-1"


@cache
def block_table() -> dict[str, dict[str, str]]:
    """Abgabegrund -> block -> J / m / N."""
    from kg.common import SEED_DIR, load_yaml

    table = load_yaml(SEED_DIR / "message_types.yaml").get("block_table") or {}
    return {str(code): dict(zip(table["columns"], row.split())) for code, row in (table.get("rows") or {}).items()}


def presence(abgabegrund: str | None, block: str) -> str | None:
    return block_table().get(abgabegrund or "", {}).get(block)


def check_block_presence(rec: Record, flags: dict[str, str]) -> list[RuleResult]:
    """Every J block present, no N block present. `flags`: block -> MM flag (from the DSLW layout)."""
    row = block_table().get(rec.abgabegrund or "")
    if row is None:
        return []
    out = []
    for block, p in row.items():
        flag = flags.get(block)
        field = f"DSLW.{flag}" if flag else f"{block}"
        if p == "J" and block not in rec.blocks:
            out.append(RuleResult(rule=RULE, ok=False, field=field, expected=block, actual=None,
                                  message=f"block {block} is mandatory on a {rec.abgabegrund} (VB Anlage 3) but missing"))
        if p == "N" and block in rec.blocks:
            out.append(RuleResult(rule=RULE, ok=False, field=field, expected=None, actual=block,
                                  message=f"block {block} must not be sent on a {rec.abgabegrund} (VB Anlage 3)"))
    return out


def recheck(d: Deviation, block_of_flag: dict[str, str]) -> tuple[str, str] | None:
    """A diff deviation for a missing or extra block: (label, explanation) if Anlage 3 decides it, else None
    (m blocks depend on the case: the family or an expert decides)."""
    if d.kind not in ("missing_block", "extra_block"):
        return None
    block = block_of_flag.get(d.field or "") or d.record
    p = presence(d.abgabegrund, block)
    if d.kind == "missing_block" and p == "J":
        return "invalid", f"block {block} is mandatory on a {d.abgabegrund} (VB Anlage 3) but missing"
    if d.kind == "extra_block" and p == "N":
        return "invalid", f"block {block} must not be sent on a {d.abgabegrund} (VB Anlage 3)"
    return None
