"""Checks of the prior-illness family: format of the employer's 41 (F41), the insurer simulator's own 61 / 62
(K61, K62), and the rule re-check that names the rule behind a diff deviation (R41, E). Rules every family shares
are in engine/rules/common.py.

Each check returns `RuleResult`s; the checker turns failed ones into labels (by the rule card's kind).
"""

from __future__ import annotations

from datetime import date

from engine.families.base import CheckContext
from engine.families.vorerkrankung.rules import deciding_rule
from engine.model import Deviation, Record, RuleResult, base_field_name
from engine.rules.common import _r

INSURER_FIELDS = ("AU-AB-SV", "KZ-AK-AU", "12-MONATSFRIST-AB")
INSURER_GROUP_FIELDS = ("KZ-NACHWEIS", "TEIL-NACHWEIS-AU-BEGINN", "TEIL-NACHWEIS-AU-ENDE", "KZ-AU", "TEIL-ANR-AU-BEGINN",
                        "TEIL-ANR-AU-ENDE")


def check_41_format(rec: Record, current_start: date | None = None) -> list[RuleResult]:
    """F41-4..7 on a 41 (failed and passed). The period order (F41-8) is the diff's `order_differs`."""
    if "DBVO" not in rec.blocks:
        return []  # A3-1
    out = [_r("F41-4", rec.get("DBVO.GRUNDAV") == 1, "GRUNDAV = 1 (Arbeitsunfähigkeit wegen Krankheit)", 1,
              rec.get("DBVO.GRUNDAV"), "DBVO.GRUNDAV")]
    if current_start is not None:
        out.append(_r("F41-5", rec.get("DBVO.AU-AB-AG") == current_start, "AU-AB-AG = Beginn der aktuellen AU",
                      current_start, rec.get("DBVO.AU-AB-AG"), "DBVO.AU-AB-AG"))
    groups = rec.blocks["DBVO"].groups
    filled = [(f, rec.get(f"DBVO.{f}")) for f in INSURER_FIELDS]
    filled += [(f, g[f].value) for g in groups for f in INSURER_GROUP_FIELDS]
    for f, v in filled:
        if v not in (None, 0):
            out.append(_r("F41-6", False, f"DBVO.{f} füllt nur die Krankenkasse: muss leer bzw. 0 sein", None, v,
                          f"DBVO.{f}"))
    n = rec.get("DBVO.ANZAHL-AU")
    out.append(_r("F41-7", n == len(groups) and n >= 1, "ANZAHL-AU = Anzahl der AU-Zeiten, mindestens 1", len(groups),
                  n, "DBVO.ANZAHL-AU"))
    return out


def check_61(rec: Record, msg_41: Record) -> list[RuleResult]:
    out = [
        _r("K61-1", rec.get("DBID.REFERENZ-ID") == msg_41.dsid, "REFERENZ-ID = DATENSATZ-ID der 41", msg_41.dsid,
           rec.get("DBID.REFERENZ-ID")),
        _r("K61-2", rec.get("DSLW.BBNR-VU") == msg_41.get("DSLW.BBNR-VU"), "BBNR-VU = BBNR-VU des Arbeitgebers",
           msg_41.get("DSLW.BBNR-VU"), rec.get("DSLW.BBNR-VU")),
        _r("K61-9", rec.get("DBID.AKTENZEICHEN-VERURSACHER") == (msg_41.get("DBID.AKTENZEICHEN-VERURSACHER") or ""),
           "die 61 wiederholt das AKTENZEICHEN-VERURSACHER", msg_41.get("DBID.AKTENZEICHEN-VERURSACHER"),
           rec.get("DBID.AKTENZEICHEN-VERURSACHER")),
    ]
    p41, p61 = msg_41.periods, rec.periods
    out.append(_r("K61-3", p61[: len(p41)] == p41, "dieselben AU-Zeiten in derselben Reihenfolge wie in der 41, weitere angehängt", p41, p61))
    return out

