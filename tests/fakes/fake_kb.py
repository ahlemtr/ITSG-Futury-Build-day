"""In-memory knowledge base for backend tests (decision D1 of BACKEND_IMPLEMENTATION_PLAN.md).

Implements `kg.interface.KnowledgeBase` with the values of plan/03 (parameters, rules, Peter and
clones) and plan/08 (rules table, compare modes, message type blocks, curated changes). Layouts are
read from `layouts/`, passages from `tests/fakes/passages.yaml` (real text of VB 13.3 / 13.4
section 3.12, BP 13.1 / 13.2 and the 4 BVORERK criteria). Replace with the KG teammate's
`yaml_backend` as soon as it exists (P9.1).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from engine.model import (
    AuPeriod,
    BlockUse,
    Change,
    DeviationContext,
    ExpectedOutcome,
    Field,
    Graph,
    GraphEdge,
    GraphNode,
    Impact,
    Layout,
    Parameter,
    ParamValue,
    Passage,
    Precedent,
    RepeatingGroup,
    Rule,
    SpecRef,
    TestCase,
    TestCaseRef,
    TestInputs,
    Version,
    base_field_name,
)

ROOT = Path(__file__).resolve().parents[2]
D = date.fromisoformat

VERSIONS = {
    "VB": [
        Version(document="VB", version="13.3", published=D("2025-11-24"), valid_from=D("2026-01-01")),
        Version(document="VB", version="13.4", published=D("2026-03-10"), valid_from=D("2027-01-01"), succeeds="13.3"),
    ],
    "BP": [Version(document="BP", version="13.3", published=D("2026-03-10"), valid_from=D("2027-01-01"))],
    "BVORERK": [Version(document="BVORERK", version="1", valid_from=D("2027-01-01"))],
}

PARAMS = {  # name: (13.3, 13.4, sim-13.5, sources)
    "min_total_days": (30, 30, 28, ["3.12/conditions"]),
    "gap_months": (6, 6, 6, ["3.12/conditions", "3.12/chaining"]),
    "gap_inclusive": (False, True, True, ["3.12/chaining"]),
    "sum_window_months": (12, 12, 12, ["3.12/conditions"]),
    "open_end_days": (7, 7, 7, ["3.12/conditions"]),
    "efz_days": (42, 42, 42, ["3.12.5"]),
}


def _vb(*secs: str) -> list[str]:
    return [f"VB@{v}#{s}" for s in secs for v in ("13.3", "13.4")]


# id, kind, applies_to, fields, params, sources, criterion, title
RULES_TABLE: list[tuple] = [
    ("R41-1", "domain", ["41"], ["DBVO.AU-AB-AG"], [], _vb("3.12/conditions") + ["BVORERK@1#f41c7278"],
     "f41c7278-b5a5-4ec3-b321-39bca5c3aeeb", "41 only if the current AU and at least one prior AU are certified"),
    ("R41-2", "domain", ["41"], ["DBVO.BEGINN-AU", "DBVO.ENDE-AU", "DBVO.AU-AB-AG"], ["gap_months", "gap_inclusive"],
     _vb("3.12/chaining") + ["BVORERK@1#0cefe80e"], "0cefe80e-4fd9-41e1-be4f-3ae1ecbde646",
     "gap between current AU start and last prior AU end at most gap_months"),
    ("R41-3", "domain", ["41"], ["DBVO.BEGINN-AU", "DBVO.ENDE-AU"], ["gap_months", "gap_inclusive"],
     _vb("3.12/chaining", "3.12.7") + ["BP@13.3#13.2", "BVORERK@1#aade0289"], "aade0289-e8f9-4e12-9c49-464cf6cd0789",
     "chain back: include a prior AU only while the gap to the next one is at most gap_months"),
    ("R41-4", "domain", ["41"], ["DBVO.BEGINN-AU", "DBVO.ENDE-AU", "DBVO.AU-AB-AG"], ["min_total_days", "sum_window_months"],
     _vb("3.12/conditions") + ["BVORERK@1#9c8c9b58"], "9c8c9b58-4d0f-4066-98ac-973095418d63",
     "prior days in the last sum_window_months + current AU days at least min_total_days"),
    ("R41-5", "domain", ["41"], ["DBVO.BEGINN-AU", "DBVO.ENDE-AU"], [], _vb("3.12/chaining"), None,
     "uncertified short absences are never listed"),
    ("R41-6", "domain", ["41"], ["DBVO.AU-AB-AG"], ["open_end_days"], _vb("3.12/conditions"), None,
     "open-ended current AU counts until report date + open_end_days - 1"),
    ("F41-1", "format", ["41"], ["DSLW.ABGABEGRUND"], [], _vb("3.1.18"), None, "ABGABEGRUND = 41"),
    ("F41-2", "format", ["41"], ["DSLW.KORR-ABGABEGRUND"], [], _vb("3.1.19"), None, "KORR-ABGABEGRUND = 00"),
    ("F41-3", "format", ["41"], ["DSLW.MM-VOER", "DSLW.MM-ANSPRECH", "DSLW.MM-ID", "DSLW.MM-NAME", "DSLW.MM-ANSCHRIFT"],
     [], _vb("3.1") + ["BP@13.3#13.1"], None, "MM-VOER = J and every MM flag matches the blocks present"),
    ("F41-4", "format", ["41"], ["DBVO.GRUNDAV"], [], _vb("3.12.1"), None, "GRUNDAV = 1"),
    ("F41-5", "format", ["41"], ["DBVO.AU-AB-AG"], [], _vb("3.12.2"), None, "AU-AB-AG = current AU start"),
    ("F41-6", "format", ["41"], ["DBVO.AU-AB-SV", "DBVO.KZ-AK-AU", "DBVO.12-MONATSFRIST-AB"], [],
     _vb("3.12.3", "3.12.4", "3.12.5"), None, "insurer-only fields are zero"),
    ("F41-7", "format", ["41"], ["DBVO.ANZAHL-AU"], [], _vb("3.12.6"), None, "ANZAHL-AU = number of groups, at least 1"),
    ("F41-8", "format", ["41"], ["DBVO.BEGINN-AU", "DBVO.ENDE-AU"], [], _vb("3.12.7"), None, "periods newest first"),
    ("F41-9", "format", ["41"], ["DBVO.KZ-NACHWEIS", "DBVO.TEIL-NACHWEIS-AU-BEGINN", "DBVO.TEIL-NACHWEIS-AU-ENDE",
                                 "DBVO.KZ-AU", "DBVO.TEIL-ANR-AU-BEGINN", "DBVO.TEIL-ANR-AU-ENDE"], [],
     _vb("3.12.9", "3.12.12"), None, "per group insurer-only fields are zero"),
    ("F41-10", "format", ["41"], ["DSLW.DATENSATZ-ID"], [], _vb("3.1.11"), None, "DATENSATZ-ID unique, 8-4-4-4-12 hex"),
    ("K61-1", "reply", ["61"], ["DBID.REFERENZ-ID"], [], _vb("3.19.3"), None, "REFERENZ-ID = DATENSATZ-ID of the 41"),
    ("K61-2", "reply", ["61"], ["DSLW.BBNR-VU"], [], _vb("3.1.10"), None, "BBNR-VU = the employer's BBNR-VU"),
    ("K61-3", "reply", ["61"], ["DBVO.BEGINN-AU", "DBVO.ENDE-AU"], [], _vb("3.12/insurer"), None,
     "same periods and order as the 41, extra periods appended"),
    ("K61-4", "reply", ["61"], ["DBVO.KZ-NACHWEIS"], [], _vb("3.12.9"), None, "KZ-NACHWEIS 1 present, 2 partly, 4 missing"),
    ("K61-5", "reply", ["61"], ["DBVO.KZ-AU", "DBVO.TEIL-ANR-AU-BEGINN", "DBVO.TEIL-ANR-AU-ENDE"], [],
     _vb("3.12.12", "3.12.13", "3.12.14"), None, "KZ-AU flags"),
    ("K61-6", "reply", ["61"], ["DBVO.12-MONATSFRIST-AB"], [], _vb("3.12.5"), None, "start of the 12-month period"),
    ("K61-7", "reply", ["61"], ["DBVO.KZ-AK-AU"], [], _vb("3.12.4"), None, "KZ-AK-AU 4 if the current note is missing"),
    ("K62-1", "reply", ["62"], ["DBID.REFERENZ-ID"], [], _vb("3.19.3"), None, "REFERENZ-ID = latest valid 01"),
    ("K62-2", "reply", ["62"], ["DBEE.EEL-ENDE", "DBEE.EEL-ENDE-GRUND"], [], _vb("3.7.3", "3.7.4"), None, "end of benefit"),
    ("E-1", "efz", ["01"], ["DBAL.DATUM-EGZBIS"], ["efz_days"], _vb("3.4.3"), None, "01 carries DATUM-EGZBIS = efz_end"),
    ("E-2", "efz", ["01", "88"], ["DBAL.DATUM-EGZBIS", "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG"], ["efz_days"],
     ["GG@13.1#2.5", "BP@13.3#23"], None, "a corrected 61 that changes efz_end requires 88 + new 01"),
    ("E-3", "efz", ["61"], ["DBVO.KZ-AK-AU", "DBVO.KZ-AU"], [], _vb("3.12.4", "3.12.12"), None,
     "interim flag changes do not cancel the earlier 61"),
    ("C-1", "chain", ["01", "41", "88"], ["DSLW.DATENSATZ-ID"], [], _vb("3.1.11"), None, "unique DATENSATZ-ID"),
    ("C-2", "chain", ["01", "41", "88"], ["DBID.AKTENZEICHEN-VERURSACHER", "DBSD.AKTENZEICHEN-VERURSACHER"], [],
     _vb("3.19.2", "3.20"), None, "AKTENZEICHEN-VERURSACHER identical across the case"),
    ("C-3", "chain", ["88"], ["DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG"], [], _vb("3.20") + ["GG@13.1#2.5"], None,
     "88 points to the 01 being cancelled"),
    ("C-4", "chain", ["88"], ["DBSD.VORNAME", "DBSD.FAMILIENNAME"], [], _vb("3.20"), None,
     "88 names = names in the cancelled record"),
    ("C-5", "chain", ["01", "88"], ["DSLW.ABGABEGRUND"], [], ["GG@13.1#2.5"], None, "new 01 comes after the 88"),
    ("C-6", "chain", ["62"], ["DBEE.EEL-ENDE"], [], _vb("3.7.3"), None, "62 end not after the end of employment"),
    ("C-7", "chain", ["61"], ["DBID.AKTENZEICHEN-VERURSACHER"], [], _vb("3.19.2"), None, "61 echoes AZVU"),
    ("C-8", "chain", ["88"], ["DSLW.MM-SD"], [], _vb("3.20") + ["BP@13.3#23"], None, "88 carries only DBSD"),
]

BLOCKS = [
    ("41", "DBNA", "MM-NAME", True), ("41", "DBAN", "MM-ANSCHRIFT", "unknown"), ("41", "DBVO", "MM-VOER", True),
    ("41", "DBAP", "MM-ANSPRECH", "unknown"), ("41", "DBID", "MM-ID", "unknown"),
    ("61", "DBNA", "MM-NAME", True), ("61", "DBVO", "MM-VOER", True), ("61", "DBAP", "MM-ANSPRECH", "unknown"),
    ("61", "DBID", "MM-ID", True), ("01", "DBNA", "MM-NAME", True), ("01", "DBAL", "MM-ALLGEMEIN", True),
    ("01", "DBAE", "MM-ENTGELT", True), ("01", "DBAP", "MM-ANSPRECH", "unknown"), ("01", "DBID", "MM-ID", "unknown"),
    ("88", "DBSD", "MM-SD", True), ("62", "DBNA", "MM-NAME", True), ("62", "DBEE", "MM-EELENDE", True),
    ("62", "DBAP", "MM-ANSPRECH", "unknown"), ("62", "DBID", "MM-ID", True),
]

COMPARE_IGNORE = {"DSLW.DATUM-ERSTELLUNG", "DSLW.DATUM-VERARBEITUNG", "DBID.AKTENZEICHEN-SV", "DBNA.UNKLAR"}
COMPARE_RULE = {"DSLW.DATENSATZ-ID", "DSLW.PRODUKT-IDENTIFIER", "DSLW.MODIFIKATIONS-IDENTIFIER", "DSLW.ABSENDERNUMMER",
                "DSLW.ABRECHNUNGSPROGRAMM", "DBID.AKTENZEICHEN-VERURSACHER", "DBID.REFERENZ-ID",
                # not in plan/08 section 8 yet: both point to other messages, like REFERENZ-ID (C-3, C-2)
                "DBSD.DATENSATZ-ID-URSPRUNGSMELDUNG", "DBSD.AKTENZEICHEN-VERURSACHER"}

CHANGES = [
    Change(key="VB-13.3-13.4-DBVO-chaining", tag="replace", block="DBVO", in_scope=True, label="editorial",
           summary='6-month chaining wording, "nicht mindestens" became "nicht mehr als"',
           old="nicht mindestens 6 Monate vergangen sind", new="nicht mehr als 6 Monate vergangen sind",
           changes_param=["gap_inclusive"], modifies_old=["VB@13.3#3.12/chaining"], modifies_new=["VB@13.4#3.12/chaining"]),
    Change(key="VB-13.3-13.4-BBNR-VU", tag="replace", block="DSLW", field="BBNR-VU", in_scope=True, label="clarification",
           summary="insurer replies carry the employer's BBNR-VU",
           modifies_old=["VB@13.3#3.1.10"], modifies_new=["VB@13.4#3.1.10"]),
    Change(key="VB-13.3-13.4-DBID-AZVU", tag="replace", block="DBID", field="AKTENZEICHEN-VERURSACHER", in_scope=True,
           label="clarification", summary="AZVU returned unchanged, blank if the employer sent none",
           modifies_old=["VB@13.3#3.19.2"], modifies_new=["VB@13.4#3.19.2"]),
    Change(key="VB-13.3-13.4-DBSD-names", tag="insert", block="DBSD", in_scope=True, label="clarification",
           summary="VORNAME and FAMILIENNAME of the 88 are the names in the cancelled record",
           modifies_old=["VB@13.3#3.20"], modifies_new=["VB@13.4#3.20"]),
    Change(key="VB-13.3-13.4-DBEE-end", tag="replace", block="DBEE", field="EEL-ENDE", in_scope=True, label="clarification",
           summary="if benefit continues after employment ends, confirm only up to the end of employment",
           modifies_old=["VB@13.3#3.7.3"], modifies_new=["VB@13.4#3.7.3"]),
]

PETER_PRIORS = [("2025-07-14", "2025-07-15"), ("2025-10-01", "2025-10-17"), ("2025-12-01", "2025-12-03"),
                ("2026-03-01", "2026-03-03")]


def _p(s: str, e: str | None, c: bool = True) -> AuPeriod:
    return AuPeriod(start=D(s), end=D(e) if e else None, certified=c)


def _exp(send: bool, periods=(), total=None) -> ExpectedOutcome:
    return ExpectedOutcome(send_41=send, periods=[(D(a), D(b)) for a, b in periods], total_days=total)


def _same(o: ExpectedOutcome) -> dict[str, ExpectedOutcome]:
    return {"13.3": o, "13.4": o, "sim-13.5": o}


def _peter_case(id_, current_end, priors, expected, kind="clone", parent="peter", targets=None, hidden=False,
                current_start="2026-03-11", report="2026-03-11", employment_end="2026-03-31", steps="single"):
    return TestCase(
        id=id_, kind=kind, origin="itsg" if id_ == "peter" else "builder", status="approved", hidden=hidden,
        parent=parent, targets=targets or [], steps=steps,
        inputs=TestInputs(report_date=D(report), employment_end=D(employment_end),
                          current=_p(current_start, current_end), priors=priors),
        expected=expected,
    )


def _build_test_cases() -> dict[str, TestCase]:
    pp = [_p(a, b) for a, b in PETER_PRIORS]
    newest = list(reversed(PETER_PRIORS))
    r41 = [f"R41-{i}" for i in range(1, 7)]
    allr = r41 + [r[0] for r in RULES_TABLE if not r[0].startswith("R41")]
    peter = _peter_case("peter", "2026-03-20", pp, _same(_exp(True, newest, 35)), kind="reference", parent=None,
                        targets=allr, steps="chain")
    peter.sources = ["HINWEISE@1#facts", "HINWEISE@1#chain"]
    peter.efz_ends = {"after_first_61": D("2026-03-30"), "after_corrected_61": D("2026-03-27")}
    peter.chain = ["41", "61", "01", "61", "88", "01", "62"]
    cases = [peter]
    gap_t = ["R41-2", "R41-3"]
    ge = [("2025-08-07", "2025-09-11")]
    cases.append(_peter_case("peter-gap-exact", "2026-03-20", [_p(*ge[0])],
                             {"13.3": _exp(False), "13.4": _exp(True, ge, 46), "sim-13.5": _exp(True, ge, 46)}, targets=gap_t))
    cases.append(_peter_case("peter-gap-out", "2026-03-20", [_p("2025-08-06", "2025-09-10")], _same(_exp(False)), targets=gap_t))
    gi = [("2025-08-08", "2025-09-12")]
    cases.append(_peter_case("peter-gap-in", "2026-03-20", [_p(*gi[0])], _same(_exp(True, gi, 46)), targets=gap_t))
    for n, end in [(27, "2026-03-12"), (28, "2026-03-13"), (29, "2026-03-14"), (30, "2026-03-15")]:
        no, yes = _exp(False, newest, n), _exp(True, newest, n)
        exp = {"13.3": yes if n >= 30 else no, "13.4": yes if n >= 30 else no, "sim-13.5": yes if n >= 28 else no}
        cases.append(_peter_case(f"peter-b{n}", end, pp, exp, targets=["R41-4"]))
    noteless = [_p("2025-07-14", "2025-07-15"), _p("2025-10-01", "2025-10-17", False), _p("2025-12-01", "2025-12-03"),
                _p("2026-03-01", "2026-03-03")]
    cases.append(_peter_case("peter-noteless", "2026-03-20", noteless,
                             _same(_exp(False, [newest[0], newest[1], newest[3]], 18)), targets=["R41-1", "R41-5"]))
    from datetime import timedelta
    sh = timedelta(days=37)
    hp = [_p(str(D(a) + sh), str(D(b) + sh)) for a, b in PETER_PRIORS]
    hn = [(str(D(a) + sh), str(D(b) + sh)) for a, b in newest]
    cases.append(_peter_case("peter-hidden", str(D("2026-03-20") + sh), hp, _same(_exp(True, hn, 35)), kind="hidden",
                             hidden=True, targets=["R41-1", "R41-2", "R41-3", "R41-4"], current_start=str(D("2026-03-11") + sh),
                             report=str(D("2026-03-11") + sh), employment_end=str(D("2026-03-31") + sh)))
    gh = [("2025-07-27", "2025-08-31")]
    cases.append(_peter_case("peter-gap-exact-hidden", "2026-03-09", [_p(*gh[0])],
                             {"13.3": _exp(False), "13.4": _exp(True, gh, 46), "sim-13.5": _exp(True, gh, 46)},
                             kind="hidden", parent="peter-gap-exact", hidden=True, targets=gap_t,
                             current_start="2026-02-28", report="2026-02-28"))

    def bp(id_, cur_s, cur_e, report, priors, exp, targets):
        return TestCase(id=id_, kind="reference", origin="beispielpapier", targets=targets, steps="single",
                        inputs=TestInputs(report_date=D(report), current=_p(cur_s, cur_e), priors=priors),
                        expected=_same(exp), sources=[f"BP@13.3#{id_[3:].replace('-', '.')}"])

    cases.append(bp("bp-13-1", "2026-08-31", None, "2026-08-31", [_p("2026-06-01", "2026-06-25")],
                    _exp(True, [("2026-06-01", "2026-06-25")], 32), ["R41-1", "R41-6"]))
    cases.append(bp("bp-13-2", "2026-08-31", None, "2026-08-31",
                    [_p("2026-06-01", "2026-06-25"), _p("2026-05-03", "2026-05-06"), _p("2025-10-01", "2025-10-28")],
                    _exp(True, [("2026-06-01", "2026-06-25"), ("2026-05-03", "2026-05-06")], 36), ["R41-3"]))
    cases.append(bp("bp-13-3", "2026-08-31", None, "2026-08-31", [_p("2026-01-10", "2026-01-28")], _exp(False), ["R41-2"]))
    cases.append(bp("bp-13-4", "2026-08-31", "2026-09-08", "2026-08-31",
                    [_p("2026-06-01", "2026-06-10"), _p("2026-05-03", "2026-05-06")], _exp(False), ["R41-4"]))
    cases.append(bp("bp-13-5", "2026-08-31", None, "2026-09-02",
                    [_p("2026-06-01", "2026-06-10"), _p("2026-05-03", "2026-05-06")], _exp(False), ["R41-6"]))
    return {c.id: c for c in cases}


class FakeKB:
    def __init__(self) -> None:
        self.precedents: dict[str, Precedent] = {}
        self.test_cases = _build_test_cases()
        self.rules = [
            Rule(id=r[0], kind=r[1], applies_to=r[2], fields=r[3], params=r[4], sources=r[5], criterion=r[6], title=r[7])
            for r in RULES_TABLE
        ]
        self.params = {
            n: Parameter(name=n, values=[ParamValue(version="13.3", valid_from=D("2026-01-01"), value=a),
                                         ParamValue(version="13.4", valid_from=D("2027-01-01"), value=b),
                                         ParamValue(version="sim-13.5", value=c, simulated=True)],
                         sources=_vb(*s))
            for n, (a, b, c, s) in PARAMS.items()
        }
        data = yaml.safe_load((ROOT / "tests/fakes/passages.yaml").read_text(encoding="utf-8"))
        self.passages = {p["key"]: Passage(**p) for p in data["passages"]}
        self._layouts: dict[str, Layout] = {}

    # ------------------------------------------------------------ layouts
    def get_layout(self, record: str, version: str) -> Layout:
        if record not in self._layouts:
            path = ROOT / "layouts" / f"{record}.yaml"
            if not path.exists():
                raise KeyError(record)
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            status = raw.get("status", "extracted")

            def mk(f: dict, repeating: bool) -> Field:
                name = base_field_name(f["name"]) if repeating else f["name"]
                return Field(name=name, start=f["start"], end=f["end"], length=f["length"], type=f["type"].lower(),
                             required=f.get("required", "M"), format=f.get("format"), constant=f.get("constant"),
                             values=f.get("values"), source=f.get("source"), repeating=repeating,
                             offset_in_group=f.get("offset_in_group"), status=status,
                             compare_mode=self._compare_mode(record, name, f))

            rg = raw.get("repeating_group")
            self._layouts[record] = Layout(
                record=record, title=raw.get("title", ""), section=raw["spec"]["section"], page=raw["spec"].get("page"),
                status=status, fixed_length=raw["fixed_length"], fields=[mk(f, False) for f in raw["fields"]],
                repeating_group=RepeatingGroup(count_field=rg["count_field"], starts_at=rg["starts_at"],
                                               group_length=rg["group_length"], fields=[mk(f, True) for f in rg["fields"]])
                if rg else None,
                block_order=raw.get("block_order", []),
                announced_by=(raw.get("announced_by") or {}).get("field"),
            )
        return self._layouts[record]

    @staticmethod
    def _compare_mode(record: str, name: str, f: dict) -> str:
        key = f"{record}.{name}"
        if key in COMPARE_IGNORE:
            return "ignore"
        if key in COMPARE_RULE or record == "DBAP":
            return "rule" if name != "KENNUNG" else "compare"
        if record in ("DBAE", "DBAL"):
            flag = f.get("format") == "date_yyyymmdd" or name.startswith(("MM-", "KZ-")) or name.endswith("GRUND")
            return "compare" if flag or name == "KENNUNG" else "ignore"
        return "compare"

    # ------------------------------------------------------------ rules and parameters
    def get_rules(self, abgabegrund: str, version: str) -> list[Rule]:
        out = []
        for r in self.rules:
            if abgabegrund in r.applies_to:
                srcs = [s for s in r.sources if not s.startswith("VB@") or s.startswith(f"VB@{version}#")]
                out.append(r.model_copy(update={"sources": srcs}))
        return out

    def get_param(self, name: str, version: str | None = None, on_date: date | None = None) -> Any:
        p = self.params[name]
        if version is not None:
            return next(v.value for v in p.values if v.version == version)
        if on_date is None:
            raise ValueError("get_param needs version or on_date")
        real = [v for v in p.values if not v.simulated and v.valid_from and v.valid_from <= on_date]
        if not real:
            raise LookupError(f"no value of {name} valid on {on_date}")
        return max(real, key=lambda v: v.valid_from).value

    def get_versions(self, document: str) -> list[Version]:
        return VERSIONS.get(document, [])

    # ------------------------------------------------------------ passages
    def get_passage(self, ref: SpecRef | str) -> Passage:
        key = ref.key if isinstance(ref, SpecRef) else ref
        if key in self.passages:
            return self.passages[key]
        raise KeyError(key)

    def search_passages(self, text: str, k: int = 5) -> list[Passage]:
        words = [w.lower() for w in re.findall(r"\w+", text) if len(w) > 2]
        scored = [(sum(p.text.lower().count(w) for w in words), p) for p in self.passages.values()]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda s: (-s[0], s[1].key))
        return [p for _, p in scored[:k]]

    # ------------------------------------------------------------ changes and impact
    def get_changes(self, document: str, old_version: str, new_version: str, in_scope_only: bool = True) -> list[Change]:
        if (document, old_version, new_version) != ("VB", "13.3", "13.4"):
            return []
        return [c for c in CHANGES if c.in_scope or not in_scope_only]

    def get_affected_rules(self, changes: list[str]) -> Impact:
        chs = [c for c in CHANGES if c.key in changes]
        params = {p for c in chs for p in c.changes_param}
        passages = {p for c in chs for p in c.modifies_old + c.modifies_new}
        recompute = [r for r in self.rules if set(r.params) & params]
        rids = {r.id for r in recompute}
        review = [r for r in self.rules if r.id not in rids and set(r.sources) & passages]
        tests = [self._ref(t) for t in self.test_cases.values() if set(t.targets) & rids]
        return Impact(recompute=recompute, review=review, tests=tests)

    # ------------------------------------------------------------ test cases
    @staticmethod
    def _ref(t: TestCase) -> TestCaseRef:
        return TestCaseRef(**t.model_dump(include=set(TestCaseRef.model_fields)))

    def get_test_cases(self, rule_id: str | None = None, include_hidden: bool = False) -> list[TestCaseRef]:
        return [self._ref(t) for t in self.test_cases.values()
                if (include_hidden or not t.hidden) and (rule_id is None or rule_id in t.targets)]

    def get_test_case(self, key: str) -> TestCase:
        return self.test_cases[key].model_copy(deep=True)

    # ------------------------------------------------------------ deviations and precedents
    def get_deviation_context(self, record: str, field: str, abgabegrund: str, version: str) -> DeviationContext:
        flag_blocks = [b for b in BLOCKS if b[0] == abgabegrund and (b[1] == record or b[2] == field)]
        key = f"{record}.{field}"
        rules = [r for r in self.get_rules(abgabegrund, version)
                 if key in r.fields or any(f.startswith(b[1] + ".") for b in flag_blocks for f in r.fields)]
        keys = [s for r in rules for s in r.sources]
        passages = [self.passages[k] for k in dict.fromkeys(keys) if k in self.passages]
        precedents = [p for s, p in self.precedents.items() if s.startswith(f"{abgabegrund}|{key}|")]
        return DeviationContext(rules=rules, passages=passages, precedents=precedents,
                                blocks=[BlockUse(type=b[0], record=b[1], flag=b[2], mandatory=b[3]) for b in flag_blocks])

    def add_precedent(self, p: Precedent) -> None:
        self.precedents[p.key] = p

    def find_precedent(self, signature: str) -> Precedent | None:
        return self.precedents.get(signature)

    def subgraph(self, label: str, key: str, depth: int = 1) -> Graph:
        if label == "Rule":
            r = next(r for r in self.rules if r.id == key)
            nodes = [GraphNode(label="Rule", key=key, props={"title": r.title})]
            edges = [GraphEdge(type="SOURCED_FROM", from_key=key, to_key=s) for s in r.sources]
            nodes += [GraphNode(label="Passage", key=s) for s in r.sources]
            return Graph(nodes=nodes, edges=edges)
        return Graph(nodes=[GraphNode(label=label, key=key)])
