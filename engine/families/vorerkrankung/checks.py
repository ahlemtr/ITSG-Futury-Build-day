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
        _r("F41-3", rec.get("DSLW.MM-VOER") == "J" and "DBVO" in rec.blocks, "MM-VOER = J mit Datenbaustein DBVO", "J",
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
        out.append(_r("F41-6", v in (None, 0), f"DBVO.{f} füllt nur die Krankenkasse: muss leer bzw. 0 sein", None, v, f"DBVO.{f}"))
    groups = rec.blocks["DBVO"].groups
    n = rec.get("DBVO.ANZAHL-AU")
    out.append(_r("F41-7", n == len(groups) and n >= 1, "ANZAHL-AU = Anzahl der AU-Zeiten, mindestens 1", len(groups), n, "DBVO.ANZAHL-AU"))
    starts = [g["BEGINN-AU"].value for g in groups]
    newest_first = all(a is not None and b is not None and a > b for a, b in itertools.pairwise(starts))
    out.append(_r("F41-8", newest_first, "AU-Zeiten absteigend (jüngste zuerst)", sorted(starts, reverse=True) if None not in starts
                  else None, starts, "DBVO.BEGINN-AU"))
    for i, g in enumerate(groups, 1):
        for f in ("KZ-NACHWEIS", "TEIL-NACHWEIS-AU-BEGINN", "TEIL-NACHWEIS-AU-ENDE", "KZ-AU", "TEIL-ANR-AU-BEGINN",
                  "TEIL-ANR-AU-ENDE"):
            v = g[f].value
            if v not in (None, 0):
                out.append(_r("F41-9", False, f"DBVO.{f}-{i} füllt nur die Krankenkasse: muss leer bzw. 0 sein", None, v,
                                  f"DBVO.{f}"))
    return out

def check_chain(msgs: list[Record], names: tuple[str, str] | None = None) -> list[RuleResult]:
    """Chain rules over the employer messages of one case, in chain order."""
    out: list[RuleResult] = []
    seen: dict[str, int] = {}
    for m in msgs:
        dsid = m.dsid or ""
        if dsid in seen:
            out.append(_r("C-1", False, f"DATENSATZ-ID {dsid} mehrfach verwendet (zuerst in Zeile {seen[dsid]})", "unique",
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
                out.append(_r("C-2", False, f"AKTENZEICHEN-VERURSACHER der Meldung {ag} weicht ab", first, az,
                                  "DBSD.AKTENZEICHEN-VERURSACHER" if ag == "88" else "DBID.AKTENZEICHEN-VERURSACHER"))
    prev_01: Record | None = None
    for i, m in enumerate(msgs):
        if m.abgabegrund == "88":
            target = m.get("DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG")
            ok = prev_01 is not None and target == prev_01.dsid
            out.append(_r("C-3", ok, "die 88 verweist auf die stornierte 01", prev_01.dsid if prev_01 else None, target,
                       "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG"))
            if prev_01 is not None:
                for f in ("VORNAME", "FAMILIENNAME"):
                    exp = prev_01.get(f"DBNA.{f}")
                    out.append(_r("C-4", m.get(f"DBSD.{f}") == exp, f"{f} der 88 = Name im stornierten Datensatz", exp,
                                  m.get(f"DBSD.{f}"), f"DBSD.{f}"))
            others = [b for b in m.blocks if b != "DBSD"]
            out.append(_r("C-8", m.get("DSLW.MM-SD") == "J" and not others, "die 88 enthält nur den Datenbaustein DBSD", ["DBSD"],
                          list(m.blocks), "DSLW.MM-SD"))
            nxt = msgs[i + 1] if i + 1 < len(msgs) else None
            out.append(_r("C-5", nxt is not None and nxt.abgabegrund == "01", "auf die 88 folgt eine neue 01", "01",
                          nxt.abgabegrund if nxt else None, "DSLW.ABGABEGRUND"))
        if m.abgabegrund == "01":
            prev_01 = m
    return out

def check_61(rec: Record, msg_41: Record) -> list[RuleResult]:
    out = [
        _r("K61-1", rec.get("DBID.REFERENZ-ID") == msg_41.dsid, "REFERENZ-ID = DATENSATZ-ID der 41", msg_41.dsid,
           rec.get("DBID.REFERENZ-ID")),
        _r("K61-2", rec.get("DSLW.BBNR-VU") == msg_41.get("DSLW.BBNR-VU"), "BBNR-VU = BBNR-VU des Arbeitgebers",
           msg_41.get("DSLW.BBNR-VU"), rec.get("DSLW.BBNR-VU")),
        _r("C-7", rec.get("DBID.AKTENZEICHEN-VERURSACHER") == (msg_41.get("DBID.AKTENZEICHEN-VERURSACHER") or ""),
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
        out.append(_r("C-6", end is not None and end <= employment_end, "Ende in der 62 nicht nach dem Ende der Beschäftigung",
                      employment_end, end))
    return out


# ---------------------------------------------------------------- self-check of the insurer simulator


def self_check(kb, scenario, replies: list[Record], employer: list[Record]) -> list[RuleResult]:
    """K61-1..3, C-7 on every 61 against the employer's 41; K62-1, C-6 on every 62 against the latest 01 before
    it; A3-1 (VB Anlage 3 blocks) on every reply. Returns the failed results."""
    from engine import layouts
    from engine.rules import blocks

    flags = layouts.get(kb, "DSLW", None).flags
    m41 = next((r for r in employer if r.abgabegrund == "41"), None)
    out: list[RuleResult] = []
    for rec in replies:
        out += blocks.check_block_presence(rec, flags)
        if rec.abgabegrund == "61" and m41 is not None:
            out += check_61(rec, m41)
        if rec.abgabegrund == "62":
            v01 = [r for r in employer if r.abgabegrund == "01"]
            if v01:
                out += check_62(rec, v01[-1], scenario.test_case.inputs.employment_end)
    return [r for r in out if not r.ok]


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
    return f"{len(v.get('chain', []))} verkettete Vorerkrankungszeit(en), insgesamt {v.get('total')} Tage"


def _last_step(ctx: CheckContext, rule: str) -> str:
    steps = [s for s in ctx.chain.decision.trace.steps if s.startswith(rule)]
    return steps[-1] if steps else rule


def _recheck_groups(ctx: CheckContext, d: Deviation) -> bool:
    chain = ctx.chain.decision.chain
    gap = ctx.params.gap_months
    if d.kind == "order_differs":
        return ctx.label(d, "bug", "F41-8", "die AU-Zeiten sind absteigend anzugeben, jüngste zuerst (VB 3.12.7)")
    if d.kind == "missing_group":
        oldest = f"{chain[-1].start}..{chain[-1].end}" if chain else None
        if d.expected == oldest:
            return ctx.label(d, "bug", "R41-3", f"die Kette reicht bis zur ersten Erkrankung zurück: {oldest} ist "
                                                f"verkettet (Abstand höchstens {gap} Monate), fehlt aber")
        return ctx.label(d, "correct_variant", "R41-3", f"{d.expected} nicht angegeben: mindestens eine AU-Zeit ist "
                                                        f"erforderlich und die älteste verkettete ist vorhanden; "
                                                        f"Hinweis: ‚so viele wie möglich' (VB 3.12)")
    if d.kind == "extra_group":
        uncert = {f"{a.start}..{a.end}" for a in ctx.scenario.test_case.inputs.priors if not a.certified}
        if d.actual in uncert:
            return ctx.label(d, "bug", "R41-5", f"{d.actual} ist nicht attestiert (keine AU-Bescheinigung) und darf nicht angegeben werden")
        return ctx.label(d, "bug", "R41-3", f"{d.actual} gehört nicht zur Kette (Abstand über {gap} Monate)")
    return False


def _no_new_01(ctx: CheckContext, d: Deviation) -> bool:
    """An 88 or a further 01 the chain does not have: E-3 if the corrected 61 only set interim flags, else E-2."""
    if ctx.chain.values.get("corrected_61_replaces_first") is False:
        return ctx.label(d, "bug", "E-3", "die korrigierte 61 setzt nur vorläufige Kennzeichen (KZ-AU 3 / KZ-AK-AU 4): "
                                          "die frühere 61 gilt weiter, die 01 wird weder storniert noch neu gesendet")
    if "efz" in ctx.chain.values:
        return ctx.label(d, "bug", "E-2", "die korrigierte 61 ändert das Ende der EFZ nicht: keine 88 und keine neue 01")
    return False


def recheck(ctx: CheckContext, d: Deviation) -> bool:
    ag, f = d.abgabegrund, f"{d.record}.{base_field_name(d.field or '')}"
    i = ctx.scenario.test_case.inputs
    if ag == "41":
        if d.kind == "missing_message":
            rule = deciding_rule(i.current, i.priors, i.report_date, ctx.params, i.insurance, i.person_group)
            return ctx.label(d, "bug", rule, f"nach V{ctx.version} ist eine 41 erforderlich ({_why41(ctx)}), "
                                             f"es wurde aber keine gesendet")
        if d.kind == "extra_message":
            failed = ctx.chain.decision.trace.failed
            rule = failed[-1] if failed else "R41-1"
            return ctx.label(d, "bug", rule, f"nach V{ctx.version} darf keine 41 gesendet werden: {_last_step(ctx, rule)}")
        if d.kind in ("missing_group", "extra_group", "order_differs"):
            return _recheck_groups(ctx, d)
        if f in F41_6:
            return ctx.label(d, "invalid", "F41-6", f"{f} füllt nur die Krankenkasse: muss leer bzw. 0 sein")
        if f in F41_9:
            return ctx.label(d, "invalid", "F41-9", f"{f} füllt nur die Krankenkasse: muss leer bzw. 0 sein")
        if f == "DBVO.AU-AB-AG":
            return ctx.label(d, "invalid", "F41-5", "AU-AB-AG muss der Beginn der aktuellen AU sein")
        if f == "DBVO.GRUNDAV":
            return ctx.label(d, "invalid", "F41-4", "GRUNDAV muss 1 sein (Arbeitsunfähigkeit wegen Krankheit)")
        if f in ("DSLW.EMPFAENGERNUMMER", "DSLW.BBNR-KK"):
            return ctx.label(d, "bug", "R41-7", "die 41 geht an die Krankenkasse der versicherten Person (deren Betriebsnummer)")
    if ag == "01":
        if f == "DBAL.DATUM-EGZBIS":
            return ctx.label(d, "bug", "E-1", f"DATUM-EGZBIS muss das aus der letzten 61 berechnete Ende der EFZ "
                                              f"{d.expected} sein, gesendet wurde {d.actual}")
        if d.kind == "missing_message":
            rule = "E-2" if (d.step or 0) > 3 else "E-1"
            return ctx.label(d, "bug", rule, "die Entgeltbescheinigung 01 fehlt")
        if d.kind == "extra_message":
            return _no_new_01(ctx, d)
    if ag == "88":
        if d.kind == "missing_message":
            return ctx.label(d, "bug", "E-2", "die korrigierte 61 ändert das Ende der EFZ: die erste 01 ist vor der "
                                              "neuen 01 mit einer 88 zu stornieren")
        if d.kind == "extra_message":
            return _no_new_01(ctx, d)
        if f == "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG":
            return ctx.label(d, "bug", "C-3", "die 88 muss auf die stornierte 01 verweisen")
        if f in ("DBSD.VORNAME", "DBSD.FAMILIENNAME"):
            return ctx.label(d, "bug", "C-4", "die Namen in der 88 müssen denen im stornierten Datensatz entsprechen")
    return False
