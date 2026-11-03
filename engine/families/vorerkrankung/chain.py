"""Expected message chain of the prior-illness family (Peter: 41, 61, 01, 61, 88, 01, 62).

Clones are single-step tests: only the 41 decision.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from engine.families.base import ChainResult, Scenario
from engine.families.vorerkrankung import rules
from engine.families.vorerkrankung.rules import efz_end
from engine.model import AuPeriod, Decision41, ExpectedMessage
from engine.rules import params as params_mod
from kg.interface import KnowledgeBase

# ---------------------------------------------------------------- message builders


def _head(sc: Scenario, step: int, abgabegrund: str, insurer: bool = False) -> dict[str, Any]:
    e, p = sc.extras["employer"], sc.extras["person"]
    snd, rcv = (e["empfaengernummer"], e["absendernummer"]) if insurer else (e["absendernummer"], e["empfaengernummer"])
    return {
        "VERFAHREN": e["verfahren"], "ABSENDERNUMMER": snd, "EMPFAENGERNUMMER": rcv, "VERSION-NR": e["version_nr"],
        "DATUM-ERSTELLUNG": sc.extras.get("created"), "FEHLER-KENNZ": 0, "FEHLER-ANZAHL": 0, "VSNR": p["vsnr"],
        "GEBURTSDAT": p["geburtsdat"], "BBNR-VU": e["bbnr_vu"], "DATENSATZ-ID": sc.extras["ids"][str(step)],
        "PRODUKT-IDENTIFIER": "" if insurer else e["produkt_identifier"],
        "MODIFIKATIONS-IDENTIFIER": "" if insurer else e["modifikations_identifier"],
        "DATUM-VERARBEITUNG": "0" * 20, "BBNR-KK": e["bbnr_kk"], "BBNR-ABRECHNUNGSSTELLE": "",
        "RUECKMELDUNG-ENTGELTERSATZLEISTUNG": "N", "ABGABEGRUND": int(abgabegrund), "KORR-ABGABEGRUND": 0,  # S-2: 00 except on a 66
        "ABRECHNUNGSPROGRAMM": 0 if insurer else e["abrechnungsprogramm"],
    }


def _dbna(sc: Scenario) -> dict[str, Any]:
    p = sc.extras["person"]
    return {"FAMILIENNAME": p["familienname"], "VORNAME": p["vorname"],
            "VORSATZWORT": "", "NAMENSZUSATZ": "", "TITEL": "", "KENNZ-AEND-BER": ""}


def _dbid(sc: Scenario, ref: str = "") -> dict[str, Any]:
    return {"AKTENZEICHEN-SV": "", "AKTENZEICHEN-VERURSACHER": sc.extras.get("azvu", ""), "REFERENZ-ID": ref}


def _group(a: AuPeriod, flags: dict[str, Any] | None = None) -> dict[str, Any]:
    g = {"BEGINN-AU": a.start, "ENDE-AU": a.end, "KZ-NACHWEIS": 0, "TEIL-NACHWEIS-AU-BEGINN": None,
         "TEIL-NACHWEIS-AU-ENDE": None, "KZ-AU": 0, "TEIL-ANR-AU-BEGINN": None, "TEIL-ANR-AU-ENDE": None}
    return {**g, **(flags or {})}


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


def _insurer_contact(sc: Scenario) -> dict[str, Any] | None:
    """DBAP of the insurer's replies (VB Anlage 3: J on 61 and 62)."""
    contact = sc.extras.get("insurer", {}).get("contact")
    return dict(contact) if contact else None


def msg_61(sc: Scenario, chain: list[AuPeriod], which: str, step: int, round_: int, ref: str,
           azvu: str | None = None) -> ExpectedMessage:
    cur = sc.test_case.inputs.current
    reply = "first" if which == "first_61" else "corrected"
    groups = [_group(a, rules.insurer_flags(a, reply)) for a in chain]  # K61-4, K61-5 from the case facts
    counted = [a for a, g in zip(chain, groups) if g["KZ-AU"] in (1, 5)]
    frist = min((a.start for a in counted), default=None)  # K61-6
    blocks = {
        "DBNA": _dbna(sc),
        # K61-8: AU-AB-SV only when the insurer's start differs from the employer's (VB 3.12.3, BP 16.1)
        "DBVO": {"GRUNDAV": 1, "AU-AB-AG": cur.start,
                 "AU-AB-SV": cur.insurer_start if cur.insurer_start and cur.insurer_start != cur.start else None,
                 "KZ-AK-AU": 0 if cur.certified else rules.INTERIM_KZ_AK_AU,  # K61-7
                 "12-MONATSFRIST-AB": frist, "groups": groups},
        "DBID": {**_dbid(sc, ref), **({"AKTENZEICHEN-VERURSACHER": azvu} if azvu is not None else {})},
    }
    if (contact := _insurer_contact(sc)) is not None:
        blocks["DBAP"] = contact
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
                           head=_head(sc, step, "88"), blocks=blocks, note="cancels the first 01")