def check_62(rec: Record, latest_01: Record, employment_end: date | None) -> list[RuleResult]:
    out = [_r("K62-1", rec.get("DBID.REFERENZ-ID") == latest_01.dsid, "REFERENZ-ID = DATENSATZ-ID der letzten 01",
              latest_01.dsid, rec.get("DBID.REFERENZ-ID"))]
    end = rec.get("DBEE.EEL-ENDE")
    if employment_end is not None:
        out.append(_r("K62-2", end is not None and end <= employment_end, "Ende in der 62 nicht nach dem Ende der Beschäftigung",
                      employment_end, end))
    return out


# ---------------------------------------------------------------- self-check of the insurer simulator


def self_check(kb, scenario, replies: list[Record], employer: list[Record]) -> list[RuleResult]:
    """K61-1..3, K61-9 on every 61 against the employer's 41; K62-1, K62-2 on every 62 against the latest 01
    before it; A3-1 (VB Anlage 3 blocks) on every reply. Returns the failed results."""
    from engine import layouts
    from engine.rules import blocks

    flags = layouts.get(kb, "DSLW", None).flags
    m41 = next((r for r in employer if r.abgabegrund == "41"), None)
    out: list[RuleResult] = []
    for rec in replies:
        out += blocks.check_blocks(rec, flags)
        if rec.abgabegrund == "61" and m41 is not None:
            out += check_61(rec, m41)
        if rec.abgabegrund == "62":
            v01 = [r for r in employer if r.abgabegrund == "01"]
            if v01:
                out += check_62(rec, v01[-1], scenario.test_case.inputs.employment_end)
    return [r for r in out if not r.ok]


# ---------------------------------------------------------------- checks on the vendor's messages


def check_cancelled_01(ctx: CheckContext) -> list[tuple[Record, RuleResult]]:
    """E-2: the vendor's 88 cancels the vendor's 01 that the expected 88 cancels (that C-3 finds some message of the
    case is not enough). Matched through the chain steps of the diff, so the order of files and lines does not
    matter. An 88 or 01 the diff could not pair is the diff's missing or extra message."""
    step_of_dsid = {m.head.get("DATENSATZ-ID"): m.step for m in ctx.chain.employer()}
    expected = {m.step: m for m in ctx.chain.employer()}
    sent = {s: r for r in ctx.actual if (s := ctx.step_of.get(id(r))) is not None}
    out = []
    for r in ctx.actual:
        exp88 = expected.get(ctx.step_of.get(id(r)))
        if r.abgabegrund != "88" or exp88 is None or exp88.abgabegrund != "88":
            continue
        cancelled = sent.get(step_of_dsid.get(exp88.blocks["DBSD"]["DATENSATZ-ID-URSPRUNGSMELDUNG"]))
        if cancelled is None:
            continue
        target = r.get("DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG")
        out.append((r, _r("E-2", target == cancelled.dsid, "die 88 storniert die erste 01 (deren DATENSATZ-ID)",
                          cancelled.dsid, target, "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG")))
    return out


def check_records(ctx: CheckContext) -> list[tuple[Record | None, RuleResult]]:
    cur = ctx.scenario.test_case.inputs.current
    start = cur.start if cur else None
    out = [(r, x) for r in ctx.actual if r.abgabegrund == "41" for x in check_41_format(r, start)]
    return out + check_cancelled_01(ctx)


# ---------------------------------------------------------------- rule re-check of diff deviations


def _why41(ctx: CheckContext) -> str:
    v = ctx.chain.decision.trace.values
    return f"{len(v.get('chain', []))} verkettete Vorerkrankungszeit(en), insgesamt {v.get('total')} Tage"


def _last_step(ctx: CheckContext, rule: str) -> str:
    steps = [s for s in ctx.chain.decision.trace.steps if s.startswith(rule)]
    return steps[-1] if steps else rule


