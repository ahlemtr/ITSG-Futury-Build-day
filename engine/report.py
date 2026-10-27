"""Report (P6.1, P6.2): JSON model, HTML via Jinja2, PDF via WeasyPrint (optional)."""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from engine.model import CheckResult
from engine.signing import sha256
from kg.interface import KnowledgeBase

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

OUTCOME_LABELS = {
    "exact_match": "Ohne Abweichung", "correct_variant": "Zulässige Variante", "bug": "Fehler festgestellt",
    "invalid": "Formal ungültig", "unclear": "Klärung erforderlich",
}
OUTCOME_SUMMARIES = {
    "exact_match": "Die Einreichung stimmt mit den erwarteten Meldungen und geprüften Regeln überein.",
    "correct_variant": "Die festgestellten Unterschiede wurden als zulässige Varianten eingeordnet.",
    "bug": "Die Prüfung hat fachliche Fehler festgestellt. Die betroffenen Meldungen und ihre Begründungen sind im Folgenden dokumentiert.",
    "invalid": "Die Einreichung erfüllt die geprüften formalen Anforderungen nicht. Die Feststellungen sind im Folgenden dokumentiert.",
    "unclear": "Mindestens eine Feststellung erfordert eine fachliche Klärung, bevor die Einreichung abschließend bewertet werden kann.",
}
KIND_LABELS = {
    "value_differs": "Abweichender Feldinhalt", "missing_block": "Fehlender Datenbaustein",
    "extra_block": "Zusätzlicher Datenbaustein", "missing_message": "Fehlende Meldung",
    "extra_message": "Zusätzliche Meldung", "missing_group": "Fehlende Wiederholungsgruppe",
    "extra_group": "Zusätzliche Wiederholungsgruppe", "order_differs": "Abweichende Reihenfolge",
}


@lru_cache(maxsize=4)
def _asset_uri(name: str, mime: str) -> str:
    """Self-contained exports: no remote logo/font requests or filesystem base URL needed."""
    return f"data:{mime};base64," + base64.b64encode((TEMPLATES / "assets" / name).read_bytes()).decode("ascii")


def _display_date(value, with_time: bool = False) -> str:
    if not value:
        return "–"
    try:
        parsed = datetime.fromisoformat(str(value))
        if with_time:
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC)
            return parsed.strftime("%d.%m.%Y · %H:%M UTC")
        return parsed.strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


class CheckLine(BaseModel):
    step: int | None
    abgabegrund: str | None
    record: str
    field: str | None
    kind: str
    outcome: str
    expected: str | None
    actual: str | None
    rule: str | None
    criterion: str | None
    sources: list[str]
    passage: str | None = None
    explanation: str
    resolved_by: str | None
    ai_proposal: dict | None = None


class InputFile(BaseModel):
    name: str
    sha256: str


class Report(BaseModel):
    submission_id: str
    test_case_id: str
    vendor: str | None = None
    product_id: str | None = None
    rule_set_version: str
    valid_on: date
    created: datetime
    label: str
    counts: dict[str, int]
    resolved_by: dict[str, int]
    expected_messages: int
    actual_messages: int
    files: list[InputFile]
    checks: list[CheckLine]
    chain: list[str] = []


def build(result: CheckResult, submission_id: str, files: dict[str, bytes | str], kb: KnowledgeBase,
          vendor: str | None = None, product_id: str | None = None, chain: list[str] | None = None,
          explanations: dict[str, str] | None = None) -> Report:
    checks = []
    for d in result.deviations:
        passage = None
        # the VB passage of the rule set version first, a 3.12 part ("/chaining") before a field passage
        for key in sorted(d.sources, key=lambda k: (not k.startswith(f"VB@{result.version}#"), "/" not in k, k)):
            try:
                passage = kb.get_passage(key).text
                break
            except KeyError:
                continue
        checks.append(CheckLine(
            step=d.step, abgabegrund=d.abgabegrund, record=d.record, field=d.field, kind=d.kind, outcome=d.label,
            expected=None if d.expected is None else str(d.expected),
            actual=None if d.actual is None else str(d.actual),
            rule=d.rule, criterion=d.criterion, sources=d.sources, passage=passage,
            explanation=(explanations or {}).get(d.id) or d.explanation, resolved_by=d.resolved_by,
            ai_proposal=d.ai_proposal.model_dump() if d.ai_proposal else None))
    return Report(
        submission_id=submission_id, test_case_id=result.test_case_id, vendor=vendor, product_id=product_id,
        rule_set_version=result.version, valid_on=result.valid_on, created=datetime.now(UTC),
        label=result.label, counts=result.counts, resolved_by=result.resolved_by,
        expected_messages=result.expected_messages, actual_messages=result.actual_messages,
        files=[InputFile(name=n, sha256=sha256(b)) for n, b in files.items()], checks=checks, chain=chain or [])


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))


def render_html(signed: dict) -> str:
    return _env().get_template("report.html.j2").render(
        r=signed["report"], sig=signed.get("signature"), outcomes=OUTCOME_LABELS,
        summaries=OUTCOME_SUMMARIES, kinds=KIND_LABELS, display_date=_display_date,
        logo=_asset_uri("itsg-logo.png", "image/png"),
        font_regular=_asset_uri("fira-sans-regular.woff", "font/woff"),
        font_medium=_asset_uri("fira-sans-medium.woff", "font/woff"),
        font_heading=_asset_uri("fira-sans-condensed-bold.woff", "font/woff"))


def render_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as e:  # WeasyPrint needs Pango: present in the Docker image
        raise RuntimeError(f"PDF rendering not available: {e}") from e
    return HTML(string=html).write_pdf()
