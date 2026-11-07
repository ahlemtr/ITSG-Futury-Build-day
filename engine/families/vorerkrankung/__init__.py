"""Prior-illness family (Vorerkrankung, VB 3.12): when the employer must send a 41, which periods it
lists, the insurer's 61, the EFZ end on the 01, cancel and resend (88 + new 01), end of benefit (62).
Reference case: Peter (ITSG Hinweise)."""

from __future__ import annotations

from collections.abc import Callable

from engine.families.base import ChainResult, CheckContext, Family, Scenario
from engine.families.vorerkrankung import builder, chain, checks
from engine.model import Case, Deviation, ExpectedMessage, ExpectedOutcome, Record, RuleResult, TestInputs
from engine.rules import params as params_mod
from kg.interface import KnowledgeBase


class Vorerkrankung(Family):
    id = "vorerkrankung"
    title = "Vorerkrankung"
    codes = frozenset({"41", "61", "01", "88", "62"})
    Inputs = TestInputs
    Outcome = ExpectedOutcome

    def params(self, kb: KnowledgeBase, version: str) -> params_mod.Params:
        return params_mod.load(kb, version=version)

    def outcome(self, kb: KnowledgeBase, case: Case, version: str) -> ExpectedOutcome:
        return builder.outcome(kb, case, version)

    def build_chain(self, kb: KnowledgeBase, scenario: Scenario, version: str) -> ChainResult:
        return chain.build_chain(kb, scenario, version)

    def check_records(self, ctx: CheckContext) -> list[tuple[Record | None, RuleResult]]:
        return checks.check_records(ctx)

    def recheck(self, ctx: CheckContext, d: Deviation) -> bool:
        return checks.recheck(ctx, d)

    def single_step_replies(self, kb: KnowledgeBase, scenario: Scenario, ch: ChainResult) -> list[ExpectedMessage]:
        reply = chain.single_step_reply(scenario, ch)
        return [reply] if reply else []

    def adapt_reply(self, reply: ExpectedMessage, vendor: list[Record]) -> ExpectedMessage:
        """REFERENZ-ID, AKTENZEICHEN-VERURSACHER and BBNR-VU from the vendor's 41 (61) or latest 01 (62);
        on the 61 the vendor's periods in the vendor's order, periods the insurer knows on top appended."""
        m = reply.model_copy(deep=True)
        v41 = next((r for r in vendor if r.abgabegrund == "41"), None)
        v01 = [r for r in vendor if r.abgabegrund == "01"]
        ref = v41 if m.abgabegrund == "61" else (v01[-1] if v01 else None)
        if ref is not None:
            m.blocks["DBID"]["REFERENZ-ID"] = ref.dsid or ""
            m.blocks["DBID"]["AKTENZEICHEN-VERURSACHER"] = ref.get("DBID.AKTENZEICHEN-VERURSACHER") or ""
            m.head["BBNR-VU"] = ref.get("DSLW.BBNR-VU") or m.head["BBNR-VU"]
        if m.abgabegrund == "61" and v41 is not None:
            exp_groups = {(g["BEGINN-AU"], g["ENDE-AU"]): g for g in m.blocks["DBVO"]["groups"]}
            ordered = []
            for s, e in v41.periods:  # K61-3
                g = exp_groups.pop((s, e), None)
                ordered.append(g or {**next(iter(m.blocks["DBVO"]["groups"])), "BEGINN-AU": s, "ENDE-AU": e,
                                     "KZ-NACHWEIS": 4, "KZ-AU": 2})
            ordered += list(exp_groups.values())
            m.blocks["DBVO"]["groups"] = ordered
        return m

    def self_check(self, kb: KnowledgeBase, scenario: Scenario, replies: list[Record],
                   employer: list[Record]) -> list[RuleResult]:
        return checks.self_check(kb, scenario, replies, employer)

    def round_one_rules(self, case: Case) -> list[str]:
        return [r for r in case.targets if r.startswith("R41")]

    def generators(self) -> dict[str, Callable[[KnowledgeBase, Case], list[Case]]]:
        return dict(builder.GENERATORS)

    def hidden(self, kb: KnowledgeBase, case: Case, seed: int = 0) -> Case:
        return builder.hidden(kb, case, seed)

    def story(self, case: Case) -> str:
        return builder.story_text(case)


FAMILY = Vorerkrankung()