def _recheck_groups(ctx: CheckContext, d: Deviation) -> bool:
    chain = ctx.chain.decision.chain
    gap = ctx.params.gap_months
    if d.kind == "order_differs":
        return ctx.label(d, None, "F41-8", "die AU-Zeiten sind absteigend anzugeben, jüngste zuerst (VB 3.12.7)")
    if d.kind == "missing_group":
        oldest = f"{chain[-1].start}..{chain[-1].end}" if chain else None
        if d.expected == oldest:
            return ctx.label(d, None, "R41-3", f"die Kette reicht bis zur ersten Erkrankung zurück: {oldest} ist "
                                                f"verkettet (Abstand höchstens {gap} Monate), fehlt aber")
        return ctx.label(d, "correct_variant", "R41-3", f"{d.expected} nicht angegeben: mindestens eine AU-Zeit ist "
                                                        f"erforderlich und die älteste verkettete ist vorhanden; "
                                                        f"Hinweis: ‚so viele wie möglich' (VB 3.12)")
    if d.kind == "extra_group":
        uncert = {f"{a.start}..{a.end}" for a in ctx.scenario.test_case.inputs.priors if not a.certified}
        if d.actual in uncert:
            return ctx.label(d, None, "R41-5", f"{d.actual} ist nicht attestiert (keine AU-Bescheinigung) und darf nicht angegeben werden")
        return ctx.label(d, None, "R41-3", f"{d.actual} gehört nicht zur Kette (Abstand über {gap} Monate)")
    return False


def _no_new_01(ctx: CheckContext, d: Deviation) -> bool:
    """An 88 or a further 01 the chain does not have: E-3 if the corrected 61 only set interim flags, else E-2."""
    if ctx.chain.values.get("corrected_61_replaces_first") is False:
        return ctx.label(d, None, "E-3", "die korrigierte 61 setzt nur vorläufige Kennzeichen (KZ-AU 3 / KZ-AK-AU 4): "
                                          "die frühere 61 gilt weiter, die 01 wird weder storniert noch neu gesendet")
    if "efz" in ctx.chain.values:
        return ctx.label(d, None, "E-2", "die korrigierte 61 ändert das Ende der EFZ nicht: keine 88 und keine neue 01")
    return False


def recheck(ctx: CheckContext, d: Deviation) -> bool:
    """Deviations no field check names: missing or extra messages and periods, the EFZ end, the recipient. A
    field a failed rule result names is labelled by the checker before this runs."""
    ag, f = d.abgabegrund, f"{d.record}.{base_field_name(d.field or '')}"
    i = ctx.scenario.test_case.inputs
    if ag == "41":
        if d.kind == "missing_message":
            rule = deciding_rule(i.current, i.priors, i.report_date, ctx.params, i.insurance, i.person_group)
            return ctx.label(d, None, rule, f"nach V{ctx.version} ist eine 41 erforderlich ({_why41(ctx)}), "
                                             f"es wurde aber keine gesendet")
        if d.kind == "extra_message":
            failed = ctx.chain.decision.trace.failed
            rule = failed[-1] if failed else "R41-1"
            return ctx.label(d, None, rule, f"nach V{ctx.version} darf keine 41 gesendet werden: {_last_step(ctx, rule)}")
        if d.kind in ("missing_group", "extra_group", "order_differs"):
            return _recheck_groups(ctx, d)
        if f in ("DSLW.EMPFAENGERNUMMER", "DSLW.BBNR-KK"):
            return ctx.label(d, None, "R41-7", "die 41 geht an die Krankenkasse der versicherten Person (deren Betriebsnummer)")
    if ag == "01":
        if f == "DBAL.DATUM-EGZBIS":
            return ctx.label(d, None, "E-1", f"DATUM-EGZBIS muss das aus der letzten 61 berechnete Ende der EFZ "
                                              f"{d.expected} sein, gesendet wurde {d.actual}")
        if d.kind == "missing_message":
            rule = "E-2" if (d.step or 0) > 3 else "E-1"
            return ctx.label(d, None, rule, "die Entgeltbescheinigung 01 fehlt")
        if d.kind == "extra_message":
            return _no_new_01(ctx, d)
    if ag == "88":
        if d.kind == "missing_message":
            return ctx.label(d, None, "E-2", "die korrigierte 61 ändert das Ende der EFZ: die erste 01 ist vor der "
                                              "neuen 01 mit einer 88 zu stornieren")
        if d.kind == "extra_message":
            return _no_new_01(ctx, d)
    return False
