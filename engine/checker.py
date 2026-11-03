"""Rule checker: exact match first, then each deviation gets one label.

Flow per submission: parse (issues -> invalid) -> expected chain under the rule set valid on
`valid_on` -> 3-level diff -> rule checks on the vendor's messages (common, then the family's) -> per
deviation: a. allowed variant of the case, catalogue and precedents, b. the failed rule check on the same
field, else the family's re-check, c. left `unclear` with an empty AI slot (filled by llm/).
A broken rule is labelled by its card's kind: format -> invalid, every other kind -> bug.
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
from engine.rules import common
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

    def _label_of(self, rule: str) -> str:
        r = self.rules.get(rule)
        return "invalid" if r is not None and r.kind == "format" else "bug"

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
        results = [(r, x) for r in actual for x in common.check_message(r, self.flags)]
        results += common.check_case(actual)
        results += self.family.check_records(self.ctx)
        # one failed check per message type and field; a field the diff already shows keeps the diff's deviation
        # and is labelled from this check in the analysis below
        self.failed: dict[tuple[str | None, str | None], RuleResult] = {}
        covered = {_key(d) for d in devs}
        for rec, x in results:
            ag = rec.abgabegrund if rec else None
            if x.ok or (ag, x.field) in self.failed:
                continue
            self.failed[(ag, x.field)] = x
            if (ag, x.field) in covered:
                continue
            rec_name, _, fld = (x.field or "DSLW.").partition(".")
            d = Deviation(step=step_of.get(id(rec)), abgabegrund=ag, record=rec_name, field=fld or None,
                          kind="value_differs", expected=_s(x.expected), actual=_s(x.actual))
            self._label(d, self._label_of(x.rule), x.rule, x.message)
            devs.append(d)

        # analysis of the diff deviations
        for d in devs:
            if d.resolved_by:
                continue
            if self._case_variant(d):
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

    def _case_variant(self, d: Deviation) -> bool:
        """A justified variant of this test case only (e.g. an official task allows an alternative date). Matched by
        signature, and by expected / actual value where the entry names them; read before the global catalogue."""
        for v in self.sc.test_case.allowed_variants:
            if v.get("signature") != d.signature:
                continue
            if "expected" in v and str(v["expected"]) != str(d.expected):
                continue
            if "actual" in v and str(v["actual"]) != str(d.actual):
                continue
            d.label, d.resolved_by = v.get("verdict", "correct_variant"), "catalogue"
            d.explanation = f"zulässige Variante dieses Testfalls: {v.get('reason', '')}"
            d.sources = [v["source"]] if v.get("source") else []
            return True
        return False

    # ------------------------------------------------------------ b. rule re-check
    def recheck(self, d: Deviation) -> bool:
        """The failed rule check on the deviation's field, else the family's re-check."""
        x = self.failed.get(_key(d))
        if x is not None:
            return self._label(d, self._label_of(x.rule), x.rule, x.message)
        return self.family.recheck(self.ctx, d)


def _key(d: Deviation) -> tuple[str | None, str]:
    return d.abgabegrund, f"{d.record}.{base_field_name(d.field or '')}"


def _s(v):
    return v if v is None or isinstance(v, (str, int, list)) else str(v)


def check(kb: KnowledgeBase, test_case_id: str | Case, files: list[str | bytes], valid_on: date,
          catalogue: Catalogue | None = None, version: str | None = None, triage: Triage | None = None) -> CheckResult:
    return Checker(kb, catalogue).check(test_case_id, files, valid_on, version=version, triage=triage)


def expected_chain(kb: KnowledgeBase, test_case_id: str, version: str) -> tuple[Scenario, ChainResult]:
    sc = load_scenario(kb, test_case_id)
    return sc, build_chain(sc, version, kb)
