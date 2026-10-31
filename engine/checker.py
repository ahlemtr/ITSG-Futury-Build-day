"""Rule checker: exact match first, then each deviation gets one label.

Flow per submission: parse (issues -> invalid) -> expected chain under the rule set valid on
`valid_on` -> 3-level diff -> rule-field and format checks -> per deviation: a. catalogue and
precedents, b. rule re-check, c. left `unclear` with an empty AI slot (filled by llm/).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date

from engine.diff import Differ, _dev_id
from engine.expected import ChainResult, Scenario, build_chain, load_scenario
from engine.model import (
    LABEL_ORDER,
    Case,
    CheckResult,
    Deviation,
    ParseIssue,
    Record,
    Rule,
    RuleResult,
    base_field_name,
)
from engine.records import parse_file
from engine.rules import formats
from engine.rules import params as params_mod
from engine.rules.vorerkrankung import deciding_rule
from engine.variants import Catalogue
from kg.interface import KnowledgeBase

EMPLOYER_TYPES = {"01", "41", "88"}
F41_6 = {"DBVO.AU-AB-SV", "DBVO.KZ-AK-AU", "DBVO.12-MONATSFRIST-AB"}
F41_9 = {"DBVO.KZ-NACHWEIS", "DBVO.TEIL-NACHWEIS-AU-BEGINN", "DBVO.TEIL-NACHWEIS-AU-ENDE", "DBVO.KZ-AU",
         "DBVO.TEIL-ANR-AU-BEGINN", "DBVO.TEIL-ANR-AU-ENDE"}

Triage = Callable[[Deviation, str], None]  # fills d.ai_proposal for unclear deviations


def worst(labels: list[str]) -> str:
    for lab in LABEL_ORDER:
        if lab in labels:
            return lab
    return "exact_match"


class Checker:
    def __init__(self, kb: KnowledgeBase, catalogue: Catalogue | None = None):
        self.kb = kb
        self.catalogue = catalogue or Catalogue()

    # ------------------------------------------------------------ helpers
    def _rules(self, version: str) -> dict[str, Rule]:
        out: dict[str, Rule] = {}
        for ag in ("41", "61", "62", "01", "88"):
            for r in self.kb.get_rules(ag, version):
                out.setdefault(r.id, r)
        return out

    def _label(self, d: Deviation, label: str, rule: str | None, why: str, resolved_by: str = "rules") -> bool:
        d.label, d.resolved_by, d.explanation = label, resolved_by, why
        if rule:
            d.rule = rule
            r = self.rules.get(rule)
            if r:
                d.criterion, d.sources = r.criterion, list(r.sources)
        return True

    # ------------------------------------------------------------ main entry
    def check(self, test_case_id: str | Case, files: list[str | bytes], valid_on: date, version: str | None = None,
              triage: Triage | None = None) -> CheckResult:
        version = version or params_mod.version_on(self.kb, valid_on)
        self.version = version
        self.rules = self._rules(version)
        self.params = params_mod.load(self.kb, version=version)
        sc = load_scenario(self.kb, test_case_id)
        self.sc = sc
        chain = build_chain(sc, version, self.kb)
        self.chain = chain

        issues: list[ParseIssue] = []
        actual: list[Record] = []
        for f in files:
            pf = parse_file(f, self.kb, version)
            issues += pf.issues
            actual += pf.messages
        expected = chain.employer()
        differ = Differ(self.kb, version)
        devs, pairs = differ.diff(expected, actual)
        self.actual_by_step = {m.step: r for m, r in pairs}
        step_of = {id(r): m.step for m, r in pairs}

        # parse issues -> invalid
        for i in issues:
            d = Deviation(record=i.record, field=i.field, kind="value_differs", actual=i.message)
            self._label(d, "invalid", None, f"format: {i.message} (line {i.line}, position {i.pos})")
            devs.append(d)

        # format and rule-field checks on the vendor's own messages
        results: list[tuple[Record, RuleResult]] = []
        employer = [r for r in actual if r.abgabegrund in EMPLOYER_TYPES]
        cur = sc.test_case.inputs.current
        for r in actual:
            results += [(r, x) for x in formats.check_mm_flags(r)]
            results += [(r, x) for x in formats.check_key_values(r)]
            if r.abgabegrund in EMPLOYER_TYPES:
                results.append((r, formats.check_uuid(r)))
            if r.abgabegrund == "41":
                results += [(r, x) for x in formats.check_41_format(r, cur.start if cur else None) if x.rule != "F41-8"]
        results += [(self._chain_record(employer, x), x) for x in formats.check_chain(employer)]
        covered = {(d.abgabegrund, f"{d.record}.{base_field_name(d.field or '')}") for d in devs}
        for rec, x in results:
            if x.ok:
                continue
            ag = rec.abgabegrund if rec else None
            if (ag, x.field) in covered:
                continue
            rec_name, _, fld = (x.field or "DSLW.").partition(".")
            d = Deviation(step=step_of.get(id(rec)), abgabegrund=ag, record=rec_name, field=fld or None,
                          kind="value_differs", expected=_s(x.expected), actual=_s(x.actual))
            self._label(d, "invalid" if x.rule.startswith(("F", "S-")) else "bug", x.rule, x.message)
            devs.append(d)
            covered.add((ag, x.field))

        # analysis of the diff deviations
        for d in devs:
            if d.resolved_by:
                continue
            if self.catalogue.resolve(d, self.kb):
                continue
            if self.recheck(d):
                continue
            d.label, d.resolved_by = "unclear", None
            d.explanation = "no rule, catalogue entry or precedent covers this deviation"
            if triage:
                triage(d, version)

        for n, d in enumerate(devs):
            if not d.id:
                d.id = _dev_id(d, 1000 + n)
        labels = [d.label for d in devs]
        return CheckResult(
            test_case_id=sc.id, valid_on=valid_on, version=version, label=worst(labels), deviations=devs,
            parse_issues=issues, counts=dict(Counter(labels)),
            resolved_by=dict(Counter(d.resolved_by or "open" for d in devs)),
            expected_messages=len(expected), actual_messages=len(actual),
        )

    @staticmethod
    def _chain_record(employer: list[Record], x: RuleResult) -> Record | None:
        if x.rule in ("C-3", "C-4", "C-5", "C-8") or (x.field or "").startswith("DBSD"):
            return next((r for r in employer if r.abgabegrund == "88"), None)
        return next((r for r in employer if r.dsid == x.actual), employer[0] if employer else None)

    # ------------------------------------------------------------ b. rule re-check
    def recheck(self, d: Deviation) -> bool:
        ag, f = d.abgabegrund, f"{d.record}.{base_field_name(d.field or '')}"
        i = self.sc.test_case.inputs
        if ag == "41":
            if d.kind == "missing_message":
                rule = deciding_rule(i.current, i.priors, i.report_date, self.params)
                return self._label(d, "bug", rule, f"a 41 is required under {self.version} ({self._why41()}) "
                                                   f"but none was sent")
            if d.kind == "extra_message":
                failed = self.chain.decision.trace.failed
                rule = failed[-1] if failed else "R41-1"
                return self._label(d, "bug", rule, f"no 41 may be sent under {self.version}: "
                                                   f"{self._last_step(rule)}")
            if d.kind in ("missing_group", "extra_group", "order_differs"):
                return self._recheck_groups(d)
            if f in F41_6:
                return self._label(d, "invalid", "F41-6", f"{f} is an insurer-only field and must be zero")
            if f in F41_9:
                return self._label(d, "invalid", "F41-9", f"{f} is an insurer-only field and must be zero")
            if f == "DBVO.AU-AB-AG":
                return self._label(d, "invalid", "F41-5", "AU-AB-AG must be the start of the current AU")
            if f == "DBVO.GRUNDAV":
                return self._label(d, "invalid", "F41-4", "GRUNDAV must be 1 (sickness)")
        if ag == "01":
            if f == "DBAL.DATUM-EGZBIS":
                return self._label(d, "bug", "E-1", f"pay end must be the EFZ end {d.expected} computed from the "
                                                    f"latest 61, vendor sent {d.actual}")
            if d.kind == "missing_message":
                rule = "E-2" if (d.step or 0) > 3 else "E-1"
                return self._label(d, "bug", rule, "the 01 certificate is missing")
        if ag == "88":
            if d.kind == "missing_message":
                return self._label(d, "bug", "E-2", "the corrected 61 changed the EFZ end: the first 01 must be "
                                                    "cancelled with an 88 before the new 01")
            if f == "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG":
                return self._label(d, "bug", "C-3", "the 88 must point to the 01 being cancelled")
            if f in ("DBSD.VORNAME", "DBSD.FAMILIENNAME"):
                return self._label(d, "bug", "C-4", "the 88 names must be the names in the cancelled record")
        return False

    def _why41(self) -> str:
        v = self.chain.decision.trace.values
        return f"{len(v.get('chain', []))} chained prior period(s), total {v.get('total')} days"

    def _last_step(self, rule: str) -> str:
        steps = [s for s in self.chain.decision.trace.steps if s.startswith(rule)]
        return steps[-1] if steps else rule

    def _recheck_groups(self, d: Deviation) -> bool:
        chain = self.chain.decision.chain
        if d.kind == "order_differs":
            return self._label(d, "bug", "F41-8", "periods must be listed newest first (VB 3.12.7)")
        if d.kind == "missing_group":
            oldest = f"{chain[-1].start}..{chain[-1].end}" if chain else None
            if d.expected == oldest:
                return self._label(d, "bug", "R41-3", f"the chain must go back to the first illness: {oldest} is "
                                                      f"chained (gap at most {self.params.gap_months} months) but "
                                                      f"missing")
            return self._label(d, "correct_variant", "R41-3", f"{d.expected} not listed: at least one period is "
                                                              f"required and the oldest chained period is present; "
                                                              f"note: 'as many as possible' (VB 3.12)")
        if d.kind == "extra_group":
            uncert = {f"{a.start}..{a.end}" for a in self.sc.test_case.inputs.priors if not a.certified}
            if d.actual in uncert:
                return self._label(d, "bug", "R41-5", f"{d.actual} has no sick note and must not be listed")
            return self._label(d, "bug", "R41-3", f"{d.actual} is not part of the chain (gap over "
                                                  f"{self.params.gap_months} months)")
        return False


def _s(v):
    return v if v is None or isinstance(v, (str, int, list)) else str(v)


def check(kb: KnowledgeBase, test_case_id: str | Case, files: list[str | bytes], valid_on: date,
          catalogue: Catalogue | None = None, version: str | None = None, triage: Triage | None = None) -> CheckResult:
    return Checker(kb, catalogue).check(test_case_id, files, valid_on, version=version, triage=triage)


def expected_chain(kb: KnowledgeBase, test_case_id: str, version: str) -> tuple[Scenario, ChainResult]:
    sc = load_scenario(kb, test_case_id)
    return sc, build_chain(sc, version, kb)
