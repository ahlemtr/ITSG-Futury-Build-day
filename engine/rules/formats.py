"""Checks every family shares: MM flags match the blocks (F41-3), S-1 code values of GG Anlage 2,
DATENSATZ-ID format (F41-10). Family rules live in engine/families/<id>/checks.py.

Each check returns `RuleResult`s; the checker turns failed ones into labels.
"""

from __future__ import annotations

import re
from functools import cache

from engine.model import Record, RuleResult, base_field_name

UUID_RE = re.compile(r"^[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}$", re.IGNORECASE)
BLOCK_FLAGS = {"DBNA": "MM-NAME", "DBAN": "MM-ANSCHRIFT", "DBAL": "MM-ALLGEMEIN", "DBAE": "MM-ENTGELT",
               "DBVO": "MM-VOER", "DBEE": "MM-EELENDE", "DBAP": "MM-ANSPRECH", "DBID": "MM-ID", "DBSD": "MM-SD"}


def _r(rule: str, ok: bool, msg: str, expected=None, actual=None, field: str | None = None) -> RuleResult:
    return RuleResult(rule=rule, ok=ok, message=msg, expected=expected, actual=actual, field=field)


def check_mm_flags(rec: Record) -> list[RuleResult]:
    """Every MM flag J has its block and every block its flag (F41-3 generalised to all messages)."""
    out = []
    for blk, flag in BLOCK_FLAGS.items():
        v = rec.get(f"DSLW.{flag}")
        if v == "J" and blk not in rec.blocks:
            out.append(_r("F41-3", False, f"{flag} = J, aber Datenbaustein {blk} fehlt", blk, None, f"DSLW.{flag}"))
        if blk in rec.blocks and v != "J":
            out.append(_r("F41-3", False, f"Datenbaustein {blk} vorhanden, aber {flag} = {v}", "J", v, f"DSLW.{flag}"))
    return out


@cache
def key_values() -> dict[str, dict]:
    """field name -> its table of GG Anlage 2 (kg/seed/key_values.yaml, read from the document by
    tools/extract_key_values)."""
    from kg.common import SEED_DIR, load_yaml

    path = SEED_DIR / "key_values.yaml"
    data = load_yaml(path) if path.exists() else {"tables": []}
    return {t["field"]: t for t in data["tables"]}


def _blank(raw: str) -> bool:
    return not raw.strip() or set(raw) <= {"0"}


def check_key_values(rec: Record) -> list[RuleResult]:
    """S-1: every filled code field carries a Schlüsselzahl of GG Anlage 2 (all message types)."""
    tables = key_values()
    out = []
    fields = [("DSLW", fv) for fv in rec.head.values()]
    for name, blk in rec.blocks.items():
        fields += [(name, fv) for fv in blk.fields.values()]
        fields += [(name, fv) for g in blk.groups for fv in g.values()]
    for record, fv in fields:
        t = tables.get(base_field_name(fv.name))
        if t is None or record not in t["records"] or _blank(fv.raw):
            continue
        code = fv.raw.strip()
        if code not in t["codes"]:
            out.append(_r("S-1", False, f"{fv.name} = {code} ist keine Schlüsselzahl nach GG Anlage 2 "
                                         f"({', '.join(t['codes'])})", sorted(t["codes"]), code,
                          f"{record}.{base_field_name(fv.name)}"))
    return out


def check_uuid(rec: Record) -> RuleResult:
    dsid = rec.dsid or ""
    return _r("F41-10", bool(UUID_RE.match(dsid)), "DATENSATZ-ID im Format 8-4-4-4-12 (hexadezimal)", "uuid", dsid, "DSLW.DATENSATZ-ID")
