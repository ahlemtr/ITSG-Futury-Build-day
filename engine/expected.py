"""Scenarios and expected message chains.

A scenario = case facts from the knowledge base (`kb.get_test_case`, as `Case`) + chain-only extras from
`fixtures/scenarios/<id>.yaml`. `build_chain` turns it into the expected messages
under one rule set version. Clones are single-step tests: only the 41 decision.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from engine.model import AuPeriod, Case, Decision41, ExpectedMessage, Trace
from engine.rules import params as params_mod
from engine.rules.vorerkrankung import efz_end, must_send_41
from kg.interface import KnowledgeBase

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios"
DEFAULT_EXTRAS = "peter"


class Scenario(BaseModel):
    test_case: Case
    extras: dict[str, Any]

    @property
    def id(self) -> str:
        return self.test_case.id


class ChainResult(BaseModel):
    version: str
    messages: list[ExpectedMessage]
    decision: Decision41
    efz: dict[str, date] = {}
    traces: dict[str, Trace] = {}

    def employer(self) -> list[ExpectedMessage]:
        return [m for m in self.messages if m.actor == "employer"]


def load_extras(kb: KnowledgeBase, tc: Case) -> dict[str, Any]:
    seen = set()
    key: str | None = tc.id
    while key and key not in seen:
        seen.add(key)
        path = SCENARIO_DIR / f"{key}.yaml"
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            key = kb.get_test_case(key).parent if key != tc.id else tc.parent
        except KeyError:
            key = None
    return yaml.safe_load((SCENARIO_DIR / f"{DEFAULT_EXTRAS}.yaml").read_text(encoding="utf-8"))


def get_case(kb: KnowledgeBase, key: str) -> Case:
    """The KG test case as the engine's typed `Case`."""
    return Case.from_kb(kb.get_test_case(key))


def load_scenario(kb: KnowledgeBase, test_case: str | Case) -> Scenario:
    tc = get_case(kb, test_case) if isinstance(test_case, str) else test_case
    return Scenario(test_case=tc, extras=load_extras(kb, tc))


# ---------------------------------------------------------------- message builders


def _head(sc: Scenario, step: int, abgabegrund: str, insurer: bool = False, korr: int = 0) -> dict[str, Any]:
    e, p = sc.extras["employer"], sc.extras["person"]
    snd, rcv = (e["empfaengernummer"], e["absendernummer"]) if insurer else (e["absendernummer"], e["empfaengernummer"])
    return {
        "VERFAHREN": e["verfahren"], "ABSENDERNUMMER": snd, "EMPFAENGERNUMMER": rcv, "VERSION-NR": e["version_nr"],
        "DATUM-ERSTELLUNG": sc.extras.get("created"), "FEHLER-KENNZ": 0, "FEHLER-ANZAHL": 0, "VSNR": p["vsnr"],
        "GEBURTSDAT": p["geburtsdat"], "BBNR-VU": e["bbnr_vu"], "DATENSATZ-ID": sc.extras["ids"][str(step)],
        "PRODUKT-IDENTIFIER": "" if insurer else e["produkt_identifier"],
        "MODIFIKATIONS-IDENTIFIER": "" if insurer else e["modifikations_identifier"],
        "DATUM-VERARBEITUNG": "0" * 20, "BBNR-KK": e["bbnr_kk"], "BBNR-ABRECHNUNGSSTELLE": "",
        "RUECKMELDUNG-ENTGELTERSATZLEISTUNG": "N", "ABGABEGRUND": int(abgabegrund), "KORR-ABGABEGRUND": korr,
        "ABRECHNUNGSPROGRAMM": 0 if insurer else e["abrechnungsprogramm"],
    }


def _dbna(sc: Scenario) -> dict[str, Any]:
    p = sc.extras["person"]
    return {"FAMILIENNAME": p["familienname"], "VORNAME": p["vorname"],
            "VORSATZWORT": "", "NAMENSZUSATZ": "", "TITEL": "", "KENNZ-AEND-BER": ""}


