"""Field and chain checks on parsed records: F41-1..10, K61, K62, C-1..8.

Each check returns `RuleResult`s; the checker turns failed ones into labels (F41 -> invalid,
R41 / E / C -> bug).
"""

from __future__ import annotations

import itertools
import re
from datetime import date
from functools import cache

from engine.model import Record, RuleResult, base_field_name

UUID_RE = re.compile(r"^[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}$", re.IGNORECASE)
BLOCK_FLAGS = {"DBNA": "MM-NAME", "DBAN": "MM-ANSCHRIFT", "DBAL": "MM-ALLGEMEIN", "DBAE": "MM-ENTGELT",
               "DBVO": "MM-VOER", "DBEE": "MM-EELENDE", "DBAP": "MM-ANSPRECH", "DBID": "MM-ID", "DBSD": "MM-SD"}


def _r(rule: str, ok: bool, msg: str, expected=None, actual=None, field: str | None = None) -> RuleResult:
    return RuleResult(rule=rule, ok=ok, message=msg, expected=expected, actual=actual, field=field)


def check_41_format(rec: Record, current_start: date | None = None) -> list[RuleResult]:
    out = [
        _r("F41-1", rec.abgabegrund == "41", "ABGABEGRUND = 41", "41", rec.abgabegrund, "DSLW.ABGABEGRUND"),
        _r("F41-2", rec.get("DSLW.KORR-ABGABEGRUND") in (0, None), "KORR-ABGABEGRUND = 00", 0,
           rec.get("DSLW.KORR-ABGABEGRUND"), "DSLW.KORR-ABGABEGRUND"),
        _r("F41-3", rec.get("DSLW.MM-VOER") == "J" and "DBVO" in rec.blocks, "MM-VOER = J with DBVO", "J",
           rec.get("DSLW.MM-VOER"), "DSLW.MM-VOER"),
    ]
    if "DBVO" not in rec.blocks:
        return out
    out.append(_r("F41-4", rec.get("DBVO.GRUNDAV") == 1, "GRUNDAV = 1", 1, rec.get("DBVO.GRUNDAV"), "DBVO.GRUNDAV"))
    if current_start is not None:
        out.append(_r("F41-5", rec.get("DBVO.AU-AB-AG") == current_start, "AU-AB-AG = current AU start",
                      current_start, rec.get("DBVO.AU-AB-AG"), "DBVO.AU-AB-AG"))
    for f in ("AU-AB-SV", "KZ-AK-AU", "12-MONATSFRIST-AB"):
        v = rec.get(f"DBVO.{f}")
        out.append(_r("F41-6", v in (None, 0), f"insurer-only field DBVO.{f} must be zero", None, v, f"DBVO.{f}"))
    groups = rec.blocks["DBVO"].groups
    n = rec.get("DBVO.ANZAHL-AU")
    out.append(_r("F41-7", n == len(groups) and n >= 1, "ANZAHL-AU = number of groups, at least 1", len(groups), n, "DBVO.ANZAHL-AU"))
    starts = [g["BEGINN-AU"].value for g in groups]
    newest_first = all(a is not None and b is not None and a > b for a, b in itertools.pairwise(starts))
    out.append(_r("F41-8", newest_first, "periods newest first", sorted(starts, reverse=True) if None not in starts
                  else None, starts, "DBVO.BEGINN-AU"))
    for i, g in enumerate(groups, 1):
        for f in ("KZ-NACHWEIS", "TEIL-NACHWEIS-AU-BEGINN", "TEIL-NACHWEIS-AU-ENDE", "KZ-AU", "TEIL-ANR-AU-BEGINN",
                  "TEIL-ANR-AU-ENDE"):
            v = g[f].value
            if v not in (None, 0):
                out.append(_r("F41-9", False, f"insurer-only field DBVO.{f}-{i} must be zero", None, v,
                                  f"DBVO.{f}"))
    return out


def check_mm_flags(rec: Record) -> list[RuleResult]:
    """Every MM flag J has its block and every block its flag (F41-3 generalised to all messages)."""
    out = []
    for blk, flag in BLOCK_FLAGS.items():
        v = rec.get(f"DSLW.{flag}")
        if v == "J" and blk not in rec.blocks:
            out.append(_r("F41-3", False, f"{flag} = J but block {blk} missing", blk, None, f"DSLW.{flag}"))
        if blk in rec.blocks and v != "J":
            out.append(_r("F41-3", False, f"block {blk} present but {flag} = {v}", "J", v, f"DSLW.{flag}"))
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
            out.append(_r("S-1", False, f"{fv.name} = {code} is not a Schlüsselzahl of GG Anlage 2 "
                                         f"({', '.join(t['codes'])})", sorted(t["codes"]), code,
                          f"{record}.{base_field_name(fv.name)}"))
    return out


