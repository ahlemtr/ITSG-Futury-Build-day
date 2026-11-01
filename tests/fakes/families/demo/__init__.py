"""A made-up mini family for tests only: proves that a family plugs in by adding files.

Story: the employer must send one 42 (Anforderung Ende Entgeltersatzleistung) when the case says so.
One rule (DEMO-1). Never shown in the UI, never in kg/seed.
"""

from __future__ import annotations

from pydantic import BaseModel

from engine.families.base import ChainResult, CheckContext, Family, Scenario
from engine.model import Case, Deviation, ExpectedMessage


class DemoInputs(BaseModel):
    send_42: bool = True


class DemoOutcome(BaseModel):
    send_42: bool


def _head(sc: Scenario) -> dict:
    e, p = sc.extras["employer"], sc.extras["person"]
    return {"VERFAHREN": e["verfahren"], "ABSENDERNUMMER": e["absendernummer"],
            "EMPFAENGERNUMMER": e["empfaengernummer"], "VERSION-NR": e["version_nr"], "VSNR": p["vsnr"],
            "GEBURTSDAT": p["geburtsdat"], "BBNR-VU": e["bbnr_vu"],
            "DATENSATZ-ID": "DE000000-0000-4000-8000-000000000042", "PRODUKT-IDENTIFIER": e["produkt_identifier"],
            "MODIFIKATIONS-IDENTIFIER": e["modifikations_identifier"], "DATUM-VERARBEITUNG": "0" * 20,
            "BBNR-KK": e["bbnr_kk"], "RUECKMELDUNG-ENTGELTERSATZLEISTUNG": "N", "ABGABEGRUND": 42,
            "KORR-ABGABEGRUND": 0, "ABRECHNUNGSPROGRAMM": e["abrechnungsprogramm"]}


class Demo(Family):
    id = "demo"
    title = "Demo"
    codes = frozenset({"42"})
    employer_codes = frozenset({"42"})
    Inputs = DemoInputs
    Outcome = DemoOutcome

    def params(self, kb, version):
        return None

    def outcome(self, kb, case: Case, version: str) -> DemoOutcome:
        return DemoOutcome(send_42=case.inputs.send_42)

    def build_chain(self, kb, scenario: Scenario, version: str) -> ChainResult:
        msgs = []
        if scenario.test_case.inputs.send_42:
            p = scenario.extras["person"]
            msgs.append(ExpectedMessage(step=1, round=1, actor="employer", abgabegrund="42", head=_head(scenario),
                                        blocks={"DBNA": {"FAMILIENNAME": p["familienname"], "VORNAME": p["vorname"]},
                                                "DBAP": dict(scenario.extras["employer"].get("contact", {}))}))
        return ChainResult(version=version, messages=msgs)

    def recheck(self, ctx: CheckContext, d: Deviation) -> bool:
        if d.abgabegrund == "42" and d.kind in ("missing_message", "extra_message"):
            return ctx.label(d, "bug", "DEMO-1", "the case decides whether a 42 is sent")
        return False

    def story(self, case: Case) -> str:
        return "Demo: senden Sie eine 42.\n" if case.inputs.send_42 else "Demo: senden Sie nichts.\n"


FAMILY = Demo()