def _dbid(sc: Scenario, ref: str = "") -> dict[str, Any]:
    return {"AKTENZEICHEN-SV": "", "AKTENZEICHEN-VERURSACHER": sc.extras.get("azvu", ""), "REFERENZ-ID": ref}


def _group(a: AuPeriod, nw: int = 0, au: int = 0) -> dict[str, Any]:
    return {"BEGINN-AU": a.start, "ENDE-AU": a.end, "KZ-NACHWEIS": nw, "TEIL-NACHWEIS-AU-BEGINN": None,
            "TEIL-NACHWEIS-AU-ENDE": None, "KZ-AU": au, "TEIL-ANR-AU-BEGINN": None, "TEIL-ANR-AU-ENDE": None}


def msg_41(sc: Scenario, chain: list[AuPeriod], step: int = 1) -> ExpectedMessage:
    cur = sc.test_case.inputs.current
    blocks = {
        "DBNA": _dbna(sc),
        "DBVO": {"GRUNDAV": 1, "AU-AB-AG": cur.start, "AU-AB-SV": None, "KZ-AK-AU": 0, "12-MONATSFRIST-AB": None,
                 "groups": [_group(a) for a in chain]},
        "DBAP": dict(sc.extras["employer"].get("contact", {})),
        "DBID": _dbid(sc),
    }
    return ExpectedMessage(step=step, round=1, actor="employer", abgabegrund="41", head=_head(sc, step, "41"),
                           blocks=blocks)


def insurer_flags(sc: Scenario, which: str, a: AuPeriod) -> tuple[int, int]:
    ins = sc.extras["insurer"]
    f = {**ins["default_flags"], **ins.get(which, {}).get(str(a.start), {})}
    return f["kz_nachweis"], f["kz_au"]


def msg_61(sc: Scenario, chain: list[AuPeriod], which: str, step: int, round_: int, ref: str,
           azvu: str | None = None) -> ExpectedMessage:
    cur = sc.test_case.inputs.current
    groups = [_group(a, *insurer_flags(sc, which, a)) for a in chain]
    counted = [a for a, g in zip(chain, groups) if g["KZ-AU"] in (1, 5)]
    frist = min((a.start for a in counted), default=None)  # K61-6
    blocks = {
        "DBNA": _dbna(sc),
        "DBVO": {"GRUNDAV": 1, "AU-AB-AG": cur.start, "AU-AB-SV": cur.start, "KZ-AK-AU": 0 if cur.certified else 4,
                 "12-MONATSFRIST-AB": frist, "groups": groups},
        "DBID": {**_dbid(sc, ref), **({"AKTENZEICHEN-VERURSACHER": azvu} if azvu is not None else {})},
    }
    return ExpectedMessage(step=step, round=round_, actor="insurer", abgabegrund="61",
                           head=_head(sc, step, "61", insurer=True), blocks=blocks,
                           note=f"{which.replace('_', ' ')} (TEEK0)")


def msg_01(sc: Scenario, step: int, round_: int, egz_bis: date) -> ExpectedMessage:
    cur, s = sc.test_case.inputs.current, sc.extras.get("salary", {})
    dbal = {"DATUM-AB": cur.start, "AE-ERSTTAG": 0, "DATUM-EGZBIS": egz_bis,
            "ENDE-BV-AM": sc.test_case.inputs.employment_end, "ENDE-BV-ZUM": None, "GRUNDBEEND": 0, "PFLZUSCHLAG": "N",
            "KINDER-UNTER-25": 0, "ARBZEITMOD": "N", "MM-KUG": 0}
    dbae = {"EAZ-BEGINN-1": s.get("eaz_beginn"), "EAZ-ENDE-1": s.get("eaz_ende"), "BRUTTO-1": Decimal(str(s.get("brutto", 0))),
            "NETTO-1": Decimal(str(s.get("netto", 0))), "ENTGART": s.get("entgart", 0)}
    blocks = {"DBNA": _dbna(sc), "DBAL": dbal, "DBAE": dbae, "DBAP": dict(sc.extras["employer"].get("contact", {})),
              "DBID": _dbid(sc)}
    return ExpectedMessage(step=step, round=round_, actor="employer", abgabegrund="01", head=_head(sc, step, "01"),
                           blocks=blocks, note=f"pay until {egz_bis}")