def check_uuid(rec: Record) -> RuleResult:
    dsid = rec.dsid or ""
    return _r("F41-10", bool(UUID_RE.match(dsid)), "DATENSATZ-ID 8-4-4-4-12 hex", "uuid", dsid, "DSLW.DATENSATZ-ID")


def check_chain(msgs: list[Record], names: tuple[str, str] | None = None) -> list[RuleResult]:
    """Chain rules over the employer messages of one case, in chain order."""
    out: list[RuleResult] = []
    seen: dict[str, int] = {}
    for m in msgs:
        dsid = m.dsid or ""
        if dsid in seen:
            out.append(_r("C-1", False, f"DATENSATZ-ID {dsid} reused (first used by message {seen[dsid]})", "unique",
                          dsid, "DSLW.DATENSATZ-ID"))
        seen.setdefault(dsid, m.line_no)
    azvus = []
    for m in msgs:
        az = m.get("DBSD.AKTENZEICHEN-VERURSACHER") if m.abgabegrund == "88" else m.get("DBID.AKTENZEICHEN-VERURSACHER")
        if az is not None:
            azvus.append((m.abgabegrund, az))
    if azvus:
        first = azvus[0][1]
        for ag, az in azvus[1:]:
            if az != first:
                out.append(_r("C-2", False, f"AKTENZEICHEN-VERURSACHER of the {ag} differs", first, az,
                                  "DBSD.AKTENZEICHEN-VERURSACHER" if ag == "88" else "DBID.AKTENZEICHEN-VERURSACHER"))
    prev_01: Record | None = None
    for i, m in enumerate(msgs):
        if m.abgabegrund == "88":
            target = m.get("DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG")
            ok = prev_01 is not None and target == prev_01.dsid
            out.append(_r("C-3", ok, "88 points to the 01 being cancelled", prev_01.dsid if prev_01 else None, target,
                       "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG"))
            if prev_01 is not None:
                for f in ("VORNAME", "FAMILIENNAME"):
                    exp = prev_01.get(f"DBNA.{f}")
                    out.append(_r("C-4", m.get(f"DBSD.{f}") == exp, f"88 {f} = name in the cancelled record", exp,
                                  m.get(f"DBSD.{f}"), f"DBSD.{f}"))
            others = [b for b in m.blocks if b != "DBSD"]
            out.append(_r("C-8", m.get("DSLW.MM-SD") == "J" and not others, "88 carries only DBSD", ["DBSD"],
                          list(m.blocks), "DSLW.MM-SD"))
            nxt = msgs[i + 1] if i + 1 < len(msgs) else None
            out.append(_r("C-5", nxt is not None and nxt.abgabegrund == "01", "a new 01 follows the 88", "01",
                          nxt.abgabegrund if nxt else None, "DSLW.ABGABEGRUND"))
        if m.abgabegrund == "01":
            prev_01 = m
    return out


def check_61(rec: Record, msg_41: Record) -> list[RuleResult]:
    out = [
        _r("K61-1", rec.get("DBID.REFERENZ-ID") == msg_41.dsid, "REFERENZ-ID = DSID of the 41", msg_41.dsid,
           rec.get("DBID.REFERENZ-ID")),
        _r("K61-2", rec.get("DSLW.BBNR-VU") == msg_41.get("DSLW.BBNR-VU"), "BBNR-VU = employer's BBNR-VU",
           msg_41.get("DSLW.BBNR-VU"), rec.get("DSLW.BBNR-VU")),
        _r("C-7", rec.get("DBID.AKTENZEICHEN-VERURSACHER") == (msg_41.get("DBID.AKTENZEICHEN-VERURSACHER") or ""),
           "61 echoes AKTENZEICHEN-VERURSACHER", msg_41.get("DBID.AKTENZEICHEN-VERURSACHER"),
           rec.get("DBID.AKTENZEICHEN-VERURSACHER")),
    ]
    p41, p61 = msg_41.periods, rec.periods
    out.append(_r("K61-3", p61[: len(p41)] == p41, "same periods and order as the 41, extras appended", p41, p61))
    return out


def check_62(rec: Record, latest_01: Record, employment_end: date | None) -> list[RuleResult]:
    out = [_r("K62-1", rec.get("DBID.REFERENZ-ID") == latest_01.dsid, "REFERENZ-ID = DSID of the latest 01",
              latest_01.dsid, rec.get("DBID.REFERENZ-ID"))]
    end = rec.get("DBEE.EEL-ENDE")
    if employment_end is not None:
        out.append(_r("C-6", end is not None and end <= employment_end, "62 end not after end of employment",
                      employment_end, end))
    return out
