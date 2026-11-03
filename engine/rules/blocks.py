"""Rule A3-1, the same for every family: which data blocks each Abgabegrund must (J), may (m) or must not (N)
carry (VB Anlage 3 chapter 2, table in kg/seed/message_types.yaml `block_table`), and each MM flag in the DSLW
is J exactly when its block is present (VB 3.1)."""

from __future__ import annotations

from functools import cache

from engine.model import Record, RuleResult

RULE = "A3-1"


@cache
def block_table() -> dict[str, dict[str, str]]:
    """Abgabegrund -> block -> J / m / N."""
    from kg.common import SEED_DIR, load_yaml

    table = load_yaml(SEED_DIR / "message_types.yaml").get("block_table") or {}
    return {str(code): dict(zip(table["columns"], row.split())) for code, row in (table.get("rows") or {}).items()}


def check_blocks(rec: Record, flags: dict[str, str]) -> list[RuleResult]:
    """At most one failed result per block. `flags`: block -> MM flag (from the DSLW layout)."""
    row = block_table().get(rec.abgabegrund or "", {})
    out = []
    for block in dict.fromkeys([*row, *flags]):
        flag, present, p = flags.get(block), block in rec.blocks, row.get(block)
        v = rec.get(f"DSLW.{flag}") if flag else None
        if p == "J" and not present:
            msg, exp, act = f"Datenbaustein {block} ist bei Abgabegrund {rec.abgabegrund} Pflicht (VB Anlage 3), fehlt aber", block, None
        elif p == "N" and present:
            msg, exp, act = f"Datenbaustein {block} darf bei Abgabegrund {rec.abgabegrund} nicht übermittelt werden (VB Anlage 3)", None, block
        elif flag and (v == "J") != present:
            msg = f"{flag} = {v}, aber Datenbaustein {block} {'vorhanden' if present else 'fehlt'}"
            exp, act = "J" if present else "N", v
        else:
            continue
        out.append(RuleResult(rule=RULE, ok=False, message=msg, expected=exp, actual=act,
                              field=f"DSLW.{flag}" if flag else block))
    return out