def msg_88(sc: Scenario, step: int, round_: int, cancelled: ExpectedMessage) -> ExpectedMessage:
    blocks = {"DBSD": {"DATENSATZ-ID-URSPRUNGSMELDUNG": cancelled.head["DATENSATZ-ID"],
                       "VORNAME": cancelled.blocks["DBNA"]["VORNAME"],
                       "FAMILIENNAME": cancelled.blocks["DBNA"]["FAMILIENNAME"],
                       "AKTENZEICHEN-VERURSACHER": sc.extras.get("azvu", "")}}
    return ExpectedMessage(step=step, round=round_, actor="employer", abgabegrund="88",
                           head=_head(sc, step, "88", korr=1), blocks=blocks, note="cancels the first 01")


def msg_62(sc: Scenario, step: int, round_: int, ref: str, benefit_start: date) -> ExpectedMessage:
    end = sc.test_case.inputs.employment_end or sc.test_case.inputs.current.end
    blocks = {"DBNA": _dbna(sc),
              "DBEE": {"EEL-ABAG": benefit_start, "EEL-ABSV": benefit_start, "EEL-ENDE": end,
                       "EEL-ENDE-GRUND": sc.extras["insurer"].get("eel_ende_grund", 99)},
              "DBID": _dbid(sc, ref)}
    return ExpectedMessage(step=step, round=round_, actor="insurer", abgabegrund="62",
                           head=_head(sc, step, "62", insurer=True), blocks=blocks, note="end of benefit (TEEK0)")


# ---------------------------------------------------------------- chains


def decide(kb: KnowledgeBase, sc: Scenario, version: str) -> Decision41:
    i = sc.test_case.inputs
    return must_send_41(i.current, i.priors, i.report_date, params_mod.load(kb, version=version))


def build_chain(sc: Scenario, version: str, kb: KnowledgeBase) -> ChainResult:
    p = params_mod.load(kb, version=version)
    d = decide(kb, sc, version)
    res = ChainResult(version=version, messages=[], decision=d, traces={"41": d.trace})
    if not d.send:
        return res
    m41 = msg_41(sc, d.chain)
    res.messages.append(m41)
    if sc.test_case.steps != "chain":
        return res
    cur = sc.test_case.inputs.current
    first = msg_61(sc, d.chain, "first_61", 2, 1, m41.head["DATENSATZ-ID"])
    efz1, t1 = efz_end(cur.start, first.blocks["DBVO"]["groups"], p)
    m01 = msg_01(sc, 3, 2, efz1)
    corrected = msg_61(sc, d.chain, "corrected_61", 4, 2, m41.head["DATENSATZ-ID"])
    efz2, t2 = efz_end(cur.start, corrected.blocks["DBVO"]["groups"], p)
    res.messages += [first, m01, corrected]
    res.efz = {"after_first_61": efz1, "after_corrected_61": efz2}
    res.traces.update(efz_first=t1, efz_corrected=t2)
    latest_01, step = m01, 5
    if efz2 != efz1:  # E-2: corrected 61 changes the EFZ end -> 88 + new 01
        m88 = msg_88(sc, 5, 3, m01)
        new01 = msg_01(sc, 6, 3, efz2)
        res.messages += [m88, new01]
        latest_01, step = new01, 7
    benefit_start = res.efz["after_corrected_61"] + timedelta(days=1)
    res.messages.append(msg_62(sc, step, 3, latest_01.head["DATENSATZ-ID"], benefit_start))
    return res
