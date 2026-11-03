"""Rules every family shares (rule cards with `family: common`).

On each message: S-1 code values of GG Anlage 2, S-2 KORR-ABGABEGRUND, A3-1 data blocks (blocks.py), C-1 the
DATENSATZ-ID format. Across the employer's messages of one case: C-1 each DATENSATZ-ID once, C-2 the same
AKTENZEICHEN-VERURSACHER, C-3 an 88 names the message it cancels. Family rules live in
engine/families/<id>/checks.py.

Each check returns `RuleResult`s; the checker turns failed ones into labels.
"""

from __future__ import annotations

import re
from functools import cache

from engine.model import Record, RuleResult, base_field_name
from engine.rules import blocks

UUID_RE = re.compile(r"^[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}$", re.IGNORECASE)


def _r(rule: str, ok: bool, msg: str, expected=None, actual=None, field: str | None = None) -> RuleResult:
    return RuleResult(rule=rule, ok=ok, message=msg, expected=expected, actual=actual, field=field)


# ---------------------------------------------------------------- one message


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
    """S-1: every filled code field carries a Schlüsselzahl of GG Anlage 2."""
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


def check_korr(rec: Record) -> list[RuleResult]:
    """S-2: KORR-ABGABEGRUND only on a 66, 00 everywhere else (VB 3.1.19)."""
    v = rec.get("DSLW.KORR-ABGABEGRUND")
    if rec.abgabegrund == "66" or v in (0, None):
        return []
    return [_r("S-2", False, f"KORR-ABGABEGRUND = {v}: nur in der Rückmeldung 66 gefüllt, sonst 00", 0, v,
               "DSLW.KORR-ABGABEGRUND")]


def check_dsid_format(rec: Record) -> list[RuleResult]:
    """C-1, format part: 8-4-4-4-12 hexadecimal."""
    dsid = rec.dsid or ""
    if UUID_RE.match(dsid):
        return []
    return [_r("C-1", False, "DATENSATZ-ID im Format 8-4-4-4-12 (hexadezimal)", "8-4-4-4-12", dsid,
               "DSLW.DATENSATZ-ID")]


def check_message(rec: Record, flags: dict[str, str]) -> list[RuleResult]:
    """All common rules on one message (failed results only). `flags`: block -> MM flag (DSLW layout)."""
    return [*check_key_values(rec), *check_korr(rec), *blocks.check_blocks(rec, flags), *check_dsid_format(rec)]


# ---------------------------------------------------------------- the employer's messages of one case


def check_case(msgs: list[Record]) -> list[tuple[Record, RuleResult]]:
    """C-1 each DATENSATZ-ID once, C-2 one AKTENZEICHEN-VERURSACHER, C-3 an 88 names the earlier message it
    cancels (its DATENSATZ-ID and names). `msgs`: the employer's messages in file order. Failed results only."""
    out: list[tuple[Record, RuleResult]] = []
    earlier: dict[str, Record] = {}
    first_az = None
    for m in msgs:
        dsid = m.dsid or ""
        if dsid in earlier:
            out.append((m, _r("C-1", False, f"DATENSATZ-ID {dsid} mehrfach verwendet (zuerst in Zeile "
                                            f"{earlier[dsid].line_no})", "eindeutig", dsid, "DSLW.DATENSATZ-ID")))
        blk = "DBSD" if m.abgabegrund == "88" else "DBID"
        az = m.get(f"{blk}.AKTENZEICHEN-VERURSACHER")
        if az is not None:
            if first_az is None:
                first_az = az
            elif az != first_az:
                out.append((m, _r("C-2", False, f"AKTENZEICHEN-VERURSACHER der Meldung {m.abgabegrund} weicht ab",
                                  first_az, az, f"{blk}.AKTENZEICHEN-VERURSACHER")))
        if m.abgabegrund == "88":
            out += [(m, x) for x in _check_cancel(m, earlier)]
        earlier.setdefault(dsid, m)
    return out


def _check_cancel(m88: Record, earlier: dict[str, Record]) -> list[RuleResult]:
    target = m88.get("DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG")
    cancelled = earlier.get(target or "")
    if cancelled is None:
        return [_r("C-3", False, "die 88 verweist auf keine frühere Meldung des Falls", sorted(earlier), target,
                   "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG")]
    out = []
    for f in ("VORNAME", "FAMILIENNAME"):
        exp, act = cancelled.get(f"DBNA.{f}"), m88.get(f"DBSD.{f}")
        if act != exp:
            out.append(_r("C-3", False, f"{f} der 88 = Name in der stornierten Meldung", exp, act, f"DBSD.{f}"))
    return out
