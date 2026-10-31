"""Seed submissions by mutation.

Each submission = the expected employer files of its test case (one TEEL0 per round) with one
mutation applied. `python -m tools.make_submissions [out_dir]` writes them to disk.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from engine.expected import build_chain, load_scenario
from engine.model import ExpectedMessage
from engine.writer_messages import TEMPLATE, write_file
from kg.interface import KnowledgeBase


class SeedSubmission(BaseModel):
    id: str
    test_case_id: str
    content: str
    expected_label: dict[str, str]  # valid_on -> label
    expected_rules: list[str] = []
    files: dict[str, str]  # name -> text


Mutation = Callable[[list[ExpectedMessage]], list[ExpectedMessage]]


def _groups(msgs: list[ExpectedMessage]) -> list[dict]:
    return msgs[0].blocks["DBVO"]["groups"]


def m_three_periods(msgs):
    g = _groups(msgs)
    del g[1]  # drop 01.12-03.12.2025 (a middle period): oldest still listed
    return msgs


def m_missing_july(msgs):
    g = _groups(msgs)
    del g[-1]  # drop 14.07-15.07.2025, the oldest chained period
    return msgs


def m_wrong_order(msgs):
    _groups(msgs).reverse()
    return msgs


def m_stale_efz(msgs):
    first01 = next(m for m in msgs if m.abgabegrund == "01")
    msgs = [m for m in msgs if m.abgabegrund != "88"]
    second01 = [m for m in msgs if m.abgabegrund == "01"][1]
    second01.blocks["DBAL"]["DATUM-EGZBIS"] = first01.blocks["DBAL"]["DATUM-EGZBIS"]
    return msgs


def m_insurer_field(msgs):
    msgs[0].blocks["DBVO"]["AU-AB-SV"] = msgs[0].blocks["DBVO"]["AU-AB-AG"]
    return msgs


def m_no_contact(msgs):
    del msgs[0].blocks["DBAP"]
    return msgs


def m_variant(msgs):
    """Other DSIDs, timestamps, product id, sender data: rule and ignore fields only."""
    new_ids = {}
    for n, m in enumerate(msgs, 1):
        old = m.head["DATENSATZ-ID"]
        new_ids[old] = f"9A{n:06d}-1234-4ABC-8DEF-0000000000{n:02d}"
        m.head.update({"DATENSATZ-ID": new_ids[old], "DATUM-ERSTELLUNG": "20260312101500000000",
                       "PRODUKT-IDENTIFIER": "1234567", "MODIFIKATIONS-IDENTIFIER": "V2.0.1",
                       "ABSENDERNUMMER": "88812345"})
        if "DBAP" in m.blocks:
            m.blocks["DBAP"]["NAME"] = "Max Beispiel"
            m.blocks["DBAP"]["TELEFON"] = "030-1234567"
    for m in msgs:
        if "DBSD" in m.blocks:
            m.blocks["DBSD"]["DATENSATZ-ID-URSPRUNGSMELDUNG"] = new_ids[m.blocks["DBSD"]["DATENSATZ-ID-URSPRUNGSMELDUNG"]]
    return msgs


def m_none(msgs):
    return msgs


def m_legacy(msgs):
    """Vendor still on 13.3 logic: sends no 41."""
    return [m for m in msgs if m.abgabegrund != "41"]


SEEDS = [
    # id, test case, content, mutation, labels by valid_on, rules
    ("s-itsg-ref", "peter", "ITSG's real TEEL0 file for step 1 + generated rest of the chain", m_none,
     {"2027-01-01": "exact_match"}, []),
    ("s-variant", "peter", "different DSIDs, timestamps, product id, sender data", m_variant,
     {"2027-01-01": "exact_match"}, []),
    ("s-three-periods", "peter", "41 lists 3 of 4 periods", m_three_periods, {"2027-01-01": "correct_variant"}, []),
    ("s-missing-july", "peter", "July period dropped", m_missing_july, {"2027-01-01": "bug"}, ["R41-3"]),
    ("s-wrong-order", "peter", "periods oldest first", m_wrong_order, {"2027-01-01": "bug"}, ["F41-8"]),
    ("s-stale-efz", "peter", "second 01 still says 30.03, no 88", m_stale_efz, {"2027-01-01": "bug"}, ["E-1", "E-2"]),
    ("s-insurer-field", "peter", "AU-AB-SV filled by the employer", m_insurer_field, {"2027-01-01": "invalid"},
     ["F41-6"]),
    ("s-no-contact", "peter", "41 without DBAP (MM-ANSPRECH = N)", m_no_contact, {"2027-01-01": "unclear"}, []),
    ("s-legacy-1", "peter-gap-exact", "vendor still on 13.3 logic: no 41 sent", m_legacy,
     {"2026-11-01": "exact_match", "2027-01-01": "bug"}, ["R41-2"]),
    ("s-legacy-hidden", "peter-gap-exact-hidden", "same vendor, dates 31.08.2025 / 28.02.2026", m_legacy,
     {"2027-01-01": "bug"}, ["R41-2"]),
]


def _files(test_case_id: str, msgs: list[ExpectedMessage], kb: KnowledgeBase, itsg_round1: bool) -> dict[str, str]:
    files = {}
    for r in sorted({m.round for m in msgs}):
        name = f"TEEL0-{test_case_id}-r{r}"
        if r == 1 and itsg_round1:
            files[name] = TEMPLATE.read_bytes().decode("utf-8")
        else:
            files[name] = write_file([m for m in msgs if m.round == r], kb)
    return files


def build_submissions(kb: KnowledgeBase, version: str = "13.4") -> list[SeedSubmission]:
    out = []
    for sid, tc, content, mut, labels, rules in SEEDS:
        sc = load_scenario(kb, tc)
        msgs = [m.model_copy(deep=True) for m in build_chain(sc, version, kb).employer()]
        msgs = mut(msgs)
        out.append(SeedSubmission(id=sid, test_case_id=tc, content=content, expected_label=labels,
                                  expected_rules=rules, files=_files(tc, msgs, kb, sid == "s-itsg-ref")))
    return out


def labels_valid_on(s: SeedSubmission) -> list[date]:
    return [date.fromisoformat(d) for d in s.expected_label]


if __name__ == "__main__":
    from kg import get_kb

    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures/submissions")
    for s in build_submissions(get_kb()):
        d = out_dir / s.id
        d.mkdir(parents=True, exist_ok=True)
        for name, text in s.files.items():
            (d / name).write_bytes(text.encode("utf-8"))
        print(s.id, len(s.files), "file(s)")