def msg_62(sc: Scenario, step: int, round_: int, ref: str, benefit_start: date) -> ExpectedMessage:
    end = sc.test_case.inputs.employment_end or sc.test_case.inputs.current.end
    blocks = {"DBNA": _dbna(sc),
              "DBEE": {"EEL-ABAG": benefit_start, "EEL-ABSV": benefit_start, "EEL-ENDE": end,
                       "EEL-ENDE-GRUND": sc.extras["insurer"].get("eel_ende_grund", 99)},
              "DBID": _dbid(sc, ref)}
    if (contact := _insurer_contact(sc)) is not None:
        blocks["DBAP"] = contact
    return ExpectedMessage(step=step, round=round_, actor="insurer", abgabegrund="62",
                           head=_head(sc, step, "62", insurer=True), blocks=blocks, note="end of benefit (TEEK0)")


# ---------------------------------------------------------------- chains


def decide(kb: KnowledgeBase, sc: Scenario, version: str) -> Decision41:
    return rules.decide(sc.test_case.inputs, params_mod.load(kb, version=version))


def build_chain(kb: KnowledgeBase, sc: Scenario, version: str) -> ChainResult:
    p = params_mod.load(kb, version=version)
    d = decide(kb, sc, version)
    res = ChainResult(version=version, messages=[], decision=d, traces={"41": d.trace})
    if not d.send:
        return res
    m41 = msg_41(sc, d.chain)
    res.messages.append(m41)
    if sc.test_case.steps != "chain":
        return res
    i = sc.test_case.inputs
    cur = i.current
    own = rules.employer_efz_days(cur, i.priors, p)  # E-4
    first = msg_61(sc, d.chain, "first_61", 2, 1, m41.head["DATENSATZ-ID"])
    efz1, t1 = efz_end(cur.start, first.blocks["DBVO"]["groups"], p, own, i.employment_end)
    m01 = msg_01(sc, 3, 2, efz1)
    if not i.insurer_corrects:  # one round: 41, the insurer's 61, the 01 (TA 167)
        res.messages += [first, m01]
        res.values["efz"] = {"after_first_61": efz1}
        res.traces.update(efz_first=t1)
        return res
    corrected = msg_61(sc, d.chain, "corrected_61", 4, 2, m41.head["DATENSATZ-ID"])
    efz2, t2 = efz_end(cur.start, corrected.blocks["DBVO"]["groups"], p, own, i.employment_end)
    res.messages += [first, m01, corrected]
    res.values["efz"] = {"after_first_61": efz1, "after_corrected_61": efz2}
    # E-3: an update that only sets interim flags (KZ-AU 3, KZ-AK-AU 4) does not replace the first 61
    replaces = rules.supersedes(first.blocks["DBVO"], corrected.blocks["DBVO"])
    res.values["corrected_61_replaces_first"] = replaces
    res.traces.update(efz_first=t1, efz_corrected=t2)
    efz = efz2 if replaces else efz1
    latest_01, step = m01, 5
    if efz != efz1:  # E-2: corrected 61 changes the EFZ end -> 88 + new 01
        m88 = msg_88(sc, 5, 3, m01)
        new01 = msg_01(sc, 6, 3, efz)
        res.messages += [m88, new01]
        latest_01, step = new01, 7
    benefit_start = efz + timedelta(days=1)
    res.messages.append(msg_62(sc, step, 3, latest_01.head["DATENSATZ-ID"], benefit_start))
    return res


def single_step_reply(sc: Scenario, ch: ChainResult) -> ExpectedMessage | None:
    """The insurer's 61 for a single-step test (round 1 only), default flags."""
    if not ch.messages:
        return None
    m41 = ch.messages[0]
    return msg_61(sc, ch.decision.chain, "corrected_61", 2, 1, m41.head["DATENSATZ-ID"])
