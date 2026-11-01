"""Rule checker: exact match first, then each deviation gets one label.

Flow per submission: parse (issues -> invalid) -> expected chain under the rule set valid on
`valid_on` -> 3-level diff -> rule-field and format checks -> per deviation: a. catalogue and
precedents, b. rule re-check, c. left `unclear` with an empty AI slot (filled by llm/).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date

from engine import families, layouts
from engine.diff import Differ, _dev_id
from engine.expected import ChainResult, Scenario, build_chain, load_scenario
from engine.families.base import CheckContext
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
from engine.rules import blocks, formats
from engine.rules import params as params_mod
from engine.variants import Catalogue
from kg.interface import KnowledgeBase

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
        for ag in sorted(self.family.codes):
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
        sc = load_scenario(self.kb, test_case_id)
        self.sc = sc
        self.family = families.of_case(sc.test_case)
        self.rules = self._rules(version)
        self.params = self.family.params(self.kb, version)
        chain = build_chain(sc, version, self.kb)
        self.chain = chain

        issues: list[ParseIssue] = []
        actual: list[Record] = []
        for f in files:
            pf = parse_file(f, self.kb, version, valid_on)
            issues += pf.issues
            actual += pf.messages
        expected = chain.employer()
        differ = Differ(self.kb, version, valid_on)
        devs, pairs = differ.diff(expected, actual)
        self.actual_by_step = {m.step: r for m, r in pairs}
        step_of = {id(r): m.step for m, r in pairs}

        # parse issues -> invalid
        for i in issues:
            d = Deviation(record=i.record, field=i.field, kind="value_differs", actual=i.message)
            self._label(d, "invalid", None, f"Format: {i.message} (Zeile {i.line}, Stelle {i.pos})")
            devs.append(d)

        # format and rule-field checks on the vendor's own messages: shared ones, then the family's
        self.ctx = CheckContext(kb=self.kb, version=version, scenario=sc, chain=chain, rules=self.rules,
                                actual=actual, params=self.params, step_of=step_of, label=self._label)
        self.flags = layouts.get(self.kb, "DSLW", version, valid_on).flags  # block -> MM flag
        results: list[tuple[Record | None, RuleResult]] = []
        for r in actual:
            results += [(r, x) for x in formats.check_mm_flags(r)]
            results += [(r, x) for x in blocks.check_block_presence(r, self.flags)]
            results += [(r, x) for x in formats.check_key_values(r)]
            if r.abgabegrund in self.family.employer_codes:
                results.append((r, formats.check_uuid(r)))
        results += self.family.check_records(self.ctx)
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
            self._label(d, "invalid" if x.rule.startswith(("F", "S-", "A3-")) else "bug", x.rule, x.message)
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
            d.explanation = "keine Regel, kein Katalogeintrag und kein Präzedenzfall deckt diese Abweichung ab"
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

    # ------------------------------------------------------------ b. rule re-check
    def recheck(self, d: Deviation) -> bool:
        """Shared rules first (VB Anlage 3 blocks), then the family's."""
        hit = blocks.recheck(d, {flag: blk for blk, flag in self.flags.items()})
        if hit:
            return self._label(d, hit[0], blocks.RULE, hit[1])
        return self.family.recheck(self.ctx, d)


def _s(v):
    return v if v is None or isinstance(v, (str, int, list)) else str(v)


def check(kb: KnowledgeBase, test_case_id: str | Case, files: list[str | bytes], valid_on: date,
          catalogue: Catalogue | None = None, version: str | None = None, triage: Triage | None = None) -> CheckResult:
    return Checker(kb, catalogue).check(test_case_id, files, valid_on, version=version, triage=triage)


def expected_chain(kb: KnowledgeBase, test_case_id: str, version: str) -> tuple[Scenario, ChainResult]:
    sc = load_scenario(kb, test_case_id)
    return sc, build_chain(sc, version, kb)
