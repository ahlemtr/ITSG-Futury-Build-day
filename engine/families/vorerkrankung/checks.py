"""Format, chain and reply checks of the prior-illness family (F41, C-1..8, K61, K62) and the rule
re-check that names the rule behind a diff deviation.

Each check returns `RuleResult`s; the checker turns failed ones into labels (F41 -> invalid,
R41 / E / C -> bug).
"""

from __future__ import annotations

import itertools
from datetime import date

from engine.families.base import CheckContext
from engine.families.vorerkrankung.rules import deciding_rule
from engine.model import Deviation, Record, RuleResult, base_field_name
from engine.rules.formats import _r


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


# ---------------------------------------------------------------- checks on the vendor's messages

EMPLOYER_TYPES = {"01", "41", "88"}
F41_6 = {"DBVO.AU-AB-SV", "DBVO.KZ-AK-AU", "DBVO.12-MONATSFRIST-AB"}
F41_9 = {"DBVO.KZ-NACHWEIS", "DBVO.TEIL-NACHWEIS-AU-BEGINN", "DBVO.TEIL-NACHWEIS-AU-ENDE", "DBVO.KZ-AU",
         "DBVO.TEIL-ANR-AU-BEGINN", "DBVO.TEIL-ANR-AU-ENDE"}


def _chain_record(employer: list[Record], x: RuleResult) -> Record | None:
    if x.rule in ("C-3", "C-4", "C-5", "C-8") or (x.field or "").startswith("DBSD"):
        return next((r for r in employer if r.abgabegrund == "88"), None)
    return next((r for r in employer if r.dsid == x.actual), employer[0] if employer else None)


def check_records(ctx: CheckContext) -> list[tuple[Record | None, RuleResult]]:
    cur = ctx.scenario.test_case.inputs.current
    out: list[tuple[Record | None, RuleResult]] = []
    for r in ctx.actual:
        if r.abgabegrund == "41":
            out += [(r, x) for x in check_41_format(r, cur.start if cur else None) if x.rule != "F41-8"]
    employer = [r for r in ctx.actual if r.abgabegrund in EMPLOYER_TYPES]
    out += [(_chain_record(employer, x), x) for x in check_chain(employer)]
    return out


# ---------------------------------------------------------------- rule re-check of diff deviations


def _why41(ctx: CheckContext) -> str:
    v = ctx.chain.decision.trace.values
    return f"{len(v.get('chain', []))} chained prior period(s), total {v.get('total')} days"


def _last_step(ctx: CheckContext, rule: str) -> str:
    steps = [s for s in ctx.chain.decision.trace.steps if s.startswith(rule)]
    return steps[-1] if steps else rule


def _recheck_groups(ctx: CheckContext, d: Deviation) -> bool:
    chain = ctx.chain.decision.chain
    gap = ctx.params.gap_months
    if d.kind == "order_differs":
        return ctx.label(d, "bug", "F41-8", "periods must be listed newest first (VB 3.12.7)")
    if d.kind == "missing_group":
        oldest = f"{chain[-1].start}..{chain[-1].end}" if chain else None
        if d.expected == oldest:
            return ctx.label(d, "bug", "R41-3", f"the chain must go back to the first illness: {oldest} is "
                                                f"chained (gap at most {gap} months) but missing")
        return ctx.label(d, "correct_variant", "R41-3", f"{d.expected} not listed: at least one period is "
                                                        f"required and the oldest chained period is present; "
                                                        f"note: 'as many as possible' (VB 3.12)")
    if d.kind == "extra_group":
        uncert = {f"{a.start}..{a.end}" for a in ctx.scenario.test_case.inputs.priors if not a.certified}
        if d.actual in uncert:
            return ctx.label(d, "bug", "R41-5", f"{d.actual} has no sick note and must not be listed")
        return ctx.label(d, "bug", "R41-3", f"{d.actual} is not part of the chain (gap over {gap} months)")
    return False


def recheck(ctx: CheckContext, d: Deviation) -> bool:
    ag, f = d.abgabegrund, f"{d.record}.{base_field_name(d.field or '')}"
    i = ctx.scenario.test_case.inputs
    if ag == "41":
        if d.kind == "missing_message":
            rule = deciding_rule(i.current, i.priors, i.report_date, ctx.params)
            return ctx.label(d, "bug", rule, f"a 41 is required under {ctx.version} ({_why41(ctx)}) "
                                             f"but none was sent")
        if d.kind == "extra_message":
            failed = ctx.chain.decision.trace.failed
            rule = failed[-1] if failed else "R41-1"
            return ctx.label(d, "bug", rule, f"no 41 may be sent under {ctx.version}: {_last_step(ctx, rule)}")
        if d.kind in ("missing_group", "extra_group", "order_differs"):
            return _recheck_groups(ctx, d)
        if f in F41_6:
            return ctx.label(d, "invalid", "F41-6", f"{f} is an insurer-only field and must be zero")
        if f in F41_9:
            return ctx.label(d, "invalid", "F41-9", f"{f} is an insurer-only field and must be zero")
        if f == "DBVO.AU-AB-AG":
            return ctx.label(d, "invalid", "F41-5", "AU-AB-AG must be the start of the current AU")
        if f == "DBVO.GRUNDAV":
            return ctx.label(d, "invalid", "F41-4", "GRUNDAV must be 1 (sickness)")
    if ag == "01":
        if f == "DBAL.DATUM-EGZBIS":
            return ctx.label(d, "bug", "E-1", f"pay end must be the EFZ end {d.expected} computed from the "
                                              f"latest 61, vendor sent {d.actual}")
        if d.kind == "missing_message":
            rule = "E-2" if (d.step or 0) > 3 else "E-1"
            return ctx.label(d, "bug", rule, "the 01 certificate is missing")
    if ag == "88":
        if d.kind == "missing_message":
            return ctx.label(d, "bug", "E-2", "the corrected 61 changed the EFZ end: the first 01 must be "
                                              "cancelled with an 88 before the new 01")
        if f == "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG":
            return ctx.label(d, "bug", "C-3", "the 88 must point to the 01 being cancelled")
        if f in ("DBSD.VORNAME", "DBSD.FAMILIENNAME"):
            return ctx.label(d, "bug", "C-4", "the 88 names must be the names in the cancelled record")
    return False
